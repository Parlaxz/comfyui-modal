"""Offline tests for the C9 fastsafetensors UNET integration
(``comfymodal_runtime.unet_fastsafetensors`` + the ``_load_unet`` branch).

Covers the required contract items without any Modal run / GPU: flag
semantics, ZImage-only eligibility, meta construction + sampling repair,
assign=True zero-copy semantics, residual-meta sweep, owner lifetime,
fallback-once contract, no-native-replay-after-success, telemetry
single-event contract, memory JSON-safety, and branch ordering.  The real
CUDA ownership micro-test runs in the structural gate on the first valid
container (unet_qd_probe ``loader_ownership`` section).

NOTE: ``unet_fastsafetensors`` imports its helpers from ``model_preload``
into its OWN namespace, so tests patch attributes on the ``fs`` module (the
branch flag gates ``mp._fs_pipeline_enabled`` etc. are the exception —
those are module-level lookups inside ``_load_unet``).
"""

from __future__ import annotations

import gc
import json
import os
import sys
import tempfile
import types
import unittest
import weakref
from pathlib import Path

import torch

import comfymodal_runtime.model_preload as mp
import comfymodal_runtime.unet_fastsafetensors as fs

try:
    import safetensors.torch as _st_torch
    _HAS_SAFETENSORS = True
except Exception:  # pragma: no cover
    _HAS_SAFETENSORS = False

_REQUIRED = unittest.skipUnless(_HAS_SAFETENSORS, "safetensors unavailable")


class _TinyModule(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.diffusion_model = torch.nn.Linear(8, 4, dtype=torch.bfloat16)
        self.diffusion_model.register_buffer(
            "scale", torch.zeros(4, dtype=torch.bfloat16))


class ZImage:
    """Fake ZImage model_config.  The CLASS NAME is what the production
    family gate checks (``type(config).__name__ == "ZImage"`` — mirroring
    comfy.model_detection's config classes)."""

    def __init__(self):
        self.supported_inference_dtypes = [torch.bfloat16, torch.float16, torch.float32]

    @staticmethod
    def get_model(meta_sd, prefix):
        with torch.no_grad(), torch.device("meta"):
            return _TinyModule()

    @staticmethod
    def process_unet_state_dict(sd):
        return dict(sd)

    def set_inference_dtype(self, *a, **k):
        pass


class Lumina2(ZImage):
    """Fake non-ZImage family (excluded by the eligibility gate)."""


def _tiny_header():
    # Unprefixed keys: the ZImage file header keys map directly onto the
    # diffusion_model's named parameters (mirrors the real file).
    return {
        "__metadata__": {},
        "weight": {"dtype": "BF16", "shape": [4, 8],
                   "data_offsets": [0, 64]},
        "bias": {"dtype": "BF16", "shape": [4],
                 "data_offsets": [64, 72]},
        "scale": {"dtype": "BF16", "shape": [4],
                  "data_offsets": [72, 80]},
    }


def _tiny_sd():
    return {
        "weight": torch.arange(32, dtype=torch.bfloat16).view(4, 8),
        "bias": torch.arange(4, dtype=torch.bfloat16),
        "scale": torch.tensor([1.0, 2.0, 3.0, 4.0],
                              dtype=torch.bfloat16),
    }


@_REQUIRED
def _write_tiny_file(path: str) -> dict:
    _st_torch.save_file(_tiny_sd(), path)
    return _tiny_header()


class _FakeFB:
    def __init__(self, tensors):
        self._t = tensors
        self.closed = False
        self.close_calls = 0

    def get_tensor(self, k):
        return self._t[k]

    def close(self):
        self.close_calls += 1
        self.closed = True


class _FakeFSTLoader:
    def __init__(self, tensors):
        self._tensors = tensors
        self.closed = False
        self.close_calls = 0

    def add_filenames(self, mapping):
        pass

    def copy_files_to_device(self, **kwargs):
        return _FakeFB(self._tensors)

    def get_keys(self):
        return list(self._tensors)

    def close(self):
        self.close_calls += 1
        self.closed = True


def _fake_fst_module(tensors):
    _mod = types.ModuleType("fastsafetensors")
    _mod.__version__ = "0.3.3-fake"
    _mod.SafeTensorsFileLoader = lambda *a, **k: _FakeFSTLoader(tensors)
    return _mod


class _FakePatcher:
    def __init__(self, model, load_device=None, offload_device=None):
        self.model = model
        self.load_device = load_device
        self.offload_device = offload_device


class _FakeTrace:
    def __init__(self):
        self.events = []

    def emit(self, name, phase=None, metadata=None):
        self.events.append((name, phase, dict(metadata or {})))


class _FakeLaneCtx:
    """Stand-in for the model_preload _ACTIVE_LANE_TRACE ContextVar: get()
    returns a lane object exposing ``_trace`` (the pipeline's trace
    resolution path)."""

    def __init__(self, trace):
        self._trace = trace

    def get(self):
        _lane = types.SimpleNamespace(_trace=self._trace)
        return _lane


class _Patch:
    """Context manager patching attributes on a module."""

    def __init__(self, module, **kw):
        self._mod = module
        self._kw = kw
        self._saved = {}

    def __enter__(self):
        for k, v in self._kw.items():
            self._saved[k] = getattr(self._mod, k, None)
            setattr(self._mod, k, v)
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is None:
                if hasattr(self._mod, k):
                    delattr(self._mod, k)
            else:
                setattr(self._mod, k, v)
        return False


def _env_flag(name, value):
    _saved = os.environ.get(name)
    os.environ[name] = value

    def _restore():
        if _saved is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = _saved

    return _restore


def _c6_fake(patcher_cls=_FakePatcher, target=None):
    """Fake comfy function dispatcher for the fs module's _c6_comfy_fn."""
    if target is None:
        target = torch.device("cpu")

    def _dispatch(module_name, attr, fallback=None):
        if attr == "ModelPatcher":
            return patcher_cls
        if attr == "get_torch_device":
            return lambda: target
        if attr == "unet_offload_device":
            return lambda: torch.device("cpu")
        return fallback

    return _dispatch


def _fs_common_patches(path, header, config, tensors, target=torch.device("cpu"),
                       expected_params=40, expected_bytes=80, threshold_ms=500.0):
    """The full set of fs-module patches needed for a pipeline run."""
    _fake_mod = _fake_fst_module(tensors)
    return {
        "_fs_fast_module": lambda: _fake_mod,
        "_fs_cuda_available": lambda: True,
        "_fs_get_target": lambda: target,
        "_fs_get_offload": lambda: torch.device("cpu"),
        "_ring_resolve_unet_path": lambda n, l: path,
        "_ring_derive_config": lambda p, _probe_wall=None: (
            config, {}, header, 2, ""),
        "_c6_value_probe_allow_fp16": lambda p, h, n: True,
        "_fast_disk_high_vram": lambda: True,
        "_fast_disk_torch_future_enabled": lambda: False,
        "_fast_disk_model_config_evidence": lambda config: {},
        "_c6_comfy_fn": _c6_fake(),
        "_FS_EXPECTED_PARAM_COUNT": expected_params,
        "_FS_EXPECTED_TOTAL_BYTES": expected_bytes,
        "_FS_FINAL_TO_DUPLICATE_THRESHOLD_MS": threshold_ms,
    }


class FlagSemanticsTests(unittest.TestCase):
    def test_flag_off_zero_new_path(self):
        for _v in ("", "0", "false", "off", "none"):
            _r = _env_flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", _v)
            try:
                self.assertEqual(mp._fs_flag_value(), "off")
                self.assertFalse(mp._fs_pipeline_enabled())
            finally:
                _r()
        # Historical flags remain untouched by the fs flag.
        _r1 = _env_flag("COMFYMODAL_V2_UNET_PINNED_RING", "1")
        _r2 = _env_flag("COMFYMODAL_V2_UNET_META_DIRECT", "1")
        _r3 = _env_flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "0")
        try:
            self.assertTrue(mp._ring_pipeline_enabled())
            self.assertTrue(mp._md_pipeline_enabled())
            self.assertFalse(mp._fs_pipeline_enabled())
        finally:
            _r1()
            _r2()
            _r3()

    def test_flag_on(self):
        _r = _env_flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "1")
        try:
            self.assertEqual(mp._fs_flag_value(), "on")
            self.assertTrue(mp._fs_pipeline_enabled())
        finally:
            _r()

    def test_flag_invalid_fail_closed(self):
        _r = _env_flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "banana")
        try:
            self.assertEqual(mp._fs_flag_value(), "invalid")
            self.assertFalse(mp._fs_pipeline_enabled())
        finally:
            _r()


class EligibilityTests(unittest.TestCase):
    def test_family_gate(self):
        with tempfile.TemporaryDirectory() as td:
            _path = str(Path(td) / "t.safetensors")
            _write_tiny_file(_path)

            class _OtherConfig(ZImage):
                name = "Lumina2"

            with _Patch(fs, **_fs_common_patches(
                    _path, _tiny_header(), _OtherConfig(), _tiny_sd())):
                _ok, _reason = fs._fs_eligible(
                    None, {"unet_name": "t.safetensors", "weight_dtype": "default"},
                    None)
                self.assertFalse(_ok)
                self.assertEqual(_reason, "family_not_zimage")

    def test_zimage_eligible(self):
        with tempfile.TemporaryDirectory() as td:
            _path = str(Path(td) / "t.safetensors")
            _write_tiny_file(_path)
            with _Patch(fs, **_fs_common_patches(
                    _path, _tiny_header(), ZImage(), _tiny_sd())):
                _ok, _reason = fs._fs_eligible(
                    None, {"unet_name": "t.safetensors", "weight_dtype": "default"},
                    None)
                self.assertTrue(_ok, _reason)

    def test_not_high_vram_ineligible(self):
        with tempfile.TemporaryDirectory() as td:
            _path = str(Path(td) / "t.safetensors")
            _write_tiny_file(_path)
            _kw = _fs_common_patches(_path, _tiny_header(), ZImage(), _tiny_sd())
            _kw["_fast_disk_high_vram"] = lambda: False
            with _Patch(fs, **_kw):
                _ok, _reason = fs._fs_eligible(
                    None, {"unet_name": "t.safetensors"}, None)
                self.assertFalse(_ok)
                self.assertEqual(_reason, "not_high_vram")

    def test_import_unavailable_ineligible(self):
        with tempfile.TemporaryDirectory() as td:
            _path = str(Path(td) / "t.safetensors")
            _write_tiny_file(_path)
            _kw = _fs_common_patches(_path, _tiny_header(), ZImage(), _tiny_sd())
            _kw["_fs_fast_module"] = lambda: None
            with _Patch(fs, **_kw):
                _ok, _reason = fs._fs_eligible(
                    None, {"unet_name": "t.safetensors"}, None)
                self.assertFalse(_ok)
                self.assertEqual(_reason, "fastsafetensors_unavailable")


class MetaConstructionTests(unittest.TestCase):
    def test_meta_construction_all_meta(self):
        _metrics = {}
        _model = fs._fs_meta_construct(ZImage(), {}, _metrics)
        _params = list(_model.parameters())
        self.assertTrue(_params)
        self.assertTrue(all(_p.device.type == "meta" for _p in _params))
        self.assertIn("meta_get_model_wall_ms", _metrics)

    def test_sampling_repair(self):
        _metrics = {}

        class _PoisonedConfig(ZImage):
            @staticmethod
            def get_model(meta_sd, prefix):
                with torch.no_grad(), torch.device("meta"):
                    _m = _TinyModule()
                _m.model_sampling = torch.nn.Module()
                # Registered buffer: collect_meta_tensors walks buffers (a
                # plain tensor attribute would be invisible to the walker).
                _m.model_sampling.register_buffer(
                    "sigma", torch.empty(4, device="meta"))
                _m.model_config = object()
                _m.model_type = "zimage"
                return _m

        def _rebuild(*a, **k):
            _m = torch.nn.Module()
            _m.register_buffer("sigma", torch.zeros(4))
            return _m

        with _Patch(fs, _c6_comfy_fn=lambda m, a, fallback=None: _rebuild):
            _fixed = fs._fs_meta_construct(_PoisonedConfig(), {}, _metrics)
        # The rebuilt sampling must be real (non-meta) and zero-meta.
        self.assertNotEqual(_fixed.model_sampling.sigma.device.type, "meta")
        self.assertFalse(fs.collect_meta_tensors(_fixed.model_sampling))
        self.assertEqual(_metrics["sampling_poisoned_tensors"], 1)


class BindAndSweepTests(unittest.TestCase):
    def test_assign_true_zero_copy(self):
        _model = _TinyModule()
        _sd = _tiny_sd()
        with torch.no_grad():
            _model.diffusion_model.load_state_dict(_sd, assign=True)
        _p = _model.diffusion_model.weight
        _w = _sd["weight"]
        self.assertEqual(_p.data_ptr(), _w.data_ptr())
        self.assertEqual(_p.dtype, torch.bfloat16)

    def test_residual_meta_detection_and_sweep(self):
        _model = _TinyModule()
        _model.diffusion_model.register_buffer("extra", torch.empty(4, device="meta"))
        with _Patch(fs, _fs_cuda_available=lambda: True):
            _n = fs._fs_sweep_meta(_model, torch.device("cpu"))
        self.assertGreaterEqual(_n, 1)
        self.assertEqual(_model.diffusion_model.extra.device.type, "cpu")
        self.assertEqual(fs.collect_meta_tensors(_model), [])

    def test_sweep_rejects_meta_param_after_bind(self):
        _model = _TinyModule()
        _model.diffusion_model.weight = torch.nn.Parameter(
            torch.empty(4, 8, dtype=torch.bfloat16, device="meta"))
        with self.assertRaises(RuntimeError):
            fs._fs_sweep_meta(_model, torch.device("cpu"))


class PipelineContractTests(unittest.TestCase):
    def _run_pipeline(self, td, tensors=None, extra=None):
        _path = str(Path(td) / "t.safetensors")
        _write_tiny_file(_path)
        _hdr = _tiny_header()
        _t = tensors if tensors is not None else _tiny_sd()
        _kw = _fs_common_patches(_path, _hdr, ZImage(), _t)
        if extra:
            _kw.update(extra)
        _trace = _FakeTrace()
        with _Patch(fs, **_kw), _Patch(fs, _ACTIVE_LANE_TRACE=_FakeLaneCtx(_trace)):
            _result = fs._fs_try_pipeline(
                None, None,
                {"unet_name": "t.safetensors", "weight_dtype": "default"}, None)
        return _result, _trace

    def _fs_events(self, trace):
        return [e for e in trace.events if e[0] == "unet_fastsafetensors_pipeline"]

    def test_success_contract(self):
        with tempfile.TemporaryDirectory() as td:
            _result, _trace = self._run_pipeline(td)
            self.assertIsNotNone(_result)
            self.assertIsInstance(_result[0], _FakePatcher)
            _owner = getattr(_result[0], fs._FS_OWNER_ATTR, None)
            self.assertIsNotNone(_owner, "owner must be attached to patcher")
            self.assertEqual(_owner.kind, "fastsafetensors.FilesBufferOnDevice")
            _events = self._fs_events(_trace)
            self.assertEqual(len(_events), 1)  # one-event contract
            _m = _events[0][2]
            self.assertEqual(_m["status"], "ok")
            self.assertEqual(_m["fallback_count"], 0)
            self.assertEqual(_m["tensor_count"], 3)
            self.assertTrue(_m["key_set_ok"])
            self.assertTrue(_m["transform_independent"])
            self.assertEqual(_m["residual_meta_after"], 0)
            self.assertTrue(_m["data_ptr_sample_match"])  # zero-copy
            self.assertFalse(_m["clone_required"])
            self.assertEqual(_m["owner_mode"], "loader_retained")
            for _k in ("header_config_wall_ms", "meta_get_model_wall_ms",
                       "fastsafe_setup_wall_ms", "fastsafe_file_gpu_wall_ms",
                       "worker_a_wall_ms", "worker_b_wall_ms", "join_delay_ms",
                       "bind_wall_ms", "final_to_wall_ms", "final_sync_wall_ms",
                       "total_pipeline_wall_ms"):
                self.assertIn(_k, _m)
            json.dumps(_m, default=str)  # memory telemetry JSON-safe

    def test_fallback_key_mismatch_releases_loader(self):
        # A missing sd key is caught by the tensor_validity gate (key_set_ok
        # fails against the header before the sd->param mapping gate).
        _bad = dict(_tiny_sd())
        _bad.pop("scale")
        with tempfile.TemporaryDirectory() as td:
            _result, _trace = self._run_pipeline(td, tensors=_bad)
            self.assertIsNone(_result)
            _events = self._fs_events(_trace)
            self.assertEqual(len(_events), 1)
            _m = _events[0][2]
            self.assertEqual(_m["status"], "fallback")
            self.assertEqual(_m["fallback_count"], 1)
            self.assertEqual(_m["reason"], "stage:tensor_validity")

    def test_fallback_shape_mismatch(self):
        _bad = dict(_tiny_sd())
        _bad["diffusion_model.weight"] = torch.zeros(3, 8, dtype=torch.bfloat16)
        with tempfile.TemporaryDirectory() as td:
            _result, _trace = self._run_pipeline(td, tensors=_bad)
            self.assertIsNone(_result)
            _m = self._fs_events(_trace)[0][2]
            self.assertEqual(_m["reason"], "stage:tensor_validity")

    def test_fallback_dtype_mismatch(self):
        _bad = dict(_tiny_sd())
        _bad["diffusion_model.bias"] = torch.zeros(4, dtype=torch.float32)
        with tempfile.TemporaryDirectory() as td:
            _result, _trace = self._run_pipeline(td, tensors=_bad)
            self.assertIsNone(_result)
            _m = self._fs_events(_trace)[0][2]
            self.assertEqual(_m["reason"], "stage:tensor_validity")

    def test_fallback_header_config_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            _path = str(Path(td) / "t.safetensors")
            _write_tiny_file(_path)
            _kw = _fs_common_patches(_path, _tiny_header(), ZImage(),
                                     _tiny_sd())
            _kw["_ring_derive_config"] = lambda p, _probe_wall=None: None
            with _Patch(fs, **_kw):
                _result = fs._fs_try_pipeline(
                    None, None,
                    {"unet_name": "t.safetensors", "weight_dtype": "default"}, None)
            self.assertIsNone(_result)

    def test_fallback_param_count_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            _result, _trace = self._run_pipeline(
                td, extra={"_FS_EXPECTED_PARAM_COUNT": 999999})
            self.assertIsNone(_result)
            _m = self._fs_events(_trace)[0][2]
            self.assertTrue(_m["reason"].startswith("stage:param_count_mismatch"))

    def test_final_to_duplicate_gate(self):
        with tempfile.TemporaryDirectory() as td:
            _result, _trace = self._run_pipeline(
                td, extra={"_FS_FINAL_TO_DUPLICATE_THRESHOLD_MS": -1.0})
            self.assertIsNone(_result)
            _m = self._fs_events(_trace)[0][2]
            self.assertEqual(_m["reason"], "stage:final_to_duplicates_transfer")


class BranchContractTests(unittest.TestCase):
    """The _load_unet branch: no native replay after success; fallback invokes
    native exactly once; ring/md branches take priority (order unchanged)."""

    def _bridge(self):
        class _Bridge:
            calls = []
            _trace = None

            def _find_request(self, kind, ident):
                return {"unet_name": "t.safetensors", "weight_dtype": "default"}

            def _invoke_original(self, class_name, kwargs):
                _Bridge.calls.append(class_name)
                return ("native_patcher",)

        _Bridge.calls = []
        _bridge = _Bridge()
        # Bind the REAL V2LoaderBridge._load_unet (with the branch logic)
        # onto the fake bridge object.
        _bridge._load_unet = types.MethodType(mp.V2LoaderBridge._load_unet, _bridge)
        return _bridge

    def _load_unet_with(self, td, fs_enabled, fs_ok, ring_ok=False):
        _path = str(Path(td) / "t.safetensors")
        _write_tiny_file(_path)
        _kw = _fs_common_patches(_path, _tiny_header(), ZImage(), _tiny_sd())
        if not fs_ok:
            _kw["_fs_fast_module"] = lambda: None  # import unavailable -> None
        _bridge = self._bridge()
        _key = types.SimpleNamespace(unet_identity="t.safetensors")
        with _Patch(mp, _ring_pipeline_enabled=lambda: ring_ok,
                    _md_pipeline_enabled=lambda: False,
                    _fs_pipeline_enabled=lambda: fs_enabled,
                    _ring_try_pipeline=lambda *a, **k: ("ring_patcher",)), \
             _Patch(fs, **_kw):
            return _bridge, _bridge._load_unet(_key)

    def test_no_native_replay_after_success(self):
        with tempfile.TemporaryDirectory() as td:
            _bridge, _result = self._load_unet_with(td, fs_enabled=True, fs_ok=True)
            self.assertNotEqual(_result, ("native_patcher",))
            self.assertEqual(_bridge.calls, [])

    def test_fallback_invokes_native_exactly_once(self):
        with tempfile.TemporaryDirectory() as td:
            _bridge, _result = self._load_unet_with(td, fs_enabled=True, fs_ok=False)
            self.assertEqual(_result, "native_patcher")  # _load_unet unwraps
            self.assertEqual(_bridge.calls, ["UNETLoader"])

    def test_flag_off_uses_native(self):
        with tempfile.TemporaryDirectory() as td:
            _bridge, _result = self._load_unet_with(td, fs_enabled=False, fs_ok=True)
            self.assertEqual(_result, "native_patcher")  # _load_unet unwraps
            self.assertEqual(_bridge.calls, ["UNETLoader"])

    def test_ring_branch_priority(self):
        with tempfile.TemporaryDirectory() as td:
            _bridge, _result = self._load_unet_with(td, fs_enabled=True, fs_ok=True,
                                                    ring_ok=True)
            self.assertEqual(_result, "ring_patcher")  # _load_unet unwraps
            self.assertEqual(_bridge.calls, [])


class OwnerLifetimeTests(unittest.TestCase):
    def test_owner_retained_and_released(self):
        _loader = _FakeFSTLoader(_tiny_sd())
        _fb = _FakeFB(_tiny_sd())
        _owner = fs._FastsafeOwner(_loader, _fb)
        _patcher = _FakePatcher(None)
        setattr(_patcher, fs._FS_OWNER_ATTR, _owner)
        _refs = (weakref.ref(_loader), weakref.ref(_fb))
        del _owner
        del _loader, _fb  # drop the test's own strong refs
        gc.collect()
        self.assertIsNotNone(_refs[0]())  # alive via patcher
        self.assertIsNotNone(_refs[1]())
        del _patcher
        gc.collect()
        gc.collect()
        self.assertIsNone(_refs[0]())  # released with the model
        self.assertIsNone(_refs[1]())


class ModuleSurfaceTests(unittest.TestCase):
    def test_module_imports_clean(self):
        self.assertTrue(callable(fs._fs_try_pipeline))
        self.assertTrue(callable(fs._fs_eligible))
        self.assertTrue(callable(fs._fs_meta_construct))
        self.assertTrue(callable(fs._fs_fastsafe_load))
        self.assertTrue(callable(fs._fs_sweep_meta))
        self.assertTrue(callable(fs._fs_validate_final))

    def test_memory_snapshot_json_safe(self):
        _s = fs._fs_memory_snapshot()
        json.dumps(_s, default=str)
        _r = fs._fs_mem_report("x", _s, _s)
        json.dumps(_r, default=str)

    def test_validate_final(self):
        _model = _TinyModule()
        _v = fs._fs_validate_final(_model, torch.device("cpu"))
        self.assertTrue(_v["all_params_on_target"])
        self.assertEqual(_v["residual_meta_count"], 0)
        self.assertEqual(_v["param_count"], 2)

    def test_telemetry_never_raises(self):
        _trace = _FakeTrace()
        fs._fs_emit("ok", "", {"total_pipeline_wall_ms": 1.0, "fallback_count": 0},
                    _trace)
        fs._fs_emit("fallback", "stage:x", {"fallback_count": 1}, _trace)
        _events = [e for e in _trace.events
                   if e[0] == "unet_fastsafetensors_pipeline"]
        self.assertEqual(len(_events), 2)
        self.assertEqual(_events[0][2]["status"], "ok")
        self.assertEqual(_events[1][2]["reason"], "stage:x")


if __name__ == "__main__":
    unittest.main()
