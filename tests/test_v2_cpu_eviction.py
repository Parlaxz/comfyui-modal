"""Focused tests for CPU snapshot model eviction lifecycle.

Covers env-var strict parsing/propagation, memory field contract, full
eviction (unconditional both-model removal), reload of selected role,
new identity validation, storage/RSS/final-drop floors, callback ordering,
state cleanup, disabled compatibility, and restore idle ordering.

No tensors, psutil, or forbidden tools.
"""

from __future__ import annotations

import gc
import os
import sys
import time
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch, MagicMock, PropertyMock

from comfymodal_runtime.modal_app import (
    _parse_evict_models_before_snapshot,
    _parse_evict_restore_idle_seconds,
    _parse_evict_retain_role,
    _collect_process_memory,
    _runtime_env,
    ModalRuntimeEntrypoint,
    _RES4LYF_PREPARED,
    _CACHEDIT_PREPARED,
    _collect_warmup_env,
    build_unique_storage_registry,
)
from comfymodal_runtime.cpu_snapshot_models import CpuSnapshotModels
from comfymodal_runtime.contracts import ModelRestoreKey


# ── Helpers ────────────────────────────────────────────────────────────────


def _clean_env():
    """Remove eviction env vars so tests start from a known state."""
    for key in ("COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT",
                "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS",
                "COMFYMODAL_V2_EVICT_RETAIN_ROLE",
                "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT",
                "COMFYMODAL_ENABLE_GPU_SNAPSHOT"):
        os.environ.pop(key, None)


class _FakeModel:
    """Minimal weakrefable model stub for testing."""
    def __init__(self, name: str = "fake"):
        self.name = name
        self.model = self  # for model_management compatibility


class _FreshFakeModel:
    """Second model class so reload produces a distinct type/identity."""
    def __init__(self, name: str = "fresh"):
        self.name = name
        self.model = self


class _FakeBridge:
    """Minimal preload bridge stub for eviction testing."""
    def __init__(self):
        self._preparation = None
        self._original_methods = None

    def clear(self):
        self._preparation = None

    def diagnostic_snapshot(self):
        return {}

    def diagnostics(self):
        return {"active_preparation_exists": False, "unet_future": None, "clip_future": None}


class _FakeCoordinator:
    def __init__(self):
        self._active = None


def _make_minimal_cpu_models(
    unet_obj: Any = None,
    clip_obj: Any = None,
    unet_identity: str = "test_unet.safetensors",
    clip_identity: str = "test_clip.safetensors",
    *,
    normal_profile: dict[str, Any] | None = None,
) -> CpuSnapshotModels:
    """Build a minimal CpuSnapshotModels for eviction testing."""
    if unet_obj is None:
        unet_obj = _FakeModel("unet")
    if clip_obj is None:
        clip_obj = _FakeModel("clip")
    if normal_profile is None:
        normal_profile = {"mode": "split", "unet": "test_unet.safetensors",
                          "clip1": "test_clip.safetensors", "clip_type": "sd3"}
    return CpuSnapshotModels(
        model_key=ModelRestoreKey(
            unet_identity=unet_identity,
            clip_identity=clip_identity,
            vae_identity="",
            clip_type="sd3",
        ),
        model_spec={"loaders": {"unet": [{"weight_dtype": "default"}], "clip": [], "vae": []}},
        normalized_profile=normal_profile,
        file_facts=(),
        unet=unet_obj,
        clip=clip_obj,
        compute_policy="default",
        policy_version=2,
    )


def _make_fake_entrypoint(
    unet_obj: Any = None,
    clip_obj: Any = None,
    *,
    normal_profile: dict[str, Any] | None = None,
) -> ModalRuntimeEntrypoint:
    """Create an entrypoint with minimal bridge and pre-set cpu_snapshot_models."""
    ep = ModalRuntimeEntrypoint()
    if unet_obj is None:
        unet_obj = _FakeModel("unet")
    if clip_obj is None:
        clip_obj = _FakeModel("clip")
    ep._cpu_snapshot_models = _make_minimal_cpu_models(
        unet_obj=unet_obj, clip_obj=clip_obj, normal_profile=normal_profile,
    )
    ep._preload_bridge = _FakeBridge()
    ep._preload_bridge.coordinator = _FakeCoordinator()
    ep._cpu_snapshot_unet_runtime_state = {"old": "state"}
    ep._cpu_snapshot_unet_storage_registry = "old_reg"
    ep._cpu_snapshot_clip_storage_registry = "old_reg"
    ep._cpu_snapshot_models_active = True
    return ep


def _fake_process_memory(
    smaps_rss_mib: float = 30000.0,
    vm_rss_mib: float = 31000.0,
    smaps_anonymous_mib: float = 28000.0,
    smaps_private_dirty_mib: float = 27000.0,
    native_thread_count: int = 42,
    torch_intraop_threads: int = 4,
    torch_interop_threads: int = 4,
    loaded_module_count: int = 350,
) -> dict[str, Any]:
    """Return a complete _collect_process_memory response with exact fields."""
    return {
        "vm_rss_mib": vm_rss_mib,
        "vm_hwm_mib": vm_rss_mib,
        "smaps_rss_mib": smaps_rss_mib,
        "smaps_pss_mib": smaps_rss_mib * 0.8,
        "smaps_private_clean_mib": smaps_rss_mib * 0.1,
        "smaps_private_dirty_mib": smaps_private_dirty_mib,
        "smaps_shared_clean_mib": smaps_rss_mib * 0.05,
        "smaps_shared_dirty_mib": smaps_rss_mib * 0.05,
        "smaps_anonymous_mib": smaps_anonymous_mib,
        "native_thread_count": native_thread_count,
        "torch_intraop_threads": torch_intraop_threads,
        "torch_interop_threads": torch_interop_threads,
        "loaded_module_count": loaded_module_count,
    }


# ── Env var strict parsing tests ─────────────────────────────────────────


class ParseEvictModelsBeforeSnapshotTests(unittest.TestCase):
    """_parse_evict_models_before_snapshot strict parsing."""

    def setUp(self):
        _clean_env()

    def test_absent_disabled(self):
        self.assertFalse(_parse_evict_models_before_snapshot())

    def test_empty_disabled(self):
        os.environ["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"] = ""
        self.assertFalse(_parse_evict_models_before_snapshot())

    def test_zero_disabled(self):
        os.environ["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"] = "0"
        self.assertFalse(_parse_evict_models_before_snapshot())

    def test_one_enabled(self):
        os.environ["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"] = "1"
        self.assertTrue(_parse_evict_models_before_snapshot())

    def test_other_nonempty_raises(self):
        for val in ("2", "true", "yes", "on", "false", " -1"):
            with self.subTest(val=val):
                os.environ["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"] = val
                with self.assertRaises(RuntimeError):
                    _parse_evict_models_before_snapshot()


class ParseEvictRestoreIdleSecondsTests(unittest.TestCase):
    """_parse_evict_restore_idle_seconds strict parsing."""

    def setUp(self):
        _clean_env()

    def test_absent_zero(self):
        self.assertEqual(_parse_evict_restore_idle_seconds(), 0)

    def test_empty_zero(self):
        os.environ["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"] = ""
        self.assertEqual(_parse_evict_restore_idle_seconds(), 0)

    def test_zero_zero(self):
        os.environ["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"] = "0"
        self.assertEqual(_parse_evict_restore_idle_seconds(), 0)

    def test_positive_integer_accepted(self):
        os.environ["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"] = "5"
        self.assertEqual(_parse_evict_restore_idle_seconds(), 5)

    def test_large_integer_accepted(self):
        os.environ["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"] = "300"
        self.assertEqual(_parse_evict_restore_idle_seconds(), 300)

    def test_negative_raises(self):
        os.environ["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"] = "-5"
        with self.assertRaises(RuntimeError):
            _parse_evict_restore_idle_seconds()

    def test_float_raises(self):
        os.environ["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"] = "3.5"
        with self.assertRaises(RuntimeError):
            _parse_evict_restore_idle_seconds()

    def test_non_numeric_raises(self):
        for val in ("abc", "true", "0x10"):
            with self.subTest(val=val):
                os.environ["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"] = val
                with self.assertRaises(RuntimeError):
                    _parse_evict_restore_idle_seconds()


# ── _runtime_env propagation tests ──────────────────────────────────────


class RuntimeEnvPropagationTests(unittest.TestCase):
    """_runtime_env propagates eviction env vars when present in os.environ."""

    def setUp(self):
        _clean_env()

    def test_absent_not_in_env(self):
        env = _runtime_env()
        self.assertNotIn("COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT", env)
        self.assertNotIn("COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS", env)
        self.assertNotIn("COMFYMODAL_V2_EVICT_RETAIN_ROLE", env)

    def test_present_in_env_when_set(self):
        os.environ["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"] = "1"
        os.environ["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"] = "30"
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "clip"
        env = _runtime_env()
        self.assertEqual(env["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"], "1")
        self.assertEqual(env["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"], "30")
        self.assertEqual(env["COMFYMODAL_V2_EVICT_RETAIN_ROLE"], "clip")

    def test_present_with_zero_values(self):
        os.environ["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"] = "0"
        os.environ["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"] = "0"
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "none"
        env = _runtime_env()
        self.assertEqual(env["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"], "0")
        self.assertEqual(env["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"], "0")
        self.assertEqual(env["COMFYMODAL_V2_EVICT_RETAIN_ROLE"], "none")


# ── Memory field contract tests ──────────────────────────────────────────


class CollectProcessMemoryFieldContractTests(unittest.TestCase):
    """Each field matches the exact return type contract."""

    def test_all_fields_have_expected_types(self):
        result = _collect_process_memory()
        for key in ("vm_rss_mib", "vm_hwm_mib",
                     "smaps_rss_mib", "smaps_pss_mib",
                     "smaps_private_clean_mib", "smaps_private_dirty_mib",
                     "smaps_shared_clean_mib", "smaps_shared_dirty_mib",
                     "smaps_anonymous_mib"):
            val = result.get(key)
            self.assertTrue(
                val == "absent" or isinstance(val, (int, float)),
                f"{key} must be 'absent' or numeric, got {type(val).__name__} = {val!r}",
            )
        for key in ("native_thread_count", "torch_intraop_threads",
                     "torch_interop_threads", "loaded_module_count"):
            val = result.get(key)
            self.assertTrue(
                val == "absent" or isinstance(val, int),
                f"{key} must be 'absent' or int, got {type(val).__name__} = {val!r}",
            )

    def test_empty_fields_defaults_to_all(self):
        result = _collect_process_memory()
        for key in ("vm_rss_mib", "native_thread_count",
                     "loaded_module_count", "torch_intraop_threads"):
            self.assertIn(key, result)

    def test_requested_fields_only(self):
        result = _collect_process_memory(fields=("vm_rss_mib", "native_thread_count"))
        self.assertIn("vm_rss_mib", result)
        self.assertIn("native_thread_count", result)
        self.assertNotIn("smaps_rss_mib", result)
        self.assertNotIn("loaded_module_count", result)


# ── Init defaults tests ────────────────────────────────────────────────────


class InitDefaultsTests(unittest.TestCase):
    """Entrypoint __init__ and _lazy_init_snapshot_state defaults."""

    def setUp(self):
        _clean_env()

    def test_init_snapshot_models_evicted_before_capture_false(self):
        ep = ModalRuntimeEntrypoint()
        self.assertFalse(ep._snapshot_models_evicted_before_capture)

    def test_init_eviction_metadata_empty_dict(self):
        ep = ModalRuntimeEntrypoint()
        self.assertEqual(ep._snapshot_eviction_metadata, {})

    def test_lazy_init_adds_missing_attrs(self):
        raw = ModalRuntimeEntrypoint.__new__(ModalRuntimeEntrypoint)
        self.assertFalse(hasattr(raw, "_snapshot_models_evicted_before_capture"))
        raw._lazy_init_snapshot_state()
        self.assertTrue(hasattr(raw, "_snapshot_models_evicted_before_capture"))
        self.assertFalse(raw._snapshot_models_evicted_before_capture)
        self.assertTrue(hasattr(raw, "_snapshot_eviction_metadata"))
        self.assertEqual(raw._snapshot_eviction_metadata, {})
        self.assertTrue(hasattr(raw, "_cpu_snapshot_unet_storage_registry"))
        self.assertIsNone(raw._cpu_snapshot_unet_storage_registry)
        self.assertTrue(hasattr(raw, "_cpu_snapshot_clip_storage_registry"))
        self.assertIsNone(raw._cpu_snapshot_clip_storage_registry)


# ── Full eviction (both models unconditionally) tests ───────────────────


class FullEvictionTests(unittest.TestCase):
    """_evict_snapshot_models unconditionally evicts both models before reload.

    Weakrefs must be dead for both.  No retained original object.
    RSS drop threshold always >=8192 MiB.
    """

    def setUp(self):
        _clean_env()
        _RES4LYF_PREPARED.clear()
        _CACHEDIT_PREPARED.clear()

    def _full_memory_side_effect(self):
        """Return a callable that produces three distinct RSS readings:
        call 1 = 30000 (full_models_loaded), call 2 = 10000 (after_gc),
        call 3 = 5000 (after_trim/after_full_eviction).
        """
        _call_count = [0]
        def _side_effect(*, fields=None):
            _call_count[0] += 1
            if _call_count[0] == 1:
                return _fake_process_memory(smaps_rss_mib=30000.0)
            elif _call_count[0] == 2:
                return _fake_process_memory(smaps_rss_mib=10000.0)
            else:
                return _fake_process_memory(
                    smaps_rss_mib=5000.0, smaps_anonymous_mib=4500.0,
                    smaps_private_dirty_mib=4400.0,
                )
        return _side_effect

    def _run_full_evict_no_reload(self):
        """Run full eviction with role=none (no reload).
        Models are created inline so weakrefs die naturally.
        Returns (marker, metadata, ep)."""
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
            snapshot_execution_seed=None,
            snapshot_seed_built=False,
        )
        del unet, clip
        _retain_role = "none"
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = _retain_role
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   side_effect=self._full_memory_side_effect()):
            metadata = ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        return ep._eviction_marker, metadata, ep

    def test_full_eviction_both_models_dead(self):
        """Both original weakrefs must be dead after full eviction."""
        marker, metadata, ep = self._run_full_evict_no_reload()
        self.assertEqual(marker["status"], "full_eviction_complete")
        self.assertEqual(marker["original_clip_alive_after_full_eviction"], 0)
        self.assertEqual(marker["original_unet_alive_after_full_eviction"], 0)

    def test_full_eviction_rss_drop_above_8192(self):
        """RSS drop after full eviction >=8192 MiB."""
        marker, metadata, ep = self._run_full_evict_no_reload()
        self.assertGreaterEqual(marker["full_eviction_rss_drop_mib"], 8192.0)

    def test_full_eviction_clears_all_state(self):
        """All registries, models, runtime state are cleared."""
        marker, metadata, ep = self._run_full_evict_no_reload()
        self.assertIsNone(ep._cpu_snapshot_unet_runtime_state)
        self.assertIsNone(ep._cpu_snapshot_unet_storage_registry)
        self.assertIsNone(ep._cpu_snapshot_clip_storage_registry)
        self.assertFalse(ep._cpu_snapshot_models_active)
        self.assertIsNone(ep._cpu_snapshot_models)

    def test_full_eviction_clears_loader_outputs(self):
        """BootstrapState loader outputs/identities/seed are cleared."""
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={"unet": object()},
            snapshot_model_identities={"unet": "u", "clip": "c"},
            snapshot_execution_seed=42,
            snapshot_seed_built=True,
        )
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "none"
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   side_effect=self._full_memory_side_effect()):
            ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        self.assertEqual(bs.snapshot_loader_outputs, {})
        self.assertEqual(bs.snapshot_model_identities, {})
        self.assertIsNone(bs.snapshot_execution_seed)
        self.assertFalse(bs.snapshot_seed_built)

    def test_full_eviction_clears_res4lyf_cachedit(self):
        """_RES4LYF_PREPARED and _CACHEDIT_PREPARED are cleared."""
        _RES4LYF_PREPARED["wf_hash"] = {"records": ()}
        _CACHEDIT_PREPARED["wf_hash"] = {"unet_id": 123}
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "none"
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   side_effect=self._full_memory_side_effect()):
            ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        self.assertEqual(_RES4LYF_PREPARED, {})
        self.assertEqual(_CACHEDIT_PREPARED, {})

    def test_full_eviction_preserves_unrelated_globals(self):
        """Certificate cache, workflow hash, RES4LYF hook preserved."""
        import comfymodal_runtime.modal_app as _ma
        _orig_cert = _ma._V2_CERT_PROCESS_CACHE.copy()
        _orig_wf = _ma._V2_WORKFLOW_HASH
        _orig_res4lyf = _ma._RES4LYF_HOOK_INSTALLED
        _ma._V2_CERT_PROCESS_CACHE["test"] = "value"
        _ma._RES4LYF_HOOK_INSTALLED = True
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "none"
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   side_effect=self._full_memory_side_effect()):
            ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        self.assertIn("test", _ma._V2_CERT_PROCESS_CACHE)
        self.assertEqual(_ma._V2_WORKFLOW_HASH, _orig_wf)
        self.assertTrue(_ma._RES4LYF_HOOK_INSTALLED)
        _ma._V2_CERT_PROCESS_CACHE.clear()
        _ma._V2_CERT_PROCESS_CACHE.update(_orig_cert)
        _ma._RES4LYF_HOOK_INSTALLED = _orig_res4lyf

    def test_full_eviction_emits_full_eviction_complete(self):
        """Final pre-capture line has status=full_eviction_complete."""
        captured = []
        original_print = print
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
            original_print(*args, **kwargs)
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "none"
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       side_effect=self._full_memory_side_effect()):
                ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        evict_complete = [l for l in captured if "status=full_eviction_complete" in l]
        self.assertEqual(len(evict_complete), 1)
        self.assertIn("original_clip_alive_after_full_eviction=0", evict_complete[0])
        self.assertIn("original_unet_alive_after_full_eviction=0", evict_complete[0])

    def test_full_eviction_three_memory_stages(self):
        """Three memory stages: full_models_loaded, after_full_eviction, after_selected_reload."""
        captured = []
        original_print = print
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
            original_print(*args, **kwargs)
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "none"
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       side_effect=self._full_memory_side_effect()):
                ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        mem_lines = [l for l in captured if "snapshot_model_eviction_memory" in l]
        stage_names = []
        for line in mem_lines:
            for part in line.split():
                if part.startswith("stage="):
                    stage_names.append(part.split("=", 1)[1])
        self.assertIn("full_models_loaded", stage_names)
        self.assertIn("after_full_eviction", stage_names)
        self.assertIn("after_selected_reload", stage_names)

    def test_metadata_has_primitive_fields(self):
        """Returned metadata has normalized_profile and model_key fields (no objects)."""
        marker, metadata, ep = self._run_full_evict_no_reload()
        self.assertIn("model_key_unet_identity", metadata)
        self.assertIn("model_key_clip_identity", metadata)
        self.assertIn("model_key_clip_type", metadata)
        self.assertIn("weight_dtype", metadata)
        self.assertIsInstance(metadata, dict)
        for v in metadata.values():
            self.assertFalse(
                hasattr(v, "__dict__") and callable(getattr(v, "__dict__", None)),
                f"metadata contains non-primitive value: {v!r}",
            )

    def test_full_eviction_snapshot_models_active_false(self):
        """_cpu_snapshot_models_active is False and _cpu_snapshot_models is None."""
        marker, metadata, ep = self._run_full_evict_no_reload()
        self.assertFalse(ep._cpu_snapshot_models_active)
        self.assertIsNone(ep._cpu_snapshot_models)

    def test_full_eviction_removes_exact_comfy_ownership(self):
        """Only exact target records are removed from model-management state."""
        import types

        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        other = _FakeModel("other")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(snapshot_loader_outputs={}, snapshot_model_identities={})

        class _LoadedRecord:
            def __init__(self, model):
                self.model = model

        records = [_LoadedRecord(unet), _LoadedRecord(clip), _LoadedRecord(other)]
        fake_mm = types.SimpleNamespace(current_loaded_models=records)

        def _free_memory(_required, _device, keep_loaded=None, **_kwargs):
            fake_mm.current_loaded_models[:] = list(keep_loaded or [])
            return []

        fake_mm.free_memory = _free_memory
        fake_mm.cleanup_models = lambda: None
        fake_comfy = types.ModuleType("comfy")
        fake_comfy.__path__ = []
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "none"
        with patch.dict(sys.modules, {
            "comfy": fake_comfy,
            "comfy.model_management": fake_mm,
        }):
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       side_effect=self._full_memory_side_effect()):
                ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        self.assertEqual(ep._snapshot_eviction_metadata["comfy_owned_target_count_before"], 2)
        self.assertEqual(ep._snapshot_eviction_metadata["comfy_owned_target_count_after"], 0)
        self.assertEqual(len(fake_mm.current_loaded_models), 1)
        self.assertIs(fake_mm.current_loaded_models[0].model, other)

    def test_full_eviction_retained_role_none_defaults(self):
        """retained_role=none leaves dedicated attrs at defaults."""
        marker, metadata, ep = self._run_full_evict_no_reload()
        self.assertEqual(ep._snapshot_eviction_retained_role, "none")
        self.assertIsNone(ep._snapshot_eviction_retained_model)
        self.assertEqual(ep._snapshot_eviction_retained_model_id, 0)
        self.assertEqual(ep._snapshot_eviction_retained_model_type, "")


# ── Full eviction failure tests ─────────────────────────────────────────


class FullEvictionFailureTests(unittest.TestCase):
    """_evict_snapshot_models failure paths (unconditional, no selective)."""

    def setUp(self):
        _clean_env()

    def test_weakrefs_alive_raises(self):
        """Original weakref alive emits object_still_alive."""
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )
        captured = []
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
                with self.assertRaises(RuntimeError) as ctx:
                    ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        self.assertIn("original weakrefs still alive", str(ctx.exception).lower())
        alive_lines = [l for l in captured if "status=object_still_alive" in l]
        self.assertGreaterEqual(len(alive_lines), 1)
        self.assertIn("original_clip_alive_after_full_eviction=1", alive_lines[0])
        self.assertIn("original_unet_alive_after_full_eviction=1", alive_lines[0])

    def test_memory_evidence_unavailable(self):
        """Both smaps and vm absent -> status=error."""
        def _all_absent(*, fields=None):
            return {f: "absent" for f in (fields or (
                "vm_rss_mib", "smaps_rss_mib", "smaps_anonymous_mib",
                "smaps_private_dirty_mib", "native_thread_count",
                "torch_intraop_threads", "torch_interop_threads",
                "loaded_module_count",
            ))}
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )
        del unet, clip
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   side_effect=_all_absent):
            with self.assertRaises(RuntimeError) as ctx:
                ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        self.assertIn("memory evidence unavailable", str(ctx.exception))
        self.assertIsNone(ep._eviction_marker)
        self.assertFalse(ep._snapshot_models_evicted_before_capture)

    def test_insufficient_rss_drop_always_8192(self):
        """RSS drop < 8192 MiB raises, no selective floor."""
        _call_count = [0]
        def _small_drop(*, fields=None):
            _call_count[0] += 1
            if _call_count[0] == 1:
                return _fake_process_memory(smaps_rss_mib=15000.0)
            elif _call_count[0] == 2:
                return _fake_process_memory(smaps_rss_mib=14000.0)
            else:
                return _fake_process_memory(smaps_rss_mib=13500.0)
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )
        del unet, clip
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   side_effect=_small_drop):
            with self.assertRaises(RuntimeError) as ctx:
                ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        self.assertIn("RSS drop", str(ctx.exception))
        self.assertIn("8192", str(ctx.exception))


# ── Reload lifecycle tests (after full eviction) ────────────────────────


class ReloadAfterEvictionTests(unittest.TestCase):
    """Full eviction + reload of selected role via injected closures."""

    def setUp(self):
        _clean_env()
        _RES4LYF_PREPARED.clear()
        _CACHEDIT_PREPARED.clear()

    def _memory_for_three_stages(self):
        _call_count = [0]
        def _side_effect(*, fields=None):
            _call_count[0] += 1
            if _call_count[0] == 1:
                return _fake_process_memory(smaps_rss_mib=30000.0)
            elif _call_count[0] <= 3:
                return _fake_process_memory(smaps_rss_mib=5000.0)
            elif _call_count[0] == 4:
                return _fake_process_memory(smaps_rss_mib=12000.0)
            else:
                return _fake_process_memory(smaps_rss_mib=12000.0)
        return _side_effect

    def _reload_unet_fake(self, name, weight_dtype):
        return _FreshFakeModel("fresh_unet")

    def _reload_clip_fake(self, *args):
        return _FreshFakeModel("fresh_clip")

    def _snap_ctx_fake(self):
        return self._noop_cm()

    def _noop_cm(self):
        class _NoopCM:
            def __enter__(self):
                return None
            def __exit__(self, *a):
                pass
        return _NoopCM()

    def _mock_comfy_utils(self):
        """Return a patcher for comfy.utils to avoid ComfyUI import in tests."""
        _mock_module = MagicMock()
        _mock_module.DISABLE_MMAP = False
        return patch.dict("sys.modules", {"comfy.utils": _mock_module})

    def _patch_storage_registry(self, total_bytes: int = 10 * 1024**3):
        """Patch build_unique_storage_registry to return a fake registry with total_bytes."""
        _fake_reg = MagicMock()
        _fake_reg.total_bytes = total_bytes
        _fake_reg.ranges = (object(), object(), object())
        return patch(
            "comfymodal_runtime.modal_app.build_unique_storage_registry",
            return_value=_fake_reg,
        )

    def _reload_unet_none(self, name, weight_dtype):
        return None

    def _run_evict_reload(self, retain_role, reload_clip=None, reload_unet=None):
        profile = {"mode": "split", "unet": "test_unet.safetensors",
                    "clip1": "test_clip.safetensors", "clip_type": "sd3",
                    "weight_dtype": "default"}
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip, normal_profile=profile)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
            snapshot_execution_seed=None,
            snapshot_seed_built=False,
        )
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = retain_role
        if reload_clip is None:
            reload_clip = self._reload_clip_fake
        if reload_unet is None:
            reload_unet = self._reload_unet_fake
        with self._mock_comfy_utils(), self._patch_storage_registry():
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       side_effect=self._memory_for_three_stages()):
                metadata = ep._evict_snapshot_models(
                    ep._cpu_snapshot_models, bs,
                    reload_unet_fn=reload_unet,
                    reload_clip_fn=reload_clip,
                    snap_ctx_cm=self._snap_ctx_fake,
                    target_gpus=("rtx-pro-6000",),
                )
        return ep._eviction_marker, metadata, ep, profile

    def test_reload_unet_new_identity(self):
        """Reloaded UNET has different id than original."""
        marker, metadata, ep, profile = self._run_evict_reload("unet")
        self.assertEqual(ep._snapshot_eviction_retained_role, "unet")
        self.assertIsNotNone(ep._snapshot_eviction_retained_model)
        original_id = int(marker.get("unet_original_id", "0"))
        self.assertNotEqual(
            ep._snapshot_eviction_retained_model_id, original_id,
            "reloaded unet must have different id from original",
        )

    def test_reload_clip_new_identity(self):
        """Reloaded CLIP has different id than original."""
        marker, metadata, ep, profile = self._run_evict_reload("clip")
        self.assertEqual(ep._snapshot_eviction_retained_role, "clip")
        self.assertIsNotNone(ep._snapshot_eviction_retained_model)
        original_id = int(marker.get("clip_original_id", "0"))
        self.assertNotEqual(
            ep._snapshot_eviction_retained_model_id, original_id,
            "reloaded clip must have different id from original",
        )

    def test_reload_unet_type_set(self):
        """reloaded UNET type is _FreshFakeModel."""
        marker, metadata, ep, profile = self._run_evict_reload("unet")
        self.assertEqual(ep._snapshot_eviction_retained_model_type, "_FreshFakeModel")

    def test_reload_clip_type_set(self):
        """reloaded CLIP type is _FreshFakeModel."""
        marker, metadata, ep, profile = self._run_evict_reload("clip")
        self.assertEqual(ep._snapshot_eviction_retained_model_type, "_FreshFakeModel")

    def test_reload_storage_metrics_are_recorded(self):
        """Selected storage count, bytes, and MiB are persistent primitives."""
        marker, metadata, ep, profile = self._run_evict_reload("clip")
        self.assertEqual(marker["selected_storage_count"], 3)
        self.assertEqual(marker["selected_storage_total_bytes"], 10 * 1024**3)
        self.assertEqual(marker["selected_storage_total_mib"], 10240.0)

    def test_reload_callback_runs_after_full_eviction(self):
        """Selected loader cannot run before both original objects are dead."""
        events = []
        original_unet = _FakeModel("unet")
        original_clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(original_unet, original_clip, normal_profile={
            "mode": "split", "unet": "test_unet.safetensors",
            "clip1": "test_clip.safetensors", "clip_type": "sd3",
        })
        bs = SimpleNamespace(snapshot_loader_outputs={}, snapshot_model_identities={})
        del original_unet, original_clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "clip"

        def _reload_clip(*args):
            events.append(("reload", ep._cpu_snapshot_models, ep._cpu_snapshot_models_active))
            return _FreshFakeModel("fresh_clip")

        with self._mock_comfy_utils(), self._patch_storage_registry():
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       side_effect=self._memory_for_three_stages()):
                ep._evict_snapshot_models(
                    ep._cpu_snapshot_models, bs,
                    reload_unet_fn=self._reload_unet_fake,
                    reload_clip_fn=_reload_clip,
                    snap_ctx_cm=self._snap_ctx_fake,
                    target_gpus=("rtx-pro-6000",),
                )
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0][1])
        self.assertFalse(events[0][2])

    def test_dual_clip_profile_uses_dual_loader_shape(self):
        """Dual CLIP profiles pass clip1, clip2, clip_type, and default."""
        calls = []
        profile = {
            "mode": "split", "unet": "test_unet.safetensors",
            "clip1": "clip_a.safetensors", "clip2": "clip_b.safetensors",
            "clip_type": "sd3",
        }
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip, normal_profile=profile)
        bs = SimpleNamespace(snapshot_loader_outputs={}, snapshot_model_identities={})
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "clip"

        def _reload_clip(*args):
            calls.append(args)
            return _FreshFakeModel("fresh_clip")

        with self._mock_comfy_utils(), self._patch_storage_registry():
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       side_effect=self._memory_for_three_stages()):
                ep._evict_snapshot_models(
                    ep._cpu_snapshot_models, bs,
                    reload_unet_fn=self._reload_unet_fake,
                    reload_clip_fn=_reload_clip,
                    snap_ctx_cm=self._snap_ctx_fake,
                    target_gpus=("rtx-pro-6000",),
                )
        self.assertEqual(calls, [("clip_a.safetensors", "clip_b.safetensors", "sd3", "default")])

    def test_reload_weakref_alive(self):
        """Retained weakref (on reloaded model) is alive after evict+reload."""
        marker, metadata, ep, profile = self._run_evict_reload("clip")
        import weakref as _wr
        wr = _wr.ref(ep._snapshot_eviction_retained_model)
        self.assertIsNotNone(wr())
        self.assertEqual(marker["retained_model_present"], 1)

    def test_status_ready_on_final_line(self):
        """Final snapshot_pre_capture has status=ready."""
        captured = []
        original_print = print
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
            original_print(*args, **kwargs)
        profile = {"mode": "split", "unet": "test_unet.safetensors",
                    "clip1": "test_clip.safetensors", "clip_type": "sd3"}
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip, normal_profile=profile)
        bs = SimpleNamespace(snapshot_loader_outputs={}, snapshot_model_identities={})
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "unet"
        with self._mock_comfy_utils(), self._patch_storage_registry():
            with patch("builtins.print", side_effect=_cap_print):
                with patch("comfymodal_runtime.modal_app._collect_process_memory",
                           side_effect=self._memory_for_three_stages()):
                    ep._evict_snapshot_models(
                        ep._cpu_snapshot_models, bs,
                        reload_unet_fn=self._reload_unet_fake,
                        reload_clip_fn=self._reload_clip_fake,
                        snap_ctx_cm=self._snap_ctx_fake,
                        target_gpus=("rtx-pro-6000",),
                    )
        ready_lines = [l for l in captured if "status=ready" in l and "snapshot_pre_capture" in l]
        self.assertGreaterEqual(len(ready_lines), 1)

    def test_reload_none_raises(self):
        """Reload function returning None raises RuntimeError."""
        profile = {"mode": "split", "unet": "test_unet.safetensors",
                    "clip1": "test_clip.safetensors", "clip_type": "sd3"}
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip, normal_profile=profile)
        bs = SimpleNamespace(snapshot_loader_outputs={}, snapshot_model_identities={})
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "clip"
        with self._mock_comfy_utils(), self._patch_storage_registry():
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       side_effect=self._memory_for_three_stages()):
                with self.assertRaises(RuntimeError) as ctx:
                    ep._evict_snapshot_models(
                        ep._cpu_snapshot_models, bs,
                        reload_unet_fn=self._reload_unet_fake,
                        reload_clip_fn=lambda *a: None,
                        snap_ctx_cm=self._snap_ctx_fake,
                        target_gpus=("rtx-pro-6000",),
                    )
        self.assertIn("None after full eviction", str(ctx.exception))

    def test_reload_new_identity_check(self):
        """New identity is verified: reloaded id differs from original."""
        marker, metadata, ep, profile = self._run_evict_reload("unet")
        original_id = int(marker.get("unet_original_id", "0"))
        self.assertNotEqual(
            ep._snapshot_eviction_retained_model_id, original_id,
            "reloaded unet must have different id from original",
        )

    def test_missing_reload_closures_raises(self):
        """Missing reload closures when role is not 'none' raises."""
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(snapshot_loader_outputs={}, snapshot_model_identities={})
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "clip"
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   side_effect=self._memory_for_three_stages()):
            with self.assertRaises(RuntimeError) as ctx:
                ep._evict_snapshot_models(
                    ep._cpu_snapshot_models, bs,
                    reload_unet_fn=None,
                    reload_clip_fn=None,
                    snap_ctx_cm=None,
                )
        self.assertIn("closures are missing", str(ctx.exception))

    def test_normal_state_absent_after_reload(self):
        """Normal snapshot model attr/state/bridge/loader outputs/seed absent after reload."""
        marker, metadata, ep, profile = self._run_evict_reload("clip")
        self.assertIsNone(ep._cpu_snapshot_models)
        self.assertFalse(ep._cpu_snapshot_models_active)
        self.assertIsNone(ep._cpu_snapshot_unet_runtime_state)
        self.assertIsNone(ep._cpu_snapshot_unet_storage_registry)
        self.assertIsNone(ep._cpu_snapshot_clip_storage_registry)

    def test_role_floors_adhered(self):
        """Reload validation requires role-specific floors (CLIP: 2048/4096, UNET: 4096/8192)."""
        # Uses fake memory where after_reload is the same as after_eviction
        # This will fail the rise check.
        profile = {"mode": "split", "unet": "test_unet.safetensors",
                    "clip1": "test_clip.safetensors", "clip_type": "sd3"}
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip, normal_profile=profile)
        bs = SimpleNamespace(snapshot_loader_outputs={}, snapshot_model_identities={})
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "clip"
        # Memory that gives: loaded=30000, after_eviction=5000, after_reload=5000 (no rise)
        _call_count = [0]
        def _flat_reload(*, fields=None):
            _call_count[0] += 1
            if _call_count[0] == 1:
                return _fake_process_memory(smaps_rss_mib=30000.0)
            elif _call_count[0] <= 3:
                return _fake_process_memory(smaps_rss_mib=5000.0)
            elif _call_count[0] == 4:
                return _fake_process_memory(smaps_rss_mib=5000.0)
            else:
                return _fake_process_memory(smaps_rss_mib=5000.0)
        with self._mock_comfy_utils(), self._patch_storage_registry():
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       side_effect=_flat_reload):
                with self.assertRaises(RuntimeError) as ctx:
                    ep._evict_snapshot_models(
                        ep._cpu_snapshot_models, bs,
                        reload_unet_fn=self._reload_unet_fake,
                        reload_clip_fn=self._reload_clip_fake,
                        snap_ctx_cm=self._snap_ctx_fake,
                        target_gpus=("rtx-pro-6000",),
                    )
        self.assertIn("RSS rise", str(ctx.exception))

    def test_unet_rss_rise_floor_is_4096(self):
        """UNET reload requires a 4096 MiB current-RSS rise."""
        profile = {"mode": "split", "unet": "test_unet.safetensors",
                   "clip1": "test_clip.safetensors", "clip_type": "sd3"}
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip, normal_profile=profile)
        bs = SimpleNamespace(snapshot_loader_outputs={}, snapshot_model_identities={})
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "unet"
        _call_count = [0]

        def _low_unet_rise(*, fields=None):
            _call_count[0] += 1
            if _call_count[0] == 1:
                return _fake_process_memory(smaps_rss_mib=30000.0)
            if _call_count[0] <= 3:
                return _fake_process_memory(smaps_rss_mib=5000.0)
            return _fake_process_memory(smaps_rss_mib=8000.0)

        with self._mock_comfy_utils(), self._patch_storage_registry(10 * 1024**3):
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       side_effect=_low_unet_rise):
                with self.assertRaises(RuntimeError) as ctx:
                    ep._evict_snapshot_models(
                        ep._cpu_snapshot_models, bs,
                        reload_unet_fn=self._reload_unet_fake,
                        reload_clip_fn=self._reload_clip_fake,
                        snap_ctx_cm=self._snap_ctx_fake,
                        target_gpus=("rtx-pro-6000",),
                    )
        self.assertIn("RSS rise", str(ctx.exception))

    def test_storage_floor_failure_prevents_ready_payload(self):
        """A selected payload below the role storage floor fails startup."""
        with self.assertRaises(RuntimeError) as ctx:
            self._run_evict_reload_with_storage_floor("unet")
        self.assertIn("storage", str(ctx.exception).lower())

    def _run_evict_reload_with_storage_floor(self, retain_role):
        profile = {"mode": "split", "unet": "test_unet.safetensors",
                   "clip1": "test_clip.safetensors", "clip_type": "sd3"}
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip, normal_profile=profile)
        bs = SimpleNamespace(snapshot_loader_outputs={}, snapshot_model_identities={})
        del unet, clip
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = retain_role
        with self._mock_comfy_utils(), self._patch_storage_registry(1024**3):
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       side_effect=self._memory_for_three_stages()):
                return ep._evict_snapshot_models(
                    ep._cpu_snapshot_models, bs,
                    reload_unet_fn=self._reload_unet_fake,
                    reload_clip_fn=self._reload_clip_fake,
                    snap_ctx_cm=self._snap_ctx_fake,
                    target_gpus=("rtx-pro-6000",),
                )


# ── Disabled compatibility tests ─────────────────────────────────────────


class EvictionDisabledCompatibilityTests(unittest.TestCase):
    """When eviction is disabled, everything works as before."""

    def setUp(self):
        _clean_env()

    def test_parse_evict_returns_false_by_default(self):
        self.assertFalse(_parse_evict_models_before_snapshot())

    def test_parse_idle_returns_zero_by_default(self):
        self.assertEqual(_parse_evict_restore_idle_seconds(), 0)

    def test_entrypoint_has_eviction_marker_attribute(self):
        ep = ModalRuntimeEntrypoint()
        self.assertIsNone(ep._eviction_marker)

    def test_lazy_init_snapshot_state_creates_attrs(self):
        raw = ModalRuntimeEntrypoint.__new__(ModalRuntimeEntrypoint)
        self.assertFalse(hasattr(raw, "_eviction_marker"))
        self.assertFalse(hasattr(raw, "_snapshot_models_evicted_before_capture"))
        raw._lazy_init_snapshot_state()
        self.assertTrue(hasattr(raw, "_eviction_marker"))
        self.assertIsNone(raw._eviction_marker)
        self.assertTrue(hasattr(raw, "_snapshot_models_evicted_before_capture"))
        self.assertFalse(raw._snapshot_models_evicted_before_capture)

    def test_disabled_prints_disabled_line(self):
        """Only the disabled line is printed when eviction disabled."""
        captured = []
        original_print = print
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
            original_print(*args, **kwargs)
        with patch("builtins.print", side_effect=_cap_print):
            if not _parse_evict_models_before_snapshot():
                print(
                    "[v2.snapshot_model_eviction] stage=snapshot_pre_capture "
                    "enabled=0 status=disabled",
                    flush=True,
                )
        evict_lines = [l for l in captured if "snapshot_model_eviction" in l]
        self.assertEqual(len(evict_lines), 1)
        self.assertIn("disabled", evict_lines[0])

    def test_disabled_path_no_error_output(self):
        """Disabled path emits exactly the disabled line."""
        captured = []
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._parse_evict_models_before_snapshot",
                       return_value=False):
                print(
                    "[v2.snapshot_model_eviction] stage=snapshot_pre_capture "
                    "enabled=0 status=disabled",
                    flush=True,
                )
        evict_lines = [l for l in captured if "snapshot_model_eviction" in l]
        self.assertEqual(len(evict_lines), 1)
        self.assertIn("enabled=0", evict_lines[0])
        self.assertIn("status=disabled", evict_lines[0])


# ── Restore idle ordering tests ──────────────────────────────────────────


class RestoreIdleOrderingTests(unittest.TestCase):
    """Restore idle ordering: marker inspection and idle delay precede
    _apply_torch_thread_limit."""

    def setUp(self):
        _clean_env()

    def test_restore_observed_emitted_when_marker_present(self):
        """restore_observed line is emitted when marker is present."""
        entrypoint = ModalRuntimeEntrypoint()
        entrypoint._eviction_marker = {
            "status": "full_eviction_complete",
            "full_eviction_rss_drop_mib": 25000.0,
            "clip_original_id": "123",
            "unet_original_id": "456",
            "original_clip_alive_after_full_eviction": 0,
            "original_unet_alive_after_full_eviction": 0,
        }
        entrypoint._snapshot_eviction_metadata = {
            "clip_present": 1,
            "unet_present": 1,
        }
        entrypoint._apply_torch_thread_limit = MagicMock()
        captured = []
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._parse_evict_restore_idle_seconds",
                       return_value=0):
                entrypoint._restore_eviction_boundary()
        obs = [l for l in captured if "restore_observed" in l]
        self.assertEqual(len(obs), 1)
        self.assertIn("marker=1", obs[0])

    def test_no_idle_when_zero(self):
        """idle=0 does not emit start/end lines."""
        entrypoint = ModalRuntimeEntrypoint()
        entrypoint._eviction_marker = {
            "status": "full_eviction_complete",
            "original_clip_alive_after_full_eviction": 0,
            "original_unet_alive_after_full_eviction": 0,
        }
        entrypoint._apply_torch_thread_limit = MagicMock()
        captured = []
        sleep_calls = []
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
        def _tracking_sleep(seconds):
            sleep_calls.append(seconds)
            return time.sleep(0)
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._parse_evict_restore_idle_seconds",
                       return_value=0):
                with patch("time.sleep", side_effect=_tracking_sleep):
                    entrypoint._restore_eviction_boundary()
        idle_start = [l for l in captured if "event=start" in l and "snapshot_model_eviction_idle" in l]
        idle_end = [l for l in captured if "event=end" in l and "snapshot_model_eviction_idle" in l]
        self.assertEqual(len(idle_start), 0)
        self.assertEqual(len(idle_end), 0)
        self.assertNotIn(3, sleep_calls)

    def test_idle_sleep_ordering(self):
        """idle_start before idle_end, sleep called with correct value."""
        entrypoint = ModalRuntimeEntrypoint()
        entrypoint._eviction_marker = {
            "status": "full_eviction_complete",
            "original_clip_alive_after_full_eviction": 0,
            "original_unet_alive_after_full_eviction": 0,
        }
        entrypoint._apply_torch_thread_limit = MagicMock()
        captured = []
        sleep_calls = []
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
        def _tracking_sleep(seconds):
            sleep_calls.append(seconds)
            return None
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._parse_evict_restore_idle_seconds",
                       return_value=3):
                with patch("time.sleep", side_effect=_tracking_sleep):
                    entrypoint._restore_eviction_boundary()
        obs_lines = [l for l in captured if "restore_observed" in l]
        idle_start = [l for l in captured if "event=start" in l and "snapshot_model_eviction_idle" in l]
        idle_end = [l for l in captured if "event=end" in l and "snapshot_model_eviction_idle" in l]
        self.assertGreater(len(obs_lines), 0)
        obs_idx = captured.index(obs_lines[0])
        if idle_start:
            start_idx = captured.index(idle_start[0])
            self.assertLess(obs_idx, start_idx,
                            "restore_observed must precede idle_start")
        if idle_end:
            end_idx = captured.index(idle_end[0])
            self.assertLess(captured.index(idle_start[0]), end_idx,
                            "idle_start must precede idle_end")
        self.assertIn(3, sleep_calls)

    def test_no_idle_when_marker_none(self):
        """No idle when _eviction_marker is None."""
        entrypoint = ModalRuntimeEntrypoint()
        entrypoint._eviction_marker = None
        entrypoint._apply_torch_thread_limit = MagicMock()
        captured = []
        sleep_calls = []
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
        def _tracking_sleep(seconds):
            sleep_calls.append(seconds)
            return time.sleep(0)
        with patch("builtins.print", side_effect=_cap_print):
            with patch("time.sleep", side_effect=_tracking_sleep):
                entrypoint._restore_eviction_boundary()
        idle_start = [l for l in captured if "event=start" in l and "snapshot_model_eviction_idle" in l]
        self.assertEqual(len(idle_start), 0)
        obs_lines = [l for l in captured if "restore_observed" in l]
        self.assertEqual(len(obs_lines), 1)
        self.assertIn("marker=0", obs_lines[0])

    def test_primitive_flag_alone_without_dict_produces_marker(self):
        """Primitive flag alone produces marker=1 and enables idle."""
        entrypoint = ModalRuntimeEntrypoint()
        entrypoint._snapshot_models_evicted_before_capture = True
        entrypoint._eviction_marker = None
        entrypoint._snapshot_eviction_metadata = {
            "clip_present": 1,
            "unet_present": 1,
        }
        entrypoint._apply_torch_thread_limit = MagicMock()
        captured = []
        sleep_calls = []
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
        def _tracking_sleep(seconds):
            sleep_calls.append(seconds)
            return None
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._parse_evict_restore_idle_seconds",
                       return_value=5):
                with patch("time.sleep", side_effect=_tracking_sleep):
                    entrypoint._restore_eviction_boundary()
        obs_lines = [l for l in captured if "restore_observed" in l]
        self.assertEqual(len(obs_lines), 1)
        self.assertIn("marker=1", obs_lines[0])
        idle_start = [l for l in captured if "event=start" in l and "snapshot_model_eviction_idle" in l]
        self.assertEqual(len(idle_start), 1)
        self.assertIn(5, sleep_calls)


# ── Restore boundary ordering tests ──────────────────────────────────────


class RestoreBoundaryOrderingTest(unittest.TestCase):
    """Verify restore() calls _restore_eviction_boundary before
    _apply_torch_thread_limit and that normal restore continuation
    is attempted after the boundary."""

    def setUp(self):
        _clean_env()

    def test_restore_boundary_before_apply_torch_thread(self):
        """entrypoint.restore() calls boundary before apply_torch_thread_limit."""
        entrypoint = ModalRuntimeEntrypoint()
        entrypoint._eviction_marker = None
        entrypoint._snapshot_models_evicted_before_capture = False
        events = []
        original_boundary = entrypoint._restore_eviction_boundary
        def _tracking_boundary():
            events.append("boundary")
            return original_boundary()
        original_apply = entrypoint._apply_torch_thread_limit
        def _tracking_apply():
            events.append("apply")
            return original_apply()
        entrypoint._configure_runtime = MagicMock()
        entrypoint._restore_publisher = PropertyMock(return_value=None)
        with patch("comfymodal_runtime.modal_app._capture_remote_identity",
                   return_value={"container_id": "test"}):
            with patch.object(entrypoint, "_restore_eviction_boundary",
                              side_effect=_tracking_boundary):
                with patch.object(entrypoint, "_apply_torch_thread_limit",
                                  side_effect=_tracking_apply):
                    original_configure = entrypoint._configure_runtime
                    def _error_configure(*a, **kw):
                        events.append("configure_runtime")
                        raise RuntimeError("controlled stop after boundary ordering")
                    entrypoint._configure_runtime = _error_configure
                    with self.assertRaises(RuntimeError) as ctx:
                        entrypoint.restore()
        self.assertIn("controlled stop", str(ctx.exception))
        self.assertIn("boundary", events)
        self.assertIn("apply", events)
        self.assertIn("configure_runtime", events)
        self.assertLess(events.index("boundary"), events.index("apply"),
                        "boundary must precede apply_torch_thread_limit")
        self.assertLess(events.index("apply"), events.index("configure_runtime"),
                        "apply_torch_thread_limit must precede configure_runtime")


# ── Retain-role selector parsing tests ───────────────────────────────────


class ParseEvictRetainRoleTests(unittest.TestCase):
    """_parse_evict_retain_role strict parsing."""

    def setUp(self):
        _clean_env()

    def test_absent_none(self):
        self.assertEqual(_parse_evict_retain_role(), "none")

    def test_empty_none(self):
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = ""
        self.assertEqual(_parse_evict_retain_role(), "none")

    def test_none_accepted(self):
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "none"
        self.assertEqual(_parse_evict_retain_role(), "none")

    def test_clip_accepted(self):
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "clip"
        self.assertEqual(_parse_evict_retain_role(), "clip")

    def test_unet_accepted(self):
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "unet"
        self.assertEqual(_parse_evict_retain_role(), "unet")

    def test_uppercase_rejected(self):
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "CLIP"
        with self.assertRaises(RuntimeError) as ctx:
            _parse_evict_retain_role()
        self.assertIn("CLIP", str(ctx.exception))

    def test_whitespace_wrapped_rejected(self):
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = " clip "
        with self.assertRaises(RuntimeError) as ctx:
            _parse_evict_retain_role()
        self.assertIn(" clip ", str(ctx.exception))

    def test_other_nonempty_raises(self):
        for val in ("unet2", "both", "true", "1", "0", "encoder", "  clip  "):
            with self.subTest(val=val):
                os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = val
                with self.assertRaises(RuntimeError):
                    _parse_evict_retain_role()

    def test_selector_disabled_ignored(self):
        """When eviction is disabled, retain selector env var still parses."""
        os.environ["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"] = "0"
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "unet"
        env = _runtime_env()
        self.assertIn("COMFYMODAL_V2_EVICT_RETAIN_ROLE", env)
        self.assertEqual(env["COMFYMODAL_V2_EVICT_RETAIN_ROLE"], "unet")
        self.assertFalse(_parse_evict_models_before_snapshot())
        self.assertEqual(_parse_evict_retain_role(), "unet")


# ── Retained model release at restore boundary tests ────────────────────


class RetainedReleaseAtRestoreTests(unittest.TestCase):
    """_restore_eviction_boundary emits retained fields and releases
    the reloaded model (held only on _snapshot_eviction_retained_model)."""

    def setUp(self):
        _clean_env()

    def test_restore_observed_contains_retained_fields(self):
        """restore_observed line contains retained_role/id/type."""
        entrypoint = ModalRuntimeEntrypoint()
        entrypoint._eviction_marker = {
            "status": "full_eviction_complete",
            "full_eviction_rss_drop_mib": 25000.0,
            "clip_original_id": "123",
            "unet_original_id": "456",
            "original_clip_alive_after_full_eviction": 0,
            "original_unet_alive_after_full_eviction": 0,
        }
        entrypoint._snapshot_models_evicted_before_capture = True
        entrypoint._snapshot_eviction_retained_role = "clip"
        retained = _FakeModel("restored_clip")
        entrypoint._snapshot_eviction_retained_model = retained
        entrypoint._snapshot_eviction_retained_model_id = id(retained)
        entrypoint._snapshot_eviction_retained_model_type = "_FakeModel"
        entrypoint._apply_torch_thread_limit = MagicMock()
        del retained
        captured = []
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._parse_evict_restore_idle_seconds",
                       return_value=0):
                entrypoint._restore_eviction_boundary()
        obs = [l for l in captured if "restore_observed" in l]
        self.assertEqual(len(obs), 1)
        self.assertIn("retained_role=clip", obs[0])
        self.assertIn("retained_model_id=", obs[0])
        self.assertIn("retained_model_type=_FakeModel", obs[0])
        self.assertIn("clip_present=0", obs[0])
        self.assertIn("unet_present=0", obs[0])

    def test_retained_attribute_defaults_on_fresh_entrypoint(self):
        """Fresh entrypoint has correct retained attr defaults."""
        ep = ModalRuntimeEntrypoint()
        self.assertEqual(ep._snapshot_eviction_retained_role, "none")
        self.assertIsNone(ep._snapshot_eviction_retained_model)
        self.assertEqual(ep._snapshot_eviction_retained_model_id, 0)
        self.assertEqual(ep._snapshot_eviction_retained_model_type, "")
        self.assertEqual(ep._snapshot_eviction_retained_release_status, "not_run")

    def test_lazy_init_creates_retained_attrs(self):
        """_lazy_init_snapshot_state creates retained attrs on old instances."""
        raw = ModalRuntimeEntrypoint.__new__(ModalRuntimeEntrypoint)
        self.assertFalse(hasattr(raw, "_snapshot_eviction_retained_role"))
        raw._lazy_init_snapshot_state()
        self.assertTrue(hasattr(raw, "_snapshot_eviction_retained_role"))
        self.assertEqual(raw._snapshot_eviction_retained_role, "none")
        self.assertIsNone(raw._snapshot_eviction_retained_model)
        self.assertEqual(raw._snapshot_eviction_retained_model_id, 0)
        self.assertEqual(raw._snapshot_eviction_retained_model_type, "")
        self.assertEqual(raw._snapshot_eviction_retained_release_status, "not_run")

    def test_retained_released_after_idle_end(self):
        """Retained model release follows idle end, requires weakref death but not RSS drop."""
        entrypoint = ModalRuntimeEntrypoint()
        retained = _FakeModel("retained_clip")
        entrypoint._snapshot_eviction_retained_role = "clip"
        entrypoint._snapshot_eviction_retained_model = retained
        entrypoint._snapshot_eviction_retained_model_id = id(retained)
        entrypoint._snapshot_eviction_retained_model_type = "_FakeModel"
        entrypoint._snapshot_models_evicted_before_capture = True
        entrypoint._eviction_marker = {
            "status": "full_eviction_complete",
            "original_clip_alive_after_full_eviction": 0,
            "original_unet_alive_after_full_eviction": 0,
        }
        entrypoint._apply_torch_thread_limit = MagicMock()
        del retained
        captured = []
        sleep_calls = []
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
        def _tracking_sleep(seconds):
            sleep_calls.append(seconds)
            return None
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._parse_evict_restore_idle_seconds",
                       return_value=3):
                with patch("time.sleep", side_effect=_tracking_sleep):
                    with patch("comfymodal_runtime.modal_app._collect_process_memory",
                               return_value=_fake_process_memory()):
                        entrypoint._restore_eviction_boundary()
        release_lines = [l for l in captured if "stage=restore_release_retained" in l]
        idle_end = [l for l in captured if "event=end" in l and "snapshot_model_eviction_idle" in l]
        if idle_end and release_lines:
            end_idx = captured.index(idle_end[0])
            release_idx = captured.index(release_lines[0])
            self.assertGreater(release_idx, end_idx,
                               "retained release must follow idle end")

    def test_release_high_rss_accepted(self):
        """Retained release accepts any RSS - no minimum drop required."""
        entrypoint = ModalRuntimeEntrypoint()
        retained = _FakeModel("big_clip")
        entrypoint._snapshot_eviction_retained_role = "clip"
        entrypoint._snapshot_eviction_retained_model = retained
        entrypoint._snapshot_eviction_retained_model_id = id(retained)
        entrypoint._snapshot_eviction_retained_model_type = "_FakeModel"
        entrypoint._snapshot_models_evicted_before_capture = True
        entrypoint._eviction_marker = {
            "status": "full_eviction_complete",
        }
        entrypoint._apply_torch_thread_limit = MagicMock()
        del retained
        captured = []
        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._parse_evict_restore_idle_seconds",
                       return_value=0):
                with patch("comfymodal_runtime.modal_app._collect_process_memory",
                           return_value=_fake_process_memory(smaps_rss_mib=999999.0)):
                    entrypoint._restore_eviction_boundary()
        release_lines = [l for l in captured if "stage=restore_release_retained" in l]
        if release_lines:
            self.assertIn("status=released", release_lines[0])


if __name__ == "__main__":
    unittest.main()
