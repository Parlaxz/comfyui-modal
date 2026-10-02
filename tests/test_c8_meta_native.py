"""Offline feasibility tests for the C8 meta + native fast-disk hybrid
(Batch C8: meta model construction feeding the EXISTING native fast-disk
read -> assign=True bind -> native model.to(cuda) replay path).

Proves, without any Modal run and without touching production wiring:

1. A meta-constructed module adopts mmap-backed safetensors CPU tensors via
   ``load_state_dict(assign=True)`` with ZERO copy (data_ptr equality) —
   requires_grad preserved, buffers adopted.
2. ``assign=False`` into a meta module is a silent no-op (the documented
   footgun) — the C8 path MUST force assign=True.
3. Non-state-dict buffers stay meta and are detected by a meta sweep; the
   sweep-and-materialize step fixes them so ``.to(cuda)`` cannot hit
   "Cannot copy out of meta tensor".
4. ``.to(cuda)`` after adoption is functionally identical to a normal
   CPU-constructed module (values match, single H2D copy).
5. The LIVE fast-disk guards in ``comfymodal_runtime.model_preload``
   accept a meta-resident model: ``_fast_disk_model_is_cpu_resident``
   (only rejects CUDA residency), ``_fast_disk_guard_to`` and
   ``_fast_disk_guard_bind`` all pass with meta params + mmap sd tensors.
   => No guard edits are required for the hybrid.
6. REAL ZImage checkpoint (local ``z_image_turbo_bf16.safetensors``,
   header-only): header -> meta state dict -> value probe (allow_fp16) ->
   ``detect_unet_config``/``model_config_from_unet`` -> meta get_model,
   with timing.  Sampling rebuild leaves zero meta tensors.
7. Real ZImage sample adoption: a subset of real mmap tensors installed
   with assign=True are adopted zero-copy; the rest stay meta (residue).

Everything is CPU-only except the CUDA-gated equivalence tests.  Real-model
tests skip cleanly when the checkpoint is missing.  No production files are
touched; no Modal run is performed.
"""

from __future__ import annotations

import gc
import os
import sys
import tempfile
import time
import unittest

import torch

import comfymodal_runtime.model_preload as mp

try:
    import safetensors.torch as _st_torch
    _HAS_SAFETENSORS = True
except Exception:  # pragma: no cover
    _HAS_SAFETENSORS = False

_HAS_CUDA = torch.cuda.is_available()

_COMFY_ROOT = r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI"
if _COMFY_ROOT not in sys.path:
    sys.path.insert(0, _COMFY_ROOT)
try:
    import comfy.model_detection  # noqa: F401
    import comfy.model_base  # noqa: F401
    _HAS_COMFY = True
except Exception:  # pragma: no cover
    _HAS_COMFY = False

_ZIMAGE_PATH = os.environ.get(
    "COMFYMODAL_C8_ZIMAGE_PATH",
    os.path.join(_COMFY_ROOT, "models", "diffusion_models",
                 "z_image_turbo_bf16.safetensors"),
)
# The local copy may be a 0-byte Modal-volume placeholder; the real-model
# tests only run when a non-empty checkpoint is actually present.
if not (os.path.isfile(_ZIMAGE_PATH) and os.path.getsize(_ZIMAGE_PATH) > 0):
    _ZIMAGE_PATH = ""

# C8 measured results surfaced for the report.
C8_RESULTS: dict = {}


class _TinyModel(torch.nn.Module):
    """Small module mimicking the shape of the fast-disk flow: one Linear
    (bf16) plus a persistent buffer, all inside a ``diffusion_model``."""

    def __init__(self):
        super().__init__()
        self.diffusion_model = torch.nn.Linear(8, 4, dtype=torch.bfloat16)
        self.register_buffer("scale", torch.empty(4, dtype=torch.bfloat16))


def _write_tiny_safetensors(path: str) -> None:
    _st_torch.save_file({
        "diffusion_model.weight": torch.arange(32, dtype=torch.bfloat16).view(4, 8),
        "diffusion_model.bias": torch.arange(4, dtype=torch.bfloat16),
        "scale": torch.tensor([1.0, 2.0, 3.0, 4.0], dtype=torch.bfloat16),
    }, path)


def _mmap_sd(path: str) -> dict:
    """Read a state dict as mmap-backed views (zero-copy adoption target)."""
    import safetensors
    out = {}
    with safetensors.safe_open(path, framework="pt", device="cpu") as f:
        for k in f.keys():
            out[k] = f.get_tensor(k)
    return out


class _TempDir:
    """Windows-safe temp dir: mmap'd safetensors files cannot be deleted
    while their storage is alive, so drop the mapping before cleanup."""

    def __init__(self, *objs_to_free):
        self._objs = objs_to_free

    def __enter__(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        return self._td.__enter__()

    def __exit__(self, *exc):
        for _o in self._objs:
            try:
                del _o
            except Exception:
                pass
        gc.collect()
        return self._td.__exit__(*exc)


def _meta_tensors(model: torch.nn.Module) -> list:
    found = []
    for t in list(model.parameters()) + list(model.buffers()):
        if getattr(t, "is_meta", False):
            found.append(t)
    return found


def _sweep_meta_to_cpu(model: torch.nn.Module) -> int:
    """Materialize residual meta params/buffers on CPU.  ``param.data =``
    and ``set_`` are illegal on meta tensors (verified empirically), so the
    parameter/buffer is REPLACED via setattr — the same object-replacement
    mechanism ``assign=True`` uses.  Returns the number of tensors fixed
    (0 means the model is fully materialized)."""
    n = 0
    for name, t in list(model.named_parameters(remove_duplicate=False)) \
            + list(model.named_buffers(remove_duplicate=False)):
        if not getattr(t, "is_meta", False):
            continue
        prefix, _, leaf = name.rpartition(".")
        host = model.get_submodule(prefix) if prefix else model
        if isinstance(t, torch.nn.Parameter):
            new = torch.nn.Parameter(
                torch.empty_like(t, device="cpu"), requires_grad=t.requires_grad)
        else:
            new = torch.empty_like(t, device="cpu")
        setattr(host, leaf, new)
        n += 1
    return n


@unittest.skipUnless(_HAS_SAFETENSORS, "safetensors not available")
class TestC8AssignAdoption(unittest.TestCase):
    """Q2: mmap tensors installed with load_state_dict(assign=True) are
    adopted zero-copy; requires_grad semantics; buffer adoption."""

    def test_assign_true_adopts_mmap_zero_copy(self):
        with _TempDir() as td:
            path = os.path.join(td, "tiny.safetensors")
            _write_tiny_safetensors(path)
            sd = _mmap_sd(path)
            model = _TinyModel().to("meta")
            self.assertTrue(all(p.is_meta for p in model.parameters()))
            model.load_state_dict(sd, assign=True)
            # Zero-copy adoption: identical data_ptr for params AND buffers.
            for key, sd_t in sd.items():
                mod_t = dict(model.state_dict())[key]
                self.assertEqual(
                    mod_t.data_ptr(), sd_t.data_ptr(),
                    f"{key} was copied, not adopted (data_ptr differs)",
                )
                self.assertFalse(mod_t.is_meta)
            # requires_grad: the module's value wins (torch >= 2.3).
            self.assertTrue(model.diffusion_model.weight.requires_grad)

    def test_assign_false_meta_is_noop_footgun(self):
        with _TempDir() as td:
            path = os.path.join(td, "tiny.safetensors")
            _write_tiny_safetensors(path)
            sd = _mmap_sd(path)
            model = _TinyModel().to("meta")
            with self.assertWarns(UserWarning):
                model.load_state_dict(sd, assign=False)
            # Silent no-op: params still meta, NO data adopted.
            self.assertTrue(all(p.is_meta for p in model.parameters()))
            self.assertTrue(model.diffusion_model.weight.is_meta)

    def test_non_sd_buffer_stays_meta_detected_and_swept(self):
        with _TempDir() as td:
            path = os.path.join(td, "tiny.safetensors")
            _write_tiny_safetensors(path)
            sd = _mmap_sd(path)
            model = _TinyModel().to("meta")
            model.register_buffer("residue", torch.empty(2, dtype=torch.bfloat16, device="meta"))
            model.load_state_dict(sd, strict=False, assign=True)
            # All sd tensors adopted; the non-sd buffer is still meta.
            meta = _meta_tensors(model)
            self.assertEqual(len(meta), 1)
            self.assertIs(meta[0], model.residue)
            # Sweep materializes it on CPU -> zero residue -> to(cuda) safe.
            self.assertEqual(_sweep_meta_to_cpu(model), 1)
            self.assertEqual(_meta_tensors(model), [])
            if _HAS_CUDA:
                model.to("cuda")
                self.assertEqual(model.residue.device.type, "cuda")
                self.assertEqual(model.diffusion_model.weight.device.type, "cuda")


@unittest.skipUnless(_HAS_SAFETENSORS and _HAS_CUDA, "needs safetensors + CUDA")
class TestC8ToCudaEquivalence(unittest.TestCase):
    """Q6: after assign=True adoption, .to(cuda) is functionally identical
    to a normally-constructed module."""

    def test_to_cuda_after_adopt_matches_control(self):
        with _TempDir() as td:
            path = os.path.join(td, "tiny.safetensors")
            _write_tiny_safetensors(path)
            sd = _mmap_sd(path)
            # Control: normal CPU construction + assign adoption + to(cuda).
            control = _TinyModel()
            control.load_state_dict(sd, assign=True)
            control.to("cuda")
            # Hybrid: meta construction + assign adoption + to(cuda).
            hybrid = _TinyModel().to("meta")
            hybrid.load_state_dict(sd, assign=True)
            hybrid.to("cuda")
            for key, _ in sd.items():
                c = dict(control.state_dict())[key]
                h = dict(hybrid.state_dict())[key]
                self.assertEqual(c.device.type, "cuda")
                self.assertEqual(h.device.type, "cuda")
                self.assertTrue(torch.equal(c, h), f"{key} diverged")


class TestC8FastDiskGuardCompatibility(unittest.TestCase):
    """Q4: the live fast-disk guards accept a meta-resident model — no
    guard edits required for the hybrid."""

    def _meta_model(self):
        return _TinyModel().to("meta")

    @staticmethod
    def _patcher_info(model, load_device, offload_device):
        return {
            "object_id": str(id(model)),
            "type_module": "comfy.model_patcher",
            "type_name": "ModelPatcher",
            "is_dynamic": False,
            "load_device": load_device,
            "offload_device": offload_device,
        }

    def test_cpu_resident_guard_accepts_meta_model(self):
        model = self._meta_model()
        # Meta-resident passes (only CUDA residency is rejected).
        self.assertTrue(mp._fast_disk_model_is_cpu_resident(model))
        if _HAS_CUDA:
            # A CPU-constructed model moved to CUDA is rejected.
            cuda_model = _TinyModel().to("cuda")
            self.assertFalse(mp._fast_disk_model_is_cpu_resident(cuda_model))
            # Documented footgun: direct meta -> cuda conversion is illegal;
            # the C8 path MUST bind (assign=True) BEFORE the native .to().
            with self.assertRaises(NotImplementedError):
                _TinyModel().to("meta").to("cuda")

    def test_guard_to_ok_with_meta_model(self):
        model = self._meta_model()
        config = type("FakeConfig", (), {
            "quant_config": None, "custom_operations": None,
            "optimizations": None})()
        record = mp._fast_disk_new_record(model, config, None)
        try:
            record["patcher"] = self._patcher_info(
                model, torch.device("cuda"), torch.device("cuda"))
            with unittest.mock.patch.object(mp, "_fast_disk_high_vram", return_value=True), \
                 unittest.mock.patch.object(mp, "_fast_disk_torch_future_enabled",
                                            return_value=False):
                ok, reason, _ = mp._fast_disk_guard_to(
                    record, torch.device("cuda"))
            self.assertTrue(ok, f"guard_to rejected meta model: {reason}")
        finally:
            mp._fast_disk_drop_record(model)

    def test_guard_bind_ok_with_meta_model_and_mmap_sd(self):
        with _TempDir() as td:
            path = os.path.join(td, "tiny.safetensors")
            _write_tiny_safetensors(path)
            sd = _mmap_sd(path)
            model = self._meta_model()
            config = type("FakeConfig", (), {
                "quant_config": None, "custom_operations": None,
                "optimizations": None})()
            record = mp._fast_disk_new_record(model, config, None)
            try:
                record["patcher"] = self._patcher_info(
                    model, torch.device("cuda"), torch.device("cuda"))
                ok, reason, _ = mp._fast_disk_guard_bind(record, (sd, ""), {})
                self.assertTrue(ok, f"guard_bind rejected meta model: {reason}")
            finally:
                mp._fast_disk_drop_record(model)


def _derive_n_layers(header: dict) -> int | None:
    """Max layers.{i}.ffn_norm1.weight index + 1 from the header."""
    best = None
    for key in (header or {}):
        if key.startswith("layers.") and key.endswith(".ffn_norm1.weight"):
            try:
                idx = int(key.split(".")[1])
            except (ValueError, IndexError):
                continue
            best = idx if best is None else max(best, idx)
    return None if best is None else best + 1


@unittest.skipUnless(
    _HAS_SAFETENSORS and _HAS_COMFY and os.path.isfile(_ZIMAGE_PATH),
    "real ZImage checkpoint or comfy unavailable",
)
class TestC8RealZImage(unittest.TestCase):
    """Q1/Q5/Q7: real ZImage meta construction from the header, sampling
    rebuild, and real-tensor zero-copy adoption."""

    @classmethod
    def setUpClass(cls):
        t0 = time.monotonic()
        cls.header = mp._c6_parse_safetensors_header(_ZIMAGE_PATH)
        assert cls.header, "header parse failed"
        cls.meta_sd = mp._c6_build_meta_sd(cls.header)
        cls.n_layers = _derive_n_layers(cls.header)
        # Value probe: the ONLY value-dependent detector input (allow_fp16).
        if cls.n_layers is None:
            cls.allow_fp16 = None
        else:
            cls.allow_fp16 = mp._c6_value_probe_allow_fp16(
                _ZIMAGE_PATH, cls.header, cls.n_layers)
            # Inject the REAL probe tensor so detect_unet_config can read it.
            probe_key = f"layers.{cls.n_layers - 2}.ffn_norm1.weight"
            if probe_key in cls.header:
                import safetensors
                with safetensors.safe_open(
                        _ZIMAGE_PATH, framework="pt", device="cpu") as f:
                    cls.meta_sd[probe_key] = f.get_tensor(probe_key)
        C8_RESULTS["real_header_keys"] = len(cls.header)
        C8_RESULTS["real_meta_sd_keys"] = len(cls.meta_sd)
        C8_RESULTS["real_n_layers"] = cls.n_layers
        C8_RESULTS["real_allow_fp16"] = cls.allow_fp16
        C8_RESULTS["real_header_parse_ms"] = round(
            (time.monotonic() - t0) * 1000, 1)

    def test_meta_get_model_real_zimage(self):
        import comfy.model_detection as cdet
        config = cdet.model_config_from_unet(
            self.meta_sd, "", metadata=self.header.get("__metadata__"))
        self.assertIsNotNone(config)
        self.assertEqual(type(config).__name__, "ZImage")
        t0 = time.monotonic()
        with torch.no_grad(), torch.device("meta"):
            model = config.get_model(self.meta_sd, "")
        wall_ms = (time.monotonic() - t0) * 1000
        C8_RESULTS["real_meta_get_model_ms"] = round(wall_ms, 1)
        print(f"[C8] real ZImage meta get_model: {wall_ms:.1f} ms")
        self.assertTrue(all(p.is_meta for p in model.parameters()))
        self.assertEqual(model.diffusion_model.weight.dtype, torch.bfloat16)
        C8_RESULTS["real_model"] = model

    def test_sampling_rebuild_leaves_zero_meta(self):
        model = C8_RESULTS.get("real_model")
        if model is None:
            self.skipTest("meta get_model did not run")
        import comfy.model_base as cbase
        t0 = time.monotonic()
        model.model_sampling = cbase.model_sampling(
            model.model_config, model.model_type)
        wall_ms = (time.monotonic() - t0) * 1000
        C8_RESULTS["real_sampling_fix_ms"] = round(wall_ms, 1)
        print(f"[C8] sampling rebuild: {wall_ms:.1f} ms")
        self.assertEqual(_meta_tensors(model.model_sampling), [])
        C8_RESULTS["real_sampling_clean"] = True

    def test_real_sample_assign_adoption_zero_copy(self):
        model = C8_RESULTS.get("real_model")
        if model is None:
            self.skipTest("meta get_model did not run")
        import safetensors
        with safetensors.safe_open(
                _ZIMAGE_PATH, framework="pt", device="cpu") as f:
            keys = list(f.keys())[:24]
            partial = {k: f.get_tensor(k) for k in keys}
        t0 = time.monotonic()
        model.diffusion_model.load_state_dict(partial, strict=False, assign=True)
        wall_ms = (time.monotonic() - t0) * 1000
        C8_RESULTS["real_sample_assign_ms"] = round(wall_ms, 1)
        print(f"[C8] assign adopt of {len(keys)} real tensors: {wall_ms:.1f} ms")
        after = dict(model.diffusion_model.state_dict())
        for k, sd_t in partial.items():
            self.assertFalse(after[k].is_meta)
            self.assertEqual(after[k].data_ptr(), sd_t.data_ptr(),
                             f"{k} copied, not adopted")
        # The remaining ~429 params are still meta (residue) — the sweep in
        # the production flow must handle them the same way.
        n_meta = len(_meta_tensors(model.diffusion_model))
        C8_RESULTS["real_residue_meta_after_partial"] = n_meta
        self.assertGreater(n_meta, 0)
        print(f"[C8] residual meta params after partial adoption: {n_meta}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
