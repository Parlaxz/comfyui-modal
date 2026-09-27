"""Focused P4.1 Golden identity/cold-label regression tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from tools.benchmark_v2_direct import (
    _extract_identity_from_trace,
    _golden_p1_cold_evidence,
    _golden_p1_duplicate_identity_fields,
    _run_golden_p1,
)
from comfymodal_runtime.modal_app import _post_restore_identity_telemetry


def _cold_identity(**overrides):
    identity = {
        "restored_instance_id": "instance-a",
        "restore_session_id": "restore-a",
        "post_restore_nonce": "nonce-a",
        "container_session_id": "container-a",
        "restore_count": 1,
        "request_count": 1,
        "min_containers": 0,
        "single_use_containers": True,
        "deployment_identity": "deploy-a",
        "snapshot_identity": "snapshot-a",
        "config_identity": "config-a",
    }
    identity.update(overrides)
    return identity


def test_post_restore_nonce_is_only_projected_from_runtime_state():
    runtime = SimpleNamespace(
        _post_restore_nonce="",
        _restore_session_id="restore-a",
        _restored_instance_id="instance-a",
        _restore_count=1,
        _request_count=1,
        container_session_id="container-a",
        _restore_timing={},
    )
    before_restore = _post_restore_identity_telemetry(runtime, request_id="req-a")
    assert before_restore["post_restore_nonce"] == ""
    runtime._post_restore_nonce = "nonce-a"
    after_restore = _post_restore_identity_telemetry(runtime, request_id="req-a")
    assert after_restore["post_restore_nonce"] == "nonce-a"


def test_identity_projection_uses_request_lifecycle_and_terminal_result():
    result = {
        "trace": {
            "metadata": {"restore_count": 99, "request_count": 99},
            "events": [
                {"name": "post_restore_identity", "metadata": {
                    "restore_session_id": "restore-a",
                    "post_restore_nonce": "nonce-a",
                }},
                {"name": "remote_method_entry", "metadata": {
                    "request_id": "req-a",
                    "restore_count": 1,
                    "request_count": 1,
                    "restored_instance_id": "instance-a",
                }},
            ],
        },
        "identity": {"post_restore_nonce": "nonce-terminal"},
    }
    identity = _extract_identity_from_trace(result, "req-a")
    assert identity["restore_count"] == 1
    assert identity["request_count"] == 1
    assert identity["restore_session_id"] == "restore-a"
    assert identity["post_restore_nonce"] == "nonce-terminal"


def test_identity_projection_preserves_absent_counts_as_none():
    identity = _extract_identity_from_trace(
        {"trace": {"events": [{"name": "remote_method_entry", "metadata": {
            "request_id": "req-a",
        }}]}},
        "req-a",
    )
    assert identity["restore_count"] is None
    assert identity["request_count"] is None


def test_cold_label_requires_all_frozen_and_runtime_evidence():
    evidence = _golden_p1_cold_evidence(_cold_identity())
    assert evidence["true_cold"] is True
    assert evidence["missing_requirements"] == []

    for key, value in (
        ("post_restore_nonce", ""),
        ("restore_count", None),
        ("min_containers", 1),
        ("single_use_containers", False),
        ("snapshot_identity", ""),
    ):
        assert _golden_p1_cold_evidence(_cold_identity(**{key: value}))["true_cold"] is False


def test_duplicate_nonce_and_exposed_instance_are_independent_failures():
    seen_nonces = {"nonce-a"}
    seen_instances = {"instance-a"}
    assert _golden_p1_duplicate_identity_fields(
        _cold_identity(), seen_nonces, seen_instances,
    ) == ["post_restore_nonce", "restored_instance_id"]
    assert _golden_p1_duplicate_identity_fields(
        _cold_identity(post_restore_nonce="nonce-b"), seen_nonces, seen_instances,
    ) == ["restored_instance_id"]


@pytest.mark.asyncio
async def test_golden_p1_rejects_nonpositive_gap_before_dispatch():
    with pytest.raises(ValueError, match="gap_seconds"):
        await _run_golden_p1(
            {},
            cast(Any, object()),
            run_count=1,
            gap_seconds=0,
            app_name="app",
            class_name="class",
            gpu="gpu",
            artifacts_dir=None,
            cohort_id=None,
            expected_output_sha="sha",
            expected_flags=None,
            force=False,
        )
