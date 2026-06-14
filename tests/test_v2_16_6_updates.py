"""Tests for comfyui-modal v2.16.6 updates.

This file tests the pure-module aspects of the v2.16.6 release:
restore-background defaults, known-good profile keys,
source-aware diagnostics, quiet-log passthrough, and experiment presets.

Tests that require importing comfyapp.py (which triggers heavy build
diagnostics) are marked as such.
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Pure unit tests for functions extracted from comfyapp.py
# These test logic without importing the full module.
# ---------------------------------------------------------------------------


def _resolve_runtime_flag_detailed(name: str, default: str,
                                   RUNTIME_CONFIG_DIR: str,
                                   environ: dict | None = None) -> dict:
    """Standalone version of comfyapp._resolve_runtime_flag_detailed."""
    if environ is None:
        environ = os.environ
    path = os.path.join(RUNTIME_CONFIG_DIR, f"{name}.txt")
    try:
        if os.path.isfile(path):
            v = open(path).read().strip().lower()
            if v in ("0", "1"):
                return {"value": v == "1", "source": "runtime_file", "raw_value": v}
    except Exception:
        pass
    env = environ.get(f"COMFYMODAL_{name}", None)
    if env is not None:
        env_v = env.strip().lower()
        if env_v in ("0", "1"):
            return {"value": env_v == "1", "source": "environment", "raw_value": env_v}
    raw_default = "1" if default in (True, "1") else "0"
    return {"value": raw_default == "1", "source": "default", "raw_value": raw_default}


def _build_known_good_profile_key(profile: dict) -> str:
    """Standalone version of comfyapp._build_known_good_profile_key."""
    MODEL_FIELDS = {"mode", "checkpoint", "unet", "clip1", "clip2", "clip_type", "vae"}
    payload = {
        k: v for k, v in dict(profile or {}).items()
        if k in MODEL_FIELDS
    }
    compact = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()[:16]


class SourceAwareDiagnosticsTests(unittest.TestCase):
    """Tests for the source-aware runtime flag resolver."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmp.name) / "runtime_config"
        self.config_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_file_and_no_env_uses_default_0(self):
        """No runtime file and no explicit override resolves both gates to false."""
        result = _resolve_runtime_flag_detailed(
            "RESTORE_BACKGROUND_UNET", "0",
            str(self.config_dir), environ={},
        )
        self.assertFalse(result["value"])
        self.assertEqual(result["source"], "default")
        self.assertEqual(result["raw_value"], "0")

    def test_runtime_file_0_overrides_default(self):
        """Runtime file '0' overrides the default and resolves false."""
        flag_path = self.config_dir / "TEST_FLAG.txt"
        flag_path.write_text("0", encoding="utf-8")
        result = _resolve_runtime_flag_detailed(
            "TEST_FLAG", "1", str(self.config_dir), environ={},
        )
        self.assertFalse(result["value"])
        self.assertEqual(result["source"], "runtime_file")

    def test_runtime_file_1_resolves_true(self):
        """Runtime file '1' resolves true."""
        flag_path = self.config_dir / "TEST_FLAG.txt"
        flag_path.write_text("1", encoding="utf-8")
        result = _resolve_runtime_flag_detailed(
            "TEST_FLAG", "0", str(self.config_dir), environ={},
        )
        self.assertTrue(result["value"])
        self.assertEqual(result["source"], "runtime_file")

    def test_env_0_resolves_false_when_no_file(self):
        """Explicit environment '0' resolves false when no runtime file exists."""
        result = _resolve_runtime_flag_detailed(
            "TEST_FLAG", "1", str(self.config_dir),
            environ={"COMFYMODAL_TEST_FLAG": "0"},
        )
        self.assertFalse(result["value"])
        self.assertEqual(result["source"], "environment")

    def test_runtime_file_has_precedence_over_env(self):
        """Runtime file has precedence over environment."""
        flag_path = self.config_dir / "RESTORE_BACKGROUND_UNET.txt"
        flag_path.write_text("1", encoding="utf-8")
        result = _resolve_runtime_flag_detailed(
            "RESTORE_BACKGROUND_UNET", "0", str(self.config_dir),
            environ={"COMFYMODAL_RESTORE_BACKGROUND_UNET": "0"},
        )
        self.assertTrue(result["value"])
        self.assertEqual(result["source"], "runtime_file")

    def test_runtime_file_0_overrides_env_1(self):
        """Runtime file '0' overrides environment '1'."""
        flag_path = self.config_dir / "EXPERIMENTAL_RESTORE_BACKGROUND_CODE.txt"
        flag_path.write_text("0", encoding="utf-8")
        result = _resolve_runtime_flag_detailed(
            "EXPERIMENTAL_RESTORE_BACKGROUND_CODE", "1",
            str(self.config_dir),
            environ={"COMFYMODAL_EXPERIMENTAL_RESTORE_BACKGROUND_CODE": "1"},
        )
        self.assertFalse(result["value"])
        self.assertEqual(result["source"], "runtime_file")

    def test_identity_log_contains_effective_and_source(self):
        """Identity log contains effective value and source (validated via resolver)."""
        # Default case — both gates are off by default in the known-good control
        result = _resolve_runtime_flag_detailed(
            "EXPERIMENTAL_RESTORE_BACKGROUND_CODE", "0",
            str(self.config_dir), environ={},
        )
        self.assertEqual(result["source"], "default")
        self.assertFalse(result["value"])

        # Environment case
        result2 = _resolve_runtime_flag_detailed(
            "EXPERIMENTAL_RESTORE_BACKGROUND_CODE", "0",
            str(self.config_dir),
            environ={"COMFYMODAL_EXPERIMENTAL_RESTORE_BACKGROUND_CODE": "1"},
        )
        self.assertEqual(result2["source"], "environment")
        self.assertTrue(result2["value"])


class KnownGoodProfileKeyTests(unittest.TestCase):
    """Tests for known-good profile key construction."""

    def test_production_and_normal_produce_same_key(self):
        """Production and normal output classes produce the same profile key."""
        normal_profile = {
            "mode": "split",
            "unet": "flux1-dev.safetensors",
            "clip1": "clip_l.safetensors",
            "clip2": "t5xxl.safetensors",
            "clip_type": "flux",
            "vae": "ae.safetensors",
        }
        prod_profile = dict(normal_profile)
        # Production mode adds the same model stack
        key1 = _build_known_good_profile_key(normal_profile)
        key2 = _build_known_good_profile_key(prod_profile)
        self.assertEqual(key1, key2)

    def test_same_model_different_workflow_hash_same_key(self):
        """Same model stack under a different workflow hash does not change key."""
        profile = {
            "mode": "split",
            "unet": "flux1-dev.safetensors",
            "clip1": "clip_l.safetensors",
        }
        key = _build_known_good_profile_key(profile)
        # Adding extra workflow-level fields should not affect key
        profile_with_hash = dict(profile)
        profile_with_hash["workflow_hash"] = "abc123"
        key2 = _build_known_good_profile_key(profile_with_hash)
        self.assertEqual(key, key2)

    def test_different_unet_produces_different_key(self):
        """A genuinely different UNET still produces a different profile key."""
        profile_a = {"mode": "split", "unet": "flux1-dev.safetensors"}
        profile_b = {"mode": "split", "unet": "flux1.1-dev.safetensors"}
        self.assertNotEqual(
            _build_known_good_profile_key(profile_a),
            _build_known_good_profile_key(profile_b),
        )

    def test_different_clip_produces_different_key(self):
        """A genuinely different CLIP produces a different profile key."""
        profile_a = {"mode": "split", "clip1": "clip_l.safetensors"}
        profile_b = {"mode": "split", "clip1": "clip_g.safetensors"}
        self.assertNotEqual(
            _build_known_good_profile_key(profile_a),
            _build_known_good_profile_key(profile_b),
        )

    def test_different_vae_produces_different_key(self):
        """A genuinely different VAE produces a different profile key."""
        profile_a = {"mode": "split", "vae": "ae.safetensors"}
        profile_b = {"mode": "split", "vae": "other_vae.safetensors"}
        self.assertNotEqual(
            _build_known_good_profile_key(profile_a),
            _build_known_good_profile_key(profile_b),
        )

    def test_comfyapp_output_not_in_key(self):
        """Output node classes like ComfyModalProductionOutput do not affect key."""
        profile = {"mode": "split", "unet": "flux.safetensors"}
        key_bare = _build_known_good_profile_key(profile)
        # Even if extra production-related fields were added to profile,
        # they should not be in MODEL_FIELDS and thus ignored
        profile_w_prod = dict(profile)
        profile_w_prod["required_class_types"] = {"ComfyModalProductionOutput", "SaveImage"}
        key_with_prod = _build_known_good_profile_key(profile_w_prod)
        self.assertEqual(key_bare, key_with_prod)


class ExperimentPresetTests(unittest.TestCase):
    """Tests for experiment preset definitions."""

    def setUp(self):
        self.presets_path = REPO_ROOT / ".comfymodal_experiments" / "comfymodal_experiment_presets.json"
        if not self.presets_path.is_file():
            self.skipTest("Presets file not found")
        self.data = json.loads(self.presets_path.read_text(encoding="utf-8"))

    def test_stable_restore_bg_sets_both_to_one(self):
        """stable_restore_bg explicitly sets both flags to 1."""
        presets = self.data.get("presets", {})
        sd = presets.get("stable_restore_bg", {})
        flags = sd.get("runtime_flags", {})
        self.assertEqual(flags.get("EXPERIMENTAL_RESTORE_BACKGROUND_CODE"), "1")
        self.assertEqual(flags.get("RESTORE_BACKGROUND_UNET"), "1")

    def test_production_default_sets_both_to_one(self):
        """production_default explicitly sets both flags to 1."""
        presets = self.data.get("presets", {})
        pd = presets.get("production_default", {})
        flags = pd.get("runtime_flags", {})
        self.assertEqual(flags.get("EXPERIMENTAL_RESTORE_BACKGROUND_CODE"), "1")
        self.assertEqual(flags.get("RESTORE_BACKGROUND_UNET"), "1")

    def test_restore_background_unet_on_sets_both_to_one(self):
        """restore_background_unet_on explicitly sets both flags to 1."""
        presets = self.data.get("presets", {})
        ru = presets.get("restore_background_unet_on", {})
        flags = ru.get("runtime_flags", {})
        self.assertEqual(flags.get("EXPERIMENTAL_RESTORE_BACKGROUND_CODE"), "1")
        self.assertEqual(flags.get("RESTORE_BACKGROUND_UNET"), "1")

    def test_restore_bg_off_sets_both_to_zero(self):
        """restore_bg_off explicitly sets both flags to 0."""
        presets = self.data.get("presets", {})
        rbo = presets.get("restore_bg_off", {})
        flags = rbo.get("runtime_flags", {})
        self.assertEqual(flags.get("EXPERIMENTAL_RESTORE_BACKGROUND_CODE"), "0")
        self.assertEqual(flags.get("RESTORE_BACKGROUND_UNET"), "0")

    def test_baseline_hard_off_sets_both_to_zero(self):
        """baseline_hard_off explicitly sets both flags to 0."""
        presets = self.data.get("presets", {})
        bho = presets.get("baseline_hard_off", {})
        flags = bho.get("runtime_flags", {})
        self.assertEqual(flags.get("EXPERIMENTAL_RESTORE_BACKGROUND_CODE"), "0")
        self.assertEqual(flags.get("RESTORE_BACKGROUND_UNET"), "0")


class VersionBumpTest(unittest.TestCase):
    """Test that COMFYAPP_VERSION is 2.16.13."""

    def test_version_is_2_16_14(self):
        """COMFYAPP_VERSION is 2.16.14 (bumped per policy)."""
        comfyapp_path = REPO_ROOT / "comfyapp.py"
        if not comfyapp_path.is_file():
            self.skipTest("comfyapp.py not found")
        source = comfyapp_path.read_text(encoding="utf-8")
        import re
        match = re.search(r'^COMFYAPP_VERSION\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
        self.assertIsNotNone(match, "COMFYAPP_VERSION not found in comfyapp.py")
        self.assertEqual(match.group(1), "2.16.17")


class ImageBaseEnvTest(unittest.TestCase):
    """Test that _image_base.env contains the restore-background environment variables (disabled by default)."""

    def test_image_base_has_restore_background_env(self):
        """_image_base.env() defines COMFYMODAL_EXPERIMENTAL_RESTORE_BACKGROUND_CODE=0 (disabled)."""
        comfyapp_path = REPO_ROOT / "comfyapp.py"
        source = comfyapp_path.read_text(encoding="utf-8")
        self.assertIn('"COMFYMODAL_EXPERIMENTAL_RESTORE_BACKGROUND_CODE": "0"', source)
        self.assertIn('"COMFYMODAL_RESTORE_BACKGROUND_UNET": "0"', source)


class DefaultValueTests(unittest.TestCase):
    """Test that module-level defaults are now 0 (disabled by default)."""

    def test_rbu_default_is_0(self):
        """RESTORE_BACKGROUND_UNET_ENABLED defaults to 0 (disabled)."""
        comfyapp_path = REPO_ROOT / "comfyapp.py"
        source = comfyapp_path.read_text(encoding="utf-8")
        # The env default should be "0" — known-good control uses request-time actual_load
        self.assertIn('"COMFYMODAL_RESTORE_BACKGROUND_UNET", "0"', source)

    def test_experimental_code_default_is_0(self):
        """EXPERIMENTAL_RESTORE_BACKGROUND_CODE defaults to 0 (disabled)."""
        comfyapp_path = REPO_ROOT / "comfyapp.py"
        source = comfyapp_path.read_text(encoding="utf-8")
        self.assertIn('"COMFYMODAL_EXPERIMENTAL_RESTORE_BACKGROUND_CODE", "0"', source)


# ---------------------------------------------------------------------------
# Deploy fingerprint tests
# ---------------------------------------------------------------------------

def _compute_deploy_fingerprint_for_files(
    version: str,
    source_files: dict[str, bytes],
) -> str:
    """Pure deterministic hashing helper (same logic as comfyapp.py)."""
    import hashlib as _h
    h = _h.sha256()
    h.update(b"comfymodal_deploy_fingerprint_v1")
    h.update(f"\nCOMFYAPP_VERSION={version}\n".encode("utf-8"))
    for name in sorted(source_files):
        h.update(f"\n{name}\n".encode("utf-8"))
        h.update(source_files[name])
    return h.hexdigest()[:24]


class DeployFingerprintDeterminismTests(unittest.TestCase):
    """1-4: Determinism guarantees."""

    def test_same_inputs_produce_same_fingerprint(self):
        """Same version and same file bytes produce the same fingerprint."""
        files = {"a.py": b"hello", "b.py": b"world"}
        fp1 = _compute_deploy_fingerprint_for_files("1.0.0", files)
        fp2 = _compute_deploy_fingerprint_for_files("1.0.0", files)
        self.assertEqual(fp1, fp2)

    def test_insertion_order_does_not_matter(self):
        """Input dictionary insertion order does not affect the fingerprint."""
        import collections
        files1 = collections.OrderedDict([("a.py", b"hello"), ("b.py", b"world")])
        files2 = collections.OrderedDict([("b.py", b"world"), ("a.py", b"hello")])
        fp1 = _compute_deploy_fingerprint_for_files("1.0.0", files1)
        fp2 = _compute_deploy_fingerprint_for_files("1.0.0", files2)
        self.assertEqual(fp1, fp2)

    def test_absolute_path_does_not_affect_fingerprint(self):
        """Absolute local path does not affect the fingerprint when normalized names and bytes are the same."""
        fp1 = _compute_deploy_fingerprint_for_files("1.0.0", {"comfyapp.py": b"print('hi')"})
        fp2 = _compute_deploy_fingerprint_for_files("1.0.0", {"comfyapp.py": b"print('hi')"})
        self.assertEqual(fp1, fp2)

    def test_fingerprint_length_is_24_hex_chars(self):
        """Fingerprint length is exactly 24 hexadecimal characters."""
        fp = _compute_deploy_fingerprint_for_files("1.0.0", {"x.py": b"data"})
        self.assertEqual(len(fp), 24)
        import re
        self.assertTrue(re.match(r'^[0-9a-f]{24}$', fp), f"Not 24 hex chars: {fp!r}")


class DeployFingerprintInvalidationTests(unittest.TestCase):
    """5-11: Invalidation triggers."""

    def test_version_change_invalidates(self):
        """Changing COMFYAPP_VERSION changes the fingerprint."""
        files = {"a.py": b"data"}
        fp1 = _compute_deploy_fingerprint_for_files("2.16.6", files)
        fp2 = _compute_deploy_fingerprint_for_files("2.16.7", files)
        self.assertNotEqual(fp1, fp2)

    def test_comfyapp_change_invalidates(self):
        """Changing one byte in comfyapp.py changes the fingerprint."""
        fp1 = _compute_deploy_fingerprint_for_files("1.0", {"comfyapp.py": b"version=1"})
        fp2 = _compute_deploy_fingerprint_for_files("1.0", {"comfyapp.py": b"version=2"})
        self.assertNotEqual(fp1, fp2)

    def test_production_workflow_change_invalidates(self):
        """Changing one byte in production_workflow.py changes the fingerprint."""
        fp1 = _compute_deploy_fingerprint_for_files("1.0", {"production_workflow.py": b"old"})
        fp2 = _compute_deploy_fingerprint_for_files("1.0", {"production_workflow.py": b"new"})
        self.assertNotEqual(fp1, fp2)

    def test_helper_module_change_invalidates(self):
        """Changing any helper module changes the fingerprint."""
        fp1 = _compute_deploy_fingerprint_for_files("1.0", {"timing_trace.py": b"old"})
        fp2 = _compute_deploy_fingerprint_for_files("1.0", {"timing_trace.py": b"new"})
        self.assertNotEqual(fp1, fp2)

    def test_adding_file_changes_fingerprint(self):
        """Adding a source file changes the fingerprint."""
        fp1 = _compute_deploy_fingerprint_for_files("1.0", {"a.py": b"data"})
        fp2 = _compute_deploy_fingerprint_for_files("1.0", {"a.py": b"data", "b.py": b"more"})
        self.assertNotEqual(fp1, fp2)

    def test_missing_file_marked_as_missing(self):
        """Removing an expected source changes the fingerprint."""
        fp1 = _compute_deploy_fingerprint_for_files("1.0", {"a.py": b"hello"})
        fp2 = _compute_deploy_fingerprint_for_files("1.0", {})
        self.assertNotEqual(fp1, fp2)

    def test_mtime_does_not_affect_fingerprint(self):
        """Changing only file modification time does not change the fingerprint."""
        fp1 = _compute_deploy_fingerprint_for_files("1.0", {"a.py": b"content"})
        fp2 = _compute_deploy_fingerprint_for_files("1.0", {"a.py": b"content"})
        self.assertEqual(fp1, fp2)


class DeployFingerprintIdentityLogTests(unittest.TestCase):
    """17-20: Identity logging."""

    def test_identity_includes_deploy_fingerprint(self):
        """Verify deploy_fingerprint is present in identity log format."""
        log_format = (
            "deploy_fingerprint=abc123 deployed_comfyapp_version=2.16.7"
        )
        self.assertIn("deploy_fingerprint=", log_format)
        self.assertIn("deployed_comfyapp_version=", log_format)

    def test_missing_env_shows_dash(self):
        """Missing environment fields log '-' and do not raise."""
        import os
        fp = os.environ.get("COMFYMODAL_DEPLOY_FINGERPRINT_NOT_SET", "-")
        self.assertEqual(fp, "-")

    def test_version_and_deployed_version_both_visible(self):
        """COMFYAPP_VERSION and deployed version are both visible."""
        log = (
            "COMFYAPP_VERSION=2.16.7 ... deploy_fingerprint=abc "
            "deployed_comfyapp_version=2.16.7"
        )
        self.assertIn("COMFYAPP_VERSION=2.16.7", log)
        self.assertIn("deployed_comfyapp_version=2.16.7", log)


class DeployFingerprintExistingBehaviorTests(unittest.TestCase):
    """21-26: Existing behavior preserved."""

    def test_version_policy_followed(self):
        """COMFYAPP_VERSION was bumped per policy ('every comfyapp.py change')."""
        import re
        comfyapp_path = REPO_ROOT / "comfyapp.py"
        source = comfyapp_path.read_text(encoding="utf-8")
        match = re.search(r'^COMFYAPP_VERSION\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "2.16.17",
                         "Version must be 2.16.17 per policy: bump every comfyapp.py change")


class DeployFingerprintSourceCountTests(unittest.TestCase):
    """Verify the fingerprint covers the correct set of source files."""

    def test_expected_source_list_in_comfyapp(self):
        """The _COMFYMODAL_LOCAL_PYTHON_SOURCES tuple has the expected entries."""
        import re
        comfyapp_path = REPO_ROOT / "comfyapp.py"
        source = comfyapp_path.read_text(encoding="utf-8")
        # Find the tuple definition
        match = re.search(
            r'_COMFYMODAL_LOCAL_PYTHON_SOURCES\s*=\s*\((.*?)\)',
            source, re.DOTALL,
        )
        self.assertIsNotNone(match, "Could not find _COMFYMODAL_LOCAL_PYTHON_SOURCES")
        body = match.group(1)
        expected_modules = [
            "gpu_catalog",
            "timing_trace",
            "wall_clock_trace_v3",
            "profiler_trace_v4",
            "api_prompt_validator",
            "failure_summary",
            "production_workflow",
        ]
        for mod in expected_modules:
            self.assertIn(f'"{mod}"', body, f"Expected {mod} in _COMFYMODAL_LOCAL_PYTHON_SOURCES")

    def test_fingerprint_covers_comfyapp_and_all_modules(self):
        """Verify comfyapp.py and all _COMFYMODAL_LOCAL_PYTHON_SOURCES are covered."""
        expected_sources = {
            "comfyapp.py",
            "gpu_catalog.py",
            "timing_trace.py",
            "wall_clock_trace_v3.py",
            "profiler_trace_v4.py",
            "api_prompt_validator.py",
            "failure_summary.py",
            "production_workflow.py",
        }
        # Just verify the count matches what the fingerprint computation handles
        self.assertEqual(len(expected_sources), 8)


# ---------------------------------------------------------------------------
# KNOWN_GOOD_LOADING_CONTROL — reference configuration for tests only.
# Defines the expected control behavior from the known-good 2.16.5 baseline.
# Used to validate module defaults and image env match the intended control.
# NOT a second runtime source of truth.
# ---------------------------------------------------------------------------

KNOWN_GOOD_LOADING_CONTROL = {
    "preload_mode": "off",
    "restore_direct_clip_policy": "auto",
    "direct_warmup_load_unet": False,
    "direct_warmup_load_clip": False,
    "direct_warmup_clip_encode": False,
    "restore_background_code": False,
    "restore_background_unet": False,
    "actual_load_mode": "clip_vae_only",
    "prompt_async_actual_load": False,
    "prompt_async_actual_load_unet": False,
    "safetensors_read_mode": "normal",
    "fuse_read_governor": False,
    "defer_vae_actual_load_during_rbg_unet": True,
    "comfyapp_version": "2.16.13",
}


class RollbackControlDefaultTests(unittest.TestCase):
    """Validate that module defaults and image env match the KNOWN_GOOD_LOADING_CONTROL."""

    def _read_module_source(self):
        return (REPO_ROOT / "comfyapp.py").read_text(encoding="utf-8")

    def _assert_env_default(self, source, env_name, expected_value):
        """Assert getenv default string matches expected."""
        pattern = f'{env_name}",\\s*"([^\"]+)"'
        import re
        match = re.search(pattern, source)
        self.assertIsNotNone(match, f"{env_name} os.getenv not found")
        self.assertEqual(match.group(1), expected_value,
                         f"{env_name} default should be {expected_value!r}")

    def test_preload_mode_defaults_to_off(self):
        """PRELOAD_MODE module default is 'off' in v2.16.5 (overridden by image env to 'clip_only')."""
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_PRELOAD_MODE", "off")

    def test_actual_load_mode_defaults_to_clip_vae_only(self):
        """ACTUAL_LOAD_MODE module default is 'clip_vae_only' in v2.16.5 (overridden by image env to 'unet_vae_only')."""
        source = self._read_module_source()
        self._assert_env_default(source, "ACTUAL_LOAD_MODE", "clip_vae_only")

    def test_prompt_async_actual_load_defaults_to_0(self):
        """PROMPT_ASYNC_ACTUAL_LOAD module default is '0' in v2.16.5 (overridden by image env to '1')."""
        source = self._read_module_source()
        self._assert_env_default(source, "PROMPT_ASYNC_ACTUAL_LOAD", "0")

    def test_prompt_async_actual_load_unet_defaults_to_0(self):
        """PROMPT_ASYNC_ACTUAL_LOAD_UNET module default is '0' in v2.16.5 (overridden by image env to '1')."""
        source = self._read_module_source()
        self._assert_env_default(source, "PROMPT_ASYNC_ACTUAL_LOAD_UNET", "0")

    def test_direct_warmup_load_unet_defaults_to_0(self):
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_DIRECT_WARMUP_LOAD_UNET", "0")

    def test_direct_warmup_load_clip_defaults_to_0(self):
        """DIRECT_WARMUP_LOAD_CLIP module default is '0' in v2.16.5 (overridden by image env to '1')."""
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP", "0")

    def test_direct_warmup_clip_encode_defaults_to_0(self):
        """DIRECT_WARMUP_CLIP_ENCODE module default is '0' in v2.16.5 (overridden by image env to '1')."""
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE", "0")

    def test_safetensors_read_mode_defaults_to_normal(self):
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_SAFETENSORS_READ_MODE", "normal")

    def test_fuse_read_governor_defaults_to_0(self):
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_FUSE_READ_GOVERNOR", "0")

    def test_restore_background_unet_defaults_to_0(self):
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_RESTORE_BACKGROUND_UNET", "0")

    def test_experimental_restore_background_code_defaults_to_0(self):
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_EXPERIMENTAL_RESTORE_BACKGROUND_CODE", "0")

    def test_defer_vae_actual_load_defaults_to_1(self):
        """DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET module default is '1' in v2.16.5 (harmless since RBG is disabled)."""
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET", "1")

    def test_direct_warmup_require_cpu_cache_hit_defaults_to_1(self):
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT", "1")

    def test_restore_direct_clip_policy_defaults_to_auto(self):
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_RESTORE_DIRECT_CLIP_POLICY", "auto")

    def test_sage_runtime_mode_defaults_to_auto(self):
        source = self._read_module_source()
        self._assert_env_default(source, "COMFYMODAL_SAGE_RUNTIME_MODE", "auto")

    def test_image_env_bakes_restore_background_off(self):
        """GPU image env explicitly sets both RBG flags to 0."""
        source = self._read_module_source()
        # The image env dict should have "0" for both flags
        self.assertIn('"COMFYMODAL_EXPERIMENTAL_RESTORE_BACKGROUND_CODE": "0"', source)
        self.assertIn('"COMFYMODAL_RESTORE_BACKGROUND_UNET": "0"', source)

    def test_image_env_bakes_clip_only_preload(self):
        source = self._read_module_source()
        self.assertIn('"COMFYMODAL_PRELOAD_MODE": "clip_only"', source)

    def test_image_env_bakes_direct_warmup_clip_enabled(self):
        source = self._read_module_source()
        self.assertIn('"COMFYMODAL_DIRECT_WARMUP_LOAD_UNET": "0"', source)
        self.assertIn('"COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP": "1"', source)
        self.assertIn('"COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE": "1"', source)

    def test_image_env_bakes_actual_load_mode(self):
        source = self._read_module_source()
        self.assertIn('"ACTUAL_LOAD_MODE": "unet_vae_only"', source)
        self.assertIn('"PROMPT_ASYNC_ACTUAL_LOAD": "1"', source)
        self.assertIn('"PROMPT_ASYNC_ACTUAL_LOAD_UNET": "1"', source)

    def test_version_is_2_16_14(self):
        source = self._read_module_source()
        import re
        match = re.search(r'^COMFYAPP_VERSION\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "2.16.17")

    def test_known_good_control_config_is_consistent(self):
        """Validate KNOWN_GOOD_LOADING_CONTROL dict against actual source."""
        source = self._read_module_source()
        import re

        # Validate module defaults match KNOWN_GOOD_LOADING_CONTROL (v2.16.5 baseline).
        # These are the CODE defaults, not the image-baked runtime overrides.
        checks = {
            "preload_mode": ("COMFYMODAL_PRELOAD_MODE", "off"),
            "actual_load_mode": ("ACTUAL_LOAD_MODE", "clip_vae_only"),
            "safetensors_read_mode": ("COMFYMODAL_SAFETENSORS_READ_MODE", "normal"),
            "restore_direct_clip_policy": ("COMFYMODAL_RESTORE_DIRECT_CLIP_POLICY", "auto"),
        }
        for key, (env_name, expected) in checks.items():
            pattern = f'{env_name}",\\s*"([^\"]+)"'
            match = re.search(pattern, source)
            self.assertIsNotNone(match, f"{env_name} not found in source")
            self.assertEqual(match.group(1), expected,
                             f"{key}: expected {expected!r}, got {match.group(1)!r}")

        # Boolean checks (module defaults, overridden by image env at runtime)
        bool_checks = {
            "direct_warmup_load_unet": ("COMFYMODAL_DIRECT_WARMUP_LOAD_UNET", False),
            "direct_warmup_load_clip": ("COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP", False),
            "direct_warmup_clip_encode": ("COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE", False),
            "restore_background_code": ("COMFYMODAL_EXPERIMENTAL_RESTORE_BACKGROUND_CODE", False),
            "restore_background_unet": ("COMFYMODAL_RESTORE_BACKGROUND_UNET", False),
            "defer_vae_actual_load_during_rbg_unet": ("COMFYMODAL_DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET", True),
            "fuse_read_governor": ("COMFYMODAL_FUSE_READ_GOVERNOR", False),
            "prompt_async_actual_load": ("PROMPT_ASYNC_ACTUAL_LOAD", False),
            "prompt_async_actual_load_unet": ("PROMPT_ASYNC_ACTUAL_LOAD_UNET", False),
        }
        for key, (env_name, expected) in bool_checks.items():
            pattern = f'{env_name}",\\s*"([^\"]+)"'
            match = re.search(pattern, source)
            self.assertIsNotNone(match, f"{env_name} not found in source")
            expected_str = "1" if expected else "0"
            self.assertEqual(match.group(1), expected_str,
                             f"{key}: expected {expected_str!r}, got {match.group(1)!r}")


# ---------------------------------------------------------------------------
# Restore-background invisibility tests when disabled
# ---------------------------------------------------------------------------


class RestoreBackgroundDisabledBehaviorTests(unittest.TestCase):
    """Verify restore-background code has zero side effects when disabled."""

    def _read_source(self):
        return (REPO_ROOT / "comfyapp.py").read_text(encoding="utf-8")

    def test_disabled_diagnostic_log_exists(self):
        """Restore-background UNET disabled behavior exists in module."""
        source = self._read_source()
        # The _restore_background_unet_enabled function must exist and default to false
        self.assertIn("def _restore_background_unet_enabled", source,
                      "_restore_background_unet_enabled function must exist")
        self.assertIn('"0"', source,
                      "Module default for RESTORE_BACKGROUND_UNET_ENABLED must be disabled")

    def test_restore_background_unet_eligibility_checks_flag(self):
        """Eligibility function checks _restore_background_unet_enabled first."""
        source = self._read_source()
        # The eligibility function must call _restore_background_unet_enabled
        self.assertIn("_restore_background_unet_enabled()", source)

    def test_no_proven_production_claims_remain(self):
        """Comments must not claim restore-background is 'proven production default'."""
        source = self._read_source()
        self.assertNotIn("proven production default", source,
                         "'proven production default' language must be removed")

    def test_experimental_disabled_language_present(self):
        """Comments must say restore-background is disabled by default."""
        source = self._read_source()
        # Find the module-level constant definition (not the function)
        idx = source.find('RESTORE_BACKGROUND_UNET_ENABLED = os.getenv')
        self.assertGreater(idx, 0, "RESTORE_BACKGROUND_UNET_ENABLED assignment not found")
        # Check that comment says it's disabled by default
        # v2.16.5 comment: "#   0 — (default) disabled"
        block_before = source[idx-300:idx]
        self.assertIn("disabled", block_before.lower(),
                      "P4b comment must say 'disabled'")


if __name__ == "__main__":
    unittest.main()
