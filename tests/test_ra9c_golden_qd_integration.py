"""Offline integration contracts for the RA9C Golden QD wiring."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "golden_serial.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("golden_serial_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("golden_serial_under_test", module)
    spec.loader.exec_module(module)
    return module


gs = _load_module()


def _request():
    return gs.GoldenRequest("request", {"1": {"class_type": "LoadImage", "inputs": {}}})


def test_selector_is_independent_of_stage_diagnostics_and_emits_run_identity_evidence(monkeypatch):
    monkeypatch.delenv(gs.GOLDEN_STAGE_DIAGNOSTICS_ENV, raising=False)
    monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, " DISPATCHER ")

    assert gs.golden_qd_transport_arm() == "dispatcher"
    session = gs.GoldenSession(_request(), volume=object())

    assert session.qd_transport_arm == "dispatcher"
    assert session.run_identity["qd_transport_arm"] == "dispatcher"
    payload = session.recorder.to_json_dict()
    assert payload["run_identity"]["qd_transport_arm"] == "dispatcher"
    assert any(
        event["name"] == "golden_qd_transport_selector"
        and event["fields"]["arm"] == "dispatcher"
        for event in payload["events"]
    )


@pytest.mark.parametrize("raw, expected", [(None, "legacy"), ("", "legacy"), ("legacy", "legacy")])
def test_selector_normalizes_legacy_without_bookkeeping(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv(gs.GOLDEN_QD_TRANSPORT_ENV, raising=False)
    else:
        monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, raw)
    monkeypatch.setenv(gs.GOLDEN_STAGE_DIAGNOSTICS_ENV, "1")

    assert gs.golden_qd_transport_arm() == expected
    session = gs.GoldenSession(_request(), volume=object())
    assert session.run_identity["qd_transport_arm"] == expected


@pytest.mark.parametrize("raw", [None, "legacy"])
def test_legacy_read_path_remains_control_branch_without_cuda(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv(gs.GOLDEN_QD_TRANSPORT_ENV, raising=False)
    else:
        monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, raw)
    called = []

    def forbidden_dispatcher(*args, **kwargs):
        called.append((args, kwargs))
        return {"status": "unexpected"}

    monkeypatch.setattr(gs, "_read_file_qd_gpu_dispatcher", forbidden_dispatcher)
    monkeypatch.setattr(gs.torch.cuda, "is_available", lambda: False)

    with pytest.raises(RuntimeError, match="cuda_unavailable"):
        gs.read_file_qd_gpu("unused.safetensors", role="clip")
    assert called == []

    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "read_file_qd_gpu"
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "golden_qd_transport_arm"
        for node in ast.walk(fn)
    )


def test_dispatcher_branch_calls_adapter_with_original_arguments(monkeypatch):
    monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, "dispatcher")
    calls = []
    sentinel = {"status": "sentinel"}

    def adapter(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(gs, "_read_file_qd_gpu_dispatcher", adapter)
    result = gs.read_file_qd_gpu(
        "checkpoint.safetensors",
        role="clip",
        device="cuda:7",
        qd=9,
        block_bytes=123,
        diagnostics=False,
    )

    assert result is sentinel
    assert calls == [
        (("checkpoint.safetensors",), {
            "role": "clip",
            "device": "cuda:7",
            "qd": 9,
            "block_bytes": 123,
            "diagnostics": False,
        })
    ]


def test_register_qd_owner_is_immediately_visible_and_deduplicated(monkeypatch):
    monkeypatch.delenv(gs.GOLDEN_QD_TRANSPORT_ENV, raising=False)
    session = gs.GoldenSession(_request(), volume=object())
    owner = gs.GoldenQDOwner(object(), [object()], "cpu", "clip")
    other_owner = gs.GoldenQDOwner(object(), [object()], "cpu", "vae")

    session.register_qd_owner(owner)
    session.register_qd_owner(other_owner)
    session.register_qd_owner(owner)

    assert session.qd_transaction_owners == [owner, other_owner]


def test_teardown_releases_earlier_clip_transaction_without_clip_owners(monkeypatch):
    monkeypatch.delenv(gs.GOLDEN_QD_TRANSPORT_ENV, raising=False)
    session = gs.GoldenSession(_request(), volume=object())
    owner = gs.GoldenQDOwner(object(), [object()], "cpu", "clip")
    releases = []

    def release_staging():
        releases.append(True)

    monkeypatch.setattr(owner, "release_staging", release_staging)
    session.register_qd_owner(owner)
    del session.clip_owners

    asyncio.run(gs.golden_teardown(session))
    assert len(releases) == 1


def test_run_identity_and_transaction_registry_are_request_local(monkeypatch):
    monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, "dispatcher")
    first = gs.GoldenSession(_request(), volume=object())
    second = gs.GoldenSession(_request(), volume=object())
    owner = gs.GoldenQDOwner(object(), [], "cpu", "clip")

    first.register_qd_owner(owner)

    assert first.run_identity is not second.run_identity
    assert first.run_identity["qd_transport_arm"] == "dispatcher"
    assert second.run_identity["qd_transport_arm"] == "dispatcher"
    assert first.qd_transaction_owners == [owner]
    assert second.qd_transaction_owners == []


def test_frozen_session_arm_wins_over_mid_request_environment_change(monkeypatch):
    monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, "dispatcher")
    session = gs.GoldenSession(_request(), volume=object())
    monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, "legacy")

    assert gs.golden_qd_transport_arm() == "legacy"
    assert gs.golden_qd_transport_arm(session.qd_transport_arm) == "dispatcher"


def test_stage_failure_preserves_wrapped_transport_telemetry():
    recorder = gs.GoldenTelemetryRecorder()
    recorder.begin_stage("golden_clip_load")
    error = RuntimeError("wrapped transport failure")
    setattr(error, "telemetry", {"h2d_completed_count": 3})
    setattr(error, "transport_failure", {"primary_error": "OSError: source failed"})

    recorder.fail_stage("golden_clip_load", error)

    interval = next(
        stage for stage in recorder.to_json_dict()["stages"] if stage["name"] == "golden_clip_load"
    )
    assert interval["details"]["transport_telemetry"] == {"h2d_completed_count": 3}
    assert interval["details"]["transport_failure"] == {
        "primary_error": "OSError: source failed"
    }
