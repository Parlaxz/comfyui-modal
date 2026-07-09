"""Tests for worker_control.py — area A1: control plane hardening."""
import asyncio
import hashlib
import importlib.util
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "worker_control.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("worker_control.py missing")
    spec = importlib.util.spec_from_file_location("worker_control", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Shared default identity values
_DEP = "dep_abc"
_EXP = "exp_test"
_CK = "ck_1"
_WID = "w_1"
_LG = 7


class ControlKeyIdentityTests(unittest.TestCase):
    """A1: control_key() must be deterministic and identical from any caller."""

    def test_control_key_deterministic(self):
        """Same inputs produce same key every time."""
        wc = load_module()
        k1 = wc.control_key("d1", "e1", "c1", "w1", 1)
        k2 = wc.control_key("d1", "e1", "c1", "w1", 1)
        self.assertEqual(k1, k2)

    def test_control_key_different_deployment(self):
        """Different deployment generation → different key."""
        wc = load_module()
        k1 = wc.control_key("d1", "e1", "c1", "w1", 1)
        k2 = wc.control_key("d2", "e1", "c1", "w1", 1)
        self.assertNotEqual(k1, k2)

    def test_control_key_different_lease_gen(self):
        """Different lease generation → different key."""
        wc = load_module()
        k1 = wc.control_key("d1", "e1", "c1", "w1", 1)
        k2 = wc.control_key("d1", "e1", "c1", "w1", 2)
        self.assertNotEqual(k1, k2)

    def test_control_key_prefix(self):
        """Key must start with 'control:'."""
        wc = load_module()
        k = wc.control_key("d1", "e1", "c1", "w1", 1)
        self.assertTrue(k.startswith("control:"))

    def test_control_key_components_in_order(self):
        """Key format: control:{dep}:{exp}:{ck}:{wid}:{gen}"""
        wc = load_module()
        k = wc.control_key("dep_x", "exp_y", "ck_z", "wid_w", 42)
        # Format: control:dep_x:exp_y:ck_z:wid_w:42
        parts = k.split(":")
        self.assertEqual(parts[0], "control")
        self.assertEqual(parts[1], "dep_x")
        self.assertEqual(parts[2], "exp_y")
        self.assertEqual(parts[3], "ck_z")
        self.assertEqual(parts[4], "wid_w")
        self.assertEqual(parts[5], "42")

    def test_control_key_allows_empty_components(self):
        """Empty strings are valid components (used in tests)."""
        wc = load_module()
        k = wc.control_key("", "", "", "", 0)
        self.assertTrue(k.startswith("control:"))
        # All components are empty except the 0 gen
        parts = k.split(":")
        self.assertEqual(len(parts), 6)


class ControlBackendTtlCleanupTests(unittest.TestCase):
    """A1: clear_expired_controls on ModalDictControlBackend."""

    def test_fake_backend_has_clear_expired(self):
        """FakeDictControlBackend should have clear_expired_controls for test parity."""
        wc = load_module()
        backend = wc.FakeDictControlBackend()
        self.assertTrue(
            hasattr(backend, "clear_expired_controls"),
            "FakeDictControlBackend must have clear_expired_controls",
        )

    def test_clear_expired_removes_old_records(self):
        """clear_expired_controls removes records older than max_age."""
        wc = load_module()
        backend = wc.FakeDictControlBackend()
        # Set a record
        asyncio.run(backend.set_control("d1", "e1", "c1", "w1", 1, "stop_now"))
        # Artificially age it
        key = wc.control_key("d1", "e1", "c1", "w1", 1)
        record = backend._store[key]
        record["updated_at"] = time.time() - 100  # 100 seconds old
        # Clear with max_age=50
        cleared = asyncio.run(backend.clear_expired_controls(50))
        self.assertGreaterEqual(cleared, 1, "should have cleared at least 1 record")
        state = asyncio.run(backend.get_control("d1", "e1", "c1", "w1", 1))
        self.assertEqual(state, "continue", "cleared record must return continue")

    def test_clear_expired_preserves_recent_records(self):
        """clear_expired_controls does not touch records within max_age."""
        wc = load_module()
        backend = wc.FakeDictControlBackend()
        asyncio.run(backend.set_control("d1", "e1", "c1", "w1", 1, "stop_now"))
        # Fresh record (just created) - should not be cleared
        cleared = asyncio.run(backend.clear_expired_controls(60))
        self.assertEqual(cleared, 0, "fresh record should not be cleared")
        state = asyncio.run(backend.get_control("d1", "e1", "c1", "w1", 1))
        self.assertEqual(state, "stop_now", "fresh record must be preserved")


class ControlBackendImportFailFastTests(unittest.TestCase):
    """A1: importing worker_control from comfyapp must fail-fast on import error."""

    def test_module_imports_cleanly(self):
        """The module imports without error in normal conditions."""
        wc = load_module()
        self.assertTrue(hasattr(wc, "ControlBackend"))
        self.assertTrue(hasattr(wc, "FakeDictControlBackend"))
        self.assertTrue(hasattr(wc, "ModalDictControlBackend"))
        self.assertTrue(hasattr(wc, "control_key"))

    def test_control_key_function_identity(self):
        """control_key() is the same function reference in both modules
        (it is imported by experiment_runner.py)."""
        wc = load_module()
        # Load experiment_runner and verify it uses the same function
        runner_path = REPO_ROOT / "experiment_runner.py"
        spec = importlib.util.spec_from_file_location("experiment_runner", runner_path)
        assert spec is not None and spec.loader is not None
        runner_mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = runner_mod
        spec.loader.exec_module(runner_mod)
        # The control_key reference in experiment_runner should be the same
        self.assertIs(
            wc.control_key,
            runner_mod.control_key,
            "control_key must be the same function reference in both modules"
        )


class FakeBackendClearExpiredTests(unittest.TestCase):
    """A1: verify clear_expired_controls works at the backend level."""

    def test_clear_expired_mixed_ages(self):
        """Only records past the age threshold are cleared."""
        wc = load_module()
        backend = wc.FakeDictControlBackend()
        # Create records with different ages
        now = time.time()
        asyncio.run(backend.set_control("d1", "e1", "c1", "w_old", 1, "stop_now"))
        key_old = wc.control_key("d1", "e1", "c1", "w_old", 1)
        backend._store[key_old]["updated_at"] = now - 200  # 200s old

        asyncio.run(backend.set_control("d1", "e1", "c1", "w_fresh", 1, "continue"))
        key_fresh = wc.control_key("d1", "e1", "c1", "w_fresh", 1)
        backend._store[key_fresh]["updated_at"] = now - 10  # 10s old

        cleared = asyncio.run(backend.clear_expired_controls(100))
        self.assertEqual(cleared, 1, "only the 200s-old record should be cleared")
        self.assertEqual(
            asyncio.run(backend.get_control("d1", "e1", "c1", "w_fresh", 1)),
            "continue"
        )


class VerifyDeploymentIntegrityTests(unittest.TestCase):
    """A1: verify_deployment_integrity function."""

    def test_verify_deployment_integrity_returns_expected_fields(self):
        """verify_deployment_integrity returns module path, SHA-256,
        control dict name, and container session id."""
        wc = load_module()
        result = wc.verify_deployment_integrity()
        self.assertIsInstance(result, dict)
        self.assertIn("module_path", result, "must include module_path")
        self.assertIn("source_sha256", result, "must include source_sha256")
        self.assertIn("control_dict_name", result, "must include control_dict_name")
        self.assertIn("container_session_id", result, "must include container_session_id")
        # Module path should point to worker_control.py
        self.assertTrue(
            result["module_path"].endswith("worker_control.py"),
            f"module_path should end with worker_control.py, got {result['module_path']}"
        )
        # SHA-256 should be a hex string
        self.assertTrue(
            len(result["source_sha256"]) == 64,
            f"source_sha256 should be 64 hex chars, got {len(result['source_sha256'])}"
        )

    def test_verify_deployment_integrity_consistent(self):
        """Multiple calls return the same SHA-256."""
        wc = load_module()
        r1 = wc.verify_deployment_integrity()
        r2 = wc.verify_deployment_integrity()
        self.assertEqual(r1["source_sha256"], r2["source_sha256"])


if __name__ == "__main__":
    unittest.main()
