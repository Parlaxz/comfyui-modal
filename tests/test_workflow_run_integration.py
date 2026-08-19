"""Integration tests for ``studio_workflow_run.py`` — the Studio Workflow run lane.

Exercises the backend adapter end-to-end against a REAL temp-directory
``WorkflowDomainService`` (workflow + immutable version + mapping + preset),
mirroring the fixture patterns in ``test_workflow_domain.py`` /
``test_workflow_routes.py``:

* bundle resolution + runnable gates (fail closed, never guessed)
* strict control validation with verbatim 0 / 0.0 / False / "" preservation
* preset+override merging and verbatim prompt application (read-back asserts)
* frozen ``ExecutionPlan`` construction (production disabled path) with the
  modern identity metadata (NO legacy ``studio_preset_id`` keys)
* the V2 handler path through a FAKE ``PlaygroundService`` (injected at the
  most local seam: ``comfymodal_runtime.playground_service.PlaygroundService``)
* the v1/shadow handler path (submission-time REGISTRY history record with
  modern identity meta + patched ``direct_studio_run_completion``)
* ``history_v2_writer`` identity threading for modern vs legacy meta
* no silent fallback to any legacy preset execution for unrunnable versions
* the modern V2 FAILURE path: returned error dicts and raised exceptions at
  the accepted execution boundary are returned unchanged AND recorded as
  exactly one failed ``playground_run`` (real ``RunHistoryService`` + real
  V2 writer mirror), with the repaired workflow snapshot and no assets
* request-level failures (control validation / unrunnable gate) create ZERO
  history records; success never duplicates a failure record; the failure
  helper never masks the original error even when History itself fails

Deterministic + fast: temp dirs, no network, no Modal calls.
"""
from __future__ import annotations

import asyncio
import copy
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import studio_workflow_run as swr
from comfymodal_runtime.contracts import ExecutionPlan
from experiment_service import RunHistoryService
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store
from history_v2_writer import (
    _gen_id,
    get_writer,
    reset_writer_config,
    set_asset_resolver,
    set_writer_data_root,
    set_writer_enabled,
)
from studio_domain import WorkflowDomainService, derive_mapping_candidates
from workflow_metadata import prompt_sha256


def _run(coro):
    return asyncio.run(coro)


# ── Fixtures (standalone copies of the house patterns) ────────────────────


def make_capture(prompt_nodes: dict, graph_json=None) -> dict:
    return {
        "graph_json": graph_json or {"id": "g1", "nodes": []},
        "api_prompt_json": {"workflow": {}, "output": prompt_nodes},
    }


def txt2img_prompt(seed: int = 0, steps: int = 20, sampler: str = "euler") -> dict:
    return {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello world", "clip": ["4", 0]}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative", "clip": ["4", 0]}},
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["4", 0], "seed": seed, "steps": steps, "cfg": 7.0,
            "sampler_name": sampler, "scheduler": "normal",
            "positive": ["1", 0], "negative": ["2", 0], "latent_image": ["5", 0],
            "denoise": 1.0}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "krea_model.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
    }


def clip_repair_prompt(seed: int = 0, steps: int = 20, sampler: str = "euler") -> dict:
    """Representative immutable version: unique CLIPLoader node 62 and two
    CLIPTextEncode nodes (67 positive, 169 negative) whose ``clip`` inputs are
    ABSENT, wired text → sampler → output."""
    return {
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["62", 0], "seed": seed, "steps": steps, "cfg": 7.0,
            "sampler_name": sampler, "scheduler": "normal",
            "positive": ["67", 0], "negative": ["169", 0], "latent_image": ["5", 0],
            "denoise": 1.0}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
        "62": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors"}},
        "67": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello world"}},
        "169": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
    }


def fake_node_def(class_type: str):
    if class_type == "KSampler":
        return (
            {
                "model": ("MODEL",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "latent_image": ("LATENT",),
                "seed": ("INT", {"min": 0, "max": 281474976710655, "step": 1, "default": 0}),
                "steps": ("INT", {"min": 1, "max": 150, "step": 1, "default": 20}),
                "cfg": ("FLOAT", {"min": 0.0, "max": 30.0, "step": 0.5, "default": 7.0}),
                "sampler_name": (["euler", "dpmpp_2m"],),
                "scheduler": (["normal", "karras"],),
                "denoise": ("FLOAT", {"min": 0.0, "max": 1.0, "step": 0.01, "default": 1.0}),
            },
            {},
        )
    if class_type == "CLIPTextEncode":
        return ({"text": ("STRING", {"multiline": True}), "clip": ("CLIP",)}, {})
    if class_type == "EmptyLatentImage":
        return (
            {
                "width": ("INT", {"min": 16, "max": 8192, "step": 8}),
                "height": ("INT", {"min": 16, "max": 8192, "step": 8}),
                "batch_size": ("INT", {"min": 1, "max": 64}),
            },
            {},
        )
    if class_type == "CheckpointLoaderSimple":
        return ({"ckpt_name": (["krea_model.safetensors", "flux-dev.safetensors"],)}, {})
    if class_type == "CLIPLoader":
        return ({"clip_name": (["qwen_3_4b.safetensors", "clip_l.safetensors"],)}, {})
    if class_type == "SaveImage":
        return ({"images": ("IMAGE",), "filename_prefix": ("STRING", {"default": "ComfyUI"})}, {})
    return None


def default_values(prompt: dict | None = None) -> dict:
    prompt = prompt or txt2img_prompt()
    return {
        "positive_prompt": "hello world",
        "negative_prompt": "negative",
        "seed": prompt["3"]["inputs"]["seed"],
        "steps": prompt["3"]["inputs"]["steps"],
        "cfg": prompt["3"]["inputs"]["cfg"],
        "sampler": prompt["3"]["inputs"]["sampler_name"],
        "scheduler": prompt["3"]["inputs"]["scheduler"],
        "denoise": prompt["3"]["inputs"]["denoise"],
        "width": prompt["5"]["inputs"]["width"],
        "height": prompt["5"]["inputs"]["height"],
        "model": prompt["4"]["inputs"]["ckpt_name"],
    }


def clip_repair_values(prompt: dict | None = None) -> dict:
    """Values for ``clip_repair_prompt``: text/scalars map onto node 3/5/62/67/169."""
    prompt = prompt or clip_repair_prompt()
    return {
        "positive_prompt": prompt["67"]["inputs"]["text"],
        "negative_prompt": prompt["169"]["inputs"]["text"],
        "seed": prompt["3"]["inputs"]["seed"],
        "steps": prompt["3"]["inputs"]["steps"],
        "cfg": prompt["3"]["inputs"]["cfg"],
        "sampler": prompt["3"]["inputs"]["sampler_name"],
        "scheduler": prompt["3"]["inputs"]["scheduler"],
        "denoise": prompt["3"]["inputs"]["denoise"],
        "width": prompt["5"]["inputs"]["width"],
        "height": prompt["5"]["inputs"]["height"],
        "model": prompt["62"]["inputs"]["clip_name"],
    }


# ── Fake REGISTRY (mirrors test_studio_direct_run.py) ─────────────────────


class FakeRunHistory:
    def __init__(self) -> None:
        self._runs: dict[str, dict] = {}

    def record_run(self, **kwargs) -> dict:
        run_id = f"r_{len(self._runs) + 1}"
        rec = dict(kwargs)
        rec["run_id"] = run_id
        self._runs[run_id] = rec
        return rec

    def update_run(self, run_id: str, **kwargs) -> dict:
        if run_id in self._runs:
            self._runs[run_id].update(kwargs)
        return self._runs.get(run_id, {})

    def get_run(self, run_id: str) -> dict | None:
        return self._runs.get(run_id)


class FakeRegistry:
    def __init__(self) -> None:
        self._history = FakeRunHistory()

    def history(self) -> FakeRunHistory:
        return self._history


class FakePlaygroundService:
    """Stand-in for ``PlaygroundService`` recording the injected pipeline.

    Runs the SAME injected hooks the real service would run (load preset →
    build plan) so tests can assert on the built plan + identity bundle, then
    returns a canned result dict (result passthrough).  ``mode`` selects the
    deterministic failure behavior (both fail BEFORE ``save_history_fn``):

    * ``"ok"`` (default) — the canned success result.  Mirrors the real
      service's Stage-8 completion hook: the injected ``save_history_fn`` is
      ALWAYS invoked with the post-materialization result and the materialized
      paths, exactly like ``PlaygroundService.execute``.
    * ``"error"`` — returns ``{"status": "error", "message": error_message}``
      (mirrors the real service's plan/execute/materialize error returns).
    * ``"raise"`` — raises ``RuntimeError(error_message)`` (mirrors the real
      service's raised exceptions).

    ``canned_result`` overrides the default success dict so tests can model a
    realistic nested ``MappingProxyType`` / raw-materialization success payload.
    It is returned and passed to the injected ``save_history_fn`` RAW (exactly
    like the real service hands its raw Modal result to the completion hook) —
    the handler's own normalization thaws it and its strict JSON boundary
    catches non-JSON-serializable leaves.  ``materialized_paths`` is passed to
    the injected ``save_history_fn`` like the real service passes its
    materializer output.
    """

    instances: list["FakePlaygroundService"] = []
    mode = "ok"
    error_message = "deterministic fake execution failure"
    call_history_on_ok = True
    canned_result: dict | None = None
    materialized_paths: list | None = None

    def __init__(self, **kwargs) -> None:
        self.load_preset_fn = kwargs.get("load_preset_fn")
        self.validate_fn = kwargs.get("validate_fn")
        self.build_plan_fn = kwargs.get("build_plan_fn")
        self.save_history_fn = kwargs.get("save_history_fn")
        self.calls: list[dict] = []
        self.snapshot = None
        self.plan = None
        FakePlaygroundService.instances.append(self)

    async def execute(self, **kwargs) -> dict:
        self.calls.append(dict(kwargs))
        preset, snapshot, _ = await self.load_preset_fn(kwargs["preset_id"], kwargs["node_dir"])
        self.snapshot = snapshot
        self.plan, _ = self.build_plan_fn(
            preset, snapshot, kwargs["feature_id"], kwargs["controls"],
            modal_options=kwargs.get("modal_options"),
        )
        if self.mode == "raise":
            raise RuntimeError(self.error_message)
        if self.mode == "error":
            return {"status": "error", "message": self.error_message}

        if self.canned_result is not None:
            # RAW passthrough: the canned payload (nested MappingProxyType and
            # all) reaches the handler's normalization AND the capture callback
            # unthawed, exactly like the real service's raw Modal result.
            result = self.canned_result
        else:
            result = {
                "status": "ok",
                "runId": "run_fake_1",
                "runHistoryId": "run_fake_1",
                "experimentId": "exp_fake_1",
                "completed_at": "2026-01-01T00:00:00Z",
                "output_paths": [],
                "output_path": "",
                "timings": {},
                "meta": dict(self.plan.request_metadata) if self.plan is not None else {},
                "direct_run": True,
            }
        if self.call_history_on_ok and self.save_history_fn is not None:
            await self.save_history_fn(
                self.plan, result, result["runHistoryId"],
                status="completed", completed_at=result["completed_at"],
                materialized_paths=(
                    list(self.materialized_paths) if self.materialized_paths else None
                ),
            )
        return result


# ── Test case ─────────────────────────────────────────────────────────────


class WorkflowRunIntegrationTests(unittest.TestCase):
    """Behavior tests for the Studio Workflow run lane (studio_workflow_run)."""

    def setUp(self) -> None:
        FakePlaygroundService.mode = "ok"
        FakePlaygroundService.error_message = "deterministic fake execution failure"
        FakePlaygroundService.call_history_on_ok = True
        FakePlaygroundService.canned_result = None
        FakePlaygroundService.materialized_paths = None
        self._tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self._tmp.name))
        self.service = WorkflowDomainService(self.root)
        self.wf = self.service.create_workflow("Text2Img Workflow")
        self.version = self._capture_mapped(self.wf["workflow_id"])
        self.version_id = self.version["workflow_version_id"]
        self.preset = self.service.create_preset(
            self.version_id, "Preset A", values=default_values()
        )
        self.preset_id = self.preset["preset_id"]
        self.service.set_default_preset(self.wf["workflow_id"], self.preset_id)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ── helpers ──────────────────────────────────────────────────────────

    def _capture_mapped(self, workflow_id: str, prompt: dict | None = None) -> dict:
        prompt = prompt or txt2img_prompt()
        version = self.service.create_version_from_capture(
            workflow_id, make_capture(prompt)
        )
        mapping = self._mapping_payload(prompt)
        self.service.set_mapping(
            version["workflow_version_id"],
            entries=mapping["entries"], output_node_id=mapping["output_node_id"],
        )
        return version

    def _mapping_payload(self, prompt: dict | None = None) -> dict:
        capture = make_capture(prompt or txt2img_prompt())
        entries, output_node_id = derive_mapping_candidates(
            capture, node_def_provider=fake_node_def
        )
        return {
            "entries": {role: e.to_dict() for role, e in entries.items()},
            "output_node_id": output_node_id,
        }

    def _service_patcher(self):
        """Patch the module's domain-service factory to use the temp service
        (no dependency resolver → deterministic runnable states)."""
        return patch(
            "studio_workflow_run._get_domain_service",
            new=lambda node_dir: WorkflowDomainService(str(node_dir)),
        )

    def _bundle(self) -> dict:
        with self._service_patcher():
            return swr.resolve_workflow_run_bundle(
                self.wf["workflow_id"], self.version_id, self.preset_id, self.root
            )

    def _clip_repair_fixture(self) -> dict:
        """A second workflow+version+preset built from ``clip_repair_prompt``."""
        wf = self.service.create_workflow("Clip Repair Workflow")
        version = self._capture_mapped(wf["workflow_id"], clip_repair_prompt())
        preset = self.service.create_preset(
            version["workflow_version_id"], "Preset C",
            values=clip_repair_values(),
        )
        self.service.set_default_preset(wf["workflow_id"], preset["preset_id"])
        with self._service_patcher():
            bundle = swr.resolve_workflow_run_bundle(
                wf["workflow_id"], version["workflow_version_id"],
                preset["preset_id"], self.root,
            )
        self.assertEqual(bundle["status"], "ok")
        return bundle

    def _run_handler(self, controls=None, modal_options=None) -> dict:
        with self._service_patcher():
            return _run(swr.handle_workflow_run_async(
                self.wf["workflow_id"], self.version_id, self.preset_id,
                "txt2img", controls or {}, self.root,
                modal_options=modal_options,
            ))

    # ── modern V2 failure-path helpers ──────────────────────────────────

    def _real_history_setup(self):
        """Real ``RunHistoryService`` + configured V2 writer (temp roots).

        Mirrors ``test_history_v2_production_writer``'s strongest project
        pattern: the legacy writer's ``_v2_try_mirror_*`` callbacks mirror
        into the real History V2 writer at ``<v2_root>/.studio_history_v2``.
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(reset_writer_config)
        legacy_root = Path(tmp.name) / "legacy"
        v2_root = Path(tmp.name) / "v2"
        legacy_root.mkdir(parents=True, exist_ok=True)
        v2_root.mkdir(parents=True, exist_ok=True)
        svc = RunHistoryService(legacy_root)
        set_writer_data_root(v2_root)
        set_writer_enabled(True)
        db_path = v2_root / ".studio_history_v2" / "history_v2.db"
        repo = HistoryV2Repository(HistoryV2Store(db_path))
        return svc, legacy_root, v2_root, repo

    def _history_shim(self, svc):
        """Fake ``experiment_service`` module routing ``REGISTRY`` to *svc*."""
        fake_exp_module = types.ModuleType("experiment_service")

        class _Shim:
            def __init__(self, history):
                self._history = history

            def history(self):
                return self._history

        fake_exp_module.REGISTRY = _Shim(svc)
        return fake_exp_module

    def _c14_producer(
        self,
        run_root: Path,
        name: str = "c14_producer.png",
        asset_id: str = "ast_c13_producer",
    ) -> tuple[str, dict]:
        """Write a local LeaseRegistry-shaped producer asset; return
        ``(path, producer_record)`` for the ``set_asset_resolver`` seam."""
        import hashlib

        path = Path(run_root) / name
        path.write_bytes(b"c14-producer-png-bytes")
        record = {
            "asset_id": asset_id,
            "path": str(path),
            "mime_type": "image/png",
            "content_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
            "width": 512,
            "height": 512,
            "byte_size": path.stat().st_size,
            "variant": "main",
            "node_id": "6",
            "output_key": "images",
            "output_index": 0,
        }
        return str(path), record

    def _expected_repaired_workflow(self, bundle, overrides=None) -> tuple[dict, str]:
        """Rebuild the exact repaired workflow the failure helper must store.

        ``overrides`` (optional) lets a handler test thread the same text/
        scalar overrides it sent to ``handle_workflow_run_async`` so the
        expected snapshot matches the recorded one.
        """
        schema = bundle["control_schema"]
        merged = swr.merge_workflow_controls(bundle["preset"], overrides or {}, schema)
        self.assertEqual(merged["errors"], [])
        expected = copy.deepcopy(bundle["executable_prompt"])
        for role, entry in schema.items():
            node_id = str(entry["node_id"])
            input_name = str(entry["input_name"])
            expected[node_id]["inputs"][input_name] = merged["values"][role]
        expected["67"]["inputs"]["clip"] = ["62", 0]
        expected["169"]["inputs"]["clip"] = ["62", 0]
        return expected, prompt_sha256(expected)

    def _assert_failed_run(
        self,
        svc,
        repo,
        bundle,
        error_fragment,
        expected_workflow,
        expected_hash,
        window_start,
        window_end,
    ) -> str:
        """Assert the shared failed-run shape across V2 failure modes.

        Returns the accepted legacy ``run_id`` (for idempotency replays).
        """
        runs = svc.list_runs(kind="playground_run")["runs"]
        self.assertEqual(len(runs), 1, "exactly one accepted legacy record")
        record = runs[0]
        self.assertEqual(record["kind"], "playground_run")
        self.assertEqual(record["status"], "error")
        run_id = record["run_id"]
        self.assertTrue(run_id.startswith("r_"))

        # Duration uses the accepted start → terminal timestamps (never
        # frontend/output times): start falls inside the handler window and
        # terminal >= start with a nonnegative duration.
        started_dt = datetime.fromisoformat(str(record["started_at"]).replace("Z", "+00:00"))
        completed_dt = datetime.fromisoformat(
            str(record["completed_at"]).replace("Z", "+00:00")
        )
        self.assertGreaterEqual(completed_dt, started_dt)
        # start is truncated to whole seconds by the handler; floor the
        # window so second-boundary crossings never fail.
        self.assertLessEqual(window_start.replace(microsecond=0), started_dt)
        self.assertGreaterEqual(window_end, started_dt)
        summary = record.get("timing_summary") or {}
        duration = summary.get("duration_ms")
        if duration is None:
            self.fail("failed attempt must carry a duration_ms")
        self.assertGreaterEqual(float(duration), 0)

        # Legacy meta: modern identity + error + hash, no output/asset data.
        extra = record["extra"]
        self.assertTrue(extra.get("playground_run"))
        self.assertEqual(extra["studio_feature_id"], "workflow")
        self.assertEqual(extra["workflow_id"], bundle["workflow"]["workflow_id"])
        self.assertEqual(
            extra["workflow_version_id"], bundle["version"]["workflow_version_id"]
        )
        self.assertEqual(extra["preset_id"], bundle["preset"]["preset_id"])
        self.assertEqual(extra["workflow_hash"], expected_hash)
        self.assertEqual(record["workflow_hash"], expected_hash)
        self.assertEqual(extra["requested_controls"]["steps"], 20)
        self.assertIn(error_fragment, extra["error"])
        self.assertNotIn("output_paths", extra)
        self.assertNotIn("primary_asset_id", extra)
        self.assertEqual(record.get("output_path", ""), "")

        # V2: generation identity + failed attempt with the error text.
        detail = repo.get_generation(_gen_id(run_id))
        self.assertIsNotNone(detail)
        gen = detail.generation
        self.assertEqual(gen.workflow_id, bundle["workflow"]["workflow_id"])
        self.assertEqual(
            gen.workflow_version_id, bundle["version"]["workflow_version_id"]
        )
        self.assertEqual(gen.preset_id, bundle["preset"]["preset_id"])
        self.assertEqual(len(detail.attempts), 1)
        attempt = detail.attempts[0]
        self.assertEqual(attempt.status, "failed")
        self.assertIn(error_fragment, attempt.error or "")

        # Request snapshot: version identity + exact repaired workflow_json
        # (including the injected CLIP links on the fixture's encoders).
        snapshot = detail.request_snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(
            snapshot.workflow_version_id, bundle["version"]["workflow_version_id"]
        )
        self.assertEqual(snapshot.workflow, expected_workflow)
        self.assertEqual(snapshot.workflow_hash, expected_hash)

        # No asset / output is ever attached to a failed run.
        self.assertEqual(len(detail.assets), 0)
        self.assertIsNone(gen.featured_asset_id)
        return run_id

    def _executed_plan_snapshot(self) -> tuple[dict, str]:
        """Return the exact plan payload used by the V2 fake execution seam."""
        plan = FakePlaygroundService.instances[-1].plan
        self.assertIsNotNone(plan)
        serialized = plan.to_dict()
        return serialized["workflow"], serialized["workflow_hash"]

    # ── 1. bundle resolution + gate ──────────────────────────────────────

    def test_01_bundle_resolution_and_gate(self):
        bundle = self._bundle()
        self.assertEqual(bundle["status"], "ok")
        self.assertEqual(bundle["workflow"]["workflow_id"], self.wf["workflow_id"])
        self.assertEqual(
            bundle["version"]["workflow_version_id"], self.version_id
        )
        self.assertEqual(bundle["preset"]["preset_id"], self.preset_id)
        self.assertEqual(bundle["state"]["runnable"], True)
        self.assertIn("seed", bundle["control_schema"])
        self.assertIn("sampler", bundle["control_schema"])

        # Incomplete version (no mapping) → WORKFLOW_VERSION_NOT_RUNNABLE + reasons.
        bare = self.service.create_workflow("Bare")
        self.service.create_version_from_capture(bare["workflow_id"], make_capture(txt2img_prompt()))
        with self._service_patcher():
            err = swr.resolve_workflow_run_bundle(
                bare["workflow_id"], "", "", self.root
            )
        self.assertEqual(err["status"], "error")
        self.assertEqual(err["error_code"], "WORKFLOW_VERSION_NOT_RUNNABLE")
        self.assertTrue(err["reasons"])
        self.assertTrue(any("missing mapping" in r for r in err["reasons"]))

        # Preset version mismatch → PRESET_VERSION_MISMATCH.
        other = self.service.create_workflow("Other")
        other_version = self._capture_mapped(other["workflow_id"])
        with self._service_patcher():
            err2 = swr.resolve_workflow_run_bundle(
                self.wf["workflow_id"], self.version_id,
                other_version["workflow_version_id"] + "_preset_does_not_exist",
                self.root,
            )
        # Unknown preset id → PRESET_NOT_FOUND (the mismatch arm needs a real
        # preset that belongs to a different version).
        self.assertEqual(err2["error_code"], "PRESET_NOT_FOUND")
        foreign_preset = self.service.create_preset(
            other_version["workflow_version_id"], "Foreign", values=default_values()
        )
        with self._service_patcher():
            err3 = swr.resolve_workflow_run_bundle(
                self.wf["workflow_id"], self.version_id,
                foreign_preset["preset_id"], self.root,
            )
        self.assertEqual(err3["status"], "error")
        self.assertEqual(err3["error_code"], "PRESET_VERSION_MISMATCH")

        # Unknown workflow → WORKFLOW_NOT_FOUND.
        with self._service_patcher():
            err4 = swr.resolve_workflow_run_bundle("wf_ghost", "", "", self.root)
        self.assertEqual(err4["error_code"], "WORKFLOW_NOT_FOUND")

    # ── 2. control validation verbatim ───────────────────────────────────

    def test_02_control_validation_verbatim(self):
        schema = self._bundle()["control_schema"]

        # 0 / 0.0 / False / "" preserved verbatim where their schema allows
        # them (custom schema mirrors test_workflow_routes.test_11: an
        # integer with min 0, a non-required float, a boolean, a non-required
        # string — every value must validate and never be coerced/dropped).
        custom_schema = {
            "seed": {"node_id": "1", "input_name": "seed", "kind": "node_input",
                     "control_kind": "integer", "data_type": "INT", "minimum": 0.0,
                     "maximum": 100, "required": True},
            "ratio": {"node_id": "1", "input_name": "ratio", "kind": "node_input",
                      "control_kind": "number", "data_type": "FLOAT",
                      "minimum": 0.0, "required": False},
            "enabled": {"node_id": "1", "input_name": "enabled", "kind": "node_input",
                        "control_kind": "boolean", "data_type": "BOOLEAN", "required": False},
            "label": {"node_id": "1", "input_name": "text", "kind": "node_input",
                      "control_kind": "string", "data_type": "STRING", "required": False},
        }
        verbatim = {"seed": 0, "ratio": 0.0, "enabled": False, "label": ""}
        errors = swr.validate_workflow_controls(verbatim, custom_schema)
        self.assertEqual(
            errors, [], f"verbatim 0 / 0.0 / False / '' must validate: {errors}"
        )

        # Derived-schema checks: legal txt2img values validate.
        good = {
            "positive_prompt": "hello world",
            "negative_prompt": "negative",
            "seed": 0, "steps": 20, "cfg": 0.0, "sampler": "euler",
            "scheduler": "normal", "denoise": 1.0, "width": 512, "height": 512,
            "model": "krea_model.safetensors",
        }
        errors = swr.validate_workflow_controls(good, schema)
        self.assertEqual(errors, [], f"legal values must validate: {errors}")

        # Unknown role rejected (never silently dropped).
        errors = swr.validate_workflow_controls({"not_a_control": 1}, schema)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["field"], "not_a_control")
        self.assertIn("unknown control", errors[0]["message"])

        # Enum exact: trailing-space sampler rejected; exact accepted.
        errors = swr.validate_workflow_controls(
            dict(good, sampler="euler "), schema
        )
        self.assertTrue(any(
            e["field"] == "sampler" and "must be one of" in e["message"]
            for e in errors
        ))
        errors = swr.validate_workflow_controls(good, schema)
        self.assertEqual(errors, [])

        # Required string must not be empty.
        bad = dict(good)
        bad["positive_prompt"] = "   "
        errors = swr.validate_workflow_controls(bad, schema)
        self.assertTrue(any(
            e["field"] == "positive_prompt" and "must not be empty" in e["message"]
            for e in errors
        ))

    # ── 3. merge + apply ─────────────────────────────────────────────────

    def test_03_merge_and_apply(self):
        bundle = self._bundle()
        schema = bundle["control_schema"]

        # Merge: preset base → overrides win → model_choices win for model.
        merged = swr.merge_workflow_controls(
            bundle["preset"], {"steps": 30}, schema
        )
        self.assertEqual(merged["errors"], [])
        self.assertEqual(merged["values"]["steps"], 30, "override wins")
        self.assertEqual(merged["values"]["seed"], 0, "preset value preserved verbatim")
        self.assertEqual(
            merged["values"]["model"], bundle["preset"]["values"]["model"]
        )

        # Merge surfaces invalid overrides as errors.
        merged_bad = swr.merge_workflow_controls(
            bundle["preset"], {"sampler": "definitely-not-a-sampler"}, schema
        )
        self.assertTrue(merged_bad["errors"])

        # Apply writes verbatim into the executable prompt; read-back passes.
        values = merged["values"]
        applied = swr.apply_workflow_values_to_prompt(
            bundle["executable_prompt"], schema, values
        )
        self.assertIn("workflow", applied)
        workflow = applied["workflow"]
        self.assertEqual(workflow["3"]["inputs"]["steps"], 30)
        self.assertEqual(workflow["3"]["inputs"]["seed"], 0)
        self.assertEqual(workflow["5"]["inputs"]["width"], 512)
        # Deep copy: original bundle executable_prompt untouched.
        self.assertEqual(bundle["executable_prompt"]["3"]["inputs"]["steps"], 20)

        # Missing node → error dict (never guesses).
        broken_schema = dict(schema)
        broken_schema["ghost_role"] = {
            "node_id": "999", "input_name": "x", "kind": "node_input",
        }
        err = swr.apply_workflow_values_to_prompt(
            bundle["executable_prompt"], broken_schema, {"ghost_role": 1}
        )
        self.assertIn("error", err)
        self.assertIn("not present", err["error"])

        # Missing input on an existing node → error dict.
        broken_schema2 = dict(schema)
        broken_schema2["ghost_input"] = {
            "node_id": "3", "input_name": "no_such_input", "kind": "node_input",
        }
        err2 = swr.apply_workflow_values_to_prompt(
            bundle["executable_prompt"], broken_schema2, {"ghost_input": 1}
        )
        self.assertIn("error", err2)
        self.assertIn("no_such_input", err2["error"])

    # ── 4. plan build ────────────────────────────────────────────────────

    def test_04_plan_build(self):
        bundle = self._bundle()
        schema = bundle["control_schema"]
        merged = swr.merge_workflow_controls(bundle["preset"], {}, schema)
        mapping_output = bundle["mapping"]["output_node_id"]

        plan, err = swr.build_workflow_execution_plan(
            bundle, merged["values"],
            modal_options={"production": {"enabled": False}},
        )
        self.assertIsNone(err)
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(plan.output_node_ids, (mapping_output,))
        self.assertTrue(plan.workflow_hash)

        meta = dict(plan.request_metadata)
        self.assertEqual(meta["workflow_id"], self.wf["workflow_id"])
        self.assertEqual(meta["workflow_version_id"], self.version_id)
        self.assertEqual(meta["preset_id"], self.preset_id)
        self.assertEqual(meta["workflow_name"], self.wf["name"])
        self.assertEqual(meta["preset_name"], "Preset A")
        self.assertEqual(meta["workflow_hash"], plan.workflow_hash)
        # Modern identity: NO legacy studio keys.
        self.assertNotIn("studio_preset_id", meta)
        self.assertNotIn("studio_snapshot_id", meta)
        self.assertNotIn("studio_preset_label", meta)

        # Mapping with no output node id → hard error.
        broken = dict(bundle)
        broken["mapping"] = dict(bundle["mapping"], output_node_id="")
        plan2, err2 = swr.build_workflow_execution_plan(
            broken, merged["values"],
            modal_options={"production": {"enabled": False}},
        )
        self.assertIsNone(plan2)
        self.assertIn("output node", err2)

    # ── 5. V2 handler path (fake PlaygroundService) ──────────────────────

    def test_05_v2_handler_path(self):
        """V2 success wiring through a fake PlaygroundService: controls reach
        the service verbatim, the identity bundle + plan carry modern identity,
        and the handler commits EXACTLY ONE completed history record AFTER the
        final result boundary (the capture-only save callback wrote nothing)."""
        fake_registry = FakeRegistry()
        fake_exp_module = types.ModuleType("experiment_service")
        fake_exp_module.REGISTRY = fake_registry
        out_file = Path(self._tmp.name) / "v2_handler_output.png"
        out_file.write_bytes(b"fake-png")
        FakePlaygroundService.instances.clear()
        FakePlaygroundService.materialized_paths = [str(out_file)]
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ):
            result = self._run_handler(
                controls={"steps": 30},
                modal_options={"execution_mode": "v2"},
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["runId"], "run_fake_1")
        # The normalized Stage-9 response is strict-JSON serializable.
        json.dumps(result)

        inst = FakePlaygroundService.instances[-1]
        self.assertEqual(len(inst.calls), 1)
        call = inst.calls[0]
        # Controls received = merged (preset + override), feature wired.
        self.assertEqual(call["controls"]["steps"], 30, "override reaches the service")
        self.assertEqual(call["controls"]["seed"], 0, "preset value survives verbatim")
        self.assertEqual(call["feature_id"], "workflow")
        self.assertEqual(call["node_dir"], self.root)
        self.assertEqual(call["modal_options"]["execution_mode"], "v2")

        # Identity bundle inside the injected load_preset snapshot.
        identity = inst.snapshot["identity"]
        self.assertEqual(identity["workflow_id"], self.wf["workflow_id"])
        self.assertEqual(identity["workflow_version_id"], self.version_id)
        self.assertEqual(identity["preset_id"], self.preset_id)
        self.assertEqual(identity["workflow_name"], self.wf["name"])
        self.assertEqual(identity["preset_name"], "Preset A")

        # The built plan carries modern identity and the applied workflow.
        self.assertIsNotNone(inst.plan)
        meta = dict(inst.plan.request_metadata)
        self.assertEqual(meta["workflow_id"], self.wf["workflow_id"])
        self.assertNotIn("studio_preset_id", meta)
        self.assertEqual(inst.plan.workflow["3"]["inputs"]["steps"], 30)

        # The handler wrote exactly ONE completed record after the boundary;
        # the capture-only injected callback created zero records by itself.
        records = list(fake_registry.history()._runs.values())
        self.assertEqual(len(records), 1, "exactly one completed record for success")
        self.assertEqual(records[0]["kind"], "playground_run")
        self.assertEqual(records[0]["status"], "completed")
        self.assertEqual(records[0]["meta"]["workflow_id"], self.wf["workflow_id"])
        self.assertIn("workflow_json", records[0]["meta"])

    # ── 6. v1/shadow handler path ────────────────────────────────────────

    def test_06_legacy_handler_path(self):
        fake_registry = FakeRegistry()
        fake_exp_module = types.ModuleType("experiment_service")
        fake_exp_module.REGISTRY = fake_registry

        async def fake_direct_completion(ctx, node_dir, **kwargs):
            return {
                "status": "ok",
                "runId": ctx.get("run_history_id") or "r_direct",
                "direct_run": True,
            }

        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "studio_run_adapter.direct_studio_run_completion",
            new=fake_direct_completion,
        ):
            result = self._run_handler(
                controls={"steps": 30},
                modal_options={"execution_mode": "v1"},
            )

        self.assertEqual(result["status"], "ok")

        records = list(fake_registry.history()._runs.values())
        self.assertEqual(len(records), 1, "submission record created for v1 path")
        record = records[0]
        self.assertEqual(record["kind"], "studio_run")
        # Recorded "submitted" then immediately moved to "running".
        self.assertIn(record["status"], ("submitted", "running"))
        meta = record["meta"]
        # Modern identity threading in the submission-time meta.
        self.assertEqual(meta["workflow_id"], self.wf["workflow_id"])
        self.assertEqual(meta["workflow_version_id"], self.version_id)
        self.assertEqual(meta["preset_id"], self.preset_id)
        self.assertEqual(meta["workflow_name"], self.wf["name"])
        self.assertEqual(meta["preset_name"], "Preset A")
        self.assertNotIn("studio_preset_id", meta)
        self.assertNotIn("studio_snapshot_id", meta)

    # ── 7. history_v2_writer identity threading ──────────────────────────

    def test_07_writer_identity_threading(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(reset_writer_config)
        writer = get_writer(tmp.name)
        db_path = Path(tmp.name) / ".studio_history_v2" / "history_v2.db"
        repo = HistoryV2Repository(HistoryV2Store(db_path))

        # Modern meta → generation columns carry the exact identity.
        writer.record_run(
            run_id="r_mod1", kind="studio_run", status="submitted",
            prompt_id="p", workflow_hash="h1",
            meta={
                "workflow_id": "wf_text2img",
                "workflow_version_id": "wv1_latest",
                "preset_id": "wpres_a",
                "preset_name": "Preset A",
                "workflow_name": "Text2Img",
                "workflow_json": {"4": {"class_type": "SaveImage", "inputs": {}}},
                "requested_controls": {"seed": 5, "steps": 20, "prompt": "x"},
            },
        )
        gen = repo.get_generation(_gen_id("r_mod1"))
        self.assertIsNotNone(gen)
        self.assertEqual(gen.generation.workflow_id, "wf_text2img")
        self.assertEqual(gen.generation.workflow_version_id, "wv1_latest")
        self.assertEqual(gen.generation.preset_id, "wpres_a")
        self.assertEqual(gen.generation.preset_name, "Preset A")
        self.assertEqual(gen.generation.prompt_text, "x")
        # Snapshot keeps workflow_version_id + workflow_json + params.
        self.assertEqual(gen.request_snapshot.workflow_version_id, "wv1_latest")
        self.assertEqual(
            gen.request_snapshot.workflow, {"4": {"class_type": "SaveImage", "inputs": {}}}
        )
        self.assertEqual(gen.request_snapshot.generation_params["seed"], 5)

        # Legacy record (meta without workflow_id) → workflow_id = workflow_hash.
        writer.record_run(
            run_id="r_leg1", kind="studio_run", status="submitted",
            prompt_id="p", workflow_hash="wfhash1",
            meta={
                "requested_controls": {"prompt": "a cat"},
                "studio_preset_id": "preset1",
                "studio_preset_label": "Preset One",
            },
        )
        gen2 = repo.get_generation(_gen_id("r_leg1"))
        self.assertEqual(gen2.generation.workflow_id, "wfhash1")
        self.assertEqual(gen2.generation.preset_id, "preset1")
        self.assertEqual(gen2.generation.preset_name, "Preset One")

        # update_run with a modern stored id + different workflow_hash keeps
        # the stored identity (no mismatch rewrite for non-hash ids).
        writer.update_run("r_mod1", status="completed", workflow_hash="h2")
        gen3 = repo.get_generation(_gen_id("r_mod1"))
        self.assertEqual(gen3.generation.workflow_id, "wf_text2img")
        self.assertEqual(gen3.attempts[0].status, "completed")

    # ── 8. no silent fallback ────────────────────────────────────────────

    def test_08_no_silent_fallback(self):
        bare = self.service.create_workflow("Unrunnable")
        self.service.create_version_from_capture(
            bare["workflow_id"], make_capture(txt2img_prompt())
        )

        async def _should_never_run(*args, **kwargs):
            self.fail("unrunnable version must never route to any execution path")

        with self._service_patcher(), patch(
            "studio_run_adapter.direct_studio_run_completion",
            new=_should_never_run,
        ):
            result = _run(swr.handle_workflow_run_async(
                bare["workflow_id"], "", "", "txt2img", {}, self.root,
                modal_options={"execution_mode": "v1"},
            ))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "WORKFLOW_VERSION_NOT_RUNNABLE")
        self.assertTrue(result["reasons"])

    # ── 9. plan build repairs missing CLIP/VAE inputs ────────────────────

    def test_09_plan_build_repairs_missing_clip_inputs(self):
        """Plan build injects the exact CLIP link on both active encoders and
        hashes the REPAIRED workflow (not the stored pre-repair prompt)."""
        bundle = self._clip_repair_fixture()
        schema = bundle["control_schema"]
        merged = swr.merge_workflow_controls(
            bundle["preset"], {"steps": 30}, schema
        )
        self.assertEqual(merged["errors"], [])

        # Precondition: stored executable_prompt has NO clip links.
        self.assertNotIn("clip", bundle["executable_prompt"]["67"]["inputs"])
        self.assertNotIn("clip", bundle["executable_prompt"]["169"]["inputs"])
        stored_pre_repair_hash = bundle["version"]["graph_hash"]
        self.assertEqual(
            stored_pre_repair_hash, prompt_sha256(bundle["executable_prompt"])
        )

        plan, err = swr.build_workflow_execution_plan(
            bundle, merged["values"],
            modal_options={"production": {"enabled": False}},
        )
        self.assertIsNone(err)
        self.assertIsInstance(plan, ExecutionPlan)

        # Frozen plan workflow, thawed for plain-dict comparisons.
        wf = swr._plain_copy(plan.workflow)

        # Exact repaired link on BOTH active encoders.
        self.assertEqual(wf["67"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(wf["169"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(wf["62"]["class_type"], "CLIPLoader")

        # Mapped text/scalar values still change only their intended keys.
        self.assertEqual(wf["67"]["inputs"]["text"], "hello world")
        self.assertEqual(wf["169"]["inputs"]["text"], "negative")
        self.assertEqual(wf["3"]["inputs"]["steps"], 30)
        self.assertEqual(wf["3"]["inputs"]["seed"], 0)
        self.assertIs(type(wf["3"]["inputs"]["seed"]), int)
        self.assertEqual(wf["62"]["inputs"]["clip_name"], "qwen_3_4b.safetensors")

        # Original bundle executable_prompt unchanged (no injected links).
        self.assertNotIn("clip", bundle["executable_prompt"]["67"]["inputs"])
        self.assertNotIn("clip", bundle["executable_prompt"]["169"]["inputs"])
        self.assertEqual(bundle["executable_prompt"]["3"]["inputs"]["steps"], 20)

        # Equivalence: identical to the stored prompt except the repaired
        # clip keys and the mapped scalar fields.
        expected = copy.deepcopy(bundle["executable_prompt"])
        for role, entry in schema.items():
            node_id = str(entry["node_id"])
            input_name = str(entry["input_name"])
            expected[node_id]["inputs"][input_name] = merged["values"][role]
        expected["67"]["inputs"]["clip"] = ["62", 0]
        expected["169"]["inputs"]["clip"] = ["62", 0]
        self.assertEqual(wf, expected)

        # workflow_hash == sha256(repaired plan workflow) and differs from the
        # stored pre-repair hash for the fixture.
        self.assertEqual(plan.workflow_hash, prompt_sha256(wf))
        self.assertNotEqual(plan.workflow_hash, stored_pre_repair_hash)
        self.assertEqual(plan.output_node_ids, (str(bundle["mapping"]["output_node_id"]),))

    # ── 10. repair helpers never overwrite and never guess ───────────────

    def test_10_repair_helpers_no_guess_and_no_overwrite(self):
        """The shared CLIP/VAE repair helpers only add missing links when a
        single unique loader exists and never overwrite existing links."""
        from studio_run_adapter import (
            _repair_missing_clip_inputs,
            _repair_missing_vae_inputs,
        )

        # Existing clip link is never overwritten.
        wf = {
            "62": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors"}},
            "67": {"class_type": "CLIPTextEncode", "inputs": {"text": "x", "clip": ["62", 0]}},
            "169": {"class_type": "CLIPTextEncode", "inputs": {"text": "y"}},
        }
        _repair_missing_clip_inputs(wf)
        self.assertEqual(wf["67"]["inputs"]["clip"], ["62", 0], "existing link preserved")
        self.assertEqual(wf["169"]["inputs"]["clip"], ["62", 0], "missing link added")

        # No CLIP loader → no guess.
        wf_no_loader = {"67": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}}}
        _repair_missing_clip_inputs(wf_no_loader)
        self.assertNotIn("clip", wf_no_loader["67"]["inputs"])

        # Multiple CLIP loaders → ambiguous, no guess.
        wf_ambiguous = {
            "62": {"class_type": "CLIPLoader", "inputs": {"clip_name": "a.safetensors"}},
            "71": {"class_type": "CLIPLoader", "inputs": {"clip_name": "b.safetensors"}},
            "67": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}},
        }
        _repair_missing_clip_inputs(wf_ambiguous)
        self.assertNotIn("clip", wf_ambiguous["67"]["inputs"])

        # VAE parity: missing added, existing preserved.
        wf_vae = {
            "9": {"class_type": "VAELoader", "inputs": {"vae_name": "v.safetensors"}},
            "10": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0]}},
        }
        _repair_missing_vae_inputs(wf_vae)
        self.assertEqual(wf_vae["10"]["inputs"]["vae"], ["9", 0])
        wf_vae2 = {
            "9": {"class_type": "VAELoader", "inputs": {"vae_name": "v.safetensors"}},
            "10": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["8", 0]}},
        }
        _repair_missing_vae_inputs(wf_vae2)
        self.assertEqual(wf_vae2["10"]["inputs"]["vae"], ["8", 0], "existing vae preserved")

    # ── 11. v1/shadow path repairs missing CLIP inputs too ───────────────

    def test_11_legacy_path_repairs_missing_clip_inputs(self):
        """The legacy v1 path applies the same CLIP repair before hashing."""
        bundle = self._clip_repair_fixture()
        wf_id = bundle["workflow"]["workflow_id"]
        version_id = bundle["version"]["workflow_version_id"]
        preset_id = bundle["preset"]["preset_id"]
        stored_pre_repair_hash = bundle["version"]["graph_hash"]

        fake_registry = FakeRegistry()
        fake_exp_module = types.ModuleType("experiment_service")
        fake_exp_module.REGISTRY = fake_registry
        captured: dict = {}

        async def fake_direct_completion(ctx, node_dir, **kwargs):
            captured["ctx"] = ctx
            return {
                "status": "ok",
                "runId": ctx.get("run_history_id") or "r_direct",
                "direct_run": True,
            }

        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "studio_run_adapter.direct_studio_run_completion",
            new=fake_direct_completion,
        ):
            result = _run(swr.handle_workflow_run_async(
                wf_id, version_id, preset_id, "txt2img", {}, self.root,
                modal_options={"execution_mode": "v1"},
            ))

        self.assertEqual(result["status"], "ok")
        ctx = captured["ctx"]
        compiled_workflow = ctx["compilation"]["checkpoints"][0]["workflow"]
        self.assertEqual(compiled_workflow["67"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(compiled_workflow["169"]["inputs"]["clip"], ["62", 0])
        # workflow_hash comes from the repaired workflow (≠ stored pre-repair).
        self.assertEqual(
            ctx["studio_meta"]["workflow_hash"], prompt_sha256(compiled_workflow)
        )
        self.assertNotEqual(ctx["studio_meta"]["workflow_hash"], stored_pre_repair_hash)


    # ── 12. V2 returned-error failure path ──────────────────────────────

    def test_12_v2_returned_error_records_failed_run(self):
        """A returned non-ok dict from the accepted execution boundary is
        returned UNCHANGED and recorded as exactly one failed
        ``playground_run`` (legacy + real V2 mirror) carrying the modern
        identity, the repaired workflow snapshot, and no assets.

        Also proves the execution-boundary stub itself receives the REPAIRED
        graph: the fake service the modern handler constructs captures a plan
        whose workflow carries the exact injected clip links on both active
        encoders, while its load snapshot still reflects the immutable
        run-context source (stored ``executable_prompt`` never mutated)."""
        svc, legacy_root, v2_root, repo = self._real_history_setup()
        fake_exp_module = self._history_shim(svc)
        bundle = self._clip_repair_fixture()

        # Small positive/negative text overrides: proves the handler applies
        # text changes onto the mapped fields without replacing the inputs
        # dict (the failure recording uses the same merged values).
        overrides = {
            "positive_prompt": "a red fox running through snow",
            "negative_prompt": "blurry, low quality",
        }
        expected_workflow, expected_hash = self._expected_repaired_workflow(
            bundle, overrides
        )
        self.assertNotEqual(expected_hash, bundle["version"]["graph_hash"])

        FakePlaygroundService.instances.clear()
        FakePlaygroundService.mode = "error"
        FakePlaygroundService.error_message = "deterministic returned error"

        wf_id = bundle["workflow"]["workflow_id"]
        version_id = bundle["version"]["workflow_version_id"]
        preset_id = bundle["preset"]["preset_id"]
        window_start = datetime.now(timezone.utc)
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ):
            result = _run(swr.handle_workflow_run_async(
                wf_id, version_id, preset_id, "txt2img", overrides, self.root,
                modal_options={"execution_mode": "v2"},
            ))
        window_end = datetime.now(timezone.utc)

        # The ORIGINAL error dict is returned unchanged (never re-raised or
        # swallowed) and the failure is recorded.
        self.assertEqual(
            result, {"status": "error", "message": "deterministic returned error"}
        )

        # The MODERN handler constructed the fake service, and its execution-
        # boundary stub received the REPAIRED graph directly (not merely a
        # separate history-helper reconstruction): the built plan's workflow
        # carries the exact injected clip link on BOTH active encoders.
        inst = FakePlaygroundService.instances[-1]
        self.assertIsNotNone(
            inst.plan, "modern handler must build the plan via the fake service"
        )
        stub_workflow = swr._plain_copy(inst.plan.workflow)
        self.assertEqual(stub_workflow["67"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(stub_workflow["169"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(stub_workflow["62"]["class_type"], "CLIPLoader")

        # The text override changes ONLY the mapped text fields: the inputs
        # dicts are updated in place (never replaced — their key set is text +
        # the repaired clip link) and the unmapped structural inputs remain.
        self.assertEqual(
            stub_workflow["67"]["inputs"]["text"], overrides["positive_prompt"]
        )
        self.assertEqual(
            stub_workflow["169"]["inputs"]["text"], overrides["negative_prompt"]
        )
        self.assertEqual(
            set(stub_workflow["67"]["inputs"]), {"text", "clip"},
            "67 inputs dict was replaced instead of updated in place",
        )
        self.assertEqual(
            set(stub_workflow["169"]["inputs"]), {"text", "clip"},
            "169 inputs dict was replaced instead of updated in place",
        )
        self.assertEqual(
            stub_workflow["62"]["inputs"],
            {"clip_name": "qwen_3_4b.safetensors"},
            "unmapped structural inputs must remain untouched",
        )
        self.assertEqual(stub_workflow["3"]["inputs"]["steps"], 20)
        self.assertEqual(
            inst.calls[0]["controls"]["positive_prompt"], overrides["positive_prompt"]
        )

        # The fake load/run snapshot reflects the immutable run-context
        # source: the stored executable_prompt is handed through untouched
        # (no clip links injected, no override applied) — the plan builder
        # and failure helper operate on deep copies only, never mutating the
        # source prompt.
        snapshot_source = inst.snapshot["executable_prompt"]
        self.assertEqual(snapshot_source, bundle["executable_prompt"])
        self.assertNotIn("clip", snapshot_source["67"]["inputs"])
        self.assertNotIn("clip", snapshot_source["169"]["inputs"])
        self.assertEqual(snapshot_source["67"]["inputs"]["text"], "hello world")
        self.assertEqual(snapshot_source["169"]["inputs"]["text"], "negative")
        self.assertEqual(snapshot_source["3"]["inputs"]["steps"], 20)
        self.assertNotIn("clip", bundle["executable_prompt"]["67"]["inputs"])
        self.assertNotIn("clip", bundle["executable_prompt"]["169"]["inputs"])

        run_id = self._assert_failed_run(
            svc, repo, bundle, "deterministic returned error",
            expected_workflow, expected_hash, window_start, window_end,
        )

        # First-terminal-wins through the real mirror: a completed replay
        # must NOT replace the failed terminal attempt.
        get_writer(v2_root).update_run(
            run_id, status="completed", completed_at="2026-01-02T00:00:00Z",
        )
        detail = repo.get_generation(_gen_id(run_id))
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "failed")
        self.assertIn("deterministic returned error", detail.attempts[0].error or "")

    # ── 13. V2 raised-exception failure path ────────────────────────────

    def test_13_v2_raised_exception_records_failed_run(self):
        """A raised exception from the accepted execution boundary is bounded,
        returned as the error result, and recorded as exactly one failed
        ``playground_run`` with the same message."""
        svc, legacy_root, v2_root, repo = self._real_history_setup()
        fake_exp_module = self._history_shim(svc)
        bundle = self._clip_repair_fixture()
        expected_workflow, expected_hash = self._expected_repaired_workflow(bundle)

        FakePlaygroundService.instances.clear()
        FakePlaygroundService.mode = "raise"
        FakePlaygroundService.error_message = "remote execution exploded"

        wf_id = bundle["workflow"]["workflow_id"]
        version_id = bundle["version"]["workflow_version_id"]
        preset_id = bundle["preset"]["preset_id"]
        window_start = datetime.now(timezone.utc)
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ):
            result = _run(swr.handle_workflow_run_async(
                wf_id, version_id, preset_id, "txt2img", {}, self.root,
                modal_options={"execution_mode": "v2"},
            ))
        window_end = datetime.now(timezone.utc)

        self.assertEqual(
            result, {"status": "error", "message": "remote execution exploded"}
        )
        self._assert_failed_run(
            svc, repo, bundle, "remote execution exploded",
            expected_workflow, expected_hash, window_start, window_end,
        )

    # ── 14. request-level failures create no history ────────────────────

    def test_14_request_failures_create_no_history(self):
        """Control-validation and unrunnable-gate failures happen BEFORE the
        accepted execution boundary: zero history records are created."""
        fake_registry = FakeRegistry()
        fake_exp_module = types.ModuleType("experiment_service")
        fake_exp_module.REGISTRY = fake_registry

        def _forbid_playground(*args, **kwargs):
            self.fail("PlaygroundService must not be constructed for request-level failures")

        # Invalid control override → WORKFLOW_CONTROL_VALIDATION, no history.
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            new=_forbid_playground,
        ):
            result = _run(swr.handle_workflow_run_async(
                self.wf["workflow_id"], self.version_id, self.preset_id,
                "txt2img", {"sampler": "not-a-sampler"}, self.root,
                modal_options={"execution_mode": "v2"},
            ))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "WORKFLOW_CONTROL_VALIDATION")
        self.assertEqual(len(fake_registry.history()._runs), 0)

        # Unrunnable version → WORKFLOW_VERSION_NOT_RUNNABLE, no history.
        bare = self.service.create_workflow("Unrunnable V2")
        self.service.create_version_from_capture(
            bare["workflow_id"], make_capture(txt2img_prompt())
        )
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            new=_forbid_playground,
        ):
            result = _run(swr.handle_workflow_run_async(
                bare["workflow_id"], "", "", "txt2img", {}, self.root,
                modal_options={"execution_mode": "v2"},
            ))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "WORKFLOW_VERSION_NOT_RUNNABLE")
        self.assertEqual(len(fake_registry.history()._runs), 0)

    # ── 15. success path: no duplicate failure record ───────────────────

    def test_15_v2_success_no_duplicate_failure_record(self):
        """Success commits exactly one completed record AFTER the final result
        boundary (accepted ``started_at`` drives ``record_run``, duration_ms in
        timing, output associated), never a duplicate failure record.

        Ordering proof: the capture-only injected callback wrote zero records
        by itself, the legacy record carries the accepted start inside the
        handler window with a nonnegative monotonic duration, and the completed
        V2 attempt + attached output exist only after the handler returned."""
        svc, legacy_root, v2_root, repo = self._real_history_setup()
        fake_exp_module = self._history_shim(svc)
        out_file = Path(self._tmp.name) / "v2_success_output.png"
        out_file.write_bytes(b"fake-png-bytes")
        FakePlaygroundService.instances.clear()
        FakePlaygroundService.mode = "ok"
        FakePlaygroundService.materialized_paths = [str(out_file)]

        window_start = datetime.now(timezone.utc)
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ):
            result = self._run_handler(
                controls={"steps": 30},
                modal_options={"execution_mode": "v2"},
            )
        window_end = datetime.now(timezone.utc)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(FakePlaygroundService.instances), 1)
        runs = svc.list_runs(kind="playground_run")["runs"]
        self.assertEqual(len(runs), 1, "exactly one legacy record for success")
        self.assertEqual(runs[0]["status"], "completed")
        self.assertNotEqual(runs[0]["status"], "error")

        # Ordering / accepted-start identity: record_run used the ACCEPTED
        # started_at (inside the handler window, before completed_at) and the
        # timing carries a monotonic duration including the accepted wait.
        record = runs[0]
        started_dt = datetime.fromisoformat(str(record["started_at"]).replace("Z", "+00:00"))
        completed_dt = datetime.fromisoformat(
            str(record["completed_at"]).replace("Z", "+00:00")
        )
        self.assertLessEqual(window_start.replace(microsecond=0), started_dt)
        self.assertGreaterEqual(window_end, started_dt)
        self.assertGreaterEqual(completed_dt, started_dt)
        timing_summary = record.get("timing_summary") or {}
        self.assertGreaterEqual(float(timing_summary.get("duration_ms", -1)), 0)
        self.assertEqual(timing_summary.get("_run_type"), "playground_direct")

        # Output association: the completed commit attached the materialized
        # file (top-level output_path + meta output_paths), no fabrication.
        self.assertEqual(record["output_path"], str(out_file))
        self.assertEqual(record["extra"]["output_paths"], [str(out_file)])
        self.assertIn("workflow_json", record["extra"])
        self.assertIn("requested_controls", record["extra"])

        run_id = runs[0]["run_id"]
        detail = repo.get_generation(_gen_id(run_id))
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail.attempts), 1)
        attempt = detail.attempts[0]
        self.assertEqual(attempt.status, "completed")
        self.assertFalse(any(a.status == "failed" for a in detail.attempts))
        self.assertGreaterEqual(float(attempt.timing.get("duration_ms", -1)), 0)
        self.assertGreaterEqual(len(detail.assets), 1)
        self.assertIsNotNone(detail.generation.featured_asset_id)

    # ── 16. writer/repository seam: first-terminal-wins (failed first) ──

    def test_16_completed_update_does_not_replace_failed_terminal(self):
        """A replayed completed update must NOT replace a failed terminal
        attempt (first-terminal-wins through the real writer/repository)."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(reset_writer_config)
        writer = get_writer(tmp.name)
        db_path = Path(tmp.name) / ".studio_history_v2" / "history_v2.db"
        repo = HistoryV2Repository(HistoryV2Store(db_path))
        run_id = "r_failed_terminal"
        failure_meta = {
            "playground_run": True,
            "workflow_id": "wf_terminal",
            "workflow_version_id": "wv_terminal",
            "preset_id": "p_terminal",
            "studio_feature_id": "workflow",
            "requested_controls": {"seed": 1},
            "error": "deterministic terminal failure",
            "workflow_json": {"1": {"class_type": "KSampler", "inputs": {}}},
            "workflow_hash": "wfhash_terminal",
        }
        writer.record_run(
            run_id=run_id, kind="playground_run", status="error",
            prompt_id="play_terminal", started_at="2026-01-01T00:00:00Z",
            meta=failure_meta, workflow_hash="wfhash_terminal",
        )
        writer.update_run(
            run_id, status="error", completed_at="2026-01-01T00:00:01Z",
            meta=failure_meta,
        )
        detail = repo.get_generation(_gen_id(run_id))
        self.assertEqual(detail.attempts[0].status, "failed")
        self.assertEqual(detail.attempts[0].error, "deterministic terminal failure")
        # A completed replay must not replace the failed terminal attempt.
        writer.update_run(
            run_id, status="completed", completed_at="2026-01-01T00:00:02Z",
        )
        detail = repo.get_generation(_gen_id(run_id))
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "failed")
        self.assertEqual(detail.attempts[0].error, "deterministic terminal failure")

    # ── 17. History failure never masks the original error ──────────────

    def test_17_failure_record_error_never_masks_original_error(self):
        """Even when History itself fails, the original execution error is
        returned unchanged (the failure helper is fully exception-isolated)."""

        class _BrokenHistory:
            def record_run(self, **kwargs):
                raise RuntimeError("history storage exploded")

            def update_run(self, *args, **kwargs):
                raise RuntimeError("history storage exploded")

        class _BrokenRegistry:
            def history(self):
                return _BrokenHistory()

        fake_exp_module = types.ModuleType("experiment_service")
        fake_exp_module.REGISTRY = _BrokenRegistry()

        FakePlaygroundService.instances.clear()
        FakePlaygroundService.mode = "error"
        FakePlaygroundService.error_message = "original execution failure"

        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ):
            result = self._run_handler(
                controls={}, modal_options={"execution_mode": "v2"},
            )

        self.assertEqual(
            result, {"status": "error", "message": "original execution failure"}
        )

    # ── 18. C11: accepted ok → local post-execution serialization failure ──

    def test_18_v2_success_post_execution_serialization_failure(self):
        """C11 boundary: the accepted execution returns SUCCESSFULLY, then the
        local post-execution serialization stage fails (the Stage-9 payload
        cannot pass the strict JSON boundary).  The API reports failure with
        the exact bounded error; exactly one failed Generation/Attempt is
        recorded with the repaired immutable snapshot, a plausible duration
        including the accepted wait, NO assets/featured, and first-terminal
        wins on a completed replay.  No History exists for this run before the
        failure record (pre-acceptance no History)."""
        svc, legacy_root, v2_root, repo = self._real_history_setup()
        fake_exp_module = self._history_shim(svc)
        bundle = self._clip_repair_fixture()
        overrides = {
            "positive_prompt": "a red fox running through snow",
            "negative_prompt": "blurry, low quality",
        }
        expected_workflow, expected_hash = self._expected_repaired_workflow(
            bundle, overrides
        )
        self.assertNotEqual(expected_hash, bundle["version"]["graph_hash"])

        # Pre-acceptance: NO history record exists for this run yet.
        self.assertEqual(len(svc.list_runs()["runs"]), 0)

        # Accepted execution "succeeds" (returns status ok) but carries a
        # payload that cannot survive the strict JSON boundary.  ``_plain_copy``
        # passes arbitrary unsupported objects through (never stringifies them),
        # so the handler's strict ``json.dumps`` fails truthfully.
        canned = {
            "status": "ok",
            "runId": "run_c11",
            "runHistoryId": "run_c11",
            "experimentId": "exp_c11",
            "completed_at": "2026-01-01T00:00:00Z",
            "output_paths": ["c11_fake.png"],
            "output_path": "c11_fake.png",
            "timings": {},
            "meta": {},
            "direct_run": True,
            "raw_payload": {"unserializable": object()},
        }
        try:
            json.dumps(swr._plain_copy(canned))
            self.fail("the canned C11 payload must fail strict JSON")
        except (TypeError, ValueError) as exc:
            expected_message = (
                f"v2 success result is not JSON serializable: {str(exc)[:200]}"
            )

        FakePlaygroundService.instances.clear()
        FakePlaygroundService.mode = "ok"
        FakePlaygroundService.canned_result = canned

        wf_id = bundle["workflow"]["workflow_id"]
        version_id = bundle["version"]["workflow_version_id"]
        preset_id = bundle["preset"]["preset_id"]
        window_start = datetime.now(timezone.utc)
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ):
            result = _run(swr.handle_workflow_run_async(
                wf_id, version_id, preset_id, "txt2img", overrides, self.root,
                modal_options={"execution_mode": "v2"},
            ))
        window_end = datetime.now(timezone.utc)

        # API failed with the EXACT bounded error (never a fabricated ok).
        self.assertEqual(result["status"], "error")
        self.assertEqual(
            result, {"status": "error", "message": expected_message}
        )

        # Exactly one failed record — the failure helper used the same accepted
        # run identity (prompt_id == canned runHistoryId) and no completed
        # record was ever made (no second record, no completed→failed repair).
        self.assertEqual(len(svc.list_runs()["runs"]), 1)
        self.assertEqual(svc.list_runs(kind="playground_run")["runs"][0]["prompt_id"], "run_c11")
        expected_workflow, expected_hash = self._executed_plan_snapshot()
        run_id = self._assert_failed_run(
            svc, repo, bundle, "not JSON serializable",
            expected_workflow, expected_hash, window_start, window_end,
        )

        # First-terminal-wins through the real mirror: a completed replay must
        # NOT replace the failed terminal attempt, and no asset is fabricated.
        get_writer(v2_root).update_run(
            run_id, status="completed", completed_at="2026-01-02T00:00:00Z",
        )
        detail = repo.get_generation(_gen_id(run_id))
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "failed")
        self.assertIn("not JSON serializable", detail.attempts[0].error or "")
        self.assertEqual(len(detail.assets), 0)
        self.assertIsNone(detail.generation.featured_asset_id)

    # ── 19. C12: production-shaped success with nested MappingProxyType ──

    def test_19_v2_success_production_shaped_output(self):
        """C12 production-shaped success: the accepted Stage-9 result carries
        realistic nested MappingProxyType / raw materialization fields plus a
        real materialized output file.  The strict API response stays JSON
        serializable with plain containers (nothing stringified), exactly one
        completed Generation/Attempt is recorded, the output file is attached
        as an asset with a featured association, and the stored snapshot
        preserves the sampling/geometry params and prompts — falsy values
        verbatim — with the repaired node 67 CLIP link + hash."""
        svc, legacy_root, v2_root, repo = self._real_history_setup()
        fake_exp_module = self._history_shim(svc)
        bundle = self._clip_repair_fixture()

        out_file = Path(self._tmp.name) / "c12_workflow_output.png"
        out_file.write_bytes(b"fake-png-materialized")
        overrides = {
            "steps": 30,
            "cfg": 0.0,
            "denoise": 0.0,
            "positive_prompt": "a red fox running through snow",
            "negative_prompt": "blurry, low quality",
        }

        trace_projection = types.MappingProxyType({
            "stages": {
                "browser_run_click": 1000.0,
                "result_received": 4000.0,
                "output_materialized": 5000.0,
            },
            "deltas_ms": {
                "clip_load": 11.5, "clip_encode": 22.25,
                "sampling": 300.0, "vae_decode": 40.0, "image_io": 5.0,
            },
            "derived_ms": {"active_profile_build_ms": 3.25},
            "metadata": {"local_active_profile_prepare_ms": 2.5},
        })
        restore_projection = types.MappingProxyType({"restore_total_ms": 42})
        primary_projection = {
            "path": str(out_file), "asset_id": "ast_c12_primary",
        }
        raw_materialization = types.MappingProxyType({
            "outputs": {
                "6": {"images": [{
                    "filename": "c12_workflow_output.png",
                    "subfolder": "", "type": "output",
                }]},
            },
            "images": [{"filename": "c12_workflow_output.png"}],
            # nested mappingproxy/raw materialization fields reachable through
            # the captured raw result projection:
            "trace": trace_projection,
            "_restore_timing": restore_projection,
            "primary_asset_id": "ast_c12_primary",
            "primary_output": primary_projection,
            "_local_primary_output": primary_projection,
        })
        canned = {
            "status": "ok",
            "runId": "run_c12",
            "runHistoryId": "run_c12",
            "experimentId": "exp_c12",
            "completed_at": "2026-01-01T00:00:00Z",
            "output_paths": [str(out_file)],
            "output_path": str(out_file),
            "timings": {"_run_type": "playground_direct"},
            "meta": {},
            "direct_run": True,
            # TOP-LEVEL raw result projection the history commit extracts:
            "trace": trace_projection,
            "_restore_timing": restore_projection,
            "primary_asset_id": "ast_c12_primary",
            "primary_output": primary_projection,
            "_local_primary_output": primary_projection,
            "raw_materialization": raw_materialization,
        }

        FakePlaygroundService.instances.clear()
        FakePlaygroundService.mode = "ok"
        FakePlaygroundService.canned_result = canned
        FakePlaygroundService.materialized_paths = [str(out_file)]

        wf_id = bundle["workflow"]["workflow_id"]
        version_id = bundle["version"]["workflow_version_id"]
        preset_id = bundle["preset"]["preset_id"]
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ):
            result = _run(swr.handle_workflow_run_async(
                wf_id, version_id, preset_id, "txt2img", overrides, self.root,
                modal_options={"execution_mode": "v2"},
            ))

        # Strict API JSON serializable; nested mappingproxies thawed to plain
        # dict/list containers — nothing stringified.
        self.assertEqual(result["status"], "ok")
        json.dumps(result)
        raw = result["raw_materialization"]
        self.assertIs(type(raw), dict)
        self.assertIs(type(raw["trace"]), dict)
        self.assertIs(type(raw["trace"]["stages"]), dict)
        self.assertIs(type(raw["outputs"]), dict)
        self.assertIs(type(raw["outputs"]["6"]["images"]), list)
        self.assertNotIsInstance(raw["trace"], types.MappingProxyType)
        self.assertEqual(raw["trace"]["stages"]["browser_run_click"], 1000.0)
        self.assertEqual(raw["_restore_timing"]["restore_total_ms"], 42)
        self.assertEqual(raw["primary_output"]["path"], str(out_file))

        # Exactly one completed legacy record with the materialized output
        # associated (output_path + meta output_paths + primary_asset_id) and
        # the SAME accepted run identity (prompt_id == canned runHistoryId).
        runs = svc.list_runs(kind="playground_run")["runs"]
        self.assertEqual(len(runs), 1)
        record = runs[0]
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["prompt_id"], "run_c12")
        self.assertEqual(record["output_path"], str(out_file))
        extra = record["extra"]
        self.assertEqual(extra["output_paths"], [str(out_file)])
        self.assertEqual(extra["primary_asset_id"], "ast_c12_primary")
        # requested_controls is a plain dict (never a stringified mapping) and
        # the prompt text survives untouched under BOTH the canonical prompt
        # key and the modern positive_prompt role.
        self.assertIs(type(extra["requested_controls"]), dict)
        self.assertEqual(
            extra["requested_controls"]["positive_prompt"],
            overrides["positive_prompt"],
        )
        self.assertEqual(
            extra["requested_controls"]["prompt"], overrides["positive_prompt"]
        )

        # V2: completed generation + exactly one completed attempt carrying
        # the captured restore/trace timing (including the mappingproxy trace
        # stage) and the accepted duration.
        run_id = record["run_id"]
        detail = repo.get_generation(_gen_id(run_id))
        self.assertIsNotNone(detail)
        gen = detail.generation
        self.assertEqual(gen.workflow_id, bundle["workflow"]["workflow_id"])
        self.assertEqual(
            gen.workflow_version_id, bundle["version"]["workflow_version_id"]
        )
        self.assertEqual(gen.preset_id, bundle["preset"]["preset_id"])
        # F6: the stored generation prompt equals the supplied positive prompt.
        self.assertEqual(gen.prompt_text, overrides["positive_prompt"])
        self.assertEqual(len(detail.attempts), 1)
        attempt = detail.attempts[0]
        self.assertEqual(attempt.status, "completed")
        self.assertFalse(any(a.status == "failed" for a in detail.attempts))
        self.assertEqual(attempt.timing.get("_run_type"), "playground_direct")
        self.assertEqual(attempt.timing.get("restore_total_ms"), 42)
        # F5: the raw MappingProxyType trace projection survives — the
        # result_received stage lands in History timing untouched.
        self.assertEqual(attempt.timing.get("result_received"), 4000.0)
        self.assertGreaterEqual(float(attempt.timing.get("duration_ms", -1)), 0)

        # Output asset attached + featured association (first original).
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertGreaterEqual(len(originals), 1)
        self.assertIsNotNone(gen.featured_asset_id)
        self.assertEqual(gen.featured_asset_id, originals[0].asset_id)
        self.assertEqual(
            Path(originals[0].filename).name, "c12_workflow_output.png"
        )

        # Request snapshot: repaired node 67/169 CLIP links + exact hash, and
        # snapshot params preserving seed/steps/cfg/sampler/scheduler/denoise/
        # width/height/prompts with falsy values verbatim.
        snapshot = detail.request_snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(
            snapshot.workflow_version_id, bundle["version"]["workflow_version_id"]
        )
        self.assertEqual(snapshot.workflow["67"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(snapshot.workflow["169"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(
            snapshot.workflow["67"]["inputs"]["text"], overrides["positive_prompt"]
        )
        self.assertEqual(snapshot.workflow_hash, prompt_sha256(snapshot.workflow))
        params = snapshot.generation_params
        self.assertEqual(params["seed"], 0)
        self.assertIs(type(params["seed"]), int)
        self.assertEqual(params["steps"], 30)
        self.assertEqual(params["cfg"], 0.0)
        self.assertIs(type(params["cfg"]), float)
        self.assertEqual(params["sampler"], "euler")
        self.assertEqual(params["scheduler"], "normal")
        self.assertEqual(params["denoise"], 0.0)
        self.assertIs(type(params["denoise"]), float)
        self.assertEqual(params["width"], 512)
        self.assertEqual(params["height"], 512)
        self.assertEqual(params["negative_prompt"], overrides["negative_prompt"])
        # F6: the snapshot prompt equals the supplied positive prompt (not
        # merely a key with an empty value).
        self.assertEqual(params["prompt"], overrides["positive_prompt"])

    # ── 20. F3: monotonic failure duration (not truncated wall seconds) ──

    def test_20_v2_failure_monotonic_duration(self):
        """A controlled accepted wait must use the MONOTONIC duration, not the
        wall-clock timestamp math.  Same-second ``started_at``/``completed_at``
        truncate to whole seconds and would yield 0 ms; the monotonic reading
        yields the exact elapsed wait."""
        svc, legacy_root, v2_root, repo = self._real_history_setup()
        fake_exp_module = self._history_shim(svc)
        bundle = self._clip_repair_fixture()

        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch("studio_workflow_run.time.monotonic", return_value=102.5):
            _run(swr._record_workflow_run_failure(
                bundle,
                bundle["preset"]["values"],
                "controlled accepted wait",
                # Same wall second: the timestamp fallback would produce 0.0.
                started_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-01T00:00:00Z",
                mono_start=100.0,
            ))

        runs = svc.list_runs(kind="playground_run")["runs"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "error")
        summary = runs[0].get("timing_summary") or {}
        self.assertEqual(
            summary.get("duration_ms"), 2500.0,
            "duration must come from time.monotonic(), not wall seconds",
        )

        # The V2 attempt carries the same monotonic duration.
        detail = repo.get_generation(_gen_id(runs[0]["run_id"]))
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "failed")
        self.assertEqual(detail.attempts[0].timing.get("duration_ms"), 2500.0)

    # ── 21. F1: output preflight failure (missing materialized candidate) ──

    def test_21_v2_success_output_preflight_failure(self):
        """A ``materialized_paths`` candidate that does not resolve (not a
        file directly, not under the studio outputs dir) is a truthful
        pre-terminal local failure: the API reports the exact bounded error,
        exactly one failed Generation/Attempt is recorded under the SAME
        accepted run identity, the repaired immutable snapshot is stored, and
        NO assets/featured are ever fabricated."""
        svc, legacy_root, v2_root, repo = self._real_history_setup()
        fake_exp_module = self._history_shim(svc)
        bundle = self._clip_repair_fixture()
        overrides = {
            "positive_prompt": "a red fox running through snow",
            "negative_prompt": "blurry, low quality",
        }
        expected_workflow, expected_hash = self._expected_repaired_workflow(
            bundle, overrides
        )

        missing = Path(self._tmp.name) / "never_materialized.png"
        self.assertFalse(missing.is_file())
        canned = {
            "status": "ok",
            "runId": "run_f1",
            "runHistoryId": "run_f1",
            "experimentId": "exp_f1",
            "completed_at": "2026-01-01T00:00:00Z",
            "output_paths": [str(missing)],
            "output_path": str(missing),
            "timings": {},
            "meta": {},
            "direct_run": True,
        }

        FakePlaygroundService.instances.clear()
        FakePlaygroundService.mode = "ok"
        FakePlaygroundService.canned_result = canned
        FakePlaygroundService.materialized_paths = [str(missing)]

        wf_id = bundle["workflow"]["workflow_id"]
        version_id = bundle["version"]["workflow_version_id"]
        preset_id = bundle["preset"]["preset_id"]
        window_start = datetime.now(timezone.utc)
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ):
            result = _run(swr.handle_workflow_run_async(
                wf_id, version_id, preset_id, "txt2img", overrides, self.root,
                modal_options={"execution_mode": "v2"},
            ))
        window_end = datetime.now(timezone.utc)

        self.assertEqual(result["status"], "error")
        self.assertIn("output preflight", result["message"])

        # Exactly one failed record under the SAME accepted identity, with the
        # repaired snapshot, plausible duration, and no assets/featured.
        self.assertEqual(len(svc.list_runs()["runs"]), 1)
        record = svc.list_runs(kind="playground_run")["runs"][0]
        self.assertEqual(record["prompt_id"], "run_f1")
        self.assertEqual(record["status"], "error")
        expected_workflow, expected_hash = self._executed_plan_snapshot()
        run_id = self._assert_failed_run(
            svc, repo, bundle, "output preflight",
            expected_workflow, expected_hash, window_start, window_end,
        )
        self.assertEqual(record["run_id"], run_id)

        detail = repo.get_generation(_gen_id(run_id))
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "failed")
        self.assertIn("output preflight", detail.attempts[0].error or "")
        self.assertEqual(len(detail.assets), 0)
        self.assertIsNone(detail.generation.featured_asset_id)


    # ── 22. C13: descriptor-only success with a valid primary_asset_id ───

    def test_22_c13_modern_success_descriptor_only_primary_asset(self):
        """C13-shaped success: the accepted Stage-9 result carries a VALID
        ``primary_asset_id`` and NO materialized output paths (descriptor-only,
        output-producing workflow).  The strict API response stays JSON
        serializable; exactly one completed Generation/Attempt is recorded with
        a plausible duration; the producer asset is adopted as exactly ONE
        managed original reference (never copied/re-encoded/thumbnailed) with
        the producer file bytes identical and featured set; and the repaired
        snapshot carries the node 67 CLIP link + hash, the workflow
        identity/name, and the existing mapped/falsy params verbatim."""
        svc, legacy_root, v2_root, repo = self._real_history_setup()
        fake_exp_module = self._history_shim(svc)
        bundle = self._clip_repair_fixture()

        file, record = self._c14_producer(Path(self._tmp.name))
        set_asset_resolver(
            lambda aid: record if aid == "ast_c13_producer" else None
        )

        overrides = {
            "steps": 30,
            "cfg": 0.0,
            "denoise": 0.0,
            "positive_prompt": "a red fox running through snow",
            "negative_prompt": "blurry, low quality",
        }
        primary_projection = {"path": file, "asset_id": "ast_c13_producer"}
        canned = {
            "status": "ok",
            "runId": "run_c13",
            "runHistoryId": "run_c13",
            "experimentId": "exp_c13",
            "completed_at": "2026-01-01T00:00:00Z",
            "output_paths": [],
            "output_path": "",
            "timings": {"_run_type": "playground_direct"},
            "meta": {},
            "direct_run": True,
            "trace": {
                "stages": {
                    "result_received": 4000.0,
                    "output_materialized": 5000.0,
                },
                "deltas_ms": {"sampling": 300.0},
            },
            "_restore_timing": {"restore_total_ms": 42},
            "primary_asset_id": "ast_c13_producer",
            "primary_output": primary_projection,
            "_local_primary_output": primary_projection,
            "raw_materialization": {
                "outputs": {
                    "6": {"images": [{"filename": "c14_producer.png"}]},
                },
                "images": [{"filename": "c14_producer.png"}],
            },
        }
        FakePlaygroundService.instances.clear()
        FakePlaygroundService.mode = "ok"
        FakePlaygroundService.canned_result = canned
        FakePlaygroundService.materialized_paths = None

        wf_id = bundle["workflow"]["workflow_id"]
        version_id = bundle["version"]["workflow_version_id"]
        preset_id = bundle["preset"]["preset_id"]
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ):
            result = _run(swr.handle_workflow_run_async(
                wf_id, version_id, preset_id, "txt2img", overrides, self.root,
                modal_options={"execution_mode": "v2"},
            ))

        # Strict JSON-safe result; descriptor-only output shape preserved.
        self.assertEqual(result["status"], "ok")
        json.dumps(result)
        self.assertEqual(result["primary_asset_id"], "ast_c13_producer")
        self.assertEqual(result["output_paths"], [])

        # Exactly one completed legacy record under the accepted identity.
        runs = svc.list_runs(kind="playground_run")["runs"]
        self.assertEqual(len(runs), 1)
        run_record = runs[0]
        self.assertEqual(run_record["status"], "completed")
        self.assertEqual(run_record["prompt_id"], "run_c13")
        extra = run_record["extra"]
        self.assertEqual(extra["primary_asset_id"], "ast_c13_producer")
        self.assertNotIn("output_paths", extra)
        self.assertIn("workflow_json", extra)

        # V2: completed generation + exactly one completed attempt with the
        # accepted identity/name and a plausible duration.
        run_id = run_record["run_id"]
        detail = repo.get_generation(_gen_id(run_id))
        self.assertIsNotNone(detail)
        gen = detail.generation
        self.assertEqual(gen.status, "completed")
        self.assertEqual(gen.workflow_id, bundle["workflow"]["workflow_id"])
        self.assertEqual(
            gen.workflow_version_id, bundle["version"]["workflow_version_id"]
        )
        self.assertEqual(gen.preset_id, bundle["preset"]["preset_id"])
        self.assertEqual(gen.prompt_text, overrides["positive_prompt"])
        self.assertEqual(len(detail.attempts), 1)
        attempt = detail.attempts[0]
        self.assertEqual(attempt.status, "completed")
        self.assertEqual(attempt.timing.get("_run_type"), "playground_direct")
        self.assertEqual(attempt.timing.get("restore_total_ms"), 42)
        self.assertGreaterEqual(float(attempt.timing.get("duration_ms", -1)), 0)

        # Exactly ONE adopted original (managed reference — never copied,
        # re-encoded, or thumbnailed); featured set; producer file valid.
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(
            [a for a in detail.assets if a.type == "thumbnail"], [],
            "producer adoption must never thumbnail",
        )
        adopted = originals[0]
        self.assertEqual(adopted.asset_id, "ast_c13_producer")
        self.assertEqual(Path(adopted.managed_path), Path(file).resolve())
        self.assertEqual(
            Path(adopted.managed_path).read_bytes(), Path(file).read_bytes()
        )
        self.assertEqual(adopted.sha256, record["content_hash"])
        self.assertEqual(adopted.format, "png")
        self.assertEqual(
            adopted.metadata.get("producer_asset_id"), "ast_c13_producer"
        )
        self.assertEqual(detail.generation.featured_asset_id, adopted.asset_id)
        self.assertEqual(Path(file).read_bytes(), b"c14-producer-png-bytes")

        # Repaired snapshot: node 67/169 CLIP links + exact hash, workflow
        # version identity + display name persisted, falsy params verbatim.
        snapshot = detail.request_snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.workflow["67"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(snapshot.workflow["169"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(
            snapshot.workflow["67"]["inputs"]["text"], overrides["positive_prompt"]
        )
        self.assertEqual(snapshot.workflow_hash, prompt_sha256(snapshot.workflow))
        self.assertEqual(
            snapshot.workflow_version_id, bundle["version"]["workflow_version_id"]
        )
        self.assertEqual(
            snapshot.preset_snapshot.get("workflow_name"),
            bundle["workflow"]["name"],
        )
        params = snapshot.generation_params
        self.assertEqual(params["seed"], 0)
        self.assertIs(type(params["seed"]), int)
        self.assertEqual(params["steps"], 30)
        self.assertEqual(params["cfg"], 0.0)
        self.assertIs(type(params["cfg"]), float)
        self.assertEqual(params["denoise"], 0.0)
        self.assertIs(type(params["denoise"]), float)
        self.assertEqual(params["sampler"], "euler")
        self.assertEqual(params["scheduler"], "normal")
        self.assertEqual(params["width"], 512)
        self.assertEqual(params["height"], 512)
        self.assertEqual(params["prompt"], overrides["positive_prompt"])
        self.assertEqual(params["negative_prompt"], overrides["negative_prompt"])

    # ── 23. C13: unknown primary_asset_id finalization failure ───────────

    def test_23_c13_unknown_primary_asset_finalization_failure(self):
        """An UNKNOWN ``primary_asset_id`` with no materialized path is a
        truthful modern finalization failure: the API returns the exact bounded
        error, NO completed terminal exists, exactly one failed
        Generation/Attempt is recorded with the repaired snapshot retained, no
        assets are fabricated, and a first-terminal completed replay stays
        failed."""
        svc, legacy_root, v2_root, repo = self._real_history_setup()
        fake_exp_module = self._history_shim(svc)
        bundle = self._clip_repair_fixture()
        set_asset_resolver(lambda aid: None)

        overrides = {
            "positive_prompt": "a red fox running through snow",
            "negative_prompt": "blurry, low quality",
        }
        expected_workflow, expected_hash = self._expected_repaired_workflow(
            bundle, overrides
        )
        canned = {
            "status": "ok",
            "runId": "run_c13_unknown",
            "runHistoryId": "run_c13_unknown",
            "experimentId": "exp_c13_unknown",
            "completed_at": "2026-01-01T00:00:00Z",
            "output_paths": [],
            "output_path": "",
            "timings": {},
            "meta": {},
            "direct_run": True,
            "primary_asset_id": "ast_c13_unknown",
        }
        FakePlaygroundService.instances.clear()
        FakePlaygroundService.mode = "ok"
        FakePlaygroundService.canned_result = canned
        FakePlaygroundService.materialized_paths = None

        wf_id = bundle["workflow"]["workflow_id"]
        version_id = bundle["version"]["workflow_version_id"]
        preset_id = bundle["preset"]["preset_id"]
        window_start = datetime.now(timezone.utc)
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ):
            result = _run(swr.handle_workflow_run_async(
                wf_id, version_id, preset_id, "txt2img", overrides, self.root,
                modal_options={"execution_mode": "v2"},
            ))
        window_end = datetime.now(timezone.utc)

        # The EXACT bounded finalization error, never a fabricated ok.
        expected_message = (
            "v2 history success commit failed: v2 output preflight failed: "
            "primary asset 'ast_c13_unknown' does not resolve in the producer "
            "asset registry"
        )
        self.assertEqual(
            result, {"status": "error", "message": expected_message}
        )

        # Exactly one FAILED record under the SAME accepted identity, with the
        # repaired snapshot retained, no assets, plausible duration.
        runs = svc.list_runs(kind="playground_run")["runs"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["prompt_id"], "run_c13_unknown")
        self.assertEqual(runs[0]["status"], "error")
        expected_workflow, expected_hash = self._executed_plan_snapshot()
        run_id = self._assert_failed_run(
            svc, repo, bundle, "does not resolve in the producer asset registry",
            expected_workflow, expected_hash, window_start, window_end,
        )

        detail = repo.get_generation(_gen_id(run_id))
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "failed")
        self.assertIn("does not resolve", detail.attempts[0].error or "")
        self.assertEqual(len(detail.assets), 0, "no fabricated assets")
        self.assertIsNone(detail.generation.featured_asset_id)

        # First-terminal replay of completed remains failed.
        get_writer(v2_root).update_run(
            run_id, status="completed", completed_at="2026-01-02T00:00:00Z",
        )
        detail = repo.get_generation(_gen_id(run_id))
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "failed")
        self.assertEqual(len(detail.assets), 0)

    # ── 24. C13: ID + path for the SAME producer output ──────────────────

    def test_24_c13_id_and_path_same_producer_output_single_original(self):
        """A materialized output path AND a ``primary_asset_id`` resolving to
        the SAME producer file yield exactly ONE logical original (the path
        copy; the producer reference dedupes via content_hash) which stays
        featured — no duplicate/copy/re-encode, one completed attempt."""
        svc, legacy_root, v2_root, repo = self._real_history_setup()
        fake_exp_module = self._history_shim(svc)
        bundle = self._clip_repair_fixture()

        file, record = self._c14_producer(Path(self._tmp.name))
        set_asset_resolver(
            lambda aid: record if aid == "ast_c13_producer" else None
        )
        overrides = {"steps": 30}
        canned = {
            "status": "ok",
            "runId": "run_c13_both",
            "runHistoryId": "run_c13_both",
            "experimentId": "exp_c13_both",
            "completed_at": "2026-01-01T00:00:00Z",
            "output_paths": [file],
            "output_path": file,
            "timings": {},
            "meta": {},
            "direct_run": True,
            "primary_asset_id": "ast_c13_producer",
            "primary_output": {"path": file, "asset_id": "ast_c13_producer"},
        }
        FakePlaygroundService.instances.clear()
        FakePlaygroundService.mode = "ok"
        FakePlaygroundService.canned_result = canned
        FakePlaygroundService.materialized_paths = [file]

        wf_id = bundle["workflow"]["workflow_id"]
        version_id = bundle["version"]["workflow_version_id"]
        preset_id = bundle["preset"]["preset_id"]
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ):
            result = _run(swr.handle_workflow_run_async(
                wf_id, version_id, preset_id, "txt2img", overrides, self.root,
                modal_options={"execution_mode": "v2"},
            ))
        self.assertEqual(result["status"], "ok")

        # Exactly one completed record associating BOTH the path and the id.
        runs = svc.list_runs(kind="playground_run")["runs"]
        self.assertEqual(len(runs), 1)
        run_record = runs[0]
        self.assertEqual(run_record["status"], "completed")
        self.assertEqual(run_record["output_path"], file)
        self.assertEqual(run_record["extra"]["output_paths"], [file])
        self.assertEqual(
            run_record["extra"]["primary_asset_id"], "ast_c13_producer"
        )

        # Exactly ONE logical original (the path copy) + featured; the
        # producer reference dedupes against it — no second original.
        run_id = run_record["run_id"]
        detail = repo.get_generation(_gen_id(run_id))
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "completed")
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(
            len(originals), 1,
            "ID+path for the same producer output must yield ONE original",
        )
        self.assertEqual(
            [a for a in detail.assets if a.metadata.get("producer_asset_id")],
            [], "producer reference must dedupe against the path copy",
        )
        self.assertEqual(
            Path(originals[0].managed_path).read_bytes(), Path(file).read_bytes()
        )
        self.assertEqual(originals[0].sha256, record["content_hash"])
        self.assertEqual(
            detail.generation.featured_asset_id, originals[0].asset_id
        )

    # ── 25. C13: resolved primary id whose History adoption fails ─────────

    def test_25_c13_resolved_primary_id_association_failure(self):
        """A ``primary_asset_id`` that RESOLVES in the producer registry (the
        preflight passes) but whose History adoption fails before the terminal
        ``completed`` write is a truthful finalization failure: the API returns
        the exact bounded error, NO completed terminal exists, exactly one
        failed accepted attempt is recorded with the repaired snapshot retained
        and no asset fabricated, and a completed replay stays failed.

        The narrow repository ``adopt_asset`` patch makes the association step
        fail while the resolver-based preflight still passes — proving the
        post-record output-association check, not the preflight, is the gate."""
        svc, legacy_root, v2_root, repo = self._real_history_setup()
        fake_exp_module = self._history_shim(svc)
        bundle = self._clip_repair_fixture()

        file, record = self._c14_producer(
            Path(self._tmp.name), asset_id="ast_c13_assoc"
        )
        set_asset_resolver(
            lambda aid: record if aid == "ast_c13_assoc" else None
        )
        overrides = {
            "positive_prompt": "a red fox running through snow",
            "negative_prompt": "blurry, low quality",
        }
        expected_workflow, expected_hash = self._expected_repaired_workflow(
            bundle, overrides
        )
        canned = {
            "status": "ok",
            "runId": "run_c13_assoc",
            "runHistoryId": "run_c13_assoc",
            "experimentId": "exp_c13_assoc",
            "completed_at": "2026-01-01T00:00:00Z",
            "output_paths": [],
            "output_path": "",
            "timings": {},
            "meta": {},
            "direct_run": True,
            "primary_asset_id": "ast_c13_assoc",
        }
        FakePlaygroundService.instances.clear()
        FakePlaygroundService.mode = "ok"
        FakePlaygroundService.canned_result = canned
        FakePlaygroundService.materialized_paths = None

        wf_id = bundle["workflow"]["workflow_id"]
        version_id = bundle["version"]["workflow_version_id"]
        preset_id = bundle["preset"]["preset_id"]
        window_start = datetime.now(timezone.utc)
        with self._service_patcher(), patch.dict(
            sys.modules, {"experiment_service": fake_exp_module}
        ), patch(
            "comfymodal_runtime.playground_service.PlaygroundService",
            FakePlaygroundService,
        ), patch(
            "history_v2_repository.HistoryV2Repository.adopt_asset",
            return_value=None,
        ):
            result = _run(swr.handle_workflow_run_async(
                wf_id, version_id, preset_id, "txt2img", overrides, self.root,
                modal_options={"execution_mode": "v2"},
            ))
        window_end = datetime.now(timezone.utc)

        # The nonterminal ``running`` record exists (the association check runs
        # AFTER the first history write); the failure helper then records ONE
        # error under the SAME accepted identity.  No completed terminal.
        runs = svc.list_runs(kind="playground_run")["runs"]
        self.assertEqual(len(runs), 2)
        running = [r for r in runs if r["status"] == "running"]
        failed = [r for r in runs if r["status"] == "error"]
        self.assertEqual(len(running), 1, "pre-finalization running record kept")
        self.assertEqual(len(failed), 1, "exactly one failed accepted record")
        self.assertEqual(failed[0]["prompt_id"], "run_c13_assoc")
        run_id = failed[0]["run_id"]
        expected_workflow, expected_hash = self._executed_plan_snapshot()

        # The EXACT bounded finalization error embeds the running record's
        # History run id (the attempt that failed to associate an output).
        expected_message = (
            "v2 history success commit failed: v2 history finalization failed: "
            f"output-producing run {running[0]['run_id']!r} has no associated "
            "History output"
        )
        self.assertEqual(
            result, {"status": "error", "message": expected_message}
        )

        # Exactly one failed attempt with the repaired snapshot retained, no
        # fabricated asset, plausible duration, and no featured association.
        detail = repo.get_generation(_gen_id(run_id))
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail.attempts), 1)
        attempt = detail.attempts[0]
        self.assertEqual(attempt.status, "failed")
        self.assertIn("has no associated History output", attempt.error or "")
        self.assertEqual(attempt.timing.get("_run_type"), "playground_direct")
        self.assertGreaterEqual(float(attempt.timing.get("duration_ms", -1)), 0)
        self.assertEqual(len(detail.assets), 0, "no fabricated assets")
        self.assertIsNone(detail.generation.featured_asset_id)

        snapshot = detail.request_snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.workflow, expected_workflow)
        self.assertEqual(snapshot.workflow_hash, expected_hash)
        self.assertEqual(
            snapshot.workflow_version_id, bundle["version"]["workflow_version_id"]
        )
        self.assertEqual(snapshot.workflow["67"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(snapshot.workflow["169"]["inputs"]["clip"], ["62", 0])

        # The running record's own V2 generation carried NO output either
        # (adoption failed) and was never completed.
        running_detail = repo.get_generation(_gen_id(running[0]["run_id"]))
        self.assertIsNotNone(running_detail)
        self.assertEqual(len(running_detail.assets), 0)
        self.assertEqual(running_detail.attempts[0].status, "running")

        # First-terminal replay of completed remains failed, no asset appears.
        get_writer(v2_root).update_run(
            run_id, status="completed", completed_at="2026-01-02T00:00:00Z",
        )
        detail = repo.get_generation(_gen_id(run_id))
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "failed")
        self.assertEqual(len(detail.assets), 0)


if __name__ == "__main__":
    unittest.main()
