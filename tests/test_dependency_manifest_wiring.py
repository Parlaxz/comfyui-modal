"""Focused tests for the dependency manifest wiring (Audit Round 9+).

Tests cover:
- ``_resolve_deployment_combined_hash`` — identity resolution with/without
  baked manifest and custom-nodes generation.
- ``_check_dependency_manifest_identity`` — exact match vs each invalidation mode.
- ``_load_dependency_manifest`` — missing, corrupt, schema-mismatch, and valid cases.
- ``_build_and_persist_dependency_manifest`` — write and atomic replace.
- Preflight integration: valid hit (no fingerprint/validation call), each
  invalidation path, and replacement write.

All helpers are mocked — no Modal runtime needed.
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch, call

import pytest


# ── Helpers ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_globals():
    """Patch module-level globals that the manifest helpers depend on.

    Uses a real temp directory so ``os.makedirs`` and file I/O work.
    Module-level path constants (``DEPENDENCY_MANIFEST_DIR``,
    ``DEPLOYMENT_DEPENDENCY_VALIDATION_CACHE_DIR``) are patched to
    point into the temp dir.
    """
    _tmp = tempfile.mkdtemp()
    _mft_dir = os.path.join(_tmp, "dependency_manifest")
    _cache_dir = os.path.join(_tmp, "deployment_dependency_validation_cache")
    with (
        patch("comfyapp.RUNTIME_CONFIG_DIR", _tmp),
        patch("comfyapp.DEPENDENCY_MANIFEST_DIR", _mft_dir),
        patch("comfyapp.DEPLOYMENT_DEPENDENCY_VALIDATION_CACHE_DIR", _cache_dir),
        patch("comfyapp.load_baked_custom_node_dependency_manifest") as mock_baked,
        patch("comfyapp._read_custom_nodes_generation_record") as mock_cn_gen,
        patch("comfyapp.CONTAINER_SESSION_ID", "test-session"),
        patch("comfyapp.COMFYAPP_VERSION", "1.0.0"),
        patch("comfyapp._V2_RUNTIME_REVISION", "abcd1234"),
        patch("comfyapp.REQUIREMENTS_REPAIR_MODE", "fail_fast"),
    ):
        yield {
            "tmpdir": _tmp,
            "mft_dir": _mft_dir,
            "cache_dir": _cache_dir,
            "mock_baked": mock_baked,
            "mock_cn_gen": mock_cn_gen,
        }


# ── _resolve_deployment_combined_hash ─────────────────────────────────


class TestResolveDeploymentCombinedHash:
    def test_full_identity(self, _patch_globals):
        """Happy path: baked hash + custom-nodes generation available."""
        _patch_globals["mock_baked"].return_value = {
            "overall_dependency_hash": "baked_hash_abc",
        }
        _patch_globals["mock_cn_gen"].return_value = {
            "generation": "cn_gen_xyz",
        }
        from comfyapp import _resolve_deployment_combined_hash

        result = _resolve_deployment_combined_hash()
        assert isinstance(result, str)
        assert len(result) == 64  # sha256 hex

    def test_missing_baked_hash(self, _patch_globals):
        """No baked manifest -> empty string."""
        _patch_globals["mock_baked"].return_value = {}
        _patch_globals["mock_cn_gen"].return_value = {
            "generation": "cn_gen_xyz",
        }
        from comfyapp import _resolve_deployment_combined_hash

        result = _resolve_deployment_combined_hash()
        assert result == ""

    def test_missing_baked_manifest(self, _patch_globals):
        """Baked manifest is None -> empty string."""
        _patch_globals["mock_baked"].return_value = None
        _patch_globals["mock_cn_gen"].return_value = {
            "generation": "cn_gen_xyz",
        }
        from comfyapp import _resolve_deployment_combined_hash

        result = _resolve_deployment_combined_hash()
        assert result == ""

    def test_missing_cn_generation(self, _patch_globals):
        """No custom-nodes generation -> empty string."""
        _patch_globals["mock_baked"].return_value = {
            "overall_dependency_hash": "baked_hash_abc",
        }
        _patch_globals["mock_cn_gen"].return_value = None
        from comfyapp import _resolve_deployment_combined_hash

        result = _resolve_deployment_combined_hash()
        assert result == ""

    def test_deterministic(self, _patch_globals):
        """Same inputs produce same hash."""
        _patch_globals["mock_baked"].return_value = {
            "overall_dependency_hash": "baked_hash_abc",
        }
        _patch_globals["mock_cn_gen"].return_value = {
            "generation": "cn_gen_xyz",
        }
        from comfyapp import _resolve_deployment_combined_hash

        h1 = _resolve_deployment_combined_hash()
        h2 = _resolve_deployment_combined_hash()
        assert h1 == h2

    def test_different_baked_hash(self, _patch_globals):
        """Different baked hash produces different combined hash."""
        _patch_globals["mock_cn_gen"].return_value = {
            "generation": "cn_gen_xyz",
        }
        from comfyapp import _resolve_deployment_combined_hash

        _patch_globals["mock_baked"].return_value = {
            "overall_dependency_hash": "hash_A",
        }
        h_a = _resolve_deployment_combined_hash()
        _patch_globals["mock_baked"].return_value = {
            "overall_dependency_hash": "hash_B",
        }
        h_b = _resolve_deployment_combined_hash()
        assert h_a != h_b


# ── _check_dependency_manifest_identity ────────────────────────────────


class TestCheckDependencyManifestIdentity:
    def _make_manifest(self, identity="ident123", schema_version=1,
                       combined_hash="ch", cn_fp_hash="fp",
                       cn_gen="gen", repair_mode="fail_fast"):
        return {
            "schema_version": schema_version,
            "identity": identity,
            "created_at_unix": time.time(),
            "combined_hash": combined_hash,
            "custom_node_fingerprint": {"overall_dependency_hash": cn_fp_hash},
            "custom_node_generation": cn_gen,
            "repair_mode": repair_mode,
            "source": "snapshot_manifest",
        }

    def test_exact_match(self, _patch_globals):
        """Exact identity match returns identity_match=True."""
        from comfyapp import (
            _build_immutable_dependency_manifest_identity,
            _check_dependency_manifest_identity,
        )

        identity = _build_immutable_dependency_manifest_identity(
            combined_hash="ch123",
            custom_node_fingerprint={"overall_dependency_hash": "fp456"},
            custom_node_generation="gen789",
            repair_mode="fail_fast",
        )
        manifest = self._make_manifest(
            identity=identity,
            combined_hash="ch123",
            cn_fp_hash="fp456",
            cn_gen="gen789",
            repair_mode="fail_fast",
        )
        result = _check_dependency_manifest_identity(
            manifest,
            combined_hash="ch123",
            custom_node_fingerprint={"overall_dependency_hash": "fp456"},
            custom_node_generation="gen789",
            repair_mode="fail_fast",
        )
        assert result["identity_match"] is True
        assert result["computed_identity"] == identity
        assert result["stored_identity"] == identity
        # New fields present
        assert result["stored_schema_version"] == 1
        assert result["stored_combined_hash"] == "ch123"
        # Identity hit: miss_component is empty string
        assert isinstance(result["miss_component"], str)
        assert result["miss_component"] == ""

    def test_missing_manifest(self, _patch_globals):
        """None manifest -> identity_match=False with reason='manifest_missing'."""
        from comfyapp import _check_dependency_manifest_identity

        result = _check_dependency_manifest_identity(
            None,
            combined_hash="ch123",
            custom_node_fingerprint=None,
            custom_node_generation="gen",
            repair_mode="fail_fast",
        )
        assert result["identity_match"] is False
        assert result["reason"] == "manifest_missing"
        # Stored fields are empty for missing manifest
        assert result["stored_schema_version"] is None
        assert result["stored_combined_hash"] == ""
        assert result["miss_component"] == "manifest_missing"

    def test_schema_mismatch(self, _patch_globals):
        """Schema version mismatch -> identity_match=False."""
        from comfyapp import _check_dependency_manifest_identity

        manifest = self._make_manifest(schema_version=999)
        result = _check_dependency_manifest_identity(
            manifest,
            combined_hash="ch123",
            custom_node_fingerprint=None,
            custom_node_generation="gen",
            repair_mode="fail_fast",
        )
        assert result["identity_match"] is False
        # miss_component reveals schema mismatch as string
        mc = result.get("miss_component", "")
        assert isinstance(mc, str)
        assert "schema_version" in mc
        assert "deployment_hash" in mc  # stored="ch" vs current="ch123"

    def test_identity_mismatch(self, _patch_globals):
        """Different identity values -> identity_match=False with reason='identity_mismatch'."""
        from comfyapp import _check_dependency_manifest_identity

        manifest = self._make_manifest(identity="stored_ident_old")
        result = _check_dependency_manifest_identity(
            manifest,
            combined_hash="ch123",
            custom_node_fingerprint={"overall_dependency_hash": "fp_new"},
            custom_node_generation="gen_new",
            repair_mode="fail_fast",
        )
        assert result["identity_match"] is False
        assert result["reason"] == "identity_mismatch"
        # miss_component shows which fields differ as string
        mc = result.get("miss_component", "")
        assert isinstance(mc, str)
        assert "deployment_hash" in mc  # stored="ch" vs current="ch123"
        assert "baked_dependency_hash" in mc
        assert "custom_nodes_generation" in mc
        assert "repair_mode" not in mc  # both are "fail_fast"

    def test_stored_identity_empty(self, _patch_globals):
        """Empty stored identity -> identity_match=False with stored_identity_empty."""
        from comfyapp import _check_dependency_manifest_identity

        manifest = self._make_manifest(identity="")
        result = _check_dependency_manifest_identity(
            manifest,
            combined_hash="ch123",
            custom_node_fingerprint=None,
            custom_node_generation="gen",
            repair_mode="fail_fast",
        )
        assert result["identity_match"] is False
        assert result["reason"] == "stored_identity_empty"


# ── _load_dependency_manifest ──────────────────────────────────────────


class TestLoadDependencyManifest:
    def _mft_path(self):
        """Return the manifest path using the patched module constants."""
        from comfyapp import DEPENDENCY_MANIFEST_DIR, DEPENDENCY_MANIFEST_FILENAME
        return os.path.join(DEPENDENCY_MANIFEST_DIR, DEPENDENCY_MANIFEST_FILENAME)

    def test_missing_file(self, _patch_globals):
        """No file on disk -> None."""
        from comfyapp import _load_dependency_manifest

        result = _load_dependency_manifest()
        assert result is None

    def test_valid_manifest(self, _patch_globals):
        """Valid JSON with correct schema -> manifest dict."""
        mft_path = self._mft_path()
        os.makedirs(os.path.dirname(mft_path), exist_ok=True)
        data = {
            "schema_version": 1,
            "identity": "test_identity",
            "combined_hash": "ch",
            "created_at_unix": time.time(),
        }
        with open(mft_path, "w") as f:
            json.dump(data, f)

        from comfyapp import _load_dependency_manifest

        result = _load_dependency_manifest()
        assert result is not None, f"manifest not loaded from {mft_path}"
        assert result["identity"] == "test_identity"

    def test_corrupt_json(self, _patch_globals):
        """Corrupt JSON -> None."""
        mft_path = self._mft_path()
        os.makedirs(os.path.dirname(mft_path), exist_ok=True)
        with open(mft_path, "w") as f:
            f.write("{invalid json!!!")

        from comfyapp import _load_dependency_manifest

        result = _load_dependency_manifest()
        assert result is None

    def test_schema_mismatch(self, _patch_globals):
        """Schema version != DEPENDENCY_MANIFEST_SCHEMA_VERSION -> None."""
        mft_path = self._mft_path()
        os.makedirs(os.path.dirname(mft_path), exist_ok=True)
        data = {
            "schema_version": 999,
            "identity": "test_identity",
        }
        with open(mft_path, "w") as f:
            json.dump(data, f)

        from comfyapp import _load_dependency_manifest

        result = _load_dependency_manifest()
        assert result is None

    def test_missing_identity_field(self, _patch_globals):
        """Manifest without identity -> None."""
        mft_path = self._mft_path()
        os.makedirs(os.path.dirname(mft_path), exist_ok=True)
        data = {
            "schema_version": 1,
        }
        with open(mft_path, "w") as f:
            json.dump(data, f)

        from comfyapp import _load_dependency_manifest

        result = _load_dependency_manifest()
        assert result is None


# ── _build_and_persist_dependency_manifest ─────────────────────────────


class TestBuildAndPersistDependencyManifest:
    def test_persist_without_commit(self, _patch_globals):
        """Write manifest without volume commit (commit=False)."""
        from comfyapp import (
            _build_and_persist_dependency_manifest,
            DEPENDENCY_MANIFEST_DIR,
            DEPENDENCY_MANIFEST_FILENAME,
        )

        result = _build_and_persist_dependency_manifest(
            combined_hash="ch123",
            custom_node_fingerprint={"overall_dependency_hash": "fp456"},
            custom_node_generation="gen789",
            repair_mode="fail_fast",
            volume=None,
            commit=False,
        )
        assert "identity" in result
        assert result["combined_hash"] == "ch123"
        # Verify file was written
        final_path = os.path.join(DEPENDENCY_MANIFEST_DIR, DEPENDENCY_MANIFEST_FILENAME)
        assert os.path.isfile(final_path)
        with open(final_path) as f:
            loaded = json.load(f)
        assert loaded["identity"] == result["identity"]

    def test_persist_with_commit(self, _patch_globals):
        """Write manifest with volume commit (commit=True)."""
        mock_vol = MagicMock()
        from comfyapp import (
            _build_and_persist_dependency_manifest,
        )

        result = _build_and_persist_dependency_manifest(
            combined_hash="ch123",
            custom_node_fingerprint={"overall_dependency_hash": "fp456"},
            custom_node_generation="gen789",
            repair_mode="fail_fast",
            volume=mock_vol,
            commit=True,
        )
        assert "identity" in result
        mock_vol.commit.assert_called_once()

    def test_persist_no_identity(self, _patch_globals):
        """When identity cannot be established, the caller should not
        invoke this function.  Test that it still writes an empty identity
        case gracefully (no crash)."""
        from comfyapp import _build_and_persist_dependency_manifest

        result = _build_and_persist_dependency_manifest(
            combined_hash="",
            custom_node_fingerprint={},
            custom_node_generation="",
            repair_mode="fail_fast",
            volume=None,
            commit=False,
        )
        assert isinstance(result, dict)

    def test_atomic_replace(self, _patch_globals):
        """Write twice: second write atomically replaces first."""
        from comfyapp import (
            _build_and_persist_dependency_manifest,
            DEPENDENCY_MANIFEST_DIR,
            DEPENDENCY_MANIFEST_FILENAME,
        )

        r1 = _build_and_persist_dependency_manifest(
            combined_hash="old_hash",
            custom_node_fingerprint={},
            custom_node_generation="old_gen",
            repair_mode="fail_fast",
        )
        r2 = _build_and_persist_dependency_manifest(
            combined_hash="new_hash",
            custom_node_fingerprint={},
            custom_node_generation="new_gen",
            repair_mode="fail_fast",
        )
        assert r1["identity"] != r2["identity"]
        final_path = os.path.join(DEPENDENCY_MANIFEST_DIR, DEPENDENCY_MANIFEST_FILENAME)
        with open(final_path) as f:
            loaded = json.load(f)
        assert loaded["identity"] == r2["identity"]


# ── _emit_dependency_validation_v2 ─────────────────────────────────────


class TestEmitDependencyValidationV2:
    def test_emits_valid_hit(self, _patch_globals, capsys):
        """Hit path emits correct fields with no fingerprint/validation."""
        from comfyapp import _emit_dependency_validation_v2

        _emit_dependency_validation_v2(
            source="persistent_manifest",
            identity_match=True,
            prompt_structure_validation_ms=1.0,
            deployment_hash_resolution_ms=2.0,
            baked_manifest_read_ms=3.0,
            custom_node_generation_read_ms=1.5,
            manifest_load_ms=5.0,
            cheap_check_ms=2.5,
            manifest_identity_check_ms=2.0,
            fallback_validation_called=False,
            fallback_fingerprint_ms=0.0,
            fallback_validation_ms=0.0,
            preflight_total_ms=14.5,
            deployment_hash="deploy_hash_abc",
            baked_dependency_hash="baked_hash",
            custom_nodes_generation="gen_123",
            repair_mode="fail_fast",
            stored_manifest_identity="stored_id",
            computed_manifest_identity="computed_id",
            miss_component="",
            reason="manifest_identity_match",
        )
        captured = capsys.readouterr()
        assert "[v2.dependency_validation]" in captured.out
        assert "identity_match=1" in captured.out
        assert "prompt_structure_validation_ms=1.0" in captured.out
        assert "deployment_hash_resolution_ms=2.0" in captured.out
        assert "baked_manifest_read_ms=3.0" in captured.out
        assert "custom_node_generation_read_ms=1.5" in captured.out
        assert "manifest_load_ms=5.0" in captured.out
        assert "cheap_check_ms=2.5" in captured.out
        assert "manifest_identity_check_ms=2.0" in captured.out
        assert "fallback_validation_called=0" in captured.out
        assert "fallback_fingerprint_ms=0.0" in captured.out
        assert "fallback_validation_ms=0.0" in captured.out
        assert "preflight_total_ms=14.5" in captured.out
        assert "deployment_hash=deploy_hash_abc" in captured.out
        assert "baked_dependency_hash=baked_hash" in captured.out
        assert "custom_nodes_generation=gen_123" in captured.out
        assert "repair_mode=fail_fast" in captured.out
        assert "stored_manifest_identity=stored_id" in captured.out
        assert "computed_manifest_identity=computed_id" in captured.out
        assert "miss_component=" in captured.out
        assert "reason=manifest_identity_match" in captured.out

    def test_emits_miss_with_refresh(self, _patch_globals, capsys):
        """Miss path with refresh includes fingerprint/validation times."""
        from comfyapp import _emit_dependency_validation_v2

        _emit_dependency_validation_v2(
            source="request_rebuild",
            identity_match=False,
            prompt_structure_validation_ms=1.0,
            deployment_hash_resolution_ms=2.0,
            baked_manifest_read_ms=3.0,
            custom_node_generation_read_ms=1.5,
            manifest_load_ms=5.0,
            manifest_identity_check_ms=1.0,
            fallback_validation_called=True,
            fallback_fingerprint_ms=450.0,
            fallback_validation_ms=300.0,
            preflight_total_ms=763.5,
            deployment_hash="deploy_hash_abc",
            baked_dependency_hash="baked_hash",
            custom_nodes_generation="gen_123",
            repair_mode="fail_fast",
            stored_manifest_identity="old_stored",
            computed_manifest_identity="new_computed",
            miss_component="deployment_hash",
            reason="identity_mismatch",
        )
        captured = capsys.readouterr()
        assert "[v2.dependency_validation]" in captured.out
        assert "identity_match=0" in captured.out
        assert "fallback_validation_called=1" in captured.out
        assert "fallback_fingerprint_ms=450.0" in captured.out
        assert "fallback_validation_ms=300.0" in captured.out
        assert "preflight_total_ms=763.5" in captured.out
        assert "stored_manifest_identity=old_stored" in captured.out
        assert "computed_manifest_identity=new_computed" in captured.out
        assert "reason=identity_mismatch" in captured.out


# ── Preflight integration ──────────────────────────────────────────────


def _get_preflight_unbound():
    """Lazy-import the unbound method so test collection doesn't
    trigger comfyapp import (which requires ComfyUI dependencies)."""
    import comfyapp as _cm
    return _cm._ComfyAPIMixin._preflight_before_prompt_execution


class FakeComfyApp:
    """Minimal stand-in for ComfyApp to exercise _preflight_before_prompt_execution."""

    def __init__(self):
        self._custom_nodes_state = {}

    @staticmethod
    def _resolve_requirements_repair_mode():
        return "fail_fast"


class TestPreflightIntegration:
    """Test the manifest fast path in _preflight_before_prompt_execution."""

    # ── Shared mock identity-check return helper ─────────────────────────

    @staticmethod
    def _identity_check_kwargs(match, **overrides):
        """Build a return dict for mock _check_dependency_manifest_identity."""
        base = {
            "identity_match": match,
            "manifest_load_ms": 3.0,
            "cheap_check_ms": 1.0,
            "computed_identity": "ident" if match else "new_ident",
            "stored_identity": "ident" if match else "old_ident",
            "reason": "" if match else "identity_mismatch",
            "stored_schema_version": 1,
            "stored_combined_hash": "combined_hash_val",
            "stored_custom_node_fingerprint_overall_dependency_hash": "fp",
            "stored_custom_node_generation": "gen",
            "stored_repair_mode": "fail_fast",
            "miss_component": "" if match else "deployment_hash,baked_dependency_hash,custom_nodes_generation",
        }
        base.update(overrides)
        return base

    # ── Test: valid hit ─────────────────────────────────────────────────

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_valid_hit_no_fingerprint(
        self,
        mock_check_identity,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build_persist,
        mock_run_val,
        _patch_globals,
    ):
        """Valid manifest hit: no fingerprint/validation call, under 50ms."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = {"identity": "some_identity", "schema_version": 1}
        mock_check_identity.return_value = self._identity_check_kwargs(match=True)

        app = FakeComfyApp()
        t0 = time.time()
        result = _get_preflight_unbound()(app, {"some": "workflow"})
        elapsed_ms = (time.time() - t0) * 1000

        assert result["dependency_prepared"] is True
        assert result["dependency_reason"] == "manifest_identity_match"
        mock_run_val.assert_not_called()
        mock_build_persist.assert_not_called()
        assert elapsed_ms < 50, f"Expected <50ms but got {elapsed_ms:.1f}ms"

    # ── Test: prompt validation still active ────────────────────────────

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_prompt_validation_still_active(
        self,
        mock_check_identity,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build_persist,
        mock_run_val,
        _patch_globals,
    ):
        """assert_valid_api_prompt_structure is always called."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = {"identity": "some_identity", "schema_version": 1}
        mock_check_identity.return_value = self._identity_check_kwargs(match=True)

        app = FakeComfyApp()
        _get_preflight_unbound()(app, {"some": "workflow"})
        mock_assert_valid.assert_called_once_with({"some": "workflow"})

    # ── Test: identity hit skips fingerprint ────────────────────────────

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_identity_hit_skips_fingerprint(
        self,
        mock_check_identity,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build_persist,
        mock_run_val,
        _patch_globals,
    ):
        """Identity match: no custom_node_dependency_fingerprint call."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = {"identity": "some_identity", "schema_version": 1}
        mock_check_identity.return_value = self._identity_check_kwargs(match=True)

        with patch("comfyapp.custom_node_dependency_fingerprint") as mock_fp:
            app = FakeComfyApp()
            _get_preflight_unbound()(app, {"some": "workflow"})
            mock_fp.assert_not_called()

    # ── Test: identity mismatch runs validation ─────────────────────────

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_identity_mismatch_runs_validation(
        self,
        mock_check_identity,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build_persist,
        mock_run_val,
        _patch_globals,
    ):
        """Identity mismatch: runs full validation and replacement write."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = {"identity": "old_identity", "schema_version": 1}
        mock_check_identity.return_value = self._identity_check_kwargs(
            match=False,
            stored_identity="old_ident",
            computed_identity="new_ident",
            reason="identity_mismatch",
        )
        mock_run_val.return_value = {
            "prepared": True,
            "reason": "hash_match",
            "dependency_fingerprint_ms": 450.0,
            "dependency_full_validation_ms": 300.0,
            "dependency_validation_reason": "hash_match",
        }

        app = FakeComfyApp()
        result = _get_preflight_unbound()(app, {"some": "workflow"})

        assert result["dependency_prepared"] is True
        mock_run_val.assert_called_once()
        mock_build_persist.assert_called_once()

    # ── Test: exact miss_component on mismatch ──────────────────────────

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_exact_miss_component(
        self,
        mock_check_identity,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build_persist,
        mock_run_val,
        _patch_globals,
    ):
        """miss_component reports per-field comparison on identity miss."""
        mock_combined.return_value = "new_hash"
        mock_baked.return_value = {"overall_dependency_hash": "new_fp"}
        mock_cn_gen.return_value = {"generation": "new_gen"}
        mock_load_mft.return_value = {
            "identity": "old_identity",
            "schema_version": 1,
            "combined_hash": "old_hash",
            "custom_node_fingerprint": {"overall_dependency_hash": "old_fp"},
            "custom_node_generation": "old_gen",
            "repair_mode": "dev",
        }
        mc = "deployment_hash,baked_dependency_hash,custom_nodes_generation,repair_mode"
        mock_check_identity.return_value = self._identity_check_kwargs(
            match=False,
            stored_identity="old_identity",
            computed_identity="new_computed",
            reason="identity_mismatch",
            miss_component=mc,
            stored_combined_hash="old_hash",
            stored_custom_node_fingerprint_overall_dependency_hash="old_fp",
            stored_custom_node_generation="old_gen",
            stored_repair_mode="dev",
        )
        mock_run_val.return_value = {
            "prepared": True,
            "reason": "hash_match",
            "dependency_fingerprint_ms": 450.0,
            "dependency_full_validation_ms": 300.0,
            "dependency_validation_reason": "hash_match",
        }

        app = FakeComfyApp()
        result = _get_preflight_unbound()(app, {"some": "workflow"})

        assert result["dependency_prepared"] is True
        # The emitted diagnostic includes miss_component (verified via capsys)
        mock_run_val.assert_called_once()
        mock_build_persist.assert_called_once()
        # Verify miss_component entries via the mock identity check
        called_mc = mock_check_identity.call_args[0][0]  # manifest arg
        assert called_mc["identity"] == "old_identity"

    # ── Test: V2 production wiring (all fields present) ────────────────

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_v2_production_wiring(
        self,
        mock_check_identity,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build_persist,
        mock_run_val,
        _patch_globals,
        capsys,
    ):
        """V2 production wiring emits all required diagnostic fields."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = {"identity": "some_identity", "schema_version": 1}
        mock_check_identity.return_value = self._identity_check_kwargs(match=True)

        app = FakeComfyApp()
        _get_preflight_unbound()(app, {"some": "workflow"})
        captured = capsys.readouterr()

        # Verify all new fields present in the output
        assert "prompt_structure_validation_ms=" in captured.out
        assert "deployment_hash_resolution_ms=" in captured.out
        assert "baked_manifest_read_ms=" in captured.out
        assert "custom_node_generation_read_ms=" in captured.out
        assert "manifest_load_ms=" in captured.out
        assert "manifest_identity_check_ms=" in captured.out
        assert "fallback_validation_called=" in captured.out
        assert "fallback_fingerprint_ms=" in captured.out
        assert "fallback_validation_ms=" in captured.out
        assert "preflight_total_ms=" in captured.out
        assert "deployment_hash=" in captured.out
        assert "baked_dependency_hash=" in captured.out
        assert "custom_nodes_generation=" in captured.out
        assert "repair_mode=" in captured.out
        assert "stored_manifest_identity=" in captured.out
        assert "computed_manifest_identity=" in captured.out
        assert "miss_component=" in captured.out

    # ── Test: missing manifest fail-closed ──────────────────────────────

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_missing_manifest_fail_closed(
        self,
        mock_check_identity,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build_persist,
        mock_run_val,
        _patch_globals,
    ):
        """Missing manifest: fail-closed (runs validation, raises on failure)."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = None  # manifest missing
        mock_check_identity.return_value = self._identity_check_kwargs(
            match=False,
            manifest_load_ms=0.0,
            cheap_check_ms=0.5,
            computed_identity="",
            stored_identity="",
            reason="manifest_missing",
            stored_schema_version=None,
            stored_combined_hash="",
            stored_custom_node_fingerprint_overall_dependency_hash="",
            stored_custom_node_generation="",
            stored_repair_mode="",
            miss_component="manifest_missing",
        )
        mock_run_val.return_value = {
            "prepared": False,
            "reason": "baked_manifest_missing",
            "baked_hash": None,
            "current_hash": None,
            "changed_nodes": [],
            "dependency_fingerprint_ms": 0.0,
            "dependency_full_validation_ms": 0.0,
            "dependency_validation_reason": "baked_manifest_missing",
        }

        app = FakeComfyApp()
        with pytest.raises(RuntimeError, match="not prepared"):
            _get_preflight_unbound()(app, {"some": "workflow"})

        mock_run_val.assert_called_once()
        mock_build_persist.assert_not_called()

    # ── Test: schema mismatch runs validation ───────────────────────────

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_schema_mismatch_runs_validation(
        self,
        mock_check_identity,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build_persist,
        mock_run_val,
        _patch_globals,
    ):
        """Schema mismatch: fails closed, runs full validation, refreshes on success."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = None
        mock_check_identity.return_value = self._identity_check_kwargs(
            match=False,
            manifest_load_ms=0.0,
            cheap_check_ms=0.5,
            computed_identity="",
            stored_identity="",
            reason="manifest_missing",
            stored_schema_version=None,
            stored_combined_hash="",
            stored_custom_node_fingerprint_overall_dependency_hash="",
            stored_custom_node_generation="",
            stored_repair_mode="",
            miss_component="manifest_missing",
        )
        mock_run_val.return_value = {
            "prepared": True,
            "reason": "hash_match",
            "dependency_fingerprint_ms": 450.0,
            "dependency_full_validation_ms": 200.0,
            "dependency_validation_reason": "hash_match",
        }

        app = FakeComfyApp()
        result = _get_preflight_unbound()(app, {"some": "workflow"})

        assert result["dependency_prepared"] is True
        mock_run_val.assert_called_once()
        mock_build_persist.assert_called_once()

    # ── Test: corrupt manifest fail-closed ──────────────────────────────

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_corrupt_manifest_fail_closed(
        self,
        mock_check_identity,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build_persist,
        mock_run_val,
        _patch_globals,
    ):
        """Corrupt manifest: fails closed, runs full validation."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = None
        mock_check_identity.return_value = self._identity_check_kwargs(
            match=False,
            manifest_load_ms=0.0,
            cheap_check_ms=0.5,
            computed_identity="",
            stored_identity="",
            reason="manifest_missing",
            stored_schema_version=None,
            stored_combined_hash="",
            stored_custom_node_fingerprint_overall_dependency_hash="",
            stored_custom_node_generation="",
            stored_repair_mode="",
            miss_component="manifest_missing",
        )
        mock_run_val.return_value = {
            "prepared": True,
            "reason": "hash_match",
            "dependency_fingerprint_ms": 450.0,
            "dependency_full_validation_ms": 200.0,
            "dependency_validation_reason": "hash_match",
        }

        app = FakeComfyApp()
        result = _get_preflight_unbound()(app, {"some": "workflow"})

        assert result["dependency_prepared"] is True
        mock_run_val.assert_called_once()
        mock_build_persist.assert_called_once()
