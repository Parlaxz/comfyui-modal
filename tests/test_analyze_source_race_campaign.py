"""Fast, local tests for source-race campaign descriptive statistics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.analyze_source_race_campaign import analyze, main, render_markdown


pytestmark = pytest.mark.fast_unit


def _artifact(
    path: Path,
    *,
    attempt_id: str,
    family: str,
    observed: str,
    width: int,
    accepted: list[float],
    loser: float = 20.0,
    session: str | None = None,
) -> None:
    blocks = []
    for index, accepted_ms in enumerate(accepted):
        blocks.append({
            "block_index": index,
            "length": 10,
            "accepted_preadv_ms": accepted_ms,
            "cumulative_physical_bytes_before_block": index * width * 10,
            "winner_to_loser_end_delta_ms": [loser] * (width - 1),
            "fighters": [
                {"physical_syscall_ms": accepted_ms, "bytes_read": 10, "status": "ok", "error": None, "is_winner": True},
                *[
                    {"physical_syscall_ms": loser, "bytes_read": 10, "status": "ok", "error": None, "is_winner": False, "loser_lifetime_ms": loser + 1}
                    for _ in range(width - 1)
                ],
            ],
        })
    engine = {
        "status": "ok",
        "config": {"race_width": width},
        "identity": {"observed_gpu": observed, "requested_gpu": observed, "container_session_id": session or attempt_id},
        "blocks": blocks,
        "accepted": {"count": len(accepted)},
        "amplification": {"attempts_launched": len(accepted) * width},
    }
    artifact = {
        "attempt_id": attempt_id,
        "round": 1,
        "gpu_family": family,
        "race_width": width,
        "observed_gpu": observed,
        "requested_gpu": observed,
        "container_session_id": session or attempt_id,
        "campaign_status": "COMPLETE",
        "coldness_evidence": {"valid": True},
        "engine_result": engine,
    }
    path.write_text(json.dumps(artifact), encoding="utf-8")


def test_known_width_statistics_and_linear_percentiles(tmp_path: Path) -> None:
    _artifact(tmp_path / "a.json", attempt_id="a", family="h100", observed="NVIDIA H100", width=2, accepted=[10, 20])
    aggregate = analyze(tmp_path)
    group = next(item for item in aggregate["groups"] if item["gpu_family"] == "h100" and item["race_width"] == 2)
    assert group["accepted_stats"]["count"] == 2
    assert group["accepted_stats"]["mean_ms"] == 15
    assert group["accepted_stats"]["median_ms"] == 15
    assert group["accepted_stats"]["p95_ms"] == pytest.approx(19.5)
    assert group["accepted_stats"]["max_ms"] == 20


def test_physical_losers_are_not_in_accepted_aggregate(tmp_path: Path) -> None:
    _artifact(tmp_path / "a.json", attempt_id="a", family="h100", observed="H100", width=2, accepted=[10], loser=10000)
    group = next(item for item in analyze(tmp_path)["groups"] if item["gpu_family"] == "h100")
    assert group["accepted_values"] == [10.0]
    assert group["physical_stats"]["max_ms"] == 10000
    assert group["accepted_stats"]["max_ms"] == 10


def test_families_stay_separate_and_mismatch_is_excluded(tmp_path: Path) -> None:
    _artifact(tmp_path / "h.json", attempt_id="h", family="h100", observed="H100", width=2, accepted=[10])
    _artifact(tmp_path / "r.json", attempt_id="r", family="rtx", observed="RTX PRO 6000", width=2, accepted=[30])
    _artifact(tmp_path / "bad.json", attempt_id="bad", family="h100", observed="H200", width=2, accepted=[99])
    aggregate = analyze(tmp_path)
    assert {group["gpu_family"] for group in aggregate["groups"]} == {"h100", "rtx"}
    assert next(group for group in aggregate["groups"] if group["gpu_family"] == "h100")["accepted_values"] == [10.0]
    assert any(item["attempt_id"] == "bad" and "does not match" in item["reason"] for item in aggregate["exclusions"])


def test_threshold_counts_and_physical_summary(tmp_path: Path) -> None:
    _artifact(tmp_path / "a.json", attempt_id="a", family="h100", observed="H100", width=2, accepted=[100, 250, 500, 1000], loser=1100)
    group = next(group for group in analyze(tmp_path)["groups"] if group["gpu_family"] == "h100")
    accepted = group["accepted_stats"]
    assert [accepted[f"ge_{threshold}"] for threshold in (100, 250, 500, 1000)] == [4, 3, 2, 1]
    assert group["amplification"]["attempts_launched"] == 8
    assert group["amplification"]["accepted_bytes"] == 40
    assert group["amplification"]["total_physical_bytes_requested"] == 80


def test_markdown_has_all_five_tables_and_cli_writes_json(tmp_path: Path) -> None:
    _artifact(tmp_path / "a.json", attempt_id="a", family="h100", observed="H100", width=2, accepted=[10])
    report = tmp_path / "report.md"
    aggregate_json = tmp_path / "aggregate.json"
    assert main(["--out", str(tmp_path), "--md", str(report), "--json", str(aggregate_json)]) == 0
    text = report.read_text(encoding="utf-8")
    for heading in (
        "## 1. Accepted latency vs race width",
        "## 2. Physical attempt latency vs race width",
        "## 3. Accepted latency vs block index",
        "## 4. Accepted latency vs cumulative speculative bytes",
        "## 5. Winner-to-loser completion delta distribution",
    ):
        assert heading in text
    assert json.loads(aggregate_json.read_text(encoding="utf-8"))["included_observations"] == 1
