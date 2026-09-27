import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "run_exp06_parallel.py"
spec = importlib.util.spec_from_file_location("run_exp06_parallel", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase2_partition_is_four_disjoint_eight_cell_shards():
    shards = module.partition_cells()
    assert list(shards) == ["clip_32_64", "clip_128_256", "unet_32_64", "unet_128_256"]
    assert [len(cells) for cells in shards.values()] == [8, 8, 8, 8]
    assert len({cell["cell_id"] for cells in shards.values() for cell in cells}) == 32
    assert {cell["block_mib"] for cell in shards["clip_32_64"]} == {32, 64}
    assert {cell["role"] for cell in shards["unet_128_256"]} == {"unet"}


def test_progress_counts_unique_eligible_observations_at_twentieth_boundary():
    progress = module.ProgressCounter()
    assert not progress.record("first", False)
    boundaries = [progress.record(f"attempt-{i}", True) for i in range(1, 21)]
    assert boundaries[-1] is True
    assert progress.newly_completed == 20
    assert not progress.record("attempt-20", True)
    assert progress.newly_completed == 20


def test_merge_preserves_attempt_union_and_closes_running_records():
    canonical = {
        "ledger": {
            "cells": [
                {
                    "cell_id": "clip_b32_qd1",
                    "role": "clip",
                    "block_mib": 32,
                    "qd": 1,
                    "attempts": [{"attempt_id": "old", "status": "COMPLETE"}],
                }
            ]
        }
    }
    shard = {
        "ledger": {
            "cells": [
                {
                    "cell_id": "clip_b32_qd1",
                    "attempts": [
                        {"attempt_id": "old", "status": "COMPLETE"},
                        {"attempt_id": "new", "status": "RUNNING"},
                    ],
                }
            ]
        }
    }
    module.reconcile_running_attempts(shard["ledger"], "interrupted_for_test")
    merged = module.merge_ledger_attempts(canonical, [shard])
    attempts = merged["ledger"]["cells"][0]["attempts"]
    assert [attempt["attempt_id"] for attempt in attempts] == ["old", "new"]
    assert attempts[-1]["status"] == "FAILED"
    assert attempts[-1]["interruption_reason"] == "interrupted_for_test"


def test_prepare_creates_separate_state_and_output_roots(tmp_path):
    state = tmp_path / "campaign.json"
    state.write_text(json.dumps({"ledger": {"cells": module.campaign_cells()}}), encoding="utf-8")
    canonical, state_paths, output_paths = module._prepare_documents(state, tmp_path / "raw", 2)
    assert len(state_paths) == len(output_paths) == 4
    assert len(canonical["parallel_shards"]) == 4
    assert all(path != state for path in state_paths.values())
    assert all(path.parent == tmp_path for path in state_paths.values())
