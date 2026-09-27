"""Focused tests for the Batch C6 measurement-only read/H2D probes (I-1 and I-2).

``COMFYMODAL_V2_UNET_READ_H2D_PIPELINE`` (default OFF, values unset/"off",
"probe", or anything else -> "unsupported" and treated as off):

  - flag off / unsupported -> byte-for-byte production: the original
    ``to()`` is called exactly once and no wave probe event is emitted.
  - phase I-1 (probe): ``_SafeOpenProxy`` records a per-tensor
    materialization series (shape/dtype/nbytes/wall/cum_bytes, capped) and
    emits ``unet_read_h2d_pipeline_probe`` on ``__exit__`` with one console
    line.
  - phase I-2 (probe): ``_fast_disk_replay_to`` replays the H2D as
    byte-boundary waves with per-wave CUDA events, emits
    ``unet_read_h2d_wave_probe``, and never synchronizes (the single
    existing ``finally`` synchronize is reused).
  - eligibility guards: pinned staging precedence, dtype conversion
    requests, non-CUDA targets, and unavailable CUDA all fall back to the
    exact original ``to()``.

No real CUDA or ComfyUI is required: ``torch.device`` descriptors and
mocked ``torch.cuda`` / ``torch.Tensor.to`` keep everything CPU-only.
"""

from __future__ import annotations

import contextlib
import gc
import io
import json
import os
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import torch

import comfymodal_runtime.model_preload as mp
from comfymodal_runtime.model_preload import _SafeOpenProxy
from comfymodal_runtime.trace import RuntimeTrace

_CUDA = torch.device("cuda")


class _FakeEvent:
    """Minimal torch.cuda.Event stand-in recording nothing, reporting a
    fixed elapsed time (1.0 ms) — enough to verify wiring without CUDA."""

    def __init__(self, *a, **k):
        pass

    def record(self):
        pass

    def elapsed_time(self, other):
        return 1.0


# ── Fakes ────────────────────────────────────────────────────────────────


def _make_lane(request_id: str = "c6-probe"):
    trace = RuntimeTrace(request_id=request_id, process="remote")
    lane = mp.ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)
    return trace, lane


def _make_replay_model():
    model = torch.nn.Module()
    model.register_parameter("w", torch.nn.Parameter(torch.zeros(4, 4)))
    return model


def _make_single_param_model():
    model = torch.nn.Module()
    model.register_parameter("w", torch.nn.Parameter(torch.zeros(8, 8)))
    return model


def _make_nested_model():
    model = torch.nn.Module()
    model.sub1 = torch.nn.Linear(4, 4)
    model.sub2 = torch.nn.Module()
    model.sub2.linear = torch.nn.Linear(3, 3)
    model.sub2.register_buffer("buf", torch.zeros(2))
    model.extra = torch.nn.Parameter(torch.zeros(2, 2))
    return model


def _make_replay_record(model, original_to, target, to_kwargs=None, to_args=None):
    return {
        "model": model,
        "model_ref": None,
        "original_to": original_to,
        "to_args": tuple(to_args or ()),
        "to_kwargs": dict(to_kwargs or {}),
        "target": target,
        "timings": {},
    }


@contextlib.contextmanager
def _active_lane(lane):
    token = mp._ACTIVE_LANE_TRACE.set(lane)
    try:
        yield
    finally:
        mp._ACTIVE_LANE_TRACE.reset(token)


def _proxy_series_console_lines(buf) -> list[str]:
    return [ln for ln in buf.getvalue().splitlines() if ln.startswith("[v2.c6_probe]")]


# ── 1. Flag parsing ──────────────────────────────────────────────────────


class TestC6ProbeFlagParsing(unittest.TestCase):
    def test_flag_parsing(self):
        cases = [
            (None, "off"),
            ("", "off"),
            ("off", "off"),
            ("0", "off"),
            ("false", "off"),
            ("no", "off"),
            ("none", "off"),
            ("OFF", "off"),
            ("probe", "probe"),
            ("PROBE", "probe"),
            (" Probe ", "probe"),
            ("1", "unsupported"),
            ("garbage", "unsupported"),
        ]
        for raw, expected in cases:
            env = {} if raw is None else {"COMFYMODAL_V2_UNET_READ_H2D_PIPELINE": raw}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(mp._read_c6_probe_mode(), expected)


# ── 2. Probe off: exact production path ──────────────────────────────────


class TestC6ProbeOffDefaultPath(unittest.TestCase):
    def test_probe_off_calls_original_to_once(self):
        trace, lane = _make_lane()
        model = _make_replay_model()
        calls = []

        def fake_to(m, *a, **k):
            calls.append("to")
            return m

        record = _make_replay_record(model, fake_to, _CUDA)
        with mock.patch.object(mp, "_C6_PROBE_MODE", "off"), \
             mock.patch.object(mp, "_fast_disk_replay_to_waves_probe",
                               wraps=mp._fast_disk_replay_to_waves_probe) as spy:
            result = mp._fast_disk_replay_to(record, lane)
        assert result is model
        assert calls == ["to"], calls
        spy.assert_not_called()
        assert not any(e.name == "unet_read_h2d_wave_probe" for e in trace.events)


# ── 3. Probe mode instruments the materialization series (I-1) ───────────


class TestC6ProbeTensorSeries(unittest.TestCase):
    def _make_proxy(self, series=None, series_cap=2048):
        class FakeSafeOpen:
            def keys(self):
                return ["a", "b", "c"]

            def get_tensor(self, k):
                return torch.zeros(4, 4)

        orig = FakeSafeOpen()
        count_agg, bytes_agg = [0], [0]
        proxy = _SafeOpenProxy(orig, orig.get_tensor, count_agg, bytes_agg,
                               series=series, series_cap=series_cap)
        return proxy, count_agg, bytes_agg

    def test_series_recorded_and_emitted(self):
        trace, lane = _make_lane()
        proxy, count_agg, bytes_agg = self._make_proxy(series=[])
        buf = io.StringIO()
        with _active_lane(lane), \
             mock.patch.object(mp, "_DIAGNOSTIC_FLAG", True), \
             mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
             mock.patch.object(torch.cuda, "is_available", return_value=False), \
             contextlib.redirect_stdout(buf):
            proxy.get_tensor("a")
            proxy.get_tensor("b")
            proxy.get_tensor("c")
            proxy.__exit__()

        assert len(proxy._series) == 3
        assert [e["ordinal"] for e in proxy._series] == [0, 1, 2]
        assert [e["key"] for e in proxy._series] == ["a", "b", "c"]
        for e in proxy._series:
            for field in ("nbytes", "wall_ms", "cum_bytes", "t_start_ms", "t_end_ms"):
                assert field in e, f"missing {field} in {e}"
        cums = [e["cum_bytes"] for e in proxy._series]
        assert all(b >= a for a, b in zip(cums, cums[1:])), cums

        probes = [e for e in trace.events if e.name == "unet_read_h2d_pipeline_probe"]
        assert len(probes) == 1
        meta = probes[0].metadata
        assert meta["mode"] == "probe"
        assert meta["kind"] == "tensor_materialize_series"
        assert meta["series_count"] == 3
        assert meta["tensor_count"] == 3
        assert meta["series_truncated"] is False
        assert meta["platform"] == sys.platform

        lines = _proxy_series_console_lines(buf)
        assert len(lines) == 1, lines
        assert lines[0].startswith("[v2.c6_probe] read tensors=3 bytes=192 wall=")
        assert "p25=" in lines[0] and "p50=" in lines[0] and "p75=" in lines[0]
        assert "p100=" in lines[0] and "largest10=" in lines[0]


# ── 4. Byte totals reconcile ─────────────────────────────────────────────


class TestC6ProbeByteReconcile(unittest.TestCase):
    def test_byte_totals_reconcile(self):
        trace, lane = _make_lane()

        class FakeSafeOpen:
            def keys(self):
                return ["a", "b", "c"]

            def get_tensor(self, k):
                return torch.zeros(4, 4)

        orig = FakeSafeOpen()
        count_agg, bytes_agg = [0], [0]
        proxy = _SafeOpenProxy(orig, orig.get_tensor, count_agg, bytes_agg, series=[])
        with _active_lane(lane), \
             mock.patch.object(mp, "_DIAGNOSTIC_FLAG", True), \
             mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
             mock.patch.object(torch.cuda, "is_available", return_value=False):
            proxy.get_tensor("a")
            proxy.get_tensor("b")
            proxy.get_tensor("c")
            proxy.__exit__()

        series_bytes = sum(e["nbytes"] for e in proxy._series)
        assert series_bytes == bytes_agg[0] == 192, (series_bytes, bytes_agg[0])
        probes = [e for e in trace.events if e.name == "unet_read_h2d_pipeline_probe"]
        assert len(probes) == 1
        assert probes[0].metadata["total_bytes"] == bytes_agg[0]
        assert probes[0].metadata["tensor_count"] == count_agg[0]


# ── 5. Wave partition (I-2 helpers) ──────────────────────────────────────


class TestC6ProbeWavePartition(unittest.TestCase):
    def test_build_items_in_apply_order_and_partition(self):
        model = _make_nested_model()
        items = mp._fast_disk_build_wave_items(model)
        names = [(it[1], it[2]) for it in items]
        assert names == [
            ("extra", "param"),
            ("weight", "param"),
            ("bias", "param"),
            ("buf", "buffer"),
            ("weight", "param"),
            ("bias", "param"),
        ], names
        assert all(isinstance(it[4], int) and it[4] > 0 for it in items)

        waves = mp._fast_disk_partition_waves(items, 8)
        assert 1 <= len(waves) <= 8, len(waves)
        assert all(w["tensor_count"] > 0 for w in waves)
        assert all(w["bytes"] > 0 for w in waves)
        assert [w["ordinal"] for w in waves] == list(range(len(waves)))
        assert waves[0]["first_ordinal"] == 0
        assert waves[-1]["last_ordinal"] == len(items) - 1
        for a, b in zip(waves, waves[1:]):
            assert b["first_ordinal"] == a["last_ordinal"] + 1
            assert a["last_ordinal"] < b["last_ordinal"]
        assert sum(w["bytes"] for w in waves) == sum(it[4] for it in items)
        assert sum(w["tensor_count"] for w in waves) == len(items)

    def test_partition_empty_input(self):
        assert mp._fast_disk_partition_waves([], 8) == []


# ── 6. Wave replay semantics (no duplicate transfer) ─────────────────────


class TestC6ProbeWaveReplay(unittest.TestCase):
    def test_wave_replay_no_duplicate_transfer_and_semantics(self):
        model = _make_nested_model()
        orig_extra = model.extra
        orig_w = model.sub1.weight
        orig_buf = model.sub2.buf
        items = mp._fast_disk_build_wave_items(model)
        waves = mp._fast_disk_partition_waves(items, 8)
        model_id = id(model)

        to_calls = []

        def fake_to(self, *a, **k):
            to_calls.append(self)
            return torch.empty_like(self)

        with mock.patch.object(torch.Tensor, "to", fake_to):
            mp._fast_disk_replay_waves(model, waves, _CUDA, {})

        assert len(to_calls) == len(items), f"expected {len(items)} transfers, got {len(to_calls)}"
        assert id(model) == model_id, "module identity must be unchanged"
        assert model.extra is not orig_extra
        assert model.sub1.weight is not orig_w
        assert model.sub2.buf is not orig_buf
        assert isinstance(model.extra, torch.nn.Parameter)
        assert isinstance(model.sub1.weight, torch.nn.Parameter)
        assert isinstance(model.sub2.linear.bias, torch.nn.Parameter)
        assert orig_extra.requires_grad is True
        assert model.extra.requires_grad == orig_extra.requires_grad
        assert model.sub1.weight.requires_grad == orig_w.requires_grad
        assert "buf" in model.sub2._buffers
        assert model.sub2.buf.requires_grad is False


# ── 7. No synchronization introduced ─────────────────────────────────────


class TestC6ProbeNoSync(unittest.TestCase):
    def test_replay_waves_never_synchronizes(self):
        model = _make_nested_model()
        items = mp._fast_disk_build_wave_items(model)
        waves = mp._fast_disk_partition_waves(items, 8)
        with mock.patch.object(torch.cuda, "synchronize") as sync_mock, \
             mock.patch.object(torch.Tensor, "to",
                               lambda self, *a, **k: torch.empty_like(self)):
            mp._fast_disk_replay_waves(model, waves, _CUDA, {})
            sync_mock.assert_not_called()

    def test_probe_helper_never_synchronizes(self):
        trace, lane = _make_lane()
        model = _make_nested_model()
        with mock.patch.object(torch.cuda, "synchronize") as sync_mock, \
             mock.patch.object(torch.cuda, "is_available", return_value=True), \
             mock.patch.object(torch.cuda, "Event", _FakeEvent), \
             mock.patch.object(torch.Tensor, "to",
                               lambda self, *a, **k: torch.empty_like(self)):
            used, waves, ev_pairs = mp._fast_disk_replay_to_waves_probe(
                model, {}, (), {}, _CUDA, trace, lane, False)
            assert used is True
            assert len(ev_pairs) == len(waves) >= 1
            sync_mock.assert_not_called()


# ── 8. Wave eligibility ──────────────────────────────────────────────────


class TestC6ProbeWavesEligibility(unittest.TestCase):
    def test_eligibility_matrix(self):
        ok, reason = mp._fast_disk_waves_eligible(_CUDA, {}, True)
        assert (ok, reason) == (False, "pinned_staging_active")
        ok, reason = mp._fast_disk_waves_eligible(_CUDA, {"dtype": torch.float16}, False)
        assert (ok, reason) == (False, "dtype_conversion_requested")
        ok, reason = mp._fast_disk_waves_eligible(_CUDA, {"memory_format": torch.channels_last}, False)
        assert (ok, reason) == (False, "dtype_conversion_requested")
        ok, reason = mp._fast_disk_waves_eligible(torch.device("cpu"), {}, False)
        assert (ok, reason) == (False, "target_not_cuda")
        ok, reason = mp._fast_disk_waves_eligible(None, {}, False)
        assert (ok, reason) == (False, "target_not_cuda")
        with mock.patch.object(torch.cuda, "is_available", return_value=True):
            ok, reason = mp._fast_disk_waves_eligible(_CUDA, {}, False)
            assert (ok, reason) == (True, "ok")
        with mock.patch.object(torch.cuda, "is_available", return_value=False):
            ok, reason = mp._fast_disk_waves_eligible(_CUDA, {}, False)
            assert (ok, reason) == (False, "cuda_unavailable")


# ── 9. End-to-end replay with probe ──────────────────────────────────────


class TestC6ProbeEndToEnd(unittest.TestCase):
    def test_end_to_end_wave_probe(self):
        trace, lane = _make_lane()
        model = _make_single_param_model()
        original_to_calls = []

        def fake_to(m, *a, **k):
            original_to_calls.append(("to", a, k))
            return m

        record = _make_replay_record(model, fake_to, _CUDA)
        with mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
             mock.patch.object(torch.cuda, "is_available", return_value=True), \
             mock.patch.object(torch.cuda, "Event", _FakeEvent), \
             mock.patch.object(torch.cuda, "synchronize", lambda *a, **k: None), \
             mock.patch.object(torch.Tensor, "to",
                               lambda self, *a, **k: torch.empty_like(self)):
            result = mp._fast_disk_replay_to(record, lane)

        assert result is model
        assert original_to_calls == [], original_to_calls
        assert isinstance(record["timings"]["to_wall_ms"], float)
        assert record["timings"]["to_wall_ms"] >= 0.0
        assert record["timings"]["to_device_ms"] == 1.0

        names = [e.name for e in trace.events]
        assert names.index(mp._EVENT_FAST_DISK_TO_START) < names.index("unet_read_h2d_wave_probe")
        probes = [e for e in trace.events if e.name == "unet_read_h2d_wave_probe"]
        assert len(probes) == 1
        meta = probes[0].metadata
        assert meta["mode"] == "probe"
        assert meta["kind"] == "h2d_wave_series"
        assert meta["wave_count"] == 1
        assert meta["total_tensors"] == 1
        assert meta["total_bytes"] == 256
        assert meta["waves"][0]["device_ms"] == 1.0
        assert abs(meta["device_ms_sum"] - 1.0) < 1e-9
        assert abs(meta["total_device_ms"] - 1.0) < 1e-9
        assert "items" not in meta["waves"][0]
        assert meta["total_wall_ms"] == record["timings"]["to_wall_ms"]


# ── 10. Unsupported flag value ───────────────────────────────────────────


class TestC6ProbeUnsupportedFlag(unittest.TestCase):
    def test_unsupported_flag_falls_back_to_original(self):
        trace, lane = _make_lane()
        model = _make_replay_model()
        calls = []

        def fake_to(m, *a, **k):
            calls.append("to")
            return m

        record = _make_replay_record(model, fake_to, _CUDA)
        with mock.patch.object(mp, "_C6_PROBE_MODE", "unsupported"):
            result = mp._fast_disk_replay_to(record, lane)
        assert result is model
        assert calls == ["to"], calls
        assert not any(e.name == "unet_read_h2d_wave_probe" for e in trace.events)


# ── 11. Pinned-staging precedence ────────────────────────────────────────


class TestC6ProbePinnedStagingPrecedence(unittest.TestCase):
    def test_pinned_staging_precedence(self):
        trace, lane = _make_lane()
        model = _make_replay_model()
        calls = []

        def fake_to(m, *a, **k):
            calls.append("to")
            return m

        record = _make_replay_record(model, fake_to, _CUDA)
        buf = io.StringIO()
        with mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
             mock.patch.object(mp, "_fast_disk_waves_eligible",
                               return_value=(False, "pinned_staging_active")), \
             contextlib.redirect_stdout(buf):
            result = mp._fast_disk_replay_to(record, lane)
        assert result is model
        assert calls == ["to"], calls
        assert "[v2.c6_probe] waves fallback=pinned_staging_active" in buf.getvalue()
        assert not any(e.name == "unet_read_h2d_wave_probe" for e in trace.events)


# ── 12. Bounded / serializable series ────────────────────────────────────


class TestC6ProbeSeriesBounds(unittest.TestCase):
    def test_series_cap_and_json_serializable(self):
        trace, lane = _make_lane()

        class FakeSafeOpen:
            def keys(self):
                return ["a", "b", "c", "d", "e"]

            def get_tensor(self, k):
                return torch.zeros(4, 4)

        orig = FakeSafeOpen()
        count_agg, bytes_agg = [0], [0]
        proxy = _SafeOpenProxy(orig, orig.get_tensor, count_agg, bytes_agg,
                               series=[], series_cap=3)
        buf = io.StringIO()
        with _active_lane(lane), \
             mock.patch.object(mp, "_DIAGNOSTIC_FLAG", True), \
             mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
             mock.patch.object(torch.cuda, "is_available", return_value=False), \
             contextlib.redirect_stdout(buf):
            for k in ("a", "b", "c", "d", "e"):
                proxy.get_tensor(k)
            proxy.__exit__()

        assert len(proxy._series) == 3
        assert proxy._series_truncated is True
        assert [e["key"] for e in proxy._series] == ["a", "b", "c"]
        assert proxy._series_cum_bytes == 5 * 64  # bookkeeping keeps running

        probes = [e for e in trace.events if e.name == "unet_read_h2d_pipeline_probe"]
        assert len(probes) == 1
        meta = probes[0].metadata
        assert meta["series_truncated"] is True
        assert meta["series_count"] == 3
        json.dumps(probes[0].to_dict())  # must not raise

        lines = _proxy_series_console_lines(buf)
        assert len(lines) == 1, lines
        assert lines[0].startswith("[v2.c6_probe] read tensors=5 bytes=320")


# ── 13. No read/H2D overlap ordering ─────────────────────────────────────


class TestC6ProbeNoReadH2DOverlap(unittest.TestCase):
    def test_wave_probe_emitted_after_to_start(self):
        trace, lane = _make_lane()
        model = _make_single_param_model()
        record = _make_replay_record(model, lambda m, *a, **k: m, _CUDA)
        with mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
             mock.patch.object(torch.cuda, "is_available", return_value=True), \
             mock.patch.object(torch.cuda, "Event", _FakeEvent), \
             mock.patch.object(torch.cuda, "synchronize", lambda *a, **k: None), \
             mock.patch.object(torch.Tensor, "to",
                               lambda self, *a, **k: torch.empty_like(self)):
            mp._fast_disk_replay_to(record, lane)
        names = [e.name for e in trace.events]
        i_start = names.index(mp._EVENT_FAST_DISK_TO_START)
        i_probe = names.index("unet_read_h2d_wave_probe")
        assert i_start < i_probe, f"names={names}"


# ── 14. Probe mode is self-sufficient (no deep-model-diag dependency) ─────


class TestC6ProbeSeriesWithoutDeepDiag(unittest.TestCase):
    def test_series_recorded_when_deep_diag_off(self):
        trace, lane = _make_lane()

        class FakeSafeOpen:
            def keys(self):
                return ["a", "b", "c"]

            def get_tensor(self, k):
                return torch.zeros(4, 4)

        orig = FakeSafeOpen()
        count_agg, bytes_agg = [0], [0]
        proxy = _SafeOpenProxy(orig, orig.get_tensor, count_agg, bytes_agg, series=[])
        buf = io.StringIO()
        with _active_lane(lane), \
             mock.patch.object(mp, "_DIAGNOSTIC_FLAG", False), \
             mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
             mock.patch.object(torch.cuda, "is_available", return_value=False), \
             contextlib.redirect_stdout(buf):
            proxy.get_tensor("a")
            proxy.get_tensor("b")
            proxy.get_tensor("c")
            proxy.__exit__()

        assert len(proxy._series) == 3
        assert count_agg[0] == 3
        assert bytes_agg[0] == 192
        probes = [e for e in trace.events if e.name == "unet_read_h2d_pipeline_probe"]
        assert len(probes) == 1
        assert probes[0].metadata["series_count"] == 3
        assert len(_proxy_series_console_lines(buf)) == 1


class TestC6ProbeCoreWrappersSelfSufficiency(unittest.TestCase):
    def _call(self):
        with mock.patch.object(mp, "_get_live_module", return_value=None), \
             mock.patch.object(mp, "_install_model_patcher_wrappers", return_value={}), \
             mock.patch.object(mp, "_install_clip_wrapper", return_value="skipped"), \
             mock.patch.object(mp, "_install_clip_span_wrappers", return_value={}), \
             mock.patch.object(mp, "_install_mp_load_wrappers", return_value={}), \
             mock.patch.object(mp, "_install_graph_unet_loader_wrapper", return_value="skipped"), \
             mock.patch.object(mp, "install_nextdit_forward_pre_hook", return_value=False):
            return mp._ensure_core_wrappers(trace=None)

    def test_deep_wrappers_installed_in_probe_mode_without_deep_diag(self):
        with mock.patch.object(mp, "_DIAGNOSTIC_FLAG", False), \
             mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
             mock.patch.object(mp, "_install_deep_diag_wrappers",
                               return_value={"deep_safe_open": "installed"}) as deep_mock:
            result = self._call()
        deep_mock.assert_called_once()
        assert result["deep_safe_open"] == "installed"

    def test_deep_wrappers_skipped_when_both_off(self):
        with mock.patch.object(mp, "_DIAGNOSTIC_FLAG", False), \
             mock.patch.object(mp, "_C6_PROBE_MODE", "off"), \
             mock.patch.object(mp, "_install_deep_diag_wrappers",
                               return_value={"deep_safe_open": "installed"}) as deep_mock:
            self._call()
        deep_mock.assert_not_called()


class TestC6ProbeRuntimeEnvPassthrough(unittest.TestCase):
    def test_runtime_env_passthrough(self):
        import comfymodal_runtime.modal_app as _ma
        env = _ma._runtime_env()
        assert env.get("COMFYMODAL_V2_UNET_READ_H2D_PIPELINE", None) == ""
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_READ_H2D_PIPELINE": "probe"}, clear=False):
            env2 = _ma._runtime_env()
        assert env2["COMFYMODAL_V2_UNET_READ_H2D_PIPELINE"] == "probe"


# ── 15. Wrapper eligibility without _DEEP_TARGET_PATH (execution lane) ────


class TestC6ProbeEligibilityWithoutTargetPath(unittest.TestCase):
    def test_probe_mode_instruments_without_target_path(self):
        trace, lane = _make_lane()

        class FakeResult:
            def keys(self):
                return ["a", "b"]

            def get_tensor(self, k):
                return torch.zeros(4, 4)

        calls = []

        def fake_original(file, framework="pt", device="cpu", **kwargs):
            calls.append(file)
            return FakeResult()

        wrapper = mp._make_safetensors_open_wrapper(fake_original)
        buf = io.StringIO()
        _tok = mp._DEEP_TARGET_PATH.set("")
        try:
            with _active_lane(lane), \
                 mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
                 mock.patch.object(mp, "_DIAGNOSTIC_FLAG", False), \
                 contextlib.redirect_stdout(buf):
                result = wrapper("model.safetensors")
                assert isinstance(result, _SafeOpenProxy)
                result.get_tensor("a")
                result.get_tensor("b")
                result.__exit__()
        finally:
            mp._DEEP_TARGET_PATH.reset(_tok)

        assert calls == ["model.safetensors"]
        assert len(result._series) == 2
        assert [e["key"] for e in result._series] == ["a", "b"]
        names = [e.name for e in trace.events]
        assert "unet_safetensors_open_start" in names
        probes = [e for e in trace.events if e.name == "unet_read_h2d_pipeline_probe"]
        assert len(probes) == 1
        assert probes[0].metadata["series_count"] == 2
        assert len(_proxy_series_console_lines(buf)) == 1

    def test_off_mode_not_instrumented_without_target_path(self):
        trace, lane = _make_lane()

        class FakeResult:
            def keys(self):
                return ["a", "b"]

            def get_tensor(self, k):
                return torch.zeros(4, 4)

        def fake_original(file, framework="pt", device="cpu", **kwargs):
            return FakeResult()

        wrapper = mp._make_safetensors_open_wrapper(fake_original)
        _tok = mp._DEEP_TARGET_PATH.set("")
        try:
            with _active_lane(lane), \
                 mock.patch.object(mp, "_C6_PROBE_MODE", "off"), \
                 mock.patch.object(mp, "_DIAGNOSTIC_FLAG", False):
                result = wrapper("model.safetensors")
        finally:
            mp._DEEP_TARGET_PATH.reset(_tok)

        assert not isinstance(result, _SafeOpenProxy)
        names = [e.name for e in trace.events]
        assert "unet_safetensors_open_start" not in names
        assert "unet_read_h2d_pipeline_probe" not in names
        assert not any(e.name == "unet_tensor_materialize_aggregated" for e in trace.events)


# ── 16. Proxy __enter__ returns the proxy (context-manager routing) ───────


class TestC6ProbeContextManagerRouting(unittest.TestCase):
    def test_context_manager_yields_proxy_and_records(self):
        trace, lane = _make_lane()
        entered = []
        exited = []

        class FakeWrapped:
            def keys(self):
                return ["a"]

            def get_tensor(self, k):
                return torch.zeros(4, 4)

            def __enter__(self):
                entered.append("enter")
                return object()

            def __exit__(self, *exc):
                exited.append("exit")
                return None

        wrapped = FakeWrapped()
        count_agg, bytes_agg = [0], [0]
        proxy = _SafeOpenProxy(wrapped, wrapped.get_tensor, count_agg, bytes_agg, series=[])
        buf = io.StringIO()
        with _active_lane(lane), \
             mock.patch.object(mp, "_DIAGNOSTIC_FLAG", True), \
             mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
             contextlib.redirect_stdout(buf):
            with proxy as f:
                assert f is proxy, "with proxy as f must yield the proxy"
                f.get_tensor("a")
        assert entered == ["enter"], entered
        assert exited == ["exit"], exited
        assert len(proxy._series) == 1
        assert proxy._series[0]["key"] == "a"
        assert count_agg[0] == 1
        assert bytes_agg[0] == 64
        assert len(_proxy_series_console_lines(buf)) == 1


try:
    import safetensors.torch as _st_torch
    _HAS_SAFETENSORS = True
except Exception:  # pragma: no cover - skip on systems without safetensors
    _HAS_SAFETENSORS = False


@unittest.skipUnless(_HAS_SAFETENSORS, "safetensors not available")
class TestC6ProbeRealSafetensorsRouting(unittest.TestCase):
    def test_real_safetensors_routes_get_tensor_through_proxy(self):
        trace, lane = _make_lane()
        _tmp = tempfile.TemporaryDirectory()
        _count = _series_len = _probe_count = None
        try:
            path = os.path.join(_tmp.name, "tiny.safetensors")
            _st_torch.save_file({"w": torch.zeros(4, 4)}, path)
            import safetensors as _st
            wrapper = mp._make_safetensors_open_wrapper(_st.safe_open)
            with _active_lane(lane), \
                 mock.patch.object(mp, "_DIAGNOSTIC_FLAG", False), \
                 mock.patch.object(mp, "_C6_PROBE_MODE", "probe"):
                result = wrapper(path)
                assert isinstance(result, _SafeOpenProxy)
                with result as f:
                    assert f is result, "with safe_open(...) as f must yield the proxy"
                    t = f.get_tensor("w")
                assert t.shape == (4, 4)
                _count = result._count_agg[0]
                _series_len = len(result._series)
                _probe_count = len([
                    e for e in trace.events if e.name == "unet_read_h2d_pipeline_probe"
                ])
                del t
                del result
                gc.collect()
        finally:
            try:
                _tmp.cleanup()
            except PermissionError:  # pragma: no cover - Windows mmap lock
                pass
        assert _count == 1
        assert _series_len == 1
        assert _probe_count == 1


# ── 17. I-3 header/meta config parity gates ──────────────────────────────


def _fake_comfy_utils_module():
    import types as _types_c6
    _cu = _types_c6.ModuleType("comfy.utils")

    def _fake_weight_dtype(sd, prefix=""):
        dtypes = {}
        for k in sd.keys():
            if k.startswith(prefix):
                w = sd[k]
                dtypes[w.dtype] = dtypes.get(w.dtype, 0) + w.numel()
        if not dtypes:
            return None
        return max(dtypes, key=dtypes.get)

    _cu.calculate_parameters = lambda sd, prefix="": sum(
        w.nelement() for k, w in sd.items() if k.startswith(prefix))
    _cu.weight_dtype = _fake_weight_dtype
    _cu._TYPES = {
        "F64": torch.float64, "F32": torch.float32, "F16": torch.float16,
        "BF16": torch.bfloat16, "I64": torch.int64, "I32": torch.int32,
        "I16": torch.int16, "I8": torch.int8, "U8": torch.uint8,
        "U64": torch.uint64, "U32": torch.uint32, "U16": torch.uint16,
    }
    return _cu


@contextlib.contextmanager
def _fake_comfy_utils_in_sys_modules():
    import types as _types_sm
    _saved_comfy = sys.modules.get("comfy")
    _saved_cu = sys.modules.get("comfy.utils")
    sys.modules["comfy"] = _types_sm.ModuleType("comfy")
    sys.modules["comfy.utils"] = _fake_comfy_utils_module()
    try:
        yield
    finally:
        if _saved_comfy is None:
            sys.modules.pop("comfy", None)
        else:
            sys.modules["comfy"] = _saved_comfy
        if _saved_cu is None:
            sys.modules.pop("comfy.utils", None)
        else:
            sys.modules["comfy.utils"] = _saved_cu


def _write_tiny_safetensors(td):
    path = os.path.join(td, "tiny.safetensors")
    _st_torch.save_file({
        "w": torch.zeros(4, 4, dtype=torch.float32),
        "b": torch.ones(3, dtype=torch.float16),
    }, path)
    return path


@unittest.skipUnless(_HAS_SAFETENSORS, "safetensors not available")
class TestC6I3HeaderParsing(unittest.TestCase):
    def test_header_parse_real_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            header = mp._c6_parse_safetensors_header(path)
        assert header is not None
        assert set(header.keys()) == {"w", "b"}
        assert header["w"]["dtype"] == "F32"
        assert header["w"]["shape"] == [4, 4]
        assert header["b"]["dtype"] == "F16"
        assert header["b"]["shape"] == [3]
        assert header["w"]["data_offsets"][0] >= 0
        assert header["w"]["data_offsets"][1] > header["w"]["data_offsets"][0]
        assert header["b"]["data_offsets"][0] >= header["w"]["data_offsets"][1]


@unittest.skipUnless(_HAS_SAFETENSORS, "safetensors not available")
class TestC6I3MetaSd(unittest.TestCase):
    def test_meta_sd_shapes_dtypes_numel(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_tiny_safetensors(td)
            header = mp._c6_parse_safetensors_header(path)
        sd = mp._c6_build_meta_sd(header)
        assert set(sd.keys()) == {"w", "b"}
        assert tuple(sd["w"].shape) == (4, 4)
        assert sd["w"].dtype == torch.float32
        assert sd["w"].device.type == "meta"
        assert sd["w"].numel() == 16
        assert sd["b"].dtype == torch.float16
        assert sd["b"].numel() == 3


@unittest.skipUnless(_HAS_SAFETENSORS, "safetensors not available")
class TestC6I3MetaParity(unittest.TestCase):
    def test_parameter_count_parity(self):
        _tmp = tempfile.TemporaryDirectory()
        _meta_count = _real_count = None
        try:
            path = _write_tiny_safetensors(_tmp.name)
            header = mp._c6_parse_safetensors_header(path)
            _loaded = _st_torch.load_file(path, device="cpu")
            real_sd = _loaded[0] if isinstance(_loaded, tuple) else _loaded
            with _fake_comfy_utils_in_sys_modules():
                calc = mp._c6_comfy_fn("comfy.utils", "calculate_parameters")
                _meta_count = calc(mp._c6_build_meta_sd(header))
                _real_count = calc(real_sd)
            del real_sd
            gc.collect()
        finally:
            try:
                _tmp.cleanup()
            except PermissionError:  # pragma: no cover - Windows mmap lock
                pass
        assert _meta_count == _real_count

    def test_weight_dtype_parity(self):
        _tmp = tempfile.TemporaryDirectory()
        _meta_wd = _real_wd = None
        try:
            path = _write_tiny_safetensors(_tmp.name)
            header = mp._c6_parse_safetensors_header(path)
            _loaded = _st_torch.load_file(path, device="cpu")
            real_sd = _loaded[0] if isinstance(_loaded, tuple) else _loaded
            with _fake_comfy_utils_in_sys_modules():
                wd = mp._c6_comfy_fn("comfy.utils", "weight_dtype")
                _meta_wd = wd(mp._c6_build_meta_sd(header))
                _real_wd = wd(real_sd)
            del real_sd
            gc.collect()
        finally:
            try:
                _tmp.cleanup()
            except PermissionError:  # pragma: no cover - Windows mmap lock
                pass
        assert _meta_wd == _real_wd


class TestC6I3ConfigParityCompare(unittest.TestCase):
    def _auth(self, **kw):
        base = {
            "config_class": "ZImage",
            "unet_config": {"dim": 3840, "n_layers": 24, "allow_fp16": True},
            "supported_inference_dtypes": ["torch.bfloat16", "torch.float16"],
            "parameters": 100,
            "param_count": 100,
            "module_count": 24,
            "weight_dtype": "torch.bfloat16",
            "unet_dtype": "torch.bfloat16",
            "manual_cast_dtype": None,
        }
        base.update(kw)
        return base

    def test_match_when_equal(self):
        auth = self._auth()
        cand = dict(auth)
        cand["unet_config"] = dict(auth["unet_config"])
        res = mp._c6_config_parity_compare(auth, cand, None)
        assert res["verdict"] == "MATCH", res

    def test_mismatch_fails_closed(self):
        auth = self._auth()
        cand = dict(auth)
        cand["config_class"] = "Other"
        cand["unet_config"] = dict(auth["unet_config"])
        res = mp._c6_config_parity_compare(auth, cand, None)
        assert res["verdict"] == "MISMATCH"
        assert res["fields"]["config_class"]["match"] is False

    def test_value_dependent_gap_resolved_by_probe(self):
        auth = self._auth()
        cand = dict(auth)
        cand["unet_config"] = {"dim": 3840, "n_layers": 24}
        cand["supported_inference_dtypes"] = ["torch.bfloat16"]
        _real = mp._c6_comfy_fn

        def _fake_c6(mod, attr, fallback=None):
            if mod == "comfy.model_management" and attr == "extended_fp16_support":
                return lambda: True
            return _real(mod, attr, fallback)

        with mock.patch.object(mp, "_c6_comfy_fn", side_effect=_fake_c6):
            res = mp._c6_config_parity_compare(auth, cand, True)
        assert res["verdict"] == "MATCH", res
        assert res["fail_closed"]["gap_resolved"] is True
        assert res["fields"]["unet_config"]["status"] == "value_dependent_gap"

    def test_value_probe_none_flags_gap_as_mismatch(self):
        auth = self._auth()
        cand = dict(auth)
        cand["unet_config"] = {"dim": 3840, "n_layers": 24}
        cand["supported_inference_dtypes"] = ["torch.bfloat16"]
        res = mp._c6_config_parity_compare(auth, cand, None)
        assert res["verdict"] == "MISMATCH"
        assert "unet_config" in res["fail_closed"]["mismatch_fields"]

    def test_parity_result_json_serializable_with_dtype_stamp(self):
        # set_inference_dtype stamps a raw torch.dtype into unet_config;
        # the stored field must be JSON-serializable while the comparison
        # keeps excluding the dtype stamp.
        auth = self._auth()
        auth["unet_config"] = {"dim": 3840, "n_layers": 24, "allow_fp16": True,
                               "dtype": torch.bfloat16}
        cand = dict(auth)
        cand["unet_config"] = {"dim": 3840, "n_layers": 24, "allow_fp16": True}
        res = mp._c6_config_parity_compare(auth, cand, None)
        json.dumps(res)  # must not raise (previously: dtype not JSON serializable)
        assert res["verdict"] == "MATCH", res
        assert res["fields"]["unet_config"]["auth"]["dtype"] == "torch.bfloat16"


class TestC6I3TransformClassification(unittest.TestCase):
    def test_identity_transform_all_independent(self):
        sd = {"a": torch.zeros(2), "b": torch.ones(3)}
        res = mp._c6_classify_transform([(sd, sd)], lambda x: x)
        assert res["transform_is_identity"] is True
        assert set(res["classification"]["INDEPENDENT"]) == {"a", "b"}
        assert res["classification"]["SMALL_GROUP"] == []
        assert res["classification"]["FULL_DICT_REQUIRED"] == []

    def test_merging_transform_small_group(self):
        a = torch.zeros(4)
        b = torch.ones(4)
        sd = {"a": a, "b": b}
        out = {"ab": a + b}

        def merge(s):
            if "a" in s and "b" in s:
                return {"ab": s["a"] + s["b"]}
            return {}

        res = mp._c6_classify_transform([(sd, out)], merge)
        assert res["transform_is_identity"] is False
        assert res["classification"]["INDEPENDENT"] == []
        assert ["a", "b"] in res["classification"]["SMALL_GROUP"]
        assert res["classification"]["FULL_DICT_REQUIRED"] == []

    def test_prefix_count_transform_full_dict_required(self):
        sd = {"a": torch.zeros(2), "b": torch.ones(3)}
        out = {"a": torch.zeros(2), "b": torch.ones(3)}

        def prefix(s):
            return dict(s) if len(s) >= 3 else {}

        res = mp._c6_classify_transform([(sd, out)], prefix)
        assert res["transform_is_identity"] is False
        assert set(res["classification"]["FULL_DICT_REQUIRED"]) == {"a", "b"}
        assert res["classification"]["SMALL_GROUP"] == []

    def test_whole_dict_keys_equal_union_of_group_outputs(self):
        a = torch.zeros(4)
        b = torch.ones(4)
        sd = {"a": a, "b": b}

        def merge(s):
            if "a" in s and "b" in s:
                return {"ab": s["a"] + s["b"]}
            return {}

        out = merge(dict(sd))
        res = mp._c6_classify_transform([(sd, out)], merge)
        groups = res["classification"]["SMALL_GROUP"]
        group_keys = set()
        for g in groups:
            group_keys |= set(merge({k: sd[k] for k in g}).keys())
        assert set(out.keys()) == group_keys


# ── 18. I-3 micro mmap/pageable H2D overlap probe ────────────────────────


class _SimpleDest:
    def copy_(self, *a, **k):
        return None


@contextlib.contextmanager
def _micro_probe_env(cuda_available=True, dest_class=None, dests=None):
    class _DefaultDest:
        def __init__(self):
            self.calls = []
            if dests is not None:
                dests.append(self)

        def copy_(self, *a, **k):
            self.calls.append((a, k))
            return None

    _factory = dest_class or _DefaultDest
    _stack = contextlib.ExitStack()
    _stack.enter_context(mock.patch.object(mp, "_C6_PROBE_MODE", "probe"))
    _stack.enter_context(mock.patch.object(mp, "_DIAGNOSTIC_FLAG", True))
    _stack.enter_context(mock.patch.object(torch.cuda, "is_available", return_value=cuda_available))
    _stack.enter_context(mock.patch.object(torch.cuda, "Event", _FakeEvent))
    _stack.enter_context(mock.patch.object(torch.cuda, "synchronize", lambda *a, **k: None))
    _stack.enter_context(mock.patch.object(torch.cuda, "empty_cache", lambda *a, **k: None))
    _stack.enter_context(mock.patch.object(torch, "empty", lambda *a, **k: _factory()))
    with _stack:
        yield


def _make_micro_proxy(tensors):
    class FakeSafeOpen:
        def keys(self):
            return [str(i) for i in range(len(tensors))]

        def get_tensor(self, k):
            return tensors[int(k)]

    orig = FakeSafeOpen()
    return _SafeOpenProxy(orig, orig.get_tensor, [0], [0], series=[])


class TestC6MicroProbeOffPath(unittest.TestCase):
    def test_no_cuda_touched_when_probe_off(self):
        trace, lane = _make_lane()
        tensors = [torch.zeros(4, 4) for _ in range(5)]
        proxy = _make_micro_proxy(tensors)

        def _boom(*a, **k):
            raise AssertionError("cuda touched when probe off")

        with _active_lane(lane), \
             mock.patch.object(mp, "_C6_PROBE_MODE", "off"), \
             mock.patch.object(mp, "_DIAGNOSTIC_FLAG", True), \
             mock.patch.object(torch.cuda, "is_available", _boom), \
             mock.patch.object(torch.cuda, "synchronize", _boom), \
             mock.patch.object(torch.cuda, "empty_cache", _boom), \
             mock.patch.object(torch.Tensor, "copy_", _boom):
            got = [proxy.get_tensor(str(i)) for i in range(5)]
            proxy.__exit__()
        assert all(g is t for g, t in zip(got, tensors))
        assert proxy._c6_micro_records == []
        assert proxy._c6_micro_pending is None
        assert proxy._c6_micro_sample_set is None


class TestC6MicroProbeRouting(unittest.TestCase):
    def test_destinations_never_bind_and_tensor_unchanged(self):
        trace, lane = _make_lane()
        tensors = [torch.zeros(4, 4) for _ in range(5)]
        proxy = _make_micro_proxy(tensors)
        dests = []
        with _active_lane(lane), _micro_probe_env(dests=dests):
            got = [proxy.get_tensor(str(i)) for i in range(5)]
            proxy.__exit__()
        assert all(g is t for g, t in zip(got, tensors))
        assert len(dests) == 1, dests  # only ordinal 2 (in the sample set) fires
        assert len(proxy._c6_micro_records) == 1
        for rec in proxy._c6_micro_records:
            assert "dest" not in rec
            assert "ev_start" not in rec and "ev_end" not in rec
            assert isinstance(rec["key"], str)
            assert rec["h2d_cuda_ms"] == 1.0
        assert proxy._c6_micro_pending is None

    def test_pending_cleared_and_dest_released(self):
        trace, lane = _make_lane()
        tensors = [torch.zeros(4, 4) for _ in range(8)]
        proxy = _make_micro_proxy(tensors)
        empty_calls = []
        with _active_lane(lane), \
             mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
             mock.patch.object(mp, "_DIAGNOSTIC_FLAG", True), \
             mock.patch.object(torch.cuda, "is_available", return_value=True), \
             mock.patch.object(torch.cuda, "Event", _FakeEvent), \
             mock.patch.object(torch.cuda, "synchronize", lambda *a, **k: None), \
             mock.patch.object(torch.cuda, "empty_cache", lambda *a, **k: empty_calls.append(1)), \
             mock.patch.object(torch, "empty", lambda *a, **k: _SimpleDest()):
            for i in range(8):
                proxy.get_tensor(str(i))
        assert proxy._c6_micro_pending is None
        assert empty_calls, "empty_cache must run on finalize"
        assert len(proxy._c6_micro_records) == 1

    def test_series_serializable_and_bounded(self):
        trace, lane = _make_lane()
        tensors = [torch.zeros(4, 4) for _ in range(8)]
        proxy = _make_micro_proxy(tensors)
        with _active_lane(lane), _micro_probe_env():
            for i in range(8):
                proxy.get_tensor(str(i))
            proxy.__exit__()
        evs = [e for e in trace.events if e.name == "unet_i3_micro_overlap"]
        assert len(evs) == 1
        assert len(evs[0].metadata["samples"]) <= 4
        json.dumps(evs[0].to_dict())


class TestC6MicroClassifier(unittest.TestCase):
    def _rec(self, h2d, nxt, comb, direct, complete):
        return {"no_next": False, "h2d_cuda_ms": h2d, "next_mat_wall_ms": nxt,
                "combined_wall_ms": comb, "overlap_direct": direct, "overlap_complete": complete}

    def test_serial_effective(self):
        res = mp._c6_classify_overlap([self._rec(10, 10, 20, False, False)])
        assert res["class"] == "EFFECTIVELY_SERIAL"
        assert res["per_sample"][0]["eff"] == 0.0

    def test_perfect_hiding(self):
        res = mp._c6_classify_overlap([
            self._rec(10, 10, 10, True, True),
            self._rec(10, 10, 10, True, True),
        ])
        assert res["class"] == "TRUE_DMA_OVERLAP"
        assert res["mean_eff"] == 1.0

    def test_partial_overlap(self):
        res = mp._c6_classify_overlap([
            self._rec(10, 10, 12, True, False),
            self._rec(10, 10, 14, True, False),
        ])
        assert res["class"] == "PARTIAL_OVERLAP"
        assert res["mean_eff"] > 0.2

    def test_empty_no_samples(self):
        res = mp._c6_classify_overlap([])
        assert res["class"] == "NO_SAMPLES"
        assert res["n_samples"] == 0


class TestC6MicroNoOutputDependency(unittest.TestCase):
    def test_identical_materialization_outcome(self):
        def run(cuda_available):
            trace, lane = _make_lane()
            tensors = [torch.zeros(4, 4) for _ in range(5)]
            proxy = _make_micro_proxy(tensors)
            with _active_lane(lane), _micro_probe_env(cuda_available=cuda_available):
                got = [proxy.get_tensor(str(i)) for i in range(5)]
            return proxy, got, tensors
        p_off, g_off, t_off = run(False)
        p_on, g_on, t_on = run(True)
        assert all(a is b for a, b in zip(g_off, t_off))
        assert all(a is b for a, b in zip(g_on, t_on))
        assert [e["key"] for e in p_off._series] == [e["key"] for e in p_on._series]
        assert p_off._c6_micro_records == []
        assert len(p_on._c6_micro_records) == 1


class TestC6MicroFailureFallback(unittest.TestCase):
    def test_copy_failure_disables_and_returns_tensor(self):
        trace, lane = _make_lane()
        tensors = [torch.zeros(4, 4) for _ in range(5)]
        proxy = _make_micro_proxy(tensors)

        class _BoomDest:
            def copy_(self, *a, **k):
                raise RuntimeError("copy boom")

        with _active_lane(lane), _micro_probe_env(dest_class=_BoomDest):
            got = [proxy.get_tensor(str(i)) for i in range(5)]
            proxy.__exit__()
        assert proxy._c6_micro_disabled is True
        assert proxy._c6_micro_pending is None
        assert all(g is t for g, t in zip(got, tensors))
        assert proxy._c6_micro_records == []


class TestC6I3Orchestration(unittest.TestCase):
    def test_capture_missing_skipped(self):
        trace = RuntimeTrace(request_id="i3-skip", process="remote")
        _saved_mode = mp._C6_PROBE_MODE
        _saved_cap = mp._C6_I3_CAPTURE
        _saved_path = mp._C6_PROBE_FILE_PATH
        mp._C6_PROBE_MODE = "probe"
        mp._C6_I3_CAPTURE = None
        mp._C6_PROBE_FILE_PATH = ""
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                mp._c6_run_config_parity()
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
            mp._C6_PROBE_MODE = _saved_mode
        evs = [e for e in trace.events if e.name == "unet_i3_config_parity"]
        assert len(evs) == 1
        assert evs[0].metadata["verdict"] == "SKIPPED"
        assert evs[0].metadata["reason"] == "capture_missing"
        assert "[v2.c6_probe] i3 parity=SKIPPED reason=capture_missing" in buf.getvalue()

    def test_full_parity_emitted_and_capture_reset(self):
        trace = RuntimeTrace(request_id="i3-full", process="remote")
        _saved_mode = mp._C6_PROBE_MODE
        _saved_cap = mp._C6_I3_CAPTURE
        _saved_path = mp._C6_PROBE_FILE_PATH
        model = torch.nn.Module()
        model.register_parameter("w", torch.nn.Parameter(torch.zeros(4, 4)))
        config = SimpleNamespace(
            unet_config={"dim": 16, "n_layers": 2, "dtype": torch.bfloat16},
            supported_inference_dtypes=[torch.bfloat16],
            manual_cast_dtype=None,
        )
        sd = {"a": torch.zeros(4, 4), "b": torch.ones(2, 2)}
        mp._C6_PROBE_MODE = "probe"
        mp._C6_I3_CAPTURE = {
            "model_config": config,
            "model": model,
            "new_sd": sd,
            "prefix": "",
            "param_count": 16,
            "module_count": 1,
            "transform_pairs": [(dict(sd), dict(sd))],
        }
        mp._C6_PROBE_FILE_PATH = "fake.safetensors"
        cand = {
            "config_class": "SimpleNamespace",
            "unet_config": {"dim": 16, "n_layers": 2},
            "supported_inference_dtypes": ["torch.bfloat16"],
            "parameters": 16,
            "param_count": 16,
            "module_count": 1,
            "weight_dtype": "torch.float32",
            "unet_dtype": "torch.bfloat16",
            "manual_cast_dtype": None,
            "meta_derivation": True,
        }
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            with mock.patch.object(mp, "_c6_derive_config_from_header", return_value=cand), \
                 mock.patch.object(mp, "_c6_parse_safetensors_header",
                                   return_value={"layers.0.ffn_norm1.weight": {"dtype": "BF16", "shape": [4], "data_offsets": [0, 8]}}), \
                 mock.patch.object(mp, "_c6_value_probe_allow_fp16", return_value=None), \
                 contextlib.redirect_stdout(io.StringIO()):
                mp._c6_run_config_parity()
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
            mp._C6_PROBE_MODE = _saved_mode
        evs = [e for e in trace.events if e.name == "unet_i3_config_parity"]
        assert len(evs) == 1
        assert evs[0].metadata["verdict"] == "MATCH", evs[0].metadata
        tevs = [e for e in trace.events if e.name == "unet_i3_transform_classification"]
        assert len(tevs) == 1
        assert tevs[0].metadata["transform_is_identity"] is True
        assert mp._C6_I3_CAPTURE is None
        assert mp._C6_PROBE_FILE_PATH == ""


# ── 19. I-3 emit failure safety (never propagate into the load path) ─────


class TestC6JsonSafe(unittest.TestCase):
    def test_json_safe_recurses(self):
        value = {
            "dtype": torch.bfloat16,
            "device": torch.device("cuda:0"),
            "tensor": torch.zeros(2, 3),
            "nested": {"d": torch.float32},
            "list": [torch.float16, 1, "x", None],
            "int": 5,
        }
        safe = mp._c6_json_safe(value)
        json.dumps(safe)
        assert safe["dtype"] == "torch.bfloat16"
        assert safe["device"] == "cuda:0"
        assert safe["tensor"].startswith("tensor(shape=[2, 3],dtype=torch.float32)")
        assert safe["nested"]["d"] == "torch.float32"
        assert safe["list"][0] == "torch.float16"
        assert safe["int"] == 5


class TestC6MicroEmitFailureSafety(unittest.TestCase):
    def test_micro_overlap_emit_failure_does_not_propagate(self):
        trace, lane = _make_lane()
        tensors = [torch.zeros(4, 4) for _ in range(8)]
        proxy = _make_micro_proxy(tensors)
        buf = io.StringIO()

        def _boom_emit(name, *a, **k):
            if name == "unet_i3_micro_overlap":
                raise RuntimeError("emit boom")
            return None

        with _active_lane(lane), \
             mock.patch.object(mp, "_C6_PROBE_MODE", "probe"), \
             mock.patch.object(mp, "_DIAGNOSTIC_FLAG", True), \
             mock.patch.object(torch.cuda, "is_available", return_value=True), \
             mock.patch.object(torch.cuda, "Event", _FakeEvent), \
             mock.patch.object(torch.cuda, "synchronize", lambda *a, **k: None), \
             mock.patch.object(torch.cuda, "empty_cache", lambda *a, **k: None), \
             mock.patch.object(torch, "empty", lambda *a, **k: _SimpleDest()), \
             mock.patch.object(lane._trace, "emit", side_effect=_boom_emit), \
             contextlib.redirect_stdout(buf):
            for i in range(8):
                proxy.get_tensor(str(i))
            proxy.__exit__()  # must not raise despite the emit failure
        assert "[v2.c6_probe] micro emit_error=RuntimeError" in buf.getvalue()


@unittest.skipUnless(_HAS_SAFETENSORS, "safetensors not available")
class TestC6ParityEmitFailureSafety(unittest.TestCase):
    def test_parity_orchestrator_emit_failure_does_not_propagate(self):
        _tmp = tempfile.TemporaryDirectory()
        _saved_mode = mp._C6_PROBE_MODE
        model = torch.nn.Module()
        model.register_parameter("w", torch.nn.Parameter(torch.zeros(4, 4)))
        config = SimpleNamespace(
            unet_config={"dim": 16, "n_layers": 2, "dtype": torch.bfloat16},
            supported_inference_dtypes=[torch.bfloat16],
            manual_cast_dtype=None,
        )
        sd = {"a": torch.zeros(4, 4)}
        cand = {
            "config_class": "SimpleNamespace",
            "unet_config": {"dim": 16, "n_layers": 2},
            "supported_inference_dtypes": ["torch.bfloat16"],
            "parameters": 16,
            "param_count": 16,
            "module_count": 1,
            "weight_dtype": "torch.float32",
            "unet_dtype": "torch.bfloat16",
            "manual_cast_dtype": None,
            "meta_derivation": True,
        }
        mp._C6_PROBE_MODE = "probe"
        mp._C6_I3_CAPTURE = {
            "model_config": config, "model": model, "new_sd": sd, "prefix": "",
            "param_count": 16, "module_count": 1, "transform_pairs": [],
        }
        _boom_trace = SimpleNamespace(emit=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("emit boom")))
        _tok = mp._ACTIVE_REQUEST_TRACE.set(_boom_trace)
        result = None
        try:
            try:
                path = _write_tiny_safetensors(_tmp.name)
                mp._C6_PROBE_FILE_PATH = path
                with mock.patch.object(mp, "_c6_derive_config_from_header", return_value=cand), \
                     mock.patch.object(mp, "_c6_parse_safetensors_header",
                                       return_value={"layers.0.ffn_norm1.weight": {"dtype": "BF16", "shape": [4], "data_offsets": [0, 8]}}), \
                     mock.patch.object(mp, "_c6_value_probe_allow_fp16", return_value=None), \
                     contextlib.redirect_stdout(io.StringIO()):
                    result = mp._c6_run_config_parity()
            finally:
                mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        finally:
            mp._C6_PROBE_MODE = _saved_mode
            try:
                _tmp.cleanup()
            except PermissionError:  # pragma: no cover - Windows mmap lock
                pass
        assert result is None  # never raises; emit failures are swallowed
        assert mp._C6_I3_CAPTURE is None
        assert mp._C6_PROBE_FILE_PATH == ""


# ── 20. Pinned-staging-ring feasibility microprobe ───────────────────────


class _RingEvent:
    def __init__(self, log=None):
        self.sync_calls = 0
        self.log = log

    def record(self):
        return None

    def elapsed_time(self, other):
        return 1.0

    def synchronize(self):
        self.sync_calls += 1
        if self.log is not None:
            self.log.append("sync")


class _RingBuffer:
    def __init__(self, log=None, kind="dest"):
        self.log = log
        self.kind = kind
        self.copy_calls = 0

    def copy_(self, src, non_blocking=False):
        self.copy_calls += 1
        if self.log is not None:
            self.log.append((self.kind, non_blocking))
        return None


class _FakeRingTorch:
    """CPU-safe torch stand-in for _c6_ring_run: records allocations and
    copy/sync order; fake events report a fixed elapsed time."""

    def __init__(self, log=None):
        self.log = log if log is not None else []
        self.empty_calls = []
        self.empties = []
        self.empty_cache_calls = [0]
        self.cuda = SimpleNamespace(
            Event=lambda enable_timing=True: _RingEvent(self.log),
            synchronize=lambda: None,
            empty_cache=lambda: self.empty_cache_calls.__setitem__(
                0, self.empty_cache_calls[0] + 1),
        )

    def empty(self, shape, *, dtype=None, pin_memory=False, device=None):
        self.empty_calls.append({
            "shape": list(shape), "dtype": dtype, "pin": bool(pin_memory), "device": device,
        })
        _b = _RingBuffer(self.log, kind="pin" if pin_memory else "dest")
        self.empties.append(_b)
        return _b


def _make_ring_sources(n, nbytes=60000000):
    return [{
        "ordinal": i, "key": "k%d" % i, "nbytes": nbytes,
        "data_ptr": i * 8, "storage_offset": 0, "is_view": True,
        "tensor": torch.zeros(4),
    } for i in range(n)]


def _fake_orchestrator_configs():
    return {
        (False, 0): {"pin": False, "buffers": 0, "records": [],
                     "ring_actual_wall_ms": 100.0, "overlap_efficiency": None,
                     "total_cpu_stage_ms": 0.0, "total_h2d_ms": 100.0,
                     "serial_expected_ms": 100.0, "thread_cpu_ms": 0.0, "minflt_delta": 0},
        (True, 1): {"pin": True, "buffers": 1, "records": [{"h2d_issue_ms": 2.0, "cpu_gbps": 10.0, "h2d_gbps": 30.0}],
                    "ring_actual_wall_ms": 50.0, "overlap_efficiency": 0.1,
                    "total_cpu_stage_ms": 0.0, "total_h2d_ms": 50.0,
                    "serial_expected_ms": 50.0, "thread_cpu_ms": 0.0, "minflt_delta": 0},
        (True, 2): {"pin": True, "buffers": 2, "records": [{"h2d_issue_ms": 3.0, "cpu_gbps": 12.0, "h2d_gbps": 31.0}],
                    "ring_actual_wall_ms": 20.0, "overlap_efficiency": 0.7,
                    "total_cpu_stage_ms": 0.0, "total_h2d_ms": 20.0,
                    "serial_expected_ms": 20.0, "thread_cpu_ms": 0.0, "minflt_delta": 0},
        (True, 3): {"pin": True, "buffers": 3, "records": [{"h2d_issue_ms": 2.5, "cpu_gbps": 11.0, "h2d_gbps": 32.0}],
                    "ring_actual_wall_ms": 21.0, "overlap_efficiency": 0.7,
                    "total_cpu_stage_ms": 0.0, "total_h2d_ms": 21.0,
                    "serial_expected_ms": 21.0, "thread_cpu_ms": 0.0, "minflt_delta": 0},
    }


class _RaisingRingBuffer(_RingBuffer):
    def __init__(self, log=None, kind="dest", raise_at=None):
        super().__init__(log, kind)
        self._raise_at = raise_at

    def copy_(self, src, non_blocking=False):
        # raise BEFORE super() so the count is not double-incremented
        if self._raise_at is not None and self.copy_calls + 1 >= self._raise_at:
            raise RuntimeError("%s copy boom" % self.kind)
        return super().copy_(src, non_blocking=non_blocking)


class _RaisingRingTorch(_FakeRingTorch):
    def __init__(self, raise_cuda_empty=False, pin_raise_at=None, dest_raise_at=None):
        super().__init__()
        self._raise_cuda_empty = raise_cuda_empty
        self._pin_raise_at = pin_raise_at
        self._dest_raise_at = dest_raise_at

    def empty(self, shape, *, dtype=None, pin_memory=False, device=None):
        self.empty_calls.append({
            "shape": list(shape), "dtype": dtype, "pin": bool(pin_memory), "device": device,
        })
        if not pin_memory and self._raise_cuda_empty:
            raise RuntimeError("dest alloc boom")
        _b = _RaisingRingBuffer(
            self.log, kind="pin" if pin_memory else "dest",
            raise_at=self._pin_raise_at if pin_memory else self._dest_raise_at,
        )
        self.empties.append(_b)
        return _b


class TestC6RingPlan(unittest.TestCase):
    def test_two_buffer_plan_no_overwrite(self):
        plan = mp._c6_ring_plan(8, 2)
        assert len(plan) == 8
        for p in plan:
            assert p["buffer"] == p["chunk"] % 2
        assert plan[0]["reuse_wait_chunk"] is None
        assert plan[1]["reuse_wait_chunk"] is None
        assert [p["reuse_wait_chunk"] for p in plan] == [None, None, 0, 1, 2, 3, 4, 5]

    def test_three_buffer_plan(self):
        plan = mp._c6_ring_plan(9, 3)
        assert [p["buffer"] for p in plan] == [0, 1, 2, 0, 1, 2, 0, 1, 2]
        assert [p["reuse_wait_chunk"] for p in plan] == [None, None, None, 0, 1, 2, 3, 4, 5]

    def test_one_buffer_serializes(self):
        plan = mp._c6_ring_plan(4, 1)
        for i, p in enumerate(plan):
            assert p["buffer"] == 0
            assert p["reuse_wait_chunk"] == (None if i == 0 else i - 1)

    def test_zero_buffers(self):
        plan = mp._c6_ring_plan(3, 0)
        assert all(p["buffer"] is None and p["reuse_wait_chunk"] is None for p in plan)


class TestC6RingRunFakeTorch(unittest.TestCase):
    def test_pinned_allocation_and_release(self):
        srcs = _make_ring_sources(5)
        fake = _FakeRingTorch()
        res = mp._c6_ring_run(srcs, pin=True, buffers=2, torch_mod=fake)
        assert res["error"] is None
        pin_allocs = [c for c in fake.empty_calls if c["pin"]]
        dest_allocs = [c for c in fake.empty_calls if not c["pin"]]
        assert len(pin_allocs) == 2  # one per ring slot, not per chunk
        assert len(dest_allocs) == 2
        assert fake.empty_cache_calls[0] >= 1
        assert len(res["records"]) == 5

    def test_pageable_path_no_pinned_alloc(self):
        srcs = _make_ring_sources(5)
        fake = _FakeRingTorch()
        res = mp._c6_ring_run(srcs, pin=False, buffers=0, torch_mod=fake)
        assert res["error"] is None
        assert all(not c["pin"] for c in fake.empty_calls)
        assert all(r["cpu_stage_ms"] == 0.0 and r["cpu_gbps"] == 0.0 for r in res["records"])
        assert res["overlap_efficiency"] is None

    def test_reuse_wait_synchronize_counts(self):
        srcs = _make_ring_sources(8)
        fake = _FakeRingTorch()
        res = mp._c6_ring_run(srcs, pin=True, buffers=2, torch_mod=fake)
        assert res["error"] is None
        assert res["records"][0]["reuse_wait_ms"] is None
        assert res["records"][1]["reuse_wait_ms"] is None
        waits = sum(1 for r in res["records"] if r["reuse_wait_ms"] is not None)
        assert waits == 6  # chunks 2..7

    def test_no_overwrite_while_dma_active(self):
        srcs = _make_ring_sources(8)
        fake = _FakeRingTorch()
        res = mp._c6_ring_run(srcs, pin=True, buffers=2, torch_mod=fake)
        assert res["error"] is None
        log = fake.log
        sync_positions = [i for i, op in enumerate(log) if op == "sync"]
        dest_positions = [i for i, op in enumerate(log)
                          if isinstance(op, tuple) and op[0] == "dest"]
        assert len(sync_positions) == 6
        for sp in sync_positions:
            nxt = next((dp for dp in dest_positions if dp > sp), None)
            assert nxt is not None, "reuse wait must precede the reuse write"

    def test_timing_reconciliation(self):
        srcs = _make_ring_sources(6)
        fake = _FakeRingTorch()
        res = mp._c6_ring_run(srcs, pin=True, buffers=2, torch_mod=fake)
        assert res["error"] is None
        assert abs(res["serial_expected_ms"]
                   - (res["total_cpu_stage_ms"] + res["total_h2d_ms"])) < 1e-6
        assert res["overlap_efficiency"] is not None
        assert 0.0 <= res["overlap_efficiency"] <= 1.0
        assert res["ring_actual_wall_ms"] <= res["serial_expected_ms"]

    def test_serial_equivalent_arithmetic(self):
        srcs = _make_ring_sources(5)
        fake = _FakeRingTorch()
        res = mp._c6_ring_run(srcs, pin=True, buffers=1, torch_mod=fake)
        assert res["error"] is None
        total_cpu = sum(r["cpu_stage_ms"] for r in res["records"])
        total_h2d = sum(r["h2d_cuda_ms"] for r in res["records"])
        assert abs(res["total_cpu_stage_ms"] - total_cpu) < 1e-9
        assert abs(res["total_h2d_ms"] - total_h2d) < 1e-9
        assert res["serial_expected_ms"] == round(
            res["total_cpu_stage_ms"] + res["total_h2d_ms"], 4)

    def test_temp_buffers_never_bind_live_model(self):
        model = torch.nn.Module()
        model.register_parameter("w", torch.nn.Parameter(torch.zeros(8, 8)))
        w0 = model.w.detach().clone()
        srcs = [{"ordinal": i, "key": "k%d" % i, "nbytes": 64, "data_ptr": None,
                 "storage_offset": 0, "is_view": True, "tensor": model.w} for i in range(5)]
        fake = _FakeRingTorch()
        res = mp._c6_ring_run(srcs, pin=True, buffers=2, torch_mod=fake)
        assert res["error"] is None
        assert torch.equal(model.w, w0)
        assert str(model.w.device) == "cpu"
        for rec in res["records"]:
            assert all(not isinstance(v, torch.nn.Module) and not isinstance(v, torch.Tensor)
                       for v in rec.values())

    def test_raise_fallback_captures_message_and_step(self):
        srcs = _make_ring_sources(5)
        fake = _RaisingRingTorch(pin_raise_at=1)  # first cpu-stage copy raises
        res = mp._c6_ring_run(srcs, pin=True, buffers=2, torch_mod=fake)
        assert res["error"] == "RuntimeError"
        assert res["error_msg"] == "pin copy boom"
        assert res["fail_step"] == "cpu_stage_copy"
        assert res["records"] == []

    def test_fail_step_dest_alloc(self):
        srcs = _make_ring_sources(5)
        fake = _RaisingRingTorch(raise_cuda_empty=True)
        res = mp._c6_ring_run(srcs, pin=True, buffers=2, torch_mod=fake)
        assert res["error"] == "RuntimeError"
        assert res["error_msg"] == "dest alloc boom"
        assert res["fail_step"] == "dest_alloc"
        assert res["records"] == []

    def test_fail_step_cpu_stage_copy(self):
        srcs = _make_ring_sources(5)
        fake = _RaisingRingTorch(pin_raise_at=1)
        res = mp._c6_ring_run(srcs, pin=True, buffers=2, torch_mod=fake)
        assert res["fail_step"] == "cpu_stage_copy"

    def test_partial_progress_records_preserved(self):
        srcs = _make_ring_sources(6)
        # with 1 buffer, the 3rd dest copy is chunk 2; chunks 0 and 1 already appended
        fake = _RaisingRingTorch(dest_raise_at=3)
        res = mp._c6_ring_run(srcs, pin=True, buffers=1, torch_mod=fake)
        assert res["error"] == "RuntimeError"
        assert res["error_msg"] == "dest copy boom"
        assert res["fail_step"] == "h2d_copy"
        assert len(res["records"]) == 2
        assert [r["ordinal"] for r in res["records"]] == [0, 1]

    def test_mixed_shapes_reallocate_slot_buffers(self):
        # ring slots see tensors of different shapes; buffers must be
        # reallocated per shape, never copied into a mismatched buffer
        shapes = [(10240, 3840), (3840, 10240), (11520, 3840)]
        srcs = [{
            "ordinal": i, "key": "k%d" % i, "nbytes": 4, "data_ptr": 0,
            "storage_offset": 0, "is_view": True, "tensor": torch.zeros(shapes[i % 3]),
        } for i in range(6)]
        for pin, buffers in ((True, 2), (False, 0)):
            fake = _FakeRingTorch()
            res = mp._c6_ring_run(srcs, pin=pin, buffers=buffers, torch_mod=fake)
            assert res["error"] is None
            assert len(res["records"]) == 6
            # reallocation happened: every distinct (slot, shape) combo reallocates
            assert len(fake.empty_calls) >= 3
            seen_shapes = {tuple(c["shape"]) for c in fake.empty_calls}
            assert seen_shapes == {(10240, 3840), (3840, 10240), (11520, 3840)}


class TestC6RingClassifier(unittest.TestCase):
    def _cfg(self, wall, eff, issue=None, cpu_gbps=None, h2d_gbps=None, error=None):
        d = {"pin": True, "buffers": 0, "records": [],
             "ring_actual_wall_ms": wall, "overlap_efficiency": eff,
             "total_cpu_stage_ms": 0.0, "total_h2d_ms": 0.0, "serial_expected_ms": 0.0}
        if error:
            d["error"] = error
        if issue is not None:
            d["records"] = [{"h2d_issue_ms": issue, "cpu_gbps": cpu_gbps, "h2d_gbps": h2d_gbps}]
        return d

    def test_prefers_two_when_p2_within_5pct_of_p3(self):
        res = mp._c6_ring_classify({
            "pageable": self._cfg(100.0, None),
            "pinned1": self._cfg(50.0, 0.1),
            "pinned2": self._cfg(20.0, 0.7),
            "pinned3": self._cfg(21.0, 0.7),
        })
        assert res["best_buffers"] == 2
        assert res["pageable_wall_ms"] == 100.0
        assert res["eff1"] == 0.1 and res["eff2"] == 0.7

    def test_pinned3_materially_better(self):
        res = mp._c6_ring_classify({
            "pageable": self._cfg(100.0, None),
            "pinned1": self._cfg(50.0, 0.1),
            "pinned2": self._cfg(20.0, 0.7),
            "pinned3": self._cfg(10.0, 0.9),
        })
        assert res["best_buffers"] == 3

    def test_error_config_ignored(self):
        res = mp._c6_ring_classify({
            "pageable": self._cfg(100.0, None, error="Boom"),
            "pinned1": self._cfg(50.0, 0.1),
            "pinned2": self._cfg(20.0, 0.7),
            "pinned3": self._cfg(21.0, 0.7),
        })
        assert res["best_buffers"] == 2
        assert res["pageable_wall_ms"] is None

    def test_medians(self):
        res = mp._c6_ring_classify({
            "pageable": self._cfg(100.0, None),
            "pinned1": self._cfg(50.0, 0.1, issue=2.0, cpu_gbps=10.0, h2d_gbps=30.0),
            "pinned2": self._cfg(20.0, 0.7, issue=3.0, cpu_gbps=12.0, h2d_gbps=31.0),
            "pinned3": self._cfg(21.0, 0.7, issue=2.5, cpu_gbps=11.0, h2d_gbps=32.0),
        })
        assert res["pinned_issue_ms_median"] == 2.5
        assert res["cpu_gbps_median"] == 11.0
        assert res["h2d_gbps_median"] == 31.0

    def test_all_error_best_none(self):
        res = mp._c6_ring_classify({
            "pageable": self._cfg(100.0, None, error="Boom"),
            "pinned1": self._cfg(50.0, 0.1, error="Boom"),
            "pinned2": self._cfg(20.0, 0.7, error="Boom"),
            "pinned3": self._cfg(21.0, 0.7, error="Boom"),
        })
        assert res["best_buffers"] is None


class TestC6RingOrchestrator(unittest.TestCase):
    def _run(self, trace, configs, srcs):
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        _saved_mode = mp._C6_PROBE_MODE
        _saved_srcs = mp._C6_RING_SOURCES
        mp._C6_PROBE_MODE = "probe"
        mp._C6_RING_SOURCES = srcs
        buf = io.StringIO()
        try:
            with mock.patch.object(mp, "_c6_ring_run",
                                   side_effect=lambda s, pin, buffers: configs[(pin, buffers)]), \
                 mock.patch.object(torch.cuda, "is_available", return_value=True), \
                 contextlib.redirect_stdout(buf):
                mp._c6_run_pinned_ring_probe()
            after = mp._C6_RING_SOURCES
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
            mp._C6_PROBE_MODE = _saved_mode
            mp._C6_RING_SOURCES = _saved_srcs
        return buf.getvalue(), after

    def test_orchestrator_end_to_end(self):
        trace = RuntimeTrace(request_id="ring", process="remote")
        out, after = self._run(trace, _fake_orchestrator_configs(), _make_ring_sources(8))
        assert after is None  # single-flight reset
        evs = [e for e in trace.events if e.name == "unet_i3_pinned_ring_probe"]
        assert len(evs) == 1
        meta = evs[0].metadata
        assert meta["verdict"] == "COMPLETE"
        assert meta["chunks"] == 8
        assert meta["classifier"]["best_buffers"] == 2
        assert "[v2.c6_probe] ring best=2" in out
        assert len(meta["records"]) == 4
        assert all(len(meta["records"][k]) <= 12 for k in meta["records"])
        json.dumps(evs[0].to_dict())

    def test_emitted_metadata_json_safe_with_dtype(self):
        configs = _fake_orchestrator_configs()
        configs[(True, 1)]["records"] = [{"h2d_issue_ms": 1.0, "dtype": torch.bfloat16}]
        trace = RuntimeTrace(request_id="ring", process="remote")
        out, after = self._run(trace, configs, _make_ring_sources(8))
        evs = [e for e in trace.events if e.name == "unet_i3_pinned_ring_probe"]
        json.dumps(evs[0].to_dict())  # must not raise
        assert evs[0].metadata["records"]["pinned1"][0]["dtype"] == "torch.bfloat16"

    def test_insufficient_sources_skipped(self):
        trace = RuntimeTrace(request_id="ring", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        _saved_mode = mp._C6_PROBE_MODE
        _saved_srcs = mp._C6_RING_SOURCES
        mp._C6_PROBE_MODE = "probe"
        mp._C6_RING_SOURCES = _make_ring_sources(2)
        buf = io.StringIO()
        try:
            with mock.patch.object(mp, "_c6_ring_run") as spy, \
                 contextlib.redirect_stdout(buf):
                mp._c6_run_pinned_ring_probe()
            spy.assert_not_called()
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
            mp._C6_PROBE_MODE = _saved_mode
            mp._C6_RING_SOURCES = _saved_srcs
        evs = [e for e in trace.events if e.name == "unet_i3_pinned_ring_probe"]
        assert len(evs) == 1
        assert evs[0].metadata["verdict"] == "SKIPPED"
        assert evs[0].metadata["reason"] == "insufficient_sources"
        assert "[v2.c6_probe] ring SKIPPED insufficient_sources" in buf.getvalue()

    def test_ring_run_raise_falls_back_safely(self):
        trace = RuntimeTrace(request_id="ring", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        _saved_mode = mp._C6_PROBE_MODE
        _saved_srcs = mp._C6_RING_SOURCES
        mp._C6_PROBE_MODE = "probe"
        mp._C6_RING_SOURCES = _make_ring_sources(8)
        buf = io.StringIO()
        after = None
        try:
            with mock.patch.object(mp, "_c6_ring_run", side_effect=RuntimeError("ring boom")), \
                 mock.patch.object(torch.cuda, "is_available", return_value=True), \
                 contextlib.redirect_stdout(buf):
                mp._c6_run_pinned_ring_probe()  # must not raise
            after = mp._C6_RING_SOURCES
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
            mp._C6_PROBE_MODE = _saved_mode
            mp._C6_RING_SOURCES = _saved_srcs
        assert "[v2.c6_probe] ring ERROR reason=RuntimeError:ring boom" in buf.getvalue()
        assert after is None

    def test_config_error_result_still_complete(self):
        configs = _fake_orchestrator_configs()
        configs[(False, 0)] = {"error": "Boom", "pin": False, "buffers": 0, "records": []}
        trace = RuntimeTrace(request_id="ring", process="remote")
        out, after = self._run(trace, configs, _make_ring_sources(8))
        evs = [e for e in trace.events if e.name == "unet_i3_pinned_ring_probe"]
        assert len(evs) == 1
        assert evs[0].metadata["verdict"] == "COMPLETE"
        assert evs[0].metadata["configs"]["pageable"]["error"] == "Boom"
        assert evs[0].metadata["classifier"]["best_buffers"] == 2

    def test_probe_off_noop(self):
        trace = RuntimeTrace(request_id="ring", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        _saved_mode = mp._C6_PROBE_MODE
        _saved_srcs = mp._C6_RING_SOURCES
        mp._C6_PROBE_MODE = "off"
        mp._C6_RING_SOURCES = _make_ring_sources(8)
        try:
            with mock.patch.object(mp, "_c6_ring_run") as spy, \
                 contextlib.redirect_stdout(io.StringIO()):
                mp._c6_run_pinned_ring_probe()
            spy.assert_not_called()
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
            mp._C6_PROBE_MODE = _saved_mode
            mp._C6_RING_SOURCES = _saved_srcs
        assert not any(e.name == "unet_i3_pinned_ring_probe" for e in trace.events)


class TestC6RingSourceCollection(unittest.TestCase):
    def test_proxy_collects_large_tensors(self):
        trace, lane = _make_lane()

        class _HugeTensor:
            shape = [15000000]
            dtype = torch.float32
            _base = None

            def numel(self):
                return 15000000

            def element_size(self):
                return 4

            def data_ptr(self):
                return 0x1000

            def storage_offset(self):
                return 0

        class FakeSafeOpen:
            def get_tensor(self, k):
                return _HugeTensor()

        proxy = _SafeOpenProxy(FakeSafeOpen(), FakeSafeOpen().get_tensor, [0], [0], series=[])
        _saved_srcs = mp._C6_RING_SOURCES
        _saved_mode = mp._C6_PROBE_MODE
        mp._C6_RING_SOURCES = None
        mp._C6_PROBE_MODE = "probe"
        try:
            with _active_lane(lane), \
                 mock.patch.object(mp, "_DIAGNOSTIC_FLAG", True), \
                 mock.patch.object(torch.cuda, "is_available", return_value=False):
                for i in range(3):
                    proxy.get_tensor("t%d" % i)
                proxy.__exit__()
        finally:
            mp._C6_PROBE_MODE = _saved_mode
        try:
            holder = mp._C6_RING_SOURCES
            assert holder is not None
            assert len(holder) == 3
            assert all(s["nbytes"] >= 60000000 for s in holder)
            assert [s["key"] for s in holder] == ["t0", "t1", "t2"]
        finally:
            mp._C6_RING_SOURCES = _saved_srcs

    def test_proxy_fallback_30mb_candidates(self):
        trace, lane = _make_lane()

        class _MidTensor:
            shape = [10000000]
            dtype = torch.float32
            _base = None

            def numel(self):
                return 10000000

            def element_size(self):
                return 4

            def data_ptr(self):
                return 0x2000

            def storage_offset(self):
                return 0

        class FakeSafeOpen:
            def get_tensor(self, k):
                return _MidTensor()

        proxy = _SafeOpenProxy(FakeSafeOpen(), FakeSafeOpen().get_tensor, [0], [0], series=[])
        _saved_srcs = mp._C6_RING_SOURCES
        _saved_mode = mp._C6_PROBE_MODE
        mp._C6_RING_SOURCES = None
        mp._C6_PROBE_MODE = "probe"
        try:
            with _active_lane(lane), \
                 mock.patch.object(mp, "_DIAGNOSTIC_FLAG", True), \
                 mock.patch.object(torch.cuda, "is_available", return_value=False):
                for i in range(3):
                    proxy.get_tensor("t%d" % i)
                proxy.__exit__()
        finally:
            mp._C6_PROBE_MODE = _saved_mode
        try:
            holder = mp._C6_RING_SOURCES
            assert holder is not None
            assert len(holder) == 3  # top-up from the 30MB+ fallback at read end
            assert all(30000000 <= s["nbytes"] < 60000000 for s in holder)
        finally:
            mp._C6_RING_SOURCES = _saved_srcs

    def test_proxy_collects_nothing_when_off(self):
        trace, lane = _make_lane()

        class _HugeTensor:
            shape = [15000000]
            dtype = torch.float32
            _base = None

            def numel(self):
                return 15000000

            def element_size(self):
                return 4

            def data_ptr(self):
                return 0

            def storage_offset(self):
                return 0

        class FakeSafeOpen:
            def get_tensor(self, k):
                return _HugeTensor()

        proxy = _SafeOpenProxy(FakeSafeOpen(), FakeSafeOpen().get_tensor, [0], [0], series=[])
        _saved_srcs = mp._C6_RING_SOURCES
        _saved_mode = mp._C6_PROBE_MODE
        mp._C6_RING_SOURCES = []
        mp._C6_PROBE_MODE = "off"
        try:
            with _active_lane(lane), \
                 mock.patch.object(mp, "_DIAGNOSTIC_FLAG", True), \
                 mock.patch.object(torch.cuda, "is_available", return_value=False):
                proxy.get_tensor("t0")
                proxy.__exit__()
        finally:
            mp._C6_PROBE_MODE = _saved_mode
            mp._C6_RING_SOURCES = _saved_srcs
        # untouched when probe is off
        assert mp._C6_RING_SOURCES == []


# ── 21. Production pinned-ring UNET fast path (default OFF) ──────────────


class _RingMeta(type):
    def __new__(mcs, name, bases, ns):
        return super().__new__(mcs, ns.get("__type_name__", name), bases, ns)


class _RingZImage(metaclass=_RingMeta):
    __type_name__ = "ZImage"

    def __init__(self, unet_config=None):
        self.unet_config = dict(unet_config or {"n_layers": 24, "dim": 3840})
        self.supported_inference_dtypes = [torch.bfloat16]
        self.manual_cast_dtype = None

    def get_model(self, sd, prefix):
        model = torch.nn.Module()
        for _k, _v in sd.items():
            _parts = _k.split(".")
            _m = model
            for _p in _parts[:-1]:
                _nxt = getattr(_m, _p, None)
                if _nxt is None:
                    _nxt = torch.nn.Module()
                    _m.add_module(_p, _nxt)
                _m = _nxt
            _m.register_parameter(
                _parts[-1], torch.nn.Parameter(torch.zeros(tuple(_v.shape), dtype=_v.dtype)))
        return model

    def process_unet_state_dict(self, state_dict):
        return state_dict

    def set_inference_dtype(self, dtype, manual_cast):
        self.unet_config["dtype"] = dtype
        self.manual_cast_dtype = manual_cast


class _RingLumina2(metaclass=_RingMeta):
    __type_name__ = "Lumina2"

    def __init__(self):
        self.unet_config = {"n_layers": 24}
        self.supported_inference_dtypes = [torch.bfloat16]

    def process_unet_state_dict(self, state_dict):
        return state_dict


class _RingPatcher:
    def __init__(self, model, load_device=None, offload_device=None):
        self.model = model
        self.load_device = load_device
        self.offload_device = offload_device


_RING_HEADER = {
    "model.diffusion_model.layers.0.ffn_norm1.weight": {"dtype": "BF16", "shape": [24], "data_offsets": [0, 48]},
    "model.diffusion_model.layers.22.ffn_norm1.weight": {"dtype": "BF16", "shape": [24], "data_offsets": [48, 96]},
}


def _ring_derived(config=None, header=None):
    return (config if config is not None else _RingZImage(),
            {}, header if header is not None else dict(_RING_HEADER), 24, "model.diffusion_model.")


_ELIG_DERIVED_SENTINEL = object()


@contextlib.contextmanager
def _ring_eligibility_env(derived=_ELIG_DERIVED_SENTINEL, high_vram=True, torch_future=False,
                          evidence=None, value_probe=True, cuda_available=True, pinned_ok=True,
                          get_full_path="fake.safetensors"):
    _real_c6 = mp._c6_comfy_fn

    def _fake_c6(mod, attr, fallback=None):
        if mod == "comfy.folder_paths" and attr == "get_full_path":
            return (lambda kind, name: get_full_path) if get_full_path else None
        if mod == "comfy.model_management" and attr == "get_torch_device":
            return lambda: torch.device("cuda")
        return _real_c6(mod, attr, fallback)

    _ev = evidence if evidence is not None else {
        "quant_config_present": False, "custom_operations_present": False,
        "fp8_optimization": False, "force_channels_last": False,
    }
    _derived = _ring_derived() if derived is _ELIG_DERIVED_SENTINEL else derived
    with mock.patch.object(mp, "_ring_resolve_unet_path", return_value=get_full_path), \
         mock.patch.object(mp, "_ring_derive_config", return_value=_derived), \
         mock.patch.object(mp, "_fast_disk_high_vram", return_value=high_vram), \
         mock.patch.object(mp, "_fast_disk_torch_future_enabled", return_value=torch_future), \
         mock.patch.object(mp, "_fast_disk_model_config_evidence", return_value=_ev), \
         mock.patch.object(mp, "_c6_value_probe_allow_fp16", return_value=value_probe), \
         mock.patch.object(mp, "_c6_comfy_fn", side_effect=_fake_c6), \
         mock.patch.object(torch.cuda, "is_available", return_value=cuda_available):
        if pinned_ok:
            with mock.patch.object(torch, "empty", return_value=torch.zeros(1)):
                yield
        else:
            def _boom(*a, **k):
                raise RuntimeError("pinned boom")

            with mock.patch.object(torch, "empty", side_effect=_boom):
                yield


def _run_eligibility(kwargs=None, **env):
    with _ring_eligibility_env(**env):
        return mp._ring_eligible(
            None, None,
            kwargs if kwargs is not None else {"unet_name": "z.safetensors", "weight_dtype": "default"},
            None)


class TestRingPathResolution(unittest.TestCase):
    def _fake_fp(self, or_raise=None, plain=None):
        import types as _types_fp
        _fp = _types_fp.ModuleType("folder_paths")
        if or_raise is not None:
            _fp.get_full_path_or_raise = or_raise
        if plain is not None:
            _fp.get_full_path = plain
        return _fp

    def test_or_raise_wins(self):
        fake = self._fake_fp(or_raise=lambda f, n: "/models/" + n,
                             plain=lambda f, n: "/WRONG/" + n)
        with mock.patch.dict(sys.modules, {"folder_paths": fake}):
            assert mp._ring_resolve_unet_path("z.safetensors", None) == "/models/z.safetensors"

    def test_plain_fallback(self):
        fake = self._fake_fp(plain=lambda f, n: "/models/" + n)
        with mock.patch.dict(sys.modules, {"folder_paths": fake}):
            assert mp._ring_resolve_unet_path("z.safetensors", None) == "/models/z.safetensors"

    def test_lane_resolved_path_fallback(self):
        # folder_paths absent -> lane trace resolved_path used
        class _Tr:
            _metadata = {"resolved_path": "/models/lane/z.safetensors"}
        class _Ln:
            _trace = _Tr()
        _saved = sys.modules.get("folder_paths")
        sys.modules.pop("folder_paths", None)
        try:
            assert mp._ring_resolve_unet_path("z.safetensors", _Ln()) == "/models/lane/z.safetensors"
        finally:
            if _saved is not None:
                sys.modules["folder_paths"] = _saved

    def test_all_fail_returns_none(self):
        fake = self._fake_fp(or_raise=lambda f, n: None, plain=lambda f, n: None)
        with mock.patch.dict(sys.modules, {"folder_paths": fake}):
            assert mp._ring_resolve_unet_path("z.safetensors", None) is None

    def test_missing_module_never_raises(self):
        _saved = sys.modules.get("folder_paths")
        sys.modules.pop("folder_paths", None)
        try:
            assert mp._ring_resolve_unet_path("z.safetensors", None) is None
            assert mp._ring_resolve_unet_path("", None) is None
        finally:
            if _saved is not None:
                sys.modules["folder_paths"] = _saved


class TestRingFlag(unittest.TestCase):
    def test_flag_values(self):
        cases = [("1", "on"), ("true", "on"), ("yes", "on"), ("on", "on"), ("ON", "on"),
                 ("", "off"), ("0", "off"), ("false", "off"), ("no", "off"), ("off", "off"),
                 ("none", "off"), ("garbage", "invalid"), ("2", "invalid")]
        for raw, expected in cases:
            env = {} if raw == "" else {"COMFYMODAL_V2_UNET_PINNED_RING": raw}
            with mock.patch.dict(os.environ, env, clear=True):
                assert mp._ring_flag_value() == expected

    def test_invalid_never_enables(self):
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_PINNED_RING": "garbage"}, clear=True):
            assert mp._ring_pipeline_enabled() is False

    def test_off_zero_pipeline_calls(self):
        bridge = _RingBridge()
        model_key = SimpleNamespace(unet_identity="z.safetensors")
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_PINNED_RING": "off"}, clear=True), \
             mock.patch.object(mp, "_ring_try_pipeline") as spy, \
             _load_unet_deps():
            mp.V2LoaderBridge._load_unet(bridge, model_key)
        spy.assert_not_called()
        assert len(bridge.invoke_calls) == 1


class _RingBridge:
    def __init__(self):
        self._trace = RuntimeTrace(request_id="ring-bridge", process="remote")
        self.invoke_calls = []

    def _find_request(self, kind, identity):
        return {"unet_name": "z.safetensors", "weight_dtype": "default"}

    def _invoke_original(self, cls, kwargs):
        self.invoke_calls.append((cls, dict(kwargs)))
        return (SimpleNamespace(ok=True),)


@contextlib.contextmanager
def _load_unet_deps():
    with mock.patch.object(mp, "resolve_unet_effective_dtype",
                           return_value=("default", "default")), \
         mock.patch.object(mp, "register_unet_forward_probe", lambda *a, **k: None), \
         mock.patch.object(mp, "collect_unet_runtime_state", lambda *a, **k: {}):
        yield


class TestRingEligibility(unittest.TestCase):
    def test_family_gate(self):
        ok, reason = _run_eligibility(derived=_ring_derived(config=_RingLumina2()))
        assert (ok, reason) == (False, "family_not_zimage")

    def test_config_derivation_failed(self):
        ok, reason = _run_eligibility(derived=None)
        assert (ok, reason) == (False, "config_derivation_failed")

    def test_value_probe_unresolved(self):
        ok, reason = _run_eligibility(value_probe=None)
        assert (ok, reason) == (False, "value_probe_unresolved")

    def test_path_unresolved(self):
        ok, reason = _run_eligibility(get_full_path=None)
        assert (ok, reason) == (False, "path_unresolved")

    def test_not_high_vram(self):
        ok, reason = _run_eligibility(high_vram=False)
        assert (ok, reason) == (False, "not_high_vram")

    def test_torch_future(self):
        ok, reason = _run_eligibility(torch_future=True)
        assert (ok, reason) == (False, "torch_future")

    def test_quant_config_present(self):
        ev = {"quant_config_present": True, "custom_operations_present": False,
              "fp8_optimization": False, "force_channels_last": False}
        ok, reason = _run_eligibility(evidence=ev)
        assert (ok, reason) == (False, "quant_config_present")

    def test_fp8_optimization(self):
        ev = {"quant_config_present": False, "custom_operations_present": False,
              "fp8_optimization": True, "force_channels_last": False}
        ok, reason = _run_eligibility(evidence=ev)
        assert (ok, reason) == (False, "fp8_optimization")

    def test_force_channels_last(self):
        ev = {"quant_config_present": False, "custom_operations_present": False,
              "fp8_optimization": False, "force_channels_last": True}
        ok, reason = _run_eligibility(evidence=ev)
        assert (ok, reason) == (False, "force_channels_last")

    def test_dtype_conversion_requested(self):
        ok, reason = _run_eligibility(kwargs={"unet_name": "z.safetensors", "weight_dtype": "fp8_e4m3fn"})
        assert (ok, reason) == (False, "dtype_conversion_requested")

    def test_non_uniform_dtype(self):
        header = {
            "model.diffusion_model.a": {"dtype": "BF16", "shape": [2], "data_offsets": [0, 4]},
            "model.diffusion_model.b": {"dtype": "F32", "shape": [2], "data_offsets": [4, 12]},
        }
        ok, reason = _run_eligibility(derived=_ring_derived(header=header))
        assert (ok, reason) == (False, "non_uniform_dtype")

    def test_unsupported_dtype(self):
        header = {
            "model.diffusion_model.a": {"dtype": "I32", "shape": [2], "data_offsets": [0, 8]},
        }
        ok, reason = _run_eligibility(derived=_ring_derived(header=header))
        assert (ok, reason) == (False, "unsupported_dtype")

    def test_cuda_unavailable(self):
        ok, reason = _run_eligibility(cuda_available=False)
        assert (ok, reason) == (False, "cuda_unavailable")

    def test_pinned_unavailable(self):
        ok, reason = _run_eligibility(pinned_ok=False)
        assert (ok, reason) == (False, "pinned_unavailable")

    def test_eligible_ok(self):
        ok, reason = _run_eligibility()
        assert (ok, reason) == (True, "")


def _derive_c6_fake(mod, attr, fallback=None):
    if mod == "comfy.model_detection" and attr == "unet_prefix_from_state_dict":
        return lambda sd: "model.diffusion_model."
    if mod == "comfy.utils" and attr == "state_dict_prefix_replace":
        def _strip(sd, repl, filter_keys=False):
            if filter_keys:
                return {k.replace("model.diffusion_model.", "", 1): v
                        for k, v in sd.items() if k.startswith("model.diffusion_model.")}
            return sd
        return _strip
    if mod == "comfy.utils" and attr == "calculate_parameters":
        return lambda sd, prefix="": sum(v.nelement() for k, v in sd.items() if k.startswith(prefix))
    if mod == "comfy.utils" and attr == "weight_dtype":
        def _wd(sd, prefix=""):
            dtypes = {}
            for k, v in sd.items():
                if k.startswith(prefix):
                    dtypes[v.dtype] = dtypes.get(v.dtype, 0) + v.numel()
            if not dtypes:
                return None
            return max(dtypes, key=dtypes.get)
        return _wd
    if mod == "comfy.model_detection" and attr == "model_config_from_unet":
        return lambda sd, prefix, metadata=None: _RingZImage()
    if mod == "comfy.model_management" and attr == "extended_fp16_support":
        return lambda: True
    if mod == "comfy.model_management" and attr == "unet_dtype":
        return lambda **kw: kw.get("weight_dtype") or torch.bfloat16
    if mod == "comfy.model_management" and attr == "unet_manual_cast":
        return lambda *a, **k: None
    if mod == "comfy.model_management" and attr == "unet_offload_device":
        return lambda: torch.device("cuda")
    return fallback


class TestRingDeriveConfig(unittest.TestCase):
    def _derive(self, value_probe=True):
        with mock.patch.object(mp, "_c6_parse_safetensors_header", return_value=dict(_RING_HEADER)), \
             mock.patch.object(mp, "_c6_comfy_fn", side_effect=_derive_c6_fake), \
             mock.patch.object(mp, "_c6_value_probe_allow_fp16", return_value=value_probe):
            return mp._ring_derive_config("fake.safetensors")

    def test_derive_zimage_config(self):
        result = self._derive()
        assert result is not None
        config, meta_sd, header, n_layers, prefix = result
        assert type(config).__name__ == "ZImage"
        assert n_layers == 24
        assert prefix == "model.diffusion_model."
        assert config.unet_config.get("allow_fp16") is True
        assert config.supported_inference_dtypes == [torch.bfloat16, torch.float16]
        assert config.unet_config.get("dtype") is not None
        assert set(meta_sd.keys()) == {"layers.0.ffn_norm1.weight", "layers.22.ffn_norm1.weight"}

    def test_derive_allow_fp16_false(self):
        result = self._derive(value_probe=False)
        config = result[0]
        assert config.unet_config.get("allow_fp16") is False
        assert config.supported_inference_dtypes == [torch.bfloat16]

    def test_derive_value_probe_unresolved(self):
        assert self._derive(value_probe=None) is None

    def test_effective_prefix_regression(self):
        # unet_prefix_from_state_dict returns the heuristic default "model."
        # for unprefixed ZImage keys; the strip falls back and the effective
        # prefix must be "" (previously the raw "model." was returned and
        # _ring_run_waves reconstructed bogus file keys -> KeyError)
        header = {
            "layers.0.ffn_norm1.weight": {"dtype": "BF16", "shape": [24], "data_offsets": [0, 48]},
            "layers.22.ffn_norm1.weight": {"dtype": "BF16", "shape": [24], "data_offsets": [48, 96]},
        }
        _real_c6 = mp._c6_comfy_fn

        def _fake_c6(mod, attr, fallback=None):
            if mod == "comfy.model_detection" and attr == "unet_prefix_from_state_dict":
                return lambda sd: "model."
            if mod == "comfy.utils" and attr == "state_dict_prefix_replace":
                return lambda sd, repl, filter_keys=False: (
                    {k.replace("model.", "", 1): v for k, v in sd.items() if k.startswith("model.")}
                    if filter_keys else sd)
            return _derive_c6_fake(mod, attr, fallback)

        with mock.patch.object(mp, "_c6_parse_safetensors_header", return_value=header), \
             mock.patch.object(mp, "_c6_comfy_fn", side_effect=_fake_c6), \
             mock.patch.object(mp, "_c6_value_probe_allow_fp16", return_value=True):
            result = mp._ring_derive_config("fake.safetensors")
        assert result is not None
        config, meta_sd, header2, n_layers, eff_prefix = result
        assert eff_prefix == ""
        assert set(meta_sd.keys()) == {"layers.0.ffn_norm1.weight", "layers.22.ffn_norm1.weight"}
        # run waves with the effective prefix: get_tensor gets unprefixed keys
        fake = _RunFakeTorch()
        requested = []

        class _RecOpen(_RunFakeOpen):
            def get_tensor(self, k):
                requested.append(k)
                return super().get_tensor(k)

        tensors = {
            "layers.0.ffn_norm1.weight": torch.full((24,), 1.0, dtype=torch.bfloat16),
            "layers.22.ffn_norm1.weight": torch.full((24,), 2.0, dtype=torch.bfloat16),
        }
        with mock.patch("safetensors.safe_open", return_value=_RecOpen(tensors)):
            res = mp._ring_run_waves(None, {}, "fake.safetensors", {}, [list(meta_sd.keys())], None,
                                     prefix=eff_prefix, target=torch.device("cuda"), torch_mod=fake)
        assert res is not None and res[0] is not None
        assert requested == ["layers.0.ffn_norm1.weight", "layers.22.ffn_norm1.weight"]

    def test_prefixed_effective_prefix(self):
        # genuinely prefixed keys keep the effective prefix and get_tensor
        # is called with prefix + stripped key
        with mock.patch.object(mp, "_c6_parse_safetensors_header", return_value=dict(_RING_HEADER)), \
             mock.patch.object(mp, "_c6_comfy_fn", side_effect=_derive_c6_fake), \
             mock.patch.object(mp, "_c6_value_probe_allow_fp16", return_value=True):
            result = mp._ring_derive_config("fake.safetensors")
        assert result is not None
        config, meta_sd, header, n_layers, eff_prefix = result
        assert eff_prefix == "model.diffusion_model."
        assert all(not k.startswith("model.diffusion_model.") for k in meta_sd.keys())
        fake = _RunFakeTorch()
        requested = []

        class _RecOpen(_RunFakeOpen):
            def get_tensor(self, k):
                requested.append(k)
                return super().get_tensor(k)

        tensors = {
            "model.diffusion_model.layers.0.ffn_norm1.weight": torch.full((24,), 1.0, dtype=torch.bfloat16),
            "model.diffusion_model.layers.22.ffn_norm1.weight": torch.full((24,), 2.0, dtype=torch.bfloat16),
        }
        with mock.patch("safetensors.safe_open", return_value=_RecOpen(tensors)):
            res = mp._ring_run_waves(None, {}, "fake.safetensors", {}, [list(meta_sd.keys())], None,
                                     prefix=eff_prefix, target=torch.device("cuda"), torch_mod=fake)
        assert res is not None and res[0] is not None
        assert requested == ["model.diffusion_model.layers.0.ffn_norm1.weight",
                             "model.diffusion_model.layers.22.ffn_norm1.weight"]

    def test_value_probe_wall_recorded(self):
        def _slow_vp(path, header, n_layers):
            _end = time.monotonic_ns() + 2_000_000  # ~2ms busy wait
            while time.monotonic_ns() < _end:
                pass
            return True

        _probe_wall = {}
        with mock.patch.object(mp, "_c6_parse_safetensors_header", return_value=dict(_RING_HEADER)), \
             mock.patch.object(mp, "_c6_comfy_fn", side_effect=_derive_c6_fake), \
             mock.patch.object(mp, "_c6_value_probe_allow_fp16", side_effect=_slow_vp):
            result = mp._ring_derive_config("fake.safetensors", _probe_wall=_probe_wall)
        assert result is not None
        assert "value_probe_wall_ms" in _probe_wall
        assert _probe_wall["value_probe_wall_ms"] > 0


class TestRingWaveBuild(unittest.TestCase):
    def test_packing_order(self):
        waves = mp._ring_wave_build(["a", "b", "c", "d"],
                                    {"a": 30, "b": 30, "c": 70, "d": 40},
                                    target_bytes=64, max_bytes=128)
        assert waves == [["a", "b"], ["c"], ["d"]]

    def test_pack_under_target(self):
        waves = mp._ring_wave_build(["a", "b"], {"a": 30, "b": 30},
                                    target_bytes=64, max_bytes=128)
        assert waves == [["a", "b"]]

    def test_large_tensor_own_wave(self):
        waves = mp._ring_wave_build(["a", "b"], {"a": 70, "b": 30},
                                    target_bytes=64, max_bytes=128)
        assert waves == [["a"], ["b"]]

    def test_tensor_exceeds_cap(self):
        assert mp._ring_wave_build(["a"], {"a": 200}, target_bytes=64, max_bytes=128) is None


class _RunFakeTorch:
    def __init__(self):
        self.empty_calls = []
        self.empties = []
        self.sync_calls = []
        self.log = []
        self.empty_cache_calls = [0]
        self.cuda = SimpleNamespace(
            Event=lambda enable_timing=True: _RingEvent(self.log),
            synchronize=lambda: self.sync_calls.append("sync"),
            empty_cache=lambda: self.empty_cache_calls.__setitem__(0, self.empty_cache_calls[0] + 1),
        )

    def empty(self, shape, *, dtype=None, pin_memory=False, device=None):
        _sz = [shape] if isinstance(shape, int) else list(shape)
        self.empty_calls.append({"shape": _sz, "pin": bool(pin_memory), "device": device})
        _t = torch.zeros(*_sz, dtype=dtype)
        self.empties.append(_t)
        return _t


class _RunFakeOpen:
    def __init__(self, tensors):
        self._t = tensors
        self.enter_calls = 0
        self.exit_calls = 0

    def get_tensor(self, k):
        return self._t[k]

    def __enter__(self):
        self.enter_calls += 1
        return self

    def __exit__(self, *a):
        self.exit_calls += 1
        return None


def _ring_run_sources(model, prefix="model.diffusion_model."):
    tensors = {}
    for _i, (_k, _p) in enumerate(model.named_parameters()):
        tensors[prefix + _k] = torch.full(tuple(_p.shape), float(_i + 1), dtype=_p.dtype)
    return tensors


class TestRingRun(unittest.TestCase):
    def _run(self, model, waves, prefix="model.diffusion_model."):
        params = dict(model.named_parameters())
        fake = _RunFakeTorch()
        fake_open = _RunFakeOpen(_ring_run_sources(model, prefix))
        with mock.patch("safetensors.safe_open", return_value=fake_open):
            res = mp._ring_run_waves(model, params, "fake.safetensors", {}, waves, None,
                                     prefix=prefix, target=torch.device("cuda"), torch_mod=fake)
        return res, fake

    def test_binds_params_to_dests(self):
        model = torch.nn.Module()
        model.register_parameter("a", torch.nn.Parameter(torch.zeros(4, 4, dtype=torch.bfloat16)))
        model.register_parameter("b", torch.nn.Parameter(torch.zeros(2, 2, dtype=torch.bfloat16)))
        res, fake = self._run(model, [["a"], ["b"]])
        assert res is not None
        dest_calls = [i for i, c in enumerate(fake.empty_calls) if not c["pin"]]
        assert len(dest_calls) == 2
        # param.data re-points to the dest storage (values live there)
        assert model.a.data_ptr() == fake.empties[dest_calls[0]].data_ptr()
        assert model.b.data_ptr() == fake.empties[dest_calls[1]].data_ptr()
        assert isinstance(model.a, torch.nn.Parameter)
        assert model.a.requires_grad is True
        assert model._parameters["a"] is model.a
        # params reference the dests, not the mmap source tensors
        assert model.a.data_ptr() != _ring_run_sources(model)["model.diffusion_model.a"].data_ptr()
        # no module-level synchronize anywhere in the loop
        assert fake.sync_calls == []

    def test_two_slots_only(self):
        model = torch.nn.Module()
        model.register_parameter("a", torch.nn.Parameter(torch.zeros(4, dtype=torch.bfloat16)))
        model.register_parameter("b", torch.nn.Parameter(torch.zeros(4, dtype=torch.bfloat16)))
        model.register_parameter("c", torch.nn.Parameter(torch.zeros(4, dtype=torch.bfloat16)))
        model.register_parameter("d", torch.nn.Parameter(torch.zeros(4, dtype=torch.bfloat16)))
        res, fake = self._run(model, [["a"], ["b"], ["c"], ["d"]])
        assert res is not None
        pin_calls = [c for c in fake.empty_calls if c["pin"]]
        assert len(pin_calls) == 2  # exactly two flat pinned slots, no per-wave allocs

    def test_slot_reuse_wait_ordering(self):
        model = torch.nn.Module()
        model.register_parameter("a", torch.nn.Parameter(torch.zeros(4, dtype=torch.bfloat16)))
        model.register_parameter("b", torch.nn.Parameter(torch.zeros(4, dtype=torch.bfloat16)))
        model.register_parameter("c", torch.nn.Parameter(torch.zeros(4, dtype=torch.bfloat16)))
        model.register_parameter("d", torch.nn.Parameter(torch.zeros(4, dtype=torch.bfloat16)))
        res, fake = self._run(model, [["a"], ["b"], ["c"], ["d"]])
        assert res is not None
        # waves 2 and 3 each waited on the previous DMA of their slot
        assert fake.log.count("sync") == 2
        assert fake.sync_calls == []

    def test_slot_grows_to_largest(self):
        model = torch.nn.Module()
        model.register_parameter("a", torch.nn.Parameter(torch.zeros(2, dtype=torch.bfloat16)))
        model.register_parameter("b", torch.nn.Parameter(torch.zeros(2, dtype=torch.bfloat16)))
        model.register_parameter("c", torch.nn.Parameter(torch.zeros(8, dtype=torch.bfloat16)))
        model.register_parameter("d", torch.nn.Parameter(torch.zeros(2, dtype=torch.bfloat16)))
        res, fake = self._run(model, [["a"], ["b"], ["c"], ["d"]])
        assert res is not None
        pin_calls = [c for c in fake.empty_calls if c["pin"]]
        # slot0: a(2) then c(8) realloc = 2 allocs; slot1: b(2), d(2) = 1 alloc
        assert len(pin_calls) == 3

    def test_buffer_binding(self):
        # an sd key mapping to a submodule buffer is bound via buf.data
        unet = torch.nn.Module()
        unet.register_buffer("buf", torch.zeros(4, dtype=torch.bfloat16))
        model = torch.nn.Module()
        model.diffusion_model = unet
        buffers = dict(unet.named_buffers())  # {"buf": <buffer>}
        fake = _RunFakeTorch()
        fake_open = _RunFakeOpen({
            "model.diffusion_model.buf": torch.full((4,), 7.0, dtype=torch.bfloat16),
        })
        with mock.patch("safetensors.safe_open", return_value=fake_open):
            res = mp._ring_run_waves(model, {}, "fake.safetensors", {}, [["buf"]], None,
                                     prefix="model.diffusion_model.", target=torch.device("cuda"),
                                     torch_mod=fake, buffers=buffers)
        assert res is not None
        dest_calls = [i for i, c in enumerate(fake.empty_calls) if not c["pin"]]
        assert len(dest_calls) == 1
        assert unet.buf.data_ptr() == fake.empties[dest_calls[0]].data_ptr()

    def test_failure_reason_stage_copy(self):
        model = torch.nn.Module()
        model.register_parameter("a", torch.nn.Parameter(torch.zeros(4, dtype=torch.bfloat16)))
        params = dict(model.named_parameters())
        fake = _RunFakeTorch()
        fake_open = _RunFakeOpen({
            "model.diffusion_model.a": torch.full((4,), 1.0, dtype=torch.bfloat16),
        })
        _calls = [0]

        def _boom_copy(self, *a, **k):
            _calls[0] += 1
            if _calls[0] == 1:  # the first copy_ is the CPU stage copy
                raise RuntimeError("stage copy boom")
            return None

        with mock.patch("safetensors.safe_open", return_value=fake_open), \
             mock.patch.object(torch.Tensor, "copy_", _boom_copy):
            res = mp._ring_run_waves(model, params, "fake.safetensors", {}, [["a"]], None,
                                     prefix="model.diffusion_model.", target=torch.device("cuda"),
                                     torch_mod=fake)
        assert isinstance(res, tuple) and res[0] is None
        assert res[1].startswith("stage_copy:")


def _bind_cuda(params):
    for _k, _p in params.items():
        _p.data = torch.zeros(*tuple(_p.shape), dtype=_p.dtype, device="cuda")


@contextlib.contextmanager
def _ring_pipeline_env(ring_run_side_effect=None, config=None, eligible=(True, ""), derived=None,
                       resolved_path="fake.safetensors"):
    _real_c6 = mp._c6_comfy_fn

    def _fake_c6(mod, attr, fallback=None):
        if mod == "comfy.model_management" and attr == "get_torch_device":
            return lambda: torch.device("cuda")
        if mod == "comfy.model_management" and attr == "unet_offload_device":
            return lambda: torch.device("cuda")
        if mod == "comfy.model_patcher" and attr == "ModelPatcher":
            return _RingPatcher
        return _real_c6(mod, attr, fallback)

    _cfg = config if config is not None else _RingZImage()
    _derived = derived if derived is not None else (None, None, None, None, None)
    with mock.patch.object(mp, "_ring_resolve_unet_path", return_value=resolved_path), \
         mock.patch.object(mp, "_c6_comfy_fn", side_effect=_fake_c6), \
         mock.patch.object(mp, "_ring_eligible", return_value=eligible), \
         mock.patch.object(mp, "_ring_derive_config", return_value=_derived), \
         mock.patch.object(mp, "_ring_run_waves", side_effect=ring_run_side_effect) as spy, \
         mock.patch.object(torch.cuda, "is_available", return_value=True), \
         mock.patch.object(torch.cuda, "synchronize", lambda: None):
        yield spy, _cfg


def _pipeline_model(prefix_keys=True):
    model = torch.nn.Module()
    model.register_parameter("layers.0.weight",
                             torch.nn.Parameter(torch.zeros(4, 4, dtype=torch.bfloat16)))
    return model


def _pipeline_meta_sd():
    return {"layers.0.weight": torch.empty((4, 4), dtype=torch.bfloat16, device="meta")}


def _unet_module_with_names(names_shapes):
    """Build a UNet-like module with nested params from dotted names."""
    _unet = torch.nn.Module()
    for _n, _sh in names_shapes.items():
        _parts = _n.split(".")
        _m = _unet
        for _p in _parts[:-1]:
            _nxt = getattr(_m, _p, None)
            if _nxt is None:
                _nxt = torch.nn.Module()
                _m.add_module(_p, _nxt)
            _m = _nxt
        _m.register_parameter(_parts[-1], torch.nn.Parameter(
            torch.zeros(*_sh, dtype=torch.bfloat16)))
    return _unet


def _default_ring_run_side_effect(bind=True):
    def _side(model, params, path, header, waves, lane, prefix="", target=None, torch_mod=None, buffers=None):
        if bind:
            _bind_cuda(params)
        return ({"pinned_alloc_bytes": 16, "read_pagein_wall_ms": 1.0, "cpu_staging_wall_ms": 1.0,
                 "h2d_host_issue_wall_ms": 1.0, "reuse_wait_total_ms": 0.5, "max_reuse_wait_ms": 0.5},
                None, [])
    return _side


class TestRingPipeline(unittest.TestCase):
    def _base_derived(self):
        return (_RingZImage(), _pipeline_meta_sd(), dict(_RING_HEADER), 24, "model.diffusion_model.")

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA required")
    def test_pipeline_success_returns_patcher(self):
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            with _ring_pipeline_env(ring_run_side_effect=_default_ring_run_side_effect(bind=True),
                                    derived=self._base_derived()):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is not None
        assert isinstance(result, tuple) and len(result) == 1
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert len(evs) == 1
        assert evs[0].metadata["status"] == "ok"
        assert evs[0].metadata["family"] == "ZImage"
        json.dumps(evs[0].to_dict())

    def test_pipeline_fallback_on_ring_run_failure(self):
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            with _ring_pipeline_env(ring_run_side_effect=lambda *a, **k: None,
                                    derived=self._base_derived()):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert len(evs) == 1
        assert evs[0].metadata["status"] == "fallback"
        assert evs[0].metadata["reason"] == "stage:ring_run"
        assert evs[0].metadata["fallback_count"] == 1

    def test_pipeline_ring_failure_detail(self):
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            with _ring_pipeline_env(ring_run_side_effect=lambda *a, **k: (None, "stage_copy:RuntimeError"),
                                    derived=self._base_derived()):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert evs[0].metadata["status"] == "fallback"
        assert evs[0].metadata["reason"] == "stage:ring_run:stage_copy:RuntimeError"

    def test_pipeline_fallback_no_bind(self):
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            with _ring_pipeline_env(ring_run_side_effect=_default_ring_run_side_effect(bind=False),
                                    derived=self._base_derived()):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert evs[0].metadata["status"] == "fallback"
        assert evs[0].metadata["reason"] == "stage:ring_bind_incomplete"

    def test_pipeline_get_model_failure(self):
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            def _boom_get_model(sd, prefix):
                raise RuntimeError("get_model boom")
            _cfg = _RingZImage()
            _cfg.get_model = _boom_get_model
            derived = (_cfg, _pipeline_meta_sd(), dict(_RING_HEADER), 24, "model.diffusion_model.")
            with _ring_pipeline_env(derived=derived):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert evs[0].metadata["reason"] == "stage:RuntimeError"

    def test_pipeline_key_mismatch_failure(self):
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            def _rename_transform(sd):
                return {"renamed." + k: v for k, v in sd.items()}
            _cfg = _RingZImage()
            _cfg.process_unet_state_dict = _rename_transform
            derived = (_cfg, _pipeline_meta_sd(), dict(_RING_HEADER), 24, "model.diffusion_model.")
            with _ring_pipeline_env(derived=derived):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert evs[0].metadata["reason"] == "stage:transform_not_independent"

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA required")
    def test_prefix_submodule_key_map(self):
        # regression: the authoritative bind loads into the diffusion_model
        # submodule with UNPREFIXED keys; top-level prefixed names must NOT
        # be used for the key gate (previously guaranteed key_param_mismatch)
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            _unet = _unet_module_with_names({"layers.0.weight": (4, 4)})
            _model = torch.nn.Module()
            _model.diffusion_model = _unet

            def _gm(sd, prefix):
                return _model

            _cfg = _RingZImage()
            _cfg.get_model = _gm
            meta_sd = {"layers.0.weight": torch.empty((4, 4), dtype=torch.bfloat16, device="meta")}
            derived = (_cfg, meta_sd, dict(_RING_HEADER), 24, "model.diffusion_model.")
            with _ring_pipeline_env(ring_run_side_effect=_default_ring_run_side_effect(bind=True),
                                    derived=derived):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is not None, "diffusion-submodule key map must resolve unprefixed names"
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert evs[0].metadata["status"] == "ok"
        assert evs[0].metadata["param_count"] == 1

    def test_subset_gate_unmapped_key(self):
        # an sd key with no destination param/buffer fails closed and is
        # recorded for diagnosis (strict=False mirror: model-only keys allowed)
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            _unet = _unet_module_with_names({"layers.0.weight": (4, 4)})
            _model = torch.nn.Module()
            _model.diffusion_model = _unet

            def _gm(sd, prefix):
                return _model

            _cfg = _RingZImage()
            _cfg.get_model = _gm
            meta_sd = {
                "layers.0.weight": torch.empty((4, 4), dtype=torch.bfloat16, device="meta"),
                "ghost.key": torch.empty((2,), dtype=torch.bfloat16, device="meta"),
            }
            derived = (_cfg, meta_sd, dict(_RING_HEADER), 24, "model.diffusion_model.")
            with _ring_pipeline_env(ring_run_side_effect=_default_ring_run_side_effect(bind=True),
                                    derived=derived):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert evs[0].metadata["status"] == "fallback"
        assert evs[0].metadata["reason"] == "stage:key_param_mismatch"
        assert list(evs[0].metadata["sd_unmapped_keys"]) == ["ghost.key"]

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA required")
    def test_subset_gate_model_only_param_allowed(self):
        # a model-only param (not in the sd) passes the gate (strict=False
        # parity) and is counted; it is moved by the final model.to
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            _unet = _unet_module_with_names({"layers.0.weight": (4, 4), "extra.bias": (4,)})
            _model = torch.nn.Module()
            _model.diffusion_model = _unet

            def _gm(sd, prefix):
                return _model

            _cfg = _RingZImage()
            _cfg.get_model = _gm
            meta_sd = {"layers.0.weight": torch.empty((4, 4), dtype=torch.bfloat16, device="meta")}
            derived = (_cfg, meta_sd, dict(_RING_HEADER), 24, "model.diffusion_model.")
            with _ring_pipeline_env(ring_run_side_effect=_default_ring_run_side_effect(bind=True),
                                    derived=derived):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is not None
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert evs[0].metadata["status"] == "ok"
        assert evs[0].metadata["model_only_param_count"] == 1

    def test_pipeline_ineligible_emits_ineligible(self):
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            with _ring_pipeline_env(eligible=(False, "family_not_zimage"), derived=self._base_derived()):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert len(evs) == 1
        assert evs[0].metadata["status"] == "ineligible"
        assert evs[0].metadata["reason"] == "family_not_zimage"

    def test_pipeline_path_unresolved(self):
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            with _ring_pipeline_env(resolved_path=None, derived=self._base_derived()):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert evs[0].metadata["reason"] == "stage:path_unresolved"

    def test_pipeline_resolver_path_proceeds_past_s1(self):
        # path resolves -> the pipeline proceeds past S1 (reason is the
        # mocked eligibility rejection, NOT stage:path_unresolved)
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            with _ring_pipeline_env(eligible=(False, "family_not_zimage"),
                                    derived=self._base_derived()):
                result = mp._ring_try_pipeline(
                    None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert len(evs) == 1
        assert evs[0].metadata["reason"] == "family_not_zimage"

    def test_pipeline_resolver_none_falls_back_exactly_once(self):
        trace = RuntimeTrace(request_id="ring-pipeline", process="remote")
        _tok = mp._ACTIVE_REQUEST_TRACE.set(trace)
        try:
            with _ring_pipeline_env(resolved_path=None, derived=self._base_derived()):
                with mock.patch.object(mp, "_ring_derive_config") as derive_spy:
                    result = mp._ring_try_pipeline(
                        None, None, {"unet_name": "z.safetensors", "weight_dtype": "default"}, None)
        finally:
            mp._ACTIVE_REQUEST_TRACE.reset(_tok)
        assert result is None
        derive_spy.assert_not_called()  # no work done after path resolution failed
        evs = [e for e in trace.events if e.name == "unet_pinned_ring_pipeline"]
        assert evs[0].metadata["status"] == "fallback"
        assert evs[0].metadata["reason"] == "stage:path_unresolved"
        assert evs[0].metadata["fallback_count"] == 1


class TestRingLoadUnetIntegration(unittest.TestCase):
    def _run_load(self, ring_result):
        bridge = _RingBridge()
        model_key = SimpleNamespace(unet_identity="z.safetensors")
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_UNET_PINNED_RING": "1"}, clear=True), \
             mock.patch.object(mp, "_ring_pipeline_enabled", return_value=True), \
             mock.patch.object(mp, "_ring_try_pipeline", return_value=ring_result), \
             _load_unet_deps():
            result = mp.V2LoaderBridge._load_unet(bridge, model_key)
        return result, bridge

    def test_pipeline_patcher_flows_through_tail(self):
        patcher = SimpleNamespace(routed=True)
        result, bridge = self._run_load((patcher,))
        assert result is patcher
        assert bridge.invoke_calls == []  # _invoke_original NOT called

    def test_pipeline_none_falls_back_to_invoke_original(self):
        result, bridge = self._run_load(None)
        assert result.ok is True
        assert len(bridge.invoke_calls) == 1
        assert bridge.invoke_calls[0][0] == "UNETLoader"


if __name__ == "__main__":
    unittest.main()
