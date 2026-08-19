"""V2 capture-boundary allocator hygiene: targeted local validation.

Covers ``comfymodal_runtime.snapshot_capture_hygiene`` with monkeypatched
/proc readers and allocator helpers (no Modal, no ComfyUI graph, no real
libc ``malloc_trim``):

- Flag gate: unset / ``"0"`` -> disabled; truthy -> enabled; with the gate
  off the caller contract ("enabled -> run") means the run is never invoked
  and nothing is emitted.
- An enabled run calls ``gc.collect()`` exactly once plus a guarded
  ``malloc_trim(0)``, with before/after VmRSS/RssAnon/RssFile/VmSize/VmData
  and cgroup memory-current deltas.
- ``malloc_trim`` unavailable is the nonfatal path (result ``None``, no raise).
- Unavailable measurements stay ``None`` -- never fabricated zeros.
- ``latest_hygiene_event()`` holds the last event; exactly one compact
  ``[v2.snapshot_capture_hygiene]`` line is printed per run.
- The pass touches no model/state: gc enablement, ``sys.modules`` and
  ``os.environ`` are unchanged and the event carries no model references.
"""

from __future__ import annotations

import gc
import os
import sys
import types

from comfymodal_runtime import snapshot_capture_hygiene as hygiene


_STATUS_ALL_NONE = {
    "rss_kb": None,
    "rss_anon_kb": None,
    "rss_file_kb": None,
    "vmsize_kb": None,
    "vmdata_kb": None,
}


# ── 1. Flag off = behavior unchanged ────────────────────────────────────────


def test_flag_off_hygiene_disabled_and_nothing_emitted(monkeypatch, capsys):
    # Baseline: no event may pre-exist from a previous run.
    monkeypatch.setattr(hygiene, "_LATEST_HYGIENE", None)
    capsys.readouterr()

    monkeypatch.delenv(hygiene.HYGIENE_GATE_KEY, raising=False)
    assert hygiene.hygiene_enabled() is False
    assert hygiene.latest_hygiene_event() is None

    monkeypatch.setenv(hygiene.HYGIENE_GATE_KEY, "0")
    assert hygiene.hygiene_enabled() is False
    assert hygiene.latest_hygiene_event() is None

    # Caller contract: the module-level gate decision is hygiene_enabled().
    # With the flag off the gate never invokes run_capture_hygiene, so no
    # event exists and nothing is printed.
    out = capsys.readouterr().out
    assert not any(
        line.startswith("[v2.snapshot_capture_hygiene]") for line in out.splitlines()
    )
    assert hygiene.latest_hygiene_event() is None


# ── 2. Flag on: gc + malloc_trim with honest before/after deltas ────────────


def test_flag_on_runs_gc_once_and_records_deltas(monkeypatch):
    monkeypatch.setenv(hygiene.HYGIENE_GATE_KEY, "1")
    gc_calls: list[int] = []

    def _fake_collect() -> int:
        gc_calls.append(1)
        return 42

    # module.gc is a stub so gc.collect is the recorded fake (isolated; the
    # global gc module is untouched).
    monkeypatch.setattr(hygiene, "gc", types.SimpleNamespace(collect=_fake_collect))

    before = {"rss_kb": 1000, "rss_anon_kb": 800, "rss_file_kb": 200, "vmsize_kb": 5000, "vmdata_kb": 3000}
    after = {"rss_kb": 950, "rss_anon_kb": 780, "rss_file_kb": 200, "vmsize_kb": 5000, "vmdata_kb": 3000}
    status_values = iter([before, after])
    monkeypatch.setattr(hygiene, "read_process_status_fields", lambda: next(status_values))

    cgroup_values = iter([5_000_000, 4_900_000])
    monkeypatch.setattr(hygiene, "read_cgroup_memory_current_bytes", lambda: next(cgroup_values))

    monkeypatch.setattr(hygiene, "_malloc_trim", lambda: (True, 1))

    event = hygiene.run_capture_hygiene()

    assert len(gc_calls) == 1
    assert event["gc_collected"] == 42
    assert event["malloc_trim_available"] is True
    assert event["malloc_trim_result"] == 1
    assert event["before_rss_kb"] == 1000
    assert event["after_rss_kb"] == 950
    assert event["delta_rss_kb"] == 50
    assert event["delta_rss_anon_kb"] == 800 - 780
    assert event["delta_rss_file_kb"] == 200 - 200
    assert event["delta_vmsize_kb"] == 5000 - 5000
    assert event["delta_vmdata_kb"] == 3000 - 3000
    assert event["cgroup_memory_current_before_bytes"] == 5_000_000
    assert event["cgroup_memory_current_after_bytes"] == 4_900_000
    assert event["cgroup_memory_current_delta_bytes"] == 100_000
    assert event["hygiene_wall_ms"] >= 0.0
    assert event["enabled"] == 1
    assert event["manifest_status"] == "not_captured"


# ── 3. malloc_trim unavailable is nonfatal ─────────────────────────────────


def test_malloc_trim_unavailable_is_nonfatal(monkeypatch):
    monkeypatch.setenv(hygiene.HYGIENE_GATE_KEY, "1")
    monkeypatch.setattr(hygiene, "gc", types.SimpleNamespace(collect=lambda: 7))
    monkeypatch.setattr(hygiene, "_malloc_trim", lambda: (False, None))
    monkeypatch.setattr(
        hygiene,
        "read_process_status_fields",
        lambda: {"rss_kb": 1, "rss_anon_kb": 1, "rss_file_kb": 1, "vmsize_kb": 1, "vmdata_kb": 1},
    )
    monkeypatch.setattr(hygiene, "read_cgroup_memory_current_bytes", lambda: None)

    event = hygiene.run_capture_hygiene()  # must not raise

    assert event["malloc_trim_available"] is False
    assert event["malloc_trim_result"] is None
    assert event["gc_collected"] == 7  # gc still ran


# ── 4. Null measurements preserved honestly ─────────────────────────────────


def test_null_measurements_stay_null_honestly(monkeypatch):
    monkeypatch.setenv(hygiene.HYGIENE_GATE_KEY, "1")
    monkeypatch.setattr(hygiene, "gc", types.SimpleNamespace(collect=lambda: 0))
    null_file = {"rss_kb": 1000, "rss_anon_kb": 800, "rss_file_kb": None, "vmsize_kb": 5000, "vmdata_kb": 3000}
    monkeypatch.setattr(hygiene, "read_process_status_fields", lambda: null_file)
    monkeypatch.setattr(hygiene, "read_cgroup_memory_current_bytes", lambda: None)
    monkeypatch.setattr(hygiene, "_malloc_trim", lambda: (True, 1))

    event = hygiene.run_capture_hygiene()

    assert event["before_rss_file_kb"] is None
    assert event["after_rss_file_kb"] is None
    assert event["delta_rss_file_kb"] is None
    assert event["file_backed_measurement_status"] == "unavailable"
    assert event["anonymous_measurement_status"] == "ok"
    assert event["cgroup_memory_current_before_bytes"] is None
    assert event["cgroup_memory_current_after_bytes"] is None
    assert event["cgroup_memory_current_delta_bytes"] is None


# ── 5. No fake zeros ────────────────────────────────────────────────────────


def test_delta_for_unavailable_measurement_is_none_not_zero(monkeypatch):
    monkeypatch.setenv(hygiene.HYGIENE_GATE_KEY, "1")
    monkeypatch.setattr(hygiene, "gc", types.SimpleNamespace(collect=lambda: 0))
    null_file = {"rss_kb": 1000, "rss_anon_kb": 800, "rss_file_kb": None, "vmsize_kb": 5000, "vmdata_kb": 3000}
    monkeypatch.setattr(hygiene, "read_process_status_fields", lambda: null_file)
    monkeypatch.setattr(hygiene, "read_cgroup_memory_current_bytes", lambda: None)
    monkeypatch.setattr(hygiene, "_malloc_trim", lambda: (True, 1))

    event = hygiene.run_capture_hygiene()

    # A None before/after must yield a None delta -- never a fabricated 0.
    assert event["delta_rss_file_kb"] is None
    assert event["delta_rss_file_kb"] != 0
    assert event["cgroup_memory_current_delta_bytes"] is None
    assert event["cgroup_memory_current_delta_bytes"] != 0


def test_all_none_fixture_yields_all_none_and_unavailable(monkeypatch):
    monkeypatch.setenv(hygiene.HYGIENE_GATE_KEY, "1")
    monkeypatch.setattr(hygiene, "gc", types.SimpleNamespace(collect=lambda: 0))
    monkeypatch.setattr(hygiene, "read_process_status_fields", lambda: dict(_STATUS_ALL_NONE))
    monkeypatch.setattr(hygiene, "read_cgroup_memory_current_bytes", lambda: None)
    monkeypatch.setattr(hygiene, "_malloc_trim", lambda: (True, 1))

    event = hygiene.run_capture_hygiene()

    for key in (
        "before_rss_kb", "after_rss_kb", "delta_rss_kb",
        "before_rss_anon_kb", "after_rss_anon_kb", "delta_rss_anon_kb",
        "before_rss_file_kb", "after_rss_file_kb", "delta_rss_file_kb",
        "before_vmsize_kb", "after_vmsize_kb", "delta_vmsize_kb",
        "before_vmdata_kb", "after_vmdata_kb", "delta_vmdata_kb",
    ):
        assert event[key] is None, key
    assert event["anonymous_measurement_status"] == "unavailable"
    assert event["file_backed_measurement_status"] == "unavailable"


# ── 6. Event emitted once per run; latest replaced ──────────────────────────


def test_event_emitted_once_per_run_and_latest_replaced(monkeypatch, capsys):
    monkeypatch.setenv(hygiene.HYGIENE_GATE_KEY, "1")
    monkeypatch.setattr(hygiene, "gc", types.SimpleNamespace(collect=lambda: 3))
    monkeypatch.setattr(
        hygiene,
        "read_process_status_fields",
        lambda: {"rss_kb": 1, "rss_anon_kb": 1, "rss_file_kb": 1, "vmsize_kb": 1, "vmdata_kb": 1},
    )
    monkeypatch.setattr(hygiene, "read_cgroup_memory_current_bytes", lambda: None)
    monkeypatch.setattr(hygiene, "_malloc_trim", lambda: (False, None))

    capsys.readouterr()
    ev1 = hygiene.run_capture_hygiene()
    out1 = capsys.readouterr().out
    lines1 = [l for l in out1.splitlines() if l.startswith("[v2.snapshot_capture_hygiene]")]
    assert len(lines1) == 1

    ev2 = hygiene.run_capture_hygiene()
    out2 = capsys.readouterr().out
    lines2 = [l for l in out2.splitlines() if l.startswith("[v2.snapshot_capture_hygiene]")]
    assert len(lines2) == 1  # two runs -> two total lines

    assert hygiene.latest_hygiene_event() is ev2
    assert hygiene.latest_hygiene_event() is not ev1


# ── 7. No model/state mutation beyond allocator reclaim ─────────────────────


def test_no_model_or_state_mutation_beyond_allocator_reclaim(monkeypatch):
    monkeypatch.setenv(hygiene.HYGIENE_GATE_KEY, "1")
    # Stub malloc_trim so the real ctypes import inside it never loads a new
    # module into sys.modules during the run.
    monkeypatch.setattr(hygiene, "_malloc_trim", lambda: (False, None))
    monkeypatch.setattr(
        hygiene,
        "read_process_status_fields",
        lambda: {"rss_kb": 1, "rss_anon_kb": 1, "rss_file_kb": None, "vmsize_kb": 1, "vmdata_kb": 1},
    )
    monkeypatch.setattr(hygiene, "read_cgroup_memory_current_bytes", lambda: None)

    gc_enabled_before = gc.isenabled()
    modules_before = set(sys.modules)
    env_before = dict(os.environ)

    event = hygiene.run_capture_hygiene()

    assert gc.isenabled() == gc_enabled_before
    assert set(sys.modules) == modules_before
    assert dict(os.environ) == env_before
    assert not any("model" in key for key in event)


# ── 8. manifest_status reflects the capture flag ────────────────────────────


def test_manifest_status_reflects_capture_flag(monkeypatch):
    monkeypatch.setenv(hygiene.HYGIENE_GATE_KEY, "1")
    monkeypatch.setattr(hygiene, "gc", types.SimpleNamespace(collect=lambda: 0))
    monkeypatch.setattr(
        hygiene,
        "read_process_status_fields",
        lambda: {"rss_kb": 1, "rss_anon_kb": 1, "rss_file_kb": 1, "vmsize_kb": 1, "vmdata_kb": 1},
    )
    monkeypatch.setattr(hygiene, "read_cgroup_memory_current_bytes", lambda: None)
    monkeypatch.setattr(hygiene, "_malloc_trim", lambda: (False, None))

    captured = hygiene.run_capture_hygiene(manifest_captured=True)
    assert captured["manifest_status"] == "captured"

    not_captured = hygiene.run_capture_hygiene(manifest_captured=False)
    assert not_captured["manifest_status"] == "not_captured"


# ── 9. hygiene_wall_ms and mono stamps ──────────────────────────────────────


def test_monotonic_stamps_and_wall_ms(monkeypatch):
    monkeypatch.setenv(hygiene.HYGIENE_GATE_KEY, "1")
    monkeypatch.setattr(hygiene, "gc", types.SimpleNamespace(collect=lambda: 0))
    monkeypatch.setattr(
        hygiene,
        "read_process_status_fields",
        lambda: {"rss_kb": 1, "rss_anon_kb": 1, "rss_file_kb": 1, "vmsize_kb": 1, "vmdata_kb": 1},
    )
    monkeypatch.setattr(hygiene, "read_cgroup_memory_current_bytes", lambda: None)
    monkeypatch.setattr(hygiene, "_malloc_trim", lambda: (False, None))

    event = hygiene.run_capture_hygiene()

    assert isinstance(event["before_mono_ns"], int)
    assert isinstance(event["after_mono_ns"], int)
    assert event["after_mono_ns"] >= event["before_mono_ns"]
    assert event["hygiene_wall_ms"] >= 0.0
