"""D1 registry-proof store tests (zero-gap registry elimination).

The D1 zero-gap architecture persists the registry fingerprint / workflow
registry proof / validation payload to a disk store keyed by the deploy-frozen
identity (``.deployed_state.json``: custom_nodes_generation +
deployment_combined_hash + comfyui_version + comfyui_commit) + normalized
comfyui_root + workflow hash.  On a store hit, plan construction reuses the
persisted payloads WITHOUT importing the full ComfyUI node registry
(17-90 s per fresh command).

Covered here (all deterministic, NO real sleeping, NO Modal, NO network, and
NEVER the real ``_ensure_full_node_registry``):
  T1  store round-trip (save → lookup hit / different hash miss /
      changed-generation miss)
  T2  fail-closed (missing/corrupt/wrong-schema store, empty anchor)
  T3  bounded + merge (max entries eviction; partial save merges)
  T4  _collect_plan_deployment_identity fast path (compute funcs never called)
  T5  build_execution_plan validation disk-hit (no live validate_prompt)
  T6  build_execution_plan miss persists (store save called)
  T7  harness _registry_proof_store_covers coverage semantics
  T8  _run_one store-hit skips registry load; miss loads it
  T9  build_user_trigger_line synthetic stamps
  T10 _prime_registry_proof mode
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CANONICAL_PATH = _REPO_ROOT / "canonical_execution.py"

_BVD_MODULE: Any = None


def _bvd():
    """Lazy guarded import of the heavy benchmark harness module."""
    global _BVD_MODULE
    if _BVD_MODULE is None:
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        import tools.benchmark_v2_direct as _mod
        _BVD_MODULE = _mod
    return _BVD_MODULE


def _load_canonical():
    """Load canonical_execution module without parent-ComfyUI imports."""
    spec = importlib.util.spec_from_file_location(
        "canonical_execution", _CANONICAL_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["canonical_execution"] = mod
    spec.loader.exec_module(mod)
    return mod


class _DummyNode:
    """Simple stand-in for a NODE_CLASS_MAPPINGS entry."""


def _make_fake_nodes(mappings=None):
    mod = types.ModuleType("nodes")
    if mappings is None:
        mappings = {"X": _DummyNode, "Y": _DummyNode}
    mod.NODE_CLASS_MAPPINGS = mappings
    return mod


class _stub_modules:
    def __init__(self, stubs):
        self._stubs = stubs
        self._saved = {}

    def __enter__(self):
        for name, value in self._stubs.items():
            self._saved[name] = sys.modules.get(name)
            sys.modules[name] = value
        return self

    def __exit__(self, exc_type, exc, tb):
        for name, value in self._saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        return False


# A valid 2-node workflow shape.
WORKFLOW_A = {
    "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
    "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
}


def _deployed_state(
    generation: str = "gen-1",
    deployment_hash: str = "hash-1",
    version: str = "0.24.0",
    commit: str = "c0ffee",
    overall: str = "overall-1",
) -> dict:
    return {
        "custom_nodes_generation": generation,
        "deployment_combined_hash": deployment_hash,
        "overall_dependency_hash": overall,
        "comfyui_version": version,
        "comfyui_commit": commit,
    }


def _synthetic_entry(**overrides) -> dict:
    entry = {
        "registry_fingerprint": "fp-abc123",
        "registry_proof": {
            "schema_version": 1,
            "workflow_class_count": 2,
            "classes": ["KSampler", "SaveImage"],
            "identities": {"KSampler": "id-ks", "SaveImage": "id-si"},
            "missing_host": [],
            "unresolved_identity": [],
            "complete": True,
        },
        "validation": {
            "schema_version": 1,
            "validated": True,
            "outputs_to_execute": ["2"],
            "node_errors": {},
            "source": "host_validate_prompt",
        },
    }
    entry.update(overrides)
    return entry


# ============================================================================
# Store-level tests (T1-T3)
# ============================================================================


class _StoreEnvBase(unittest.TestCase):
    """Sets up isolated store + deployed-state temp files via env overrides."""

    def setUp(self):
        self._td = tempfile.mkdtemp()
        self._store = Path(self._td) / "store.json"
        self._state = Path(self._td) / "deployed_state.json"
        self._saved_store = os.environ.get("COMFYMODAL_V2_REGISTRY_PROOF_STORE")
        self._saved_state = os.environ.get("COMFYMODAL_V2_DEPLOYED_STATE_JSON")
        os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = str(self._store)
        os.environ["COMFYMODAL_V2_DEPLOYED_STATE_JSON"] = str(self._state)
        import comfymodal_runtime.registry_proof_store as mod
        self.store_mod = mod

    def tearDown(self):
        import shutil
        for env_name, saved in (
            ("COMFYMODAL_V2_REGISTRY_PROOF_STORE", self._saved_store),
            ("COMFYMODAL_V2_DEPLOYED_STATE_JSON", self._saved_state),
        ):
            if saved is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = saved
        shutil.rmtree(self._td, ignore_errors=True)

    def _write_state(self, state: dict | None = None):
        self._state.write_text(json.dumps(state if state is not None else _deployed_state()),
                               encoding="utf-8")


class TestStoreRoundTrip(_StoreEnvBase):
    def test_round_trip_hit_and_misses(self):
        self._write_state()
        self.store_mod.save({
            "workflow_hash": "wf-1",
            "comfyui_root": str(self._td),
            "registry_fingerprint": "fp-abc123",
            "registry_proof": _synthetic_entry()["registry_proof"],
            "validation": _synthetic_entry()["validation"],
        })
        # Same workflow_hash + comfyui_root → hit with identical payloads.
        hit = self.store_mod.lookup("wf-1", str(self._td))
        self.assertIsNotNone(hit)
        self.assertEqual(hit["registry_fingerprint"], "fp-abc123")
        self.assertTrue(hit["registry_proof"]["complete"])
        self.assertEqual(hit["validation"]["validated"], True)
        # Different workflow_hash → None.
        self.assertIsNone(self.store_mod.lookup("wf-other", str(self._td)))
        # Different comfyui_root → None.
        self.assertIsNone(self.store_mod.lookup("wf-1", "C:\\some\\other\\root"))
        # Changed generation → None.
        self._write_state(_deployed_state(generation="gen-2"))
        self.assertIsNone(self.store_mod.lookup("wf-1", str(self._td)))

    def test_lookup_normalizes_comfyui_root(self):
        self._write_state()
        self.store_mod.save({
            "workflow_hash": "wf-1",
            "comfyui_root": str(self._td),
            "registry_fingerprint": "fp-x",
            "registry_proof": _synthetic_entry()["registry_proof"],
            "validation": _synthetic_entry()["validation"],
        })
        # Trailing separator / different separator spellings collide.
        hit = self.store_mod.lookup("wf-1", str(self._td) + os.sep)
        self.assertIsNotNone(hit)


class TestStoreFailClosed(_StoreEnvBase):
    def test_missing_store_file(self):
        self._write_state()
        self.assertIsNone(self.store_mod.lookup("wf-1", str(self._td)))
        self.assertFalse(self.store_mod.has_generation_entry())

    def test_corrupt_store_json(self):
        self._write_state()
        self._store.write_text("{not json!!", encoding="utf-8")
        self.assertIsNone(self.store_mod.lookup("wf-1", str(self._td)))
        self.assertFalse(self.store_mod.has_generation_entry())

    def test_wrong_schema_version(self):
        self._write_state()
        self._store.write_text(json.dumps({
            "schema_version": 99,
            "entries": {},
        }), encoding="utf-8")
        self.assertIsNone(self.store_mod.lookup("wf-1", str(self._td)))

    def test_empty_anchor_save_noop_and_lookup_none(self):
        # No deployed-state file at all → anchor empty.
        self.assertFalse(self._state.exists())
        self.store_mod.save({
            "workflow_hash": "wf-1",
            "comfyui_root": str(self._td),
            "registry_fingerprint": "fp-abc123",
            "registry_proof": _synthetic_entry()["registry_proof"],
        })
        self.assertIsNone(self.store_mod.lookup("wf-1", str(self._td)))
        self.assertFalse(self.store_mod.has_generation_entry())
        # Partial deployed-state (missing fields) → anchor empty.
        self._state.write_text(json.dumps({"custom_nodes_generation": "gen-1"}),
                               encoding="utf-8")
        self.store_mod.save({
            "workflow_hash": "wf-1",
            "comfyui_root": str(self._td),
            "registry_fingerprint": "fp-abc123",
            "registry_proof": _synthetic_entry()["registry_proof"],
        })
        self.assertIsNone(self.store_mod.lookup("wf-1", str(self._td)))


class TestStoreBoundedAndMerge(_StoreEnvBase):
    def test_max_entries_bounded(self):
        self._write_state()
        for i in range(10):
            self.store_mod.save({
                "workflow_hash": f"wf-{i}",
                "comfyui_root": str(self._td),
                "registry_fingerprint": f"fp-{i}",
                "registry_proof": _synthetic_entry()["registry_proof"],
                "validation": _synthetic_entry()["validation"],
            })
        data = json.loads(self._store.read_text(encoding="utf-8"))
        self.assertLessEqual(len(data["entries"]), self.store_mod._MAX_ENTRIES)
        # Newest keys retained.
        self.assertIsNotNone(self.store_mod.lookup("wf-9", str(self._td)))

    def test_merge_keeps_existing_payload(self):
        self._write_state()
        # First save: fingerprint + proof, no validation.
        self.store_mod.save({
            "workflow_hash": "wf-1",
            "comfyui_root": str(self._td),
            "registry_fingerprint": "fp-abc123",
            "registry_proof": _synthetic_entry()["registry_proof"],
        })
        hit1 = self.store_mod.lookup("wf-1", str(self._td))
        self.assertEqual(hit1["registry_fingerprint"], "fp-abc123")
        self.assertNotIn("validation", hit1)
        # Second save: validation only → fingerprint retained, validation added.
        self.store_mod.save({
            "workflow_hash": "wf-1",
            "comfyui_root": str(self._td),
            "validation": _synthetic_entry()["validation"],
        })
        hit2 = self.store_mod.lookup("wf-1", str(self._td))
        self.assertEqual(hit2["registry_fingerprint"], "fp-abc123")
        self.assertEqual(hit2["validation"]["validated"], True)


# ============================================================================
# canonical_execution seams (T4-T6)
# ============================================================================


class _FrozenIdentityBase(unittest.TestCase):
    """Frozen deploy identity patches shared by T4-T6."""

    def setUp(self):
        import contextlib
        import shutil
        self._td = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self._td, ignore_errors=True))
        self._temp_store = str(Path(self._td) / "store.json")
        self._temp_state = str(Path(self._td) / "deployed_state.json")
        # Isolate the store module's OWN anchor/save paths (build_execution_plan
        # persists via the real store save() on the miss path — never write to
        # the real repo store during tests).
        self._saved_store = os.environ.get("COMFYMODAL_V2_REGISTRY_PROOF_STORE")
        self._saved_state = os.environ.get("COMFYMODAL_V2_DEPLOYED_STATE_JSON")
        os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = self._temp_store
        os.environ["COMFYMODAL_V2_DEPLOYED_STATE_JSON"] = self._temp_state
        Path(self._temp_state).write_text(json.dumps(_deployed_state()), encoding="utf-8")
        self.mod = _load_canonical()
        self.mod._PLAN_VALIDATION_MEMO.clear()
        self._saved_env = os.environ.get("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH")
        os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
        self._frozen = _deployed_state()
        self._stack = contextlib.ExitStack()
        self._stack.enter_context(mock.patch.object(
            self.mod, "_read_persisted_deployment_combined_hash",
            return_value=self._frozen["deployment_combined_hash"],
        ))
        self._stack.enter_context(mock.patch.object(
            self.mod, "_read_frozen_deployed_identity",
            return_value=dict(self._frozen),
        ))
        self.addCleanup(self._stack.close)

    def tearDown(self):
        if self._saved_env is None:
            os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
        else:
            os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = self._saved_env
        for env_name, saved in (
            ("COMFYMODAL_V2_REGISTRY_PROOF_STORE", self._saved_store),
            ("COMFYMODAL_V2_DEPLOYED_STATE_JSON", self._saved_state),
        ):
            if saved is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = saved


class TestCollectDeploymentIdentityFastPath(_FrozenIdentityBase):
    def test_store_hit_reuses_persisted_payload(self):
        """Store hit → persisted fingerprint/proof used; live compute NEVER
        called (patched to raise)."""
        entry = _synthetic_entry()
        with mock.patch(
                 "comfymodal_runtime.registry_proof_store.lookup", return_value=entry
             ), \
             mock.patch(
                 "comfymodal_runtime.contracts.compute_registry_fingerprint",
                 side_effect=AssertionError("should not compute fingerprint"),
             ), \
             mock.patch(
                 "comfymodal_runtime.registry_proof.build_workflow_registry_proof",
                 side_effect=AssertionError("should not build proof"),
             ), \
             _stub_modules({"nodes": _make_fake_nodes()}):
            ident = self.mod._collect_plan_deployment_identity(
                {}, str(_REPO_ROOT), workflow=WORKFLOW_A
            )
        self.assertEqual(ident["registry_fingerprint"], "fp-abc123")
        self.assertEqual(ident["registry_proof"]["complete"], True)
        self.assertIs(ident["deployment_identity_frozen"], True)
        # complete semantics preserved: dep + gen + proof complete.
        self.assertIs(ident["complete"], True)

    def test_store_miss_falls_back_to_live_compute(self):
        """Store miss → live compute runs (fingerprint/proof called)."""
        called = {"fp": 0, "proof": 0}

        def fake_fp(**kw):
            called["fp"] += 1
            return "fp-live"

        def fake_proof(workflow, **kw):
            called["proof"] += 1
            return _synthetic_entry()["registry_proof"]

        with mock.patch("comfymodal_runtime.registry_proof_store.lookup", return_value=None), \
             mock.patch("comfymodal_runtime.contracts.compute_registry_fingerprint", side_effect=fake_fp), \
             mock.patch(
                 "comfymodal_runtime.registry_proof.build_workflow_registry_proof",
                 side_effect=fake_proof,
             ), \
             _stub_modules({"nodes": _make_fake_nodes()}):
            ident = self.mod._collect_plan_deployment_identity(
                {}, str(_REPO_ROOT), workflow=WORKFLOW_A
            )
        self.assertEqual(called["fp"], 1)
        self.assertEqual(called["proof"], 1)
        self.assertEqual(ident["registry_fingerprint"], "fp-live")
        self.assertIs(ident["complete"], True)


class TestBuildExecutionPlanValidationDiskHit(_FrozenIdentityBase):
    def test_disk_hit_populates_validation_without_live_validate(self):
        """Store entry carries validation → plan.validation populated from the
        persisted payload; live _collect_plan_validation_proof NEVER called."""
        entry = _synthetic_entry()
        with mock.patch(
                 "comfymodal_runtime.registry_proof_store.lookup", return_value=entry
             ), \
             mock.patch(
                 "comfymodal_runtime.contracts.compute_registry_fingerprint",
                 side_effect=AssertionError("should not compute fingerprint"),
             ), \
             mock.patch(
                 "comfymodal_runtime.registry_proof.build_workflow_registry_proof",
                 side_effect=AssertionError("should not build proof"),
             ), \
             mock.patch(
                 "canonical_execution._collect_plan_validation_proof",
                 side_effect=AssertionError("should not validate live"),
             ), \
             _stub_modules({"nodes": _make_fake_nodes()}):
            plan = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True, comfyui_root=str(_REPO_ROOT),
            )
        self.assertEqual(plan.validation.get("validated"), True)
        self.assertEqual(list(plan.validation.get("outputs_to_execute") or []), ["2"])
        self.assertEqual(plan.validation.get("validated_workflow_hash"), plan.workflow_hash)


class TestBuildExecutionPlanMissPersists(_FrozenIdentityBase):
    def test_store_miss_runs_live_and_persists(self):
        """Store miss → live validation runs, store save called with the
        workflow hash + validation payload."""
        save_calls: list[dict[str, Any]] = []
        entry = _synthetic_entry()

        def fake_save(fields: dict):
            save_calls.append(dict(fields))

        with mock.patch(
                 "comfymodal_runtime.registry_proof_store.lookup", return_value=None
             ), \
             mock.patch(
                 "comfymodal_runtime.registry_proof_store.save", side_effect=fake_save
             ), \
             mock.patch(
                 "comfymodal_runtime.contracts.compute_registry_fingerprint",
                 return_value="fp-live",
             ), \
             mock.patch(
                 "comfymodal_runtime.registry_proof.build_workflow_registry_proof",
                 return_value=entry["registry_proof"],
             ), \
             mock.patch(
                 "canonical_execution._collect_plan_validation_proof",
                 return_value={
                     "schema_version": 1,
                     "validated": True,
                     "outputs_to_execute": ["2"],
                     "node_errors": {},
                     "source": "host_validate_prompt",
                 },
             ), \
             _stub_modules({"nodes": _make_fake_nodes()}):
            plan = self.mod.build_execution_plan(
                dict(WORKFLOW_A), prompt_id="p1", validate=False,
                collect_validation_proof=True, comfyui_root=str(_REPO_ROOT),
            )
        self.assertEqual(plan.validation.get("validated"), True)
        self.assertEqual(len(save_calls), 1)
        self.assertTrue(save_calls[0]["workflow_hash"])
        self.assertEqual(save_calls[0]["workflow_hash"], plan.workflow_hash)
        self.assertEqual(save_calls[0]["validation"]["validated"], True)
        self.assertEqual(save_calls[0]["registry_fingerprint"], "fp-live")


# ============================================================================
# Harness helpers (T7)
# ============================================================================


class TestRegistryProofStoreCovers(unittest.TestCase):
    def _patch_lookup(self, entry):
        return mock.patch(
            "comfymodal_runtime.registry_proof_store.lookup", return_value=entry
        )

    def test_covered_entry_returns_true(self):
        bvd = _bvd()
        with self._patch_lookup(_synthetic_entry()):
            self.assertTrue(bvd._registry_proof_store_covers(WORKFLOW_A))

    def test_missing_validation_and_proof_enabled_returns_false(self):
        bvd = _bvd()
        entry = _synthetic_entry()
        entry.pop("validation", None)
        with self._patch_lookup(entry):
            self.assertFalse(bvd._registry_proof_store_covers(WORKFLOW_A))

    def test_proof_disabled_allows_without_validation(self):
        bvd = _bvd()
        entry = _synthetic_entry()
        entry.pop("validation", None)
        with self._patch_lookup(entry), \
             mock.patch.object(bvd, "_PLAN_VALIDATION_PROOF", False):
            self.assertTrue(bvd._registry_proof_store_covers(WORKFLOW_A))

    def test_lookup_none_returns_false(self):
        bvd = _bvd()
        with self._patch_lookup(None):
            self.assertFalse(bvd._registry_proof_store_covers(WORKFLOW_A))


# ============================================================================
# _run_one store-hit skip (T8)
# ============================================================================


def _valid_runtime_trace() -> dict[str, Any]:
    from comfymodal_runtime.runtime_shape import runtime_shape_config
    shape = runtime_shape_config().identity_payload()
    remote_metadata = {
        "method_name": "run_plan_stream",
        "app_name": "stable-modal-comfy-v2-shadow",
        "class_name": "ModalRuntimeEntrypointV2",
        "gpu": "rtx-pro-6000",
        "cpu": 16,
        "memory_mb": 49152,
        "fingerprint": "test-snapshot-fingerprint",
        "runtime_shape": shape,
        "runtime_shape_fingerprint": shape["runtime_shape_fingerprint"],
        "runtime_shape_label": None,
        "stored_snapshot_model_order": "O0",
    }
    return {
        "events": [
            {"name": "remote_method_entry", "metadata": remote_metadata},
            {
                "name": "runtime_shape_observed",
                "metadata": {**shape, "status": "baseline_passthrough"},
            },
        ],
        "metadata": {},
    }


class TestRunOneStoreHitSkipsRegistry(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        self.output_dir = self._tmp
        self.workspace = {"token_id": "t", "token_secret": "s"}
        self.transport = mock.AsyncMock()
        self.workflow = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
        self.modal_options = {"production": {"enabled": False}}

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    async def _run(self, store_hit: bool) -> tuple[str, Any]:
        bvd = _bvd()
        result = {"trace": _valid_runtime_trace()}

        async def fake_execute_plan(plan: Any, **kw: Any) -> dict[str, Any]:
            return result

        class _SeqClock:
            def __init__(self):
                self._n = 0

            def __call__(self):
                n = self._n
                self._n += 1
                return (1_700_000_000_000_000_000 + n * 1_000_000,
                        1_000_000_000_000 + n * 1_000_000)

        registry = mock.AsyncMock(return_value=True)
        buf = io.StringIO()
        with (
            mock.patch("tools.benchmark_v2_direct._capture_ts", _SeqClock()),
            mock.patch("tools.benchmark_v2_direct.normalize_production_options", return_value={}),
            mock.patch("tools.benchmark_v2_direct.build_execution_plan", return_value={}),
            mock.patch("tools.benchmark_v2_direct.execute_plan", fake_execute_plan),
            mock.patch("tools.benchmark_v2_direct._ensure_full_node_registry", registry),
            mock.patch("tools.benchmark_v2_direct._validate_runtime_shape", return_value={}),
            mock.patch("tools.benchmark_v2_direct._validate_remote_profile"),
            mock.patch("tools.benchmark_v2_direct.reconcile_waterfall_local"),
            mock.patch("tools.benchmark_v2_direct._handle_full_trace_artifact", mock.AsyncMock()),
            mock.patch("comfymodal_runtime.modal_transport.join_persistence_drain", mock.AsyncMock()),
            mock.patch("tools.benchmark_v2_direct._registry_proof_store_covers", return_value=store_hit),
            mock.patch("sys.stdout", buf),
        ):
            artifact = await bvd._run_one(
                index=0,
                workflow=self.workflow,
                modal_options=self.modal_options,
                workspace=self.workspace,
                transport=self.transport,
                output_dir=self.output_dir,
            )
        return buf.getvalue(), artifact

    async def test_store_hit_skips_registry(self):
        out, artifact = await self._run(store_hit=True)
        self.assertIsInstance(artifact, dict)
        self.assertIn("[v2.harness] registry_load=skipped store_hit=yes", out)
        # Registry was NOT awaited on the store-hit path.
        self.assertIn("[v2.user_trigger]", out)
        self.assertIn("registry_store_hit=True", out)

    async def test_store_miss_loads_registry(self):
        out, artifact = await self._run(store_hit=False)
        self.assertIsInstance(artifact, dict)
        self.assertNotIn("[v2.harness] registry_load=skipped store_hit=yes", out)
        self.assertIn("[v2.user_trigger]", out)
        self.assertIn("registry_store_hit=False", out)
        self.assertIn("registry_load_ms=", out)


# ============================================================================
# build_user_trigger_line (T9)
# ============================================================================

_CMD_MS = 1_700_000_000_000
_CMD_NS = _CMD_MS * 1_000_000


def _parse(line):
    return dict(part.split("=", 1) for part in line.split(" ") if "=" in part)


class TestBuildUserTriggerLine(unittest.TestCase):
    def test_synthetic_stamps(self):
        bvd = _bvd()
        line = bvd.build_user_trigger_line(
            request_id="req-1",
            command_start_unix_ms=_CMD_MS,
            python_first_line_ns=_CMD_NS + 500_000_000,
            submission_attempt_wall_ns=_CMD_NS + 2_500_000_000,
            response_received_wall_ns=_CMD_NS + 3_000_000_000,
            registry_store_hit=True,
            registry_load_ms=0.0,
        )
        self.assertTrue(str(line).startswith("[v2.user_trigger]"))
        parts = _parse(line)
        self.assertEqual(parts["request_id"], "req-1")
        self.assertEqual(parts["process_start_to_response_ms"], "2500.0")
        self.assertEqual(parts["user_equivalent_trigger_to_response_ms"], "3000.0")
        self.assertEqual(parts["user_equivalent_trigger_to_modal_submission_ms"], "2500.0")
        self.assertEqual(parts["registry_store_hit"], "True")
        self.assertEqual(parts["registry_load_ms"], "0.0")

    def test_missing_stamps_absent_no_raise(self):
        bvd = _bvd()
        line = bvd.build_user_trigger_line(request_id="req-2")
        parts = _parse(line)
        self.assertEqual(parts["process_start_to_response_ms"], "absent")
        self.assertEqual(parts["user_equivalent_trigger_to_response_ms"], "absent")
        self.assertEqual(parts["user_equivalent_trigger_to_modal_submission_ms"], "absent")
        self.assertEqual(parts["registry_store_hit"], "absent")
        self.assertEqual(parts["registry_load_ms"], "absent")


# ============================================================================
# _prime_registry_proof (T10)
# ============================================================================


class TestPrimeRegistryProof(unittest.IsolatedAsyncioTestCase):
    async def test_prime_success(self):
        bvd = _bvd()
        registry = mock.AsyncMock(return_value=True)
        plan = SimpleNamespace(workflow_hash="h" * 64)
        buf = io.StringIO()
        with (
            mock.patch("tools.benchmark_v2_direct._ensure_full_node_registry", registry),
            mock.patch("tools.benchmark_v2_direct._load_workflow", return_value=(WORKFLOW_A, {})),
            mock.patch("tools.benchmark_v2_direct.normalize_production_options", return_value={}),
            mock.patch("tools.benchmark_v2_direct.build_execution_plan", return_value=plan),
            mock.patch("tools.benchmark_v2_direct._registry_proof_store_covers", return_value=True),
            mock.patch("comfymodal_runtime.registry_proof_store.store_path", return_value=Path("store.json")),
            mock.patch("sys.stdout", buf),
        ):
            await bvd._prime_registry_proof()
        registry.assert_awaited_once()
        data = json.loads("\n".join(
            ln for ln in buf.getvalue().splitlines()
            if ln.lstrip().startswith("{")
        ))
        self.assertTrue(data["prime_registry_proof"])
        self.assertTrue(data["prime_ok"])
        self.assertEqual(data["workflow_hash"], ("h" * 64)[:16])

    async def test_prime_failure_raises(self):
        bvd = _bvd()
        plan = SimpleNamespace(workflow_hash="h" * 64)
        with (
            mock.patch("tools.benchmark_v2_direct._ensure_full_node_registry", mock.AsyncMock(return_value=True)),
            mock.patch("tools.benchmark_v2_direct._load_workflow", return_value=(WORKFLOW_A, {})),
            mock.patch("tools.benchmark_v2_direct.normalize_production_options", return_value={}),
            mock.patch("tools.benchmark_v2_direct.build_execution_plan", return_value=plan),
            mock.patch("tools.benchmark_v2_direct._registry_proof_store_covers", return_value=False),
        ):
            with self.assertRaises(RuntimeError):
                await bvd._prime_registry_proof()


if __name__ == "__main__":
    unittest.main()
