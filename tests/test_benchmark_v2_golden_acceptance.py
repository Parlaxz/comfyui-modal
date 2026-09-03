"""Focused regression tests for the canonical Golden acceptance gates."""

from __future__ import annotations

import asyncio
import copy
import json

import pytest

from comfymodal_runtime.contracts import DEPLOYMENT_HASH_NAMESPACE
import tools.benchmark_v2_direct as benchmark
from tools.benchmark_v2_direct import (
    GOLDEN_P1_REQUIRED_FLAGS,
    _golden_p1_consume_stream,
    _golden_p1_extract_telemetry,
    _golden_p1_deployed_identity,
    _golden_p1_scan_events,
    _golden_p1_validate_attempt,
)


SHA = "a" * 64
MISMATCH_SHA = "b" * 64


def _deployment_manifest(*, app: str, profile: str, fingerprint: str) -> dict:
    return {
        "schema_version": 2,
        "deployment_hash_namespace": DEPLOYMENT_HASH_NAMESPACE,
        "fingerprint_algorithm": "canonical-boundary-identity-v2",
        "deployment_hash": fingerprint,
        "created_at": "2026-08-30T12:00:00+00:00",
        "profile": profile,
        "target": {
            "app": app,
            "class": "ModalRuntimeEntrypointV2",
            "method": "run_golden_serial_stream",
        },
        "resources": {"gpu": "rtx-pro-6000"},
        "deploy_fingerprint": fingerprint,
    }


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


def test_golden_identity_uses_matching_manifest_not_stale_deployed_state(
    tmp_path, monkeypatch
):
    app = "batch-s1-cache-e1"
    profile = "golden_p1"
    fingerprint = "b" * 64
    deployments = tmp_path / ".v2ctl" / "deployments"
    deployments.mkdir(parents=True)
    (tmp_path / ".deployed_state.json").write_text(
        json.dumps({
            "app_name": "batch-ra2-active-patcher",
            "class_name": "StaleClass",
            "deployment_combined_hash": "stale",
            "profile": profile,
        }),
        encoding="utf-8",
    )
    (deployments / "deploy_20260830-120000-bbbbbbbb.json").write_text(
        json.dumps(_deployment_manifest(app=app, profile=profile, fingerprint=fingerprint)),
        encoding="utf-8",
    )
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)

    identity = _golden_p1_deployed_identity(
        app_name=app, profile=profile, deploy_fingerprint=fingerprint
    )

    assert identity["app_name"] == app
    assert identity["class_name"] == "ModalRuntimeEntrypointV2"
    assert identity["deploy_fingerprint"] == fingerprint
    assert identity["deployment_combined_hash"] == fingerprint
    assert "batch-ra2-active-patcher" not in json.dumps(identity)


def test_golden_identity_fails_closed_without_current_matching_manifest(tmp_path, monkeypatch):
    app = "batch-s1-cache-e1"
    profile = "golden_p1"
    current_fingerprint = "b" * 64
    deployments = tmp_path / ".v2ctl" / "deployments"
    deployments.mkdir(parents=True)
    (tmp_path / ".deployed_state.json").write_text(
        json.dumps({"app_name": "batch-ra2-active-patcher", "deploy_fingerprint": "a" * 64}),
        encoding="utf-8",
    )
    (deployments / "deploy_20260830-110000-aaaaaaaa.json").write_text(
        json.dumps(_deployment_manifest(
            app="batch-ra2-active-patcher", profile=profile, fingerprint="a" * 64
        )),
        encoding="utf-8",
    )
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)

    assert _golden_p1_deployed_identity(
        app_name=app, profile=profile, deploy_fingerprint=current_fingerprint
    ) == {}


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


def test_golden_output_sha_mismatch_is_valid_only_with_explicit_warning():
    scan = _scan()
    scan["output_shas"] = [(0, "result.output_sha", MISMATCH_SHA)]
    scan["output_sha_warnings"] = [(
        0,
        "result.golden_telemetry.stages[0].details.output_sha_warning",
        {"expected": SHA, "observed": MISMATCH_SHA},
    )]

    valid, failures, details = _validate(scan)

    assert valid, failures
    assert failures == []
    assert details["output_sha_match"] is False
    assert details["output_sha_warning"] == {
        "expected": SHA,
        "observed": MISMATCH_SHA,
    }

    scan["output_sha_warnings"] = []
    valid, failures, _details = _validate(scan)
    assert not valid
    assert any("without explicit warning evidence" in failure for failure in failures)


def test_golden_output_sha_malformed_or_missing_remains_invalid():
    missing = _scan()
    missing["output_shas"] = []
    valid, failures, _details = _validate(missing)
    assert not valid
    assert any("observed output SHA absent" in failure for failure in failures)

    malformed = _scan()
    malformed["output_shas"] = [(0, "result.output_sha", "not-a-sha")]
    valid, failures, _details = _validate(malformed)
    assert not valid
    assert any("malformed" in failure for failure in failures)


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


@pytest.mark.fast_unit
def test_golden_stream_stops_at_terminal_and_closes_once_with_metadata():
    telemetry = {"schema": "golden_p1_telemetry_v1", "events": [{"name": "done"}]}
    progress = {"type": "progress", "data": {"stage": "output"}}
    terminal = {
        "type": "result",
        "data": {
            "golden_telemetry": telemetry,
            "artifact_metadata": {"asset_id": SHA, "byte_count": 7},
        },
    }

    class _NeverExhaustingStream:
        def __init__(self):
            self.events = [progress, terminal]
            self.close_calls = 0
            self.exhaustion_attempted = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.events:
                return self.events.pop(0)
            self.exhaustion_attempted = True
            await asyncio.Future()
            raise AssertionError("unreachable")

        async def aclose(self):
            self.close_calls += 1
            await asyncio.Future()

    stream = _NeverExhaustingStream()

    class _RemoteMethod:
        remote_gen = None

        def aio(self, _payload):
            return stream

    class _Handle:
        run_golden_serial_stream = _RemoteMethod()

    events = asyncio.run(asyncio.wait_for(
        _golden_p1_consume_stream(_Handle(), {"request_id": "r"}), timeout=2
    ))

    assert events == [progress, terminal]
    assert stream.close_calls == 1
    assert not stream.exhaustion_attempted
    assert _golden_p1_extract_telemetry(events) == telemetry
    assert terminal["data"]["artifact_metadata"] == {"asset_id": SHA, "byte_count": 7}


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
