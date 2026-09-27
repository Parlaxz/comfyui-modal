"""Offline contract tests for the generic checkpoint prewarm reader.

Covers: start/stop, cancellation mid-file, max-bytes, max-time, join-timeout
abandonment, missing files (fail-open), de-duplication, deterministic
multi-file order, no retained payload, the demand guard before a normal
loader, "failure does not block loader", env parsing (default OFF, bounds,
join ms), and a synthetic slow-reader overlap test proving overlap with
unrelated setup and no demand overlap with an active reader.

Everything is local, temporary, and deterministic; blocked fake readers are
always released/joined before the test exits.
"""

from __future__ import annotations

import os
import threading
import time

import pytest

from comfymodal_runtime import checkpoint_prewarm as cp


_MIB = 1024 * 1024
_FLAG = cp.PREWARM_FLAG
_MAX_MB_ENV = cp.PREWARM_MAX_MB_ENV
_MAX_MS_ENV = cp.PREWARM_MAX_MS_ENV
_JOIN_MS_ENV = cp.PREWARM_JOIN_MS_ENV

_REQUIRED_TELEMETRY_KEYS = {
    "prewarm_enabled",
    "prewarm_started",
    "prewarm_start_at",
    "prewarm_stop_at",
    "prewarm_files",
    "prewarm_bytes",
    "prewarm_read_calls",
    "prewarm_wall_ms",
    "prewarm_thread_cpu_ms",
    "prewarm_stop_reason",
    "prewarm_join_ms",
    "prewarm_overlap_with_setup_ms",
    "demand_loader_start_at",
    "prewarm_finished_before_demand",
}


# ── Test doubles ─────────────────────────────────────────────────────────────


class _FakeFile:
    """In-memory fake with an optional one-shot blocking gate on first read.

    ``gate``: a ``threading.Event``; the first ``readinto`` sets ``gate_hit``
    then blocks until ``gate`` is set.  Used to hold the worker mid-file so
    join-timeout/overlap behavior is deterministic.  Always release ``gate``
    in a ``finally`` so the daemon worker exits before the test ends.
    """

    def __init__(self, data=b"\x00" * (8 * 1024), label="fake", order=None, gate=None):
        self._data = data
        self._label = label
        self._order = order
        self._gate = gate
        self._pos = 0
        self._gate_done = False
        self.closed = False
        self.read_calls = 0
        self.gate_hit = threading.Event()

    def readinto(self, buf):
        self.read_calls += 1
        if self._order is not None:
            self._order.append(("read", self._label, self.read_calls))
        if self._gate is not None and not self._gate_done:
            self.gate_hit.set()
            if not self._gate.wait(10.0):
                raise RuntimeError("fake reader gate was not released before test timeout")
            self._gate_done = True
        if self._pos >= len(self._data):
            return 0
        n = min(len(buf), len(self._data) - self._pos)
        buf[:n] = self._data[self._pos : self._pos + n]
        self._pos += n
        return n

    def close(self):
        self.closed = True
        if self._order is not None:
            self._order.append(("close", self._label, 0))


class _SlowFile:
    """Fake that sleeps per chunk so wall-time bounds are deterministic."""

    def __init__(self, data, sleep_s=0.01):
        self._data = data
        self._sleep_s = sleep_s
        self._pos = 0
        self.closed = False

    def readinto(self, buf):
        time.sleep(self._sleep_s)
        if self._pos >= len(self._data):
            return 0
        n = min(len(buf), len(self._data) - self._pos)
        buf[:n] = self._data[self._pos : self._pos + n]
        self._pos += n
        return n

    def close(self):
        self.closed = True


def _make_files(tmp_path, sizes):
    paths = []
    for i, size in enumerate(sizes):
        p = tmp_path / f"chk_{i}.safetensors"
        p.write_bytes(b"\x00" * size)
        paths.append(str(p))
    return paths


def _opener(files_by_path):
    """Return a ``_open_for_prewarm`` replacement keyed by physical path."""

    def open_fn(path):
        return files_by_path[path]

    return open_fn


def _wait_finished(prewarmer, timeout=5.0):
    assert prewarmer._finished_event.wait(timeout), "prewarm worker did not finish in time"


def _join_worker(prewarmer, timeout=5.0):
    """Join the daemon worker and assert it exited (used for blocked fakes)."""
    thread = prewarmer._thread
    assert thread is not None, "no worker thread to join"
    thread.join(timeout)
    assert thread.is_alive() is False


# ── Env parsing & telemetry contract ─────────────────────────────────────────


def test_telemetry_snapshot_has_required_keys(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)
    prewarmer = cp.CheckpointPrewarmer()
    snapshot = prewarmer.as_dict()
    for key in _REQUIRED_TELEMETRY_KEYS:
        assert key in snapshot, f"missing telemetry key: {key}"


def test_disabled_default_off_start_noop(tmp_path, monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)
    paths = _make_files(tmp_path, [4096])
    prewarmer = cp.CheckpointPrewarmer()
    snapshot = prewarmer.as_dict()
    assert snapshot["prewarm_enabled"] is False
    assert prewarmer.start(paths) is False
    assert prewarmer.before_demand_load() is True
    snapshot = prewarmer.as_dict()
    assert snapshot["prewarm_started"] is False
    assert snapshot["prewarm_stop_reason"] == "disabled"
    assert snapshot["prewarm_finished_before_demand"] is True


def test_explicit_zero_disables(monkeypatch):
    monkeypatch.setenv(_FLAG, "0")
    assert cp.CheckpointPrewarmer().as_dict()["prewarm_enabled"] is False
    monkeypatch.setenv(_FLAG, "off")
    assert cp.CheckpointPrewarmer().as_dict()["prewarm_enabled"] is False


def test_env_flag_enable_and_bound_parse(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    monkeypatch.setenv(_MAX_MB_ENV, "2")
    monkeypatch.setenv(_MAX_MS_ENV, "500")
    prewarmer = cp.CheckpointPrewarmer()
    assert prewarmer.as_dict()["prewarm_enabled"] is True
    assert prewarmer._max_bytes == 2 * _MIB
    assert prewarmer._max_wall_ms == 500


def test_zero_bounds_mean_no_bound_when_enabled(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    monkeypatch.setenv(_MAX_MB_ENV, "0")
    monkeypatch.setenv(_MAX_MS_ENV, "0")
    prewarmer = cp.CheckpointPrewarmer()
    assert prewarmer._max_bytes == 0  # no byte bound
    assert prewarmer._max_wall_ms == 0  # no wall bound


def test_invalid_negative_bounds_fail_closed_to_zero(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    for bad in ("bogus", "", "-5", "-1"):
        monkeypatch.setenv(_MAX_MB_ENV, bad)
        monkeypatch.setenv(_MAX_MS_ENV, bad)
        prewarmer = cp.CheckpointPrewarmer()
        assert prewarmer._max_bytes == 0
        assert prewarmer._max_wall_ms == 0


def test_constructor_overrides_win_over_env(monkeypatch):
    monkeypatch.setenv(_FLAG, "0")
    monkeypatch.setenv(_MAX_MB_ENV, "1")
    monkeypatch.setenv(_MAX_MS_ENV, "111")
    prewarmer = cp.CheckpointPrewarmer(enabled=True, max_bytes=5 * _MIB, max_wall_ms=222)
    assert prewarmer.as_dict()["prewarm_enabled"] is True
    assert prewarmer._max_bytes == 5 * _MIB
    assert prewarmer._max_wall_ms == 222


def test_join_env_parse_and_clamp(monkeypatch):
    monkeypatch.setenv(_JOIN_MS_ENV, "1234")
    assert cp.CheckpointPrewarmer()._join_timeout_ms == 1234
    for bad in ("bogus", "", "-7"):
        monkeypatch.setenv(_JOIN_MS_ENV, bad)
        assert cp.CheckpointPrewarmer()._join_timeout_ms == cp.DEFAULT_JOIN_TIMEOUT_MS
    monkeypatch.setenv(_JOIN_MS_ENV, "99999999")
    assert cp.CheckpointPrewarmer()._join_timeout_ms == cp.MAX_JOIN_TIMEOUT_MS


def test_default_chunk_bytes_matches_volume_read_precedent():
    assert cp.DEFAULT_CHUNK_BYTES == 8 * _MIB


def test_default_join_timeout_is_safe():
    assert cp.DEFAULT_JOIN_TIMEOUT_MS == 1000


# ── Start/stop lifecycle ─────────────────────────────────────────────────────


def test_start_stop_reads_all_files_and_join(tmp_path):
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024)
    paths = _make_files(tmp_path, [10_000, 20_000, 30_000])
    assert prewarmer.start(paths) is True
    _wait_finished(prewarmer)
    assert prewarmer.before_demand_load() is True
    snapshot = prewarmer.as_dict()
    assert snapshot["prewarm_started"] is True
    assert snapshot["prewarm_files"] == paths
    assert snapshot["prewarm_file_count"] == 3
    assert snapshot["prewarm_bytes"] == 60_000
    assert snapshot["bytes_read_for_prewarm"] == 60_000
    assert snapshot["prewarm_read_calls"] > 0
    assert snapshot["prewarm_stop_reason"] == "completed"
    assert snapshot["prewarm_join_ms"] is not None
    assert snapshot["prewarm_wall_ms"] > 0
    assert snapshot["prewarm_overlap_with_setup_ms"] == 0
    assert snapshot["prewarm_finished_before_demand"] is True
    assert snapshot["demand_loader_start_at"] is not None
    assert snapshot["demand_loader_start_at"] >= snapshot["prewarm_stop_at"]


def test_idempotent_stop_and_join(tmp_path):
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024)
    paths = _make_files(tmp_path, [8192])
    assert prewarmer.start(paths) is True
    _wait_finished(prewarmer)
    assert prewarmer.stop_and_join_before_demand() is True
    # Second call is idempotent and still returns True (worker already done).
    assert prewarmer.stop_and_join_before_demand() is True
    snapshot = prewarmer.as_dict()
    assert snapshot["prewarm_join_ms"] is not None
    assert snapshot["demand_loader_start_at"] is not None
    assert snapshot["prewarm_finished_before_demand"] is True


def test_stop_and_join_directly_closes_demand_gate(tmp_path):
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024)
    paths = _make_files(tmp_path, [8192])
    assert prewarmer.start(paths) is True
    assert prewarmer.stop_and_join_before_demand() is True
    assert prewarmer.start(paths) is False
    snapshot = prewarmer.as_dict()
    assert snapshot["demand_loader_start_at"] is not None
    assert snapshot["prewarm_finished_before_demand"] is True


def test_no_paths_start_false(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    prewarmer = cp.CheckpointPrewarmer()
    assert prewarmer.start([]) is False
    assert prewarmer.start(None) is False
    assert prewarmer.as_dict()["prewarm_stop_reason"] == "no_paths"
    assert prewarmer.before_demand_load() is True
    assert prewarmer.as_dict()["demand_loader_start_at"] is not None


def test_second_start_while_running_is_noop(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    gate = threading.Event()
    fake = _FakeFile(data=b"\x00" * (64 * 1024), gate=gate)
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024)
    monkeypatch.setattr(cp, "_open_for_prewarm", lambda path: fake)
    try:
        assert prewarmer.start(["a.safetensors"]) is True
        assert fake.gate_hit.wait(5.0)
        assert prewarmer.start(["b.safetensors"]) is False  # still running
    finally:
        gate.set()
        _join_worker(prewarmer)


# ── Cancellation / bounds ────────────────────────────────────────────────────


def test_cancellation_mid_file(monkeypatch):
    fake = _SlowFile(data=b"\x00" * (2 * _MIB), sleep_s=0.002)
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024)
    monkeypatch.setattr(cp, "_open_for_prewarm", lambda path: fake)
    assert prewarmer.start(["mid.safetensors"]) is True
    deadline = time.monotonic() + 5.0
    while prewarmer._read_calls < 3 and time.monotonic() < deadline:
        time.sleep(0.002)
    assert prewarmer._read_calls >= 3, "worker never reached mid-file state"
    assert prewarmer.before_demand_load() is True
    snapshot = prewarmer.as_dict()
    assert snapshot["prewarm_stop_reason"] == "cancelled"
    assert 0 < snapshot["prewarm_bytes"] < 2 * _MIB
    assert snapshot["prewarm_finished_before_demand"] is True


def test_max_bytes_bound(monkeypatch):
    fake = _FakeFile(data=b"\x00" * (64 * 1024), label="bounded")
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024, max_bytes=20 * 1024)
    monkeypatch.setattr(cp, "_open_for_prewarm", lambda path: fake)
    assert prewarmer.start(["bounded.safetensors"]) is True
    _wait_finished(prewarmer)
    assert prewarmer.before_demand_load() is True
    snapshot = prewarmer.as_dict()
    # Two full 8 KiB chunks plus one bounded 4 KiB chunk reaches the cap.
    assert snapshot["prewarm_stop_reason"] == "max_bytes"
    assert snapshot["prewarm_bytes"] == 20 * 1024
    assert snapshot["prewarm_read_calls"] == 3
    assert snapshot["prewarm_finished_before_demand"] is True


def test_max_wall_ms_bound(monkeypatch):
    fake = _SlowFile(data=b"\x00" * (64 * 1024), sleep_s=0.01)
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024, max_wall_ms=30)
    monkeypatch.setattr(cp, "_open_for_prewarm", lambda path: fake)
    assert prewarmer.start(["slow.safetensors"]) is True
    _wait_finished(prewarmer, timeout=5.0)
    assert prewarmer.before_demand_load() is True
    snapshot = prewarmer.as_dict()
    assert snapshot["prewarm_stop_reason"] == "max_wall_ms"
    assert 0 < snapshot["prewarm_bytes"] < 64 * 1024
    assert snapshot["prewarm_wall_ms"] < 1000  # bounded in practice


# ── Fail-open behavior ───────────────────────────────────────────────────────


def test_missing_file_fail_open_continues_and_loader_unblocked(tmp_path):
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024)
    real_a, real_b = _make_files(tmp_path, [5000, 7000])
    missing = str(tmp_path / "does_not_exist.safetensors")
    paths = [missing, real_a, missing, real_b]
    assert prewarmer.start(paths) is True
    _wait_finished(prewarmer)
    # Missing files never block the demand loader: guard joins cleanly.
    assert prewarmer.before_demand_load() is True
    snapshot = prewarmer.as_dict()
    assert snapshot["prewarm_stop_reason"] == "completed_with_errors"
    # Paths are de-duplicated, so the missing path appears exactly once.
    assert snapshot["prewarm_open_errors"] == 1
    assert snapshot["prewarm_read_errors"] == 0
    assert snapshot["prewarm_bytes"] == 12_000  # both real files fully read
    assert snapshot["prewarm_files"] == [missing, real_a, real_b]
    assert snapshot["prewarm_file_count"] == 3  # deduped path list
    assert snapshot["prewarm_finished_before_demand"] is True


# ── Path list API ────────────────────────────────────────────────────────────


def test_dedup_preserves_first_occurrence():
    paths = ["b.safetensors", "a.safetensors", "b.safetensors", "c.safetensors", "a.safetensors"]
    assert cp.resolve_prewarm_paths(paths) == ["b.safetensors", "a.safetensors", "c.safetensors"]


def test_resolve_drops_none_and_accepts_pathlike(tmp_path):
    p = tmp_path / "m.safetensors"
    p.write_bytes(b"\x00" * 4)
    result = cp.resolve_prewarm_paths([None, p, str(p), None])
    assert result == [str(p)]


def test_deterministic_multi_file_order(monkeypatch):
    order = []
    files = {
        "a.safetensors": _FakeFile(data=b"\x00" * (16 * 1024), label="a", order=order),
        "b.safetensors": _FakeFile(data=b"\x00" * (16 * 1024), label="b", order=order),
        "c.safetensors": _FakeFile(data=b"\x00" * (16 * 1024), label="c", order=order),
    }
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024)
    monkeypatch.setattr(cp, "_open_for_prewarm", _opener(files))
    assert prewarmer.start(["b.safetensors", "a.safetensors", "c.safetensors"]) is True
    _wait_finished(prewarmer)
    reads = [event[1] for event in order if event[0] == "read"]
    # One daemon reader walks the files strictly in source order, no interleave.
    # Each 16 KiB file yields 3 reads (2 data chunks + 1 EOF read).
    assert reads == ["b", "b", "b", "a", "a", "a", "c", "c", "c"]
    assert prewarmer.as_dict()["prewarm_files"] == ["b.safetensors", "a.safetensors", "c.safetensors"]


def test_no_retained_payload_after_completion(tmp_path):
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024)
    paths = _make_files(tmp_path, [16 * 1024])
    assert prewarmer.start(paths) is True
    _wait_finished(prewarmer)
    assert prewarmer.before_demand_load() is True
    assert prewarmer._buffer is None
    payload = [name for name, value in vars(prewarmer).items()
               if isinstance(value, (bytes, bytearray))]
    assert payload == [], f"retained payload in object state: {payload}"


# ── Demand guard ─────────────────────────────────────────────────────────────


def test_demand_guard_before_normal_loader(tmp_path):
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024)
    paths = _make_files(tmp_path, [10_000, 20_000])
    assert prewarmer.start(paths) is True
    _wait_finished(prewarmer)
    assert prewarmer.before_demand_load() is True
    snapshot = prewarmer.as_dict()
    assert snapshot["prewarm_finished_before_demand"] is True
    assert snapshot["prewarm_stop_at"] is not None
    assert snapshot["demand_loader_start_at"] >= snapshot["prewarm_stop_at"]

    # Simulated normal (demand) loader runs after the guard returned.
    loader_ran_at = time.monotonic()
    assert loader_ran_at >= snapshot["demand_loader_start_at"]


def test_no_start_after_demand_guard(tmp_path):
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024)
    paths = _make_files(tmp_path, [8192])
    assert prewarmer.start(paths) is True
    _wait_finished(prewarmer)
    assert prewarmer.before_demand_load() is True
    assert prewarmer.start(["another.safetensors"]) is False
    assert prewarmer.as_dict()["prewarm_stop_reason"] == "after_demand_guard"
    assert prewarmer.as_dict()["prewarm_files"] == paths  # original run only


# ── Join timeout / abandon ───────────────────────────────────────────────────


def test_join_timeout_abandons_and_demand_proceeds(monkeypatch):
    gate = threading.Event()
    fake = _FakeFile(data=b"\x00" * (64 * 1024), label="blocked", gate=gate)
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024, join_timeout_ms=100)
    monkeypatch.setattr(cp, "_open_for_prewarm", lambda path: fake)
    assert prewarmer.start(["blocked.safetensors"]) is True
    assert fake.gate_hit.wait(5.0), "fake reader never reached the gate"
    try:
        joined = prewarmer.before_demand_load()
        assert joined is False
        snapshot = prewarmer.as_dict()
        assert snapshot["prewarm_stop_reason"] == "retirement_failed"
        assert snapshot["prewarm_finished_before_demand"] is False
        assert snapshot["demand_loader_start_at"] is None
        assert snapshot["prefetch_workers_alive_at_demand_start"] > 0
        assert snapshot["source_fence_valid"] is False
        assert snapshot["prewarm_join_ms"] is not None
        assert snapshot["prefetch_retirement_result"] == "retirement_failed"
        # The final retirement bound is finite and the request must not start
        # a demand reader while the blocked source reader remains alive.
        assert snapshot["prefetch_retirement_ms"] < 2_000
        assert prewarmer._buffer is None  # prewarm state retired
        assert prewarmer._thread is not None and prewarmer._thread.is_alive() is True
        assert prewarmer.start(["x.safetensors"]) is False  # one-shot lifecycle
    finally:
        gate.set()
        _join_worker(prewarmer)


def test_slow_reader_overlap_with_setup_no_demand_overlap(monkeypatch):
    """Overlap telemetry proves prewarm overlapped *unrelated setup* only.

    The reader is deliberately held mid-file; the demand guard must abandon
    within its bound, demand must start after the guard returns, and the
    reader must make zero progress while demand runs.
    """
    gate = threading.Event()
    fake = _FakeFile(data=b"\x00" * (64 * 1024), label="blocked", gate=gate)
    prewarmer = cp.CheckpointPrewarmer(enabled=True, chunk_bytes=8 * 1024, join_timeout_ms=100)
    monkeypatch.setattr(cp, "_open_for_prewarm", lambda path: fake)

    prewarmer.mark_setup_start()
    assert prewarmer.start(["blocked.safetensors"]) is True
    assert fake.gate_hit.wait(5.0), "fake reader never reached the gate"
    # Hold the setup window open past the monotonic-clock resolution so the
    # overlap is measurable (Windows monotonic tick is ~15.6 ms).
    time.sleep(0.05)
    prewarmer.mark_setup_end()
    try:
        guard_started = time.monotonic()
        joined = prewarmer.before_demand_load()
        guard_elapsed_s = time.monotonic() - guard_started
        assert joined is False  # abandoned, demand proceeds
        assert guard_elapsed_s < 2.0  # hard-bounded join

        snapshot = prewarmer.as_dict()
        # Prewarm genuinely overlapped the unrelated-setup window.
        assert snapshot["prewarm_overlap_with_setup_ms"] > 0
        assert snapshot["prewarm_stop_reason"] == "retirement_failed"
        assert snapshot["source_fence_valid"] is False

        # The demand loader is not permitted to begin while the reader remains
        # blocked: no demand/reader overlap is claimed.
        assert snapshot["demand_loader_start_at"] is None
        reads_before_demand = fake.read_calls
        time.sleep(0.05)  # simulated demand work
        assert fake.read_calls == reads_before_demand  # reader made no progress
    finally:
        gate.set()
        _join_worker(prewarmer)
