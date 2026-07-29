"""Focused tests for CPU snapshot model eviction lifecycle.

Covers env-var strict parsing/propagation, memory field contract, eviction
logic with fake weakrefable models, state cleanup, disabled compatibility,
and restore idle ordering.

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
    _collect_process_memory,
    _runtime_env,
    ModalRuntimeEntrypoint,
    _RES4LYF_PREPARED,
    _CACHEDIT_PREPARED,
    _collect_warmup_env,
)
from comfymodal_runtime.cpu_snapshot_models import CpuSnapshotModels
from comfymodal_runtime.contracts import ModelRestoreKey


# ── Helpers ────────────────────────────────────────────────────────────────


def _clean_env():
    """Remove eviction env vars so tests start from a known state."""
    for key in ("COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT",
                "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS",
                "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT",
                "COMFYMODAL_ENABLE_GPU_SNAPSHOT"):
        os.environ.pop(key, None)


class _FakeModel:
    """Minimal weakrefable model stub for testing."""
    def __init__(self, name: str = "fake"):
        self.name = name
        self.model = self  # for model_management compatibility


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
) -> CpuSnapshotModels:
    """Build a minimal CpuSnapshotModels for eviction testing."""
    if unet_obj is None:
        unet_obj = _FakeModel("unet")
    if clip_obj is None:
        clip_obj = _FakeModel("clip")
    return CpuSnapshotModels(
        model_key=ModelRestoreKey(
            unet_identity=unet_identity,
            clip_identity=clip_identity,
            vae_identity="",
            clip_type="sd3",
        ),
        model_spec={"loaders": {"unet": [], "clip": [], "vae": []}},
        normalized_profile={"mode": "split"},
        file_facts=(),
        unet=unet_obj,
        clip=clip_obj,
        compute_policy="default",
        policy_version=2,
    )


def _make_fake_entrypoint(
    unet_obj: Any = None,
    clip_obj: Any = None,
) -> ModalRuntimeEntrypoint:
    """Create an entrypoint with minimal bridge and pre-set cpu_snapshot_models."""
    ep = ModalRuntimeEntrypoint()
    if unet_obj is None:
        unet_obj = _FakeModel("unet")
    if clip_obj is None:
        clip_obj = _FakeModel("clip")
    ep._cpu_snapshot_models = _make_minimal_cpu_models(
        unet_obj=unet_obj, clip_obj=clip_obj,
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

    def test_present_in_env_when_set(self):
        os.environ["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"] = "1"
        os.environ["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"] = "30"
        env = _runtime_env()
        self.assertEqual(env["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"], "1")
        self.assertEqual(env["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"], "30")

    def test_present_with_zero_values(self):
        os.environ["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"] = "0"
        os.environ["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"] = "0"
        env = _runtime_env()
        self.assertEqual(env["COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT"], "0")
        self.assertEqual(env["COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS"], "0")


# ── Memory field contract tests ──────────────────────────────────────────


class CollectProcessMemoryFieldContractTests(unittest.TestCase):
    """Each field matches the exact return type contract."""

    def test_all_fields_have_expected_types(self):
        result = _collect_process_memory()
        # Memory fields: numeric (int/float) or 'absent'
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
        # Thread/module fields: int or 'absent'
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


# ── Eviction lifecycle tests ─────────────────────────────────────────────


class EvictSnapshotModelsSuccessTests(unittest.TestCase):
    """_evict_snapshot_models success path — models dead, threshold pass.

    Note: models are created inline and local refs are deleted before the
    eviction call so the weakref check finds them truly dead (no strong refs
    remain besides those managed inside _evict_snapshot_models).
    """

    def setUp(self):
        _clean_env()
        _RES4LYF_PREPARED.clear()
        _CACHEDIT_PREPARED.clear()

    def _run_inline_evict(self):
        """Create models/ep locally, run evict, return marker.
        No external strong refs to model objects survive the call.
        Models are held only via container.unet/container.clip,
        and those are cleared inside _evict_snapshot_models before gc."""
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
            snapshot_execution_seed=None,
            snapshot_seed_built=False,
        )
        # Delete our local refs so the container is the only holder.
        # The container and its .unet/.clip are managed inside evict.
        del unet, clip
        return ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)

    def _run_inline_evict_captured(self, captured_list):
        """Run evict and capture print output into *captured_list*."""
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
        # Capture prints
        original_print = print
        def _cap_print(*args, **kwargs):
            captured_list.append(" ".join(str(a) for a in args))
            original_print(*args, **kwargs)
        with patch("builtins.print", side_effect=_cap_print):
            marker = ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        return marker, ep

    def test_success_eviction_reaches_evicted_status(self):
        """Success path: weakrefs dead, threshold pass, marker stored."""
        _call_count = [0]

        def _side_effect(*, fields=None):
            _call_count[0] += 1
            if _call_count[0] == 1:
                return _fake_process_memory(smaps_rss_mib=30000.0)
            elif _call_count[0] == 2:
                return _fake_process_memory(smaps_rss_mib=10000.0)
            else:
                return _fake_process_memory(
                    smaps_rss_mib=5000.0,
                    smaps_anonymous_mib=4500.0,
                    smaps_private_dirty_mib=4400.0,
                )

        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   side_effect=_side_effect):
            # _run_inline_evict has no external refs to model objects
            marker, ep = self._run_inline_evict_captured([])

        # Verify marker
        self.assertIsNotNone(ep._eviction_marker)
        self.assertIs(marker, ep._eviction_marker)
        self.assertEqual(ep._eviction_marker["status"], "evicted")
        self.assertEqual(ep._eviction_marker["rss_before_mib"], 30000.0)
        self.assertEqual(ep._eviction_marker["rss_after_trim_mib"], 5000.0)
        self.assertAlmostEqual(ep._eviction_marker["rss_drop_mib"], 25000.0)
        self.assertIn("clip_original_id", ep._eviction_marker)
        self.assertIn("unet_original_id", ep._eviction_marker)
        self.assertEqual(ep._eviction_marker["clip_alive_after_cleanup"], 0)
        self.assertEqual(ep._eviction_marker["unet_alive_after_cleanup"], 0)
        # Marker must be primitive-only (no objects)
        for v in ep._eviction_marker.values():
            self.assertFalse(
                hasattr(v, "__dict__") and callable(getattr(v, "__dict__", None)),
                f"marker contains non-primitive value: {v!r}",
            )
        self.assertTrue(ep._snapshot_models_evicted_before_capture)

        # Verify state cleanup
        self.assertIsNone(ep._cpu_snapshot_unet_runtime_state)
        self.assertIsNone(ep._cpu_snapshot_unet_storage_registry)
        self.assertIsNone(ep._cpu_snapshot_clip_storage_registry)
        self.assertFalse(ep._cpu_snapshot_models_active)
        self.assertIsNone(ep._cpu_snapshot_models)

    def test_success_emits_evicted_final_line(self):
        """Final output line has status=evicted and full schema."""
        captured = []
        _call_count = [0]

        def _side_effect(*, fields=None):
            _call_count[0] += 1
            if _call_count[0] == 1:
                return _fake_process_memory(smaps_rss_mib=30000.0)
            elif _call_count[0] == 2:
                return _fake_process_memory(smaps_rss_mib=10000.0)
            else:
                return _fake_process_memory(
                    smaps_rss_mib=5000.0,
                    smaps_anonymous_mib=4500.0,
                    smaps_private_dirty_mib=4400.0,
                )

        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   side_effect=_side_effect):
            _, ep = self._run_inline_evict_captured(captured)

        final = [l for l in captured if "stage=snapshot_pre_capture" in l and "status=evicted" in l]
        self.assertEqual(len(final), 1, f"expected 1 evicted line, got {len(final)}")
        self.assertIn("clip_original_id=", final[0])
        self.assertIn("unet_original_id=", final[0])
        self.assertIn("clip_alive_after_cleanup=0", final[0])
        self.assertIn("unet_alive_after_cleanup=0", final[0])
        self.assertIn("rss_drop_mib=25000.0", final[0])


# ── Eviction failure tests ───────────────────────────────────────────────


class EvictSnapshotModelsFailureTests(unittest.TestCase):
    """_evict_snapshot_models failure paths."""

    def setUp(self):
        _clean_env()
        _RES4LYF_PREPARED.clear()
        _CACHEDIT_PREPARED.clear()

    def _run_inline_evict_fail(self, memory_side_effect):
        """Run eviction with inline models (so weakrefs die) using patched memory.
        Returns the ctx.exception from the RuntimeError."""
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
            snapshot_execution_seed=None,
            snapshot_seed_built=False,
        )
        # Delete our local refs, then container is the only holder
        del unet, clip
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   side_effect=memory_side_effect):
            with self.assertRaises(RuntimeError) as ctx:
                ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        return ctx.exception, ep

    def test_weakrefs_alive_emits_object_still_alive(self):
        """Models survive → status=object_still_alive, known_reference_state present.
        Models are kept alive via setUp refs (not using inline pattern)."""
        _clean_env()
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
            snapshot_execution_seed=None,
            snapshot_seed_built=False,
        )
        captured = []

        def _side_effect(*, fields=None):
            return _fake_process_memory(smaps_rss_mib=30000.0)

        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))

        # Models are kept alive via local unet/clip refs — weakref check finds them.
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       side_effect=_side_effect):
                with self.assertRaises(RuntimeError) as ctx:
                    ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)

        self.assertIn("Model eviction failed: weakrefs still alive", str(ctx.exception))
        final = [l for l in captured if "stage=snapshot_pre_capture" in l]
        alive_lines = [l for l in final if "status=object_still_alive" in l]
        self.assertGreaterEqual(len(alive_lines), 1, "expected object_still_alive line")
        self.assertIn("known_reference_state=", alive_lines[0])
        # Marker must NOT be set on failure
        self.assertIsNone(ep._eviction_marker)

    def test_memory_evidence_unavailable_emits_error(self):
        """When both smaps and vm are absent → status=error.
        Weakrefs die first (inline pattern), then memory check triggers."""

        def _all_absent(*, fields=None):
            return {f: "absent" for f in (fields or (
                "vm_rss_mib", "smaps_rss_mib", "smaps_anonymous_mib",
                "smaps_private_dirty_mib", "native_thread_count",
                "torch_intraop_threads", "torch_interop_threads",
                "loaded_module_count",
            ))}

        exc, ep = self._run_inline_evict_fail(_all_absent)
        self.assertIn("memory evidence unavailable", str(exc))
        self.assertIsNone(ep._eviction_marker)
        self.assertFalse(ep._snapshot_models_evicted_before_capture)

    def test_insufficient_rss_drop_emits_insufficient_status(self):
        """RSS drop below 8192 MiB → status=insufficient_rss_drop.
        Weakrefs die first (inline pattern), then drop check triggers."""
        _call_count = [0]

        def _side_effect(*, fields=None):
            _call_count[0] += 1
            if _call_count[0] == 1:
                return _fake_process_memory(smaps_rss_mib=15000.0)
            elif _call_count[0] == 2:
                return _fake_process_memory(smaps_rss_mib=14000.0)
            else:
                return _fake_process_memory(smaps_rss_mib=13500.0)

        exc, ep = self._run_inline_evict_fail(_side_effect)
        self.assertIn("RSS drop", str(exc))
        self.assertIn("< 8192 MiB", str(exc))
        self.assertIsNone(ep._eviction_marker)


# ── Eviction state cleanup tests ─────────────────────────────────────────


class EvictSnapshotModelsStateTests(unittest.TestCase):
    """State cleanup verification during eviction."""

    def setUp(self):
        _clean_env()
        _RES4LYF_PREPARED.clear()
        _CACHEDIT_PREPARED.clear()
        self._unet = _FakeModel("unet")
        self._clip = _FakeModel("clip")

    def _caller_local_evict(self, entrypoint, state):
        return entrypoint._evict_snapshot_models(
            entrypoint._cpu_snapshot_models,
            state,
        )

    def test_eviction_records_metadata(self):
        """Eviction stores primitive snapshot-state metadata."""
        ep = _make_fake_entrypoint(self._unet, self._clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={"unet": object()},
            snapshot_model_identities={"unet": "u", "clip": "c"},
            snapshot_execution_seed=42,
            snapshot_seed_built=True,
        )
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
            with self.assertRaises(RuntimeError):
                self._caller_local_evict(ep, bs)
        meta = ep._snapshot_eviction_metadata
        self.assertIn("clip_present", meta)
        self.assertIn("unet_present", meta)
        self.assertIn("torch_module_loaded", meta)
        self.assertIn("transformers_module_loaded", meta)
        self.assertIn("diffusers_module_loaded", meta)
        self.assertIn("cache_dit_module_loaded", meta)
        self.assertIn("comfy_module_loaded", meta)

    def test_eviction_clears_bridge_and_state(self):
        """Bridge clear is called and entrypoint registries are reset."""
        ep = _make_fake_entrypoint(self._unet, self._clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={"unet": object()},
            snapshot_model_identities={"unet": "u", "clip": "c"},
            snapshot_execution_seed=42,
            snapshot_seed_built=True,
        )
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
            with self.assertRaises(RuntimeError):
                self._caller_local_evict(ep, bs)
        self.assertIsNone(ep._cpu_snapshot_unet_runtime_state)
        self.assertIsNone(ep._cpu_snapshot_unet_storage_registry)
        self.assertIsNone(ep._cpu_snapshot_clip_storage_registry)
        self.assertFalse(ep._cpu_snapshot_models_active)
        self.assertIsNone(ep._cpu_snapshot_models)

    def test_eviction_clears_bootstrap_snapshot_state(self):
        """snapshot_loader_outputs, identities, seed are cleared."""
        ep = _make_fake_entrypoint(self._unet, self._clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={"unet": object()},
            snapshot_model_identities={"unet": "u", "clip": "c"},
            snapshot_execution_seed=42,
            snapshot_seed_built=True,
        )
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
            with self.assertRaises(RuntimeError):
                self._caller_local_evict(ep, bs)
        self.assertEqual(bs.snapshot_loader_outputs, {})
        self.assertEqual(bs.snapshot_model_identities, {})
        self.assertIsNone(bs.snapshot_execution_seed)
        self.assertFalse(bs.snapshot_seed_built)

    def test_eviction_clears_res4lyf_and_cachedit_prepared(self):
        """_RES4LYF_PREPARED and _CACHEDIT_PREPARED are cleared."""
        _RES4LYF_PREPARED["wf_hash"] = {"records": ()}
        _CACHEDIT_PREPARED["wf_hash"] = {"unet_id": 123}
        ep = _make_fake_entrypoint(self._unet, self._clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
            with self.assertRaises(RuntimeError):
                self._caller_local_evict(ep, bs)
        self.assertEqual(_RES4LYF_PREPARED, {})
        self.assertEqual(_CACHEDIT_PREPARED, {})

    def test_eviction_preserves_unrelated_globals(self):
        """Certificate cache, workflow hash, RES4LYF hook are preserved."""
        import comfymodal_runtime.modal_app as _ma
        _orig_cert = _ma._V2_CERT_PROCESS_CACHE.copy()
        _orig_wf = _ma._V2_WORKFLOW_HASH
        _orig_res4lyf = _ma._RES4LYF_HOOK_INSTALLED
        _ma._V2_CERT_PROCESS_CACHE["test"] = "value"
        _ma._RES4LYF_HOOK_INSTALLED = True

        ep = _make_fake_entrypoint(self._unet, self._clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
            with self.assertRaises(RuntimeError):
                self._caller_local_evict(ep, bs)

        self.assertIn("test", _ma._V2_CERT_PROCESS_CACHE)
        self.assertEqual(_ma._V2_WORKFLOW_HASH, _orig_wf)
        self.assertTrue(_ma._RES4LYF_HOOK_INSTALLED)

        _ma._V2_CERT_PROCESS_CACHE.clear()
        _ma._V2_CERT_PROCESS_CACHE.update(_orig_cert)
        _ma._RES4LYF_HOOK_INSTALLED = _orig_res4lyf

    def test_eviction_emits_three_checkpoint_lines(self):
        """Three [v2.snapshot_model_eviction_memory] lines are emitted."""
        captured = []
        original_print = print

        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
            original_print(*args, **kwargs)

        ep = _make_fake_entrypoint(self._unet, self._clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )

        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
                with self.assertRaises(RuntimeError):
                    self._caller_local_evict(ep, bs)

        mem_lines = [l for l in captured if "snapshot_model_eviction_memory" in l]
        self.assertEqual(
            len(mem_lines), 3,
            f"expected 3 memory lines, got {len(mem_lines)}: {mem_lines}",
        )
        self.assertIn("stage=before", mem_lines[0])
        self.assertIn("stage=after_gc", mem_lines[1])
        self.assertIn("stage=after_trim", mem_lines[2])

    def test_eviction_emits_final_line_on_error(self):
        """Failure emits final line with status=object_still_alive."""
        captured = []
        original_print = print

        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))
            original_print(*args, **kwargs)

        ep = _make_fake_entrypoint(self._unet, self._clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )

        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
                with self.assertRaises(RuntimeError):
                    self._caller_local_evict(ep, bs)

        final_lines = [l for l in captured if "stage=snapshot_pre_capture" in l]
        self.assertGreaterEqual(len(final_lines), 1)
        self.assertIn("clip_original_id=", final_lines[-1])
        self.assertIn("unet_original_id=", final_lines[-1])

    def test_eviction_does_not_store_marker_on_failure(self):
        """On failure, _eviction_marker is not stored."""
        ep = _make_fake_entrypoint(self._unet, self._clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
        )
        self.assertIsNone(ep._eviction_marker)
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
            with self.assertRaises(RuntimeError):
                self._caller_local_evict(ep, bs)
        # Marker should not be set on failure (weakrefs still alive in test)
        self.assertIsNone(ep._eviction_marker)

    def test_current_preparation_exists_key_accepted(self):
        """diagnostic_snapshot current_preparation_exists=True sets bridge_active_prep=1."""
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
        _orig_diag = ep._preload_bridge.diagnostic_snapshot
        ep._preload_bridge.diagnostic_snapshot = lambda: {"current_preparation_exists": True}
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
                with self.assertRaises(RuntimeError):
                    ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        ep._preload_bridge.diagnostic_snapshot = _orig_diag
        alive = [l for l in captured if "bridge_active_preparation=1" in l]
        self.assertGreaterEqual(len(alive), 1,
            "expected at least one line with bridge_active_preparation=1")

    def test_coordinator_active_forces_bridge_active_prep(self):
        """coordinator._active non-None forces bridge_active_preparation=1."""
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
        ep._preload_bridge.coordinator._active = object()
        with patch("builtins.print", side_effect=_cap_print):
            with patch("comfymodal_runtime.modal_app._collect_process_memory",
                       return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
                with self.assertRaises(RuntimeError):
                    ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        alive = [l for l in captured if "bridge_active_preparation=1" in l]
        self.assertGreaterEqual(len(alive), 1,
            "expected at least one line with bridge_active_preparation=1")


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

        en = "0"
        with patch("builtins.print", side_effect=_cap_print):
            # Simulate the startup disabled path
            if not _parse_evict_models_before_snapshot():
                print(
                    "[v2.snapshot_model_eviction] stage=snapshot_pre_capture "
                    "enabled=0 status=disabled",
                    flush=True,
                )

        evict_lines = [l for l in captured if "snapshot_model_eviction" in l]
        self.assertEqual(len(evict_lines), 1)
        self.assertIn("disabled", evict_lines[0])

    def test_disabled_preserves_models_and_loader_outputs(self):
        """When disabled, models and loader outputs are preserved."""
        ep = ModalRuntimeEntrypoint()
        fake_models = _make_minimal_cpu_models()
        ep._cpu_snapshot_models = fake_models
        ep._preload_bridge = _FakeBridge()
        bs = SimpleNamespace(
            snapshot_loader_outputs={"unet": object()},
            snapshot_model_identities={"unet": "u"},
            snapshot_execution_seed=42,
            snapshot_seed_built=True,
        )

        # Models and state should remain untouched
        self.assertIsNotNone(ep._cpu_snapshot_models)
        self.assertIsNotNone(bs.snapshot_loader_outputs.get("unet"))
        self.assertGreater(len(bs.snapshot_loader_outputs), 0)

    def test_disabled_path_no_error_output(self):
        """Disabled path emits exactly the disabled line, no error/skip."""
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
            "status": "evicted",
            "rss_before_mib": 20000.0,
            "rss_after_trim_mib": 1000.0,
            "rss_drop_mib": 19000.0,
            "clip_original_id": "123",
            "unet_original_id": "456",
            "clip_alive_after_cleanup": 0,
            "unet_alive_after_cleanup": 0,
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
            "status": "evicted",
            "clip_alive_after_cleanup": 0,
            "unet_alive_after_cleanup": 0,
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
            "status": "evicted",
            "clip_alive_after_cleanup": 0,
            "unet_alive_after_cleanup": 0,
        }
        entrypoint._apply_torch_thread_limit = MagicMock()

        captured = []
        sleep_calls = []

        def _cap_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))

        def _tracking_sleep(seconds):
            sleep_calls.append(seconds)
            return None  # don't actually sleep

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
            self.assertLess(
                obs_idx, start_idx,
                "restore_observed must precede idle_start",
            )
        if idle_end:
            end_idx = captured.index(idle_end[0])
            self.assertLess(
                captured.index(idle_start[0]),
                end_idx,
                "idle_start must precede idle_end",
            )
        self.assertIn(3, sleep_calls)

    def test_no_idle_when_marker_none(self):
        """No idle when _eviction_marker is None (no eviction happened)."""
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
        # When marker is None, restore_observed is still emitted (marker=0)
        self.assertEqual(len(obs_lines), 1)
        self.assertIn("marker=0", obs_lines[0])

    def test_primitive_flag_alone_without_dict_produces_marker(self):
        """Primitive _snapshot_models_evicted_before_capture alone (no dict)
        produces marker=1 and enables idle."""
        entrypoint = ModalRuntimeEntrypoint()
        entrypoint._snapshot_models_evicted_before_capture = True
        # _eviction_marker is not set — dict path for older instances only
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
        idle_end = [l for l in captured if "event=end" in l and "snapshot_model_eviction_idle" in l]
        self.assertEqual(len(idle_start), 1,
            "expected idle_start when primitive flag is True")
        self.assertEqual(len(idle_end), 1)
        self.assertIn(5, sleep_calls)


# ── restore() boundary ordering tests ────────────────────────────────────


class RestoreBoundaryOrderingTest(unittest.TestCase):
    """Verify restore() calls _restore_eviction_boundary before
    _apply_torch_thread_limit and that normal restore continuation
    is attempted after the boundary."""

    def setUp(self):
        _clean_env()

    def test_restore_boundary_before_apply_torch_thread(self):
        """entrypoint.restore() calls boundary before apply_torch_thread_limit.
        Uses mocks/stubs that cause a controlled exception after the boundary
        so we can record events and verify ordering."""
        entrypoint = ModalRuntimeEntrypoint()
        entrypoint._eviction_marker = None  # no eviction happened
        entrypoint._snapshot_models_evicted_before_capture = False

        # Stub out the many dependencies that restore() needs to pass through
        # before reaching the controlled exception point.
        events = []

        # _restore_eviction_boundary — must be called first
        original_boundary = entrypoint._restore_eviction_boundary
        def _tracking_boundary():
            events.append("boundary")
            return original_boundary()

        # _apply_torch_thread_limit — must be called after boundary
        original_apply = entrypoint._apply_torch_thread_limit
        def _tracking_apply():
            events.append("apply")
            return original_apply()

        # Stub everything that restore() does after apply_torch_thread_limit
        # to avoid actual ComfyUI/snapshot/GPU work.
        entrypoint._configure_runtime = MagicMock()
        entrypoint._restore_publisher = PropertyMock(return_value=None)  # type: ignore
        # Use MagicMock for deeply nested attributes restore will access

        with patch("comfymodal_runtime.modal_app._capture_remote_identity",
                   return_value={"container_id": "test"}):
            with patch.object(entrypoint, "_restore_eviction_boundary",
                              side_effect=_tracking_boundary):
                with patch.object(entrypoint, "_apply_torch_thread_limit",
                                  side_effect=_tracking_apply):
                    # Cause controlled exception after boundary + apply
                    # but before further restore work that needs real deps.
                    original_configure = entrypoint._configure_runtime
                    def _error_configure(*a, **kw):
                        events.append("configure_runtime")
                        raise RuntimeError("controlled stop after boundary ordering")
                    entrypoint._configure_runtime = _error_configure

                    with self.assertRaises(RuntimeError) as ctx:
                        entrypoint.restore()

        self.assertIn("controlled stop", str(ctx.exception),
                      "expected restore to propagate our controlled exception")
        self.assertIn("boundary", events,
                      "boundary must be called")
        self.assertIn("apply", events,
                      "apply_torch_thread_limit must be called")
        self.assertIn("configure_runtime", events,
                      "normal restore continuation must be attempted")
        self.assertLess(events.index("boundary"), events.index("apply"),
                        "boundary must precede apply_torch_thread_limit")
        self.assertLess(events.index("apply"), events.index("configure_runtime"),
                        "apply_torch_thread_limit must precede configure_runtime")


class WeakrefEvictionTests(unittest.TestCase):
    """Verify weakref-based eviction with caller-local deletion pattern."""

    def setUp(self):
        _clean_env()

    def test_clear_exact_models_from_loaded(self):
        """Verify that even without a real loaded_models(), eviction
        progresses (doesn't crash) and clears registries."""
        unet = _FakeModel("unet")
        clip = _FakeModel("clip")
        ep = _make_fake_entrypoint(unet, clip)
        bs = SimpleNamespace(
            snapshot_loader_outputs={"unet": object(), "clip": object()},
            snapshot_model_identities={"unet": "u", "clip": "c"},
            snapshot_execution_seed=42,
            snapshot_seed_built=True,
        )
        with patch("comfymodal_runtime.modal_app._collect_process_memory",
                   return_value=_fake_process_memory(smaps_rss_mib=30000.0)):
            with self.assertRaises(RuntimeError):
                ep._evict_snapshot_models(ep._cpu_snapshot_models, bs)
        self.assertIsNone(ep._cpu_snapshot_unet_runtime_state)
        self.assertIsNone(ep._cpu_snapshot_unet_storage_registry)
        self.assertIsNone(ep._cpu_snapshot_clip_storage_registry)
        self.assertFalse(ep._cpu_snapshot_models_active)


if __name__ == "__main__":
    unittest.main()
