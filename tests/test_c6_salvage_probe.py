"""Focused offline tests for the C6 UNET salvage mechanism probe
(``comfymodal_runtime.unet_salvage_probe``).

Everything here is CPU-only and offline: no real CUDA work, no real
ZImage file.  OS/Linux-only capabilities (``os.preadv``,
``os.posix_fadvise``, GDS, ``cudaHostRegister``) are monkeypatched or
degrade to named ``skipped``/``error`` entries exactly as they do on the
Windows dev box.  The probe's real exercise happens on the Linux Modal
container.
"""

from __future__ import annotations

import contextlib
import gc
import io
import json
import os
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import torch

import comfymodal_runtime.model_preload as mp
import comfymodal_runtime.unet_salvage_probe as usp

try:
    import safetensors.torch as _st_torch
    import safetensors as _st
    _HAS_SAFETENSORS = True
except Exception:  # pragma: no cover - skip on systems without safetensors
    _HAS_SAFETENSORS = False


def _write_tiny_safetensors(td):
    """Three mixed-dtype tensors with non-aligned sizes."""
    path = os.path.join(td, "tiny.safetensors")
    _st_torch.save_file({
        "a": torch.randn(8, 8, dtype=torch.float32),
        "b": torch.randn(5, dtype=torch.float16),
        "c": torch.randn(3, 3, dtype=torch.bfloat16),
    }, path)
    return path


def _synth_header(sizes, dtype="F32", start=0):
    """Synthetic packed header with tensor sizes in bytes."""
    header = {}
    off = int(start)
    for i, s in enumerate(sizes):
        header[f"t{i}"] = {"dtype": dtype, "shape": [int(s)],
                           "data_offsets": [off, off + int(s)]}
        off += int(s)
    return header


def _orchestrator_env(path, cuda_available=False, subprocess_stdout="525.60.13\n"):
    """ExitStack mocking the platform capabilities so the orchestrator runs
    deterministically offline: CUDA absent, preadv/fadvise removed, and the
    gds nvidia-smi subprocess faked."""
    _stack = contextlib.ExitStack()
    _stack.enter_context(mock.patch.object(torch.cuda, "is_available",
                                           return_value=cuda_available))
    _stack.enter_context(mock.patch.object(
        usp._subprocess, "run",
        return_value=SimpleNamespace(stdout=subprocess_stdout, stderr="")))
    _stack.enter_context(mock.patch.object(usp._os, "preadv", None, create=True))
    _stack.enter_context(mock.patch.object(usp._os, "posix_fadvise", None, create=True))
    return _stack


class _FakeCudart:
    def __init__(self, register=None, unregister=None, get_attr=None,
                 error_str=None):
        self.cudaHostRegister = register
        self.cudaHostUnregister = unregister
        self.cudaDeviceGetAttribute = get_attr
        self.cudaGetErrorString = error_str or (lambda rc: "fake_cuda_error")


# ── 1. build_wave_ranges ─────────────────────────────────────────────────


class TestBuildWaveRanges(unittest.TestCase):
    def test_contiguous_order_packing_and_reconcile(self):
        # 10 tensors of 32 bytes each, target 64 -> 2-tensor waves.
        header = _synth_header([32] * 10)
        waves = usp.build_wave_ranges(header, wave_target_bytes=64)
        assert waves is not None
        assert [w["keys"] for w in waves] == [["t0", "t1"], ["t2", "t3"],
                                              ["t4", "t5"], ["t6", "t7"],
                                              ["t8", "t9"]]
        # Order preserved (header order).
        all_keys = [k for w in waves for k in w["keys"]]
        assert all_keys == [f"t{i}" for i in range(10)]
        for w in waves:
            # Per-wave byte contiguity.
            assert w["rel_byte_start"] == w["tensors"][0]["rel_off"]
            assert w["rel_byte_end"] == w["tensors"][-1]["rel_end"]
            assert w["rel_byte_end"] - w["rel_byte_start"] == w["tensor_bytes"]
            # Running contiguity: tensor i's rel_off == previous rel_end.
            prev_end = w["tensors"][0]["rel_off"]
            for t in w["tensors"]:
                assert t["rel_off"] == prev_end
                prev_end = t["rel_end"]
            # Per-tensor nbytes reconcile.
            assert sum(t["nbytes"] for t in w["tensors"]) == w["tensor_bytes"]
        # Sum reconciles to total data bytes.
        assert sum(w["tensor_bytes"] for w in waves) == 320
        # Intervals exactly cover [0, total) with no gaps/overlaps.
        intervals = sorted((w["rel_byte_start"], w["rel_byte_end"]) for w in waves)
        cursor = 0
        for s, e in intervals:
            assert s == cursor
            cursor = e
        assert cursor == 320

    def test_single_huge_tensor_gets_own_wave(self):
        header = _synth_header([100, 30, 30])
        waves = usp.build_wave_ranges(header, wave_target_bytes=64)
        assert waves is not None
        assert len(waves) == 2
        assert waves[0]["keys"] == ["t0"]
        assert waves[0]["tensor_bytes"] == 100
        assert waves[1]["keys"] == ["t1", "t2"]
        assert waves[1]["tensor_bytes"] == 60

    def test_tensor_over_max_returns_none(self):
        header = _synth_header([1000])
        assert usp.build_wave_ranges(header, wave_target_bytes=64, max_wave_bytes=128) is None

    def test_empty_and_none_inputs(self):
        assert usp.build_wave_ranges(None) == []
        assert usp.build_wave_ranges({}) == []
        assert usp.build_wave_ranges({"__metadata__": {"x": "y"}}) == []

    def test_keys_filter_preserves_order(self):
        header = _synth_header([10, 20, 30])
        waves = usp.build_wave_ranges(header, keys=["t2", "t0"], wave_target_bytes=64)
        assert waves is not None
        assert [k for w in waves for k in w["keys"]] == ["t2", "t0"]
        # Wave reflects the t2 (start 30, 30 bytes) then t0 (start 0) -> the
        # contiguity rule opens a new wave between them.
        assert len(waves) == 2

    def test_gap_in_file_splits_wave(self):
        header = _synth_header([16, 16])
        header["t0"] = {"dtype": "F32", "shape": [16], "data_offsets": [0, 16]}
        header["t1"] = {"dtype": "F32", "shape": [16], "data_offsets": [64, 80]}
        waves = usp.build_wave_ranges(header, wave_target_bytes=1024)
        assert waves is not None
        assert len(waves) == 2  # contiguity break forces a new wave
        assert waves[0]["keys"] == ["t0"] and waves[1]["keys"] == ["t1"]
        assert waves[0]["rel_byte_start"] == 0 and waves[0]["rel_byte_end"] == 16
        assert waves[1]["rel_byte_start"] == 64 and waves[1]["rel_byte_end"] == 80
        # No overlap between the two intervals.
        assert waves[0]["rel_byte_end"] <= waves[1]["rel_byte_start"]


# ── 2. Real tiny safetensors file ────────────────────────────────────────


@unittest.skipUnless(_HAS_SAFETENSORS, "safetensors not available")
class TestRealSafetensorsFile(unittest.TestCase):
    def test_header_and_data_start_offset_match_file_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            header = mp._c6_parse_safetensors_header(path)
            assert header is not None
            with open(path, "rb") as f:
                head_len = struct.unpack("<Q", f.read(8))[0]
                raw = json.loads(f.read(head_len).decode("utf-8"))
            # The parsed header must mirror the ACTUAL on-disk JSON header
            # (safetensors writes compact JSON, so compare structure, not
            # a re-serialized length).
            for key, info in header.items():
                if key == "__metadata__":
                    continue
                assert info["dtype"] == raw[key]["dtype"]
                assert info["shape"] == raw[key]["shape"]
                assert info["data_offsets"] == raw[key]["data_offsets"]
            # Data region ends exactly at EOF: header (8 + N) + packed tensor
            # bytes == file size (no alignment padding).
            rec = usp.reconcile_header_bytes(header)
            assert rec is not None
            assert 8 + head_len + rec[0] == os.path.getsize(path)

    def test_wave_ranges_match_actual_file_layout(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            header = mp._c6_parse_safetensors_header(path)
            with open(path, "rb") as f:
                head_len = struct.unpack("<Q", f.read(8))[0]
            total = os.path.getsize(path) - (8 + head_len)
            waves = usp.build_wave_ranges(header)
            assert waves is not None
            assert len(waves) == 1
            w = waves[0]
            assert w["rel_byte_start"] == 0
            assert w["rel_byte_end"] == total
            # tensor rel offsets match header data_offsets exactly
            for t in w["tensors"]:
                assert (t["rel_off"], t["rel_end"]) == tuple(header[t["key"]]["data_offsets"])
            rec = usp.reconcile_header_bytes(header)
            assert rec is not None
            assert rec[0] == total

    def test_slice_tensor_from_buffer_reproduces_get_tensor(self):
        _tmp = tempfile.TemporaryDirectory()
        try:
            path = _write_tiny_safetensors(_tmp.name)
            header = mp._c6_parse_safetensors_header(path)
            with open(path, "rb") as f:
                head_len = struct.unpack("<Q", f.read(8))[0]
                f.seek(8 + head_len)
                data = f.read()
            buf = torch.frombuffer(bytearray(data), dtype=torch.uint8)
            dtype_map = {"F32": torch.float32, "F16": torch.float16,
                         "BF16": torch.bfloat16}
            so = _st.safe_open(path, framework="pt", device="cpu")
            try:
                for key, info in header.items():
                    offs = info["data_offsets"]
                    nbytes = offs[1] - offs[0]
                    want = so.get_tensor(key)
                    got = usp.slice_tensor_from_buffer(
                        buf, dtype_map[info["dtype"]], info["shape"],
                        offs[0], nbytes)
                    assert tuple(got.shape) == tuple(want.shape)
                    assert got.dtype == want.dtype
                    assert torch.equal(got, want)
            finally:
                usp._safe_open_exit(so)
                gc.collect()
        finally:
            try:
                _tmp.cleanup()
            except PermissionError:  # pragma: no cover - Windows mmap lock
                pass


# ── 3. page_align_range math ─────────────────────────────────────────────


class TestPageAlignRange(unittest.TestCase):
    def test_boundary_math(self):
        assert usp.page_align_range(0, 100) == (0, 4096)
        assert usp.page_align_range(1, 4097) == (0, 8192)
        assert usp.page_align_range(4096, 8192) == (4096, 8192)
        assert usp.page_align_range(4095, 4096) == (0, 4096)
        assert usp.page_align_range(0, 0) == (0, 0)
        assert usp.page_align_range(5000, 5000) == (4096, 8192)
        assert usp.page_align_range(0, 4096, page_size=1024) == (0, 4096)
        assert usp.page_align_range(1, 1025, page_size=1024) == (0, 2048)
        assert usp.page_align_range(-10, 10) == (-4096, 4096)

    def test_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            usp.page_align_range(10, 5)
        with self.assertRaises(ValueError):
            usp.page_align_range(0, 10, page_size=0)


# ── 4. reconcile_header_bytes ────────────────────────────────────────────


class TestReconcileHeaderBytes(unittest.TestCase):
    def test_valid_packed_header(self):
        header = _synth_header([10, 20, 30])
        total, per = usp.reconcile_header_bytes(header)
        assert total == 60
        assert per == {"t0": 10, "t1": 20, "t2": 30}

    def test_overlapping_ranges_detected(self):
        header = _synth_header([10, 10])
        header["t1"] = {"dtype": "F32", "shape": [10], "data_offsets": [5, 20]}
        assert usp.reconcile_header_bytes(header) is None

    def test_gapped_ranges_detected(self):
        header = _synth_header([10, 10])
        header["t1"] = {"dtype": "F32", "shape": [10], "data_offsets": [20, 30]}
        assert usp.reconcile_header_bytes(header) is None

    def test_out_of_order_ranges_still_validate_if_contiguous(self):
        # Header order is irrelevant to the byte layout: sorted offsets must
        # cover [0, total) exactly.
        header = _synth_header([10, 10])
        header = {"t1": {"dtype": "F32", "shape": [10], "data_offsets": [10, 20]},
                  "t0": {"dtype": "F32", "shape": [10], "data_offsets": [0, 10]}}
        total, per = usp.reconcile_header_bytes(header)
        assert total == 20
        assert per == {"t0": 10, "t1": 10}

    def test_negative_or_inverted_ranges_detected(self):
        bad = {"x": {"data_offsets": [-5, 10]}}
        assert usp.reconcile_header_bytes(bad) is None
        bad = {"x": {"data_offsets": [10, 5]}}
        assert usp.reconcile_header_bytes(bad) is None

    def test_empty_and_metadata_only(self):
        assert usp.reconcile_header_bytes({}) == (0, {})
        assert usp.reconcile_header_bytes({"__metadata__": {}}) == (0, {})


# ── 5. collect_meta_tensors ──────────────────────────────────────────────


class TestCollectMetaTensors(unittest.TestCase):
    def test_nested_modules_and_plain_trees(self):
        model = torch.nn.Module()
        model.sub = torch.nn.Linear(4, 4)  # real params, ignored
        model.meta_p = torch.nn.Parameter(torch.empty(2, 3, device="meta"))
        model.register_buffer("meta_buf", torch.empty(5, device="meta"))
        model.register_buffer("real_buf", torch.ones(3))

        class Obj:
            pass

        obj = Obj()
        obj.t = torch.empty(5, device="meta")
        obj.d = {"k": torch.empty(2, 2, device="meta"), "real": torch.ones(3)}
        obj.real_attr = torch.ones(4)
        model.plain = obj

        res = usp.collect_meta_tensors(model)
        paths = [p for (p, d, s, n) in res]
        assert "meta_p" in paths
        assert "meta_buf" in paths
        assert "plain.t" in paths
        assert "plain.d.k" in paths
        assert not any("real" in p for p in paths)
        assert not any(p.startswith("sub.") for p in paths)
        # dtype/shape/numel metadata is recorded.
        for path, dtype, shape, numel in res:
            if path == "meta_p":
                assert shape == [2, 3] and numel == 6
            assert isinstance(dtype, str) and isinstance(numel, int)

    def test_ignores_real_tensors_and_cycles(self):
        model = torch.nn.Module()
        model.w = torch.nn.Parameter(torch.zeros(4, 4))  # cpu
        res = usp.collect_meta_tensors(model)
        assert res == []
        # cycle-safe plain object graph
        a = []
        a.append(a)  # self cycle
        res = usp.collect_meta_tensors({"a": a})
        assert res == []


# ── 6. Orchestrator: missing OS APIs degrade to named skips ───────────────


@unittest.skipUnless(_HAS_SAFETENSORS, "safetensors not available")
class TestOrchestratorMissingOsApis(unittest.TestCase):
    def test_missing_preadv_fadvise_skipped_and_no_raise(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            with _orchestrator_env(path) as stack, \
                 mock.patch("sys.stdout", io.StringIO()):
                result = usp.run_unet_mechanism_probes(path)
        assert isinstance(result, dict)
        io_sec = result["sections"]["io"]
        assert io_sec["i_preadv"]["status"] == "skipped"
        assert "unavailable" in io_sec["i_preadv"]["reason"]
        assert io_sec["i_fadvise"]["status"] == "skipped"
        assert "unavailable" in io_sec["i_fadvise"]["reason"]
        assert io_sec["i_reg"]["status"] == "skipped"
        assert result["sections"]["summary"]["preadv_available"] is False

    def test_nonexistent_path_still_returns_dict(self):
        with _orchestrator_env(os.path.join(tempfile.gettempdir(), "nope.safetensors")) as stack, \
             mock.patch("sys.stdout", io.StringIO()):
            result = usp.run_unet_mechanism_probes("C:/definitely/not/here.safetensors")
        assert isinstance(result, dict)
        json.dumps(result)


# ── 7. cudart wrapper behavior ───────────────────────────────────────────


@unittest.skipUnless(_HAS_SAFETENSORS, "safetensors not available")
class TestCudartBehavior(unittest.TestCase):
    def _run_with_cudart(self, path, cudart):
        with _orchestrator_env(path, cuda_available=True), \
             mock.patch.object(torch.cuda, "cudart", return_value=cudart), \
             mock.patch("sys.stdout", io.StringIO()):
            return usp.run_unet_mechanism_probes(path)

    def test_missing_cudart_fns_skipped_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            result = self._run_with_cudart(
                path, _FakeCudart(register=None, unregister=lambda *a, **k: 0))
        i_reg = result["sections"]["io"]["i_reg"]
        assert i_reg["status"] == "skipped"
        assert "unavailable" in i_reg["reason"]

    def test_register_raising_captured_and_later_probes_run(self):
        def boom(*a, **k):
            raise RuntimeError("register boom")

        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            result = self._run_with_cudart(
                path, _FakeCudart(register=boom, unregister=lambda *a, **k: 0))
        i_reg = result["sections"]["io"]["i_reg"]
        assert i_reg["reg_256MiB"]["status"] == "error"
        assert "register boom" in i_reg["reg_256MiB"]["error"]
        # Later i_reg sub-probes still ran.
        assert "reg_256MiB_readonly" in i_reg
        assert "reg_1.5GiB" in i_reg
        # Other io probes still recorded.
        assert result["sections"]["io"]["i_touch"]["status"] == "ok"
        json.dumps(result)


# ── 8. JSON safety + single console line ─────────────────────────────────


@unittest.skipUnless(_HAS_SAFETENSORS, "safetensors not available")
class TestJsonSafetyAndConsole(unittest.TestCase):
    def test_full_result_json_serializable_and_one_console_line(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            buf = io.StringIO()
            with _orchestrator_env(path), mock.patch("sys.stdout", buf):
                result = usp.run_unet_mechanism_probes(path)
        json.dumps(result)  # must not raise
        lines = [ln for ln in buf.getvalue().splitlines()
                 if ln.startswith("[v2.salvage_probe]")]
        assert len(lines) == 1, lines
        assert lines[0].startswith("[v2.salvage_probe] summary=")
        # parse the compact payload back
        payload = json.loads(lines[0].split("summary=", 1)[1])
        assert "secs" in payload and "wall_ms" in payload

    def test_emit_callable_fires_one_event(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            events = []
            with _orchestrator_env(path), mock.patch("sys.stdout", io.StringIO()):
                result = usp.run_unet_mechanism_probes(path, emit=lambda n, m: events.append((n, m)))
        assert len(events) == 1
        assert events[0][0] == "unet_salvage_mechanism_probe"
        assert isinstance(events[0][1], dict)
        assert events[0][1].get("total_wall_ms") is not None
        json.dumps(events[0][1])

    def test_emit_never_raises_when_emit_raises(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            with _orchestrator_env(path), mock.patch("sys.stdout", io.StringIO()):
                result = usp.run_unet_mechanism_probes(
                    path, emit=lambda n, m: (_ for _ in ()).throw(RuntimeError("emit boom")))
        assert isinstance(result, dict)
        json.dumps(result)


# ── 9. Failure isolation ─────────────────────────────────────────────────


@unittest.skipUnless(_HAS_SAFETENSORS, "safetensors not available")
class TestFailureIsolation(unittest.TestCase):
    def test_one_sub_probe_raising_does_not_affect_others(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            with _orchestrator_env(path), \
                 mock.patch.object(usp, "_probe_i_touch",
                                   side_effect=RuntimeError("touch boom")), \
                 mock.patch("sys.stdout", io.StringIO()):
                result = usp.run_unet_mechanism_probes(path)
        io_sec = result["sections"]["io"]
        assert io_sec["i_touch"]["status"] == "error"
        assert "touch boom" in io_sec["i_touch"]["error"]
        assert io_sec["i_fadvise"]["status"] == "skipped"
        assert io_sec["i_preadv"]["status"] == "skipped"
        assert io_sec["i_reg"]["status"] == "skipped"
        assert result["sections"]["file"]["status"] == "ok"
        assert result["sections"]["construction"]["config_derivation"]["status"] == "error"
        assert result["sections"]["summary"]["total_wall_ms"] is not None
        json.dumps(result)

    def test_file_section_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            with _orchestrator_env(path), \
                 mock.patch.object(usp, "_probe_file",
                                   side_effect=RuntimeError("file boom")), \
                 mock.patch("sys.stdout", io.StringIO()):
                result = usp.run_unet_mechanism_probes(path)
        assert result["sections"]["file"]["status"] == "error"
        assert "file boom" in result["sections"]["file"]["error"]
        assert result["sections"]["io"]["i_touch"]["status"] == "ok"
        json.dumps(result)


# ── 10. Bounded pinned allocation (structural) ───────────────────────────


class TestBoundedPinnedAllocations(unittest.TestCase):
    def test_pinned_buffers_allocated_sequentially(self):
        header = _synth_header([100] * 4)  # total_data == 400 bytes
        tracker = {"live": 0, "peak": 0, "total": 0}
        real_empty = torch.empty

        class _Pinned:
            def __init__(self, buf):
                self._buf = buf

            def numpy(self):
                return self._buf.numpy()

            def __del__(self):
                tracker["live"] -= 1

        def _fake_empty(*args, **kwargs):
            if kwargs.get("pin_memory"):
                tracker["live"] += 1
                tracker["peak"] = max(tracker["peak"], tracker["live"])
                tracker["total"] += 1
                return _Pinned(real_empty(*args, **kwargs))
            return real_empty(*args, **kwargs)

        def _fake_preadv(fd, iov, offset):
            return iov[0].nbytes

        with mock.patch.object(torch, "empty", _fake_empty), \
             mock.patch.object(usp._os, "preadv", _fake_preadv, create=True):
            res = usp._preadv_size_runs(-1, None, header, 8, 400, 16)
        # 3 in-bounds ranges + 1 warm repeat == 4 sequential allocations.
        assert tracker["total"] == 4, tracker
        assert tracker["peak"] <= 1, tracker
        assert tracker["live"] == 0, tracker  # all freed
        assert len(res["ranges"]) == 3
        assert [r["bytes_returned"] for r in res["ranges"]] == [16, 16, 16]
        assert res["warm_repeat_wall_ms"] is not None


# ── 11. modal_app passthrough + standalone method wiring ─────────────────


class TestModalAppWiring(unittest.TestCase):
    def test_runtime_env_passthrough(self):
        import comfymodal_runtime.modal_app as _ma
        env = _ma._runtime_env()
        assert env.get("COMFYMODAL_V2_UNET_SALVAGE_PROBE", None) == ""
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_SALVAGE_PROBE": "1"}, clear=False):
            env2 = _ma._runtime_env()
        assert env2["COMFYMODAL_V2_UNET_SALVAGE_PROBE"] == "1"

    def test_method_registered_and_resolves_path(self):
        import comfymodal_runtime.modal_app as _ma
        entry = _ma.ModalRuntimeEntrypoint()
        assert hasattr(entry, "run_unet_mechanism_probe")

        _fake_fp = type("FakeFolderPaths", (), {
            "get_full_path_or_raise": staticmethod(
                lambda folder, name: os.path.join("C:/models", name)),
        })
        calls = []

        def _fake_probe(path):
            calls.append(path)
            return {"status": "ok", "probe": "unet_salvage_mechanism", "sections": {}}

        _saved = sys.modules.get("folder_paths")
        sys.modules["folder_paths"] = _fake_fp
        try:
            with mock.patch.object(usp, "run_unet_mechanism_probes", _fake_probe):
                result = entry.run_unet_mechanism_probe("zimage.safetensors")
        finally:
            if _saved is None:
                sys.modules.pop("folder_paths", None)
            else:
                sys.modules["folder_paths"] = _saved
        assert result["status"] == "ok"
        assert result["model_name"] == "zimage.safetensors"
        assert os.path.normpath(result["resolved_path"]) == os.path.normpath(
            "C:/models/zimage.safetensors")
        assert len(calls) == 1
        assert os.path.normpath(calls[0]) == os.path.normpath("C:/models/zimage.safetensors")

    def test_method_unresolvable_path_reports_error(self):
        import comfymodal_runtime.modal_app as _ma
        entry = _ma.ModalRuntimeEntrypoint()
        _fake_fp = type("FakeFolderPaths", (), {
            "get_full_path_or_raise": staticmethod(lambda folder, name: None),
            "get_full_path": staticmethod(lambda folder, name: None),
        })
        _saved = sys.modules.get("folder_paths")
        sys.modules["folder_paths"] = _fake_fp
        try:
            result = entry.run_unet_mechanism_probe("missing.safetensors")
        finally:
            if _saved is None:
                sys.modules.pop("folder_paths", None)
            else:
                sys.modules["folder_paths"] = _saved
        assert result["status"] == "error"
        assert result["error"] == "model_path_unresolved"


# ── 12. Helper-level edge cases ──────────────────────────────────────────


class TestHelperEdges(unittest.TestCase):
    def test_is_pinned_never_raises(self):
        t = torch.zeros(4)
        assert usp.is_pinned(t) is False
        assert usp.is_pinned(None) is False

    def test_snapshot_rusage_never_raises(self):
        r = usp.snapshot_rusage()
        assert isinstance(r, dict)
        assert set(r.keys()) <= {"rss_bytes", "minflt", "majflt", "utime", "stime"}

    def test_slice_tensor_mixed_dtypes(self):
        buf = torch.frombuffer(bytearray(b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a"),
                               dtype=torch.uint8)
        t = usp.slice_tensor_from_buffer(buf, torch.float16, [2], 2, 4)
        assert t.shape == (2,)
        assert t.dtype == torch.float16
        # little-endian byte layout is preserved exactly
        assert t.view(torch.uint8).tolist() == [0x03, 0x04, 0x05, 0x06]

    def test_collect_meta_depth_bound(self):
        # A chain deeper than 6 levels is not traversed (bounded walk).
        class Node:
            def __init__(self):
                self.child = None
                self.t = None

        root = Node()
        node = root
        for _ in range(8):
            nxt = Node()
            node.child = nxt
            node = nxt
        node.t = torch.empty(2, device="meta")
        res = usp.collect_meta_tensors(root)
        assert res == []  # depth 8 exceeds the depth-6 bound


if __name__ == "__main__":
    unittest.main()
