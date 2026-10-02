"""Durable v2ctl invocation identity tests for the experiment writer."""

from __future__ import annotations

import json
import hashlib

from comfymodal_runtime.experiment_result_store import (
    build_run_record,
    save_experiment_run,
    write_campaign_manifest,
)
from tools.v2_control.provenance import (
    Provenance,
    read_provenance_sibling,
    write_provenance_sibling,
)


_IDENTITY = {
    "v2ctl_invocation_id": "invocation-e32-001",
    "profile": "production",
    "profile_config_fingerprint": "c" * 64,
    "deploy_fingerprint": "d" * 64,
    "run_fingerprint": "r" * 64,
}


def _build_identity_record(result: dict, generated_at_utc: str) -> dict:
    return build_run_record(
        result,
        v2ctl_invocation_id=_IDENTITY["v2ctl_invocation_id"],
        profile=_IDENTITY["profile"],
        profile_config_fingerprint=_IDENTITY["profile_config_fingerprint"],
        deploy_fingerprint=_IDENTITY["deploy_fingerprint"],
        run_fingerprint=_IDENTITY["run_fingerprint"],
        generated_at_utc=generated_at_utc,
    )


def test_build_run_record_receives_identity_and_request_timestamp() -> None:
    record = _build_identity_record(
        {"request_id": "request-001", "output_sha": "sha-001"},
        "2026-08-20T12:00:00+00:00",
    )

    assert record["v2ctl_invocation_id"] == _IDENTITY["v2ctl_invocation_id"]
    assert record["profile"] == "production"
    assert record["profile_config_fingerprint"] == "c" * 64
    assert record["deploy_fingerprint"] == "d" * 64
    assert record["run_fingerprint"] == "r" * 64
    assert record["request_id"] == "request-001"
    assert record["generated_at_utc"] == "2026-08-20T12:00:00+00:00"


def test_e31_record_uses_forward_events_not_hydration_conversion_count() -> None:
    result = {
        "trace": {
            "events": [
                {"name": "clip_fh_hydration", "metadata": {"conversion_count": 0}},
                {
                    "name": "clip_forward_evidence",
                    "metadata": {
                        "forward_observed": True,
                        "forward_conversion_count": 0,
                        "forward_cast_summary": {"real_conversions": 0},
                    },
                },
                {
                    "name": "clip_fh_cast_once_bind_proof",
                    "metadata": {"ok": True, "generation": 4},
                },
            ]
        }
    }
    record = build_run_record(result)
    assert record["e31_forward_evidence_observed"] is True
    assert record["e31_forward_evidence"]["forward_observed"] is True
    assert record["e31_forward_cast_summary"]["real_conversions"] == 0
    assert record["e31_cast_once_residency_proof"]["generation"] == 4


def test_e31_record_projects_actual_bind_generation() -> None:
    result = {
        "trace": {
            "events": [
                {
                    "name": "clip_fh_cast_once_bind_proof",
                    "metadata": {
                        "ok": True,
                        "generation": 1,
                        "count_by_dtype": {"torch.float32": 398},
                    },
                },
                {
                    "name": "clip_fh_cast_once_applied",
                    "metadata": {"generation": 1, "fp32_params": 398},
                },
                {
                    "name": "clip_fh_cast_once_forward_check",
                    "metadata": {
                        "bind_generation": 1,
                        "post_forward_generation": 1,
                    },
                },
            ]
        }
    }

    record = build_run_record(result)

    assert record["e31_cast_once_residency_proof"]["generation"] == 1
    assert record["e31_cast_once_forward_proof"]["bind_generation"] == 1


def test_build_run_record_reads_reserved_identity_environment(monkeypatch) -> None:
    for key, value in {
        "COMFYMODAL_V2CTL_INVOCATION_ID": "invocation-env-001",
        "COMFYMODAL_V2CTL_PROFILE": "diagnostics",
        "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "p" * 64,
        "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "e" * 64,
        "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "f" * 64,
    }.items():
        monkeypatch.setenv(key, value)

    record = build_run_record(
        {
            "request_id": "request-env-001",
            "generated_at_utc": "2026-08-20T12:01:00+00:00",
        }
    )

    assert record["v2ctl_invocation_id"] == "invocation-env-001"
    assert record["profile"] == "diagnostics"
    assert record["profile_config_fingerprint"] == "p" * 64
    assert record["deploy_fingerprint"] == "e" * 64
    assert record["run_fingerprint"] == "f" * 64
    assert record["request_id"] == "request-env-001"
    assert record["generated_at_utc"] == "2026-08-20T12:01:00+00:00"


def test_save_experiment_run_writes_identity_to_real_json(tmp_path) -> None:
    record = _build_identity_record(
        {"request_id": "request-file-001", "output_sha": "sha-file-001"},
        "2026-08-20T12:02:00+00:00",
    )

    path = save_experiment_run(record, output_dir=tmp_path / "runs")
    assert path.is_file()
    persisted = json.loads(path.read_text(encoding="utf-8"))
    for key, value in _IDENTITY.items():
        assert persisted[key] == value
    assert persisted["request_id"] == "request-file-001"
    assert persisted["generated_at_utc"] == "2026-08-20T12:02:00+00:00"
    assert persisted["artifact_path"] == str(path.resolve())
    assert "artifact_sha256" not in persisted


def test_writer_sidecar_readback_preserves_exact_identity(tmp_path) -> None:
    record = _build_identity_record(
        {"request_id": "request-sidecar-001", "output_sha": "output-sha-001"},
        "2026-08-20T12:02:30+00:00",
    )
    path = save_experiment_run(record, output_dir=tmp_path / "runs")
    persisted = json.loads(path.read_text(encoding="utf-8"))

    provenance = Provenance(
        profile=_IDENTITY["profile"],
        owner="v2-core",
        deploy_fingerprint=_IDENTITY["deploy_fingerprint"],
        run_fingerprint=_IDENTITY["run_fingerprint"],
        git_head="",
        v2ctl_invocation_id=_IDENTITY["v2ctl_invocation_id"],
        profile_config_fingerprint=_IDENTITY["profile_config_fingerprint"],
        request_id=persisted["request_id"],
    )
    write_provenance_sibling(path, provenance)
    restored = read_provenance_sibling(path)

    assert restored is not None
    for key, value in _IDENTITY.items():
        assert persisted[key] == value
        assert getattr(restored, key) == value
    assert persisted["request_id"] == restored.request_id == "request-sidecar-001"
    assert persisted["artifact_path"] == restored.artifact_path == str(path.resolve())
    assert persisted["output_sha"] == "output-sha-001"
    assert "artifact_sha256" not in persisted
    assert restored.artifact_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_campaign_manifest_preserves_invocation_profile_identity(tmp_path) -> None:
    record = _build_identity_record(
        {"request_id": "request-manifest-001"},
        "2026-08-20T12:03:00+00:00",
    )
    manifest_path = write_campaign_manifest([record], output_dir=tmp_path / "campaign")

    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["v2ctl_invocation_id"] == _IDENTITY["v2ctl_invocation_id"]
    assert manifest["v2ctl_invocation_ids"] == [_IDENTITY["v2ctl_invocation_id"]]
    assert manifest["profile"] == "production"
    assert manifest["profile_config_fingerprint"] == "c" * 64
    assert manifest["records"][0]["v2ctl_invocation_id"] == _IDENTITY["v2ctl_invocation_id"]
    assert manifest["records"][0]["profile_config_fingerprint"] == "c" * 64


def test_legacy_input_does_not_fabricate_invocation_id(tmp_path, monkeypatch) -> None:
    for key in (
        "COMFYMODAL_V2CTL_INVOCATION_ID",
        "COMFYMODAL_V2CTL_PROFILE",
        "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT",
        "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT",
        "COMFYMODAL_V2CTL_RUN_FINGERPRINT",
    ):
        monkeypatch.delenv(key, raising=False)

    record = build_run_record({"request_id": "legacy-request"})
    path = save_experiment_run(record, output_dir=tmp_path / "legacy")
    persisted = json.loads(path.read_text(encoding="utf-8"))

    assert record["v2ctl_invocation_id"] == ""
    assert persisted["v2ctl_invocation_id"] == ""
    assert persisted["request_id"] == "legacy-request"
