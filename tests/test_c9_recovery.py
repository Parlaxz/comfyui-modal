"""Offline contracts for the isolated C9 recovery campaign."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tools import run_c9_recovery as runner


def _valid_result(item: dict) -> dict:
    return {
        "experiment": "c9_recovery",
        "arm": "source_only",
        "execution_arm": "source_only",
        "status": "ok",
        "role": item["role"],
        "model_name": item["model_name"],
        "configured_source_qd": item["qd"],
        "source_block_bytes": runner.BLOCK_BYTES,
        "source_only": True,
        "torch_imported": False,
        "cuda_used": False,
        "h2d_used": False,
        "model_construction": False,
        "FILE_TO_CUDA_WALL_MS": None,
        "fixed_config": {
            "execution_arm": "source_only",
            "configured_qd": item["qd"],
            "producer_count": item["qd"],
            "source_block_bytes": runner.BLOCK_BYTES,
            "h2d_target_bytes": None,
            "aggregation_enabled": False,
            "cuda_used": False,
            "h2d_used": False,
            "model_construction": False,
        },
        "metrics": {"H2D_WALL_MS": None},
        "coverage": {"ok": True},
        "byte_reconciliation": {"returned_equals_expected": True},
        "SOURCE_WALL_MS": 1.0,
        "effective_GBps": 1.0,
        "time_weighted_achieved_qd": 1.0,
        "max_achieved_qd": item["qd"],
        "workers": [{} for _ in range(item["qd"])],
        "regions": [{"producer_id": n, "end": 12} for n in range(item["qd"])],
        "filesystem_identity": {},
        "cpu_allocation": {},
        "physical_reads": [{
            "worker_id": 0,
            "offset": 8,
            "requested_bytes": 4,
            "returned_bytes": 4,
            "syscall_begin_ns": 1,
            "syscall_end_ns": 2,
        }],
    }


def test_fixed_schedule_is_exact_and_has_no_other_geometry():
    schedule = runner.campaign_schedule()
    assert len(schedule) == 60
    assert {item["role"] for item in schedule} == {"clip", "unet"}
    assert {item["qd"] for item in schedule} == {2, 4, 8}
    assert {item["block_bytes"] for item in schedule} == {32 * 1024 * 1024}
    assert {item["observation"] for item in schedule} == set(range(1, 11))
    assert len({item["attempt_id"] for item in schedule}) == 60


def test_directional_schedule_allows_one_observation_without_new_geometry():
    schedule = runner.campaign_schedule(1)
    assert len(schedule) == 6
    assert {item["block_bytes"] for item in schedule} == {runner.BLOCK_BYTES}


def test_validation_rejects_non_32mib_or_non_source_result():
    item = runner.campaign_schedule()[0]
    result = _valid_result(item)
    result["source_block_bytes"] = 64 * 1024 * 1024
    result["fixed_config"]["source_block_bytes"] = 64 * 1024 * 1024
    failures = runner.validate_c9_result(result, item)
    assert "top_level_block_bytes_mismatch" in failures
    assert "fixed_config_source_block_bytes_mismatch" in failures


def test_campaign_calls_are_strictly_serial_and_keeps_ledger(tmp_path: Path):
    active = 0
    maximum = 0
    calls: list[str] = []

    async def fake_call(_function, item):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        calls.append(item["attempt_id"])
        await asyncio.sleep(0)
        active -= 1
        return _valid_result(item)

    output = asyncio.run(runner.run_campaign("test-c9", tmp_path, function=object(), call=fake_call))
    assert maximum == 1
    assert len(calls) == 60
    assert len(output["results"]) == 60
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["status"] == "COMPLETE"
    assert len(ledger["attempts"]) == 60
    assert all(item["status"] == "COMPLETE" for item in ledger["attempts"])
    assert len(list((tmp_path / "runs").glob("*.json"))) == 60


def test_campaign_records_remote_failure(tmp_path: Path):
    async def failing_call(_function, item):
        if item["campaign_index"] == 1:
            raise RuntimeError("synthetic remote failure")
        return _valid_result(item)

    output = asyncio.run(runner.run_campaign("test-c9", tmp_path, function=object(), call=failing_call))
    assert output["results"][0]["classification"] == "DNF"
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["attempts"][0]["status"] == "FAILED"
    assert len(ledger["attempts"]) == 60
