import unittest

from runtime_config import build_runtime_snapshot_key


def _base_kwargs(**overrides):
    """Return a full kwargs dict for build_runtime_snapshot_key, overridable."""
    defaults = dict(
        runtime_version="1", comfy_version="2", worker_version="3",
        manifest_hash="aaa", warmup_version="0", warmup_profile="off", gpu_type="a100",
    )
    defaults.update(overrides)
    return defaults


class RuntimeConfigTests(unittest.TestCase):
    def test_snapshot_key_is_deterministic(self):
        """Same inputs always produce the same key."""
        a = build_runtime_snapshot_key(**_base_kwargs())
        b = build_runtime_snapshot_key(**_base_kwargs())
        self.assertEqual(a, b)

    def test_snapshot_key_changes_with_manifest_hash(self):
        a = build_runtime_snapshot_key(**_base_kwargs(manifest_hash="aaa"))
        b = build_runtime_snapshot_key(**_base_kwargs(manifest_hash="bbb"))
        self.assertNotEqual(a, b)

    def test_snapshot_key_changes_with_gpu_type(self):
        a = build_runtime_snapshot_key(**_base_kwargs(gpu_type="a100"))
        b = build_runtime_snapshot_key(**_base_kwargs(gpu_type="t4"))
        self.assertNotEqual(a, b)

    def test_snapshot_key_changes_with_runtime_version(self):
        a = build_runtime_snapshot_key(**_base_kwargs(runtime_version="1"))
        b = build_runtime_snapshot_key(**_base_kwargs(runtime_version="2"))
        self.assertNotEqual(a, b)

    def test_snapshot_key_changes_with_comfy_version(self):
        a = build_runtime_snapshot_key(**_base_kwargs(comfy_version="2"))
        b = build_runtime_snapshot_key(**_base_kwargs(comfy_version="3"))
        self.assertNotEqual(a, b)

    def test_snapshot_key_changes_with_worker_version(self):
        a = build_runtime_snapshot_key(**_base_kwargs(worker_version="3"))
        b = build_runtime_snapshot_key(**_base_kwargs(worker_version="4"))
        self.assertNotEqual(a, b)

    def test_snapshot_key_changes_with_warmup_version(self):
        a = build_runtime_snapshot_key(**_base_kwargs(warmup_version="0"))
        b = build_runtime_snapshot_key(**_base_kwargs(warmup_version="1"))
        self.assertNotEqual(a, b)

    def test_snapshot_key_changes_with_warmup_profile(self):
        a = build_runtime_snapshot_key(**_base_kwargs(warmup_profile="off"))
        b = build_runtime_snapshot_key(**_base_kwargs(warmup_profile="light"))
        self.assertNotEqual(a, b)


class RuntimeConfigConstantsTests(unittest.TestCase):
    """Verify resolved constants are importable with expected types."""

    def test_default_execution_backend_accessible(self):
        from runtime_config import DEFAULT_EXECUTION_BACKEND
        self.assertIn(DEFAULT_EXECUTION_BACKEND, ("subprocess", "in_process"))

    def test_enable_warmup_is_bool(self):
        from runtime_config import ENABLE_WARMUP
        self.assertIsInstance(ENABLE_WARMUP, bool)

    def test_warmup_profile_is_str(self):
        from runtime_config import WARMUP_PROFILE
        self.assertIsInstance(WARMUP_PROFILE, str)

    def test_runtime_version_is_str(self):
        from runtime_config import RUNTIME_VERSION
        self.assertIsInstance(RUNTIME_VERSION, str)

    def test_snapshot_schema_version_is_str(self):
        from runtime_config import SNAPSHOT_SCHEMA_VERSION
        self.assertIsInstance(SNAPSHOT_SCHEMA_VERSION, str)

    def test_warmup_profile_version_is_str(self):
        from runtime_config import WARMUP_PROFILE_VERSION
        self.assertIsInstance(WARMUP_PROFILE_VERSION, str)
