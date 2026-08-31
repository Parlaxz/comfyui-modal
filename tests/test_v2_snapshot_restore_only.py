"""Focused tests for the prepare-then-evict snapshot restore-only benchmark.

Reconciled design (identity-only gate + strict clip_vae eviction retain):

  * ``COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET`` is an experiment identity /
    reporting gate ONLY.  It propagates through ``_runtime_env`` and the
    probe's ``snapshot_exclude_unet_gate``, but it must NOT control
    construction/load/dtype validation and must NOT weaken the production
    snapshot invariant (which always requires the UNET under the
    ``production`` profile).  Startup unconditionally calls
    ``load_cpu_snapshot_models`` (CLIP + UNET + VAE) and runs the normal
    BF16/diffusion-model validation; the Plan-C activation gate uses the
    state guard ``getattr(self._cpu_snapshot_models, "unet", None)``.
  * The UNET-absent snapshot is produced by the strict ``clip_vae``
    eviction retain role in ``_evict_snapshot_models``: the existing full
    UNET cleanup/ownership/weakref-dead proof runs, then fresh CLIP and VAE
    are reloaded back into the retained ``CpuSnapshotModels`` container
    (``unet=None``, no retained eviction slot, activation off).
  * ``_restore_eviction_boundary`` emits container-retained evidence for
    ``clip_vae`` and returns, leaving the container CLIP/VAE available.
  * The no-op ``run_snapshot_restore_only_probe`` reports clip/vae/
    container-retained plus all current identity/timestamp/RSS/UNET-absence
    evidence; the harness validity requires UNET absent, container present
    and retained, snapshot identity nonempty, and CLIP/VAE present, with
    exactly-6 valid probes hard-stop.
  * Both ``.bat`` scripts wire the restore-only block to set
    ``COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1`` (identity),
    ``COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1``,
    ``COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae``, restore idle 0 and the
    ``inherit`` profile.  The deploy invocation is labeled/excluded and
    issues NO probes; the run script invokes the reuse harness.

No Modal, tensors, psutil, or forbidden tools.
"""

from __future__ import annotations

import asyncio
import contextlib
import gc
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import patch

import comfymodal_runtime.modal_app as modal_app
from comfymodal_runtime.modal_app import (
    ModalRuntimeEntrypoint,
    _parse_evict_retain_role,
    _runtime_env,
    _snapshot_exclude_unet_enabled,
    production_snapshot_invariant,
)
from comfymodal_runtime.cpu_snapshot_models import CpuSnapshotModels

# Import the benchmark harness HERMETICALLY: ``tools.benchmark_v2_direct``
# inserts the parent ComfyUI root into ``sys.path`` at import time (making the
# real ``comfy`` package importable in this process from then on).  The module
# object stays available to the tests below, but sys.path and sys.modules are
# restored so this test module never changes ambient comfy importability.
_path_before = list(sys.path)
_comfy_mods_before = {
    _k: _v for _k, _v in list(sys.modules.items())
    if _k == "comfy" or _k.startswith("comfy.") or _k.startswith("comfy_")
}
import tools.benchmark_v2_direct as benchmark  # noqa: E402
sys.path[:] = _path_before
for _k in list(sys.modules):
    if _k == "comfy" or _k.startswith("comfy.") or _k.startswith("comfy_"):
        if _k in _comfy_mods_before:
            sys.modules[_k] = _comfy_mods_before[_k]
        else:
            sys.modules.pop(_k, None)


# ── Helpers ────────────────────────────────────────────────────────────────


class _FakeModel:
    """Weakref-able stand-in for a snapshot model object."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.model = SimpleNamespace(label=label)


def _lean_snapshot_models(unet_present: bool = False) -> CpuSnapshotModels:
    """A CpuSnapshotModels struct whose UNET slot is either empty or filled."""
    model_key = SimpleNamespace(
        unet_identity="z_image_turbo_bf16.safetensors",
        clip_identity="clip_l.safetensors",
        vae_identity="vae_ft_mse.safetensors",
        stable_hash="a" * 32,
    )
    return CpuSnapshotModels(
        model_key=model_key,  # type: ignore[arg-type]
        model_spec={},
        normalized_profile={},
        file_facts=(),
        unet=SimpleNamespace(model=None) if unet_present else None,
        clip=SimpleNamespace(),
        vae=SimpleNamespace(),
    )


def _full_container() -> CpuSnapshotModels:
    """A fully populated container for the clip_vae eviction test."""
    model_key = SimpleNamespace(
        unet_identity="z_image_turbo_bf16.safetensors",
        clip_identity="clip_l.safetensors",
        vae_identity="vae_ft_mse.safetensors",
        stable_hash="b" * 32,
    )
    return CpuSnapshotModels(
        model_key=model_key,  # type: ignore[arg-type]
        model_spec={},
        normalized_profile={
            "mode": "split",
            "unet": "z_image_turbo_bf16.safetensors",
            "clip1": "clip_l.safetensors",
            "clip_type": "stable_diffusion",
            "vae": "vae_ft_mse.safetensors",
            "weight_dtype": "default",
        },
        file_facts=(),
        unet=_FakeModel("unet"),
        clip=_FakeModel("clip"),
        vae=_FakeModel("vae"),
        vae_policy_mode="v1",
        vae_policy_version=1,
        vae_weight_dtype="bfloat16",
        vae_compute_dtype="bfloat16_native",
        vae_memory_format="contiguous",
        vae_policy_metadata={"vae_prefetch_mode": "off", "c5_impl_version": "c5-1"},
    )


_MEMORY_SNAPSHOT = {
    "vm_rss_mib": 13000.0,
    "vm_hwm_mib": 13500.0,
    "smaps_rss_mib": 12000.0,
    "smaps_pss_mib": 11900.0,
    "smaps_private_clean_mib": 3000.0,
    "smaps_private_dirty_mib": 8500.0,
    "smaps_shared_clean_mib": 200.0,
    "smaps_shared_dirty_mib": 300.0,
    "smaps_anonymous_mib": 8600.0,
    "native_thread_count": 12,
    "torch_intraop_threads": 8,
    "torch_interop_threads": 2,
    "loaded_module_count": 90,
}


def _install_comfy_fakes() -> None:
    """Install deterministic fake ``comfy`` modules for eviction tests.

    The production path runs inside the Modal image where the real comfy
    modules exist.  For unit tests we shadow them so cleanup/ownership
    behaviour is fully deterministic regardless of the local environment.
    """
    saved: dict[str, Any] = {}
    for name in ("comfy", "comfy.utils", "comfy.model_management"):
        saved[name] = sys.modules.get(name)
    comfy_mod = ModuleType("comfy")
    comfy_mod.__path__ = []
    cu = ModuleType("comfy.utils")
    cu.DISABLE_MMAP = False
    mm = ModuleType("comfy.model_management")
    mm.current_loaded_models = []
    mm.free_memory = lambda *a, **k: None
    mm.cleanup_models = lambda *a, **k: None
    mm.loaded_models = lambda: []
    mm.unload_model_and_clones = lambda *a, **k: None
    sys.modules["comfy"] = comfy_mod
    sys.modules["comfy.utils"] = cu
    sys.modules["comfy.model_management"] = mm
    _install_comfy_fakes._saved = saved


def _restore_comfy_fakes() -> None:
    saved = getattr(_install_comfy_fakes, "_saved", None)
    if saved is None:
        return
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod
    _install_comfy_fakes._saved = None


def _fake_valid_result(
    request_id: str,
    restored_instance_id: str,
    *,
    unet_present: int = 0,
    clip_present: int = 1,
    vae_present: int = 1,
    container_retained: int = 1,
) -> dict[str, Any]:
    resume_ns = 1_700_000_000_000_000_000
    return {
        "status": "ok",
        "mode": "snapshot_restore_only",
        "request_id": request_id,
        "entry_wall_unix_ns": resume_ns + 5_000_000_000,
        "graph_executed": False,
        "unet_loaded": False,
        "vae_decoded": False,
        "volume_read": False,
        "placement": {
            "cloud": "aws", "region": "us-east-2", "gpu": "rtx-pro-6000",
            "cpu_request": "12", "memory_request_mb": "32768",
        },
        "identity": {
            "restored_instance_id": restored_instance_id,
            "restore_count": 1,
            "request_count": 1,
            "container_session_id": "sess-1",
        },
        "snapshot_identity": "a" * 32,
        "snapshot_identity_source": "cpu_snapshot_models.model_key.stable_hash",
        "invariant": {
            "unet_present": unet_present,
            "retained_unet_payload": 0,
            "reconstructed_unet_present": 0,
            "cpu_snapshot_models_present": 1,
            "container_retained": container_retained,
            "clip_present": clip_present,
            "vae_present": vae_present,
            "cpu_snapshot_models_active": 0,
            "snapshot_exclude_unet_gate": 1,
            "eviction_retained_role": "clip_vae",
            "retained_unet_runtime_state_present": 0,
            "retained_eviction_model_present": 0,
            "model_key_unet_identity": "z_image_turbo_bf16.safetensors",
        },
        "restore_timing": {
            "remote_python_resume_wall_unix_ns": resume_ns,
            "restore_method_start_wall_unix_ns": resume_ns,
            "restore_method_end_wall_unix_ns": resume_ns + 2_000_000_000,
            "restore_total_ms": 1500.0,
            "restore_session_id": "rs-1",
            "restore_count": 1,
            "restored_instance_id": restored_instance_id,
            "container_session_id": "sess-1",
            "lifecycle_status": "ok",
            "lifecycle_method": "restore",
        },
        "rss": {"rss_mib": 8123.4, "source": "smaps_rollup"},
    }


class _FakeRemoteAio:
    def __init__(self, fn):
        self._fn = fn

    def aio(self, request_id: str = "") -> Any:
        return self._fn(request_id)


class _FakeProbeMethod:
    def __init__(self, fn):
        self.remote = _FakeRemoteAio(fn)


class _FakeHandle:
    def __init__(self, fn):
        self.run_snapshot_restore_only_probe = _FakeProbeMethod(fn)


class _FakeTransport:
    def __init__(self, fn):
        self._fn = fn

    def _v2_handle(self, workspace: Any, gpu: str) -> _FakeHandle:
        return _FakeHandle(self._fn)


# ══════════════════════════════════════════════════════════════════════
# Tests: SNAPSHOT_EXCLUDE_UNET is identity/reporting ONLY
# ══════════════════════════════════════════════════════════════════════


class TestIdentityOnlyFlag(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", None)
        os.environ.pop("COMFYMODAL_V2_ENV_PROFILE", None)

    def test_default_off(self):
        os.environ.pop("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", None)
        self.assertFalse(_snapshot_exclude_unet_enabled())

    def test_on_when_one(self):
        os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = "1"
        self.assertTrue(_snapshot_exclude_unet_enabled())

    def test_off_for_other_values(self):
        # env_flag treats 1/true/yes/on as on; everything else stays off.
        for value in ("0", "false", "no", "off", "2", "anything"):
            os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = value
            self.assertFalse(
                _snapshot_exclude_unet_enabled(),
                f"value {value!r} must stay off",
            )

    def test_runtime_env_propagates_gate(self):
        os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = "1"
        self.assertEqual(
            _runtime_env()["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"], "1"
        )

    def test_runtime_env_defaults_zero_when_absent(self):
        os.environ.pop("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", None)
        self.assertEqual(
            _runtime_env()["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"], "0"
        )

    def test_excluded_builder_removed_from_class(self):
        # The forbidden skip-UNET construction path is fully removed.
        self.assertFalse(
            hasattr(ModalRuntimeEntrypoint, "_build_unet_excluded_snapshot_models")
        )

    def test_flag_never_gates_construction_validation_or_activation(self):
        # Source-level reconciliation proof: no conditional excluded builder,
        # no flag guard in the Plan-C activation gate, no skipped dtype
        # validation — startup unconditionally calls load_cpu_snapshot_models.
        src = Path(modal_app.__file__).read_text(encoding="utf-8")
        self.assertNotIn("_build_unet_excluded_snapshot_models", src)
        self.assertNotIn("and not _snapshot_exclude_unet_enabled()", src)
        self.assertNotIn("if _snapshot_exclude_unet_enabled():", src)
        self.assertIn("load_cpu_snapshot_models(", src)
        self.assertIn("load_unet=_cpu_load_unet", src)
        self.assertIn(
            'getattr(self._cpu_snapshot_models, "unet", None) is not None',
            src,
        )


# ══════════════════════════════════════════════════════════════════════
# Tests: production snapshot invariant always expects UNET
# ══════════════════════════════════════════════════════════════════════


class TestProductionInvariantUnconditional(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", None)
        os.environ.pop("COMFYMODAL_V2_ENV_PROFILE", None)

    def test_expected_unet_is_always_one(self):
        os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = "1"
        os.environ["COMFYMODAL_V2_ENV_PROFILE"] = "inherit"
        result = production_snapshot_invariant(
            _lean_snapshot_models(unet_present=False), phase="test",
        )
        self.assertEqual(result["expected_unet"], 1)
        self.assertNotIn("exclude_unet", result)

    def test_flag_never_weakens_production(self):
        # The identity flag must NOT flip the production expectation.
        os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = "1"
        os.environ["COMFYMODAL_V2_ENV_PROFILE"] = "production"
        with self.assertRaises(RuntimeError):
            production_snapshot_invariant(
                _lean_snapshot_models(unet_present=False), phase="test",
            )

    def test_production_requires_unet_when_flag_off(self):
        os.environ.pop("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", None)
        os.environ["COMFYMODAL_V2_ENV_PROFILE"] = "production"
        with self.assertRaises(RuntimeError):
            production_snapshot_invariant(
                _lean_snapshot_models(unet_present=False), phase="test",
            )

    def test_production_passes_when_full(self):
        os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = "1"
        os.environ["COMFYMODAL_V2_ENV_PROFILE"] = "production"
        result = production_snapshot_invariant(
            _lean_snapshot_models(unet_present=True), phase="test",
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["actual_unet"], 1)

    def test_inherit_profile_never_raises(self):
        # The restore-only app uses the inherit profile; a UNET-absent
        # container after clip_vae eviction must never trip the invariant.
        os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = "1"
        os.environ["COMFYMODAL_V2_ENV_PROFILE"] = "inherit"
        result = production_snapshot_invariant(
            _lean_snapshot_models(unet_present=False), phase="test",
        )
        self.assertEqual(result["status"], "pass")


# ══════════════════════════════════════════════════════════════════════
# Tests: strict eviction retain-role parser
# ══════════════════════════════════════════════════════════════════════


class TestEvictRetainRoleParser(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("COMFYMODAL_V2_EVICT_RETAIN_ROLE", None)

    def test_absent_defaults_none(self):
        os.environ.pop("COMFYMODAL_V2_EVICT_RETAIN_ROLE", None)
        self.assertEqual(_parse_evict_retain_role(), "none")

    def test_empty_defaults_none(self):
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = ""
        self.assertEqual(_parse_evict_retain_role(), "none")

    def test_existing_roles_unchanged(self):
        for role in ("none", "clip", "unet"):
            os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = role
            self.assertEqual(_parse_evict_retain_role(), role)

    def test_clip_vae_accepted(self):
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "clip_vae"
        self.assertEqual(_parse_evict_retain_role(), "clip_vae")

    def test_invalid_values_rejected(self):
        for value in ("clip-vae", "CLIP_VAE", "Clip_Vae", "both", "1", "true", "clip,vae", " clip_vae"):
            os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = value
            with self.assertRaises(RuntimeError, msg=f"value {value!r} must fail"):
                _parse_evict_retain_role()


# ══════════════════════════════════════════════════════════════════════
# Tests: clip_vae eviction retention + weakref-dead proof
# ══════════════════════════════════════════════════════════════════════


class TestEvictSnapshotModelsClipVae(unittest.TestCase):
    def setUp(self) -> None:
        _install_comfy_fakes()
        # The strict clip_vae retain role is selected via the environment.
        os.environ["COMFYMODAL_V2_EVICT_RETAIN_ROLE"] = "clip_vae"
        self._entrypoint = self._make_entrypoint()

    def tearDown(self) -> None:
        _restore_comfy_fakes()
        for key in (
            "COMFYMODAL_V2_EVICT_RETAIN_ROLE",
            "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS",
        ):
            os.environ.pop(key, None)
        gc.collect()

    @staticmethod
    def _make_entrypoint() -> ModalRuntimeEntrypoint:
        ep = ModalRuntimeEntrypoint()
        ep._preload_bridge = SimpleNamespace(
            clear=lambda: None,
            diagnostic_snapshot=lambda: {},
            coordinator=None,
        )
        ep._cpu_snapshot_models = None
        return ep

    def _run_clip_vae_eviction(
        self,
        container: CpuSnapshotModels,
        *,
        keep_unet_alive: bool = False,
        reload_vae_fn: Any = None,
        vae_revalidation: Any = None,
        vae_revalidation_side_effect: Any = None,
    ) -> dict[str, Any]:
        if reload_vae_fn is None:
            reload_vae_fn = lambda name: _FakeModel("new-vae")
        if vae_revalidation is None and vae_revalidation_side_effect is None:
            vae_revalidation = ({"object_id": "recomputed"}, None)
        ep = self._entrypoint
        ep._cpu_snapshot_models = container
        bootstrap = SimpleNamespace(
            snapshot_loader_outputs={},
            snapshot_model_identities={},
            snapshot_execution_seed=None,
            snapshot_seed_built=False,
        )
        unet_ref = container.unet if keep_unet_alive else None
        if vae_revalidation_side_effect is not None:
            vae_patch = patch(
                "comfymodal_runtime.cpu_snapshot_models._validate_vae_policy_metadata",
                side_effect=vae_revalidation_side_effect,
            )
        else:
            vae_patch = patch(
                "comfymodal_runtime.cpu_snapshot_models._validate_vae_policy_metadata",
                return_value=vae_revalidation,
            )
        with patch.object(
            modal_app, "_collect_process_memory", return_value=_MEMORY_SNAPSHOT,
        ), patch.object(
            modal_app, "build_unique_storage_registry",
            return_value=SimpleNamespace(ranges=(), total_bytes=0),
        ), vae_patch:
            meta = ep._evict_snapshot_models(
                container,
                bootstrap,
                reload_unet_fn=lambda *a, **k: None,
                reload_clip_fn=lambda *a, **k: _FakeModel("new-clip"),
                reload_vae_fn=reload_vae_fn,
                snap_ctx_cm=lambda: contextlib.nullcontext(),
            )
        if keep_unet_alive:
            del unet_ref
        return meta

    def test_clip_vae_retains_container_with_fresh_clip_vae(self):
        container = _full_container()
        meta = self._run_clip_vae_eviction(container)

        # Container is retained and points back at the same object.
        self.assertIs(self._entrypoint._cpu_snapshot_models, container)
        self.assertIsNone(container.unet)
        self.assertIsNotNone(container.clip)
        self.assertIsNotNone(container.vae)
        self.assertEqual(container.clip.label, "new-clip")
        self.assertEqual(container.vae.label, "new-vae")
        # No retained eviction slot / activation / runtime state.
        self.assertIsNone(self._entrypoint._snapshot_eviction_retained_model)
        self.assertEqual(self._entrypoint._snapshot_eviction_retained_model_id, 0)
        self.assertFalse(self._entrypoint._cpu_snapshot_models_active)
        self.assertIsNone(self._entrypoint._cpu_snapshot_unet_runtime_state)
        # VAE policy metadata recomputed onto the container.
        self.assertEqual(
            self._entrypoint._cpu_snapshot_models.vae_validation_metadata,
            {"object_id": "recomputed"},
        )

    def test_clip_vae_marker_and_metadata(self):
        container = _full_container()
        meta = self._run_clip_vae_eviction(container)

        marker = self._entrypoint._eviction_marker
        self.assertEqual(marker["status"], "full_eviction_complete")
        self.assertEqual(marker["retain_role"], "clip_vae")
        self.assertEqual(marker["container_retained"], 1)
        self.assertEqual(marker["retained_clip_present"], 1)
        self.assertEqual(marker["retained_vae_present"], 1)
        self.assertEqual(marker["retained_unet_present"], 0)
        self.assertEqual(meta["retained_role"], "clip_vae")
        self.assertEqual(
            self._entrypoint._snapshot_eviction_metadata["retained_role"],
            "clip_vae",
        )
        self.assertTrue(self._entrypoint._snapshot_models_evicted_before_capture)

    def test_fresh_loads_are_new_objects(self):
        container = _full_container()
        original_clip_id = id(container.clip)
        original_vae_id = id(container.vae)
        self._run_clip_vae_eviction(container)
        self.assertNotEqual(id(container.clip), original_clip_id)
        self.assertNotEqual(id(container.vae), original_vae_id)

    def test_original_unet_stays_alive_fails_closed(self):
        # Fail closed: if the original UNET cannot be proven dead the
        # eviction must raise before capture.
        container = _full_container()
        with self.assertRaises(RuntimeError) as ctx:
            self._run_clip_vae_eviction(container, keep_unet_alive=True)
        self.assertIn("weakrefs still alive", str(ctx.exception))

    def test_vae_reload_none_fails_closed(self):
        container = _full_container()
        with self.assertRaises(RuntimeError):
            self._run_clip_vae_eviction(
                container, reload_vae_fn=lambda name: None,
            )

    def test_vae_policy_revalidation_failure_fails_closed(self):
        container = _full_container()

        def _bad_revalidation(vae, policy, **kwargs):
            raise RuntimeError("VAE policy revalidation failed")

        with self.assertRaises(RuntimeError) as ctx:
            self._run_clip_vae_eviction(
                container, vae_revalidation_side_effect=_bad_revalidation,
            )
        self.assertIn("VAE policy revalidation failed", str(ctx.exception))

    def test_missing_vae_in_profile_fails_closed(self):
        container = _full_container()
        container.normalized_profile = dict(container.normalized_profile)
        container.normalized_profile.pop("vae", None)
        with self.assertRaises(RuntimeError) as ctx:
            self._run_clip_vae_eviction(container)
        self.assertIn("no 'vae' field", str(ctx.exception))

    def test_original_weakrefs_dead_after_clip_vae_eviction(self):
        # The weakref-dead proof is satisfied only when the originals are
        # garbage collected.  Run gc before the method and verify no
        # lingering reference keeps them alive (method would have raised).
        container = _full_container()
        import weakref as _wr
        unet_wr = _wr.ref(container.unet)
        clip_wr = _wr.ref(container.clip)
        vae_wr = _wr.ref(container.vae)
        self._run_clip_vae_eviction(container)
        self.assertIsNone(unet_wr())
        self.assertIsNone(clip_wr())
        self.assertIsNone(vae_wr())


# ══════════════════════════════════════════════════════════════════════
# Tests: restore boundary for clip_vae (container retained)
# ══════════════════════════════════════════════════════════════════════


class TestRestoreEvictionBoundaryClipVae(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS", None)
        os.environ.pop("COMFYMODAL_V2_EVICT_RETAIN_ROLE", None)

    def test_clip_vae_emits_evidence_and_leaves_container_available(self):
        ep = ModalRuntimeEntrypoint()
        clip = SimpleNamespace()
        vae = SimpleNamespace()
        container = _lean_snapshot_models(unet_present=False)
        container.clip = clip
        container.vae = vae
        ep._snapshot_models_evicted_before_capture = True
        ep._eviction_marker = {"status": "full_eviction_complete", "retain_role": "clip_vae"}
        ep._snapshot_eviction_retained_role = "clip_vae"
        ep._snapshot_eviction_retained_model = None
        ep._snapshot_eviction_retained_model_id = 0
        ep._snapshot_eviction_retained_model_type = ""
        ep._cpu_snapshot_models = container

        with patch.object(
            modal_app, "_collect_process_memory", return_value=_MEMORY_SNAPSHOT,
        ):
            # Must NOT raise for clip_vae (no retained-slot release).
            ep._restore_eviction_boundary()

        self.assertEqual(
            ep._snapshot_eviction_retained_release_status, "container_retained",
        )
        # Container CLIP/VAE left available; unet still absent.
        self.assertIs(ep._cpu_snapshot_models, container)
        self.assertIs(ep._cpu_snapshot_models.clip, clip)
        self.assertIs(ep._cpu_snapshot_models.vae, vae)
        self.assertIsNone(ep._cpu_snapshot_models.unet)
        self.assertIsNone(ep._snapshot_eviction_retained_model)


# ══════════════════════════════════════════════════════════════════════
# Tests: no-op restore-only probe method semantics / data
# ══════════════════════════════════════════════════════════════════════


class TestRestoreOnlyProbeMethod(unittest.TestCase):
    def _make_entrypoint(self, *, unet_present: bool = False) -> ModalRuntimeEntrypoint:
        ep = ModalRuntimeEntrypoint()
        ep._request_count = 0
        ep._restore_count = 1
        ep._restored_instance_id = "restored-abc-123"
        ep._restore_timing = {
            "restore_total_ms": 1234.5,
            "restore_session_id": "rs-probe",
            "restored_instance_id": "restored-abc-123",
            "container_session_id": "sess-probe",
            "restore_count": 1,
            "lifecycle_status": "ok",
            "lifecycle_method": "restore",
            "remote_python_resume_wall_unix_ns": 1_700_000_000_000_000_000,
            "restore_method_start_wall_unix_ns": 1_700_000_000_000_000_000,
            "restore_method_end_wall_unix_ns": 1_700_000_000_002_000_000,
        }
        ep._cpu_snapshot_models = _lean_snapshot_models(unet_present=unet_present)
        ep._cpu_snapshot_models_active = False
        ep._cpu_snapshot_unet_runtime_state = None
        ep._snapshot_eviction_retained_model = None
        ep._snapshot_eviction_retained_role = "clip_vae"
        return ep

    def test_exclusion_probe_reports_unet_absent(self):
        os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = "1"
        try:
            ep = self._make_entrypoint(unet_present=False)
            result = ep.run_snapshot_restore_only_probe(request_id="req-1")
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["mode"], "snapshot_restore_only")
            self.assertEqual(result["request_id"], "req-1")
            invariant = result["invariant"]
            self.assertEqual(invariant["unet_present"], 0)
            self.assertEqual(invariant["retained_unet_payload"], 0)
            self.assertEqual(invariant["reconstructed_unet_present"], 0)
            self.assertEqual(invariant["snapshot_exclude_unet_gate"], 1)
            self.assertEqual(invariant["cpu_snapshot_models_present"], 1)
            self.assertEqual(invariant["model_key_unet_identity"], "z_image_turbo_bf16.safetensors")
            self.assertEqual(result["snapshot_identity"], "a" * 32)
            self.assertFalse(result["graph_executed"])
            self.assertFalse(result["unet_loaded"])
            self.assertFalse(result["vae_decoded"])
            self.assertFalse(result["volume_read"])
            self.assertEqual(result["identity"]["restored_instance_id"], "restored-abc-123")
            self.assertEqual(result["identity"]["request_count"], 1)
        finally:
            os.environ.pop("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", None)

    def test_probe_reports_clip_vae_container_retained_evidence(self):
        os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = "1"
        try:
            ep = self._make_entrypoint(unet_present=False)
            result = ep.run_snapshot_restore_only_probe(request_id="req-cv")
            invariant = result["invariant"]
            self.assertEqual(invariant["clip_present"], 1)
            self.assertEqual(invariant["vae_present"], 1)
            self.assertEqual(invariant["container_retained"], 1)
            self.assertEqual(invariant["eviction_retained_role"], "clip_vae")
        finally:
            os.environ.pop("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", None)

    def test_probe_reports_unet_present_when_snapshot_has_unet(self):
        # Without eviction, a snapshot with a UNET is reported (harness rejects).
        os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = "0"
        try:
            ep = self._make_entrypoint(unet_present=True)
            result = ep.run_snapshot_restore_only_probe(request_id="req-3")
            self.assertEqual(result["invariant"]["unet_present"], 1)
            self.assertEqual(result["invariant"]["retained_unet_payload"], 1)
            self.assertEqual(result["invariant"]["container_retained"], 0)
        finally:
            os.environ.pop("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", None)

    def test_probe_surfaces_restore_timing_and_entry(self):
        os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = "1"
        try:
            ep = self._make_entrypoint(unet_present=False)
            # Placement is sourced from the process environment.  Keep this
            # hermetic assertion independent of a host/runner's Modal metadata.
            with patch.dict(
                os.environ,
                {"MODAL_CLOUD_PROVIDER": "", "MODAL_REGION": ""},
                clear=False,
            ):
                result = ep.run_snapshot_restore_only_probe(request_id="req-2")
            timing = result["restore_timing"]
            self.assertEqual(timing["remote_python_resume_wall_unix_ns"], 1_700_000_000_000_000_000)
            self.assertEqual(timing["restore_total_ms"], 1234.5)
            self.assertEqual(timing["restore_session_id"], "rs-probe")
            self.assertEqual(timing["restore_count"], 1)
            self.assertGreater(result["entry_wall_unix_ns"], 0)
            self.assertGreater(result["entry_mono_ns"], 0)
            self.assertIsInstance(result["rss"], dict)
            self.assertIn("source", result["rss"])
            self.assertEqual(result["placement"]["cloud"], "")
            # placement keys always present
            for key in ("cloud", "region", "gpu", "cpu_request", "memory_request_mb"):
                self.assertIn(key, result["placement"])
        finally:
            os.environ.pop("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", None)

    def test_probe_never_loads_unet_or_reads_volume(self):
        # The probe only reads live attributes; no loader/volume calls.
        os.environ["COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"] = "1"
        try:
            ep = self._make_entrypoint(unet_present=False)
            with patch.object(
                ModalRuntimeEntrypoint, "_load_legacy_runtime",
                side_effect=AssertionError("probe must not load runtime"),
            ):
                with patch(
                    "comfymodal_runtime.modal_app._read_v2_validation_certificate_for_snapshot",
                    side_effect=AssertionError("probe must not read Volume/cert"),
                ):
                    result = ep.run_snapshot_restore_only_probe(request_id="req-4")
            self.assertEqual(result["status"], "ok")
        finally:
            os.environ.pop("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", None)


# ══════════════════════════════════════════════════════════════════════
# Tests: harness validity gate
# ══════════════════════════════════════════════════════════════════════


class TestRestoreOnlyValidity(unittest.TestCase):
    def _valid_attempt(self) -> dict[str, Any]:
        result = _fake_valid_result("req-v", "inst-v")
        return {
            "result": result,
            "identity": result["identity"],
            "cold_check": {"cold": True, "failures": []},
            "cold_gate_available": True,
            "banner_epoch_ms": 1_700_000_000_000.0,
            "dispatch_unix_ms": 1_699_999_800_000,
            "error": None,
            "dnf": False,
        }

    def test_fully_valid_attempt_passes(self):
        valid, failures = benchmark._restore_only_validity(self._valid_attempt())
        self.assertTrue(valid, failures)

    def test_missing_banner_fails_closed(self):
        attempt = self._valid_attempt()
        attempt["banner_epoch_ms"] = None
        valid, failures = benchmark._restore_only_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("banner" in f for f in failures))

    def test_missing_python_resume_timestamp_fails_closed(self):
        attempt = self._valid_attempt()
        attempt["result"]["restore_timing"]["remote_python_resume_wall_unix_ns"] = 0
        valid, failures = benchmark._restore_only_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("remote_python_resume_wall_unix_ns" in f for f in failures))

    def test_unet_present_fails_closed(self):
        attempt = self._valid_attempt()
        attempt["result"] = _fake_valid_result("req-v", "inst-v", unet_present=1)
        attempt["result"]["invariant"]["retained_unet_payload"] = 1
        attempt["result"]["invariant"]["reconstructed_unet_present"] = 1
        valid, failures = benchmark._restore_only_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("unet_present" in f for f in failures))

    def test_container_not_present_fails_closed(self):
        attempt = self._valid_attempt()
        attempt["result"]["invariant"]["cpu_snapshot_models_present"] = 0
        attempt["result"]["invariant"]["container_retained"] = 0
        valid, failures = benchmark._restore_only_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("cpu_snapshot_models_present" in f for f in failures))
        self.assertTrue(any("container_retained" in f for f in failures))

    def test_clip_absent_fails_closed(self):
        attempt = self._valid_attempt()
        attempt["result"]["invariant"]["clip_present"] = 0
        valid, failures = benchmark._restore_only_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("clip_present" in f for f in failures))

    def test_vae_absent_fails_closed(self):
        attempt = self._valid_attempt()
        attempt["result"]["invariant"]["vae_present"] = 0
        valid, failures = benchmark._restore_only_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("vae_present" in f for f in failures))

    def test_container_not_retained_fails_closed(self):
        attempt = self._valid_attempt()
        attempt["result"]["invariant"]["container_retained"] = 0
        valid, failures = benchmark._restore_only_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("container_retained" in f for f in failures))

    def test_cold_gate_failure_fails_closed(self):
        attempt = self._valid_attempt()
        attempt["cold_check"] = {
            "cold": False,
            "failures": ["restore_count=2, expected 1"],
        }
        valid, failures = benchmark._restore_only_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("cold identity gate" in f for f in failures))

    def test_missing_snapshot_identity_fails_closed(self):
        attempt = self._valid_attempt()
        attempt["result"]["snapshot_identity"] = ""
        valid, failures = benchmark._restore_only_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("snapshot_identity" in f for f in failures))

    def test_missing_placement_fails_closed(self):
        attempt = self._valid_attempt()
        attempt["result"]["placement"]["cloud"] = ""
        valid, failures = benchmark._restore_only_validity(attempt)
        self.assertFalse(valid)
        self.assertTrue(any("placement.cloud" in f for f in failures))

    def test_intervals_derivable(self):
        intervals = benchmark._restore_only_intervals(self._valid_attempt())
        self.assertIsNotNone(intervals["dispatch_to_banner_ms"])
        self.assertIsNotNone(intervals["pre_python_restore_ms"])
        self.assertIsNotNone(intervals["python_restore_total_ms"])
        self.assertIsNotNone(intervals["python_resume_to_method_entry_ms"])
        self.assertIsNotNone(intervals["banner_to_method_entry_ms"])
        self.assertIsNotNone(intervals["dispatch_to_method_entry_ms"])


# ══════════════════════════════════════════════════════════════════════
# Tests: harness exactly-6-valid hard-stop loop
# ══════════════════════════════════════════════════════════════════════


class TestRestoreOnlyHarnessLoop(unittest.TestCase):
    def _run_harness(
        self, probe_fn: Any, *, run_count: int = 6, max_attempts: int = 40,
    ) -> dict[str, Any]:
        banner_timestamps: dict[str, float] = {}

        async def _fake_banner(
            workspace: Any, app_name: str, request_id: str, **kwargs: Any,
        ) -> dict[str, Any]:
            return {"banner_epoch_ms": banner_timestamps.get(request_id, 1_700_000_000_000.0)}

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)

            def _tracked_probe(request_id: str) -> Any:
                result = probe_fn(request_id)
                banner_timestamps[request_id] = 1_700_000_000_000.0
                return result

            with patch.object(
                benchmark, "_fetch_restore_only_banner_timing", new=_fake_banner,
            ):
                summary = asyncio.run(benchmark._run_snapshot_restore_only(
                    workspace={"token_id": "t", "token_secret": "s"},
                    transport=_FakeTransport(_tracked_probe),
                    output_dir=out_dir,
                    run_count=run_count,
                    max_attempts=max_attempts,
                    gap_seconds=0.0,
                    app_name="stable-modal-comfy-v2-restore-only-shadow",
                    class_name="ModalRuntimeEntrypointV2",
                    gpu="rtx-pro-6000",
                ))
            self.assertTrue((out_dir / "summary.json").exists())
            self.assertTrue((out_dir / "restore_only_report.json").exists())
            self.assertGreater(len(list(out_dir.glob("run_*.json"))), 0)
        return summary

    def test_six_valid_probes_hard_stop(self):
        counter = {"n": 0}

        def _probe(request_id: str) -> dict[str, Any]:
            counter["n"] += 1
            return _fake_valid_result(request_id, f"inst-{counter['n']}")

        summary = self._run_harness(_probe, run_count=6, max_attempts=40)
        self.assertEqual(summary["valid_count"], 6)
        self.assertEqual(summary["attempt_count"], 6)
        self.assertTrue(summary["target_reached"])
        # never more than 6 valid probes issued
        self.assertEqual(counter["n"], 6)

    def test_invalid_probes_never_count_and_never_exceed_six_valid(self):
        counter = {"n": 0}

        def _probe(request_id: str) -> dict[str, Any]:
            counter["n"] += 1
            if counter["n"] <= 2:
                # first two probes are invalid (UNET spuriously present)
                return _fake_valid_result(request_id, f"inst-{counter['n']}", unet_present=1)
            return _fake_valid_result(request_id, f"inst-{counter['n']}")

        summary = self._run_harness(_probe, run_count=6, max_attempts=40)
        self.assertEqual(summary["valid_count"], 6)
        self.assertEqual(summary["attempt_count"], 8)
        self.assertEqual(summary["invalid_count"], 2)
        self.assertTrue(summary["target_reached"])
        # exactly 6 valid probes issued, never more
        self.assertEqual(counter["n"], 8)

    def test_dnf_probe_recorded_and_does_not_count(self):
        counter = {"n": 0}

        def _probe(request_id: str) -> dict[str, Any]:
            counter["n"] += 1
            if counter["n"] == 1:
                raise RuntimeError("remote exploded")
            return _fake_valid_result(request_id, f"inst-{counter['n']}")

        summary = self._run_harness(_probe, run_count=6, max_attempts=40)
        self.assertEqual(summary["valid_count"], 6)
        self.assertEqual(summary["dnf_count"], 1)
        self.assertEqual(summary["attempt_count"], 7)
        self.assertTrue(summary["target_reached"])
        self.assertEqual(counter["n"], 7)

    def test_target_unreachable_fails_closed(self):
        counter = {"n": 0}

        def _probe(request_id: str) -> dict[str, Any]:
            counter["n"] += 1
            return _fake_valid_result(request_id, f"inst-{counter['n']}", unet_present=1)

        summary = self._run_harness(_probe, run_count=6, max_attempts=4)
        self.assertEqual(summary["valid_count"], 0)
        self.assertEqual(summary["attempt_count"], 4)
        self.assertFalse(summary["target_reached"])


# ══════════════════════════════════════════════════════════════════════
# Tests: dual-source banner log merge, ns timestamp preference, bounds
# ══════════════════════════════════════════════════════════════════════


class _FakeTaskLog(SimpleNamespace):
    """Stand-in for a Modal ``api_pb2.TaskLogs`` item."""


class TestBannerLogMerge(unittest.TestCase):
    """Pure-helper tests: source tagging, ns preference, merge, bounds."""

    def test_ns_timestamp_preference(self):
        item = _FakeTaskLog(
            timestamp_ns=1_700_000_000_000_500_000,
            timestamp=1_700_000_000.0,
            data=b"hello",
            file_descriptor=1,
        )
        entry = benchmark._restore_only_tasklog_entry(item, fallback_source="stdout")
        self.assertEqual(entry["epoch_ms"], 1_700_000_000_000.5)
        self.assertEqual(entry["timestamp_ns"], 1_700_000_000_000_500_000)
        self.assertEqual(entry["source"], "stdout")

    def test_seconds_fallback_when_ns_absent(self):
        item = _FakeTaskLog(
            timestamp_ns=0,
            timestamp=1_700_000_000.0,
            data=b"restore",
            file_descriptor=3,
        )
        entry = benchmark._restore_only_tasklog_entry(item, fallback_source="stdout")
        self.assertEqual(entry["epoch_ms"], 1_700_000_000_000.0)
        self.assertEqual(entry["source"], "system_info")

    def test_merge_combines_sources_and_sorts_ascending(self):
        info = [
            {"epoch_ms": 2000.0, "text": "b", "source": "system_info", "timestamp_ns": 2000_000_000},
            {"epoch_ms": 1000.0, "text": "a", "source": "system_info", "timestamp_ns": 1000_000_000},
        ]
        stdout = [
            {"epoch_ms": 1500.0, "text": "m", "source": "stdout", "timestamp_ns": 1500_000_000},
        ]
        merged = benchmark._merge_restore_only_entries([info, stdout])
        self.assertEqual([e["epoch_ms"] for e in merged], [1000.0, 1500.0, 2000.0])

    def test_merge_dedupes_and_prefers_system_info_tag(self):
        info = [
            {"epoch_ms": 1000.0, "text": "same", "source": "system_info", "timestamp_ns": 1000_000_000},
        ]
        stdout = [
            {"epoch_ms": 1000.0, "text": "same", "source": "stdout", "timestamp_ns": 1000_000_000},
        ]
        merged = benchmark._merge_restore_only_entries([info, stdout])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source"], "system_info")

    def test_pair_requires_system_source_strictly_preceding_anchor(self):
        # A stdout-tagged banner line is NOT acceptable — only system/INFO is.
        entries = [
            {"epoch_ms": 1000.0, "text": "Restoring Function from memory snapshot.", "source": "stdout", "timestamp_ns": 0},
            {"epoch_ms": 1500.0, "text": "v2.restore_only_probe request_method_entry request_id=req-1", "source": "stdout", "timestamp_ns": 0},
            {"epoch_ms": 2000.0, "text": "Restoring Function from memory snapshot.", "source": "system_info", "timestamp_ns": 0},
            {"epoch_ms": 2500.0, "text": "v2.restore_only_probe request_method_entry request_id=req-2", "source": "stdout", "timestamp_ns": 0},
        ]
        paired = benchmark._pair_restore_only_banner(
            entries, anchor="request_id=req-2",
        )
        self.assertEqual(paired["pair_status"], "paired")
        self.assertEqual(paired["banner_epoch_ms"], 2000.0)
        self.assertEqual(paired["banner_source"], "system_info")

    def test_pair_fails_closed_when_no_system_banner(self):
        entries = [
            {"epoch_ms": 1000.0, "text": "Restoring Function from memory snapshot.", "source": "stdout", "timestamp_ns": 0},
            {"epoch_ms": 1500.0, "text": "v2.restore_only_probe request_method_entry request_id=req-1", "source": "stdout", "timestamp_ns": 0},
        ]
        paired = benchmark._pair_restore_only_banner(
            entries, anchor="request_id=req-1",
        )
        self.assertEqual(paired["pair_status"], "banner_missing")
        self.assertIsNone(paired["banner_epoch_ms"])

    def test_pair_bounds_pass(self):
        entries = [
            {"epoch_ms": 1_000_000_000_000.0, "text": "Restoring Function from memory snapshot.", "source": "system_info", "timestamp_ns": 0},
            {"epoch_ms": 1_000_000_100_000.0, "text": "v2.restore_only_probe request_method_entry request_id=req-1", "source": "stdout", "timestamp_ns": 0},
        ]
        paired = benchmark._pair_restore_only_banner(
            entries, anchor="request_id=req-1",
            dispatch_unix_ms=999_999_900_000,
            remote_python_resume_wall_unix_ns=1_000_000_200_000_000_000,
        )
        self.assertEqual(paired["pair_status"], "paired")
        self.assertEqual(paired["banner_epoch_ms"], 1_000_000_000_000.0)

    def test_pair_bounds_fail_closed_before_dispatch(self):
        entries = [
            {"epoch_ms": 999_000_000_000.0, "text": "Restoring Function from memory snapshot.", "source": "system_info", "timestamp_ns": 0},
            {"epoch_ms": 1_000_000_100_000.0, "text": "v2.restore_only_probe request_method_entry request_id=req-1", "source": "stdout", "timestamp_ns": 0},
        ]
        paired = benchmark._pair_restore_only_banner(
            entries, anchor="request_id=req-1",
            dispatch_unix_ms=1_000_000_000_000,
        )
        self.assertEqual(paired["pair_status"], "bounds_failed")
        self.assertIsNone(paired["banner_epoch_ms"])
        self.assertTrue(paired["bounds_failures"])

    def test_pair_bounds_fail_closed_after_resume(self):
        entries = [
            {"epoch_ms": 1_000_000_000_000.0, "text": "Restoring Function from memory snapshot.", "source": "system_info", "timestamp_ns": 0},
            {"epoch_ms": 1_000_000_100_000.0, "text": "v2.restore_only_probe request_method_entry request_id=req-1", "source": "stdout", "timestamp_ns": 0},
        ]
        paired = benchmark._pair_restore_only_banner(
            entries, anchor="request_id=req-1",
            remote_python_resume_wall_unix_ns=999_999_000_000_000_000,
        )
        self.assertEqual(paired["pair_status"], "bounds_failed")
        self.assertIsNone(paired["banner_epoch_ms"])

    def test_pair_anchor_missing_fails_closed(self):
        entries = [
            {"epoch_ms": 1000.0, "text": "Restoring Function from memory snapshot.", "source": "system_info", "timestamp_ns": 0},
        ]
        paired = benchmark._pair_restore_only_banner(
            entries, anchor="request_id=req-ghost",
        )
        self.assertEqual(paired["pair_status"], "anchor_missing")
        self.assertIsNone(paired["banner_epoch_ms"])

    def test_pair_task_scoped_no_anchor_success(self):
        # Two distinct system banners, no stdout anchor at all: task-scoped
        # pairing must select the LATEST in-bounds exact banner without an
        # anchor, correlated by container_task_id.
        entries = [
            {"epoch_ms": 1000.0, "text": "Restoring Function from memory snapshot.", "source": "system_info", "timestamp_ns": 1_000_000_000_000, "container_id": "c1"},
            {"epoch_ms": 1500.0, "text": "Restoring Function from memory snapshot.", "source": "system_info", "timestamp_ns": 1_500_000_000_000, "container_id": "c1"},
        ]
        paired = benchmark._pair_restore_only_banner(
            entries, anchor="request_id=req-ghost",
            task_scoped=True, container_task_id="ta-abc",
            dispatch_unix_ms=500,
            remote_python_resume_wall_unix_ns=2_000_000_000_000_000_000,
        )
        self.assertEqual(paired["pair_status"], "paired_task_scoped")
        self.assertEqual(paired["correlation"], "ta-abc")
        self.assertEqual(paired["banner_epoch_ms"], 1500.0)
        self.assertEqual(paired["candidate_count"], 2)
        self.assertEqual(paired["bounded_candidate_count"], 2)
        self.assertEqual(paired["distinct_timestamps"], 2)
        self.assertEqual(paired["anchor_found"], False)
        self.assertEqual(paired["banner_container_id"], "c1")
        self.assertIsNone(paired["method_entry_epoch_ms"])

    def test_pair_task_scoped_out_of_bounds_fails(self):
        entries = [
            {"epoch_ms": 1500.0, "text": "Restoring Function from memory snapshot.", "source": "system_info", "timestamp_ns": 0},
        ]
        paired = benchmark._pair_restore_only_banner(
            entries, anchor="request_id=req-1",
            task_scoped=True, container_task_id="ta-abc",
            dispatch_unix_ms=2000,
        )
        self.assertEqual(paired["pair_status"], "task_scoped_bounds_failed")
        self.assertIsNone(paired["banner_epoch_ms"])
        self.assertTrue(paired["bounds_failures"])
        self.assertEqual(paired["candidate_count"], 1)

    def test_pair_task_scoped_no_exact_banner_fails(self):
        # INFO line contains the banner text as a prefix but is not exact.
        entries = [
            {"epoch_ms": 1000.0, "text": "Restoring Function from memory snapshot. (attempt 2)", "source": "system_info", "timestamp_ns": 0},
        ]
        paired = benchmark._pair_restore_only_banner(
            entries, anchor="request_id=req-1",
            task_scoped=True, container_task_id="ta-abc",
        )
        self.assertEqual(paired["pair_status"], "task_scoped_banner_missing")
        self.assertIsNone(paired["banner_epoch_ms"])
        self.assertEqual(paired["candidate_count"], 0)

    def test_pair_task_scoped_indistinguishable_fails(self):
        # Two exact banners with IDENTICAL timestamps are indistinguishable.
        entries = [
            {"epoch_ms": 1500.0, "text": "Restoring Function from memory snapshot.", "source": "system_info", "timestamp_ns": 0},
            {"epoch_ms": 1500.0, "text": "Restoring Function from memory snapshot.", "source": "system_info", "timestamp_ns": 0},
        ]
        paired = benchmark._pair_restore_only_banner(
            entries, anchor="request_id=req-1",
            task_scoped=True, container_task_id="ta-abc",
            dispatch_unix_ms=1000,
            remote_python_resume_wall_unix_ns=2_000_000_000_000_000_000,
        )
        self.assertEqual(paired["pair_status"], "task_scoped_candidates_indistinguishable")
        self.assertIsNone(paired["banner_epoch_ms"])
        self.assertEqual(paired["bounded_candidate_count"], 2)
        self.assertEqual(paired["distinct_timestamps"], 1)

    def test_pair_unscoped_still_requires_anchor(self):
        # Without task scoping the stdout anchor is still mandatory even when
        # an exact system banner is present.
        entries = [
            {"epoch_ms": 1000.0, "text": "Restoring Function from memory snapshot.", "source": "system_info", "timestamp_ns": 0},
        ]
        paired = benchmark._pair_restore_only_banner(
            entries, anchor="request_id=req-ghost",
            task_scoped=False, container_task_id=None,
        )
        self.assertEqual(paired["pair_status"], "anchor_missing")
        self.assertIsNone(paired["banner_epoch_ms"])


class TestBannerFetchDualSource(unittest.TestCase):
    """End-to-end fetch test with ``tail_logs`` mocked (no network)."""

    def _run_fetch(
        self,
        *,
        tail_logs_fake: Any,
        dispatch_ms: Any = None,
        resume_ns: Any = None,
        container_task_id: str | None = None,
        end_unix_ms: int | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        async def _fake_credentials(token_id, token_secret):
            return SimpleNamespace(token_id=token_id)

        async def _fake_resolve(app_name, lookup, client):
            return ("app-1", None, None)

        async def _no_sleep(*args: Any, **kwargs: Any) -> None:
            return None

        calls: list[dict[str, Any]] = []
        with patch("modal.client._Client.from_credentials", side_effect=_fake_credentials), \
             patch("modal.cli.app.resolve_app_identifier", side_effect=_fake_resolve), \
             patch("modal._logs.tail_logs", new=tail_logs_fake), \
             patch("asyncio.sleep", new=_no_sleep):
            result = asyncio.run(benchmark._fetch_restore_only_banner_timing(
                {"token_id": "t", "token_secret": "s"}, "app", "req-1",
                dispatch_unix_ms=dispatch_ms,
                remote_python_resume_wall_unix_ns=resume_ns,
                container_task_id=container_task_id,
                end_unix_ms=end_unix_ms,
            ))
            calls = tail_logs_fake.calls
            return result, calls

    @staticmethod
    def _recording_tail_logs(lines: list[tuple[Any, Any, Any, int, str]]) -> Any:
        """Build a recording async-gen tail_logs fake.

        Lines are ``(timestamp_ns, timestamp, data, file_descriptor, task_id)``.
        The default stream (source UNSPECIFIED) never sees system/INFO lines,
        reproducing the observed platform-banner visibility bug; the INFO
        stream returns only INFO lines.  ``search_text``/``task_id`` filters
        are honoured server-side so the task-scoped queries return the exact
        anchor/banner lines.  Recorded calls are exposed via ``fake.calls``.
        """
        async def _fake(
            client: Any, app_id: str, n: int,
            *, since: Any = None, until: Any = None, filters: Any = None,
        ) -> Any:
            src = getattr(filters, "source", 0) if filters is not None else 0
            st = getattr(filters, "search_text", "") if filters is not None else ""
            tid = getattr(filters, "task_id", "") if filters is not None else ""
            _fake.calls.append({
                "n": n, "since": since, "until": until,
                "source": src, "task_id": tid, "search_text": st,
            })
            items = []
            for (ts_ns, ts, data, fd, task_id) in lines:
                if src == 3:
                    if fd != 3:
                        continue
                elif fd == 3:
                    continue
                text = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
                if st and st not in text:
                    continue
                if tid and task_id != tid:
                    continue
                items.append(_FakeTaskLog(
                    timestamp_ns=ts_ns, timestamp=ts, data=data, file_descriptor=fd,
                ))
            yield SimpleNamespace(items=items)

        _fake.calls = []
        return _fake

    def test_fetch_uses_exact_task_scoped_filters(self):
        lines = [
            (1_700_000_000_000_000_000, 1_700_000_000.0, b"Restoring Function from memory snapshot.", 3, "task-42"),
            (1_700_000_001_000_000_000, 1_700_000_001.0, b"v2.restore_only_probe request_method_entry request_id=req-1", 1, "task-42"),
        ]
        fake = self._recording_tail_logs(lines)
        result, calls = self._run_fetch(
            tail_logs_fake=fake,
            dispatch_ms=1_699_999_800_000,
            resume_ns=1_700_000_002_000_000_000,
            container_task_id="task-42",
        )
        # Task-scoped INFO banner is direct evidence: no stdout anchor needed.
        self.assertEqual(result["pair_status"], "paired_task_scoped")
        self.assertEqual(result["correlation"], "task-42")
        self.assertEqual(result["anchor_found"], True)
        self.assertEqual(result["banner_scope"], "task_scoped")
        self.assertEqual(result["container_task_id_scoped"], 1)
        self.assertEqual(result["container_task_id_used"], "task-42")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["banner_container_id"], "")
        # Exactly two queries: task-scoped anchor + task-scoped INFO banner.
        self.assertEqual(len(calls), 2)
        anchor_query = calls[0]
        self.assertEqual(anchor_query["source"], 0)
        self.assertEqual(anchor_query["task_id"], "task-42")
        self.assertIn("request_id=req-1", anchor_query["search_text"])
        banner_query = calls[1]
        self.assertEqual(banner_query["source"], 3)
        self.assertEqual(banner_query["task_id"], "task-42")
        self.assertEqual(banner_query["search_text"], benchmark.RESTORE_ONLY_RESTORING_BANNER)

    def test_fetch_task_scoped_no_anchor_success(self):
        # Reproduces the observed backfill scenario: the task-scoped stdout
        # anchor query returns nothing (historical anchor not retained), but
        # the task-scoped INFO query returns exact system banners correlated
        # to the same container_task_id.  Pairing must succeed WITHOUT anchor.
        lines = [
            (1_700_000_000_000_000_000, 1_700_000_000.0, b"Restoring Function from memory snapshot.", 3, "ta-abc"),
            (1_700_000_001_000_000_000, 1_700_000_001.0, b"Restoring Function from memory snapshot.", 3, "ta-abc"),
            (1_700_000_001_500_000_000, 1_700_000_001.0, b"v2.restore_only_probe request_method_entry request_id=req-1", 1, "task-other"),
        ]
        fake = self._recording_tail_logs(lines)
        result, calls = self._run_fetch(
            tail_logs_fake=fake,
            dispatch_ms=1_699_999_800_000,
            resume_ns=1_700_000_002_000_000_000,
            container_task_id="ta-abc",
        )
        # Anchor query (task ta-abc) returns nothing; INFO query returns 2
        # exact banners at distinct timestamps -> latest in-bounds wins.
        self.assertEqual(result["pair_status"], "paired_task_scoped")
        self.assertEqual(result["correlation"], "ta-abc")
        self.assertEqual(result["anchor_found"], False)
        self.assertEqual(result["banner_scope"], "task_scoped")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["bounded_candidate_count"], 2)
        self.assertEqual(result["distinct_timestamps"], 2)
        self.assertEqual(result["banner_epoch_ms"], 1_700_000_001_000.0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["task_id"], "ta-abc")

    def test_fetch_task_scoped_out_of_bounds_fails(self):
        lines = [
            (1_700_000_002_000_000_000, 1_700_000_002.0, b"Restoring Function from memory snapshot.", 3, "ta-abc"),
            (1_700_000_001_500_000_000, 1_700_000_001.0, b"v2.restore_only_probe request_method_entry request_id=req-1", 1, "task-other"),
        ]
        fake = self._recording_tail_logs(lines)
        result, _ = self._run_fetch(
            tail_logs_fake=fake,
            dispatch_ms=1_699_999_800_000,
            resume_ns=1_700_000_001_000_000_000,
            container_task_id="ta-abc",
        )
        self.assertEqual(result["pair_status"], "task_scoped_bounds_failed")
        self.assertIsNone(result["banner_epoch_ms"])
        self.assertEqual(result["candidate_count"], 1)
        self.assertTrue(result["bounds_failures"])

    def test_fetch_scoped_fallback_unscoped_when_task_banner_missing(self):
        # The banner belongs to a different task (task-7); the task-scoped
        # INFO query returns nothing, so the bounded fallback re-queries INFO
        # with the same tight window + banner search_text, no task filter.
        lines = [
            (1_700_000_000_000_000_000, 1_700_000_000.0, b"Restoring Function from memory snapshot.", 3, "task-7"),
            (1_700_000_001_000_000_000, 1_700_000_001.0, b"v2.restore_only_probe request_method_entry request_id=req-1", 1, "task-42"),
        ]
        fake = self._recording_tail_logs(lines)
        result, calls = self._run_fetch(
            tail_logs_fake=fake,
            dispatch_ms=1_699_999_800_000,
            resume_ns=1_700_000_002_000_000_000,
            container_task_id="task-42",
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1]["source"], 3)
        self.assertEqual(calls[1]["task_id"], "task-42")
        fallback = calls[2]
        self.assertEqual(fallback["source"], 3)
        self.assertEqual(fallback["task_id"], "")
        self.assertEqual(fallback["search_text"], benchmark.RESTORE_ONLY_RESTORING_BANNER)
        self.assertEqual(result["banner_scope"], "fallback_unscoped")
        self.assertEqual(result["pair_status"], "paired")
        self.assertEqual(result["banner_epoch_ms"], 1_700_000_000_000.0)

    def test_fetch_tight_until_from_resume(self):
        lines = [
            (1_700_000_000_000_000_000, 1_700_000_000.0, b"Restoring Function from memory snapshot.", 3, "task-1"),
            (1_700_000_001_000_000_000, 1_700_000_001.0, b"v2.restore_only_probe request_method_entry request_id=req-1", 1, "task-1"),
        ]
        fake = self._recording_tail_logs(lines)
        result, calls = self._run_fetch(
            tail_logs_fake=fake,
            dispatch_ms=1_699_999_800_000,
            resume_ns=1_700_000_002_000_000_000,
        )
        self.assertEqual(result["pair_status"], "paired")
        query = calls[0]
        self.assertEqual(
            query["since"],
            datetime.fromtimestamp(1_699_999_800_000 / 1000.0 - 120.0, tz=timezone.utc),
        )
        self.assertEqual(
            query["until"],
            datetime.fromtimestamp(
                (1_700_000_002_000_000_000 / 1_000_000.0 + 120_000.0) / 1000.0,
                tz=timezone.utc,
            ),
        )

    def test_fetch_tight_until_from_artifact_end(self):
        lines = [
            (1_700_000_000_000_000_000, 1_700_000_000.0, b"Restoring Function from memory snapshot.", 3, "task-1"),
            (1_700_000_001_000_000_000, 1_700_000_001.0, b"v2.restore_only_probe request_method_entry request_id=req-1", 1, "task-1"),
        ]
        fake = self._recording_tail_logs(lines)
        result, calls = self._run_fetch(
            tail_logs_fake=fake,
            dispatch_ms=1_699_999_800_000,
            end_unix_ms=1_700_000_005_000,
        )
        self.assertEqual(result["pair_status"], "paired")
        self.assertEqual(
            calls[0]["until"],
            datetime.fromtimestamp((1_700_000_005_000 + 120_000.0) / 1000.0, tz=timezone.utc),
        )

    def test_fetch_merges_dual_sources_and_pairs(self):
        # ts_ns values chosen so ns/1e6 lands on exactly-representable ms.
        lines = [
            (1_700_000_000_000_000_000, 1_700_000_000.0, b"Restoring Function from memory snapshot.", 3, "task-1"),
            (1_700_000_001_000_000_000, 1_700_000_001.0, b"v2.restore_only_probe request_method_entry request_id=req-1", 1, "task-1"),
        ]
        fake = self._recording_tail_logs(lines)
        result, calls = self._run_fetch(
            tail_logs_fake=fake,
            dispatch_ms=1_699_999_800_000,
            resume_ns=1_700_000_002_000_000_000,
        )
        self.assertEqual(result["pair_status"], "paired")
        self.assertEqual(result["banner_epoch_ms"], 1_700_000_000_000.0)
        self.assertEqual(result["banner_source"], "system_info")
        self.assertEqual(result["method_entry_epoch_ms"], 1_700_000_001_000.0)
        self.assertEqual(result["sources_fetched"], ["system_info", "stdout"])
        self.assertEqual(result["entry_count"], 2)
        # Legacy path (no task id): 2 queries, INFO-only banner stream.
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["source"], 3)

    def test_fetch_ns_preference_over_seconds(self):
        # timestamp_ns says 2000_000_000_000.0ms but timestamp (seconds)
        # would imply 1000_000_000_000.0ms — ns must win.
        lines = [
            (2_000_000_000_000_000_000, 1_000_000_000.0, b"Restoring Function from memory snapshot.", 3, "task-1"),
            (2_000_000_001_000_000_000, 1_000_000_001.0, b"v2.restore_only_probe request_method_entry request_id=req-1", 1, "task-1"),
        ]
        fake = self._recording_tail_logs(lines)
        result, _ = self._run_fetch(
            tail_logs_fake=fake,
            dispatch_ms=1_999_000_000_000,
            resume_ns=2_000_000_002_000_000_000,
        )
        self.assertEqual(result["pair_status"], "paired")
        self.assertEqual(result["banner_epoch_ms"], 2_000_000_000_000.0)

    def test_fetch_fails_closed_on_bounds_violation(self):
        # System banner is AFTER the container-observed python resume.
        lines = [
            (1_700_000_000_000_000_000, 1_700_000_000.0, b"Restoring Function from memory snapshot.", 3, "task-1"),
            (1_700_000_001_000_000_000, 1_700_000_001.0, b"v2.restore_only_probe request_method_entry request_id=req-1", 1, "task-1"),
        ]
        fake = self._recording_tail_logs(lines)
        result, _ = self._run_fetch(
            tail_logs_fake=fake,
            dispatch_ms=1_699_999_800_000,
            resume_ns=1_699_999_900_000_000_000,
        )
        self.assertEqual(result["pair_status"], "bounds_failed")
        self.assertIsNone(result["banner_epoch_ms"])
        self.assertTrue(result["bounds_failures"])

    def test_fetch_fails_closed_without_system_banner(self):
        lines = [
            (1_700_000_001_000_000_000, 1_700_000_001.0, b"v2.restore_only_probe request_method_entry request_id=req-1", 1, "task-1"),
        ]
        fake = self._recording_tail_logs(lines)
        result, _ = self._run_fetch(tail_logs_fake=fake)
        self.assertEqual(result["pair_status"], "banner_missing")
        self.assertIsNone(result["banner_epoch_ms"])


# ══════════════════════════════════════════════════════════════════════
# Tests: restore-only BACKFILL (report-only, log retrieval, no probes)
# ══════════════════════════════════════════════════════════════════════


def _fake_backfill_artifact(index: int) -> dict[str, Any]:
    """A valid restore-only artifact missing ONLY the platform banner."""
    resume_ns = 1_700_000_000_000_000_000 + index * 100_000_000
    request_id = f"v2-restore-only-{index}-req1234"
    result = _fake_valid_result(request_id, f"inst-backfill-{index}")
    result["restore_timing"]["remote_python_resume_wall_unix_ns"] = resume_ns
    result["identity"]["container_task_id"] = f"task-{index}"
    return {
        "run_index": index,
        "run_id": f"restore-only-{index}-abc",
        "request_id": request_id,
        "mode": "snapshot_restore_only",
        "dispatch_unix_ms": 1_699_999_800_000 + index * 60_000,
        "dispatch_iso": "2026-08-11T20:00:00+00:00",
        "start_ts": "2026-08-11T20:00:00+00:00",
        "end_ts": "2026-08-11T20:00:05+00:00",
        "target": {
            "app_name": "stable-modal-comfy-v2-restore-only-shadow",
            "class_name": "ModalRuntimeEntrypointV2",
            "gpu": "rtx-pro-6000",
        },
        "config": {
            "target_valid": 6,
            "max_attempts": 40,
            "gap_seconds": 30,
            "snapshot_exclude_unet": 1,
            "evict_retain_role": "clip_vae",
        },
        "identity": result["identity"],
        "cold_check": {"cold": True, "failures": [], "cold_valid": True, "freshness_checked": True},
        "cold_gate_available": True,
        "banner": {},
        "banner_epoch_ms": None,
        "result": result,
        "valid": False,
        "dnf": False,
        "failures": ["banner_epoch_ms missing (pre-fix system-log source bug)"],
        "error": None,
    }


class TestRestoreOnlyBackfill(unittest.TestCase):
    def _write_run_dir(self, count: int = 30) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="ro_backfill_"))
        for i in range(count):
            (tmp / f"run_{i}.json").write_text(
                json.dumps(_fake_backfill_artifact(i), default=str), encoding="utf-8",
            )
        return tmp

    def _run_backfill(self, source_dir: Path, *, limit: int = 6, fetch_side: Any = None) -> dict[str, Any]:
        async def _fake_fetch(workspace: Any, app_name: str, request_id: str, **kwargs: Any) -> dict[str, Any]:
            if fetch_side is not None:
                return fetch_side(request_id, kwargs)
            resume_ns = kwargs.get("remote_python_resume_wall_unix_ns")
            return {
                "banner_epoch_ms": ((resume_ns or 1_700_000_000_000_000_000) / 1_000_000.0) - 2000.0,
                "banner_log_line": "Restoring Function from memory snapshot.",
                "banner_source": "system_info",
                "method_entry_epoch_ms": ((resume_ns or 0) / 1_000_000.0) + 1000.0,
                "pair_status": "paired",
                "bounds_checked": True,
            }

        with patch.object(benchmark, "_fetch_restore_only_banner_timing", new=_fake_fetch):
            return asyncio.run(benchmark._backfill_snapshot_restore_only(
                {"token_id": "t", "token_secret": "s"}, source_dir, limit=limit,
            ))

    def test_backfill_exact_first_six_and_overrun_disclosure(self):
        source_dir = self._write_run_dir(30)
        summary = self._run_backfill(source_dir)
        self.assertEqual(summary["source_attempt_count"], 30)
        self.assertEqual(summary["selected_attempts"], [0, 1, 2, 3, 4, 5])
        self.assertEqual(
            summary["excluded_instrumentation_overrun_attempts"], list(range(6, 30)),
        )
        self.assertEqual(summary["valid_count"], 6)
        self.assertEqual(summary["attempt_count"], 6)
        self.assertEqual(len(summary["runs"]), 6)
        self.assertTrue(summary["target_reached"])
        note = summary["meta"]["protocol_note"]
        self.assertIn("system/INFO", note)
        self.assertIn("instrumentation overrun", note)
        self.assertIn("never substituted", note)
        # exactly six backfilled artifacts written; originals preserved.
        for i in range(6):
            self.assertTrue((source_dir / f"backfilled_run_{i}.json").is_file())
            self.assertTrue((source_dir / f"run_{i}.json").is_file())
        self.assertTrue((source_dir / "backfilled_summary.json").is_file())
        self.assertTrue((source_dir / "backfilled_restore_only_report.json").is_file())
        # distribution/cohort machine-readable data present.
        self.assertIn("pre_python_restore_ms", summary["distribution"])
        self.assertEqual(summary["cohort"]["source_attempt_count"], 30)

    def test_backfill_no_remote_invocation_and_raw_preserved(self):
        source_dir = self._write_run_dir(30)
        raw_before = (source_dir / "run_0.json").read_text(encoding="utf-8")
        with patch.object(
            benchmark, "ModalTransport",
            side_effect=AssertionError("backfill must never create ModalTransport"),
        ):
            summary = self._run_backfill(source_dir)
        self.assertEqual(summary["valid_count"], 6)
        self.assertEqual(summary["meta"]["no_remote_invocation"], True)
        # Raw evidence untouched; separate backfilled copies written.
        self.assertEqual((source_dir / "run_0.json").read_text(encoding="utf-8"), raw_before)
        backfilled = json.loads((source_dir / "backfilled_run_0.json").read_text(encoding="utf-8"))
        self.assertTrue(backfilled["backfilled"])
        self.assertEqual(backfilled["backfill_source_file"], "run_0.json")
        self.assertEqual(backfilled["banner"]["banner_source"], "system_info")
        self.assertTrue(backfilled["valid"])

    def test_backfill_fails_without_substitution(self):
        source_dir = self._write_run_dir(30)

        def _fetch_side(request_id: str, kwargs: dict[str, Any]) -> dict[str, Any]:
            if "restore-only-2-" in request_id:
                return {"banner_epoch_ms": None, "pair_status": "banner_missing", "anchor_found": True}
            return {
                "banner_epoch_ms": (kwargs["remote_python_resume_wall_unix_ns"] / 1_000_000.0) - 2000.0,
                "banner_source": "system_info",
                "pair_status": "paired",
            }

        calls: list[str] = []

        async def _fetch_tracker(workspace: Any, app_name: str, request_id: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(request_id)
            return _fetch_side(request_id, kwargs)

        with patch.object(benchmark, "_fetch_restore_only_banner_timing", new=_fetch_tracker):
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(benchmark._backfill_snapshot_restore_only(
                    {"token_id": "t", "token_secret": "s"}, source_dir, limit=6,
                ))
        self.assertIn("attempt 2", str(ctx.exception))
        # Only the first three attempts were fetched — never a later substitute.
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("restore-only-3-" not in c for c in calls))
        # Failure diagnostics persisted separately for inspection BEFORE the
        # raise, and no backfilled file was written for the failed attempt.
        diag = json.loads((source_dir / "backfill_failure_attempt_2.json").read_text(encoding="utf-8"))
        self.assertEqual(diag["run_index"], 2)
        self.assertIn("banner_epoch_ms missing", "; ".join(diag["failures"]))
        self.assertIsNotNone(diag["banner"])
        self.assertFalse((source_dir / "backfilled_run_2.json").exists())

    def test_backfill_passes_task_scoped_context(self):
        source_dir = self._write_run_dir(30)
        seen: list[tuple[str, dict[str, Any]]] = []

        async def _fetch_tracker(workspace: Any, app_name: str, request_id: str, **kwargs: Any) -> dict[str, Any]:
            seen.append((request_id, kwargs))
            resume_ns = kwargs.get("remote_python_resume_wall_unix_ns")
            return {
                "banner_epoch_ms": ((resume_ns or 1_700_000_000_000_000_000) / 1_000_000.0) - 2000.0,
                "banner_source": "system_info",
                "pair_status": "paired",
            }

        with patch.object(benchmark, "_fetch_restore_only_banner_timing", new=_fetch_tracker):
            summary = asyncio.run(benchmark._backfill_snapshot_restore_only(
                {"token_id": "t", "token_secret": "s"}, source_dir, limit=6,
            ))
        self.assertEqual(summary["valid_count"], 6)
        self.assertEqual(len(seen), 6)
        for i, (req_id, kwargs) in enumerate(seen):
            self.assertIn(f"restore-only-{i}-", req_id)
            self.assertEqual(kwargs["container_task_id"], f"task-{i}")
            self.assertIsNotNone(kwargs["remote_python_resume_wall_unix_ns"])
            self.assertIsNotNone(kwargs["dispatch_unix_ms"])
            # end_unix_ms derived from the artifact's end_ts.
            self.assertIsNotNone(kwargs["end_unix_ms"])
            self.assertGreater(kwargs["end_unix_ms"], 0)

    def test_backfill_requires_at_least_limit_attempts(self):
        source_dir = self._write_run_dir(5)
        with self.assertRaises(RuntimeError) as ctx:
            self._run_backfill(source_dir)
        self.assertIn("at least 6 source attempts", str(ctx.exception))

    def test_backfill_requires_exact_first_indices(self):
        source_dir = self._write_run_dir(30)
        (source_dir / "run_3.json").unlink()
        with self.assertRaises(RuntimeError) as ctx:
            self._run_backfill(source_dir)
        self.assertIn("exactly [0..5]", str(ctx.exception))

    def test_backfill_main_branch_wires_and_exits_nonzero_on_partial(self):
        source_dir = self._write_run_dir(30)

        async def _fake_fetch(workspace: Any, app_name: str, request_id: str, **kwargs: Any) -> dict[str, Any]:
            if "restore-only-2-" in request_id:
                return {"banner_epoch_ms": None, "pair_status": "banner_missing", "anchor_found": True}
            return {
                "banner_epoch_ms": (kwargs["remote_python_resume_wall_unix_ns"] / 1_000_000.0) - 2000.0,
                "banner_source": "system_info",
                "pair_status": "paired",
            }

        with patch.object(benchmark, "_load_workspace", return_value={"token_id": "t", "token_secret": "s"}), \
             patch.object(benchmark, "_fetch_restore_only_banner_timing", new=_fake_fetch):
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(benchmark.main(snapshot_restore_only_backfill=str(source_dir)))
        self.assertIn("restore-only backfill FAILED", str(ctx.exception))


# ══════════════════════════════════════════════════════════════════════
# Tests: mode wiring in the .bat scripts
# ══════════════════════════════════════════════════════════════════════


class TestBatWiring(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def _bat_text(self, name: str) -> str:
        return (self.ROOT / name).read_text(encoding="utf-8", errors="replace")

    def test_deploy_script_has_restore_only_mode_and_identity_gate(self):
        text = self._bat_text("deploy_and_run_v2_single.bat")
        self.assertIn("snapshot_restore_only", text)
        self.assertIn("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1", text)
        self.assertIn(
            "stable-modal-comfy-v2-restore-only-shadow", text,
        )
        # deploy invocation is labeled/excluded and issues NO probes
        self.assertIn("labeled/excluded", text)
        self.assertIn("issues NO reuse probes", text)

    def test_deploy_script_evicts_unet_with_clip_vae_retention(self):
        text = self._bat_text("deploy_and_run_v2_single.bat")
        self.assertIn("COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1", text)
        self.assertIn("COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae", text)
        self.assertIn("COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0", text)
        # inherit profile, never production, for the restore-only arm
        self.assertIn("COMFYMODAL_V2_ENV_PROFILE=inherit", text)

    def test_run_script_has_restore_only_mode_and_identity_gate(self):
        text = self._bat_text("run_v2_single.bat")
        self.assertIn("snapshot_restore_only", text)
        self.assertIn("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1", text)
        self.assertIn("--snapshot-restore-only", text)
        self.assertIn("V2_RESTORE_ONLY_RUN_COUNT", text)

    def test_run_script_evicts_unet_with_clip_vae_retention(self):
        text = self._bat_text("run_v2_single.bat")
        self.assertIn("COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1", text)
        self.assertIn("COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae", text)
        self.assertIn("COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0", text)
        self.assertIn("COMFYMODAL_V2_ENV_PROFILE=inherit", text)

    def test_harness_constants_defaults(self):
        self.assertEqual(benchmark.RESTORE_ONLY_MODE, "snapshot_restore_only")
        self.assertEqual(benchmark.RESTORE_ONLY_RUN_COUNT, 6)
        self.assertEqual(
            benchmark.RESTORE_ONLY_APP_NAME,
            "stable-modal-comfy-v2-restore-only-shadow",
        )
        self.assertIn(
            "Restoring Function from memory snapshot.",
            benchmark.RESTORE_ONLY_RESTORING_BANNER,
        )


if __name__ == "__main__":
    unittest.main()
