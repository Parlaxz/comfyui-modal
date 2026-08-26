"""F8 GPU Authority Consolidation — deterministic tests.

Covers the four F8 closures on the GPU lane:

1. Persistence: the selected GPU lives in the canonical
   ``.modal_settings.json`` settings (defaults, load normalization,
   POST /config persistence with truthful failure + rollback, restart
   seeding via ``_seed_server_gpu_from_settings``).
2. Immutable capture: modern Studio submissions resolve the GPU ONCE at
   acceptance (request override → modal_options → persisted server GPU)
   and freeze ``request_metadata.selected_gpu`` into the ExecutionPlan;
   later Settings changes never mutate accepted plans; replay/resume/
   retry keep the saved GPU and never re-read current Settings.
3. Transport boundary: canonical execution passes the frozen
   ``selected_gpu`` to the transport; empty selection falls back to the
   documented env/hardcoded fallback only.
4. Reset semantics: POSTing the canonical default GPU resets server +
   persisted state (frontend Reset All exercises this endpoint).

Deterministic: temp dirs, fake transports/executors, no Modal calls.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import modal_client
from gpu_catalog import DEFAULT_GPU


def _run(coro):
    return asyncio.run(coro)


def _restore_gpu(value: str) -> None:
    modal_client._current_gpu = value


# ── 1. Persistence (route-level, stub PromptServer) ──────────────────────


class F8GpuSettingsPersistenceTests(unittest.TestCase):
    """POST/GET /comfymodal/config GPU persistence + restart simulation."""

    @classmethod
    def setUpClass(cls):
        from tests.test_routes_registered import _StubServer, _build_init_with_stub

        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._settings_file = str(Path(self._tmp.name) / ".modal_settings.json")
        self._orig_settings_file = self.init_mod._MODAL_SETTINGS_FILE
        self.init_mod._MODAL_SETTINGS_FILE = self._settings_file
        self.init_mod._modal_settings_cache = None
        self._orig_gpu = modal_client.get_gpu()
        self.addCleanup(self._teardown)

    def _teardown(self):
        self.init_mod._MODAL_SETTINGS_FILE = self._orig_settings_file
        self.init_mod._modal_settings_cache = None
        _restore_gpu(self._orig_gpu)
        self._tmp.cleanup()

    def _get_handler(self):
        from tests.test_routes_registered import _handler_for

        return _handler_for(self.init_mod, "GET", "/comfymodal/config")

    def _post_handler(self):
        from tests.test_routes_registered import _handler_for

        return _handler_for(self.init_mod, "POST", "/comfymodal/config")

    def _request(self, body=None):
        from tests.test_routes_registered import _MockRequest

        return _MockRequest(json_body=body if body is not None else {})

    def _disk_settings(self) -> dict:
        with open(self._settings_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # 17.1 — default config returns canonical GPU
    def test_default_config_returns_canonical_gpu(self):
        resp = _run(self._get_handler()(self._request()))
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.body)
        self.assertEqual(body["gpu"], DEFAULT_GPU)
        self.assertEqual(body["default_gpu"], DEFAULT_GPU)
        self.assertEqual(body["persisted_gpu"], DEFAULT_GPU)
        self.assertTrue(body["available_gpus"])

    # 17.2 — POST GPU persists (memory + disk acknowledged)
    def test_post_gpu_persists_to_canonical_settings(self):
        resp = _run(self._post_handler()(self._request({"gpu": "L4"})))
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.body)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["gpu"], "l4")
        self.assertEqual(modal_client.get_gpu(), "l4")
        disk = self._disk_settings()
        self.assertEqual(disk.get("gpu"), "l4")

    # 17.3 — reload/restart reads persisted GPU (restart simulation)
    def test_restart_seeds_server_gpu_from_persisted_settings(self):
        _run(self._post_handler()(self._request({"gpu": "l4"})))
        # Simulate a fresh process: cache dropped, in-memory GPU back to default.
        self.init_mod._modal_settings_cache = None
        _restore_gpu(DEFAULT_GPU)
        seeded = self.init_mod._seed_server_gpu_from_settings()
        self.assertEqual(seeded, "l4")
        self.assertEqual(modal_client.get_gpu(), "l4")
        # GET still reports the previously persisted GPU after restart.
        body = json.loads(_run(self._get_handler()(self._request())).body)
        self.assertEqual(body["gpu"], "l4")
        self.assertEqual(body["persisted_gpu"], "l4")

    def test_missing_gpu_value_falls_back_to_catalog_default(self):
        self.init_mod._modal_settings_cache = None
        Path(self._settings_file).write_text(
            json.dumps({"output_format": "png"}), encoding="utf-8"
        )
        settings = self.init_mod._load_modal_settings()
        self.assertEqual(settings["gpu"], DEFAULT_GPU)

    def test_invalid_retired_gpu_normalizes_truthfully_to_default(self):
        self.init_mod._modal_settings_cache = None
        Path(self._settings_file).write_text(
            json.dumps({"gpu": "gtx-480-retired"}), encoding="utf-8"
        )
        settings = self.init_mod._load_modal_settings()
        self.assertEqual(settings["gpu"], DEFAULT_GPU)

    def test_non_string_gpu_value_never_persists_nonsense(self):
        self.init_mod._modal_settings_cache = None
        Path(self._settings_file).write_text(
            json.dumps({"gpu": {"bogus": True}}), encoding="utf-8"
        )
        settings = self.init_mod._load_modal_settings()
        self.assertEqual(settings["gpu"], DEFAULT_GPU)

    # 17.4 — invalid GPU rejected truthfully
    def test_invalid_gpu_rejected_without_state_change(self):
        _run(self._post_handler()(self._request({"gpu": "l4"})))
        resp = _run(self._post_handler()(self._request({"gpu": "not-a-gpu"})))
        self.assertEqual(resp.status, 400)
        body = json.loads(resp.body)
        self.assertEqual(body["status"], "error")
        self.assertIn("Unsupported GPU", body["message"])
        self.assertEqual(modal_client.get_gpu(), "l4")
        self.assertEqual(self._disk_settings().get("gpu"), "l4")

    # 17.5 — persistence failure doesn't falsely acknowledge; rollback keeps
    # GET aligned with actual authority.
    def test_persistence_failure_rolls_back_and_reports_truthfully(self):
        _run(self._post_handler()(self._request({"gpu": "l4"})))
        with patch.object(
            self.init_mod, "_save_modal_settings", side_effect=OSError("disk full")
        ):
            resp = _run(self._post_handler()(self._request({"gpu": "h100"})))
        self.assertEqual(resp.status, 500)
        body = json.loads(resp.body)
        self.assertEqual(body["status"], "error")
        self.assertIn("persistence failed", body["message"])
        # Rolled back: memory AND GET report the previous acknowledged value.
        self.assertEqual(modal_client.get_gpu(), "l4")
        get_body = json.loads(_run(self._get_handler()(self._request())).body)
        self.assertEqual(get_body["gpu"], "l4")

    # Partial saves must never silently reset the persisted GPU/engine.
    # H12: POST /config rejects retired engines, so the engine value carried
    # alongside the GPU is the only public one (v2).
    def test_partial_output_post_preserves_persisted_gpu_and_mode(self):
        _run(self._post_handler()(self._request({"gpu": "l4", "execution_mode": "v2"})))
        resp = _run(self._post_handler()(self._request({"quality": 80})))
        self.assertEqual(resp.status, 200)
        disk = self._disk_settings()
        self.assertEqual(disk.get("gpu"), "l4")
        self.assertEqual(disk.get("execution_mode"), "v2")
        self.assertEqual(disk.get("quality"), 80)
        self.assertEqual(modal_client.get_gpu(), "l4")

    # H12 — a retired engine can no longer be persisted via /config.
    def test_retired_engine_rejected_by_config_post(self):
        for retired in ("v1", "legacy", "shadow"):
            resp = _run(self._post_handler()(self._request({"execution_mode": retired})))
            self.assertEqual(resp.status, 400, retired)
            body = json.loads(resp.body)
            self.assertEqual(body["status"], "error", retired)
        if not Path(self._settings_file).exists():
            return  # nothing persisted at all — rejection is total
        disk = self._disk_settings()
        self.assertNotIn(disk.get("execution_mode"), ("v1", "shadow"))

    # 17.6 — display payload carries everything both Settings surfaces need.
    def test_config_payload_serves_modern_and_legacy_display(self):
        _run(self._post_handler()(self._request({"gpu": "a10g"})))
        body = json.loads(_run(self._get_handler()(self._request())).body)
        self.assertEqual(body["gpu"], "a10g")
        values = {o["value"] for o in body["available_gpus"]}
        self.assertIn("a10g", values)
        self.assertIn(body["default_gpu"], values)


# ── 2. Request-time precedence resolution ────────────────────────────────


class F8RequestGpuPrecedenceTests(unittest.TestCase):
    """resolve_request_gpu precedence: request > modal_options > server."""

    def setUp(self):
        from studio_run_adapter import resolve_request_gpu

        self.resolve = resolve_request_gpu
        self._orig_gpu = modal_client.get_gpu()
        modal_client._current_gpu = "a10g"
        self.addCleanup(lambda: _restore_gpu(self._orig_gpu))

    def test_explicit_request_override_wins(self):
        gpu, source = self.resolve("H100", {"gpu": "l4"})
        self.assertEqual(gpu, "h100")
        self.assertEqual(source, "request")

    def test_modal_options_gpu_beats_server_settings(self):
        gpu, source = self.resolve(None, {"gpu": "l4"})
        self.assertEqual((gpu, source), ("l4", "modal_options"))

    def test_server_settings_is_final_fallback(self):
        gpu, source = self.resolve(None, None)
        self.assertEqual((gpu, source), ("a10g", "server_settings"))

    def test_empty_values_fall_through_to_next_level(self):
        gpu, source = self.resolve("", {"gpu": ""})
        self.assertEqual((gpu, source), ("a10g", "server_settings"))

    def test_invalid_explicit_override_fails_closed(self):
        with self.assertRaises(ValueError):
            self.resolve("not-a-gpu", None)

    def test_invalid_modal_options_gpu_fails_closed(self):
        with self.assertRaises(ValueError):
            self.resolve(None, {"gpu": "not-a-gpu"})

    def test_no_capture_anywhere_returns_empty_for_transport_fallback(self):
        _restore_gpu("")
        gpu, source = self.resolve("", {})
        self.assertEqual((gpu, source), ("", "server_settings"))


# ── 3. Acceptance capture threading (Single / Workflow / Experiment) ─────


class _RecordingAdapter:
    def __init__(self):
        self.calls: list[dict] = []

    async def __call__(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return {"status": "ok", "output_paths": []}


class F8StudioSingleCaptureTests(unittest.TestCase):
    """handle_studio_run_async freezes the captured GPU per submission."""

    def setUp(self):
        self._orig_gpu = modal_client.get_gpu()
        modal_client._current_gpu = "l4"
        self.addCleanup(lambda: _restore_gpu(self._orig_gpu))

    def _call(self, *, gpu=None, modal_options=None):
        import studio_run_adapter as sra

        recorder = _RecordingAdapter()
        with patch.object(sra, "playground_adapter_direct_run", recorder):
            result = _run(sra.handle_studio_run_async(
                "preset_1", "txt2img", {"prompt": "test"}, REPO_ROOT,
                gpu=gpu, modal_options=modal_options,
            ))
        return result, recorder

    def test_single_captures_server_gpu_when_request_has_none(self):
        _, recorder = self._call()
        self.assertEqual(recorder.calls[0]["kwargs"]["gpu"], "l4")

    def test_next_submission_captures_changed_settings_gpu(self):
        _, first = self._call()
        self.assertEqual(first.calls[0]["kwargs"]["gpu"], "l4")
        modal_client._current_gpu = "a10g"
        _, second = self._call()
        self.assertEqual(second.calls[0]["kwargs"]["gpu"], "a10g")

    def test_explicit_request_override_wins_at_acceptance(self):
        _, recorder = self._call(gpu="H100")
        self.assertEqual(recorder.calls[0]["kwargs"]["gpu"], "h100")

    def test_invalid_override_fails_before_dispatch(self):
        result, recorder = self._call(gpu="not-a-gpu")
        self.assertEqual(result.get("status"), "error")
        self.assertIn("Unsupported GPU", result.get("message", ""))
        self.assertEqual(recorder.calls, [])


class F8WorkflowCaptureTests(unittest.TestCase):
    """Modern Workflow runs capture the same GPU authority."""

    def setUp(self):
        import studio_workflow_run as swr
        from studio_domain import WorkflowDomainService

        self.swr = swr
        self._tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self._tmp.name))
        self.service = WorkflowDomainService(self.root)
        self.wf = self.service.create_workflow("Text2Img Workflow")
        self.version = self.service.create_version_from_capture(
            self.wf["workflow_id"],
            {
                "graph_json": {"id": "g1", "nodes": []},
                "api_prompt_json": {"workflow": {}, "output": _TXT2IMG_PROMPT},
            },
        )
        entries, output_node_id = _derive_mapping()
        self.service.set_mapping(
            self.version["workflow_version_id"],
            entries=entries, output_node_id=output_node_id,
        )
        self.preset = self.service.create_preset(
            self.version["workflow_version_id"], "Preset A",
            values=_default_values(),
        )
        self.service.set_default_preset(self.wf["workflow_id"], self.preset["preset_id"])
        self._orig_gpu = modal_client.get_gpu()
        modal_client._current_gpu = "l4"
        self.addCleanup(self._teardown)

    def _teardown(self):
        _restore_gpu(self._orig_gpu)
        self._tmp.cleanup()

    def _bundle(self):
        with patch.object(
            self.swr, "_get_domain_service", lambda node_dir: self.service
        ):
            return self.swr.resolve_workflow_run_bundle(
                self.wf["workflow_id"], self.version["workflow_version_id"],
                self.preset["preset_id"], self.root,
            )

    def test_workflow_v2_run_receives_captured_server_gpu(self):
        recorder = _RecordingAdapter()
        with patch.object(self.swr, "_get_domain_service", lambda node_dir: self.service), \
             patch.object(self.swr, "_workflow_v2_run", recorder):
            result = _run(self.swr.handle_workflow_run_async(
                self.wf["workflow_id"], self.version["workflow_version_id"],
                self.preset["preset_id"], "txt2img", {}, self.root,
                modal_options={"execution_mode": "v2"},
            ))
        self.assertEqual(result.get("status"), "ok")
        # Positional contract: (bundle, merged, preset_id, node_dir, modal_options, gpu, workspace, trace_ctx)
        self.assertEqual(recorder.calls[0]["args"][5], "l4")

    def test_workflow_future_submission_captures_new_gpu(self):
        recorder = _RecordingAdapter()
        with patch.object(self.swr, "_get_domain_service", lambda node_dir: self.service), \
             patch.object(self.swr, "_workflow_v2_run", recorder):
            _run(self.swr.handle_workflow_run_async(
                self.wf["workflow_id"], self.version["workflow_version_id"],
                self.preset["preset_id"], "txt2img", {}, self.root,
                modal_options={"execution_mode": "v2"},
            ))
            modal_client._current_gpu = "a10g"
            _run(self.swr.handle_workflow_run_async(
                self.wf["workflow_id"], self.version["workflow_version_id"],
                self.preset["preset_id"], "txt2img", {}, self.root,
                modal_options={"execution_mode": "v2"},
            ))
        self.assertEqual(recorder.calls[0]["args"][5], "l4")
        self.assertEqual(recorder.calls[1]["args"][5], "a10g")


class F8ExperimentCaptureTests(unittest.TestCase):
    """Experiments freeze ONE accepted GPU for every cell."""

    def setUp(self):
        import studio_run_adapter as sra

        self.sra = sra
        self._orig_gpu = modal_client.get_gpu()
        modal_client._current_gpu = "l4"
        self.addCleanup(lambda: _restore_gpu(self._orig_gpu))

    def test_experiment_threads_accepted_gpu_into_scheduler(self):
        compilation = {
            "experiment_id": "exp_f8",
            "cells": [{"cell_key": "c1"}, {"cell_key": "c2"}],
            "studio_meta": {},
        }
        recorder = _RecordingAdapter()

        fake_registry_module = types.ModuleType("experiment_service")
        fake_registry_module.REGISTRY = SimpleNamespace(
            get_or_create_scheduler=lambda *a, **k: None
        )

        async def _noop_schedule(*a, **k):
            return {"status": "submitted"}

        with patch.object(self.sra, "load_preset_and_snapshot",
                          return_value=({"id": "p1"}, {})), \
             patch.object(self.sra, "build_experiment_spec",
                          return_value=compilation), \
             patch.dict(sys.modules, {"experiment_service": fake_registry_module}), \
             patch.object(self.sra, "_create_experiment", lambda *a, **k: None), \
             patch.object(self.sra, "_schedule_and_start", recorder):
            result = self.sra.handle_studio_experiment(
                ["p1"], "txt2img", {"name": "F8"}, REPO_ROOT,
                modal_options={}, gpu=None,
            )
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(recorder.calls[0]["kwargs"]["gpu"], "l4")

    def test_experiment_explicit_override_wins(self):
        compilation = {
            "experiment_id": "exp_f8b",
            "cells": [{"cell_key": "c1"}],
            "studio_meta": {},
        }
        recorder = _RecordingAdapter()
        fake_registry_module = types.ModuleType("experiment_service")
        fake_registry_module.REGISTRY = SimpleNamespace()

        with patch.object(self.sra, "load_preset_and_snapshot",
                          return_value=({"id": "p1"}, {})), \
             patch.object(self.sra, "build_experiment_spec",
                          return_value=compilation), \
             patch.dict(sys.modules, {"experiment_service": fake_registry_module}), \
             patch.object(self.sra, "_create_experiment", lambda *a, **k: None), \
             patch.object(self.sra, "_schedule_and_start", recorder):
            result = self.sra.handle_studio_experiment(
                ["p1"], "txt2img", {"name": "F8"}, REPO_ROOT,
                modal_options={}, gpu="H100",
            )
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(recorder.calls[0]["kwargs"]["gpu"], "h100")

    def test_experiment_invalid_gpu_fails_truthfully(self):
        with patch.object(self.sra, "load_preset_and_snapshot",
                          return_value=({"id": "p1"}, {})):
            result = self.sra.handle_studio_experiment(
                ["p1"], "txt2img", {"name": "F8"}, REPO_ROOT,
                modal_options={}, gpu="not-a-gpu",
            )
        self.assertEqual(result.get("status"), "error")
        self.assertIn("Unsupported GPU", result.get("message", ""))


# ── 4. Plan freezing + replay/resume preservation ────────────────────────


_TXT2IMG_PROMPT = {
    "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello world", "clip": ["4", 0]}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative", "clip": ["4", 0]}},
    "3": {"class_type": "KSampler", "inputs": {
        "model": ["4", 0], "seed": 0, "steps": 20, "cfg": 7.0,
        "sampler_name": "euler", "scheduler": "normal",
        "positive": ["1", 0], "negative": ["2", 0], "latent_image": ["5", 0],
        "denoise": 1.0}},
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "krea_model.safetensors"}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
    "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
}


def _fake_node_def(class_type: str):
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
    if class_type == "SaveImage":
        return ({"images": ("IMAGE",), "filename_prefix": ("STRING", {"default": "ComfyUI"})}, {})
    return None


def _derive_mapping():
    from studio_domain import derive_mapping_candidates

    capture = {
        "graph_json": {"id": "g1", "nodes": []},
        "api_prompt_json": {"workflow": {}, "output": _TXT2IMG_PROMPT},
    }
    entries, output_node_id = derive_mapping_candidates(
        capture, node_def_provider=_fake_node_def
    )
    return {role: e.to_dict() for role, e in entries.items()}, output_node_id


def _default_values() -> dict:
    p = _TXT2IMG_PROMPT
    return {
        "positive_prompt": "hello world",
        "negative_prompt": "negative",
        "seed": p["3"]["inputs"]["seed"],
        "steps": p["3"]["inputs"]["steps"],
        "cfg": p["3"]["inputs"]["cfg"],
        "sampler": p["3"]["inputs"]["sampler_name"],
        "scheduler": p["3"]["inputs"]["scheduler"],
        "denoise": p["3"]["inputs"]["denoise"],
        "width": p["5"]["inputs"]["width"],
        "height": p["5"]["inputs"]["height"],
        "model": p["4"]["inputs"]["ckpt_name"],
    }


class F8PlanFreezeTests(unittest.TestCase):
    """selected_gpu is frozen into plans; replay/resume preserve it."""

    def setUp(self):
        import studio_workflow_run as swr

        self.swr = swr
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # E7: stub host validation proof for headless deterministic runs
        # (mirrors tests/test_workflow_run_integration.py).
        import canonical_execution as _ce

        self._validation_patcher = patch.object(
            _ce,
            "_collect_plan_validation_proof",
            return_value={
                "schema_version": 1,
                "validated": True,
                "source": "host_validate_prompt",
                "outputs_to_execute": ["3", "6"],
                "node_errors": {"3": {"errors": []}},
                "validated_workflow_hash": "vwh_f8_fixed",
            },
        )
        self._validation_patcher.start()
        self.addCleanup(self._validation_patcher.stop)

    def _bundle(self):
        from studio_domain import WorkflowDomainService

        service = WorkflowDomainService(self._tmp.name)
        wf = service.create_workflow("Text2Img Workflow")
        version = service.create_version_from_capture(
            wf["workflow_id"],
            {
                "graph_json": {"id": "g1", "nodes": []},
                "api_prompt_json": {"workflow": {}, "output": _TXT2IMG_PROMPT},
            },
        )
        entries, output_node_id = _derive_mapping()
        service.set_mapping(
            version["workflow_version_id"],
            entries=entries, output_node_id=output_node_id,
        )
        preset = service.create_preset(
            version["workflow_version_id"], "Preset A", values=_default_values()
        )
        service.set_default_preset(wf["workflow_id"], preset["preset_id"])
        with patch.object(self.swr, "_get_domain_service", lambda node_dir: service):
            return self.swr.resolve_workflow_run_bundle(
                wf["workflow_id"], version["workflow_version_id"],
                preset["preset_id"], self._tmp.name,
            )

    def test_workflow_plan_freezes_selected_gpu_production_path(self):
        bundle = self._bundle()
        merged = self.swr.merge_workflow_controls(
            bundle["preset"], {}, bundle["control_schema"]
        )
        plan, err = self.swr.build_workflow_execution_plan(
            bundle, merged["values"], modal_options=None, gpu="l4",
        )
        self.assertIsNone(err)
        self.assertEqual(plan.request_metadata.get("selected_gpu"), "l4")

    def test_workflow_plan_freezes_selected_gpu_nonproduction_path(self):
        bundle = self._bundle()
        merged = self.swr.merge_workflow_controls(
            bundle["preset"], {}, bundle["control_schema"]
        )
        plan, err = self.swr.build_workflow_execution_plan(
            bundle, merged["values"],
            modal_options={"production": {"enabled": False}}, gpu="a10g",
        )
        self.assertIsNone(err)
        self.assertEqual(plan.request_metadata.get("selected_gpu"), "a10g")

    def test_later_settings_change_does_not_mutate_accepted_plan(self):
        bundle = self._bundle()
        merged = self.swr.merge_workflow_controls(
            bundle["preset"], {}, bundle["control_schema"]
        )
        plan, err = self.swr.build_workflow_execution_plan(
            bundle, merged["values"], modal_options=None, gpu="l4",
        )
        self.assertIsNone(err)
        frozen = dict(plan.request_metadata)
        # The user changes Settings after acceptance:
        # H20 Wave G isolation fix: restore the module global afterwards —
        # this leak was the historical F8→workflow reverse-order artifact.
        _orig_gpu = modal_client.get_gpu()
        self.addCleanup(lambda: _restore_gpu(_orig_gpu))
        modal_client._current_gpu = "h100"
        self.assertEqual(plan.request_metadata.get("selected_gpu"), "l4")
        self.assertEqual(dict(plan.request_metadata), frozen)

    def test_generate_original_replay_preserves_saved_gpu(self):
        from history_v2_replay import build_original_replay_plan

        bundle = self._bundle()
        merged = self.swr.merge_workflow_controls(
            bundle["preset"], {}, bundle["control_schema"]
        )
        saved, err = self.swr.build_workflow_execution_plan(
            bundle, merged["values"], modal_options=None, gpu="l4",
        )
        self.assertIsNone(err)
        replay = build_original_replay_plan(
            saved, request_id="req-f8", prompt_id="p-f8",
        )
        self.assertEqual(replay.request_metadata.get("selected_gpu"), "l4")

    def test_retry_original_preserves_saved_gpu(self):
        from history_v2_replay import build_original_replay_plan, validate_replay_delta

        bundle = self._bundle()
        merged = self.swr.merge_workflow_controls(
            bundle["preset"], {}, bundle["control_schema"]
        )
        saved, err = self.swr.build_workflow_execution_plan(
            bundle, merged["values"], modal_options=None, gpu="l4",
        )
        retry = build_original_replay_plan(saved, prompt_id="retry-f8")
        delta = validate_replay_delta(saved, retry)
        self.assertTrue(delta.ok, msg=f"unexpected delta paths: {delta.unexpected_paths}")
        self.assertEqual(retry.request_metadata.get("selected_gpu"), "l4")

    def test_single_resume_preserves_saved_gpu(self):
        from history_v2_replay import build_resume_replay_plan

        bundle = self._bundle()
        merged = self.swr.merge_workflow_controls(
            bundle["preset"], {}, bundle["control_schema"]
        )
        saved, err = self.swr.build_workflow_execution_plan(
            bundle, merged["values"], modal_options=None, gpu="l4",
        )
        resumed = build_resume_replay_plan(saved, prompt_id="resume-f8")
        self.assertEqual(resumed.request_metadata.get("selected_gpu"), "l4")

    def test_replay_dispatch_never_reads_current_settings_gpu(self):
        """The replay executor dispatches the SAVED plan without consulting
        current GPU Settings."""
        import canonical_execution as ce
        from history_v2_replay import _default_replay_executor

        bundle = self._bundle()
        merged = self.swr.merge_workflow_controls(
            bundle["preset"], {}, bundle["control_schema"]
        )
        saved, err = self.swr.build_workflow_execution_plan(
            bundle, merged["values"], modal_options=None, gpu="l4",
        )
        recorded = {}

        async def fake_execute_plan(plan, **kwargs):
            recorded["kwargs"] = kwargs
            recorded["meta"] = dict(plan.request_metadata)
            return {"trace": {}}

        def _explode():
            raise AssertionError("replay must not read current GPU Settings")

        with patch.object(ce, "execute_plan", fake_execute_plan), \
             patch.object(modal_client, "get_gpu", side_effect=lambda: _explode()), \
             patch("history_v2_replay._resolve_replay_workspace", return_value=None):
            _run(_default_replay_executor(saved))
        self.assertNotIn("gpu", recorded["kwargs"])
        self.assertEqual(recorded["meta"].get("selected_gpu"), "l4")


# ── 5. Transport boundary ────────────────────────────────────────────────


class F8TransportBoundaryTests(unittest.TestCase):
    """Frozen selected_gpu reaches the transport; fallback only when absent."""

    def _plan(self, gpu: str):
        from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan

        metadata = {"prompt_id": "p_f8"}
        if gpu is not None:
            metadata["selected_gpu"] = gpu
        return ExecutionPlan(
            workflow={"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
            workflow_hash="hash_f8",
            source_workflow_hash="src_hash_f8",
            execution_options=ExecutionOptions.from_legacy({}, default_production=False),
            request_metadata=metadata,
        )

    def _execute(self, plan, *, gpu=None):
        import canonical_execution as ce
        from unittest.mock import MagicMock

        captured = {}

        async def stream(plan_arg, *, gpu_arg=None, **kw):
            captured["gpu"] = gpu_arg
            yield {"type": "result", "data": {"outputs": {}}}

        async def _stream(plan, *, gpu=None, workspace=None, trace=None,
                          runtime_trace=None, **kwargs):
            captured["gpu"] = gpu
            yield {"type": "result", "data": {"outputs": {}}}

        mock_transport = MagicMock()
        mock_transport.run_plan_stream = _stream
        kwargs = {}
        if gpu is not None:
            kwargs["gpu"] = gpu
        _run(ce.execute_plan(plan, transport=mock_transport, **kwargs))
        return captured

    # 19.1 — plan selected_gpu=A reaches transport A
    def test_plan_selected_gpu_reaches_transport(self):
        captured = self._execute(self._plan("l4"))
        self.assertEqual(captured["gpu"], "l4")

    # 19.2 — non-empty selection not replaced by hardcoded default
    def test_nonempty_selection_not_replaced_by_hardcoded_default(self):
        captured = self._execute(self._plan("a10g"))
        self.assertNotEqual(captured["gpu"], "rtx-pro-6000")
        self.assertEqual(captured["gpu"], "a10g")

    # 19.3 — explicit per-request override beats frozen plan value
    def test_explicit_override_wins_over_frozen_plan(self):
        captured = self._execute(self._plan("l4"), gpu="h100")
        self.assertEqual(captured["gpu"], "h100")

    # 19.3b — fallback ONLY when field absent/empty
    def test_empty_selection_defers_to_transport_env_fallback(self):
        captured = self._execute(self._plan(""))
        self.assertIsNone(captured["gpu"])
        captured_absent = self._execute(self._plan(None))
        self.assertIsNone(captured_absent["gpu"])

    def test_transport_canonicalize_env_then_hardcoded_fallback(self):
        from comfymodal_runtime.modal_transport import ModalTransport

        self.assertEqual(
            ModalTransport._canonicalize_gpu_config(None), "rtx-pro-6000"
        )
        self.assertEqual(
            ModalTransport._canonicalize_gpu_config(""), "rtx-pro-6000"
        )
        with patch.dict("os.environ", {"COMFYMODAL_V2_GPU": "L4"}):
            self.assertEqual(ModalTransport._canonicalize_gpu_config(None), "l4")
        # An explicit selection is never overridden by the env fallback.
        with patch.dict("os.environ", {"COMFYMODAL_V2_GPU": "L4"}):
            self.assertEqual(
                ModalTransport._canonicalize_gpu_config("h100"), "h100"
            )

    # 19.4 — unavailable/unsupported selected GPU fails truthfully (fail-closed)
    def test_unsupported_selection_fails_closed_not_substituted(self):
        from studio_run_adapter import resolve_request_gpu

        with self.assertRaises(ValueError):
            resolve_request_gpu("v100-ancient", None)


# ── 6. Experiment invoker cell-plan consistency ──────────────────────────


class F8ExperimentInvokerFreezeTests(unittest.TestCase):
    """V2ExperimentInvoker freezes its construction GPU into every cell plan."""

    def test_all_cells_use_the_gpu_frozen_into_the_invoker(self):
        import canonical_execution as ce
        from comfymodal_runtime import modal_transport as mt_mod
        from comfymodal_runtime import result_delivery as rd
        from comfymodal_runtime.v2_experiment_invoker import V2ExperimentInvoker
        import local_artifacts

        builds: list[str] = []
        executions: list[str] = []
        fake_plan = SimpleNamespace(output_node_ids=[])

        def fake_build(workflow, *, prompt_id="", modal_options=None,
                       production_options=None, gpu=None, workspace=None,
                       validate=False, **kw):
            builds.append(gpu or "")
            return fake_plan

        async def fake_execute(plan, *, transport=None, profile_setter=None,
                               gpu=None, workspace=None, trace=None,
                               event_sink=None, **kw):
            executions.append(gpu or "")
            return {"trace": {}}

        def fake_materialize(*a, **k):
            return {"written_files": [], "history_outputs": {},
                    "primary_output": None, "materialization_timing": {}}

        out_dir = Path(self._tmp_dir())

        with patch.object(ce, "build_execution_plan", fake_build), \
             patch.object(ce, "execute_plan", fake_execute), \
             patch.object(mt_mod, "ModalTransport", lambda *a, **k: SimpleNamespace()), \
             patch.object(rd, "materialize_modal_result", fake_materialize), \
             patch.object(local_artifacts, "get_studio_outputs_dir",
                          lambda: out_dir):
            invoker = V2ExperimentInvoker(
                "exp_f8_invoker", gpu="l4",
                modal_options={"auto_save_local": False},
            )
            _run(invoker.open_worker("w1", "ck1", "p1", {}, {}))
            cells = [
                {"cell_key": "c1", "_resolved_workflow": {"1": {}}, "attempt_id": "a1"},
                {"cell_key": "c2", "_resolved_workflow": {"1": {}}, "attempt_id": "a2"},
            ]
            for cell in cells:
                result = _run(invoker.run_cell("w1", cell))
                self.assertEqual(result.get("status"), "completed")

        self.assertEqual(builds, ["l4", "l4"])
        self.assertEqual(executions, ["l4", "l4"])

    def _tmp_dir(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        return path


if __name__ == "__main__":
    unittest.main()
