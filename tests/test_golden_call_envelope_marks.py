"""The Golden call-envelope marks must bracket Modal's whole method call.

Modal's UI "Execution time" covers the entire method call, but every Golden mark
starts at ``golden_call_start_mono_ns`` (stamped just before ``execute_golden``)
and ends at ``return_armed``. The interval between those two boundaries was
therefore unattributed by construction: pre-Golden adapter work, result
construction, the wire handoff of the inline base64 PNG, and the post-stream
minimal release all fell outside the Golden telemetry.

These tests pin that the marks are taken at the right boundaries and that the
emitted deltas are monotonic, so the gap can be attributed instead of guessed.

They import ``golden_envelope`` rather than ``modal_app``: the logic under test
is an ordered dict of integers and a print, so paying a ~3s torch/ComfyUI import
to assert boundary ordering was measuring the import, not the behavior.
"""

from __future__ import annotations

import pytest

from comfymodal_runtime import golden_envelope as env

pytestmark = pytest.mark.fast_unit


def test_envelope_marks_are_ordered_and_delta_is_monotonic(capsys):
    env.ENVELOPE.clear()
    env.emit_envelope("no-such-request")  # must be a safe no-op
    assert capsys.readouterr().out == ""

    # Simulate a real envelope with deliberately out-of-order insertion to
    # prove the emitter sorts by the declared boundary order, not dict order.
    base = 1_000_000_000
    env.record(
        "req-1",
        {
            "method_entry_mono_ns": base,
            "golden_call_start_mono_ns": base + 80_000_000,
            "golden_return_mono_ns": base + 8_456_000_000,
            "yield_mono_ns": base + 8_476_000_000,
            "stream_drained_mono_ns": base + 9_756_000_000,
            "release_start_mono_ns": base + 9_757_000_000,
            "release_end_mono_ns": base + 9_787_000_000,
        },
    )
    env.emit_envelope("req-1")
    out = capsys.readouterr().out.strip()

    assert out.startswith("[v2.golden.envelope] request_id=req-1")
    # Every declared boundary is present, in the declared order.
    positions = [out.index(k) for k in env.ENVELOPE_ORDER]
    assert positions == sorted(positions), "marks emitted out of boundary order"
    # Deltas are milliseconds from method entry and must be non-decreasing.
    deltas = [
        float(part.split("delta_ms=")[1])
        for part in out.split()
        if "delta_ms=" in part
    ]
    assert len(deltas) == len(env.ENVELOPE_ORDER)
    assert deltas == sorted(deltas), "delta_ms not monotonic: %r" % (deltas,)
    # The envelope is popped so a long-lived container cannot accumulate it.
    assert "req-1" not in env.ENVELOPE


def test_envelope_emits_partial_marks_without_inventing_them(capsys):
    """A missing boundary is omitted; it is never fabricated as zero."""
    env.ENVELOPE.clear()
    env.record(
        "req-2",
        {
            "method_entry_mono_ns": 5_000_000_000,
            "golden_call_start_mono_ns": 5_001_000_000,
        },
    )
    env.emit_envelope("req-2")
    out = capsys.readouterr().out
    assert "golden_return_mono_ns" not in out
    assert "release_end_mono_ns" not in out
    assert "delta_ms=1.000" in out


def test_envelope_table_is_bounded():
    """The mark table must not grow without bound in a long-lived container."""
    env.ENVELOPE.clear()
    for i in range(env.ENVELOPE_MAX + 25):
        env.record("req-%d" % i, {"method_entry_mono_ns": i})
    assert len(env.ENVELOPE) <= env.ENVELOPE_MAX
    env.ENVELOPE.clear()


def test_emitted_identity_is_the_import_time_value_not_a_request_time_hash(capsys):
    """The emitted sha must come from the import-time freeze.

    Reading ``__file__`` during the request would report whatever is mounted at
    that moment, which diverges from the executing code after a memory-snapshot
    restore. The emitter must instead report the value frozen at import.

    ``modal_app`` is deliberately not imported here: this file stays inside
    FAST_UNIT precisely because it avoids the torch/ComfyUI import tree. The
    registry entry is seeded directly, which is exactly the state the freeze
    would have produced at modal_app import time.
    """
    from comfymodal_runtime import source_identity as si

    frozen = "a" * 64
    si.IMPORTED_SOURCE_SHA256["comfymodal_runtime.modal_app"] = frozen
    try:
        env.ENVELOPE.clear()
        env.record("req-identity", {"method_entry_mono_ns": 1_000})
        env.emit_envelope("req-identity")
        out = capsys.readouterr().out
    finally:
        si.IMPORTED_SOURCE_SHA256.pop("comfymodal_runtime.modal_app", None)

    assert "executed_source_sha256=%s" % frozen in out
    # No filesystem hash happens on this path at all.
    assert len(frozen) == 64


def test_emitted_identity_survives_a_newer_mounted_file(capsys):
    """A stale snapshot must keep reporting its own older identity."""
    from comfymodal_runtime import source_identity as si

    # The interpreter keeps the identity captured in its snapshot even when the
    # deployment it is nominally serving has moved on. Nothing re-hashes the
    # mounted file, so the old value is what gets reported and the caller can
    # reject the mismatch.
    si.IMPORTED_SOURCE_SHA256["comfymodal_runtime.modal_app"] = "f" * 64
    try:
        env.ENVELOPE.clear()
        env.record("req-stale", {"method_entry_mono_ns": 1_000})
        env.emit_envelope("req-stale")
        out = capsys.readouterr().out
    finally:
        si.IMPORTED_SOURCE_SHA256.pop("comfymodal_runtime.modal_app", None)

    assert "executed_source_sha256=%s" % ("f" * 64) in out