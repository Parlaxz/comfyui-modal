"""Tests for tools/v2_control/provenance.py (design section 13).

Covers contract section 21 provenance coverage: to_json/from_dict round-trip,
fingerprint_line format, redacted environment (never contains secrets),
build_provenance wiring, and the deferred hook doc.

The provenance *sibling* -- a sidecar written next to an artifact to attest to
it -- has been deleted. Identity lives in the canonical run record instead, so
there is no second local file whose purpose is to prove another.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from tools.v2_control.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    Provenance,
    build_provenance,
    inject_provenance_hook_doc,
)

from tests.v2ctl_fakes import FakeConfig, FakeFlag
from tools.v2_control.runtime_overrides import RuntimeOverride


def make_provenance() -> Provenance:
    return Provenance(
        profile="production",
        owner="v2-core",
        deploy_fingerprint="abcd1234" * 8,
        run_fingerprint="ef567890" * 8,
        git_head="0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997",
        target={"app": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypointV2", "method": "run_plan_stream"},
        resources={"gpu": "rtx-pro-6000", "cpu": 12, "memory_mb": 8192},
        requested_environment={"PATH": "/usr/bin", "COMFYMODAL_V2_ENV_PROFILE": "production"},
        effective_environment={"PATH": "/usr/bin", "COMFYMODAL_V2_ENV_PROFILE": "production"},
        flag_sources={"COMFYMODAL_V2_UNET_FASTSAFETENSORS": "profile:production"},
        unregistered_flags=["COMFYMODAL_V2_NEW_EXPERIMENT"],
        runtime_overrides=[{"name": "COMFYMODAL_V2_BENCHMARK", "value": "1", "source": "local_staging"}],
        workload={"fresh_required": True, "run_count": 10, "gap_seconds": 35.0},
    )


class TestSerialization:
    def test_to_dict_shape(self):
        data = make_provenance().to_dict()
        assert data["schema_version"] == PROVENANCE_SCHEMA_VERSION
        assert data["profile"] == "production"
        assert data["resources"]["memory_mb"] == 8192
        assert data["deploy_fingerprint"] == "abcd1234" * 8
        assert data["unregistered_flags"] == ["COMFYMODAL_V2_NEW_EXPERIMENT"]

    def test_round_trip_to_json_from_dict(self):
        original = make_provenance()
        restored = Provenance.from_dict(json.loads(original.to_json()))
        assert restored == original
        assert restored.profile == original.profile
        assert restored.deploy_fingerprint == original.deploy_fingerprint

    def test_to_json_compact_sorted(self):
        text = make_provenance().to_json()
        assert ", " not in text
        assert '"schema_version":1' in text

    def test_from_dict_tolerates_missing_keys(self):
        restored = Provenance.from_dict({"profile": "production"})
        assert restored.profile == "production"
        assert restored.target == {}
        assert restored.unregistered_flags == []


class TestFingerprintLine:
    def test_fingerprint_line_format(self):
        line = make_provenance().fingerprint_line()
        assert line.startswith("[v2ctl.config] deploy=")
        assert "deploy=abcd1234 run=ef567890 profile=production" in line
        # exactly 8-char prefixes
        assert line == "[v2ctl.config] deploy=abcd1234 run=ef567890 profile=production"

    def test_fingerprint_line_short_fps(self):
        provenance = Provenance(
            profile="e29-tracer",
            deploy_fingerprint="abc",
            run_fingerprint="def",
            owner="",
            git_head="",
        )
        assert provenance.fingerprint_line() == "[v2ctl.config] deploy=abc run=def profile=e29-tracer"



class TestBuildProvenance:
    def test_build_from_config(self):
        config = FakeConfig()
        config.flags = [
            FakeFlag(name="COMFYMODAL_V2_UNET_FASTSAFETENSORS", value="0", source="profile:production"),
            FakeFlag(name="COMFYMODAL_V2_GAP_SECONDS", value="35.0", source="cli"),
        ]
        config.unregistered = [FakeFlag(name="COMFYMODAL_V2_NEW_EXPERIMENT", value="1", source="cli")]
        env = {
            "PATH": "/usr/bin",
            "COMFYMODAL_V2_ENV_PROFILE": "production",
            "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
        }
        overrides = [RuntimeOverride(name="COMFYMODAL_V2_BENCHMARK", value="1", source="local_staging")]
        provenance = build_provenance(config, env, "d" * 64, "r" * 64, overrides)
        assert provenance.profile == "production"
        assert provenance.owner == "v2-core"
        assert provenance.deploy_fingerprint == "d" * 64
        assert provenance.run_fingerprint == "r" * 64
        assert provenance.git_head == config.git.head
        assert provenance.flag_sources["COMFYMODAL_V2_UNET_FASTSAFETENSORS"] == "profile:production"
        assert provenance.unregistered_flags == ["COMFYMODAL_V2_NEW_EXPERIMENT"]
        assert provenance.runtime_overrides == [
            {"name": "COMFYMODAL_V2_BENCHMARK", "value": "1", "source": "local_staging"}
        ]
        assert provenance.workload["fresh_required"] is True

    def test_redacted_env_never_contains_secrets(self):
        config = FakeConfig()
        env = {
            "MODAL_TOKEN_ID": "tok-123",
            "MODAL_TOKEN_SECRET": "super-secret",
            "V2CTL_DEPLOY_FINGERPRINT": "d" * 64,
            "COMFYMODAL_V2_ENV_PROFILE": "production",
            "SAFE_VAR": "1",
        }
        provenance = build_provenance(config, env, "d" * 64, "r" * 64, [])
        blob = provenance.to_json()
        assert "super-secret" not in blob
        assert "tok-123" not in blob
        for key, value in provenance.requested_environment.items():
            if any(m in key.upper() for m in ("TOKEN", "SECRET", "AUTH", "FINGERPRINT")):
                assert value == "<redacted>", key
        assert provenance.requested_environment["SAFE_VAR"] == "1"


class TestHookDoc:
    def test_hook_doc_nonempty_and_mentions_fingerprint_line(self):
        snippet = inject_provenance_hook_doc()
        assert snippet.strip()
        assert "[v2ctl.config]" in snippet
        assert "V2CTL_DEPLOY_FINGERPRINT" in snippet
        assert "V2CTL_RUN_FINGERPRINT" in snippet
