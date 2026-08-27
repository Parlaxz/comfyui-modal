"""Focused regression tests for the canonical Golden acceptance gates."""

from __future__ import annotations

import copy

import pytest

from tools.benchmark_v2_direct import (
    GOLDEN_P1_REQUIRED_FLAGS,
    _golden_p1_extract_telemetry,
    _golden_p1_scan_events,
    _golden_p1_validate_attempt,
)


SHA = "a" * 64


def _proof() -> dict:
    return {
        "schema": "golden_snapshot_content_proof_v1",
        "passive": True,
        "proven": True,
        "surface_count": 1,
        "snapshot_size_bytes": 1,
        "snapshot_size_limit_bytes": 2,
        "snapshot_size_source": "process_rss_pre_capture_resident_memory_proxy",
        "snapshot_size_is_serialized": False,
        "tensor_count": 0,
        "parameter_bytes": 0,
        "model_patcher_count": 0,
        "qd_owner_count": 0,
        "open_payload_reader_count": 0,
        "preload_worker_count": 0,
        "future_count": 0,
        "nonzero": {},
        "nonzero_roles": {},
        "roles": {
            role: {"tensor_count": 0, "parameter_bytes": 0, "qd_owner_count": 0}
            for role in ("unet", "clip", "vae")
        },
    }


def _scan(*, flags: dict | None = None, proof: dict | None = None,
          seriality: dict | None = None) -> dict:
    return {
        "terminal_results": [(0, {"type": "result"})],
        "error_events": [],
        "true_durable": [(0, "result.true_durable", True)],
        "seriality": [(0, "result.seriality", seriality if seriality is not None else {
            "ok": True, "violations": [], "count": 0,
        })],
        "teardown": [(0, "result.teardown", {"ok": True})],
        "snapshot_proof": [(
            0, "result.golden_snapshot_content_proof", proof if proof is not None else _proof()
        )],
        "commit": [(0, "result.commit", 1)],
        "reopen": [(0, "result.reopen", 2)],
        "true_first": [(0, "result.true_first_durable_result", 3)],
        "flags": [(
            0, "result.golden_flags_observed",
            flags if flags is not None else dict(GOLDEN_P1_REQUIRED_FLAGS),
        )],
        "identities": [],
        "output_shas": [(0, "result.output_sha", SHA)],
        "non_dict_events": 0,
    }


def _validate(scan: dict, *, expected_flags: dict | None = None):
    return _golden_p1_validate_attempt(
        scan,
        expected_output_sha=SHA,
        expected_flags=expected_flags,
    )


def test_terminal_golden_flags_are_scanned_and_optional_extra_expectations_match():
    events = [{
        "type": "result",
        "data": {"golden_flags_observed": dict(GOLDEN_P1_REQUIRED_FLAGS)},
    }]
    scanned = _golden_p1_scan_events(events)
    assert scanned["flags"] == [(0, "data.golden_flags_observed", dict(GOLDEN_P1_REQUIRED_FLAGS))]

    valid, failures, _details = _validate(
        _scan(flags={**GOLDEN_P1_REQUIRED_FLAGS, "custom_gate": True}),
        expected_flags={"custom_gate": "1"},
    )
    assert valid, failures


def test_nested_telemetry_uses_seriality_proof_and_earliest_commit_event():
    commit_event_ts = 1787855533.821160861
    reopen_event_ts = 1787855533.827739060
    events = [{
        "type": "result",
        "data": {
            "seriality_violation_count": 0,
            "golden_telemetry": {
                "seriality": {"ok": True, "violations": [], "count": 0},
                "stages": [{
                    "name": "golden_durable_commit",
                    "end_wall_ns": 1787855533827747600,
                    "ok": True,
                }],
                "events": [
                    {"name": "VOLUME_COMMIT_COMPLETE", "wall_ns": commit_event_ts},
                    {"name": "durable_reopen_verified", "wall_ns": reopen_event_ts},
                ],
            },
        },
    }]

    nested = _golden_p1_scan_events(events)
    assert nested["seriality"] == [(
        0,
        "data.golden_telemetry.seriality",
        {"ok": True, "violations": [], "count": 0},
    )]
    assert all("seriality_violation_count" not in path for _, path, _ in nested["seriality"])

    scan = _scan()
    scan["seriality"] = nested["seriality"]
    scan["commit"] = nested["commit"]
    scan["reopen"] = nested["reopen"]
    scan["true_first"] = [(0, "result.true_first_durable_result", 1787855533.9)]
    valid, failures, details = _validate(scan)
    assert valid, failures
    assert details["commit_evidence"] == {
        "index": 0,
        "path": "data.golden_telemetry.events[0]",
        "ts": commit_event_ts,
    }
    assert details["reopen_evidence"] == {
        "index": 0,
        "path": "data.golden_telemetry.events[1]",
        "ts": reopen_event_ts,
    }


def test_host_artifact_projection_keeps_telemetry_on_result_or_error():
    telemetry = {"schema": "golden_p1_telemetry_v1", "events": []}
    assert _golden_p1_extract_telemetry(
        [{"type": "result", "data": {"golden_telemetry": telemetry}}]
    ) == telemetry
    assert _golden_p1_extract_telemetry(
        [{"type": "error", "golden_telemetry": telemetry}]
    ) == telemetry


@pytest.mark.parametrize(
    "mutate",
    [
        lambda proof: proof.clear(),
        lambda proof: proof.update(proven=False),
        lambda proof: proof.update(future_count=1),
        lambda proof: proof.update(nonzero={"future_count": 1}),
        lambda proof: proof["roles"]["clip"].update(tensor_count=1),
    ],
)
def test_nonempty_but_unproven_or_contaminated_snapshot_proof_fails_closed(mutate):
    proof = copy.deepcopy(_proof())
    mutate(proof)
    valid, failures, _details = _validate(_scan(proof=proof))
    assert not valid
    assert any("snapshot proof" in failure for failure in failures)


@pytest.mark.parametrize(
    "seriality",
    [
        {"ok": False, "violations": [], "count": 0},
        {"ok": True, "violations": ["stage overlap"], "count": 1},
        {"ok": True, "count": 0},
    ],
)
def test_seriality_requires_explicit_success_and_empty_violations(seriality):
    valid, failures, _details = _validate(_scan(seriality=seriality))
    assert not valid
    assert any("seriality proof invalid" in failure for failure in failures)


def test_missing_or_mismatched_canonical_flags_fails_closed():
    missing = dict(GOLDEN_P1_REQUIRED_FLAGS)
    missing.pop("core_model_patcher_is_dynamic")
    valid, failures, _details = _validate(_scan(flags=missing))
    assert not valid
    assert any("runtime flag evidence missing" in failure for failure in failures)

    wrong = dict(GOLDEN_P1_REQUIRED_FLAGS)
    wrong["COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM"] = False
    valid, failures, _details = _validate(_scan(flags=wrong))
    assert not valid
    assert any("runtime flag mismatch" in failure for failure in failures)
