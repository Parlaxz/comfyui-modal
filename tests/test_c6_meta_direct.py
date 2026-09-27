"""Focused offline tests for the V2 meta-direct UNET loader
(``comfymodal_runtime.unet_meta_direct``, flag ``COMFYMODAL_V2_UNET_META_DIRECT``).

Everything is CPU-only except the end-to-end pipeline test (gated on real
CUDA, which exercises the genuine to_empty + async DMA path on this box).
The Linux-only ``os.preadv``/``os.posix_fadvise`` are simulated via
monkeypatched fakes (exactly as the Modal container exercises them).
"""

from __future__ import annotations

import contextlib
import gc
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import torch

import comfymodal_runtime.model_preload as mp
import comfymodal_runtime.unet_meta_direct as md

try:
    import safetensors.torch as _st_torch
    _HAS_SAFETENSORS = True
except Exception:  # pragma: no cover - skip on systems without safetensors
    _HAS_SAFETENSORS = False

_HAS_CUDA = torch.cuda.is_available()

_MD_TOTAL_BYTES = 12_309_817_472  # measured ZImage tensor data bytes
_MD_HEADER_JSON = 48_920


class _FakeEvent:
    def __init__(self, *a, **k):
        self.syncs = 0

    def record(self):
        pass

    def synchronize(self):
        self.syncs += 1

    def elapsed_time(self, other):
        return 1.0


class _FakeSampling:
    def __init__(self):
        self.sigmas = torch.zeros(10)


class _FakePatcher:
    def __init__(self, model, load_device, offload_device):
        self.model = model
        self.load_device = load_device
        self.offload_device = offload_device


class _TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.diffusion_model = torch.nn.Linear(8, 4, dtype=torch.bfloat16)
        self.model_sampling = _FakeSampling()
        self.model_type = "flow"
        self.model_config = None


class _FakeConfig:
    def __init__(self, name="ZImage", model_cls=None, supported=None):
        self.unet_config = {"dim": 8, "n_layers": 1}
        self.supported_inference_dtypes = supported or [torch.bfloat16]
        self._name = name
        self._model_cls = model_cls or _TinyModel
        self.process_calls = 0

    @property
    def name(self):
        return self._name

    def get_model(self, sd, prefix=""):
        m = self._model_cls()
        m.model_config = self
        return m

    def process_unet_state_dict(self, sd):
        self.process_calls += 1
        return dict(sd)


# Config class whose runtime type name is exactly "ZImage" so the pipeline's
# family gate (`type(config).__name__ == "ZImage"`) passes.
_ZImageConfig = type("ZImage", (_FakeConfig,), {})


def _make_header(entries, dtype="BF16"):
    """entries: list of (key, numel) -> packed header with the key's dtype."""
    header = {}
    off = 0
    for key, numel in entries:
        nbytes = numel * 2  # BF16
        header[key] = {"dtype": dtype, "shape": [numel],
                       "data_offsets": [off, off + nbytes]}
        off += nbytes
    return header


def _tiny_pipeline_header():
    """Header matching _TinyModel's diffusion_model (weight (4,8) + bias (4),
    BF16) with data offsets that match a real safetensors file layout."""
    header = {}
    off = 0
    for key, shape in (("weight", [4, 8]), ("bias", [4])):
        numel = 1
        for s in shape:
            numel *= s
        nbytes = numel * 2  # BF16
        header[key] = {"dtype": "BF16", "shape": list(shape),
                       "data_offsets": [off, off + nbytes]}
        off += nbytes
    return header


def _make_derived(config=None, header=None):
    config = config or _ZImageConfig()
    header = header or _tiny_pipeline_header()
    meta_sd = {
        "weight": torch.empty(4, 8, dtype=torch.bfloat16, device="meta"),
        "bias": torch.empty(4, dtype=torch.bfloat16, device="meta"),
    }
    return (config, meta_sd, header, 1, "")


def _fake_comfy_fn(mod, attr, fallback=None):
    if mod == "comfy.model_management" and attr == "get_torch_device":
        return lambda: torch.device("cuda")
    if mod == "comfy.model_management" and attr == "unet_offload_device":
        return lambda: torch.device("cpu")
    if mod == "comfy.model_patcher" and attr == "ModelPatcher":
        return _FakePatcher
    if mod == "comfy.model_base" and attr == "model_sampling":
        return lambda config, mtype: _FakeSampling()
    return fallback


def _fake_preadv(fd, iov, offset):
    """Simulate Linux os.preadv on Windows: seek + read into each buffer."""
    total = 0
    for buf in iov:
        os.lseek(fd, offset + total, os.SEEK_SET)
        data = os.read(fd, buf.nbytes)
        if not data:
            break
        buf[: len(data)] = data
        total += len(data)
    return total


def _write_tiny_safetensors(td):
    path = os.path.join(td, "tiny.safetensors")
    _st_torch.save_file({
        "weight": torch.zeros(4, 8, dtype=torch.bfloat16),
        "bias": torch.zeros(4, dtype=torch.bfloat16),
    }, path)
    return path


def _runner_env(path, preadv=None, fadvise=None):
    """ExitStack mocking the platform capabilities for the pipeline/runner."""
    _stack = contextlib.ExitStack()
    _stack.enter_context(mock.patch.object(torch.cuda, "is_available", return_value=True))
    _stack.enter_context(mock.patch.object(torch.cuda, "Event", _FakeEvent))
    _stack.enter_context(mock.patch.object(torch.cuda, "synchronize", lambda *a, **k: None))
    _stack.enter_context(mock.patch.object(torch.cuda, "empty_cache", lambda *a, **k: None))
    if preadv is None:
        _stack.enter_context(mock.patch.object(md._os, "preadv", _fake_preadv, create=True))
    else:
        _stack.enter_context(mock.patch.object(md._os, "preadv", preadv, create=True))
    if fadvise is None:
        _stack.enter_context(mock.patch.object(md._os, "posix_fadvise",
                                               lambda *a, **k: None, create=True))
    elif fadvise is False:
        _stack.enter_context(mock.patch.object(md._os, "posix_fadvise", None, create=True))
    else:
        _stack.enter_context(mock.patch.object(md._os, "posix_fadvise", fadvise, create=True))
    _stack.enter_context(mock.patch.object(md._os, "POSIX_FADV_WILLNEED", 3, create=True))
    return _stack


# ── 1. Flag parsing ──────────────────────────────────────────────────────


class TestMetaDirectFlagParsing(unittest.TestCase):
    def test_flag_parsing(self):
        cases = [
            (None, "off"), ("", "off"), ("off", "off"), ("0", "off"),
            ("false", "off"), ("no", "off"), ("none", "off"), ("OFF", "off"),
            ("1", "on"), ("TRUE", "on"), ("Yes", "on"), ("on", "on"),
            ("garbage", "invalid"), ("2", "invalid"),
        ]
        for raw, expected in cases:
            env = {} if raw is None else {"COMFYMODAL_V2_UNET_META_DIRECT": raw}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(mp._md_flag_value(), expected)

    def test_invalid_fail_closed_printed_once(self):
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_META_DIRECT": "bogus"}, clear=True), \
             mock.patch("builtins.print") as pr:
            assert mp._md_pipeline_enabled() is False
            assert mp._md_pipeline_enabled() is False
        printed = [c for c in pr.call_args_list if "invalid" in str(c)]
        assert len(printed) == 1, pr.call_args_list

    def test_off_zero_pipeline_disabled(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert mp._md_pipeline_enabled() is False
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_META_DIRECT": "on"}, clear=True):
            assert mp._md_pipeline_enabled() is True

    def test_independent_of_v1_ring_flag(self):
        # V1 ring flag must NOT enable the meta-direct pipeline and vice versa.
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_PINNED_RING": "on"}, clear=True):
            assert mp._md_pipeline_enabled() is False
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_META_DIRECT": "on"}, clear=True):
            assert mp._ring_pipeline_enabled() is False


# ── 2. Eligibility ───────────────────────────────────────────────────────


class TestMetaDirectEligibility(unittest.TestCase):
    def _call_eligible(self, **patches):
        path = "C:/models/zimage.safetensors"
        with mock.patch.object(md, "_ring_resolve_unet_path", return_value=path), \
             mock.patch.object(md, "_c6_value_probe_allow_fp16", return_value=True), \
             mock.patch.object(md, "_fast_disk_high_vram", return_value=True), \
             mock.patch.object(md, "_fast_disk_torch_future_enabled", return_value=False), \
             mock.patch.object(md, "_fast_disk_model_config_evidence", return_value={}):
            with contextlib.ExitStack() as stack:
                for k, v in patches.items():
                    stack.enter_context(mock.patch.object(md, k, v))
                return md._md_eligible(None, None, {"unet_name": "x"}, None)

    def test_family_not_zimage(self):
        config = _FakeConfig()  # type name "FakeConfig" != "ZImage"
        ok, reason = self._call_eligible(_ring_derive_config=lambda p: (
            config, {}, _tiny_pipeline_header(), 1, ""))
        assert (ok, reason) == (False, "family_not_zimage")

    def test_value_probe_unresolved(self):
        config = type("ZImage", (), {"unet_config": {"dim": 8}, "supported_inference_dtypes": [torch.bfloat16]})()
        derived = (config, {}, _tiny_pipeline_header(), 1, "")
        ok, reason = self._call_eligible(
            _ring_derive_config=lambda p: derived,
            _c6_value_probe_allow_fp16=lambda p, h, n: None)
        assert (ok, reason) == (False, "value_probe_unresolved")

    def test_missing_preadv_ineligible_named(self):
        config = type("ZImage", (), {"unet_config": {"dim": 8}, "supported_inference_dtypes": [torch.bfloat16]})()
        derived = (config, {}, _tiny_pipeline_header(), 1, "")
        with mock.patch.object(md._os, "preadv", None, create=True):
            ok, reason = self._call_eligible(_ring_derive_config=lambda p: derived)
        assert (ok, reason) == (False, "preadv_unavailable")

    def test_pinned_probe_fail_ineligible(self):
        config = type("ZImage", (), {"unet_config": {"dim": 8}, "supported_inference_dtypes": [torch.bfloat16]})()
        derived = (config, {}, _tiny_pipeline_header(), 1, "")

        def _boom(*a, **k):
            if k.get("pin_memory"):
                raise RuntimeError("no pin")
            return torch.empty(*a, **k)

        with mock.patch.object(md._os, "preadv", lambda *a, **k: 0, create=True), \
             mock.patch.object(torch, "empty", _boom):
            ok, reason = self._call_eligible(_ring_derive_config=lambda p: derived)
        assert (ok, reason) == (False, "pinned_unavailable")

    def test_non_high_vram_ineligible(self):
        config = type("ZImage", (), {"unet_config": {"dim": 8}, "supported_inference_dtypes": [torch.bfloat16]})()
        derived = (config, {}, _tiny_pipeline_header(), 1, "")
        with mock.patch.object(md._os, "preadv", lambda *a, **k: 0, create=True):
            ok, reason = self._call_eligible(
                _ring_derive_config=lambda p: derived,
                _fast_disk_high_vram=lambda: False)
        assert (ok, reason) == (False, "not_high_vram")


# ── 3. Meta construction path ────────────────────────────────────────────


@unittest.skipUnless(_HAS_CUDA, "CUDA required for to_empty path")
class TestMetaConstruction(unittest.TestCase):
    def _run_pipeline(self, path, trace=None, sync_counter=None):
        config = _ZImageConfig()
        derived = _make_derived(config, _tiny_pipeline_header())
        to_empty_calls = []
        _orig_to_empty = torch.nn.Module.to_empty

        def _spy_to_empty(self_mod, *args, **kwargs):
            to_empty_calls.append((self_mod, kwargs.get("device")))
            return _orig_to_empty(self_mod, *args, **kwargs)

        with _runner_env(path), \
             mock.patch.object(md, "_ring_resolve_unet_path", return_value=path), \
             mock.patch.object(md, "_ring_derive_config", return_value=derived), \
             mock.patch.object(md, "_md_eligible", return_value=(True, "")), \
             mock.patch.object(md, "_c6_comfy_fn", side_effect=_fake_comfy_fn), \
             mock.patch.object(torch.cuda, "synchronize", sync_counter or (lambda *a, **k: None)), \
             mock.patch.object(torch.nn.Module, "to_empty", _spy_to_empty):
            _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
            try:
                result = md._md_try_pipeline(None, None, {"unet_name": "x"}, None)
            finally:
                mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        return result, config, to_empty_calls

    def test_meta_get_model_and_sampling_fix(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            result, config, _te = self._run_pipeline(path)
        assert result is not None and len(result) == 1
        patcher = result[0]
        model = patcher.model
        params = list(model.parameters())
        assert params and all(p.device.type == "cuda" for p in params)
        assert all(p.dtype == torch.bfloat16 for p in params)
        # model_sampling was rebuilt outside the meta context (no meta left).
        assert md.collect_meta_tensors(model.model_sampling) == []

    def test_to_empty_called_with_cuda_device(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            result, config, _te = self._run_pipeline(path)
        assert result is not None
        assert _te, "to_empty must be called"
        assert str(_te[0][1]) == "cuda"

    def test_exactly_one_final_sync(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            counter = {"n": 0}

            def _sync(*a, **k):
                counter["n"] += 1

            result, config, _te = self._run_pipeline(path, sync_counter=_sync)
        assert result is not None
        assert counter["n"] == 1, counter

    def test_lean_telemetry_event_json_safe(self):
        from comfymodal_runtime.trace import RuntimeTrace
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            trace = RuntimeTrace(request_id="md-e2e", process="remote")
            result, config, _te = self._run_pipeline(path, trace=trace)
        assert result is not None
        evs = [e for e in trace.events if e.name == "unet_meta_direct_pipeline"]
        assert len(evs) == 1
        meta = evs[0].metadata
        assert meta["status"] == "ok"
        json.dumps(evs[0].to_dict())
        # No I-1/I-2 per-tensor series events in production mode.
        names = [e.name for e in trace.events]
        assert "unet_read_h2d_wave_probe" not in names
        assert "unet_tensor_materialize_aggregated" not in names


# ── 4. Wave building (128 MiB target) ────────────────────────────────────


class TestMetaDirectWaves(unittest.TestCase):
    def test_build_wave_ranges_128mb_target_exact(self):
        # 8 tensors of 64 MiB -> exactly 2 per 128 MiB-target wave.
        header = _make_header([(f"t{i}", 64 * 1024 * 1024 // 2) for i in range(8)])
        waves = md.build_wave_ranges(header, wave_target_bytes=128 * 1024 * 1024,
                                     max_wave_bytes=256 * 1024 * 1024)
        assert waves is not None
        assert [w["keys"] for w in waves] == [["t0", "t1"], ["t2", "t3"],
                                              ["t4", "t5"], ["t6", "t7"]]
        for w in waves:
            assert w["rel_byte_end"] - w["rel_byte_start"] == w["tensor_bytes"]
        assert sum(w["tensor_bytes"] for w in waves) == 8 * 64 * 1024 * 1024

    def test_zimage_sized_header_wave_bounds(self):
        # Synthetic 453-key header whose total matches the measured ZImage
        # tensor bytes (12,309,817,472).  Exact wave count depends on the real
        # size distribution (~96 expected); assert the byte-derived bounds and
        # the max-wave cap instead.
        sizes = [26_845_000] * 452 + [_MD_TOTAL_BYTES - 452 * 26_845_000]
        header = _make_header([(f"t{i}", s // 2) for i, s in enumerate(sizes)])
        assert len(sizes) == 453
        assert sum(s // 2 * 2 for s in sizes) == _MD_TOTAL_BYTES
        waves = md.build_wave_ranges(header, wave_target_bytes=128 * 1024 * 1024,
                                     max_wave_bytes=256 * 1024 * 1024)
        assert waves is not None
        assert len(waves) >= 92  # ceil(total / 128 MiB)
        assert all(w["tensor_bytes"] <= 256 * 1024 * 1024 for w in waves)
        assert sum(w["tensor_bytes"] for w in waves) == _MD_TOTAL_BYTES
        keys = [k for w in waves for k in w["keys"]]
        assert len(keys) == 453 and keys[0] == "t0" and keys[-1] == "t452"
        # contiguity inside every wave
        for w in waves:
            prev = w["tensors"][0]["rel_off"]
            for t in w["tensors"]:
                assert t["rel_off"] == prev
                prev = t["rel_end"]


# ── 5. preadv short-read retry loop ──────────────────────────────────────


class TestPreadvRetry(unittest.TestCase):
    def _make_waves(self, path):
        data = bytes(range(16))
        with open(path, "wb") as f:
            f.write(data)
        waves = [{
            "keys": ["w"], "rel_byte_start": 0, "rel_byte_end": 16,
            "tensor_bytes": 16,
            "tensors": [{"key": "w", "dtype": "BF16", "shape": [8],
                         "rel_off": 0, "rel_end": 16, "nbytes": 16}],
        }]
        return waves

    def test_short_read_loop_accumulates_until_complete(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            waves = self._make_waves(path)
            reads = {"calls": 0}
            fd = os.open(path, os.O_RDONLY)
            try:
                def _partial(fd, iov, offset):
                    # at most 3 bytes per preadv call -> retry loop must complete
                    reads["calls"] += 1
                    buf = iov[0]
                    chunk = os.read(fd, min(3, buf.nbytes))
                    if not chunk:
                        return 0
                    buf[: len(chunk)] = chunk
                    return len(chunk)

                with _runner_env(path, preadv=_partial):
                    got = md._md_preadv_all(_partial, fd, memoryview(bytearray(16)), 0, 16)
            finally:
                os.close(fd)
            assert got == 16
            assert reads["calls"] >= 6  # 16 bytes / 3 per call
        # read exactly once per call until nbytes reached

    def test_eof_short_read_detected(self):
        # Request 16 bytes from an 8-byte file -> preadv hits EOF -> the
        # runner detects a short read and reports a fallback reason.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            with open(path, "wb") as f:
                f.write(bytes(8))
            waves = [{
                "keys": ["w"], "rel_byte_start": 0, "rel_byte_end": 16,
                "tensor_bytes": 16,
                "tensors": [{"key": "w", "dtype": "BF16", "shape": [8],
                             "rel_off": 0, "rel_end": 16, "nbytes": 16}],
            }]
            params = {"w": torch.zeros(8, dtype=torch.bfloat16)}
            with _runner_env(path):
                result = md._md_run_waves(params, None, path, waves, torch.bfloat16, 0)
            assert result is not None and result[0] is None
            assert "preadv_short_read" in result[1]

    def test_short_read_in_runner_returns_fallback_reason(self):
        # A preadv implementation that returns at most 2 bytes per call and
        # the file is only 6 bytes -> the retry loop accumulates but cannot
        # reach the 16-byte wave size -> named fallback reason.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            with open(path, "wb") as f:
                f.write(bytes(6))
            waves = [{
                "keys": ["w"], "rel_byte_start": 0, "rel_byte_end": 16,
                "tensor_bytes": 16,
                "tensors": [{"key": "w", "dtype": "BF16", "shape": [8],
                             "rel_off": 0, "rel_end": 16, "nbytes": 16}],
            }]

            def _trunc(fd, iov, offset):
                buf = iov[0]
                chunk = os.read(fd, min(2, buf.nbytes))
                if not chunk:
                    return 0
                buf[: len(chunk)] = chunk
                return len(chunk)

            params = {"w": torch.zeros(8, dtype=torch.bfloat16)}
            with _runner_env(path, preadv=_trunc):
                result = md._md_run_waves(params, None, path, waves, torch.bfloat16, 0)
            assert result is not None and result[0] is None
            assert "preadv_short_read" in result[1]


# ── 6. Slice view math (real tensor shapes) ──────────────────────────────


class TestSliceViewMath(unittest.TestCase):
    def test_bf16_view_shape_dtype_exact(self):
        # Real ZImage attention weight shape: (10240, 3840) BF16.
        nbytes = 10240 * 3840 * 2
        buf = torch.zeros(nbytes, dtype=torch.uint8)
        view = md.slice_tensor_from_buffer(buf, torch.bfloat16, [10240, 3840], 0, nbytes)
        assert tuple(view.shape) == (10240, 3840)
        assert view.dtype == torch.bfloat16
        assert view.is_contiguous()

    def test_bf16_view_at_nonzero_offset(self):
        nbytes = 64
        buf = torch.arange(64, dtype=torch.uint8)
        view = md.slice_tensor_from_buffer(buf, torch.bfloat16, [4, 4], 16, 32)
        assert tuple(view.shape) == (4, 4)
        assert view.dtype == torch.bfloat16
        assert view.view(torch.uint8).reshape(-1).tolist() == list(range(16, 48))


# ── 7. Slot reuse-wait + 2-slot ring + grow-to-largest ───────────────────


class TestSlotReuse(unittest.TestCase):
    def _make_multi_waves(self):
        waves = []
        off = 0
        for i in range(4):
            nbytes = 8
            waves.append({
                "keys": [f"t{i}"], "rel_byte_start": off, "rel_byte_end": off + nbytes,
                "tensor_bytes": nbytes,
                "tensors": [{"key": f"t{i}", "dtype": "BF16", "shape": [4],
                             "rel_off": off, "rel_end": off + nbytes, "nbytes": nbytes}],
            })
            off += nbytes
        return waves, off

    def test_two_slots_ring_and_reuse_wait(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            waves, total = self._make_multi_waves()
            with open(path, "wb") as f:
                f.write(bytes(total))
            params = {f"t{i}": torch.zeros(4, dtype=torch.bfloat16) for i in range(4)}
            allocs = []
            real_empty = torch.empty

            def _counting_empty(*a, **k):
                if k.get("pin_memory"):
                    allocs.append(a[0])
                return real_empty(*a, **k)

            # Track the pending-event syncs (reuse waits) and global syncs.
            event_syncs = []
            real_event = torch.cuda.Event

            class _TrackEvent(_FakeEvent):
                def synchronize(self):
                    event_syncs.append(1)

            with _runner_env(path), \
                 mock.patch.object(torch, "empty", _counting_empty), \
                 mock.patch.object(torch.cuda, "Event", _TrackEvent), \
                 mock.patch.object(torch.cuda, "synchronize",
                                   lambda *a, **k: event_syncs.append("global")):
                result = md._md_run_waves(params, None, path, waves, torch.bfloat16, 0)
            metrics, wave_events = result
            # 1 pinned self-test probe + grow-to-largest: the 2 slots stay 8 B.
            assert len(allocs) == 3, allocs
            assert metrics["pinned_bytes"] == 2 * 8
            # wave 2 waits on slot 0's event; wave 3 on slot 1's: exactly 2
            # reuse waits, and NEVER a global synchronize inside the runner.
            assert len(wave_events) == 4
            assert event_syncs.count(1) == 2, event_syncs
            assert "global" not in event_syncs, event_syncs

    def test_grow_to_largest_realloc_replaces(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            waves = []
            off = 0
            for i, size in enumerate((8, 8, 64, 64)):
                waves.append({
                    "keys": [f"t{i}"], "rel_byte_start": off, "rel_byte_end": off + size,
                    "tensor_bytes": size,
                    "tensors": [{"key": f"t{i}", "dtype": "BF16",
                                 "shape": [size // 2], "rel_off": off,
                                 "rel_end": off + size, "nbytes": size}],
                })
                off += size
            with open(path, "wb") as f:
                f.write(bytes(off))
            params = {f"t{i}": torch.zeros(s // 2, dtype=torch.bfloat16)
                      for i, s in enumerate((8, 8, 64, 64))}
            allocs = []
            real_empty = torch.empty

            def _counting_empty(*a, **k):
                if k.get("pin_memory"):
                    allocs.append(a[0])
                return real_empty(*a, **k)

            with _runner_env(path), mock.patch.object(torch, "empty", _counting_empty):
                result = md._md_run_waves(params, None, path, waves, torch.bfloat16, 0)
            metrics, _ = result
            # 1 pinned self-test probe + slot 0: 8 -> 64 (grow), slot 1: 8 -> 64.
            assert len(allocs) == 5, allocs
            assert metrics["pinned_bytes"] == 8 + 8 + 64 + 64


# ── 8. No param.data rebinding ───────────────────────────────────────────


class TestNoDataRebinding(unittest.TestCase):
    def test_copies_target_existing_params(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            waves = [{
                "keys": ["w"], "rel_byte_start": 0, "rel_byte_end": 16,
                "tensor_bytes": 16,
                "tensors": [{"key": "w", "dtype": "BF16", "shape": [8],
                             "rel_off": 0, "rel_end": 16, "nbytes": 16}],
            }]
            with open(path, "wb") as f:
                f.write(bytes(16))
            w = torch.zeros(8, dtype=torch.bfloat16)
            params = {"w": w}
            copies = []
            orig_copy = torch.Tensor.copy_

            def _record_copy(dst, src, non_blocking=False):
                copies.append(dst)
                return orig_copy(dst, src, non_blocking=non_blocking)

            with _runner_env(path), mock.patch.object(torch.Tensor, "copy_", _record_copy):
                result = md._md_run_waves(params, None, path, waves, torch.bfloat16, 0)
            assert result[0] is not None
            assert len(copies) == 1
            assert copies[0] is w, "copy_ must target the EXISTING param storage"


# ── 9. Failure injection at every stage ──────────────────────────────────


class TestFailureInjection(unittest.TestCase):
    def test_pipeline_never_raises_and_returns_none_on_failure(self):
        # Each stage failure must return None (fresh fallback), never raise.
        from comfymodal_runtime.trace import RuntimeTrace
        config = _ZImageConfig()
        header = _tiny_pipeline_header()
        derived = _make_derived(config, header)

        def _mk_env(**patches):
            return contextlib.ExitStack()

        def _run(derive="__default__", **patches):
            trace = RuntimeTrace(request_id="md-fail", process="remote")
            _dv = derived if derive == "__default__" else derive
            with _runner_env("C:/nope/x.safetensors", preadv=_fake_preadv), \
                 mock.patch.object(md, "_ring_resolve_unet_path",
                                   return_value="C:/nope/x.safetensors"), \
                 mock.patch.object(md, "_ring_derive_config", return_value=_dv), \
                 mock.patch.object(md, "_c6_comfy_fn", side_effect=_fake_comfy_fn), \
                 mock.patch.object(md, "_md_eligible", return_value=(True, "")):
                with contextlib.ExitStack() as stack:
                    for k, v in patches.items():
                        stack.enter_context(mock.patch.object(md, k, v))
                    _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
                    try:
                        result = md._md_try_pipeline(None, None, {"unet_name": "x"}, None)
                    finally:
                        mp._ACTIVE_REQUEST_TRACE.reset(_tok)
            return result, trace

        # config derivation fails
        result, trace = _run(derive=None)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_meta_direct_pipeline"]
        assert evs and evs[-1].metadata["status"] == "fallback"
        assert "config_derivation_failed" in evs[-1].metadata["reason"]

        # family not ZImage (post-derivation gate)
        bad_config = _FakeConfig()  # type name "FakeConfig" != "ZImage"
        bad_derived = (bad_config, {}, header, 1, "")
        result, trace = _run(derive=bad_derived)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_meta_direct_pipeline"]
        assert "family_not_zimage" in evs[-1].metadata["reason"]

        # transform not independent
        def _bad_transform(sd):
            return {"zzz": sd.get("weight")}

        bad_config2 = _ZImageConfig()
        bad_config2.process_unet_state_dict = _bad_transform
        bad_derived2 = (bad_config2, derived[1], header, 1, "")
        result, trace = _run(derive=bad_derived2)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_meta_direct_pipeline"]
        assert "transform_not_independent" in evs[-1].metadata["reason"]

        # key<->param mismatch: an sd key that maps to no param/buffer
        ghost_meta_sd = dict(derived[1])
        ghost_meta_sd["ghost"] = torch.empty(4, dtype=torch.bfloat16, device="meta")
        bad_config3 = _ZImageConfig()  # identity transform, unlike bad_config2
        bad_derived3 = (bad_config3, ghost_meta_sd, header, 1, "")
        result, trace = _run(derive=bad_derived3)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_meta_direct_pipeline"]
        assert "key_param_mismatch" in evs[-1].metadata["reason"]

        # meta get_model failure: config.get_model builds a CPU module
        class _CpuModel(_TinyModel):
            pass

        class _CpuConfig(_FakeConfig):
            def get_model(self, sd, prefix=""):
                m = _CpuModel()
                m.model_config = self
                # Explicit device=cpu defeats the caller's meta-device context,
                # so the constructed params are REAL (non-meta).
                m.diffusion_model = torch.nn.Linear(
                    8, 4, dtype=torch.bfloat16, device="cpu")
                return m

        cpu_config = type("ZImage", (_CpuConfig,), {})()
        cpu_derived = (cpu_config, derived[1], header, 1, "")
        result, trace = _run(derive=cpu_derived)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_meta_direct_pipeline"]
        assert "meta_construction_failed" in evs[-1].metadata["reason"]

        # sampling fix incomplete
        def _bad_ms_fn(config, mtype):
            s = _FakeSampling()
            s.sigmas = torch.empty(10, device="meta")
            return s

        def _comfy_with_bad_ms(mod, attr, fallback=None):
            if mod == "comfy.model_base" and attr == "model_sampling":
                return _bad_ms_fn
            return _fake_comfy_fn(mod, attr, fallback)

        result, trace = _run(_c6_comfy_fn=_comfy_with_bad_ms)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_meta_direct_pipeline"]
        assert "sampling_fix_incomplete" in evs[-1].metadata["reason"]

    @unittest.skipUnless(_HAS_CUDA, "CUDA required for the full pipeline")
    def test_runner_failures_discard_and_cleanup(self):
        # preadv raising -> md_run error -> fallback, no partial publish.
        from comfymodal_runtime.trace import RuntimeTrace

        def _boom_preadv(fd, iov, offset):
            raise OSError("preadv boom")

        config = _ZImageConfig()
        derived = _make_derived(config, _tiny_pipeline_header())
        empties = []

        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            trace = RuntimeTrace(request_id="md-runfail", process="remote")
            with _runner_env(path, preadv=_boom_preadv), \
                 mock.patch.object(md, "_ring_resolve_unet_path", return_value=path), \
                 mock.patch.object(md, "_ring_derive_config", return_value=derived), \
                 mock.patch.object(md, "_md_eligible", return_value=(True, "")), \
                 mock.patch.object(md, "_c6_comfy_fn", side_effect=_fake_comfy_fn), \
                 mock.patch.object(torch.cuda, "empty_cache",
                                   lambda *a, **k: empties.append(1)):
                _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
                try:
                    result = md._md_try_pipeline(None, None, {"unet_name": "x"}, None)
                finally:
                    mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        assert empties, "empty_cache must be called on failure cleanup"
        evs = [e for e in trace.events if e.name == "unet_meta_direct_pipeline"]
        assert evs and evs[-1].metadata["status"] == "fallback"
        assert "md_run" in evs[-1].metadata["reason"]


# ── 10. _load_unet branch (flag off -> original; on -> patcher/fallback) ─


class _FakeKey:
    unet_identity = "unet:test"


class _FakeBridge:
    def __init__(self):
        self._trace = None
        self._model_key = _FakeKey()
        self.requests = {"unet": [{"unet_name": "z.safetensors",
                                   "weight_dtype": "default"}]}
        self.invoked = None

    def _find_request(self, bucket, identity):
        lst = self.requests.get(bucket, [])
        return lst[0] if lst else None

    def _invoke_original(self, class_name, kwargs):
        self.invoked = (class_name, kwargs)
        return ("original_unet",)


class TestLoadUnetBranch(unittest.TestCase):
    def _run(self, md_enabled, md_result=None):
        bridge = _FakeBridge()
        called = {"ring": 0, "md": 0}

        def _fake_ring(*a, **k):
            called["ring"] += 1
            return None

        def _fake_md(*a, **k):
            called["md"] += 1
            return md_result

        with mock.patch.dict(os.environ, {
            "COMFYMODAL_V2_UNET_META_DIRECT": "on" if md_enabled else "",
            "COMFYMODAL_V2_UNET_PINNED_RING": "",
        }, clear=True), \
             mock.patch.object(mp, "_ring_pipeline_enabled", return_value=False), \
             mock.patch.object(mp, "_ring_try_pipeline", side_effect=_fake_ring), \
             mock.patch.object(mp, "_md_pipeline_enabled",
                               return_value=bool(md_enabled)), \
             mock.patch.object(mp, "resolve_unet_effective_dtype",
                               return_value=("default", "default")), \
             mock.patch.object(mp, "collect_unet_runtime_state", return_value={}), \
             mock.patch.object(mp, "register_unet_forward_probe",
                               lambda *a, **k: None), \
             mock.patch.object(md, "_md_try_pipeline", side_effect=_fake_md), \
             mock.patch("builtins.print"):
            _tok = mp._ACTIVE_REQUEST_TRACE.set(None)
            try:
                result = mp.V2LoaderBridge._load_unet(bridge, _FakeKey())
            finally:
                mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        return bridge, called, result

    def test_flag_off_original_loader_path(self):
        bridge, called, result = self._run(md_enabled=False)
        assert called["md"] == 0, called
        assert called["ring"] == 0
        assert bridge.invoked is not None and bridge.invoked[0] == "UNETLoader"
        assert result == "original_unet"

    def test_flag_on_meta_direct_patcher_used(self):
        bridge, called, result = self._run(md_enabled=True, md_result=("patcher",))
        assert called["md"] == 1
        assert bridge.invoked is None, "original must not run when patcher returned"
        assert result == "patcher"

    def test_flag_on_pipeline_failure_fresh_original_fallback(self):
        bridge, called, result = self._run(md_enabled=True, md_result=None)
        assert called["md"] == 1
        assert bridge.invoked is not None and bridge.invoked[0] == "UNETLoader"
        assert result == "original_unet"


# ── 11. probe-mode machinery + salvage probe untouched ───────────────────


class TestProbeMachineryUntouched(unittest.TestCase):
    def test_salvage_probe_module_still_importable_and_runs_offline(self):
        import comfymodal_runtime.unet_salvage_probe as usp
        assert callable(usp.build_wave_ranges)
        assert callable(usp.run_unet_mechanism_probes)
        header = _tiny_pipeline_header()
        waves = usp.build_wave_ranges(header)
        assert waves is not None and len(waves) == 1

    def test_v1_ring_flag_functions_unchanged(self):
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_PINNED_RING": "probe"}, clear=True):
            assert mp._ring_flag_value() == "invalid"
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_PINNED_RING": "1"}, clear=True):
            assert mp._ring_flag_value() == "on"

    def test_runtime_env_passthrough(self):
        import comfymodal_runtime.modal_app as _ma
        env = _ma._runtime_env()
        assert env.get("COMFYMODAL_V2_UNET_META_DIRECT", None) == ""
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_META_DIRECT": "on"}, clear=False):
            env2 = _ma._runtime_env()
        assert env2["COMFYMODAL_V2_UNET_META_DIRECT"] == "on"


# ── 12. Sub-chunked preadv + self-test + partial-progress diagnostics ────


class TestPreadvChunking(unittest.TestCase):
    def _wave(self, nbytes=16, key="w"):
        return [{
            "keys": [key], "rel_byte_start": 0, "rel_byte_end": nbytes,
            "tensor_bytes": nbytes,
            "tensors": [{"key": key, "dtype": "BF16", "shape": [nbytes // 2],
                         "rel_off": 0, "rel_end": nbytes, "nbytes": nbytes}],
        }]

    def test_chunk_sizes_bounded_and_offsets_advance(self):
        # Wave of 16 bytes with the chunk cap patched to 6 -> preadv calls at
        # offsets 0, 6, 12 with sizes 6, 6, 4; every call <= cap; wave exact.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            with open(path, "wb") as f:
                f.write(bytes(20))
            params = {"w": torch.zeros(8, dtype=torch.bfloat16)}
            calls = []

            def _rec(fd, iov, offset):
                calls.append((int(offset), int(iov[0].nbytes)))
                return _fake_preadv(fd, iov, offset)

            with mock.patch.object(md, "_MD_PREADV_CHUNK_BYTES", 6), \
                 _runner_env(path, preadv=_rec):
                result = md._md_run_waves(params, None, path, self._wave(16), torch.bfloat16, 0)
            assert result[0] is not None, result
            metrics, _ = result
            # self-test probe (20 B at offset 0) then 6/6/4 wave chunks.
            assert calls == [(0, 20), (0, 6), (6, 6), (12, 4)], calls
            assert all(n <= 6 for _, n in calls[1:])
            assert metrics["preadv_bytes"] == 16
            assert metrics["preadv_selftest_wall_ms"] is not None

    def test_chunk_assembly_exact_and_param_values_match(self):
        # Pattern-filled file; chunked assembly must reproduce the exact byte
        # stream in the destination param (bf16 reinterpretation).
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            with open(path, "wb") as f:
                f.write(bytes(range(16)))
            w = torch.zeros(8, dtype=torch.bfloat16)
            params = {"w": w}
            with mock.patch.object(md, "_MD_PREADV_CHUNK_BYTES", 6), \
                 _runner_env(path):
                result = md._md_run_waves(params, None, path, self._wave(16), torch.bfloat16, 0)
            assert result[0] is not None, result
            expected = torch.frombuffer(bytes(range(16)), dtype=torch.bfloat16).clone()
            assert torch.equal(w, expected), (w, expected)

    def test_partial_return_within_chunk_retries(self):
        # preadv returns at most 2 bytes per call: each 6-byte chunk needs
        # 3 retries; the sub-chunk loop still assembles the full wave.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            with open(path, "wb") as f:
                f.write(bytes(range(16)))
            params = {"w": torch.zeros(8, dtype=torch.bfloat16)}
            calls = {"n": 0}

            def _partial(fd, iov, offset):
                calls["n"] += 1
                buf = iov[0]
                n = min(2, buf.nbytes)
                os.lseek(fd, offset, os.SEEK_SET)
                data = os.read(fd, n)
                if not data:
                    return 0
                buf[: len(data)] = data
                return len(data)

            with mock.patch.object(md, "_MD_PREADV_CHUNK_BYTES", 6), \
                 _runner_env(path, preadv=_partial):
                result = md._md_run_waves(params, None, path, self._wave(16), torch.bfloat16, 0)
            assert result[0] is not None, result
            metrics, _ = result
            assert metrics["preadv_bytes"] == 16
            assert calls["n"] >= 8  # self-test + 3 chunks x >= 2 retries

    def test_short_read_on_later_chunk_reports_details(self):
        # File has 10 bytes: chunk 0 (6 B, offset 0) ok; chunk 1 wants 6 B at
        # offset 6 but only 4 remain -> short read with exact fail fields and
        # partial progress preserved (6 bytes read).
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            with open(path, "wb") as f:
                f.write(bytes(10))
            params = {"w": torch.zeros(8, dtype=torch.bfloat16)}
            with mock.patch.object(md, "_MD_PREADV_CHUNK_BYTES", 6), \
                 _runner_env(path):
                result = md._md_run_waves(params, None, path, self._wave(16), torch.bfloat16, 0)
            assert result is not None and result[0] is None
            assert "preadv_short_read" in result[1], result
            partial = result[2]
            assert partial["preadv_bytes"] == 6, partial
            assert partial["fail_wave_idx"] == 0, partial
            assert partial["fail_wave_offset"] == 6, partial
            assert partial["fail_requested_bytes"] == 6, partial
            assert partial["fail_got_bytes"] == 4, partial


class TestPreadvSelftest(unittest.TestCase):
    def _wave(self, nbytes=16):
        return [{
            "keys": ["w"], "rel_byte_start": 0, "rel_byte_end": nbytes,
            "tensor_bytes": nbytes,
            "tensors": [{"key": "w", "dtype": "BF16", "shape": [nbytes // 2],
                         "rel_off": 0, "rel_end": nbytes, "nbytes": nbytes}],
        }]

    def test_short_probe_volume_unsupported_fails_before_waves(self):
        # A preadv that returns at most 4 bytes per call and 0 beyond offset
        # 8 simulates a volume that cannot fill the 16-byte probe -> named
        # reason, no wave processed.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            with open(path, "wb") as f:
                f.write(bytes(16))
            params = {"w": torch.zeros(8, dtype=torch.bfloat16)}

            def _short(fd, iov, offset):
                if int(offset) >= 8:
                    return 0
                buf = iov[0]
                n = min(4, buf.nbytes)
                os.lseek(fd, int(offset), os.SEEK_SET)
                data = os.read(fd, n)
                if not data:
                    return 0
                buf[: len(data)] = data
                return len(data)

            with _runner_env(path, preadv=_short):
                result = md._md_run_waves(params, None, path, self._wave(16), torch.bfloat16, 0)
            assert result is not None and result[0] is None
            assert "preadv_volume_unsupported" in result[1], result
            assert result[2]["preadv_bytes"] == 0  # no wave started

    def test_full_probe_then_waves_proceed(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            with open(path, "wb") as f:
                f.write(bytes(16))
            params = {"w": torch.zeros(8, dtype=torch.bfloat16)}
            with _runner_env(path):
                result = md._md_run_waves(params, None, path, self._wave(16), torch.bfloat16, 0)
            assert result[0] is not None, result
            metrics, _ = result
            assert metrics["preadv_selftest_wall_ms"] is not None
            assert metrics["preadv_bytes"] == 16


class TestFadviseErrorRecorded(unittest.TestCase):
    def test_fadvise_failure_recorded_not_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "blob.bin")
            with open(path, "wb") as f:
                f.write(bytes(16))
            params = {"w": torch.zeros(8, dtype=torch.bfloat16)}

            def _boom(*a, **k):
                raise OSError("fadvise boom")

            with _runner_env(path, fadvise=_boom):
                result = md._md_run_waves(params, None, path, [{
                    "keys": ["w"], "rel_byte_start": 0, "rel_byte_end": 16,
                    "tensor_bytes": 16,
                    "tensors": [{"key": "w", "dtype": "BF16", "shape": [8],
                                 "rel_off": 0, "rel_end": 16, "nbytes": 16}],
                }], torch.bfloat16, 0)
            assert result[0] is not None, result
            metrics, _ = result
            assert metrics["fadvise_error"] and "OSError" in metrics["fadvise_error"]
            assert metrics["preadv_bytes"] == 16


@unittest.skipUnless(_HAS_CUDA, "CUDA required for the full pipeline")
class TestPartialMetricsMergedIntoEmit(unittest.TestCase):
    def test_failure_event_carries_partial_progress(self):
        # _md_run_waves fails after 6 bytes on wave 3: the emitted fallback
        # event must carry the merged partial progress + fail details.
        from comfymodal_runtime.trace import RuntimeTrace
        config = _ZImageConfig()
        derived = _make_derived(config, _tiny_pipeline_header())
        partial = {
            "preadv_bytes": 6, "preadv_io_wall_ms": 3.5,
            "fail_wave_idx": 3, "fail_wave_offset": 192,
            "fail_requested_bytes": 64, "fail_got_bytes": 32,
        }
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            trace = RuntimeTrace(request_id="md-partial", process="remote")
            with _runner_env(path), \
                 mock.patch.object(md, "_ring_resolve_unet_path", return_value=path), \
                 mock.patch.object(md, "_ring_derive_config", return_value=derived), \
                 mock.patch.object(md, "_md_eligible", return_value=(True, "")), \
                 mock.patch.object(md, "_c6_comfy_fn", side_effect=_fake_comfy_fn), \
                 mock.patch.object(md, "_md_run_waves",
                                   return_value=(None, "preadv_short_read", partial)):
                _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
                try:
                    result = md._md_try_pipeline(None, None, {"unet_name": "x"}, None)
                finally:
                    mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_meta_direct_pipeline"]
        assert evs and evs[-1].metadata["status"] == "fallback"
        assert "preadv_short_read" in evs[-1].metadata["reason"]
        assert evs[-1].metadata.get("preadv_bytes") == 6
        assert evs[-1].metadata.get("fail_wave_idx") == 3
        assert evs[-1].metadata.get("fail_got_bytes") == 32


if __name__ == "__main__":
    unittest.main()
