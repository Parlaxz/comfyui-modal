"""Tests for C0 child VizTracer attachment into the parent trace bundle.

The C0 child process traces itself to a deterministic /tmp path when
``COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER`` is ON, but a child cannot add itself to
the parent's bundle.  Without the explicit copy in ``modal_app`` the bundle ships
parent-only, and a whole request reads as a single traced process even though the
child recorded thousands of intervals -- which is exactly the failure this module
guards.

These are ``heavy_local`` rather than ``fast_unit`` on purpose: importing
``comfymodal_runtime.modal_app`` costs about 9 seconds, because it pulls in the
Modal and Torch runtime.  Per the repository test-performance policy a test that
loads heavyweight runtime resources must not contaminate ordinary FAST_UNIT
verification, so it is marked and run explicitly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytestmark = pytest.mark.heavy_local


class _FakeSession:
    """Minimal stand-in for the trace session passed to the attach helper."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.trace_id = "t123"


@pytest.fixture(scope="module")
def modal_app():
    """Import the heavy module once, not once per test."""
    from comfymodal_runtime import modal_app as ma  # type: ignore

    return ma


def _fake_artifact(monkeypatch, artifact) -> None:
    """Point ``child_viztracer_artifact`` at *artifact* for the attach helper."""
    import comfymodal_runtime.golden_io_process_v2 as gio  # type: ignore

    monkeypatch.setattr(gio, "child_viztracer_artifact", lambda: dict(artifact))


def test_child_trace_is_copied_into_the_bundle(tmp_path, monkeypatch, modal_app):
    # The child wrote its trace to its own path; the parent must copy it into
    # raw/ or the bundle ships parent-only and the child work reads as missing.
    child_file = tmp_path / "comfymodal_c0_child_viztracer.json"
    payload = json.dumps({"traceEvents": [
        {"name": "c0_worker (a.py:1)", "ph": "X", "ts": 0, "dur": 5000,
         "pid": 48, "tid": 48, "cat": "FEE"},
    ]})
    child_file.write_text(payload, encoding="utf-8")
    (tmp_path / (child_file.name + ".status.json")).write_text(
        json.dumps({"status": "saved", "pid": 48, "tracer_entries": 1}),
        encoding="utf-8",
    )
    _fake_artifact(monkeypatch, {
        "enabled": True, "path": str(child_file), "status": "saved",
        "trace_present": True, "pid": 48, "tracer_entries": 1,
    })

    session_dir = tmp_path / "s"
    (session_dir / "raw").mkdir(parents=True)

    result = modal_app._attach_child_viztracer_trace(_FakeSession(session_dir))

    assert result["status"] == "captured"
    assert result["trace_present"] is True
    copied = session_dir / "raw" / "trace_child_viztracer.json"
    assert copied.is_file()
    assert json.loads(copied.read_text(encoding="utf-8"))["traceEvents"]
    # A manifest must exist so a captured child is distinguishable from none.
    manifest = json.loads(
        (session_dir / "raw" / "trace_child_viztracer_manifest.json").read_text(
            encoding="utf-8",
        )
    )
    assert manifest["status"] == "captured"
    assert manifest["sha256"] == result["sha256"]


def test_captured_child_is_discoverable_as_a_second_process(tmp_path, monkeypatch, modal_app):
    """End of the chain: an attached child trace must count as a traced process.

    This is the actual user-visible contract -- the profiler reports
    ``TRACED_PROCESSES`` from discovered trace files, so a child that is traced
    but not attached is invisible exactly like a child that never ran.
    """
    from comfymodal_runtime import golden_exhaustive_profile as gep  # type: ignore

    child_file = tmp_path / "comfymodal_c0_child_viztracer.json"
    child_file.write_text(json.dumps({"traceEvents": [
        {"name": "c0_worker (a.py:1)", "ph": "X", "ts": 0, "dur": 5000,
         "pid": 48, "tid": 48, "cat": "FEE"},
    ]}), encoding="utf-8")
    (tmp_path / (child_file.name + ".status.json")).write_text(
        json.dumps({"status": "saved", "pid": 48}), encoding="utf-8",
    )
    _fake_artifact(monkeypatch, {
        "enabled": True, "path": str(child_file), "status": "saved",
        "trace_present": True, "pid": 48,
    })

    session_dir = tmp_path / "s"
    (session_dir / "raw").mkdir(parents=True)
    (session_dir / "raw" / "viztracer.json").write_text(json.dumps({"traceEvents": [
        {"name": "golden_parallel_execute (a.py:1)", "ph": "X", "ts": 0,
         "dur": 9000000, "pid": 2, "tid": 2, "cat": "GOLDEN_ROOT"},
    ]}), encoding="utf-8")

    result = modal_app._attach_child_viztracer_trace(_FakeSession(session_dir))
    assert result["status"] == "captured"

    processes = gep.discover_process_traces(session_dir)
    assert sorted(p.pid for p in processes) == [2, 48]


def test_missing_child_trace_is_reported_not_silently_absent(tmp_path, monkeypatch, modal_app):
    # Flag ON but the child produced nothing: the run must not look complete.
    _fake_artifact(monkeypatch, {
        "enabled": True, "path": str(tmp_path / "absent.json"),
        "status": "missing", "trace_present": False,
    })
    session_dir = tmp_path / "s"
    (session_dir / "raw").mkdir(parents=True)

    result = modal_app._attach_child_viztracer_trace(_FakeSession(session_dir))

    assert result["status"] == "missing_child_trace"
    assert result["trace_present"] is False
    assert not (session_dir / "raw" / "trace_child_viztracer.json").exists()
    assert (session_dir / "raw" / "trace_child_viztracer_manifest.json").is_file()


def test_disabled_child_tracer_writes_nothing(tmp_path, monkeypatch, modal_app):
    _fake_artifact(monkeypatch, {
        "enabled": False, "path": "", "status": "disabled", "trace_present": False,
    })
    session_dir = tmp_path / "s"
    (session_dir / "raw").mkdir(parents=True)

    result = modal_app._attach_child_viztracer_trace(_FakeSession(session_dir))

    assert result["status"] == "disabled"
    assert not (session_dir / "raw" / "trace_child_viztracer.json").exists()
    assert not (session_dir / "raw" / "trace_child_viztracer_manifest.json").exists()


def test_attach_helper_never_raises_on_a_broken_child(monkeypatch, tmp_path, modal_app):
    def _boom():
        raise RuntimeError("child bootstrap exploded")

    import comfymodal_runtime.golden_io_process_v2 as gio  # type: ignore

    monkeypatch.setattr(gio, "child_viztracer_artifact", _boom)
    session_dir = tmp_path / "s"
    (session_dir / "raw").mkdir(parents=True)

    result = modal_app._attach_child_viztracer_trace(_FakeSession(session_dir))
    assert result["status"] == "disabled"


def test_bundle_includes_the_attached_child_trace(monkeypatch, tmp_path, modal_app):
    """The attach must land before bundling, or raw/ is walked too early."""
    child_file = tmp_path / "comfymodal_c0_child_viztracer.json"
    child_file.write_text(json.dumps({"traceEvents": [
        {"name": "c0_worker (a.py:1)", "ph": "X", "ts": 0, "dur": 1000,
         "pid": 48, "tid": 48, "cat": "FEE"},
    ]}), encoding="utf-8")
    (tmp_path / (child_file.name + ".status.json")).write_text(
        json.dumps({"status": "saved", "pid": 48}), encoding="utf-8",
    )
    _fake_artifact(monkeypatch, {
        "enabled": True, "path": str(child_file), "status": "saved",
        "trace_present": True, "pid": 48,
    })

    session_dir = tmp_path / "s"
    (session_dir / "raw").mkdir(parents=True)
    (session_dir / "raw" / "viztracer.json").write_text(
        json.dumps({"traceEvents": []}), encoding="utf-8",
    )
    session = _FakeSession(session_dir)

    assert modal_app._attach_child_viztracer_trace(session)["status"] == "captured"
    # Build the real bundle and confirm the child trace is one of its entries.
    bundle = modal_app._build_full_trace_bundle(session)
    assert bundle is not None
    trace_id, _base, tar_bytes, _sha, entries = bundle
    assert trace_id == "t123"
    paths = {e["path"] for e in entries}
    assert "raw/trace_child_viztracer.json" in paths
    assert "raw/trace_child_viztracer_manifest.json" in paths
    assert tar_bytes


def test_unknown_state_writes_a_manifest(monkeypatch, tmp_path, modal_app):
    """An unreadable artifact state must not look like a proven disable.

    This path used to return before both the manifest write and the log line, so
    a bundle with no manifest was ambiguous: flag off, or state never learned.
    """
    def _boom():
        raise RuntimeError("child bootstrap exploded")

    import comfymodal_runtime.golden_io_process_v2 as gio  # type: ignore

    monkeypatch.setattr(gio, "child_viztracer_artifact", _boom)
    session_dir = tmp_path / "s"
    (session_dir / "raw").mkdir(parents=True)

    result = modal_app._attach_child_viztracer_trace(_FakeSession(session_dir))
    manifest = session_dir / "raw" / "trace_child_viztracer_manifest.json"
    assert manifest.exists()
    assert result["state_unknown"] is True
    assert result["error"] == "RuntimeError"
    recorded = json.loads(manifest.read_text(encoding="utf-8"))
    assert recorded["state_unknown"] is True
