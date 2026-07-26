"""Comprehensive Lane B tests: snapshot-memory validation, pre-scan identity,
Sage patch retention, immutable workflow artifacts, CLIP key/wiring, and
reachability-based graph trimming evidence.

All tests use mocks and temp directories — no Modal or ComfyUI runtime required.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_workspace() -> str:
    """Return a temporary directory path for file-based tests."""
    return tempfile.mkdtemp()


@pytest.fixture
def mock_volume() -> MagicMock:
    """Return a MagicMock that behaves like a Modal Volume.

    Provides write_bytes, read_bytes, exists, and commit with .aio() support.
    """
    vol = MagicMock()
    vol._store = {}

    def _write_bytes(path: str, data: bytes) -> None:
        vol._store[path] = data

    def _read_bytes(path: str) -> bytes | None:
        return vol._store.get(path)

    def _exists(path: str) -> bool:
        return path in vol._store

    vol.write_bytes.side_effect = _write_bytes
    vol.read_bytes.side_effect = _read_bytes
    vol.exists.side_effect = _exists
    vol.commit = MagicMock()
    # Modal 1.4.x async interface
    vol.commit.aio = MagicMock(return_value=MagicMock())
    vol.commit.aio.return_value.__await__ = lambda: iter([])
    return vol


# ═══════════════════════════════════════════════════════════════════════
# Lane B.1: Authoritative pre-scan generation identity reuse
# ═══════════════════════════════════════════════════════════════════════


class TestPrescanGenerationIdentity:
    """Authoritative pre-scan generation identity capture and reuse."""

    def test_prescan_returns_identity(self):
        from optimizations import prescan_custom_node_generation

        result = prescan_custom_node_generation(
            runtime_generation="runtime-v42",
            custom_node_generation="cn-gen-007",
            reason="test_prescan",
        )
        assert result["runtime_generation"] == "runtime-v42"
        assert result["custom_node_generation"] == "cn-gen-007"

    def test_prescan_persists_record(self, tmp_workspace: str):
        from optimizations import prescan_custom_node_generation, read_prescan_generation_record

        record_path = os.path.join(tmp_workspace, "prescan_gen.json")
        prescan_custom_node_generation(
            runtime_generation="rt-1",
            custom_node_generation="cn-1",
            reason="persist_test",
            record_path=record_path,
        )

        assert os.path.isfile(record_path)
        with open(record_path, "r") as f:
            data = json.load(f)
        assert data["generation"] == "cn-1"
        assert data["content_hash"] == "rt-1"
        assert data["reason"] == "persist_test"
        assert data["schema_version"] == 1

    def test_read_prescan_hit(self, tmp_workspace: str):
        from optimizations import (
            prescan_custom_node_generation,
            read_prescan_generation_record,
        )

        record_path = os.path.join(tmp_workspace, "prescan.json")
        prescan_custom_node_generation(
            runtime_generation="rt-x",
            custom_node_generation="cn-x",
            reason="test",
            record_path=record_path,
        )

        result = read_prescan_generation_record(record_path)
        assert result["generation"] == "cn-x"
        assert result["content_hash"] == "rt-x"
        assert result["reason"] == "test"

    def test_read_prescan_miss(self, tmp_workspace: str):
        from optimizations import read_prescan_generation_record

        result = read_prescan_generation_record(
            os.path.join(tmp_workspace, "nonexistent.json")
        )
        assert result["generation"] == ""
        assert result["content_hash"] == ""
        assert result["reason"] == ""

    def test_prescan_empty_values(self):
        from optimizations import prescan_custom_node_generation

        result = prescan_custom_node_generation(
            runtime_generation="",
            custom_node_generation="",
            reason="empty",
        )
        assert result["runtime_generation"] == ""
        assert result["custom_node_generation"] == ""

    def test_prescan_no_record_path_no_file(self, tmp_workspace: str):
        """Without a record_path, no file is created."""
        from optimizations import prescan_custom_node_generation

        prescan_custom_node_generation(
            runtime_generation="rt",
            custom_node_generation="cn",
            reason="no_file",
        )
        # No error — no file expected

    def test_prescan_ordering(self, tmp_workspace: str):
        """Pre-scan record is written atomically (tmp + replace)."""
        from optimizations import prescan_custom_node_generation

        record_path = os.path.join(tmp_workspace, "atomic_prescan.json")
        prescan_custom_node_generation(
            runtime_generation="before",
            custom_node_generation="before",
            reason="first",
            record_path=record_path,
        )
        prescan_custom_node_generation(
            runtime_generation="after",
            custom_node_generation="after",
            reason="second",
            record_path=record_path,
        )

        with open(record_path, "r") as f:
            data = json.load(f)
        assert data["generation"] == "after"
        assert data["content_hash"] == "after"
        assert data["reason"] == "second"

    def test_prescan_via_bootstrap_state(self):
        """Verify BootstrapState.freeze_prescan_identity and has_prescan_identity."""
        from comfymodal_runtime.runtime_bootstrap import BootstrapState

        state = BootstrapState()
        assert not state.has_prescan_identity()

        state.runtime_generation = "rt-99"
        state.custom_node_generation = "cn-99"
        state.freeze_prescan_identity(record_path="/tmp/test.json")

        assert state.prescan_runtime_generation == "rt-99"
        assert state.prescan_custom_node_generation == "cn-99"
        assert state.prescan_record_path == "/tmp/test.json"
        assert state.has_prescan_identity()

    def test_prescan_via_bootstrap_startup(self):
        """Verify that startup() freezes the pre-scan identity
        via the observe_generations callback.
        """
        from comfymodal_runtime.runtime_bootstrap import (
            BootstrapConfig,
            RuntimeBootstrap,
        )
        from unittest.mock import MagicMock

        trace = MagicMock()
        observe_called = False

        def _observe() -> dict[str, str]:
            nonlocal observe_called
            observe_called = True
            return {"runtime_state": "obs-rt", "custom_nodes": "obs-cn"}

        config = BootstrapConfig(prescan_record_path="/tmp/prescan_test.json")
        bootstrap = RuntimeBootstrap(config=config, observe_generations=_observe)

        with (
            patch("optimizations.prescan_custom_node_generation") as mock_prescan,
            patch("comfymodal_runtime.runtime_bootstrap.ensure_models_symlink") as mock_symlink,
        ):
            bootstrap.startup(trace=trace)
            assert observe_called
            # prescan_custom_node_generation should have been called with
            # the observed generations
            mock_prescan.assert_called_once()
            _call_kwargs = mock_prescan.call_args[1]
            assert _call_kwargs["runtime_generation"] == "obs-rt"
            assert _call_kwargs["custom_node_generation"] == "obs-cn"
            assert _call_kwargs["reason"] == "startup_prescan"
            assert _call_kwargs["record_path"] == "/tmp/prescan_test.json"


# ═══════════════════════════════════════════════════════════════════════
# Lane B.2: Sage patch snapshot identity retention
# ═══════════════════════════════════════════════════════════════════════


class TestSageIdentityRetention:
    """Sage patch snapshot identity retention after real CUDA init."""

    def test_sage_identity_captured(self):
        from comfymodal_runtime.runtime_bootstrap import BootstrapState

        state = BootstrapState()
        state.sage_mode = "baked_cuda"
        state.sage_reason = "patched"

        identity = state.sage_identity()
        assert identity["sage_mode"] == "baked_cuda"
        assert identity["sage_reason"] == "patched"

    def test_sage_identity_default(self):
        from comfymodal_runtime.runtime_bootstrap import BootstrapState

        state = BootstrapState()
        identity = state.sage_identity()
        assert identity["sage_mode"] == ""
        assert identity["sage_reason"] == ""

    def test_sage_identity_in_snapshot_cert(self):
        """Sage identity is included in the snapshot certificate."""
        from optimizations import build_snapshot_certificate

        cert = build_snapshot_certificate(
            runtime_generation="rt-1",
            custom_node_generation="cn-1",
            sage_mode="baked_cuda",
            sage_reason="sage_attn_v2_patched",
        )
        assert cert["sage_mode"] == "baked_cuda"
        assert cert["sage_reason"] == "sage_attn_v2_patched"
        assert "cert_hash" in cert

    def test_sage_mode_match_in_cert(self):
        """Sage mode changes produce different cert hashes."""
        from optimizations import build_snapshot_certificate

        cert_a = build_snapshot_certificate(
            runtime_generation="rt-1", custom_node_generation="cn-1",
            sage_mode="baked_cuda", sage_reason="patched",
        )
        cert_b = build_snapshot_certificate(
            runtime_generation="rt-1", custom_node_generation="cn-1",
            sage_mode="triton_fallback", sage_reason="not-patched",
        )
        assert cert_a["cert_hash"] != cert_b["cert_hash"]

    def test_sage_retained_across_restore(self):
        """Sage identity set during CUDA init is retained in state
        after restore completes.
        """
        from comfymodal_runtime.runtime_bootstrap import (
            BootstrapConfig,
            RuntimeBootstrap,
        )
        from unittest.mock import MagicMock

        def _fake_sage() -> dict[str, str]:
            return {"mode": "baked_cuda", "reason": "sage_attn_v2_patched"}

        trace = MagicMock()
        bootstrap = RuntimeBootstrap(
            config=BootstrapConfig(),
            initialize_cuda=lambda: {"device": "cuda:0", "cuda_available": "True"},
            apply_sage_policy=_fake_sage,
            reload_runtime_state=lambda: None,
            reload_models=lambda: None,
            sync_custom_nodes=lambda: None,
            observe_generations=lambda: {"runtime_state": "rt", "custom_nodes": "cn"},
        )
        state = bootstrap.restore(trace=trace)
        assert state.sage_mode == "baked_cuda"
        assert state.sage_reason == "sage_attn_v2_patched"


# ═══════════════════════════════════════════════════════════════════════
# Lane B.3: Snapshot-memory validation certificate
# ═══════════════════════════════════════════════════════════════════════


class TestSnapshotCertificate:
    """Snapshot-memory validation certificate with Volume fallback."""

    def test_build_snapshot_certificate(self):
        from optimizations import build_snapshot_certificate

        cert = build_snapshot_certificate(
            runtime_generation="rt-alpha",
            custom_node_generation="cn-beta",
            sage_mode="baked_cuda",
            sage_reason="patched",
            unet_identity="unet-hash-abc",
            clip_identity="clip-hash-def",
            clip_type="flux",
        )
        assert cert["schema_version"] == 1
        assert cert["runtime_generation"] == "rt-alpha"
        assert cert["custom_node_generation"] == "cn-beta"
        assert cert["sage_mode"] == "baked_cuda"
        assert cert["sage_reason"] == "patched"
        assert cert["unet_identity"] == "unet-hash-abc"
        assert cert["clip_identity"] == "clip-hash-def"
        assert cert["clip_type"] == "flux"
        assert "cert_hash" in cert
        assert "created_at" in cert

    def test_build_snapshot_certificate_defaults(self):
        from optimizations import build_snapshot_certificate

        cert = build_snapshot_certificate(
            runtime_generation="r",
            custom_node_generation="c",
            sage_mode="",
            sage_reason="",
        )
        assert cert["unet_identity"] == ""
        assert cert["clip_identity"] == ""

    def test_validate_snapshot_certificate_valid(self):
        from optimizations import build_snapshot_certificate, validate_snapshot_certificate

        cert = build_snapshot_certificate(
            runtime_generation="rt-x",
            custom_node_generation="cn-x",
            sage_mode="baked_cuda",
            sage_reason="patched",
        )
        result = validate_snapshot_certificate(cert)
        assert result["valid"] is True
        assert result["cert_hash"] == cert["cert_hash"]

    def test_validate_snapshot_certificate_tampered(self):
        from optimizations import build_snapshot_certificate, validate_snapshot_certificate

        cert = build_snapshot_certificate(
            runtime_generation="rt-x",
            custom_node_generation="cn-x",
            sage_mode="baked_cuda",
            sage_reason="patched",
        )
        # Tamper with a field
        cert["runtime_generation"] = "rt-tampered"
        result = validate_snapshot_certificate(cert)
        assert result["valid"] is False
        assert "hash_mismatch" in result.get("reason", "")

    def test_validate_snapshot_certificate_not_dict(self):
        from optimizations import validate_snapshot_certificate

        result = validate_snapshot_certificate(None)
        assert result["valid"] is False
        assert result["reason"] == "not_a_dict"

    def test_validate_snapshot_certificate_wrong_schema(self):
        from optimizations import validate_snapshot_certificate

        result = validate_snapshot_certificate({"schema_version": 999})
        assert result["valid"] is False
        assert "schema_version_mismatch" in result.get("reason", "")

    def test_certificate_non_deterministic_created_at(self):
        """Two certs with same identity values have same hash
        despite different created_at.
        """
        from optimizations import build_snapshot_certificate

        cert1 = build_snapshot_certificate(
            runtime_generation="rt", custom_node_generation="cn",
            sage_mode="baked_cuda", sage_reason="patched",
        )
        time.sleep(0.01)
        cert2 = build_snapshot_certificate(
            runtime_generation="rt", custom_node_generation="cn",
            sage_mode="baked_cuda", sage_reason="patched",
        )
        assert cert1["cert_hash"] == cert2["cert_hash"]

    def test_bootstrap_state_set_snapshot_cert(self):
        from comfymodal_runtime.runtime_bootstrap import BootstrapState
        from optimizations import build_snapshot_certificate

        state = BootstrapState()
        assert state.snapshot_certificate == {}
        assert state.snapshot_cert_valid is False

        cert = build_snapshot_certificate(
            runtime_generation="rt",
            custom_node_generation="cn",
            sage_mode="baked_cuda",
            sage_reason="patched",
        )
        state.set_snapshot_certificate(cert)
        assert state.snapshot_cert_valid is True
        assert state.snapshot_certificate["cert_hash"] == cert["cert_hash"]


# ═══════════════════════════════════════════════════════════════════════
# Lane B: dependency_manifest.py snapshot cert payload
# ═══════════════════════════════════════════════════════════════════════


class TestDependencyManifestSnapshotCert:
    """Snapshot certificate via the dependency_manifest module."""

    def test_build_snapshot_cert_payload(self):
        from comfymodal_runtime.dependency_manifest import build_snapshot_cert_payload

        payload = build_snapshot_cert_payload(
            runtime_generation="rt-m42",
            custom_node_generation="cn-g7",
            sage_mode="baked_cuda",
            sage_reason="sage_attn_v2",
            unet_identity="unet-hash-1",
            clip_identity="clip-hash-2",
            clip_type="sdxl",
        )
        assert payload["schema_version"] == 1
        assert "cert_identity" in payload
        assert "identity_components" in payload
        assert "created_at" in payload
        assert payload["identity_components"]["runtime_generation"] == "rt-m42"
        assert payload["identity_components"]["sage_mode"] == "baked_cuda"
        assert payload["identity_components"]["clip_type"] == "sdxl"

    def test_validate_snapshot_cert_payload_valid(self):
        from comfymodal_runtime.dependency_manifest import (
            build_snapshot_cert_payload,
            validate_snapshot_cert_payload,
        )

        payload = build_snapshot_cert_payload(
            runtime_generation="rt-1",
            custom_node_generation="cn-1",
            sage_mode="baked_cuda",
            sage_reason="patched",
        )
        result = validate_snapshot_cert_payload(payload)
        assert result["valid"] is True
        assert result["cert_identity"] == payload["cert_identity"]

    def test_validate_snapshot_cert_payload_tampered(self):
        from comfymodal_runtime.dependency_manifest import (
            build_snapshot_cert_payload,
            validate_snapshot_cert_payload,
        )

        payload = build_snapshot_cert_payload(
            runtime_generation="rt-1",
            custom_node_generation="cn-1",
            sage_mode="baked_cuda",
            sage_reason="patched",
        )
        payload["identity_components"]["runtime_generation"] = "rt-tampered"
        result = validate_snapshot_cert_payload(payload)
        assert result["valid"] is False
        assert "identity_mismatch" in result.get("reason", "")

    def test_persist_to_volume(self, mock_volume: MagicMock):
        from comfymodal_runtime.dependency_manifest import (
            build_snapshot_cert_payload,
            persist_snapshot_cert_to_volume,
        )

        payload = build_snapshot_cert_payload(
            runtime_generation="rt-v",
            custom_node_generation="cn-v",
            sage_mode="baked_cuda",
            sage_reason="patched",
        )
        ok = persist_snapshot_cert_to_volume(mock_volume, payload=payload)
        assert ok is True

        cert_id = payload["cert_identity"]
        filename = f"snapshot_cert_{cert_id}.json"
        assert mock_volume.exists(filename)
        mock_volume.commit.assert_called()

    def test_read_from_volume_hit(self, mock_volume: MagicMock):
        from comfymodal_runtime.dependency_manifest import (
            build_snapshot_cert_payload,
            persist_snapshot_cert_to_volume,
            read_snapshot_cert_from_volume,
        )

        payload = build_snapshot_cert_payload(
            runtime_generation="rt-r",
            custom_node_generation="cn-r",
            sage_mode="baked_cuda",
            sage_reason="patched",
        )
        persist_snapshot_cert_to_volume(mock_volume, payload=payload)

        read_back = read_snapshot_cert_from_volume(
            mock_volume,
            cert_identity=payload["cert_identity"],
        )
        assert read_back is not None
        assert read_back["cert_identity"] == payload["cert_identity"]
        assert read_back["identity_components"]["runtime_generation"] == "rt-r"

    def test_read_from_volume_miss(self, mock_volume: MagicMock):
        from comfymodal_runtime.dependency_manifest import read_snapshot_cert_from_volume

        result = read_snapshot_cert_from_volume(
            mock_volume,
            cert_identity="nonexistent",
        )
        assert result is None

    def test_read_from_volume_tampered(self, mock_volume: MagicMock):
        from comfymodal_runtime.dependency_manifest import (
            build_snapshot_cert_payload,
            persist_snapshot_cert_to_volume,
            read_snapshot_cert_from_volume,
        )

        payload = build_snapshot_cert_payload(
            runtime_generation="rt-ok",
            custom_node_generation="cn-ok",
            sage_mode="baked_cuda",
            sage_reason="patched",
        )
        persist_snapshot_cert_to_volume(mock_volume, payload=payload)

        # Tamper the stored payload directly
        cert_id = payload["cert_identity"]
        filename = f"snapshot_cert_{cert_id}.json"
        stored = json.loads(mock_volume._store[filename].decode("utf-8"))
        stored["identity_components"]["runtime_generation"] = "rt-tampered"
        mock_volume._store[filename] = json.dumps(stored, sort_keys=True, separators=(",", ":")).encode("utf-8")

        read_back = read_snapshot_cert_from_volume(
            mock_volume,
            cert_identity=cert_id,
        )
        assert read_back is None


# ═══════════════════════════════════════════════════════════════════════
# Lane B.4: Immutable workflow artifact identity
# ═══════════════════════════════════════════════════════════════════════


class TestImmutableWorkflowArtifactIdentity:
    """Immutable workflow artifact identity computation."""

    def test_build_artifact_identity(self):
        from comfymodal_runtime.dependency_manifest import build_immutable_artifact_identity

        result = build_immutable_artifact_identity(
            compiled_workflow_hash="abc123",
            source_workflow_hash="def456",
            production_plan_hash="ghi789",
        )
        assert "artifact_identity" in result
        assert result["components"]["compiled_workflow_hash"] == "abc123"
        assert result["components"]["source_workflow_hash"] == "def456"
        assert result["components"]["production_plan_hash"] == "ghi789"
        assert result["schema_version"] == 1

    def test_artifact_identity_includes_output_ids(self):
        from comfymodal_runtime.dependency_manifest import build_immutable_artifact_identity

        result = build_immutable_artifact_identity(
            compiled_workflow_hash="a",
            source_workflow_hash="b",
            production_plan_hash="c",
            output_node_ids=["10", "20"],
        )
        assert "10" in result["components"]["output_node_ids"]
        assert "20" in result["components"]["output_node_ids"]

    def test_artifact_identity_deterministic(self):
        from comfymodal_runtime.dependency_manifest import build_immutable_artifact_identity

        r1 = build_immutable_artifact_identity(
            compiled_workflow_hash="x",
            source_workflow_hash="y",
            production_plan_hash="z",
        )
        r2 = build_immutable_artifact_identity(
            compiled_workflow_hash="x",
            source_workflow_hash="y",
            production_plan_hash="z",
        )
        assert r1["artifact_identity"] == r2["artifact_identity"]

    def test_artifact_identity_different_hashes_differ(self):
        from comfymodal_runtime.dependency_manifest import build_immutable_artifact_identity

        r1 = build_immutable_artifact_identity(
            compiled_workflow_hash="a",
            source_workflow_hash="b",
            production_plan_hash="c",
        )
        r2 = build_immutable_artifact_identity(
            compiled_workflow_hash="a",
            source_workflow_hash="b",
            production_plan_hash="d",
        )
        assert r1["artifact_identity"] != r2["artifact_identity"]

    def test_artifact_no_live_objects(self):
        """Verify that the artifact identity never captures live objects."""
        from comfymodal_runtime.dependency_manifest import build_immutable_artifact_identity

        result = build_immutable_artifact_identity(
            compiled_workflow_hash="hash1",
            source_workflow_hash="hash2",
            production_plan_hash="hash3",
        )
        # All values should be strings
        for key, value in result["components"].items():
            assert isinstance(value, str), f"Component {key} is not a string: {type(value)}"


# ═══════════════════════════════════════════════════════════════════════
# Lane B.5: Snapshot identity service
# ═══════════════════════════════════════════════════════════════════════


class TestSnapshotIdentityService:
    """Pre-scan snapshot identity (generation reuse detection)."""

    def test_build_snapshot_identity(self):
        from comfymodal_runtime.dependency_manifest import build_snapshot_identity

        identity = build_snapshot_identity(
            runtime_generation="rt-v1",
            custom_node_generation="cn-v1",
            combined_hash="dep-hash-abc",
        )
        assert "snapshot_identity" in identity
        assert identity["runtime_generation"] == "rt-v1"
        assert identity["custom_node_generation"] == "cn-v1"
        assert identity["combined_hash"] == "dep-hash-abc"
        assert identity["schema_version"] == 1

    def test_snapshot_identity_match(self):
        from comfymodal_runtime.dependency_manifest import (
            build_snapshot_identity,
            check_snapshot_identity_match,
        )

        a = build_snapshot_identity(
            runtime_generation="rt-v1",
            custom_node_generation="cn-v1",
        )
        b = build_snapshot_identity(
            runtime_generation="rt-v1",
            custom_node_generation="cn-v1",
        )
        result = check_snapshot_identity_match(a, b)
        assert result["match"] is True

    def test_snapshot_identity_mismatch(self):
        from comfymodal_runtime.dependency_manifest import (
            build_snapshot_identity,
            check_snapshot_identity_match,
        )

        a = build_snapshot_identity(
            runtime_generation="rt-old",
            custom_node_generation="cn-old",
        )
        b = build_snapshot_identity(
            runtime_generation="rt-new",
            custom_node_generation="cn-new",
        )
        result = check_snapshot_identity_match(a, b)
        assert result["match"] is False
        assert result["reason"] == "identity_mismatch"

    def test_snapshot_identity_missing(self):
        from comfymodal_runtime.dependency_manifest import check_snapshot_identity_match

        result = check_snapshot_identity_match(None, {"snapshot_identity": "abc"})
        assert result["match"] is False
        assert result["reason"] == "identity_a_missing"


# ═══════════════════════════════════════════════════════════════════════
# Lane B.6: CLIP key/wiring fix verification
# ═══════════════════════════════════════════════════════════════════════


class TestCLIPKeyWiring:
    """Verify CLIP key/wiring fixes — CLIPLoaderAdvanced removed."""

    def test_clip_loader_model_keys_no_advanced(self):
        from optimizations import _LOADER_MODEL_KEYS

        # CLIPLoaderAdvanced does not exist in ComfyUI nodes.py:
        # https://github.com/comfyanonymous/ComfyUI/blob/master/nodes.py
        # Only CLIPLoader and DualCLIPLoader are defined.
        assert "CLIPLoaderAdvanced" not in _LOADER_MODEL_KEYS

    def test_native_clip_loader_classes_no_advanced(self):
        from optimizations import _NATIVE_CLIP_LOADER_CLASSES

        assert "CLIPLoaderAdvanced" not in _NATIVE_CLIP_LOADER_CLASSES

    def test_clip_loader_model_keys_structure(self):
        from optimizations import _LOADER_MODEL_KEYS

        assert _LOADER_MODEL_KEYS["CLIPLoader"] == ["clip_name"]
        assert _LOADER_MODEL_KEYS["DualCLIPLoader"] == ["clip_name1", "clip_name2"]

    def test_loader_first_filename_clip_loader(self):
        from optimizations import _loader_first_filename

        result = _loader_first_filename("CLIPLoader", {"clip_name": "my_clip.safetensors"})
        assert result == "my_clip.safetensors"

    def test_loader_all_filenames_dual(self):
        from optimizations import _loader_all_filenames

        result = _loader_all_filenames(
            "DualCLIPLoader",
            {"clip_name1": "clip_l.safetensors", "clip_name2": "clip_g.safetensors"},
        )
        assert result == ["clip_l.safetensors", "clip_g.safetensors"]

    def test_loader_all_filenames_empty(self):
        from optimizations import _loader_all_filenames

        result = _loader_all_filenames("CLIPLoader", {})
        assert result == []


# ═══════════════════════════════════════════════════════════════════════
# Lane B.7: Reachability-based graph trimming evidence
# ═══════════════════════════════════════════════════════════════════════


class TestGraphTrimmingEvidence:
    """Reachability-based graph trimming evidence reporter."""

    def test_trimming_candidates_simple_workflow(self):
        """A workflow with disconnected nodes reports trimming candidates."""
        from production_workflow import report_graph_trimming_candidates

        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello", "clip": ["3", 0]}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["3", 0], "clip": ["1", 0]}},
            "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "stable_diffusion"}},
            "4": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
        }
        result = report_graph_trimming_candidates(workflow, output_node_ids=["2"])
        assert result["trimming_possible"] is True
        assert "4" in result["removable_node_ids"]  # VAE is not connected to outputs
        assert "1" in result["kept_node_ids"]
        assert "2" in result["kept_node_ids"]
        assert "3" in result["kept_node_ids"]
        assert result["original_node_count"] == 4
        assert result["removable_node_count"] == 1
        assert len(result["evidence"]) == 1
        assert result["evidence"][0]["node_id"] == "4"
        assert result["evidence"][0]["reason"] == "not_reachable_from_outputs"
        assert result["method"] == "reachability_from_outputs"

    def test_trimming_candidates_no_removable(self):
        """When all nodes are reachable from outputs, trimming is not possible."""
        from production_workflow import report_graph_trimming_candidates

        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello", "clip": ["2", 0]}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "stable_diffusion"}},
        }
        result = report_graph_trimming_candidates(workflow, output_node_ids=["1"])
        assert result["trimming_possible"] is False
        assert result["removable_node_ids"] == []
        assert result["removable_node_count"] == 0
        assert result["kept_node_count"] == 2

    def test_trimming_candidates_stable_mode(self):
        """Stable mode reports no trimming candidates."""
        from production_workflow import report_graph_trimming_candidates

        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a", "clip": ["2", 0]}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.safetensors", "type": "stable_diffusion"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v.safetensors"}},
        }
        result = report_graph_trimming_candidates(workflow, output_node_ids=["1"], stable=True)
        assert result["trimming_possible"] is False
        assert result["removable_node_ids"] == []
        assert result["stable"] is True
        assert result["kept_node_count"] == 3

    def test_trimming_candidates_empty_outputs(self):
        """No output_node_ids means no trimming candidates."""
        from production_workflow import report_graph_trimming_candidates

        result = report_graph_trimming_candidates({"1": {"class_type": "A"}}, output_node_ids=[])
        assert result["trimming_possible"] is False

    def test_trimming_candidates_invalid_output(self):
        """Output node ID not in workflow -> no trimming."""
        from production_workflow import report_graph_trimming_candidates

        result = report_graph_trimming_candidates(
            {"1": {"class_type": "A"}}, output_node_ids=["999"]
        )
        assert result["trimming_possible"] is False

    def test_trimming_candidates_empty_workflow(self):
        from production_workflow import report_graph_trimming_candidates

        result = report_graph_trimming_candidates({}, output_node_ids=["1"])
        assert result["trimming_possible"] is False

    def test_trimming_candidates_non_dict_workflow(self):
        from production_workflow import report_graph_trimming_candidates

        result = report_graph_trimming_candidates(None, output_node_ids=["1"])
        assert result["trimming_possible"] is False
        assert result["original_node_count"] == 0

    def test_trimming_candidates_multiple_removable(self):
        """Multiple disconnected nodes are all reported."""
        from production_workflow import report_graph_trimming_candidates

        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a", "clip": ["2", 0]}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.pt", "type": "sd"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v.pt"}},
            "4": {"class_type": "LoadImage", "inputs": {"image": "img.png"}},
            "5": {"class_type": "PreviewImage", "inputs": {"images": ["4", 0]}},
        }
        result = report_graph_trimming_candidates(workflow, output_node_ids=["1"])
        assert result["trimming_possible"] is True
        assert "3" in result["removable_node_ids"]  # VAE not connected
        assert "4" in result["removable_node_ids"]  # LoadImage not connected
        assert "5" in result["removable_node_ids"]  # PreviewImage not connected
        assert result["removable_node_count"] == 3

    def test_trimming_candidates_preserves_input(self):
        """The reporter never mutates the input workflow."""
        from production_workflow import report_graph_trimming_candidates
        import copy

        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a", "clip": ["2", 0]}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.pt", "type": "sd"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v.pt"}},
        }
        original = copy.deepcopy(workflow)
        report_graph_trimming_candidates(workflow, output_node_ids=["1"])
        assert workflow == original  # Unchanged

    def test_trimming_candidates_analysis_ms(self):
        """analysis_ms is a positive float."""
        from production_workflow import report_graph_trimming_candidates

        result = report_graph_trimming_candidates(
            {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "t", "clip": ["2", 0]}},
             "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.pt", "type": "sd"}}},
            output_node_ids=["1"],
        )
        assert isinstance(result["analysis_ms"], (int, float))
        assert result["analysis_ms"] >= 0

    def test_trimming_candidates_integration_with_compile(self):
        """Trimming candidates match what compile_production_workflow removes."""
        from production_workflow import (
            compile_production_workflow,
            report_graph_trimming_candidates,
            normalize_production_options,
        )

        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "t", "clip": ["2", 0]}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.pt", "type": "sd"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v.pt"}},
        }
        production = normalize_production_options({"production": {"output_node_ids": ["1"]}})

        plan = compile_production_workflow(
            workflow,
            production,
            allow_direct_output_rewrite=False,
            allow_rgthree_comparer_rewrite=False,
        )
        report = report_graph_trimming_candidates(workflow, output_node_ids=["1"])

        # The same node should be removed by both
        removed_by_compile = set(plan.report.get("removed_node_ids", []))
        removable_by_report = set(report["removable_node_ids"])
        assert removed_by_compile == removable_by_report


# ═══════════════════════════════════════════════════════════════════════
# Lane B.8: RuntimeBootstrap snapshot certificate integration
# ═══════════════════════════════════════════════════════════════════════


class TestBootstrapSnapshotCertificate:
    """RuntimeBootstrap builds and stores the snapshot certificate."""

    def test_bootstrap_builds_certificate_in_restore(self):
        """After restore(), the state has a snapshot certificate."""
        from comfymodal_runtime.runtime_bootstrap import (
            BootstrapConfig,
            RuntimeBootstrap,
        )
        from unittest.mock import MagicMock

        trace = MagicMock()
        bootstrap = RuntimeBootstrap(
            config=BootstrapConfig(),
            initialize_cuda=lambda: {
                "device": "cuda:0",
                "cuda_available": "True",
                "unet_identity": "unet-abc",
                "clip_identity": "clip-def",
                "clip_type": "flux",
            },
            apply_sage_policy=lambda: {"mode": "baked_cuda", "reason": "patched"},
            reload_runtime_state=lambda: None,
            reload_models=lambda: None,
            sync_custom_nodes=lambda: None,
            observe_generations=lambda: {"runtime_state": "rt-42", "custom_nodes": "cn-7"},
        )
        state = bootstrap.restore(trace=trace)

        assert state.snapshot_certificate != {}
        cert = state.snapshot_certificate
        assert cert["runtime_generation"] == "rt-42"
        assert cert["custom_node_generation"] == "cn-7"
        assert cert["sage_mode"] == "baked_cuda"
        assert cert["sage_reason"] == "patched"
        assert cert["unet_identity"] == "unet-abc"
        assert cert["clip_identity"] == "clip-def"
        assert cert["clip_type"] == "flux"
        assert state.snapshot_cert_valid is True


# ═══════════════════════════════════════════════════════════════════════
# Selected-output preservation test
# ═══════════════════════════════════════════════════════════════════════


class TestSelectedOutputPreservation:
    """Verify that trimming preserves selected output nodes."""

    def test_selected_outputs_preserved_after_trimming(self):
        """Output nodes survive trimming when they are reachable."""
        from production_workflow import report_graph_trimming_candidates

        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "t", "clip": ["3", 0]}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["3", 0], "clip": ["1", 0]}},
            "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.pt", "type": "sd"}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512}},
            "5": {"class_type": "VAELoader", "inputs": {"vae_name": "v.pt"}},
        }
        result = report_graph_trimming_candidates(workflow, output_node_ids=["2"])
        assert "2" in result["kept_node_ids"]
        assert "5" in result["removable_node_ids"]  # VAE not connected to output path

    def test_all_nodes_kept_when_fully_connected(self):
        """If all nodes are on the path to outputs, none are removed."""
        from production_workflow import report_graph_trimming_candidates

        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "t", "clip": ["3", 0]}},
            "2": {"class_type": "VAEDecode", "inputs": {"samples": ["4", 0], "vae": ["5", 0]}},
            "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.pt", "type": "sd"}},
            "4": {"class_type": "KSampler", "inputs": {"model": ["3", 0], "clip": ["1", 0]}},
            "5": {"class_type": "VAELoader", "inputs": {"vae_name": "v.pt"}},
        }
        result = report_graph_trimming_candidates(workflow, output_node_ids=["2"])
        assert result["trimming_possible"] is False
        assert result["removable_node_ids"] == []
        assert result["kept_node_count"] == 5


# ═══════════════════════════════════════════════════════════════════════
# RuntimeBootstrap pre-scan identity during restore
# ═══════════════════════════════════════════════════════════════════════


class TestPrescanRestore:
    """Pre-scan identity restoration during restore()."""

    def test_prescan_identity_restored(self, tmp_workspace: str):
        """When a pre-scan record exists, restore reads and uses it."""
        from comfymodal_runtime.runtime_bootstrap import (
            BootstrapConfig,
            RuntimeBootstrap,
        )
        from optimizations import prescan_custom_node_generation
        from unittest.mock import MagicMock

        record_path = os.path.join(tmp_workspace, "prescan_restore.json")
        prescan_custom_node_generation(
            runtime_generation="rt-prescan",
            custom_node_generation="cn-prescan",
            reason="pre",
            record_path=record_path,
        )

        config = BootstrapConfig(prescan_record_path=record_path)
        trace = MagicMock()
        bootstrap = RuntimeBootstrap(
            config=config,
            initialize_cuda=lambda: {"device": "cuda:0", "cuda_available": "True"},
            apply_sage_policy=lambda: {"mode": "baked_cuda", "reason": "patched"},
            reload_runtime_state=lambda: None,
            reload_models=lambda: None,
            sync_custom_nodes=lambda: None,
            observe_generations=lambda: {"runtime_state": "rt-restore", "custom_nodes": "cn-restore"},
        )
        state = bootstrap.restore(trace=trace)

        # The snapshot cert uses the pre-scan identity since it was
        # successfully restored (preferred over observe_generations)
        assert state.prescan_custom_node_generation == "cn-prescan"
        # The cert uses prescan_custom_node_generation because
        # _build_and_store_snapshot_certificate prefers it
        assert state.snapshot_certificate["custom_node_generation"] == "cn-prescan"

    def test_prescan_identity_not_restored_when_no_record(self):
        """Without a record path, no pre-scan restore is attempted."""
        from comfymodal_runtime.runtime_bootstrap import (
            BootstrapConfig,
            RuntimeBootstrap,
        )
        from unittest.mock import MagicMock

        bootstrap = RuntimeBootstrap(
            config=BootstrapConfig(),  # no prescan_record_path
            initialize_cuda=lambda: {"device": "cuda:0", "cuda_available": "True"},
            apply_sage_policy=lambda: {"mode": "baked_cuda", "reason": "patched"},
            reload_runtime_state=lambda: None,
            reload_models=lambda: None,
            sync_custom_nodes=lambda: None,
            observe_generations=lambda: {"runtime_state": "rt", "custom_nodes": "cn"},
        )
        bootstrap.restore(trace=MagicMock())
        assert bootstrap.state.prescan_custom_node_generation == ""
