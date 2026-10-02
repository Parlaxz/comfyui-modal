"""Focused, local-only tests for the compact Golden guardrails."""

from __future__ import annotations

import json
import os
import subprocess
from collections import namedtuple
from datetime import datetime, timezone

import pytest

from tools.v2_control.golden_guard import (
    ARTIFACT_DNF,
    INVALID,
    NOT_SENT,
    REMOTE_FAILED,
    VALID,
    GitSnapshot,
    classify_lock,
    classify_outcome,
    dirty_diff,
    disk_check,
    worktree_occupancy,
    bootstrap_worktree,
    run_safe_operation,
)
import tools.v2_control.golden_guard as golden_guard
from tools.v2_control.locking import DeployLock


pytestmark = pytest.mark.fast_unit


def _write_lock(path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps({
        "schema_version": 1, "owner": "test", "pid": pid,
        "host": DeployLock.host_id(), "target": "app", "profile": "golden_p1",
        "timestamp": now, "started_at": now,
    }), encoding="utf-8")


def test_lock_classification_distinguishes_live_and_dead_pid(tmp_path, monkeypatch):
    path = tmp_path / ".v2ctl" / "deploy.lock"
    _write_lock(path, 1234)
    lock = DeployLock(path)
    monkeypatch.setattr(lock, "_pid_alive", lambda pid: True)
    assert classify_lock(lock)["live_owner"] is True
    monkeypatch.setattr(lock, "_pid_alive", lambda pid: False)
    assert classify_lock(lock)["stale"] is True


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"attempted": False}, NOT_SENT),
        ({"attempted": True, "returncode": 1}, REMOTE_FAILED),
        ({"attempted": True, "returncode": 0}, ARTIFACT_DNF),
        ({"attempted": True, "returncode": 0, "artifact_found": True}, INVALID),
        ({"attempted": True, "returncode": 0, "artifact_found": True, "valid": True}, VALID),
    ],
)
def test_outcome_classifier(kwargs, expected):
    assert classify_outcome(**kwargs) == expected


def test_dirty_worktree_is_not_occupancy(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.v2_control.golden_guard.process_alive", lambda pid: True)
    state = worktree_occupancy(tmp_path, conflicting_pids=[])
    assert state["occupied"] is False
    assert state["dirty_is_occupancy"] is False


def test_low_disk_fails_guard(tmp_path):
    Usage = namedtuple("Usage", "total used free")
    check = disk_check(tmp_path, min_free_gb=1, usage_fn=lambda path: Usage(10, 9, 10))
    assert check.ok is False
    assert check.free_bytes == 10


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), -float("inf")])
def test_disk_threshold_must_be_finite_and_nonnegative(tmp_path, value):
    with pytest.raises(ValueError):
        disk_check(tmp_path, min_free_gb=value)


def test_corrupt_lock_is_present_ambiguous_and_not_stale(tmp_path):
    path = tmp_path / ".v2ctl" / "deploy.lock"
    path.parent.mkdir()
    path.write_text("not json", encoding="utf-8")
    result = classify_lock(DeployLock(path))
    assert result["present"] is True
    assert result["ambiguous"] is True
    assert result["stale"] is False


def test_timeout_inspects_state_and_refuses_blind_retry(tmp_path, monkeypatch):
    calls = []
    timeouts = []

    def run_fn(*args, **kwargs):
        calls.append(args[0])
        timeouts.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output="partial")

    inspected = {"lock": {"present": False}, "remote_completion": "unknown"}
    monkeypatch.setattr(golden_guard, "_inspect_supported_state", lambda root, app: inspected)
    result = run_safe_operation(tmp_path, "source-probe", "test-app", retries=2, run_fn=run_fn)
    assert len(calls) == 1
    assert timeouts == [1_800.0]
    assert result.outcome == REMOTE_FAILED
    assert result.timeout_classification == "operation_timeout_state_ambiguous"
    assert result.inspections[0]["after_timeout"] is True
    assert "state_inspection" in result.stderr


def test_bootstrap_never_copies_credentials_or_runtime_state(tmp_path, monkeypatch):
    for relative in (".modal_workspaces.json", ".deployed_state.json", ".deploy_warmup_state.json"):
        path = tmp_path / relative
        path.write_text("secret", encoding="utf-8")
    (tmp_path / ".runtime_state").mkdir()
    (tmp_path / ".runtime_state" / "state.json").write_text("runtime", encoding="utf-8")
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "large.bin").write_bytes(b"x" * 32)
    monkeypatch.setattr(golden_guard.subprocess, "run", lambda *args, **kwargs: None)
    result = bootstrap_worktree(tmp_path, tmp_path / "staged")
    assert result["copied"] == []
    assert not (tmp_path / "staged" / ".modal_workspaces.json").exists()
    assert not (tmp_path / "staged" / ".runtime_state" / "state.json").exists()
    assert not (tmp_path / "staged" / "artifacts" / "large.bin").exists()


def test_preexisting_and_experiment_owned_dirty_paths_are_separate():
    baseline = GitSnapshot("TESTING2", "old", ("CONTEXT.md", "notes.txt"))
    current = GitSnapshot("TESTING2", "new", ("CONTEXT.md", "tools/new.py"))
    diff = dirty_diff(baseline, current)
    assert diff["pre_existing_dirty"] == ["CONTEXT.md", "notes.txt"]
    assert diff["experiment_owned_dirty"] == ["tools/new.py"]
    assert diff["cleaned_since_baseline"] == ["notes.txt"]
