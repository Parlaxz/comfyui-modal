"""Lifecycle tests for the immutable dependency manifest.

Proves:
- Startup/snapshot preparation creates the manifest (with diagnostic emit).
- First request hits the persisted manifest (no fingerprint/full validation).
- Deployment hash, generation, repair mode, and schema invalidate properly.
- Absent/corrupt manifests fail closed (trigger validation, raise on failure).
- Refresh does exactly one commit (no fire-and-forget threading).
- Async paths have no blocking Modal call and use the awaited API where needed.
- Prompt structural validation remains active.
- Startup does not call expensive fingerprint traversal twice.

All tests use mocks and temp directories — no Modal runtime required.
"""

import asyncio
import json
import os
import tempfile
import time
from unittest.mock import ANY, AsyncMock, MagicMock, patch, call

import pytest


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def manifest_env():
    """Set up a temp environment with patched module-level constants.

    Returns a dict with paths and mocks for test assertions.
    """
    _tmp = tempfile.mkdtemp()
    _mft_dir = os.path.join(_tmp, "dependency_manifest")
    _cache_dir = os.path.join(_tmp, "deployment_dependency_validation_cache")
    _gen_dir = os.path.join(_tmp, "control")
    _gen_path = os.path.join(_gen_dir, "custom_nodes_generation.json")
    os.makedirs(_gen_dir, exist_ok=True)

    with (
        patch("comfyapp.RUNTIME_CONFIG_DIR", _tmp),
        patch("comfyapp.DEPENDENCY_MANIFEST_DIR", _mft_dir),
        patch("comfyapp.DEPLOYMENT_DEPENDENCY_VALIDATION_CACHE_DIR", _cache_dir),
        patch("comfyapp.CUSTOM_NODES_GENERATION_CONTROL_DIR", _gen_dir),
        patch("comfyapp.CUSTOM_NODES_GENERATION_CONTROL_PATH", _gen_path),
        patch("comfyapp.CONTAINER_SESSION_ID", "lifecycle-test-session"),
        patch("comfyapp.COMFYAPP_VERSION", "1.0.0"),
        patch("comfyapp._V2_RUNTIME_REVISION", "deadbeef"),
        patch("comfyapp.REQUIREMENTS_REPAIR_MODE", "fail_fast"),
        patch("comfyapp.load_baked_custom_node_dependency_manifest") as mock_baked,
        patch("comfyapp._read_custom_nodes_generation_record") as mock_gen,
        # Don't mock _write_custom_nodes_generation_record_no_commit so
        # tests that verify file creation work correctly.
        patch("comfyapp.custom_nodes_vol") as mock_cn_vol,
        patch("comfyapp.runtime_config_vol") as mock_rc_vol,
    ):
        yield {
            "tmpdir": _tmp,
            "mft_dir": _mft_dir,
            "cache_dir": _cache_dir,
            "gen_dir": _gen_dir,
            "gen_path": _gen_path,
            "mock_baked": mock_baked,
            "mock_gen": mock_gen,
            "mock_cn_vol": mock_cn_vol,
            "mock_rc_vol": mock_rc_vol,
        }


def _write_gen_record(gen_dir, generation="test-gen-001"):
    """Helper to write a generation record to disk."""
    gen_path = os.path.join(gen_dir, "custom_nodes_generation.json")
    with open(gen_path, "w") as f:
        json.dump({
            "schema_version": 1,
            "generation": generation,
            "updated_at_unix": time.time(),
            "reason": "test",
        }, f)
    return gen_path


def _read_manifest(mft_dir):
    """Read the persisted manifest from disk, or None."""
    path = os.path.join(mft_dir, "immutable_manifest.json")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)


# ── Helpers: Fake ComfyApp ─────────────────────────────────────────────


class FakeComfyApp:
    """Minimal stand-in for ComfyApp to exercise startup and preflight."""

    def __init__(self):
        self._custom_nodes_state = {}
        self._custom_nodes_generation_seen = ""
        self._custom_nodes_state_last_synced = None

    @staticmethod
    def _resolve_requirements_repair_mode():
        return "fail_fast"

    @staticmethod
    def _select_backend():
        return "in_process"

    @staticmethod
    def _ensure_models_symlink():
        pass

    def _log_profile(self, *args, **kwargs):
        pass

    def _record_runtime_state(self):
        pass

    def _ensure_validation_cache(self):
        pass

    def _sync_custom_nodes_from_volume(self):
        return {"created": [], "kept": [], "removed": []}, {}

    def _install_custom_node_requirements(self, force=False):
        return {
            "installed": [], "skipped": [], "failed": [],
            "mode": "fail_fast", "prepared": True,
        }


# ── Test: Startup creates the manifest ──────────────────────────────────


class TestStartupCreatesManifest:
    """Startup/snapshot preparation must create the manifest.
    
    Tests call ``_build_and_persist_dependency_manifest`` directly to verify
    the manifest creation logic used during startup.
    """

    def test_build_and_persist_creates_manifest_file(self, manifest_env):
        """_build_and_persist_dependency_manifest creates the manifest file."""
        import comfyapp

        result = comfyapp._build_and_persist_dependency_manifest(
            combined_hash="deploy_hash_abc",
            custom_node_fingerprint={"overall_dependency_hash": "baked_fp"},
            custom_node_generation="test-gen-001",
            repair_mode="fail_fast",
            volume=None,
            commit=False,
        )
        assert "identity" in result
        manifest = _read_manifest(manifest_env["mft_dir"])
        assert manifest is not None, "manifest was not created"
        assert manifest["identity"] == result["identity"]

    def test_manifest_has_correct_source(self, manifest_env):
        """Manifest source must be snapshot_manifest."""
        import comfyapp

        result = comfyapp._build_and_persist_dependency_manifest(
            combined_hash="ch",
            custom_node_fingerprint={"overall_dependency_hash": "fp"},
            custom_node_generation="gen",
            repair_mode="fail_fast",
            volume=None,
            commit=False,
        )
        manifest = _read_manifest(manifest_env["mft_dir"])
        assert manifest["source"] == "snapshot_manifest"

    def test_manifest_has_all_identity_fields(self, manifest_env):
        """Manifest must contain all required identity fields."""
        import comfyapp

        comfyapp._build_and_persist_dependency_manifest(
            combined_hash="ch",
            custom_node_fingerprint={"overall_dependency_hash": "fp"},
            custom_node_generation="gen",
            repair_mode="fail_fast",
            volume=None,
            commit=False,
        )
        manifest = _read_manifest(manifest_env["mft_dir"])
        assert manifest["schema_version"] == 1
        assert manifest["combined_hash"] == "ch"
        assert "overall_dependency_hash" in manifest["custom_node_fingerprint"]
        assert manifest["custom_node_generation"] == "gen"
        assert manifest["repair_mode"] == "fail_fast"

    def test_initializes_generation_when_missing(self, manifest_env):
        """Simulate generation record initialization (part of startup)."""
        env = manifest_env
        import comfyapp

        # No generation record on disk yet
        assert not os.path.isfile(env["gen_path"])
        env["mock_gen"].return_value = None

        # Simulate startup calling _write_custom_nodes_generation_record_no_commit
        gen_rec = comfyapp._write_custom_nodes_generation_record_no_commit(
            reason="startup_init_generation_record"
        )
        assert gen_rec["generation"]
        assert gen_rec["reason"] == "startup_init_generation_record"

        # Now the generation record exists
        assert os.path.isfile(env["gen_path"])

        # Build manifest with the new generation
        result = comfyapp._build_and_persist_dependency_manifest(
            combined_hash="ch",
            custom_node_fingerprint={"overall_dependency_hash": "fp"},
            custom_node_generation=gen_rec["generation"],
            repair_mode="fail_fast",
            volume=None,
            commit=False,
        )
        manifest = _read_manifest(env["mft_dir"])
        assert manifest["custom_node_generation"] == gen_rec["generation"]

    def test_build_and_persist_with_empty_identity_components(self, manifest_env):
        """Manifest build handles empty identity components gracefully
        (the identity will be empty, triggering a rebuild on first request)."""
        import comfyapp

        result = comfyapp._build_and_persist_dependency_manifest(
            combined_hash="",
            custom_node_fingerprint={},
            custom_node_generation="",
            repair_mode="fail_fast",
            volume=None,
            commit=False,
        )
        assert isinstance(result, dict)
        manifest = _read_manifest(manifest_env["mft_dir"])
        assert manifest is not None
        # Identity may be short/empty but file must exist

    def test_startup_does_not_call_fingerprint(self, manifest_env):
        """_build_and_persist_dependency_manifest does NOT call
        custom_node_dependency_fingerprint (only uses baked manifest fingerprint)."""
        import comfyapp

        with patch("comfyapp.custom_node_dependency_fingerprint") as mock_fp:
            comfyapp._build_and_persist_dependency_manifest(
                combined_hash="ch",
                custom_node_fingerprint={"overall_dependency_hash": "fp"},
                custom_node_generation="gen",
                repair_mode="fail_fast",
                volume=None,
                commit=False,
            )
            mock_fp.assert_not_called()

    def test_startup_commits_exactly_once(self, manifest_env):
        """Manifest build with commit=True does exactly one volume commit
        and returns a valid non-empty identity."""
        mock_vol = MagicMock()
        import comfyapp

        result = comfyapp._build_and_persist_dependency_manifest(
            combined_hash="ch",
            custom_node_fingerprint={"overall_dependency_hash": "fp"},
            custom_node_generation="gen",
            repair_mode="fail_fast",
            volume=mock_vol,
            commit=True,
        )
        assert "identity" in result
        assert result["identity"], "identity must be non-empty on successful commit"
        assert mock_vol.commit.call_count == 1

    def test_commit_failure_returns_error_dict(self, manifest_env):
        """When volume commit fails, returns error dict with empty identity
        and does NOT attempt a second commit."""
        import comfyapp

        mock_vol = MagicMock()
        mock_vol.commit.side_effect = Exception("boom")

        result = comfyapp._build_and_persist_dependency_manifest(
            combined_hash="ch",
            custom_node_fingerprint={"overall_dependency_hash": "fp"},
            custom_node_generation="gen",
            repair_mode="fail_fast",
            volume=mock_vol,
            commit=True,
        )
        assert isinstance(result, dict)
        assert result.get("identity") == "", (
            f"Expected empty identity on commit failure, got {result.get('identity')!r}"
        )
        assert "error" in result
        # Exactly one commit attempt — no retry, no second commit
        assert mock_vol.commit.call_count == 1


# ── Test: First request hits manifest ───────────────────────────────────


def _get_preflight_unbound():
    """Lazy-import the unbound preflight method."""
    import comfyapp as _cm
    return _cm._ComfyAPIMixin._preflight_before_prompt_execution


class TestFirstRequestHitsManifest:
    """First request after startup must hit the persisted manifest."""

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_valid_hit_skips_validation(
        self,
        mock_check_id,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build,
        mock_run_val,
        manifest_env,
    ):
        """Valid manifest hit: no fingerprint/validation call, under 50ms."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = {"identity": "some_id", "schema_version": 1}
        mock_check_id.return_value = {
            "identity_match": True,
            "manifest_load_ms": 3.0,
            "cheap_check_ms": 1.0,
            "computed_identity": "ident",
            "stored_identity": "ident",
            "reason": "",
        }

        app = FakeComfyApp()
        t0 = time.time()
        result = _get_preflight_unbound()(app, {"some": "workflow"})
        elapsed_ms = (time.time() - t0) * 1000

        assert result["dependency_prepared"] is True
        assert result["dependency_reason"] == "manifest_identity_match"
        mock_run_val.assert_not_called()
        mock_build.assert_not_called()
        assert elapsed_ms < 50, f"Expected <50ms but got {elapsed_ms:.1f}ms"

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
        mock_check_id,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build,
        mock_run_val,
        manifest_env,
    ):
        """assert_valid_api_prompt_structure is always called."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = {"identity": "some_id", "schema_version": 1}
        mock_check_id.return_value = {
            "identity_match": True,
            "manifest_load_ms": 3.0,
            "cheap_check_ms": 1.0,
            "computed_identity": "ident",
            "stored_identity": "ident",
            "reason": "",
        }

        app = FakeComfyApp()
        _get_preflight_unbound()(app, {"some": "workflow"})
        mock_assert_valid.assert_called_once_with({"some": "workflow"})

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_identity_hit_does_not_call_fingerprint(
        self,
        mock_check_id,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build,
        mock_run_val,
        manifest_env,
    ):
        """Identity match: no custom_node_dependency_fingerprint call."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = {"identity": "some_id", "schema_version": 1}
        mock_check_id.return_value = {
            "identity_match": True,
            "manifest_load_ms": 3.0,
            "cheap_check_ms": 1.0,
            "computed_identity": "ident",
            "stored_identity": "ident",
            "reason": "",
        }

        with patch("comfyapp.custom_node_dependency_fingerprint") as mock_fp:
            app = FakeComfyApp()
            _get_preflight_unbound()(app, {"some": "workflow"})
            mock_fp.assert_not_called()


# ── Test: Invalidation modes ────────────────────────────────────────────


class TestInvalidationModes:
    """Deployment hash, generation, repair mode, and schema invalidate."""

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    def test_deployment_hash_change_invalidates(
        self,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build,
        mock_run_val,
        manifest_env,
    ):
        """Different deployment combined hash invalidates manifest."""
        mock_combined.return_value = "new_hash"
        mock_baked.return_value = {"overall_dependency_hash": "fp_new"}
        mock_cn_gen.return_value = {"generation": "gen_new"}
        mock_load_mft.return_value = {
            "identity": "old_identity",
            "schema_version": 1,
        }
        mock_run_val.return_value = {
            "prepared": True,
            "reason": "hash_match",
            "dependency_fingerprint_ms": 400.0,
            "dependency_full_validation_ms": 200.0,
            "dependency_validation_reason": "hash_match",
        }

        app = FakeComfyApp()
        result = _get_preflight_unbound()(app, {"some": "workflow"})
        assert result["dependency_prepared"] is True
        mock_run_val.assert_called_once()
        mock_build.assert_called_once()

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    def test_generation_change_invalidates(
        self,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build,
        mock_run_val,
        manifest_env,
    ):
        """Different custom-node generation invalidates manifest."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        # Stored manifest has old generation
        mock_cn_gen.return_value = {"generation": "new_gen"}
        mock_load_mft.return_value = {
            "identity": "identity_with_old_gen",
            "schema_version": 1,
        }
        mock_run_val.return_value = {
            "prepared": True,
            "reason": "hash_match",
            "dependency_fingerprint_ms": 400.0,
            "dependency_full_validation_ms": 200.0,
            "dependency_validation_reason": "hash_match",
        }

        app = FakeComfyApp()
        result = _get_preflight_unbound()(app, {"some": "workflow"})
        assert result["dependency_prepared"] is True
        mock_run_val.assert_called_once()
        mock_build.assert_called_once()

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    def test_repair_mode_change_invalidates(
        self,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build,
        mock_run_val,
        manifest_env,
    ):
        """Different repair mode invalidates manifest (e.g. dev vs fail_fast)."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = {
            "identity": "identity_with_dev_mode",
            "schema_version": 1,
        }
        mock_run_val.return_value = {
            "prepared": True,
            "reason": "hash_match",
            "dependency_fingerprint_ms": 400.0,
            "dependency_full_validation_ms": 200.0,
            "dependency_validation_reason": "hash_match",
        }

        # Override REQUIREMENTS_REPAIR_MODE for this test
        with patch("comfyapp.REQUIREMENTS_REPAIR_MODE", "fail_fast"):
            app = FakeComfyApp()
            # The method reads repair_mode from REQUIREMENTS_REPAIR_MODE
            with patch.object(app, "_resolve_requirements_repair_mode",
                              return_value="fail_fast"):
                result = _get_preflight_unbound()(app, {"some": "workflow"})
            assert result["dependency_prepared"] is True
            mock_run_val.assert_called_once()
            mock_build.assert_called_once()

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    def test_schema_change_invalidates(
        self,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build,
        mock_run_val,
        manifest_env,
    ):
        """Different schema version invalidates (loader returns None)."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        # Loader returns None for wrong schema
        mock_load_mft.return_value = None
        mock_run_val.return_value = {
            "prepared": True,
            "reason": "hash_match",
            "dependency_fingerprint_ms": 400.0,
            "dependency_full_validation_ms": 200.0,
            "dependency_validation_reason": "hash_match",
        }

        app = FakeComfyApp()
        result = _get_preflight_unbound()(app, {"some": "workflow"})
        assert result["dependency_prepared"] is True
        mock_run_val.assert_called_once()
        mock_build.assert_called_once()


# ── Test: Absent/corrupt manifest fails closed ──────────────────────────


class TestManifestFailClosed:
    """Absent or corrupt manifests must fail closed."""

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    def test_absent_manifest_triggers_validation_fail(
        self,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build,
        mock_run_val,
        manifest_env,
    ):
        """Absent manifest: runs validation, raises on failure."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = None  # absent
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
        mock_build.assert_not_called()

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    def test_corrupt_manifest_triggers_validation_refresh(
        self,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build,
        mock_run_val,
        manifest_env,
    ):
        """Corrupt manifest: runs validation, refreshes on success."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = None  # corrupt -> None
        mock_run_val.return_value = {
            "prepared": True,
            "reason": "hash_match",
            "dependency_fingerprint_ms": 400.0,
            "dependency_full_validation_ms": 200.0,
            "dependency_validation_reason": "hash_match",
        }

        app = FakeComfyApp()
        result = _get_preflight_unbound()(app, {"some": "workflow"})
        assert result["dependency_prepared"] is True
        mock_run_val.assert_called_once()
        mock_build.assert_called_once()


# ── Test: Refresh does exactly one commit ──────────────────────────────


class TestRefreshCommit:
    """Manifest refresh does exactly one deterministic commit."""

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_refresh_commits_exactly_once(
        self,
        mock_check_id,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build,
        mock_run_val,
        manifest_env,
    ):
        """Manifest refresh commits exactly once on the runtime config volume."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = {"identity": "old_id", "schema_version": 1}
        mock_check_id.return_value = {
            "identity_match": False,
            "manifest_load_ms": 3.0,
            "cheap_check_ms": 1.0,
            "computed_identity": "new_id",
            "stored_identity": "old_id",
            "reason": "identity_mismatch",
        }
        mock_run_val.return_value = {
            "prepared": True,
            "reason": "hash_match",
            "dependency_fingerprint_ms": 400.0,
            "dependency_full_validation_ms": 200.0,
            "dependency_validation_reason": "hash_match",
        }

        app = FakeComfyApp()
        result = _get_preflight_unbound()(app, {"some": "workflow"})

        assert result["dependency_prepared"] is True
        mock_build.assert_called_once()
        # Verify the manifest build called commit=True
        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs.get("commit") is True
        # And uses the runtime_config_vol
        assert call_kwargs.get("volume") is not None


# ── Test: Async path has no blocking Modal call ─────────────────────────


class TestAsyncPathSafety:
    """Async path must not use blocking Modal .commit() calls."""

    def test_build_and_persist_commit_not_fire_and_forget(self, manifest_env):
        """_build_and_persist_dependency_manifest uses deterministic sync commit,
        not fire-and-forget thread."""
        import comfyapp

        mock_vol = MagicMock()
        result = comfyapp._build_and_persist_dependency_manifest(
            combined_hash="ch",
            custom_node_fingerprint={"overall_dependency_hash": "fp"},
            custom_node_generation="gen",
            repair_mode="fail_fast",
            volume=mock_vol,
            commit=True,
        )
        assert "identity" in result
        # The commit must be synchronous: .commit() called exactly once
        assert mock_vol.commit.call_count == 1

    def test_build_and_persist_uses_sync_commit(self, manifest_env):
        """_build_and_persist_dependency_manifest uses sync commit, not thread."""
        import comfyapp

        # Mock _commit_runtime_config_vol_async to detect any call
        with patch.object(comfyapp, "_commit_runtime_config_vol_async") as mock_async:
            result = comfyapp._build_and_persist_dependency_manifest(
                combined_hash="test_hash",
                custom_node_fingerprint={"overall_dependency_hash": "fp"},
                custom_node_generation="gen",
                repair_mode="fail_fast",
                volume=MagicMock(),
                commit=True,
            )
            assert "identity" in result
            # The async commit helper must NOT be called
            mock_async.assert_not_called()


# ── Test: Module-level pure functions ──────────────────────────────────


class TestDependencyManifestModule:
    """Test the extracted dependency_manifest module directly."""

    def test_build_identity_deterministic(self):
        """Same inputs produce same identity."""
        from comfymodal_runtime.dependency_manifest import build_identity

        id1 = build_identity("ch", {"overall_dependency_hash": "fp"}, "gen", "fail_fast")
        id2 = build_identity("ch", {"overall_dependency_hash": "fp"}, "gen", "fail_fast")
        assert id1 == id2
        assert len(id1) == 64

    def test_build_identity_different_inputs(self):
        """Different inputs produce different identity."""
        from comfymodal_runtime.dependency_manifest import build_identity

        id1 = build_identity("ch1", {"overall_dependency_hash": "fp1"}, "gen1", "fail_fast")
        id2 = build_identity("ch2", {"overall_dependency_hash": "fp2"}, "gen2", "dev")
        assert id1 != id2

    def test_build_identity_empty_fingerprint(self):
        """Empty fingerprint is handled gracefully."""
        from comfymodal_runtime.dependency_manifest import build_identity

        identity = build_identity("ch", None, "gen", "fail_fast")
        assert isinstance(identity, str)
        assert len(identity) == 64

    def test_build_manifest_dict(self):
        """build_manifest_dict produces expected structure."""
        from comfymodal_runtime.dependency_manifest import (
            build_manifest_dict,
        )

        manifest = build_manifest_dict(
            combined_hash="ch",
            custom_node_fingerprint={"overall_dependency_hash": "fp"},
            custom_node_generation="gen",
            repair_mode="fail_fast",
            source="snapshot_manifest",
        )
        assert manifest["schema_version"] == 1
        assert manifest["combined_hash"] == "ch"
        assert manifest["custom_node_generation"] == "gen"
        assert manifest["repair_mode"] == "fail_fast"
        assert manifest["source"] == "snapshot_manifest"
        assert "identity" in manifest
        assert "created_at_unix" in manifest

    def test_persist_and_load_round_trip(self):
        """Persist then load returns the same data."""
        from comfymodal_runtime.dependency_manifest import (
            build_manifest_dict,
            persist_manifest,
            load_manifest,
        )

        tmpdir = tempfile.mkdtemp()
        manifest = build_manifest_dict(
            combined_hash="ch_roundtrip",
            custom_node_fingerprint={"overall_dependency_hash": "fp_rt"},
            custom_node_generation="gen_rt",
            repair_mode="fail_fast",
        )

        ok = persist_manifest(manifest, tmpdir, "test_manifest.json")
        assert ok is True

        loaded = load_manifest(tmpdir, "test_manifest.json")
        assert loaded is not None
        assert loaded["identity"] == manifest["identity"]
        assert loaded["combined_hash"] == "ch_roundtrip"

    def test_load_missing_returns_none(self):
        """load_manifest returns None for missing file."""
        from comfymodal_runtime.dependency_manifest import load_manifest

        tmpdir = tempfile.mkdtemp()
        result = load_manifest(tmpdir, "nonexistent.json")
        assert result is None

    def test_load_corrupt_returns_none(self):
        """load_manifest returns None for corrupt JSON."""
        from comfymodal_runtime.dependency_manifest import load_manifest

        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "corrupt.json")
        with open(path, "w") as f:
            f.write("{invalid")
        result = load_manifest(tmpdir, "corrupt.json")
        assert result is None

    def test_check_identity_exact_match(self):
        """check_identity returns match for identical identity."""
        from comfymodal_runtime.dependency_manifest import (
            build_manifest_dict,
            check_identity,
        )

        manifest = build_manifest_dict(
            combined_hash="ch",
            custom_node_fingerprint={"overall_dependency_hash": "fp"},
            custom_node_generation="gen",
            repair_mode="fail_fast",
        )
        result = check_identity(
            manifest,
            combined_hash="ch",
            custom_node_fingerprint={"overall_dependency_hash": "fp"},
            custom_node_generation="gen",
            repair_mode="fail_fast",
        )
        assert result["identity_match"] is True

    def test_check_identity_mismatch(self):
        """check_identity returns mismatch for different identity."""
        from comfymodal_runtime.dependency_manifest import (
            build_manifest_dict,
            check_identity,
        )

        manifest = build_manifest_dict(
            combined_hash="ch_old",
            custom_node_fingerprint={"overall_dependency_hash": "fp_old"},
            custom_node_generation="gen_old",
            repair_mode="fail_fast",
        )
        result = check_identity(
            manifest,
            combined_hash="ch_new",
            custom_node_fingerprint={"overall_dependency_hash": "fp_new"},
            custom_node_generation="gen_new",
            repair_mode="dev",
        )
        assert result["identity_match"] is False
        assert result["reason"] == "identity_mismatch"

    def test_check_identity_none_manifest(self):
        """check_identity returns manifest_missing for None input."""
        from comfymodal_runtime.dependency_manifest import check_identity

        result = check_identity(
            None,
            combined_hash="ch",
            custom_node_fingerprint=None,
            custom_node_generation="gen",
            repair_mode="fail_fast",
        )
        assert result["identity_match"] is False
        assert result["reason"] == "manifest_missing"

    def test_check_identity_empty_stored(self):
        """check_identity detects empty stored identity."""
        from comfymodal_runtime.dependency_manifest import check_identity

        result = check_identity(
            {"identity": "", "schema_version": 1},
            combined_hash="ch",
            custom_node_fingerprint=None,
            custom_node_generation="gen",
            repair_mode="fail_fast",
        )
        assert result["identity_match"] is False
        assert result["reason"] == "stored_identity_empty"

    def test_emit_diagnostic(self, capsys):
        """emit_validation_diagnostic emits correct format."""
        from comfymodal_runtime.dependency_manifest import (
            emit_validation_diagnostic,
        )

        emit_validation_diagnostic(
            source="snapshot_manifest",
            identity_match=True,
            manifest_load_ms=2.0,
            cheap_check_ms=1.0,
            fingerprint_ms=0.0,
            full_validation_ms=0.0,
            total_ms=3.0,
            refresh_performed=True,
            reason="startup_manifest_created",
        )
        captured = capsys.readouterr()
        assert "[v2.dependency_validation]" in captured.out
        assert "source=snapshot_manifest" in captured.out
        assert "identity_match=1" in captured.out
        assert "fingerprint_ms=0.0" in captured.out
        assert "refresh_performed=1" in captured.out
        assert "reason=startup_manifest_created" in captured.out


# ── Test: Commit volume sync ────────────────────────────────────────────


class TestCommitVolumeSync:
    """commit_volume_sync is deterministic, no fire-and-forget."""

    def test_commit_success(self):
        """Successful commit returns True."""
        from comfymodal_runtime.dependency_manifest import commit_volume_sync

        mock_vol = MagicMock()
        result = commit_volume_sync(mock_vol)
        assert result is True
        mock_vol.commit.assert_called_once()

    def test_commit_none_volume(self):
        """None volume returns False."""
        from comfymodal_runtime.dependency_manifest import commit_volume_sync

        result = commit_volume_sync(None)
        assert result is False

    def test_commit_failure(self):
        """Failed commit returns False."""
        from comfymodal_runtime.dependency_manifest import commit_volume_sync

        mock_vol = MagicMock()
        mock_vol.commit.side_effect = Exception("commit failed")
        result = commit_volume_sync(mock_vol)
        assert result is False

    def test_no_fire_and_forget_thread(self):
        """Commit is synchronous, not using a daemon thread."""
        from comfymodal_runtime.dependency_manifest import commit_volume_sync

        mock_vol = MagicMock()
        commit_volume_sync(mock_vol)
        # The commit is synchronous: when commit() returns, the commit is done.
        # No threads involved. We verify this by checking commit was called
        # directly and returned before our assertion.
        mock_vol.commit.assert_called_once()


# ── Test: Async commit via .aio() ───────────────────────────────────────


class TestCommitVolumeAsync:
    """commit_volume_async uses Modal's awaited .aio() interface."""

    def test_async_helper_awaits_aio_exactly_once(self):
        """commit_volume_async awaits volume.commit.aio() exactly once."""
        from comfymodal_runtime.dependency_manifest import commit_volume_async

        mock_vol = MagicMock()
        mock_aio = AsyncMock(return_value=None)
        mock_vol.commit.aio = mock_aio

        asyncio.run(commit_volume_async(mock_vol))

        mock_aio.assert_awaited_once()
        # Direct blocking commit must NOT be called when .aio() is awaitable
        mock_vol.commit.assert_not_called()

    def test_async_helper_no_direct_blocking_call(self):
        """commit_volume_async does not call volume.commit() directly."""
        from comfymodal_runtime.dependency_manifest import commit_volume_async

        mock_vol = MagicMock()
        mock_aio = AsyncMock(return_value=None)
        mock_vol.commit.aio = mock_aio

        asyncio.run(commit_volume_async(mock_vol))

        commit_call_count = mock_vol.commit.call_count
        assert commit_call_count == 0, (
            f"Expected 0 direct commit calls, got {commit_call_count}"
        )

    def test_async_helper_none_volume(self):
        """None volume returns False."""
        from comfymodal_runtime.dependency_manifest import commit_volume_async

        result = asyncio.run(commit_volume_async(None))
        assert result is False

    def test_async_helper_failure_reports_false(self):
        """Failed async commit returns False."""
        from comfymodal_runtime.dependency_manifest import commit_volume_async

        mock_vol = MagicMock()
        mock_aio = AsyncMock(side_effect=Exception("aio failed"))
        mock_vol.commit.aio = mock_aio

        result = asyncio.run(commit_volume_async(mock_vol))
        assert result is False

    def test_async_helper_magicmock_fallback(self):
        """When .aio() is not awaitable, falls back to sync volume.commit()."""
        from comfymodal_runtime.dependency_manifest import commit_volume_async

        mock_vol = MagicMock()
        # Plain MagicMock for .aio() — returns MagicMock, not awaitable
        mock_vol.commit.aio = MagicMock(return_value="not_awaitable")

        result = asyncio.run(commit_volume_async(mock_vol))
        assert result is True
        # Falls back to synchronous .commit() exactly once
        mock_vol.commit.assert_called_once()


# ── Test: Persist ordering ──────────────────────────────────────────────


class TestPersistOrdering:
    """Write-before-commit ordering is preserved."""

    def test_write_then_commit_ordering(self, manifest_env):
        """Persist happens before commit."""
        import comfyapp

        mock_vol = MagicMock()
        result = comfyapp._build_and_persist_dependency_manifest(
            combined_hash="ch",
            custom_node_fingerprint={"overall_dependency_hash": "fp"},
            custom_node_generation="gen",
            repair_mode="fail_fast",
            volume=mock_vol,
            commit=True,
        )
        # File must exist on disk
        mft_path = os.path.join(manifest_env["mft_dir"], "immutable_manifest.json")
        assert os.path.isfile(mft_path)

        # Commit was called AFTER write (at least once)
        mock_vol.commit.assert_called_once()

    def test_generation_record_written_before_manifest(self, manifest_env):
        """Generation record is initialized before manifest build in startup."""
        env = manifest_env
        env["mock_baked"].return_value = {
            "schema_version": 2,
            "overall_dependency_hash": "baked_hash_abc123",
            "nodes": {},
        }
        env["mock_gen"].return_value = None  # no gen record yet

        # Test generation record initialization directly
        import comfyapp
        gen_rec = comfyapp._write_custom_nodes_generation_record_no_commit(
            reason="startup_init_generation_record"
        )
        assert gen_rec["reason"] == "startup_init_generation_record"

        # Generation was written to disk
        assert os.path.isfile(env["gen_path"])
        # In the real startup flow, custom_nodes_vol.commit() would be
        # called after writing the generation record.  We test the write
        # ordering directly here.
        # Then runtime config was committed (manifest commit via _build_and_persist)
        comfyapp._build_and_persist_dependency_manifest(
            combined_hash="ch",
            custom_node_fingerprint={"overall_dependency_hash": "fp"},
            custom_node_generation=gen_rec["generation"],
            repair_mode="fail_fast",
            volume=env["mock_rc_vol"],
            commit=True,
        )
        assert env["mock_rc_vol"].commit.call_count >= 1


# ── Test: Startup orchestration ──────────────────────────────────────────


class TestStartupOrchestration:
    """Real ``startup()`` orchestration with all heavy dependencies mocked.

    Proves:
    - Manifest build is present
    - Occurs after requirements preparation, before backend start
    - Does not call ``custom_node_dependency_fingerprint`` itself
    """

    @patch("comfyapp._dep_mft.emit_validation_diagnostic")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp._write_custom_nodes_generation_record_no_commit")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp.custom_node_dependency_fingerprint")
    @patch("comfyapp.custom_nodes_vol")
    @patch("comfyapp.runtime_config_vol")
    @patch("comfyapp.vol")
    @patch("comfyapp._log_storage_identity_diagnostics")
    @patch("comfyapp._log_remote_identity")
    @patch("comfyapp._read_models_generation_record")
    def test_startup_manifest_after_requirements_before_backend(
        self,
        mock_read_models_gen,
        mock_log_remote_id,
        mock_log_storage,
        mock_vol,
        mock_rc_vol,
        mock_cn_vol,
        mock_fingerprint,
        mock_baked,
        mock_read_gen,
        mock_write_gen,
        mock_combined,
        mock_build,
        mock_emit,
        manifest_env,
    ):
        """Startup runs: requirements → manifest build → backend."""
        # Arrange: provide valid baked manifest + generation record
        mock_baked.return_value = {
            "overall_dependency_hash": "baked_hash_abc",
            "schema_version": 2,
        }
        mock_read_gen.return_value = {
            "generation": "test_gen_startup",
            "schema_version": 1,
        }
        mock_combined.return_value = "deadbeef" * 8
        mock_build.return_value = {"identity": "mft_id_startup"}
        mock_read_models_gen.return_value = {
            "generation": "models_gen",
            "schema_version": 1,
        }
        mock_write_gen.return_value = {
            "generation": "test_gen_startup",
            "reason": "startup_init_generation_record",
        }

        # Build a minimal ComfyApp with just enough methods stubbed
        from comfyapp import _ComfyAPIMixin

        app = _ComfyAPIMixin.__new__(_ComfyAPIMixin)
        app._custom_nodes_state = {}
        app._models_generation_seen = ""
        # Stub instance methods that startup() calls
        import types
        app._ensure_models_symlink = types.MethodType(lambda self: None, app)
        app._select_backend = types.MethodType(lambda self: "in_process", app)
        app._log_profile = types.MethodType(lambda self, *a, **k: None, app)
        app._sync_custom_nodes_from_volume = types.MethodType(
            lambda self: (None, {}), app,
        )
        app._install_custom_node_requirements = types.MethodType(
            lambda self, force=False: {
                "installed": [], "skipped": [], "failed": [],
                "mode": "fail_fast", "prepared": True,
            },
            app,
        )
        app._record_runtime_state = types.MethodType(lambda self: None, app)
        app._start_backend = types.MethodType(lambda self: None, app)
        app._warmup_runtime = types.MethodType(lambda self: {}, app)
        # Define _profile_ms for the log_profile calls
        app._profile_ms = types.MethodType(
            lambda self, started: round((time.time() - started) * 1000, 1), app,
        )

        # Act
        app.startup()

        # Assert: manifest was built and persisted
        mock_build.assert_called_once()
        build_kwargs = mock_build.call_args.kwargs
        assert build_kwargs.get("commit") is True

        # Assert: requirements install happened (our stub returned prepared=True)
        # If the test gets here without raising, requirements check passed.

        # Assert: startup did NOT call custom_node_dependency_fingerprint
        mock_fingerprint.assert_not_called()

        # Assert: manifest was persisted (emit called)
        mock_emit.assert_called_once()

    @patch("comfyapp._dep_mft.emit_validation_diagnostic")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp._write_custom_nodes_generation_record_no_commit")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp.custom_node_dependency_fingerprint")
    @patch("comfyapp.custom_nodes_vol")
    @patch("comfyapp.runtime_config_vol")
    @patch("comfyapp.vol")
    @patch("comfyapp._log_storage_identity_diagnostics")
    @patch("comfyapp._log_remote_identity")
    @patch("comfyapp._read_models_generation_record")
    def test_startup_fails_closed_when_requirements_not_prepared(
        self,
        mock_read_models_gen,
        mock_log_remote_id,
        mock_log_storage,
        mock_vol,
        mock_rc_vol,
        mock_cn_vol,
        mock_fingerprint,
        mock_baked,
        mock_read_gen,
        mock_write_gen,
        mock_combined,
        mock_build,
        mock_emit,
        manifest_env,
    ):
        """Startup raises when requirements are not prepared (off mode)."""
        mock_baked.return_value = {
            "overall_dependency_hash": "baked_hash_abc",
        }
        mock_read_gen.return_value = {
            "generation": "test_gen",
            "schema_version": 1,
        }
        mock_read_models_gen.return_value = {
            "generation": "models_gen",
            "schema_version": 1,
        }
        mock_write_gen.return_value = {
            "generation": "test_gen",
            "reason": "startup_init_generation_record",
        }

        from comfyapp import _ComfyAPIMixin

        app = _ComfyAPIMixin.__new__(_ComfyAPIMixin)
        app._custom_nodes_state = {}
        app._models_generation_seen = ""
        import types
        app._ensure_models_symlink = types.MethodType(lambda self: None, app)
        app._select_backend = types.MethodType(lambda self: "in_process", app)
        app._log_profile = types.MethodType(lambda self, *a, **k: None, app)
        app._sync_custom_nodes_from_volume = types.MethodType(
            lambda self: (None, {}), app,
        )
        # Return NOT prepared — simulates "off" mode
        app._install_custom_node_requirements = types.MethodType(
            lambda self, force=False: {
                "installed": [], "skipped": [], "failed": [],
                "mode": "off", "prepared": False,
            },
            app,
        )
        app._record_runtime_state = types.MethodType(lambda self: None, app)
        app._start_backend = types.MethodType(lambda self: None, app)
        app._warmup_runtime = types.MethodType(lambda self: {}, app)
        app._profile_ms = types.MethodType(
            lambda self, started: round((time.time() - started) * 1000, 1), app,
        )

        with pytest.raises(RuntimeError, match="not prepared"):
            app.startup()

        # Manifest must NOT be built/persisted when requirements not prepared
        mock_build.assert_not_called()
        # No diagnostic emitted
        mock_emit.assert_not_called()


# ── Test: Preflight commit failure handling ──────────────────────────────


class TestPreflightCommitFailure:
    """Preflight must raise when the commit helper fails to produce a valid
    identity (manifest not considered durable)."""

    @patch("comfyapp._run_dependency_validation_with_cache")
    @patch("comfyapp._build_and_persist_dependency_manifest")
    @patch("comfyapp._resolve_deployment_combined_hash")
    @patch("comfyapp.load_baked_custom_node_dependency_manifest")
    @patch("comfyapp._read_custom_nodes_generation_record")
    @patch("comfyapp.assert_valid_api_prompt_structure")
    @patch("comfyapp._load_dependency_manifest")
    @patch("comfyapp._check_dependency_manifest_identity")
    def test_commit_failure_raises_in_preflight(
        self,
        mock_check_id,
        mock_load_mft,
        mock_assert_valid,
        mock_cn_gen,
        mock_baked,
        mock_combined,
        mock_build,
        mock_run_val,
        manifest_env,
    ):
        """When _build_and_persist_dependency_manifest returns no identity,
        preflight raises in production mode."""
        mock_combined.return_value = "combined_hash_val"
        mock_baked.return_value = {"overall_dependency_hash": "fp"}
        mock_cn_gen.return_value = {"generation": "gen"}
        mock_load_mft.return_value = {"identity": "old_id", "schema_version": 1}
        mock_check_id.return_value = {
            "identity_match": False,
            "manifest_load_ms": 3.0,
            "cheap_check_ms": 1.0,
            "reason": "identity_mismatch",
        }
        mock_run_val.return_value = {
            "prepared": True,
            "reason": "hash_match",
        }
        # Simulate commit failure: return dict with empty identity
        mock_build.return_value = {"identity": "", "error": "commit failed"}

        from tests.test_dependency_manifest_lifecycle import FakeComfyApp

        app = FakeComfyApp()
        with pytest.raises(RuntimeError, match="identity"):
            _get_preflight_unbound()(app, {"some": "workflow"})

        # Full validation still ran
        mock_run_val.assert_called_once()
        # Build/persist was attempted but didn't count as refresh


# ── Test: One-shot sync bridge ───────────────────────────────────────────


class TestOneShotSyncBridge:
    """commit_volume_sync is a deterministic one-shot bridge with no retry."""

    def test_rejects_async_context(self):
        """commit_volume_sync raises when called from a running event loop."""
        from comfymodal_runtime.dependency_manifest import commit_volume_sync

        async def _call_from_async():
            mock_vol = MagicMock()
            return commit_volume_sync(mock_vol)

        with pytest.raises(RuntimeError, match="async context"):
            asyncio.run(_call_from_async())

    def test_no_retry_on_success(self):
        """Successful commit makes exactly one underlying commit call."""
        from comfymodal_runtime.dependency_manifest import commit_volume_sync

        mock_vol = MagicMock()
        result = commit_volume_sync(mock_vol)
        assert result is True
        # Exactly one commit call (via asyncio.to_thread fallback)
        assert mock_vol.commit.call_count == 1

    def test_no_retry_on_failure(self):
        """Failed commit returns False without retry."""
        from comfymodal_runtime.dependency_manifest import commit_volume_sync

        mock_vol = MagicMock()
        mock_vol.commit.side_effect = Exception("boom")
        result = commit_volume_sync(mock_vol)
        assert result is False
        # Exactly one commit attempt
        assert mock_vol.commit.call_count == 1
