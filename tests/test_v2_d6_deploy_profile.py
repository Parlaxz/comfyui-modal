"""D6 fast-path deploy-profile validation tests (atomic opt-in gate).

The previous D6 remote run was INVALID because the deploy shell lacked the 8
D6 fast-path env vars, so the launcher's ``if not defined ... set ...=0`` pins
baked zeros into the container.  This suite covers the fix: a single explicit
opt-in profile (``V2_D6_FASTPATH_VALIDATION``) that forces the 8 values in
``deploy_and_run_v2_single.bat`` and a fail-fast ``--verify-d6-profile`` gate
that aborts the launcher BEFORE ``modal deploy`` when the effective values —
read from the ACTUAL ``modal_app._runtime_env()`` construction the deployment
bakes — drift from the expected map.

Dual-mode verifier contract:
  * Profile active (V2_D6_FASTPATH_VALIDATION = 1/true/yes/on) -> the eight
    flags MUST equal the fastpath map (1,1,1,1,1,1,1,0).
  * Profile absent -> the eight flags MUST equal the production defaults
    (0,0,0,0,0,0,1,0), so the launcher's always-on verify call is a trivial
    no-op PASS in default mode.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]

D6_KEYS: tuple[str, ...] = (
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA",
    "COMFYMODAL_V2_INPUT_TYPES_WARM",
    "COMFYMODAL_V2_UNET_FORENSICS",
)

# Must match deploy_and_run_v2_single.bat's D6 profile block AND the
# benchmark verifier's D6_FASTPATH_PROFILE.
D6_FASTPATH: dict[str, str] = {
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "1",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "1",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "1",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
}

# D10 integration-validation profile: D6 minus the intrusive per-load CUDA
# synchronization (SYNC_CUDA=0).  Must match the launcher's D10 block and the
# verifier's D10_FASTPATH_PROFILE.
D10_FASTPATH: dict[str, str] = dict(D6_FASTPATH)
D10_FASTPATH["COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA"] = "0"

E10_BUCKET_FIRST: dict[str, str] = {
    "COMFYMODAL_V2_STAGED_SAFETENSORS": "1",
    "COMFYMODAL_V2_STAGED_PRODUCERS": "4",
    "COMFYMODAL_V2_STAGED_POOL_MB": "1024",
    "COMFYMODAL_V2_STAGED_BUCKET_MB": "256",
    "COMFYMODAL_V2_STAGED_CPU_CAST": "1",
    "COMFYMODAL_V2_STAGED_ASYNC_H2D": "1",
    "COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS": "1",
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "1",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "1",
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "1",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "1",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
}

# The launcher pins these when the profile is absent (default behavior).
D6_PRODUCTION_DEFAULTS: dict[str, str] = {
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
}

_BVD: Any = None


def _bvd():
    """Lazy guarded import of the heavy benchmark harness module."""
    global _BVD
    if _BVD is None:
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        import tools.benchmark_v2_direct as _mod
        _BVD = _mod
    return _BVD


class _D6EnvBase(unittest.TestCase):
    """Save/restore the 8 D6 flags + profile toggle around every test."""

    _ENV_VARS: tuple[str, ...] = D6_KEYS + ("V2_D6_FASTPATH_VALIDATION",)

    def setUp(self):
        self._saved = {name: os.environ.get(name) for name in self._ENV_VARS}
        for name in self._ENV_VARS:
            os.environ.pop(name, None)
        self.bvd = _bvd()

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _set_profile(self, active: bool, flags: dict[str, str] | None = None):
        if active:
            os.environ["V2_D6_FASTPATH_VALIDATION"] = "1"
        for key, value in (flags or {}).items():
            os.environ[key] = value


class TestVerifyD6FastpathProfile(_D6EnvBase):
    """a/b/c) The verifier's dual-mode contract."""

    def test_profile_absent_preserves_defaults(self):
        ok, details = self.bvd.verify_d6_fastpath_profile()
        self.assertTrue(ok)
        self.assertEqual(details["validation"], "PASS")
        self.assertFalse(details["active"])
        for key, want in D6_PRODUCTION_DEFAULTS.items():
            self.assertEqual(details[key], want, key)

    def test_profile_enabled_exact_map(self):
        self._set_profile(True, D6_FASTPATH)
        ok, details = self.bvd.verify_d6_fastpath_profile()
        self.assertTrue(ok)
        self.assertEqual(details["validation"], "PASS")
        self.assertTrue(details["active"])
        for key, want in D6_FASTPATH.items():
            self.assertEqual(details[key], want, key)

    def test_wrong_value_fails_gate(self):
        flags = dict(D6_FASTPATH)
        flags["COMFYMODAL_V2_UNET_FASTSAFETENSORS"] = "0"
        self._set_profile(True, flags)
        ok, details = self.bvd.verify_d6_fastpath_profile()
        self.assertFalse(ok)
        self.assertEqual(details["validation"], "FAIL")
        self.assertEqual(details["COMFYMODAL_V2_UNET_FASTSAFETENSORS"], "0")

    def test_profile_active_tokens_recognized_case_insensitive(self):
        # true/yes/on (and mixed case) all activate the fastpath expectation,
        # which is NOT met when the 8 flags are cleared -> FAIL + active=True.
        for token in ("true", "yes", "on", "TRUE", "Yes"):
            os.environ["V2_D6_FASTPATH_VALIDATION"] = token
            ok, details = self.bvd.verify_d6_fastpath_profile()
            self.assertFalse(ok, token)
            self.assertTrue(details["active"], token)


class TestVerifyGoldenP1Profile(unittest.TestCase):
    """Golden uses the shared D6 gate with its own exact effective tuple."""

    def setUp(self):
        self.bvd = _bvd()
        self._env_vars = tuple(self.bvd.GOLDEN_P1_PROFILE) + (
            "COMFYMODAL_V2CTL_PROFILE",
            "V2_D6_FASTPATH_VALIDATION",
            "V2_D10_INTEGRATION_VALIDATION",
            "V2_E10_BUCKET_FIRST_VALIDATION",
            "V2_E19_FINAL_COLD_LOADER",
        )
        self._saved = {name: os.environ.get(name) for name in self._env_vars}
        for name in self._env_vars:
            os.environ.pop(name, None)

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _set_golden_profile(self):
        os.environ["COMFYMODAL_V2CTL_PROFILE"] = "golden_p1"
        os.environ.update(self.bvd.GOLDEN_P1_PROFILE)

    def test_golden_profile_accepts_effective_runtime_tuple(self):
        self._set_golden_profile()
        # _runtime_env() preserves this absent/empty UNET value; the verifier
        # must retain the existing empty-is-off normalization contract.
        os.environ["COMFYMODAL_V2_UNET_FASTSAFETENSORS"] = ""

        ok, details = self.bvd.verify_d6_fastpath_profile()

        self.assertTrue(ok, details)
        self.assertEqual(details["profile"], "golden_p1")
        self.assertEqual(details["validation"], "PASS")
        for key, expected in self.bvd.GOLDEN_P1_PROFILE.items():
            self.assertEqual(details[key], expected, key)

    def test_golden_profile_rejects_control_mismatch(self):
        self._set_golden_profile()
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"

        ok, details = self.bvd.verify_d6_fastpath_profile()

        self.assertFalse(ok)
        self.assertEqual(details["profile"], "golden_p1")
        self.assertEqual(details["validation"], "FAIL")
        self.assertEqual(details["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"], "1")


class TestRuntimeEnvEffectiveValues(_D6EnvBase):
    """d) _runtime_env() itself returns the effective 8 values."""

    def test_runtime_env_returns_profile_values(self):
        from comfymodal_runtime.modal_app import _runtime_env

        self._set_profile(True, D6_FASTPATH)
        env = _runtime_env()
        for key, want in D6_FASTPATH.items():
            self.assertEqual(str(env.get(key, "") or ""), want, key)

    def test_runtime_env_defaults_without_profile(self):
        from comfymodal_runtime.modal_app import _runtime_env

        env = _runtime_env()
        for key, want in D6_PRODUCTION_DEFAULTS.items():
            self.assertEqual(self.bvd._d6_normalize(env.get(key)), want, key)


class TestVerifyD10IntegrationProfile(_D6EnvBase):
    """D10 integration-validation profile: D6 minus SYNC_CUDA (measurement
    integrity).  The verifier is profile-aware; D10 takes precedence."""

    _ENV_VARS: tuple[str, ...] = D6_KEYS + (
        "V2_D6_FASTPATH_VALIDATION",
        "V2_D10_INTEGRATION_VALIDATION",
    )

    def test_d10_profile_enabled_exact_map(self):
        os.environ["V2_D10_INTEGRATION_VALIDATION"] = "1"
        os.environ.update(D10_FASTPATH)
        ok, details = self.bvd.verify_d6_fastpath_profile()
        self.assertTrue(ok)
        self.assertEqual(details["validation"], "PASS")
        self.assertTrue(details["active"])
        self.assertEqual(details["profile"], "d10_integration_validation")
        for key, want in D10_FASTPATH.items():
            self.assertEqual(details[key], want, key)

    def test_d10_takes_precedence_over_d6(self):
        os.environ["V2_D10_INTEGRATION_VALIDATION"] = "1"
        os.environ["V2_D6_FASTPATH_VALIDATION"] = "1"
        os.environ.update(D10_FASTPATH)
        ok, details = self.bvd.verify_d6_fastpath_profile()
        self.assertTrue(ok)
        self.assertEqual(details["profile"], "d10_integration_validation")
        self.assertEqual(details["COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA"], "0")

    def test_d10_wrong_sync_value_fails_gate(self):
        os.environ["V2_D10_INTEGRATION_VALIDATION"] = "1"
        os.environ.update(D10_FASTPATH)
        os.environ["COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA"] = "1"
        ok, details = self.bvd.verify_d6_fastpath_profile()
        self.assertFalse(ok)
        self.assertEqual(details["validation"], "FAIL")
        self.assertEqual(details["COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA"], "1")

    def test_d10_absent_falls_back_to_d6_contract(self):
        # D10 flag absent + D6 profile active -> D6 map (SYNC_CUDA=1 expected).
        self._set_profile(True, D6_FASTPATH)
        ok, details = self.bvd.verify_d6_fastpath_profile()
        self.assertTrue(ok)
        self.assertEqual(details["profile"], "fastpath_validation")
        self.assertEqual(details["COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA"], "1")

    def test_runtime_env_returns_d10_values(self):
        from comfymodal_runtime.modal_app import _runtime_env

        os.environ["V2_D10_INTEGRATION_VALIDATION"] = "1"
        os.environ.update(D10_FASTPATH)
        env = _runtime_env()
        for key, want in D10_FASTPATH.items():
            self.assertEqual(str(env.get(key, "") or ""), want, key)

    def test_cli_exit_zero_on_d10_profile(self):
        env = dict(os.environ)
        env["V2_D10_INTEGRATION_VALIDATION"] = "1"
        env.update(D10_FASTPATH)
        result = subprocess.run(
            [sys.executable, "tools/benchmark_v2_direct.py", "--verify-d6-profile"],
            cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True,
            errors="replace", timeout=240,
        )
        self.assertEqual(result.returncode, 0, result.stdout[-2000:])
        self.assertIn("validation=PASS", result.stdout)
        self.assertIn("profile=d10_integration_validation", result.stdout)


class TestVerifyE10BucketFirstProfile(unittest.TestCase):
    def setUp(self):
        self._saved = {
            key: os.environ.get(key)
            for key in tuple(E10_BUCKET_FIRST)
            + ("V2_E10_BUCKET_FIRST_VALIDATION",)
        }
        for key in self._saved:
            os.environ.pop(key, None)
        self.bvd = _bvd()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_profile_requires_explicit_opt_in(self):
        ok, details = self.bvd.verify_e10_bucket_first_profile()
        self.assertFalse(ok)
        self.assertEqual(details["validation"], "FAIL")

    def test_profile_matches_runtime_env(self):
        os.environ["V2_E10_BUCKET_FIRST_VALIDATION"] = "1"
        os.environ.update(E10_BUCKET_FIRST)
        ok, details = self.bvd.verify_e10_bucket_first_profile()
        self.assertTrue(ok)
        self.assertEqual(details["validation"], "PASS")
        for key, expected in E10_BUCKET_FIRST.items():
            self.assertEqual(details[key], expected, key)

    def test_profile_rejects_missing_clip_staged_flag(self):
        os.environ["V2_E10_BUCKET_FIRST_VALIDATION"] = "1"
        os.environ.update(E10_BUCKET_FIRST)
        os.environ.pop("COMFYMODAL_V2_CLIP_STAGED_HYDRATION")
        ok, details = self.bvd.verify_e10_bucket_first_profile()
        self.assertFalse(ok)
        self.assertEqual(details["COMFYMODAL_V2_CLIP_STAGED_HYDRATION"], "0")


class TestLauncherGate(unittest.TestCase):
    """e) Source-level: the launcher verifies BEFORE the first deploy and
    aborts on failure; behavioral: the CLI exits 0/1 as gated."""

    def test_bat_verifies_before_first_deploy_and_aborts(self):
        text = (_REPO_ROOT / "deploy_and_run_v2_single.bat").read_text(
            encoding="utf-8"
        )
        lines = text.splitlines()
        verify_idx = next(
            i for i, ln in enumerate(lines)
            if "--verify-d6-profile" in ln and ln.lstrip().startswith("python ")
        )
        deploy_idx = [
            i for i, ln in enumerate(lines)
            if "modal deploy" in ln or "deploy -m" in ln or "deploy comfyapp.py" in ln
        ]
        self.assertTrue(deploy_idx, "no deploy invocation found in the launcher")
        self.assertLess(verify_idx, min(deploy_idx))
        # The fail-fast abort block immediately follows the verify call.
        tail = "\n".join(lines[verify_idx:verify_idx + 8])
        self.assertIn("if errorlevel 1", tail)
        self.assertIn("exit /b 1", tail)
        self.assertIn("deploy profile validation FAILED", tail)

    def test_cli_exit_zero_on_correct_profile(self):
        env = dict(os.environ)
        env["V2_D6_FASTPATH_VALIDATION"] = "1"
        env.update(D6_FASTPATH)
        result = subprocess.run(
            [sys.executable, "tools/benchmark_v2_direct.py", "--verify-d6-profile"],
            cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True,
            errors="replace", timeout=240,
        )
        self.assertEqual(result.returncode, 0, result.stdout[-2000:])
        self.assertIn("validation=PASS", result.stdout)

    def test_cli_exit_one_on_wrong_value(self):
        env = dict(os.environ)
        env["V2_D6_FASTPATH_VALIDATION"] = "1"
        env.update(D6_FASTPATH)
        env["COMFYMODAL_V2_UNET_FASTSAFETENSORS"] = "0"
        result = subprocess.run(
            [sys.executable, "tools/benchmark_v2_direct.py", "--verify-d6-profile"],
            cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True,
            errors="replace", timeout=240,
        )
        self.assertEqual(result.returncode, 1, result.stdout[-2000:])
        self.assertIn("validation=FAIL", result.stdout)


if __name__ == "__main__":
    unittest.main()
