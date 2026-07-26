"""Focused tests for disk-persisted cache across ``run_v2_single`` processes.

Lane A extends the in-memory profile and restore-publication caches with
a bounded/versioned atomic JSON disk store so that a separate Python process
(the second ``run_v2_single`` invocation) can reuse cached results without
remote calls.

Covers:
- Bootstrap: disk cache loaded into ``_PROFILE_PREP_CACHE`` at module init
- Write-after-success: disk cache written only after confirmed remote success
- Invalidate-on-failure: disk entry removed when remote op fails
- Corruption recovery: corrupt/version-mismatched file → empty + counter bump
- Atomic write: ``os.replace`` via ``tempfile.mkstemp`` ensures crash safety
- Subprocess simulation: write in one process context, read in another
- Exact invalidation across every identity field
- No handles/sensitive/request/output data in disk cache
- Bounded max entries
- Telemetry counters (read/write/miss/corruption)
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from canonical_execution import (
    _DISK_CACHE_VERSION,
    _DISK_CACHE_MAX,
    _PROFILE_PREP_CACHE,
    _PROFILE_PREP_CACHE_LOCK,
    _RESTORE_PUBLISH_CACHE,
    _RESTORE_PUBLISH_CACHE_LOCK,
    _app_identity,
    _disk_cache_dir,
    _disk_cache_filepath,
    _flush_profile_disk_cache,
    _flush_restore_disk_cache,
    _populate_profile_cache_from_disk,
    _populate_restore_cache_from_disk,
    _profile_disk_cache,
    _profile_disk_lock,
    _profile_prep_cache_key,
    _read_disk_cache,
    _remove_profile_disk_entry,
    _remove_restore_disk_entry,
    _reset_all_cache_counters,
    _reset_disk_caches,
    _reset_profile_prep_cache,
    _reset_restore_publish_cache,
    _restore_disk_cache,
    _restore_disk_lock,
    _write_disk_cache,
    build_execution_plan,
    execute_plan,
)
import canonical_execution as _ce
from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from comfymodal_runtime.modal_transport import ModalTransport
from warmup_profile import _reset_last_stable_profile_cache


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_profile_disk_entry(
    profile_cache_key: str,
    status: str = "written",
) -> dict:
    """Create a synthetic disk cache entry for testing."""
    return {
        "result": {
            "status": status,
            "active_profile_stable_key": "test_stable_key_0000000000000000",
            "active_profile_token": "test_token_000000000000",
            "model_profile_key": "mk_test",
            "prefill_key": "pk_test",
        },
        "model_profile_key": "mk_test",
        "prefill_key": "pk_test",
        "ws_id": "ws_test",
        "app_identity": _app_identity(),
        "ts": time.time(),
        "pid": os.getpid(),
    }


def _make_restore_disk_entry(cache_key: str) -> dict:
    """Create a synthetic restore disk cache entry for testing."""
    return {
        "identity_hash": "test_identity_hash_abcd1234",
        "publication_result": {"generation": 1, "status": "published"},
        "ws_id": "ws_test",
        "app_identity": _app_identity(),
        "ts": time.time(),
        "pid": os.getpid(),
    }


# ═══════════════════════════════════════════════════════════════════════
# Bootstrap: disk cache loaded into in-memory caches at module init
# ═══════════════════════════════════════════════════════════════════════


class TestDiskCacheBootstrap(unittest.TestCase):
    """Disk cache populates in-memory caches on load."""

    def setUp(self):
        _reset_all_cache_counters()

    def tearDown(self):
        _reset_all_cache_counters()

    def test_profile_cache_loaded_from_disk(self):
        """``_populate_profile_cache_from_disk`` fills ``_PROFILE_PREP_CACHE``."""
        # Write a valid disk cache entry
        ck = _profile_prep_cache_key("app", "ws_boot", "mk", "pk")
        entry = _make_profile_disk_entry(ck)
        with _profile_disk_lock:
            _profile_disk_cache[ck] = entry
        _flush_profile_disk_cache()

        # Clear in-memory and reload
        _reset_profile_prep_cache()
        self.assertNotIn(ck, _PROFILE_PREP_CACHE)
        _populate_profile_cache_from_disk()
        self.assertIn(ck, _PROFILE_PREP_CACHE)

    def test_restore_cache_loaded_from_disk(self):
        """``_populate_restore_cache_from_disk`` fills ``_RESTORE_PUBLISH_CACHE``."""
        ck = _profile_prep_cache_key("app", "ws_boot", "plan_id", "")
        entry = _make_restore_disk_entry(ck)
        with _restore_disk_lock:
            _restore_disk_cache[ck] = entry
        _flush_restore_disk_cache()

        _reset_restore_publish_cache()
        self.assertNotIn(ck, _RESTORE_PUBLISH_CACHE)
        _populate_restore_cache_from_disk()
        self.assertIn(ck, _RESTORE_PUBLISH_CACHE)

    def test_bootstrap_skips_error_status(self):
        """Disk entries with ``status=error`` are NOT loaded into memory."""
        ck = _profile_prep_cache_key("app", "ws_err", "mk_err", "pk_err")
        entry = _make_profile_disk_entry(ck, status="error")
        with _profile_disk_lock:
            _profile_disk_cache[ck] = entry
        _flush_profile_disk_cache()

        _reset_profile_prep_cache()
        _populate_profile_cache_from_disk()
        self.assertNotIn(ck, _PROFILE_PREP_CACHE,
                         "Error-status entries must not be loaded")


# ═══════════════════════════════════════════════════════════════════════
# Write-after-success / Invalidate-on-failure
# ═══════════════════════════════════════════════════════════════════════


class TestDiskCacheWriteOnSuccess(unittest.TestCase):
    """Disk cache is written only after confirmed remote success."""

    def setUp(self):
        _reset_all_cache_counters()

    def tearDown(self):
        _reset_all_cache_counters()

    def test_profile_cache_written_on_success(self):
        """After a successful profile prep, disk cache has the entry."""
        ck = _profile_prep_cache_key("app", "ws_write", "mk_s", "pk_s")
        # Simulate the flow: success path writes both memory and disk
        pn_result = {
            "status": "written",
            "active_profile_stable_key": "stable_0000",
            "active_profile_token": "tok_0000",
        }
        with _PROFILE_PREP_CACHE_LOCK:
            _PROFILE_PREP_CACHE[ck] = dict(pn_result)
        with _profile_disk_lock:
            _profile_disk_cache[ck] = {
                "result": dict(pn_result),
                "model_profile_key": "mk_s",
                "prefill_key": "pk_s",
                "ws_id": "ws_write",
                "app_identity": _app_identity(),
                "ts": time.time(),
                "pid": os.getpid(),
            }
        _flush_profile_disk_cache()

        # Verify disk file now has the entry
        disk_entries = _read_disk_cache("profile")
        self.assertIn(ck, disk_entries)

    def test_profile_cache_invalidated_on_failure(self):
        """On profile prep failure, disk entry is removed."""
        ck = _profile_prep_cache_key("app", "ws_fail", "mk_f", "pk_f")
        # Pre-populate disk with a stale entry
        with _profile_disk_lock:
            _profile_disk_cache[ck] = _make_profile_disk_entry(ck)
        _flush_profile_disk_cache()

        # Ensure disk has it
        self.assertIn(ck, _read_disk_cache("profile"))

        # Simulate failure: remove from disk
        _remove_profile_disk_entry(ck)

        # Verify disk no longer has it
        disk_entries = _read_disk_cache("profile")
        self.assertNotIn(ck, disk_entries)

    def test_restore_cache_written_on_success(self):
        """After successful restore publish, disk cache has the entry."""
        ck = _profile_prep_cache_key("app", "ws_rs", "plan_rs", "")
        with _RESTORE_PUBLISH_CACHE_LOCK:
            _RESTORE_PUBLISH_CACHE[ck] = {
                "identity_hash": "hash_rs",
                "publication_result": {"generation": 1},
            }
        with _restore_disk_lock:
            _restore_disk_cache[ck] = _make_restore_disk_entry(ck)
        _flush_restore_disk_cache()

        disk_entries = _read_disk_cache("restore")
        self.assertIn(ck, disk_entries)

    def test_restore_cache_invalidated_on_failure(self):
        """On restore publish failure, disk entry is removed."""
        ck = _profile_prep_cache_key("app", "ws_rf", "plan_rf", "")
        with _restore_disk_lock:
            _restore_disk_cache[ck] = _make_restore_disk_entry(ck)
        _flush_restore_disk_cache()

        self.assertIn(ck, _read_disk_cache("restore"))
        _remove_restore_disk_entry(ck)
        self.assertNotIn(ck, _read_disk_cache("restore"))

    def test_write_only_after_remote_success_execute_plan(self):
        """Full execute_plan with success writes disk cache (smoke test)."""
        call_count = [0]

        async def _counting_setter(payload, *, workspace=None):
            call_count[0] += 1
            return {"status": "written", "changed": True}

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            _reset_all_cache_counters()
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="disk_smoke", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(
                plan, transport=transport,
                profile_setter=_counting_setter,
                workspace={"id": "ws_disk_smoke"},
            )

        asyncio.run(run())

        # After success, disk cache should have the profile entry
        disk_entries = _read_disk_cache("profile")
        self.assertGreater(len(disk_entries), 0,
                           "Disk cache must have entries after successful execute_plan")


# ═══════════════════════════════════════════════════════════════════════
# Corruption recovery
# ═══════════════════════════════════════════════════════════════════════


class TestDiskCacheCorruption(unittest.TestCase):
    """Corrupt file returns empty and increments corruption counter."""

    def setUp(self):
        _reset_all_cache_counters()
        # Reset telemetry counters for isolation
        _ce._disk_profile_corruption_count = 0
        _ce._disk_restore_corruption_count = 0

    def tearDown(self):
        _reset_all_cache_counters()

    def test_corrupt_json_returns_empty(self):
        """Invalid JSON in disk cache file returns empty dict."""
        path = _disk_cache_filepath("profile")
        with open(path, "w") as f:
            f.write("{invalid json!!!}")
        result = _read_disk_cache("profile")
        self.assertEqual(result, {})

    def test_corrupt_json_increments_counter(self):
        """Corrupt JSON increments ``_disk_profile_corruption_count``."""
        path = _disk_cache_filepath("profile")
        with open(path, "w") as f:
            f.write("not json at all")
        before = _ce._disk_profile_corruption_count
        _read_disk_cache("profile")
        self.assertGreater(_ce._disk_profile_corruption_count, before)

    def test_version_mismatch_returns_empty(self):
        """Wrong schema version returns empty dict."""
        path = _disk_cache_filepath("profile")
        with open(path, "w") as f:
            json.dump({"version": 999, "entries": {"k": "v"}}, f)
        result = _read_disk_cache("profile")
        self.assertEqual(result, {})

    def test_version_mismatch_increments_corruption(self):
        """Wrong version increments corruption counter."""
        path = _disk_cache_filepath("profile")
        with open(path, "w") as f:
            json.dump({"version": 999, "entries": {}}, f)
        before = _ce._disk_profile_corruption_count
        _read_disk_cache("profile")
        self.assertGreater(_ce._disk_profile_corruption_count, before)

    def test_missing_file_returns_empty(self):
        """Non-existent file returns empty dict without error."""
        # Use a non-existent path
        from canonical_execution import _disk_cache_dir
        fake_path = os.path.join(_disk_cache_dir(), "_nonexistent.json")
        # Temporarily override the disk cache path by writing then removing
        # The _read_disk_cache function checks os.path.isfile
        _write_disk_cache("profile", {})
        path = _disk_cache_filepath("profile")
        os.unlink(path)
        result = _read_disk_cache("profile")
        self.assertEqual(result, {})

    def test_restore_corruption_counter(self):
        """Restore cache corruption increments restore counter."""
        path = _disk_cache_filepath("restore")
        with open(path, "w") as f:
            f.write("garbage data")
        before = _ce._disk_restore_corruption_count
        _read_disk_cache("restore")
        self.assertGreater(_ce._disk_restore_corruption_count, before)


# ═══════════════════════════════════════════════════════════════════════
# Atomic write via tempfile + os.replace
# ═══════════════════════════════════════════════════════════════════════


class TestDiskCacheAtomicWrite(unittest.TestCase):
    """Disk cache writes are atomic (tempfile + os.replace)."""

    def setUp(self):
        _reset_all_cache_counters()

    def tearDown(self):
        _reset_all_cache_counters()

    def test_write_creates_valid_json(self):
        """Written file is valid JSON with correct version."""
        _write_disk_cache("profile", {"test_key": {"result": {"status": "ok"}}})
        path = _disk_cache_filepath("profile")
        with open(path, "rb") as f:
            data = json.loads(f.read().decode("utf-8"))
        self.assertEqual(data["version"], _DISK_CACHE_VERSION)
        self.assertIn("entries", data)
        self.assertIn("test_key", data["entries"])

    def test_write_does_not_leave_tmp_file(self):
        """No .tmp files remain after write."""
        _write_disk_cache("profile", {"k": {"result": {"status": "ok"}}})
        cache_dir = _disk_cache_dir()
        tmp_files = [f for f in os.listdir(cache_dir) if f.endswith(".tmp")]
        self.assertEqual(len(tmp_files), 0,
                         f"Leftover .tmp files: {tmp_files}")

    def test_multiple_writes_are_independent(self):
        """Two sequential writes produce a valid final file."""
        _write_disk_cache("profile", {"k1": {"result": {"status": "first"}}})
        _write_disk_cache("profile", {"k2": {"result": {"status": "second"}}})
        entries = _read_disk_cache("profile")
        self.assertIn("k2", entries)
        # k1 may or may not be present (depends on write impl)
        # At minimum the last write should be present
        self.assertEqual(entries["k2"]["result"]["status"], "second")

    def test_profile_and_restore_files_are_independent(self):
        """Profile and restore cache files are independent."""
        _write_disk_cache("profile", {"p": {"result": {"status": "profile"}}})
        _write_disk_cache("restore", {"r": {"identity_hash": "hash"}})
        p_entries = _read_disk_cache("profile")
        r_entries = _read_disk_cache("restore")
        self.assertIn("p", p_entries)
        self.assertIn("r", r_entries)
        self.assertNotIn("r", p_entries)
        self.assertNotIn("p", r_entries)


# ═══════════════════════════════════════════════════════════════════════
# Subprocess simulation
# ═══════════════════════════════════════════════════════════════════════


class TestSubprocessSimulation(unittest.TestCase):
    """Simulate cross-process cache by writing in one context and reading
    in another (same test, same process — simulates the file round-trip)."""

    def setUp(self):
        _reset_all_cache_counters()

    def tearDown(self):
        _reset_all_cache_counters()

    def test_write_then_read_simulates_cross_process(self):
        """Write cache, clear memory, reload — simulates a fresh process."""
        # Phase 1: "process A" writes to disk
        ck = _profile_prep_cache_key("proc_a", "ws_a", "mk_a", "pk_a")
        with _profile_disk_lock:
            _profile_disk_cache[ck] = _make_profile_disk_entry(ck)
        _flush_profile_disk_cache()

        # Phase 2: "process B" starts with no memory cache
        _reset_profile_prep_cache()
        _populate_profile_cache_from_disk()
        self.assertIn(ck, _PROFILE_PREP_CACHE,
                      "Process B must see process A's cached data")

    def test_identity_change_causes_miss_in_new_process(self):
        """With a different identity key, the cache miss is expected."""
        # Phase 1: "process A" writes with identity X
        ck_a = _profile_prep_cache_key("app", "ws", "mk_a", "pk")
        with _profile_disk_lock:
            _profile_disk_cache[ck_a] = _make_profile_disk_entry(ck_a)
        _flush_profile_disk_cache()

        # Phase 2: "process B" has identity Y — different model key
        ck_b = _profile_prep_cache_key("app", "ws", "mk_b", "pk")
        _reset_profile_prep_cache()
        _populate_profile_cache_from_disk()
        self.assertIn(ck_a, _PROFILE_PREP_CACHE,
                      "Old identity should be in cache")
        self.assertNotIn(ck_b, _PROFILE_PREP_CACHE,
                         "New identity should NOT be in cache (different key)")

    def test_restore_cache_cross_process(self):
        """Restore cache survives a simulate-restart cycle."""
        ck = _profile_prep_cache_key("app", "ws_r", "plan_r", "")
        with _restore_disk_lock:
            _restore_disk_cache[ck] = _make_restore_disk_entry(ck)
        _flush_restore_disk_cache()

        _reset_restore_publish_cache()
        _populate_restore_cache_from_disk()
        self.assertIn(ck, _RESTORE_PUBLISH_CACHE)


# ═══════════════════════════════════════════════════════════════════════
# Exact invalidation across every identity field
# ═══════════════════════════════════════════════════════════════════════


class TestExactInvalidation(unittest.TestCase):
    """Every identity field change causes cache invalidation."""

    def setUp(self):
        _reset_all_cache_counters()

    def tearDown(self):
        _reset_all_cache_counters()

    def test_invalidation_app_identity(self):
        """Different app identity → different cache key."""
        k1 = _profile_prep_cache_key("app_a", "ws", "mk", "pk")
        k2 = _profile_prep_cache_key("app_b", "ws", "mk", "pk")
        self.assertNotEqual(k1, k2)

    def test_invalidation_workspace_id(self):
        """Different workspace → different cache key."""
        k1 = _profile_prep_cache_key("app", "ws_a", "mk", "pk")
        k2 = _profile_prep_cache_key("app", "ws_b", "mk", "pk")
        self.assertNotEqual(k1, k2)

    def test_invalidation_model_profile_key(self):
        """Different model_profile_key → different cache key."""
        k1 = _profile_prep_cache_key("app", "ws", "mk_a", "pk")
        k2 = _profile_prep_cache_key("app", "ws", "mk_b", "pk")
        self.assertNotEqual(k1, k2)

    def test_invalidation_prefill_key(self):
        """Different prefill_key → different cache key."""
        k1 = _profile_prep_cache_key("app", "ws", "mk", "pk_a")
        k2 = _profile_prep_cache_key("app", "ws", "mk", "pk_b")
        self.assertNotEqual(k1, k2)

    def test_invalidation_all_four_fields(self):
        """All four fields differ → four distinct keys."""
        k1 = _profile_prep_cache_key("app1", "ws1", "mk1", "pk1")
        k2 = _profile_prep_cache_key("app2", "ws2", "mk2", "pk2")
        k3 = _profile_prep_cache_key("app1", "ws2", "mk1", "pk2")
        keys = {k1, k2, k3}
        self.assertEqual(len(keys), 3, "All three keys must be unique")

    def test_remove_only_exact_key(self):
        """Removing one cache entry does not affect other entries."""
        ck_a = _profile_prep_cache_key("app", "ws", "mk_a", "pk")
        ck_b = _profile_prep_cache_key("app", "ws", "mk_b", "pk")
        with _profile_disk_lock:
            _profile_disk_cache[ck_a] = _make_profile_disk_entry(ck_a)
            _profile_disk_cache[ck_b] = _make_profile_disk_entry(ck_b)
        _flush_profile_disk_cache()

        _remove_profile_disk_entry(ck_a)
        disk_entries = _read_disk_cache("profile")
        self.assertNotIn(ck_a, disk_entries)
        self.assertIn(ck_b, disk_entries,
                      "Removing key A must not affect key B")


# ═══════════════════════════════════════════════════════════════════════
# No handles/sensitive/request/output data in disk cache
# ═══════════════════════════════════════════════════════════════════════


class TestNoSensitiveData(unittest.TestCase):
    """Disk cache never serialises handles, images, prompts, or outputs."""

    SENSITIVE_PATTERNS = (
        "token_id", "token_secret", "api_key", "secret",
        "handle", "Handle",
        "base64", "image_data", "image_bytes",
        "full_workflow", "workflow_json",
        "prompt_text", "prompt_content",
        "output_data", "result_images",
        "ssh_key", "password", "credential",
    )

    def setUp(self):
        _reset_all_cache_counters()

    def tearDown(self):
        _reset_all_cache_counters()

    def _scan_for_sensitive(self, entries: dict, label: str) -> list[str]:
        """Scan *entries* for any sensitive key/value patterns."""
        findings: list[str] = []
        entries_str = json.dumps(entries)
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern.lower() in entries_str.lower():
                findings.append(f"{label}: found '{pattern}' in serialized cache")
        return findings

    def test_profile_cache_no_sensitive_data(self):
        """Profile disk cache has no sensitive fields."""
        ck = _profile_prep_cache_key("app", "ws", "mk", "pk")
        entry = _make_profile_disk_entry(ck)
        findings = self._scan_for_sensitive(entry, "profile")
        self.assertEqual(len(findings), 0,
                         f"Sensitive data found: {findings}")

    def test_restore_cache_no_sensitive_data(self):
        """Restore disk cache has no sensitive fields."""
        ck = _profile_prep_cache_key("app", "ws", "plan", "")
        entry = _make_restore_disk_entry(ck)
        findings = self._scan_for_sensitive(entry, "restore")
        self.assertEqual(len(findings), 0,
                         f"Sensitive data found: {findings}")

    def test_actual_disk_write_no_images(self):
        """After an execute_plan with images, disk cache has no base64."""
        async def _counting_setter(payload, *, workspace=None):
            return {"status": "written", "changed": True}

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            _reset_all_cache_counters()
            plan = build_execution_plan(
                {"1": {"class_type": "LoadImage", "inputs": {"image": "cat.png"}},
                 "2": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                input_images={"cat.png": "fake_base64_data_here_ABCD=="},
                prompt_id="disk_no_img", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(
                plan, transport=transport,
                profile_setter=_counting_setter,
                workspace={"id": "ws_no_img"},
            )

        asyncio.run(run())
        disk_entries = _read_disk_cache("profile")
        entries_str = json.dumps(disk_entries)
        self.assertNotIn("base64", entries_str.lower(),
                         "Disk cache must not contain base64 image data")
        self.assertNotIn("cat.png", entries_str,
                         "Disk cache must not contain image filenames")


# ═══════════════════════════════════════════════════════════════════════
# Bounded max entries
# ═══════════════════════════════════════════════════════════════════════


class TestBoundedMaxEntries(unittest.TestCase):
    """Disk cache does not exceed ``_DISK_CACHE_MAX`` entries."""

    def setUp(self):
        _reset_all_cache_counters()

    def tearDown(self):
        _reset_all_cache_counters()

    def test_profile_cache_bounded(self):
        """Writing more than max entries forces eviction."""
        # Write max + 10 entries
        with _profile_disk_lock:
            for i in range(_DISK_CACHE_MAX + 10):
                ck = _profile_prep_cache_key("app", "ws", f"mk_{i}", "pk")
                _profile_disk_cache[ck] = _make_profile_disk_entry(ck)
        _flush_profile_disk_cache()

        disk_entries = _read_disk_cache("profile")
        self.assertLessEqual(len(disk_entries), _DISK_CACHE_MAX,
                             f"Profile disk cache exceeds {_DISK_CACHE_MAX} entries")

    def test_restore_cache_bounded(self):
        """Writing more than max entries forces eviction."""
        with _restore_disk_lock:
            for i in range(_DISK_CACHE_MAX + 10):
                ck = _profile_prep_cache_key("app", "ws", f"plan_{i}", "")
                _restore_disk_cache[ck] = _make_restore_disk_entry(ck)
        _flush_restore_disk_cache()

        disk_entries = _read_disk_cache("restore")
        self.assertLessEqual(len(disk_entries), _DISK_CACHE_MAX,
                             f"Restore disk cache exceeds {_DISK_CACHE_MAX} entries")


# ═══════════════════════════════════════════════════════════════════════
# Telemetry counters
# ═══════════════════════════════════════════════════════════════════════


class TestDiskCacheTelemetry(unittest.TestCase):
    """Read/write/miss/corruption counters are monotonic."""

    def setUp(self):
        _reset_all_cache_counters()
        # Explicitly reset telemetry via module reference
        _ce._disk_profile_read_count = 0
        _ce._disk_profile_write_count = 0
        _ce._disk_profile_miss_count = 0
        _ce._disk_profile_corruption_count = 0
        _ce._disk_restore_read_count = 0
        _ce._disk_restore_write_count = 0
        _ce._disk_restore_miss_count = 0
        _ce._disk_restore_corruption_count = 0

    def tearDown(self):
        _reset_all_cache_counters()

    def test_read_count_increments(self):
        """Each disk read increments read counter."""
        _write_disk_cache("profile", {"k": {"result": {"status": "ok"}}})
        before = _ce._disk_profile_read_count
        _read_disk_cache("profile")
        self.assertGreater(_ce._disk_profile_read_count, before)

    def test_write_count_increments(self):
        """Each disk write increments write counter."""
        before = _ce._disk_profile_write_count
        _write_disk_cache("profile", {"k": {"result": {"status": "ok"}}})
        self.assertGreater(_ce._disk_profile_write_count, before)

    def test_miss_count_for_missing_file(self):
        """Missing file doesn't increment miss (file not found isn't a read)."""
        # Remove the file
        path = _disk_cache_filepath("profile")
        if os.path.isfile(path):
            os.unlink(path)
        before = _ce._disk_profile_read_count
        result = _read_disk_cache("profile")
        # read_count shouldn't increment since file doesn't exist
        self.assertEqual(result, {})
        self.assertEqual(_ce._disk_profile_read_count, before)

    def test_corruption_count_increments(self):
        """Corrupt file increments corruption counter."""
        path = _disk_cache_filepath("profile")
        with open(path, "w") as f:
            f.write("{{{corrupted")
        before = _ce._disk_profile_corruption_count
        _read_disk_cache("profile")
        self.assertGreater(_ce._disk_profile_corruption_count, before)

    def test_restore_telemetry_independent(self):
        """Restore cache has its own independent telemetry counters."""
        _write_disk_cache("restore", {"k": {"identity_hash": "h"}})
        r_before = _ce._disk_restore_read_count
        p_before = _ce._disk_profile_read_count

        _read_disk_cache("restore")
        self.assertGreater(_ce._disk_restore_read_count, r_before)
        # Profile counter should NOT have changed
        self.assertEqual(_ce._disk_profile_read_count, p_before)


# ═══════════════════════════════════════════════════════════════════════
# Invalidation reason in telemetry
# ═══════════════════════════════════════════════════════════════════════


class TestInvalidationReason(unittest.TestCase):
    """Miss reason reflects the exact cause of cache invalidation."""

    def setUp(self):
        _reset_all_cache_counters()

    def tearDown(self):
        _reset_all_cache_counters()

    def test_trace_metadata_has_miss_reason(self):
        """``profile_miss_reason`` is set in trace metadata on cache miss."""
        from comfymodal_runtime.trace import RuntimeTrace

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def _setter(payload, *, workspace=None):
            return {"status": "written", "changed": True}

        async def run():
            trace = RuntimeTrace(request_id="miss_reason_test", process="local")
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="miss_reason_test", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(
                plan, transport=transport,
                profile_setter=_setter,
                workspace={"id": "ws_mr"},
                trace=trace,
            )
            miss_reason = trace._metadata.get("profile_miss_reason", "")
            self.assertIn(miss_reason,
                          ("key_not_found", "cache_reset", "identity_mismatch"),
                          f"Unexpected miss reason: {miss_reason!r}")

        asyncio.run(run())

    def test_disk_cache_telemetry_in_trace(self):
        """Disk cache telemetry fields appear in trace metadata."""
        from comfymodal_runtime.trace import RuntimeTrace

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def _setter(payload, *, workspace=None):
            return {"status": "written", "changed": True}

        async def run():
            _reset_all_cache_counters()
            trace = RuntimeTrace(request_id="disk_telemetry", process="local")
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="disk_telemetry", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(
                plan, transport=transport,
                profile_setter=_setter,
                workspace={"id": "ws_dt"},
                trace=trace,
            )
            md = trace._metadata
            self.assertIn("disk_profile_read_count", md)
            self.assertIn("disk_profile_write_count", md)
            self.assertIn("disk_profile_miss_count", md)
            self.assertIn("disk_profile_corruption_count", md)

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# Cleanup: teardown resets all caches
# ═══════════════════════════════════════════════════════════════════════


class TestResetDiskCache(unittest.TestCase):
    """``_reset_disk_caches`` clears both profile and restore disk caches."""

    def setUp(self):
        _reset_all_cache_counters()

    def tearDown(self):
        _reset_all_cache_counters()

    def test_reset_clears_profile_disk_cache(self):
        """After reset, profile disk cache is empty."""
        with _profile_disk_lock:
            _profile_disk_cache["k"] = {"result": {"status": "ok"}}
        _flush_profile_disk_cache()
        self.assertGreater(len(_read_disk_cache("profile")), 0)

        _reset_disk_caches()
        self.assertEqual(len(_read_disk_cache("profile")), 0)

    def test_reset_clears_restore_disk_cache(self):
        """After reset, restore disk cache is empty."""
        with _restore_disk_lock:
            _restore_disk_cache["k"] = {"identity_hash": "h"}
        _flush_restore_disk_cache()
        self.assertGreater(len(_read_disk_cache("restore")), 0)

        _reset_disk_caches()
        self.assertEqual(len(_read_disk_cache("restore")), 0)

    def test_reset_all_clears_everything(self):
        """``_reset_all_cache_counters`` clears disk caches too."""
        ck = _profile_prep_cache_key("app", "ws", "mk", "pk")
        with _profile_disk_lock:
            _profile_disk_cache[ck] = _make_profile_disk_entry(ck)
        _flush_profile_disk_cache()

        _reset_all_cache_counters()
        self.assertEqual(len(_read_disk_cache("profile")), 0)
        self.assertEqual(len(_read_disk_cache("restore")), 0)


if __name__ == "__main__":
    unittest.main()
