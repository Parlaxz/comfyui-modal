from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.fast_unit


def _args(**overrides):
    values = {
        "profile": "golden_p1",
        "app": "golden-test-app",
        "set": [],
        "inherit": [],
        "owner": None,
        "dry_run": False,
        "gpu": None,
        "memory_mb": None,
        "cpu": None,
        "skip_deploy": True,
        "min_ms": 1.0,
        "trace_id": None,
        "skip_analyze": False,
        "workspace_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_golden_profile_runs_publication_after_source_probe_and_fail_soft(
    monkeypatch, tmp_path, capsys
):
    from tools.v2_control import cli

    calls = []

    def fake_v2ctl(_repo_root, argv, *, capture):
        calls.append(argv[-1])
        if argv[-1] == "source-probe":
            return 0, "RESULT=PASS\n"
        if argv[-1] == "publish-model-metadata-cache":
            return 1, "RESULT=ERROR\n"
        return 0, "trace_id=trace-for-test\n"

    volume_calls = iter([set(), {"trace-for-test"}])
    monkeypatch.setattr(cli, "_run_v2ctl", fake_v2ctl)
    monkeypatch.setattr(cli, "_volume_trace_ids", lambda *_args: next(volume_calls))
    monkeypatch.setattr(cli, "_profile_app_name", lambda *_args: "golden-test-app")
    monkeypatch.setitem(
        sys.modules,
        "golden_profile_pipeline",
        SimpleNamespace(main=lambda _argv: 0),
    )

    assert cli.cmd_golden_profile(_args(), tmp_path) == 0
    assert calls == ["source-probe", "publish-model-metadata-cache", "run"]
    output = capsys.readouterr()
    assert "continuing fail-soft" in output.err
    assert "step 2 publish-model-metadata-cache" in output.out


def test_golden_profile_dry_run_lists_publication_step(monkeypatch, tmp_path, capsys):
    from tools.v2_control import cli

    assert cli.cmd_golden_profile(_args(dry_run=True), tmp_path) == 0
    assert "source-probe, publish-model-metadata-cache, run" in capsys.readouterr().out
