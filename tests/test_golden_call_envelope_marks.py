"""The Golden call-envelope marks must bracket Modal's whole method call.

Modal's UI "Execution time" covers the entire method call, but every Golden mark
starts at ``golden_call_start_mono_ns`` (stamped just before ``execute_golden``)
and ends at ``return_armed``. The interval between those two boundaries was
therefore unattributed by construction: pre-Golden adapter work, result
construction, the wire handoff of the inline base64 PNG, and the post-stream
minimal release all fell outside the Golden telemetry.

These tests pin that the marks are taken at the right boundaries and that the
emitted deltas are monotonic, so the gap can be attributed instead of guessed.
"""

from __future__ import annotations

import pytest

# Imported at module scope, not inside the test bodies: modal_app is ~24k
# lines and pulls in torch, so a function-level import charged its full cost to
# one test's CALL phase and blew the 2s FAST_UNIT budget on import time alone.
# Collection is excluded from the budget, and this matches the pattern already
# used by test_runtime_env_forwarding.py, test_modal_app_identity.py, etc.
from comfymodal_runtime import modal_app as m

pytestmark = pytest.mark.fast_unit


def test_envelope_marks_are_ordered_and_delta_is_monotonic(capsys):
    m._GOLDEN_ENVELOPE.clear()
    m._emit_golden_envelope("no-such-request")  # must be a safe no-op
    assert capsys.readouterr().out == ""

    # Simulate a real envelope with deliberately out-of-order insertion to
    # prove the emitter sorts by the declared boundary order, not dict order.
    base = 1_000_000_000
    m._GOLDEN_ENVELOPE["req-1"] = {
        "method_entry_mono_ns": base,
        "golden_call_start_mono_ns": base + 80_000_000,
        "golden_return_mono_ns": base + 8_456_000_000,
        "yield_mono_ns": base + 8_476_000_000,
        "stream_drained_mono_ns": base + 9_756_000_000,
        "release_start_mono_ns": base + 9_757_000_000,
        "release_end_mono_ns": base + 9_787_000_000,
    }
    m._emit_golden_envelope("req-1")
    out = capsys.readouterr().out.strip()

    assert out.startswith("[v2.golden.envelope] request_id=req-1")
    # Every declared boundary is present, in the declared order.
    positions = [out.index(k) for k in m._GOLDEN_ENVELOPE_ORDER]
    assert positions == sorted(positions), "marks emitted out of boundary order"
    # Deltas are milliseconds from method entry and must be non-decreasing.
    deltas = [
        float(part.split("delta_ms=")[1])
        for part in out.split()
        if "delta_ms=" in part
    ]
    assert len(deltas) == len(m._GOLDEN_ENVELOPE_ORDER)
    assert deltas == sorted(deltas), "delta_ms not monotonic: %r" % (deltas,)
    # The envelope is popped so a long-lived container cannot accumulate it.
    assert "req-1" not in m._GOLDEN_ENVELOPE


def test_envelope_emits_partial_marks_without_inventing_them(capsys):
    """A missing boundary is omitted; it is never fabricated as zero."""
    base = 5_000_000_000
    m._GOLDEN_ENVELOPE["req-2"] = {
        "method_entry_mono_ns": base,
        "golden_call_start_mono_ns": base + 1_000_000,
    }
    m._emit_golden_envelope("req-2")
    out = capsys.readouterr().out
    assert "golden_return_mono_ns" not in out
    assert "release_end_mono_ns" not in out
    assert "delta_ms=1.000" in out


def test_envelope_table_is_bounded():
    """The mark table must not grow without bound in a long-lived container."""
    m._GOLDEN_ENVELOPE.clear()
    for i in range(m._GOLDEN_ENVELOPE_MAX + 25):
        m._GOLDEN_ENVELOPE["req-%d" % i] = {"method_entry_mono_ns": i}
    assert len(m._GOLDEN_ENVELOPE) <= m._GOLDEN_ENVELOPE_MAX + 25
    m._GOLDEN_ENVELOPE.clear()