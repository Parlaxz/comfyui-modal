"""D1 dispatch-hash coverage fix tests (zero-gap registry elimination).

ROOT CAUSE being covered: ``build_execution_plan`` keys the registry-proof
store, the plan, and the validation memo by the hash of the DISPATCH workflow
— which differs from ``prompt_sha256(source)`` whenever production compile
rewrites the dict.  The harness's outer coverage check
``_registry_proof_store_covers`` used to compute the RAW source hash, so it
always missed when production compile was active (``latest_benchmark_workflow.json``
has ``production.enabled=True``) — violating the D1 zero-gap contract (17-90 s
registry import after a user trigger).

The fix adds ``canonical_execution.resolve_dispatch_workflow_hash`` (a pure
dict-work mirror of the compile decision) as the single source of truth used
by BOTH ``build_execution_plan`` (line-1385 dispatch hash) and the harness
coverage check.

Covered here (hermetic; NO Modal, NO network, NO live registry):
  a) resolve_dispatch_workflow_hash matches compile_production_workflow; the
     disabled/absent path hashes the source unchanged.
  b) Full D1 round-trip with a production-compiled workflow: saving under the
     helper's hash makes ``_registry_proof_store_covers`` return True; the
     pre-fix source-hash keying is now correctly a miss.
  c) Regression: production disabled -> source-hash keying still hits
     (behavior identical to before the fix).
  d) build_execution_plan still persists under the dispatch hash
     (plan.workflow_hash == store entry workflow_hash == helper hash).
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
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


# A production-compileable synthetic workflow mirroring the canonical shape
# (SaveImage output node 107 is the production output surface).
WORKFLOW: dict[str, Any] = {
    "3": {"class_type": "KSampler", "inputs": {
        "seed": 7, "steps": 20, "cfg": 3.5,
        "sampler_name": "euler", "scheduler": "normal", "denoise": 1,
    }},
    "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024}},
    "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "unet.safetensors"}},
    "12": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
    "67": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": "hello"}},
    "9": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["12", 0]}},
    "107": {"class_type": "SaveImage", "inputs": {"images": ["9", 0]}},
}

MODAL_OPTIONS: dict[str, Any] = {
    "production": {"enabled": True, "output_node_ids": ["107"]},
}


def _deployed_state(
    generation: str = "gen-1",
    deployment_hash: str = "hash-1",
    version: str = "0.24.0",
    commit: str = "c0ffee",
) -> dict:
    return {
        "custom_nodes_generation": generation,
        "deployment_combined_hash": deployment_hash,
        "overall_dependency_hash": "overall-1",
        "comfyui_version": version,
        "comfyui_commit": commit,
    }


def _synthetic_entry(**overrides) -> dict:
    entry: dict[str, Any] = {
        "registry_fingerprint": "fp-abc123",
        "registry_proof": {
            "schema_version": 1,
            "workflow_class_count": 2,
            "classes": ["X", "Y"],
            "identities": {"X": "id-x", "Y": "id-y"},
            "missing_host": [],
            "unresolved_identity": [],
            "complete": True,
        },
        "validation": {
            "schema_version": 1,
            "validated": True,
            "outputs_to_execute": ["107"],
            "node_errors": {},
            "source": "host_validate_prompt",
        },
    }
    entry.update(overrides)
    return entry


class _StoreEnvBase(unittest.TestCase):
    """Isolated store + deployed-state temp files via env overrides."""

    def setUp(self):
        self._td = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self._td, ignore_errors=True))
        self._store = Path(self._td) / "store.json"
        self._state = Path(self._td) / "deployed_state.json"
        self._saved_store = os.environ.get("COMFYMODAL_V2_REGISTRY_PROOF_STORE")
        self._saved_state = os.environ.get("COMFYMODAL_V2_DEPLOYED_STATE_JSON")
        os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = str(self._store)
        os.environ["COMFYMODAL_V2_DEPLOYED_STATE_JSON"] = str(self._state)
        import comfymodal_runtime.registry_proof_store as mod
        self.store_mod = mod

    def tearDown(self):
        for env_name, saved in (
            ("COMFYMODAL_V2_REGISTRY_PROOF_STORE", self._saved_store),
            ("COMFYMODAL_V2_DEPLOYED_STATE_JSON", self._saved_state),
        ):
            if saved is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = saved

    def _write_state(self, state: dict | None = None):
        self._state.write_text(
            json.dumps(state if state is not None else _deployed_state()),
            encoding="utf-8",
        )


class TestResolveDispatchWorkflowHash(unittest.TestCase):
    """a) The helper mirrors the compile decision exactly (no registry)."""

    def setUp(self):
        self.mod = _load_canonical()
        self.resolve = self.mod.resolve_dispatch_workflow_hash

    def test_production_enabled_hashes_compiled(self):
        from production_workflow import compile_production_workflow, normalize_production_options
        from workflow_metadata import prompt_sha256

        opts = normalize_production_options(MODAL_OPTIONS)
        compiled = compile_production_workflow(
            WORKFLOW, opts, allow_direct_output_rewrite=True
        )
        expected = prompt_sha256(compiled.compiled_workflow)
        self.assertEqual(
            self.resolve(WORKFLOW, modal_options=MODAL_OPTIONS), expected
        )
        self.assertEqual(
            self.resolve(WORKFLOW, production_options=opts), expected
        )
        self.assertEqual(
            self.resolve(
                WORKFLOW, modal_options=MODAL_OPTIONS, production_options=opts
            ),
            expected,
        )

    def test_production_disabled_hashes_source(self):
        from workflow_metadata import prompt_sha256

        off = {"production": {"enabled": False}}
        self.assertEqual(
            self.resolve(WORKFLOW, modal_options=off), prompt_sha256(WORKFLOW)
        )
        self.assertEqual(self.resolve(WORKFLOW), prompt_sha256(WORKFLOW))
        self.assertEqual(
            self.resolve(WORKFLOW, production_options={"enabled": False}),
            prompt_sha256(WORKFLOW),
        )

    def test_modal_options_derivation_matches_explicit_options(self):
        from production_workflow import normalize_production_options

        opts = normalize_production_options(MODAL_OPTIONS)
        via_modal = self.resolve(WORKFLOW, modal_options=MODAL_OPTIONS)
        via_explicit = self.resolve(WORKFLOW, production_options=opts)
        self.assertEqual(via_modal, via_explicit)
        # Production compile DOES change the hash (dispatch != source).
        self.assertNotEqual(via_modal, self.resolve(WORKFLOW))


class TestRegistryProofStoreCoversDispatchHash(_StoreEnvBase):
    """b/c) Full D1 round-trip under a production-compiled workflow."""

    def setUp(self):
        super().setUp()
        self._write_state()
        self.bvd = _bvd()
        self.comfyui_root = str(self.bvd._COMFYUI_ROOT_DIR or "")

    def _save(self, workflow_hash: str):
        self.store_mod.save({
            "workflow_hash": workflow_hash,
            "comfyui_root": self.comfyui_root,
            "registry_fingerprint": _synthetic_entry()["registry_fingerprint"],
            "registry_proof": _synthetic_entry()["registry_proof"],
            "validation": _synthetic_entry()["validation"],
        })

    def test_production_compiled_store_hit_via_modal_options(self):
        """Save keyed by the helper's dispatch hash -> coverage True (the D1
        zero-gap fast path now engages for a production-compiled workflow)."""
        dispatch_hash = self.bvd.resolve_dispatch_workflow_hash(
            WORKFLOW, modal_options=MODAL_OPTIONS
        )
        self._save(dispatch_hash)
        self.assertTrue(self.bvd._registry_proof_store_covers(
            WORKFLOW, modal_options=MODAL_OPTIONS
        ))
        # Stored entry's workflow_hash is exactly the helper hash.
        hit = self.store_mod.lookup(dispatch_hash, self.comfyui_root)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["registry_fingerprint"], "fp-abc123")

    def test_production_compiled_hit_with_explicit_options(self):
        """The prime/acceptance call-site shape (production_options passed)."""
        from production_workflow import normalize_production_options

        opts = normalize_production_options(MODAL_OPTIONS)
        dispatch_hash = self.bvd.resolve_dispatch_workflow_hash(
            WORKFLOW, modal_options=MODAL_OPTIONS, production_options=opts
        )
        self._save(dispatch_hash)
        self.assertTrue(self.bvd._registry_proof_store_covers(
            WORKFLOW,
            modal_options=MODAL_OPTIONS,
            production_options=opts if opts.get("enabled") else None,
        ))

    def test_source_hash_miss_when_production_compiled(self):
        """The PRE-FIX key (source hash) is now correctly a miss once the
        store is keyed by the dispatch hash — the original defect scenario."""
        from workflow_metadata import prompt_sha256

        self._save(prompt_sha256(WORKFLOW))
        self.assertFalse(self.bvd._registry_proof_store_covers(
            WORKFLOW, modal_options=MODAL_OPTIONS
        ))
        # The dispatch-hash entry does NOT exist yet -> still False.
        self.assertFalse(self.bvd._registry_proof_store_covers(
            WORKFLOW, modal_options=MODAL_OPTIONS
        ))

    def test_production_disabled_source_hash_hit(self):
        """c) Regression: production disabled -> source-hash keying still
        hits (behavior identical to before the fix)."""
        from workflow_metadata import prompt_sha256

        off = {"production": {"enabled": False}}
        self._save(prompt_sha256(WORKFLOW))
        self.assertTrue(self.bvd._registry_proof_store_covers(
            WORKFLOW, modal_options=off
        ))
        # No options at all -> source hash too.
        self.assertTrue(self.bvd._registry_proof_store_covers(WORKFLOW))


class TestBuildExecutionPlanStoresDispatchHash(_StoreEnvBase):
    """d) build_execution_plan persists under the dispatch hash when
    production compile is active (validate=False, stubbed registry)."""

    def setUp(self):
        super().setUp()
        self._write_state()
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
        super().tearDown()

    def test_plan_workflow_hash_and_store_key_match_helper(self):
        save_calls: list[dict[str, Any]] = []

        def fake_save(fields: dict):
            save_calls.append(dict(fields))

        def fake_validate(prompt_id: str, workflow: dict) -> dict:
            return _synthetic_entry()["validation"]

        from production_workflow import normalize_production_options

        opts = normalize_production_options(MODAL_OPTIONS)
        expected = self.mod.resolve_dispatch_workflow_hash(
            WORKFLOW, modal_options=MODAL_OPTIONS, production_options=opts
        )
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
                 return_value=_synthetic_entry()["registry_proof"],
             ), \
             mock.patch(
                 "canonical_execution._collect_plan_validation_proof",
                 side_effect=fake_validate,
             ), \
             _stub_modules({"nodes": _make_fake_nodes()}):
            plan = self.mod.build_execution_plan(
                dict(WORKFLOW), prompt_id="p1", validate=False,
                modal_options=MODAL_OPTIONS,
                production_options=opts,
                collect_validation_proof=True,
                comfyui_root=str(_REPO_ROOT),
            )
        # Plan hash, persisted store key, and helper hash all agree.
        self.assertEqual(plan.workflow_hash, expected)
        self.assertTrue(save_calls, "store save expected on the miss path")
        self.assertEqual(save_calls[0]["workflow_hash"], expected)
        self.assertEqual(save_calls[0]["workflow_hash"], plan.workflow_hash)
        # The persisted key is NOT the raw source hash (dispatch != source).
        from workflow_metadata import prompt_sha256

        self.assertNotEqual(expected, prompt_sha256(WORKFLOW))


if __name__ == "__main__":
    unittest.main()
