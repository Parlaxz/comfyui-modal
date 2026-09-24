from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools.run_source_race_campaign import (
    _DEFAULT_WIDTHS,
    _new_ledger,
    campaign_schedule,
    ledger_key,
    serialize_run,
    transition_cell,
)


pytestmark = pytest.mark.fast_unit


def test_default_schedule_is_the_required_five_by_five_latin_square():
    schedule = campaign_schedule("source_race_h100", 5, _DEFAULT_WIDTHS, "clip")
    rows = [
        [item["race_width"] for item in schedule[offset : offset + 5]]
        for offset in range(0, 25, 5)
    ]
    assert rows == [
        [1, 2, 4, 8, 16],
        [16, 8, 4, 2, 1],
        [2, 8, 1, 16, 4],
        [4, 1, 16, 2, 8],
        [8, 16, 2, 4, 1],
    ]
    assert all(sorted(row) == sorted(_DEFAULT_WIDTHS) for row in rows)


def test_schedule_covers_each_width_per_round_and_supports_custom_inputs():
    schedule = campaign_schedule("source_race_rtx", 3, (3, 7, 11), "clip")
    rows = [[item["race_width"] for item in schedule[offset : offset + 3]] for offset in (0, 3, 6)]
    assert rows == [[3, 7, 11], [7, 11, 3], [11, 3, 7]]
    assert all(sorted(row) == [3, 7, 11] for row in rows)
    assert [item["cell_key"] for item in schedule[:2]] == [
        ledger_key("source_race_rtx", 1, 3),
        ledger_key("source_race_rtx", 1, 7),
    ]


def test_ledger_key_and_state_transitions_are_explicit():
    schedule = campaign_schedule("source_race_h100", 1, (1,), "clip")
    ledger = _new_ledger("source_race_h100", {"rounds": 1}, schedule)
    cell = ledger["cells"][ledger_key("source_race_h100", 1, 1)]
    assert cell["status"] == "PENDING"
    transition_cell(cell, "RUNNING", attempt_id="a1")
    assert cell["status"] == "RUNNING" and cell["attempt_id"] == "a1"
    transition_cell(cell, "COMPLETE", artifact="a1.json")
    assert cell["status"] == "COMPLETE" and cell["artifact"] == "a1.json"
    with pytest.raises(ValueError):
        transition_cell(cell, "UNKNOWN")


def test_serialization_preserves_engine_dict_and_records_absent_evidence():
    item = campaign_schedule("source_race_h100", 1, (4,), "clip")[0]
    engine = {
        "status": "ok",
        "identity": {"container_session_id": "container-a"},
        "provider": "provider-a",
        "raw_payload": {"kept": True},
    }
    artifact = serialize_run(
        item,
        model_name="qwen_3_4b.safetensors",
        logical_qd=2,
        read_bytes=128,
        max_blocks=0,
        fd_mode="independent",
        hash_mode="winners_in_order",
        attempt_id="attempt-a",
        binding={"deployment_version": 3, "receipt_path": "receipt.json"},
        engine_result=engine,
        previous_container_id=None,
    )
    assert artifact["engine_result"] is engine
    assert artifact["evidence"] == {
        "identity": {"container_session_id": "container-a"},
        "provider": "provider-a",
        "region": "",
        "observed_gpu": "",
        "requested_gpu": "",
    }
    assert artifact["coldness_evidence"]["observed_container_identity"] == "container-a"
    assert artifact["campaign_status"] == "COMPLETE"
