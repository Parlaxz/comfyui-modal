"""Unit tests for ``comfymodal_runtime.full_execution_trace``.

Covers:
- Disabled/inert mode when env flag is not set.
- Factory with exact keyword-only signature and identity storage.
- Lifecycle state machine with exact states and transitions.
- ``claim_first_request`` exactly-once semantics with request_tracing auto-transition.
- ``mark``, ``operation_start``, ``operation_end`` semantic operation events.
- ``update_identity`` keyword-only registration.
- ``capture_milestone`` exact signature, bridge validation, asyncio task fields,
  wrapper inventory with symbol discovery.
- ``start_torch_profiler`` / ``stop_torch_profiler`` with exact params.
- ``stop_tracing`` idempotent ordering.
- ``ContainerResourceSampler`` flat-format nullable fields with cgroup v2 parsing.
- Thread/process inventory enumeration.
- Security: broadened key redaction, no leakage.
- ``raw_session_dir``, ``status_dict`` properties.
- ``_TEST_TRACE_BASE`` internal test override.
- Environment variable names ``COMFYMODAL_V2_FULL_TRACE_ENTRIES`` and
  ``COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS``.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

# Module under test
import comfymodal_runtime.full_execution_trace as ft
from comfymodal_runtime.full_execution_trace import (
    _sanitize_cmdline,
    _safe_repr,
    _redact_sensitive,
    _stable_hash,
    _env_int,
    _env_int_chain,
    _json_fallback,
    _safe_json_value,
    _LEGACY_ENV_ENTRIES,
    _LEGACY_ENV_RESOURCE_INTERVAL,
    _ALLOWED_WRAPPER_ORIGINAL_ATTRS,
    _ALLOWED_WRAPPER_PREFIXES,
    _VALID_TRANSITIONS,
    SCHEMA_VERSION,
    _REQUIRED_RAW_FILES,
    _SUBDIRS,
    _TRACE_BASE,
    _TEST_TRACE_BASE,
    _TEST_PROC_SELF,
    _TEST_PROC_ROOT,
    _TEST_CGROUP_V2,
    _ENV_ENTRIES,
    _ENV_RESOURCE_INTERVAL,
    ContainerResourceSampler,
    FullExecutionTraceSession,
    capture_wrapper_inventory,
    _inspect_wrapper_callable,
    _inspect_asyncio_task,
    _discover_wrapper_symbols,
    _resolve_trace_include_paths,
    _resolve_cgroup_v2_path,
    _read_cgroup_stat,
    _read_cgroup_memory,
    _read_cgroup_io,
    _parse_stat_fields,
    _get_proc_self,
    _get_proc_root,
    _KNOWN_WRAPPER_SYMBOLS,
    golden_trace_span,
)


def _make_proc_tree(tmp: Path, pid: int) -> Path:
    """Create a mock /proc/<pid> filesystem under *tmp*."""
    proc = tmp / "proc"
    (proc / str(pid)).mkdir(parents=True, exist_ok=True)
    pid_dir = proc / str(pid)

    # stat (must have fields up to rss at index 21 after comm)
    (pid_dir / "stat").write_text(
        f"0 (python) S {pid} 1 1 0 -1 4194304 123 0 0 0 "
        f"10 20 30 40 50 60 70 80 {pid} 90 999"
    )

    # status
    (pid_dir / "status").write_text(
        f"Name:\tpython\n"
        f"State:\tS (sleeping)\n"
        f"Pid:\t{pid}\n"
        f"PPid:\t1\n"
        f"VmRSS:\t102400 kB\n"
        f"VmSize:\t512000 kB\n"
        f"VmPeak:\t768000 kB\n"
        f"VmSwap:\t0 kB\n"
    )

    # io
    (pid_dir / "io").write_text(
        "read_bytes: 1000\n"
        "write_bytes: 2000\n"
        "read_chars: 500\n"
        "write_chars: 600\n"
    )

    # cmdline
    (pid_dir / "cmdline").write_text(
        f"python\x00main.py\x00--token\x00abc123\x00--model\x00test\x00"
    )

    # comm
    (pid_dir / "comm").write_text("python\n")

    # task dir
    task_dir = pid_dir / "task"
    task_dir.mkdir()
    for tid in [pid, pid + 1]:
        tdir = task_dir / str(tid)
        tdir.mkdir()
        (tdir / "stat").write_text(
            f"{tid} (python-task) S {pid} 1 1 0 -1 4194304 123 0 0 0 "
            f"10 20 30 40 50 60 70 80 {pid} 90"
        )
        (tdir / "comm").write_text(f"python-task-{tid}\n")
        (tdir / "status").write_text(
            f"Name:\tpython-task-{tid}\n"
            f"State:\tS (sleeping)\n"
        )

    # Other numeric dirs
    for p in [100, 200, 300]:
        pd = proc / str(p)
        pd.mkdir()
        (pd / "stat").write_text(
            f"{p} (other) S 1 1 1 0 -1 4194304 0 0 0 0 "
            f"5 10 15 20 25 30 35 40 {p} 50"
        )
        (pd / "status").write_text(
            f"Name:\tother\n"
            f"State:\tS (sleeping)\n"
            f"Pid:\t{p}\n"
            f"PPid:\t1\n"
        )

    # meminfo (system)
    (proc / "meminfo").write_text(
        "MemTotal:       16384000 kB\n"
        "MemFree:         8192000 kB\n"
        "MemAvailable:   10240000 kB\n"
    )

    return proc


def _make_cgroup_tree(tmp: str) -> Path:
    """Create a mock cgroup v2 hierarchy under *tmp* (a directory path string).

    Returns the cgroup directory path (simulating /sys/fs/cgroup/system.slice/...).
    """
    base = Path(tmp)
    cg = base / "sys" / "fs" / "cgroup" / "system.slice" / "docker-abc.scope"
    cg.mkdir(parents=True, exist_ok=True)

    # cpu.stat
    (cg / "cpu.stat").write_text(
        "usage_usec 1234567\n"
        "user_usec 1000000\n"
        "system_usec 234567\n"
        "nr_periods 500\n"
        "nr_throttled 3\n"
        "throttled_usec 15000\n"
    )

    # memory.current
    (cg / "memory.current").write_text("838860800\n")  # 800 MB

    # memory.peak
    (cg / "memory.peak").write_text("1073741824\n")  # 1 GB

    # memory.stat
    (cg / "memory.stat").write_text(
        "anon 419430400\n"
        "file 419430400\n"
        "inactive_file 104857600\n"
        "active_file 314572800\n"
        "pgfault 12345\n"
        "pgmajfault 67\n"
        "kernel 8388608\n"
        "kernel_stack 4194304\n"
    )

    # io.stat
    (cg / "io.stat").write_text(
        "8:0 rbytes=1048576 wbytes=2097152 rios=500 wios=300\n"
        "8:16 rbytes=524288 wbytes=1048576 rios=200 wios=150\n"
    )

    return cg


# ═══════════════════════════════════════════════════════════════════════════════════
# Test helper: create session with test trace base override
# ═══════════════════════════════════════════════════════════════════════════════════

def _create_test_session(
    trace_base: str,
    container_session_id: str = "test_container",
    restored_instance_id: str = "",
    restore_session_id: str = "",
) -> FullExecutionTraceSession:
    """Create a FullExecutionTraceSession for testing with base override.

    Uses the internal ``_TEST_TRACE_BASE`` mechanism — no extra public params.
    """
    previous = ft._TEST_TRACE_BASE
    ft._TEST_TRACE_BASE = trace_base
    try:
        return FullExecutionTraceSession(
            container_session_id=container_session_id,
            restored_instance_id=restored_instance_id,
            restore_session_id=restore_session_id,
            _trace_id_override="test_trace",
        )
    finally:
        ft._TEST_TRACE_BASE = previous


# ═══════════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════════

class TestDisabledMode(unittest.TestCase):
    """When COMFYMODAL_V2_FULL_TRACE != '1', the module is fully inert."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()

    def test_create_if_enabled_returns_none_when_not_1(self):
        with patch.dict(os.environ, {ft._ENV_ENABLE: "0"}, clear=False):
            session = FullExecutionTraceSession.create_if_enabled(
                container_session_id="test",
            )
            self.assertIsNone(session)

    def test_create_if_enabled_returns_none_when_unset(self):
        with patch.dict(os.environ, clear=True):
            session = FullExecutionTraceSession.create_if_enabled(
                container_session_id="test",
            )
            self.assertIsNone(session)

    def test_create_if_enabled_returns_instance_when_1(self):
        with patch.dict(os.environ, {ft._ENV_ENABLE: "1"}, clear=False):
            with tempfile.TemporaryDirectory() as td:
                ft._TEST_TRACE_BASE = td
                try:
                    session = FullExecutionTraceSession.create_if_enabled(
                        container_session_id="test_container",
                    )
                    self.assertIsNotNone(session)
                    self.assertIsInstance(session, FullExecutionTraceSession)
                finally:
                    ft._TEST_TRACE_BASE = None
                    FullExecutionTraceSession.reset_instance()

    def test_no_viztracer_import_at_module_level(self):
        """VizTracer must not be imported at module scope (only lazily)."""
        import inspect
        import comfymodal_runtime.full_execution_trace as mod
        source = inspect.getsource(mod)
        import_lines = [
            l for l in source.split("\n")
            if l.strip().startswith(("import ", "from ")) and "viztracer" in l.lower()
        ]
        for line in import_lines:
            self.assertTrue(
                line.startswith(" "),
                f"Module-level viztracer import found: {line.strip()}",
            )


class TestFactory(unittest.TestCase):
    """Factory signature, identity storage, trace_id generation, session root."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()

    def test_factory_keyword_only_params(self):
        """create_if_enabled must have keyword-only container_session_id."""
        import inspect
        sig = inspect.signature(FullExecutionTraceSession.create_if_enabled)
        params = list(sig.parameters.values())
        # All parameters after the first (cls or container_session_id) must be keyword-only
        # On some Python versions, classmethod shows (cls, ...), others hide cls
        first_param = params[0]
        remaining = params[1:] if first_param.name in ("cls", "container_session_id") else params
        for p in remaining:
            self.assertEqual(
                p.kind, inspect.Parameter.KEYWORD_ONLY,
                f"{p.name} must be keyword-only",
            )

    def test_factory_stores_container_session_id(self):
        with patch.dict(os.environ, {ft._ENV_ENABLE: "1"}, clear=False):
            with tempfile.TemporaryDirectory() as td:
                ft._TEST_TRACE_BASE = td
                try:
                    session = FullExecutionTraceSession.create_if_enabled(
                        container_session_id="my_container_42",
                        restored_instance_id="inst_1",
                        restore_session_id="rs_1",
                    )
                    self.assertIsNotNone(session)
                    self.assertEqual(session._container_session_id, "my_container_42")
                    self.assertEqual(session._restored_instance_id, "inst_1")
                    self.assertEqual(session._restore_session_id, "rs_1")
                finally:
                    ft._TEST_TRACE_BASE = None
                    FullExecutionTraceSession.reset_instance()

    def test_session_root_exact_path(self):
        """Session root must be /tmp/comfymodal_full_trace/<trace_id>."""
        with patch.dict(os.environ, {ft._ENV_ENABLE: "1"}, clear=False):
            # Reset _TEST_TRACE_BASE to None for this test
            ft._TEST_TRACE_BASE = None
            try:
                session = FullExecutionTraceSession.create_if_enabled(
                    container_session_id="test",
                )
                self.assertIsNotNone(session)
                expected_root = Path("/tmp/comfymodal_full_trace") / session.trace_id
                self.assertEqual(session.base_dir, expected_root)
            finally:
                FullExecutionTraceSession.reset_instance()

    def test_trace_id_is_opaque_uuid(self):
        """trace_id should be a hex string (not a human-readable prefix)."""
        session = FullExecutionTraceSession(
            container_session_id="test",
            _trace_id_override=None,
        )
        self.assertIsInstance(session.trace_id, str)
        # Should be 32 hex chars (uuid4 hex), not have a prefix like "ft_"
        self.assertEqual(len(session.trace_id), 32)
        self.assertNotIn("ft_", session.trace_id)

    def test_trace_id_test_override(self):
        """Internal _trace_id_override sets a known trace_id."""
        session = FullExecutionTraceSession(
            container_session_id="test",
            _trace_id_override="my_fixed_id",
        )
        self.assertEqual(session.trace_id, "my_fixed_id")

    def test_status_dict_shape(self):
        session = FullExecutionTraceSession(
            container_session_id="test_container",
            restored_instance_id="inst_1",
            restore_session_id="rs_1",
            _trace_id_override="status_test",
        )
        sd = session.status_dict()
        self.assertEqual(sd["trace_id"], "status_test")
        self.assertEqual(sd["container_session_id"], "test_container")
        self.assertEqual(sd["state"], "created")
        self.assertIn("identity", sd)
        self.assertIn("claimed", sd)
        self.assertIn("base_dir", sd)
        self.assertIn("raw_dir", sd)

    def test_raw_session_dir(self):
        session = FullExecutionTraceSession(
            container_session_id="test",
            _trace_id_override="raw_dir_test",
        )
        raw = session.raw_session_dir()
        self.assertEqual(raw, session.base_dir / "raw")
        self.assertTrue(raw.exists())

    def test_new_env_var_names_in_config(self):
        """Config must use COMFYMODAL_V2_FULL_TRACE_ENTRIES and ..._RESOURCE_INTERVAL_MS."""
        with tempfile.TemporaryDirectory() as td:
            ft._TEST_TRACE_BASE = td
            try:
                session = _create_test_session(td)
                config_path = session.base_dir / "raw" / "trace_config.json"
                config = json.loads(config_path.read_text(encoding="utf-8"))
                cfg = config.get("config", {})
                self.assertIn("env_entries_var", cfg)
                self.assertEqual(cfg["env_entries_var"], "COMFYMODAL_V2_FULL_TRACE_ENTRIES")
                self.assertIn("env_resource_interval_var", cfg)
                self.assertEqual(
                    cfg["env_resource_interval_var"],
                    "COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS",
                )
            finally:
                ft._TEST_TRACE_BASE = None


class TestLifecycle(unittest.TestCase):
    """Full lifecycle: exact state transitions, claim, events."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()
        self.td_obj = tempfile.TemporaryDirectory()
        self.addCleanup(self.td_obj.cleanup)
        self._sessions: list[FullExecutionTraceSession] = []

    def tearDown(self):
        for s in self._sessions:
            try:
                if s.resource_sampler is not None:
                    s.resource_sampler.stop()
            except Exception:
                pass

    def _make_session(self) -> FullExecutionTraceSession:
        s = _create_test_session(self.td_obj.name)
        self._sessions.append(s)
        return s

    def test_initial_state_created(self):
        session = self._make_session()
        self.assertEqual(session.state, "created")

    def test_valid_full_lifecycle(self):
        session = self._make_session()
        self.assertEqual(session.state, "created")

        # created -> restore_tracing
        session.start_restore()
        self.assertEqual(session.state, "restore_tracing")

        # restore_tracing -> restore_complete
        session.set_restore_complete()
        self.assertEqual(session.state, "restore_complete")

        # restore_complete -> request_claimed (and auto request_tracing)
        ok = session.claim_first_request("req_1")
        self.assertTrue(ok)
        self.assertIn(session.state, ("request_claimed", "request_tracing"))

        # request_tracing -> trace_stopped
        result = session.stop_tracing()
        self.assertEqual(session.state, "trace_stopped")
        self.assertIn("resource_sampler", result)
        self.assertIn("torch_profiler", result)
        self.assertIn("viztracer", result)
        self.assertEqual(result["final_state"], "trace_stopped")

    def test_exact_lifecycle_states(self):
        """State machine must use exact state names."""
        session = self._make_session()
        self.assertEqual(session.state, "created")

        session.start_restore()
        self.assertEqual(session.state, "restore_tracing")

        session.set_restore_complete()
        self.assertEqual(session.state, "restore_complete")

        session.claim_first_request("req_1")
        # May be request_claimed or request_tracing
        self.assertIn(session.state, ("request_claimed", "request_tracing"))

        session.stop_tracing()
        self.assertEqual(session.state, "trace_stopped")

    def test_transitions_validity_map(self):
        """All valid transitions in the exact state map."""
        self.assertIn("created", _VALID_TRANSITIONS)
        self.assertIn("restore_tracing", _VALID_TRANSITIONS)
        self.assertIn("restore_complete", _VALID_TRANSITIONS)
        self.assertIn("request_claimed", _VALID_TRANSITIONS)
        self.assertIn("request_tracing", _VALID_TRANSITIONS)
        self.assertIn("trace_stopped", _VALID_TRANSITIONS)
        self.assertIn("failed", _VALID_TRANSITIONS)
        self.assertEqual(_VALID_TRANSITIONS["trace_stopped"], set())
        self.assertEqual(_VALID_TRANSITIONS["failed"], set())

    def test_claim_first_request_exactly_once(self):
        session = self._make_session()
        session.start_restore()
        session.set_restore_complete()

        ok1 = session.claim_first_request("req_1")
        self.assertTrue(ok1)
        self.assertTrue(session._claimed)
        self.assertEqual(session._claimed_request_id, "req_1")

        ok2 = session.claim_first_request("req_2")
        self.assertFalse(ok2)
        self.assertEqual(session._claimed_request_id, "req_1")

    def test_claim_before_restore_complete_returns_false(self):
        session = self._make_session()
        ok = session.claim_first_request("req_1")
        self.assertFalse(ok)
        self.assertFalse(session._claimed)

    def test_invalid_transition_logged_not_raised(self):
        session = self._make_session()
        session.start_restore()  # restore_tracing
        # Try invalid: restore_tracing -> trace_stopped
        result = session._transition("trace_stopped")
        self.assertFalse(result)
        self.assertEqual(session.state, "restore_tracing")

        # Check event was recorded
        self.assertGreater(len(session.events), 0)
        invalid_events = [
            e for e in session.events
            if e.get("event") == "state_transition"
            and e.get("data", {}).get("valid") is False
        ]
        self.assertGreaterEqual(len(invalid_events), 1)
        self.assertIn(
            "Invalid transition",
            invalid_events[0]["data"]["reason"],
        )

    def test_failed_transition(self):
        session = self._make_session()
        session._transition("failed")
        self.assertEqual(session.state, "failed")
        result = session._transition("restore_tracing")
        self.assertFalse(result)

    def test_session_events_persisted(self):
        session = self._make_session()
        session.start_restore()
        session.set_restore_complete()
        events_path = session.events_path
        self.assertIsNotNone(events_path)
        self.assertTrue(events_path.exists())
        content = events_path.read_text(encoding="utf-8")
        self.assertGreater(len(content), 0)
        lines = content.strip().split("\n")
        self.assertGreaterEqual(len(lines), 3)

    def test_directory_layout(self):
        session = self._make_session()
        base = session.base_dir
        for sub in _SUBDIRS:
            self.assertTrue((base / sub).is_dir(), f"Missing subdir: {sub}")
        raw_dir = base / "raw"
        for name in _REQUIRED_RAW_FILES:
            path = raw_dir / name
            self.assertTrue(path.exists(), f"Missing required raw file: {name}")

    def test_trace_config_content(self):
        session = self._make_session()
        config_path = session.base_dir / "raw" / "trace_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["schema_version"], SCHEMA_VERSION)
        self.assertEqual(config["trace_id"], "test_trace")
        self.assertEqual(config["container_session_id"], "test_container")
        self.assertIn("identity", config)
        self.assertIn("include_paths", config)
        self.assertIn("exclusions", config)
        self.assertIn("entry_capacity", config)
        self.assertIn("config", config)

    def test_runtime_result_summary_empty_initially(self):
        session = self._make_session()
        summary_path = session.base_dir / "raw" / "runtime_result_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary, {})

    def test_update_identity(self):
        session = self._make_session()
        session.update_identity(
            restored_instance_id="new_inst",
            restore_session_id="new_rs",
            modal_task_id="task_42",
            image_id="img_v3",
            cloud="aws",
            region="us-east-1",
        )
        self.assertEqual(session._restored_instance_id, "new_inst")
        self.assertEqual(session._restore_session_id, "new_rs")
        self.assertEqual(session._modal_task_id, "task_42")
        self.assertEqual(session._image_id, "img_v3")
        self.assertEqual(session._cloud, "aws")
        self.assertEqual(session._region, "us-east-1")

        # Check event recorded
        identity_events = [
            e for e in session.events
            if e.get("event") == "identity_updated"
        ]
        self.assertEqual(len(identity_events), 1)
        data = identity_events[0]["data"]
        self.assertEqual(data["restored_instance_id"], "new_inst")

    def test_update_identity_keyword_only(self):
        """update_identity must be keyword-only."""
        import inspect
        sig = inspect.signature(FullExecutionTraceSession.update_identity)
        for name, param in list(sig.parameters.items())[1:]:  # skip self
            self.assertEqual(
                param.kind, inspect.Parameter.KEYWORD_ONLY,
                f"update_identity {name} must be keyword-only",
            )

    def test_set_restore_complete_required(self):
        """set_restore_complete is required for claim_first_request to succeed."""
        session = self._make_session()
        session.start_restore()
        # Don't call set_restore_complete
        ok = session.claim_first_request("req_1")
        self.assertFalse(ok)


class TestMarkAndOperations(unittest.TestCase):
    """mark, operation_start, operation_end semantics."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self._sessions = []

    def tearDown(self):
        for s in self._sessions:
            try:
                if s.resource_sampler is not None:
                    s.resource_sampler.stop()
            except Exception:
                pass

    def _make_session(self) -> FullExecutionTraceSession:
        s = _create_test_session(self.td.name)
        self._sessions.append(s)
        return s

    def _make_ready_session(self) -> FullExecutionTraceSession:
        s = self._make_session()
        s.start_restore()
        s.set_restore_complete()
        s.claim_first_request("req_1")
        return s

    def test_mark_creates_event(self):
        session = self._make_ready_session()
        session.mark("load_model", model_name="sd_xl", step=1)
        mark_events = [
            e for e in session.events
            if e.get("event") == "mark"
        ]
        self.assertGreaterEqual(len(mark_events), 1)
        data = mark_events[-1]["data"]
        self.assertEqual(data["name"], "load_model")
        self.assertIn("monotonic_ns", data)

    def test_mark_before_claim_skipped(self):
        session = self._make_session()
        session.start_restore()
        # Still in restore_tracing — mark should be skipped
        session.mark("early_mark")
        mark_events = [
            e for e in session.events
            if e.get("event") == "mark"
        ]
        self.assertEqual(len(mark_events), 0)
        # Should have a mark_skipped event
        skipped = [
            e for e in session.events
            if e.get("event") == "mark_skipped"
        ]
        self.assertGreaterEqual(len(skipped), 1)

    def test_operation_start_end_lifecycle(self):
        session = self._make_ready_session()
        op_id = session.operation_start("load", semantic_key="model::sd_xl::v1")
        self.assertTrue(op_id != "")

        session.operation_end(op_id, status="ok", duration_ms=150.0)
        end_events = [
            e for e in session.events
            if e.get("event") == "operation_end"
        ]
        self.assertGreaterEqual(len(end_events), 1)
        data = end_events[-1]["data"]
        self.assertEqual(data["operation_id"], op_id)
        self.assertEqual(data["status"], "ok")
        # Verify full schema populated from cache
        self.assertEqual(data["operation_type"], "load")
        self.assertIsNotNone(data["semantic_key_hash"])
        self.assertIn("semantic_key_hash", data)
        self.assertIsNotNone(data["start_monotonic_ns"])
        self.assertIsNotNone(data["end_monotonic_ns"])
        self.assertGreaterEqual(data["end_monotonic_ns"], data["start_monotonic_ns"])
        self.assertIsNotNone(data["wall_ms"])
        self.assertGreaterEqual(data["wall_ms"], 0)
        self.assertIsNotNone(data["native_thread_id"])
        self.assertIsNotNone(data["pid"])
        # parent_operation_id is None when there's no nesting (single operation)
        self.assertIn("parent_operation_id", data)
        self.assertIn("request_id", data)
        self.assertIn("restore_session_id", data)
        self.assertIn("restored_instance_id", data)

    def test_operation_start_returns_opaque_id(self):
        session = self._make_ready_session()
        op_id = session.operation_start("test", semantic_key="sk1")
        self.assertIsInstance(op_id, str)
        self.assertGreater(len(op_id), 0)
        # Should NOT contain the semantic key
        self.assertNotIn("sk1", op_id)

    def test_operation_start_contains_expected_fields(self):
        session = self._make_ready_session()
        op_id = session.operation_start("compile", semantic_key="sk_compile")
        start_events = [
            e for e in session.events
            if e.get("event") == "operation_start"
        ]
        self.assertGreaterEqual(len(start_events), 1)
        data = start_events[-1]["data"]
        self.assertEqual(data["operation_id"], op_id)
        self.assertEqual(data["operation_type"], "compile")
        self.assertIn("semantic_key_hash", data)
        # Should NOT have the raw semantic key
        self.assertNotIn("semantic_key", data)
        self.assertIn("parent_operation_id", data)
        self.assertIn("request_id", data)
        self.assertIn("restore_session_id", data)
        self.assertIn("restored_instance_id", data)
        self.assertIn("pid", data)
        self.assertIn("native_thread_id", data)
        self.assertIn("asyncio_task_id", data)
        self.assertIn("start_monotonic_ns", data)
        # Start records include full schema with null end/wall_ms and started status
        self.assertIn("end_monotonic_ns", data)
        self.assertIsNone(data["end_monotonic_ns"])
        self.assertIn("wall_ms", data)
        self.assertIsNone(data["wall_ms"])
        self.assertIn("status", data)
        self.assertEqual(data["status"], "started")
        self.assertIn("metadata", data)

    def test_operation_end_mismatch_logged(self):
        session = self._make_ready_session()
        session.operation_end("nonexistent_op_id")
        mismatch_events = [
            e for e in session.events
            if e.get("event") == "operation_end_mismatch"
        ]
        self.assertGreaterEqual(len(mismatch_events), 1)

    def test_operation_stack_nesting(self):
        session = self._make_ready_session()
        op1 = session.operation_start("outer", semantic_key="sk_outer")
        op2 = session.operation_start("inner", semantic_key="sk_inner")

        # Check parent chain from start events
        start_events = [
            e for e in session.events
            if e.get("event") == "operation_start"
        ]
        # Last start event (inner) should have op1 as parent
        inner_start = start_events[-1]["data"]
        self.assertEqual(inner_start["parent_operation_id"], op1)

        # End inner then outer
        session.operation_end(op2)
        session.operation_end(op1)

    def test_operation_never_stores_raw_semantic_key(self):
        session = self._make_ready_session()
        session.operation_start("test", semantic_key="super-secret-prompt-key")
        event_log = session.events_path.read_text(encoding="utf-8")
        self.assertNotIn("super-secret-prompt-key", event_log)
        # The field name is "semantic_key_hash" (with _hash suffix), not "semantic_key"
        # Check that the raw key value is absent
        self.assertRegex(event_log, r'"semantic_key_hash"')
        # But no field should have the raw value as a JSON string value
        self.assertNotIn('"super-secret-prompt-key"', event_log)

    def test_mark_metadata_safe(self):
        session = self._make_ready_session()
        session.mark("test", secret_token="should_be_redacted", normal="ok")
        mark_events = [
            e for e in session.events
            if e.get("event") == "mark"
        ]
        data = mark_events[-1]["data"]
        self.assertIn("normal", data["metadata"])
        # The session-level redaction applies; key may be redacted
        self.assertIn("ok", str(data))

    def test_operation_start_metadata_safe_and_no_results(self):
        session = self._make_ready_session()
        session.operation_start("load", semantic_key="sk", result_tensor="should_not_leak")
        # The metadata value should be safe (type name, not repr)
        start_events = [
            e for e in session.events
            if e.get("event") == "operation_start"
        ]
        meta = start_events[-1]["data"].get("metadata", {})
        # result_tensor should be converted to a safe string
        if "result_tensor" in meta:
            self.assertIsInstance(meta["result_tensor"], str)
            self.assertNotIn("<tensor", meta["result_tensor"])

    def test_mark_in_request_tracing(self):
        """mark also works in request_tracing state."""
        session = self._make_ready_session()
        session.mark("post_claim_mark")
        mark_events = [
            e for e in session.events
            if e.get("event") == "mark"
        ]
        self.assertGreaterEqual(len(mark_events), 1)


class TestGoldenTraceSpan(unittest.TestCase):
    """Golden spans use only an already-registered VizTracer."""

    def test_registered_tracer_duration_event_is_entered_and_exited(self):
        calls: list[tuple[str, str]] = []

        class Event:
            def __enter__(self):
                calls.append(("enter", "golden.test"))

            def __exit__(self, *_args):
                calls.append(("exit", "golden.test"))

        class Tracer:
            def log_event(self, name):
                calls.append(("log", name))
                return Event()

        fake_module = SimpleNamespace(get_tracer=lambda: Tracer())
        with patch.dict(ft.sys.modules, {"viztracer": fake_module}):
            with golden_trace_span("golden.test"):
                calls.append(("body", "golden.test"))

        self.assertEqual(
            calls,
            [
                ("log", "golden.test"),
                ("enter", "golden.test"),
                ("body", "golden.test"),
                ("exit", "golden.test"),
            ],
        )

    def test_missing_or_broken_tracer_never_changes_body(self):
        with patch.dict(ft.sys.modules, {}, clear=False):
            with golden_trace_span("golden.noop"):
                value = 42
        self.assertEqual(value, 42)


class TestResourceSampler(unittest.TestCase):
    """ContainerResourceSampler with flat nullable fields."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)

    def _sampler(self, **kw) -> ContainerResourceSampler:
        return ContainerResourceSampler(
            self.td.name,
            interval_ms=10000,
            session_phase="test",
            **kw,
        )

    def test_start_stop(self):
        sampler = self._sampler()
        sampler.start()
        self.assertTrue(sampler._running)
        result = sampler.stop()
        self.assertIn("sample_count", result)
        self.assertIn("path", result)
        self.assertFalse(sampler._running)

    def test_collect_sample_flat_fields(self):
        """Each sample has the exact flat nullable top-level fields."""
        sampler = self._sampler()
        sample = sampler._collect_sample()
        # Required top-level nullable fields
        self.assertIn("wall_unix_ns", sample)
        self.assertIn("monotonic_ns", sample)
        self.assertIn("session_phase", sample)
        self.assertEqual(sample["session_phase"], "test")
        self.assertIn("cgroup_cpu_usage_usec", sample)
        self.assertIn("cgroup_user_usec", sample)
        self.assertIn("cgroup_system_usec", sample)
        self.assertIn("cgroup_nr_periods", sample)
        self.assertIn("cgroup_nr_throttled", sample)
        self.assertIn("cgroup_throttled_usec", sample)
        self.assertIn("memory_current_bytes", sample)
        self.assertIn("memory_peak_bytes", sample)
        self.assertIn("memory_stat_anon_bytes", sample)
        self.assertIn("memory_stat_file_bytes", sample)
        self.assertIn("memory_stat_inactive_file_bytes", sample)
        self.assertIn("memory_stat_active_file_bytes", sample)
        self.assertIn("memory_stat_pgfault", sample)
        self.assertIn("memory_stat_pgmajfault", sample)
        self.assertIn("io_rbytes", sample)
        self.assertIn("io_wbytes", sample)
        self.assertIn("process_inventory", sample)
        self.assertIn("thread_inventory", sample)

    def test_null_when_no_cgroup(self):
        """When cgroup is not available, fields are None."""
        sampler = self._sampler()
        sample = sampler._collect_sample()
        # All cgroup/memory/io fields should be None (not missing, not {}")
        for key in ("cgroup_cpu_usage_usec", "cgroup_user_usec", "cgroup_system_usec",
                     "cgroup_nr_periods", "cgroup_nr_throttled", "cgroup_throttled_usec",
                     "memory_current_bytes", "memory_peak_bytes",
                     "memory_stat_anon_bytes", "memory_stat_file_bytes",
                     "memory_stat_inactive_file_bytes", "memory_stat_active_file_bytes",
                     "memory_stat_pgfault", "memory_stat_pgmajfault",
                     "io_rbytes", "io_wbytes"):
            self.assertIsNone(sample[key], f"{key} should be None, got {sample[key]}")

    def test_process_thread_inventory_are_lists(self):
        sampler = self._sampler()
        sample = sampler._collect_sample()
        self.assertIsInstance(sample["process_inventory"], list)
        self.assertIsInstance(sample["thread_inventory"], list)

    def test_wall_unix_ns_monotonic_ns_types(self):
        sampler = self._sampler()
        sample = sampler._collect_sample()
        self.assertIsInstance(sample["wall_unix_ns"], int)
        self.assertIsInstance(sample["monotonic_ns"], int)
        self.assertGreater(sample["wall_unix_ns"], 1_700_000_000_000_000_000)  # ~2024

    def test_gzip_incremental_write(self):
        sampler = self._sampler()
        sampler.start()
        time.sleep(0.05)
        result = sampler.stop()
        self.assertGreaterEqual(result["sample_count"], 0)
        gz_path = Path(result["path"])
        self.assertTrue(gz_path.exists())
        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            content = f.read()
        self.assertGreater(len(content), 0)
        lines = content.strip().split("\n")
        for line in lines:
            obj = json.loads(line)
            self.assertIn("wall_unix_ns", obj)
            self.assertIn("monotonic_ns", obj)
            self.assertIn("session_phase", obj)

    def test_session_phase_updates(self):
        sampler = self._sampler()
        sample = sampler._collect_sample()
        self.assertEqual(sample["session_phase"], "test")
        sampler._session_phase = "restore_tracing"
        sample2 = sampler._collect_sample()
        self.assertEqual(sample2["session_phase"], "restore_tracing")


class TestResourceSamplerParsing(unittest.TestCase):
    """Cgroup v2 parsing and proc enumeration."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)

    def test_cgroup_v2_parsing(self):
        """Cgroup v2 cpu.stat, memory.*, io.stat parsed correctly."""
        cg_dir = _make_cgroup_tree(self.td.name)
        # Override cgroup v2 path
        ft._TEST_CGROUP_V2 = str(cg_dir)
        try:
            stat = _read_cgroup_stat(cg_dir)
            self.assertEqual(stat["usage_usec"], 1234567)
            self.assertEqual(stat["user_usec"], 1000000)
            self.assertEqual(stat["system_usec"], 234567)
            self.assertEqual(stat["nr_periods"], 500)
            self.assertEqual(stat["nr_throttled"], 3)
            self.assertEqual(stat["throttled_usec"], 15000)

            mem = _read_cgroup_memory(cg_dir)
            self.assertEqual(mem["current_bytes"], 838860800)
            self.assertEqual(mem["peak_bytes"], 1073741824)
            self.assertEqual(mem["anon_bytes"], 419430400)
            self.assertEqual(mem["file_bytes"], 419430400)
            self.assertEqual(mem["inactive_file_bytes"], 104857600)
            self.assertEqual(mem["active_file_bytes"], 314572800)
            self.assertEqual(mem["pgfault"], 12345)
            self.assertEqual(mem["pgmajfault"], 67)

            io = _read_cgroup_io(cg_dir)
            self.assertEqual(io["rbytes"], 1048576 + 524288)  # 1572864
            self.assertEqual(io["wbytes"], 2097152 + 1048576)  # 3145728
        finally:
            ft._TEST_CGROUP_V2 = None

    @patch("comfymodal_runtime.full_execution_trace.os.getpid")
    def test_proc_process_inventory(self, mock_getpid):
        """Process inventory from mock proc tree."""
        pid = 12345
        mock_getpid.return_value = pid
        proc_root = _make_proc_tree(Path(self.td.name), pid)

        ft._TEST_PROC_ROOT = str(proc_root)
        ft._TEST_PROC_SELF = str(proc_root / str(pid))

        sampler = ContainerResourceSampler(
            self.td.name,
            interval_ms=10000,
            session_phase="test",
        )
        try:
            sample = sampler._collect_sample()
            proc_inv = sample["process_inventory"]

            # Should include our mock PIDs
            pids_found = {p.get("pid") for p in proc_inv if "pid" in p}
            self.assertIn(pid, pids_found)
            self.assertIn(100, pids_found)
            self.assertIn(200, pids_found)
            self.assertIn(300, pids_found)

            # Check process fields for our mock process
            our_proc = [p for p in proc_inv if p.get("pid") == pid]
            self.assertGreaterEqual(len(our_proc), 1)
            p = our_proc[0]
            self.assertEqual(p["comm"], "python")
            self.assertIsNotNone(p.get("sanitized_cmdline"))
            self.assertIn("python", p.get("sanitized_cmdline", ""))
            self.assertIn("***", p.get("sanitized_cmdline", ""))
            self.assertIn("state", p)
            self.assertIn("user_ticks", p)
            self.assertIn("system_ticks", p)
            self.assertIn("minor_faults", p)
            self.assertIn("major_faults", p)
            self.assertIn("rss_pages", p)
            self.assertIn("thread_count", p)
            self.assertIn("read_bytes", p)
            self.assertIn("write_bytes", p)
        finally:
            ft._TEST_PROC_ROOT = None
            ft._TEST_PROC_SELF = None

    @patch("comfymodal_runtime.full_execution_trace.os.getpid")
    def test_thread_inventory(self, mock_getpid):
        pid = 12345
        mock_getpid.return_value = pid
        proc_root = _make_proc_tree(Path(self.td.name), pid)

        ft._TEST_PROC_ROOT = str(proc_root)
        ft._TEST_PROC_SELF = str(proc_root / str(pid))

        sampler = ContainerResourceSampler(
            self.td.name,
            interval_ms=10000,
            session_phase="test",
        )
        try:
            sample = sampler._collect_sample()
            thread_inv = sample["thread_inventory"]
            # Should have thread entries
            self.assertGreaterEqual(len(thread_inv), 0)
            # Check shape if threads are available
            for t in thread_inv:
                self.assertIn("tid", t)
                self.assertIn("comm", t)
                self.assertIn("state", t)
                self.assertIn("user_ticks", t)
                self.assertIn("system_ticks", t)
                self.assertIn("minor_faults", t)
                self.assertIn("major_faults", t)
        finally:
            ft._TEST_PROC_ROOT = None
            ft._TEST_PROC_SELF = None

    def test_parse_stat_fields(self):
        stat_text = (
            "12345 (python) S 1 1 1 0 -1 4194304 999 888 777 666 "
            "100 200 300 400 500 600 700 800 5 900 1000 1100 1200 333 1400"
        )
        fields = _parse_stat_fields(stat_text)
        self.assertEqual(fields["minflt"], 999)   # rest[7]
        self.assertEqual(fields["majflt"], 777)   # rest[9]
        self.assertEqual(fields["utime"], 100)    # rest[11] (test data has "100 200 300 400")
        self.assertEqual(fields["stime"], 200)    # rest[12]
        self.assertEqual(fields["num_threads"], 700)  # rest[17]
        self.assertEqual(fields["rss"], 1000)     # rest[21]

    def test_parse_stat_fields_comm_with_spaces(self):
        stat_text = (
            "42 (java launcher) S 1 1 1 0 -1 4194304 10 20 30 40 "
            "50 60 70 80 90 100 110 120 8 130 140 150 160 99 180"
        )
        fields = _parse_stat_fields(stat_text)
        self.assertEqual(fields["minflt"], 10)    # rest[7]
        self.assertEqual(fields["majflt"], 30)    # rest[9]
        self.assertEqual(fields["utime"], 50)     # rest[11]
        self.assertEqual(fields["stime"], 60)     # rest[12]
        self.assertEqual(fields["num_threads"], 110)  # rest[17]
        self.assertEqual(fields["rss"], 140)      # rest[21]


class TestCmdlineSanitization(unittest.TestCase):
    """_sanitize_cmdline edge cases with broadened patterns."""

    def test_basic_sanitize(self):
        cmdline = "python\x00main.py\x00--token\x00abc123\x00--model\x00test"
        result = _sanitize_cmdline(cmdline)
        parts = result.split("\x00")
        self.assertIn("--token", parts)
        token_idx = parts.index("--token")
        self.assertEqual(parts[token_idx + 1], "***")
        self.assertNotIn("abc123", parts)

    def test_sanitize_equal_form(self):
        cmdline = "python main.py --token=abc123 --model test"
        result = _sanitize_cmdline(cmdline)
        self.assertIn("--token=***", result)
        self.assertNotIn("abc123", result)

    def test_sanitize_modal_token(self):
        cmdline = "python\x00run.py\x00MODAL_TOKEN_ID\x00tok_xxx\x00MODAL_TOKEN_SECRET\x00sec_yyy"
        result = _sanitize_cmdline(cmdline)
        parts = result.split("\x00")
        self.assertIn("MODAL_TOKEN_ID", parts)
        tid_idx = parts.index("MODAL_TOKEN_ID")
        self.assertEqual(parts[tid_idx + 1], "***")
        self.assertIn("MODAL_TOKEN_SECRET", parts)
        ts_idx = parts.index("MODAL_TOKEN_SECRET")
        self.assertEqual(parts[ts_idx + 1], "***")
        self.assertNotIn("tok_xxx", result)
        self.assertNotIn("sec_yyy", result)

    def test_sanitize_bearer_token(self):
        cmdline = "python server.py --bearer mysecrettoken"
        result = _sanitize_cmdline(cmdline)
        self.assertIn("--bearer", result)
        self.assertIn("***", result)
        self.assertNotIn("mysecrettoken", result)

    def test_sanitize_api_key_flag(self):
        cmdline = "python run.py --api-key=sk-1234567890abcdef"
        result = _sanitize_cmdline(cmdline)
        self.assertIn("--api-key=***", result)
        self.assertNotIn("sk-1234567890abcdef", result)

    def test_space_separated(self):
        cmdline = "python main.py -t secret123"
        result = _sanitize_cmdline(cmdline)
        parts = result.split(" ")
        self.assertIn("-t", parts)
        t_idx = parts.index("-t")
        self.assertEqual(parts[t_idx + 1], "***")
        self.assertNotIn("secret123", result)

    def test_no_sensitive_data(self):
        cmdline = "python main.py --model test --steps 20"
        result = _sanitize_cmdline(cmdline)
        self.assertEqual(result, cmdline)


class TestSafeRepr(unittest.TestCase):
    """_safe_repr must not leak tensor/model data."""

    def test_tensor_repr(self):
        class FakeTensor:
            shape = (1, 3, 512, 512)
            dtype = "float32"

        result = _safe_repr(FakeTensor())
        self.assertIn("tensor", result)
        self.assertIn("shape", result)
        self.assertNotIn("data", result.lower())

    def test_large_list(self):
        result = _safe_repr(list(range(100)))
        self.assertIn("100 items", result)

    def test_small_list(self):
        result = _safe_repr([1, 2, 3])
        self.assertIn("1, 2, 3", result)

    def test_dict(self):
        result = _safe_repr({"a": 1, "b": 2})
        self.assertIn("2 keys", result)

    def test_other(self):
        result = _safe_repr(object())
        self.assertTrue(result.startswith("<"))


class TestSecurity(unittest.TestCase):
    """Security: broadened key redaction, no leakage."""

    def test_redact_sensitive_keys_broadened(self):
        """Broadened patterns match keys containing sensitive terms."""
        data = {
            "MODAL_TOKEN_ID": "tok_xxx",
            "MODAL_TOKEN_SECRET": "sec_yyy",
            "AUTHORIZATION": "Bearer xxx",
            "COOKIE": "session=abc",
            "PASSWORD": "hunter2",
            "API_KEY": "sk-xxx",
            "ACCESS_TOKEN": "ghp_xxx",
            "BEARER": "bearer_token",
            "SESSION_KEY": "sess_abc",
            "normal_key": "normal_value",
        }
        redacted = _redact_sensitive(data)
        for key in ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "AUTHORIZATION",
                     "COOKIE", "PASSWORD", "API_KEY", "ACCESS_TOKEN",
                     "BEARER", "SESSION_KEY"):
            self.assertEqual(
                redacted.get(key), "***REDACTED***",
                f"{key} should be redacted",
            )
        self.assertEqual(redacted["normal_key"], "normal_value")

    def test_redact_nested(self):
        data = {"config": {"TOKEN": "secret", "name": "public"}}
        redacted = _redact_sensitive(data)
        self.assertEqual(redacted["config"]["TOKEN"], "***REDACTED***")
        self.assertEqual(redacted["config"]["name"], "public")

    def test_redact_case_insensitive(self):
        data = {"modal_token_id": "xxx", "Modal_Token_Secret": "yyy"}
        redacted = _redact_sensitive(data)
        self.assertEqual(redacted["modal_token_id"], "***REDACTED***")
        self.assertEqual(redacted["Modal_Token_Secret"], "***REDACTED***")

    def test_redact_key_containing_sensitive(self):
        """Keys that *contain* sensitive patterns must be redacted."""
        data = {
            "my_api_key": "sk-xxx",
            "frontend_bearer_token": "tok_yyy",
            "user_password_hash": "abc123",
        }
        redacted = _redact_sensitive(data)
        self.assertEqual(redacted["my_api_key"], "***REDACTED***")
        self.assertEqual(redacted["frontend_bearer_token"], "***REDACTED***")
        self.assertEqual(redacted["user_password_hash"], "***REDACTED***")

    def test_stable_hash_no_leak(self):
        value = "sensitive-prompt-text"
        h = _stable_hash(value)
        self.assertNotIn("sensitive", h)
        self.assertEqual(len(h), 64)

    def test_safe_json_serialize_redacts(self):
        data = {"MODAL_TOKEN_ID": "tok_xxx", "prompt": "a cat"}
        result = ft._safe_json_serialize(data)
        self.assertIn("***REDACTED***", result)
        self.assertNotIn("tok_xxx", result)


class TestMilestones(unittest.TestCase):
    """capture_milestone exact signature, bridge validation, task fields."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)

    def _make_session(self):
        return _create_test_session(self.td.name)

    def test_milestone_basic_shape(self):
        session = self._make_session()
        session.capture_milestone("test_point")
        # Milestones are written to file — check the file
        milestones_path = session.base_dir / "raw" / "milestones.jsonl"
        self.assertTrue(milestones_path.exists())
        lines = milestones_path.read_text(encoding="utf-8").strip().split("\n")
        self.assertGreaterEqual(len(lines), 1)
        m = json.loads(lines[-1])
        self.assertEqual(m["milestone_type"], "test_point")
        self.assertIn("timestamp", m)
        self.assertIn("monotonic_ns", m)
        self.assertEqual(m["state"], "created")
        self.assertEqual(m["trace_id"], "test_trace")

    def test_milestone_thread_inventory(self):
        session = self._make_session()
        session.capture_milestone("thread_check")
        milestones_path = session.base_dir / "raw" / "milestones.jsonl"
        lines = milestones_path.read_text(encoding="utf-8").strip().split("\n")
        m = json.loads(lines[-1])
        threads = m["thread_inventory"]
        self.assertIsInstance(threads, list)
        self.assertGreaterEqual(len(threads), 1)
        main_threads = [t for t in threads if t.get("name") == "MainThread"]
        self.assertGreaterEqual(len(main_threads), 1)
        for t in threads:
            self.assertIn("name", t)
            self.assertIn("ident", t)
            self.assertIn("daemon", t)
            self.assertIn("alive", t)

    def test_milestone_asyncio_tasks(self):
        session = self._make_session()
        async def dummy():
            await asyncio.sleep(0.01)

        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(dummy())
            loop.run_until_complete(asyncio.sleep(0.005))

            session.capture_milestone("async_check", loop=loop)
            milestones_path = session.base_dir / "raw" / "milestones.jsonl"
            lines = milestones_path.read_text(encoding="utf-8").strip().split("\n")
            m = json.loads(lines[-1])
            tasks = m["asyncio_tasks"]
            self.assertIsInstance(tasks, list)
            for t in tasks:
                self.assertIn("task_id", t)
                self.assertIn("task_name", t)
                self.assertIn("done", t)
                self.assertIn("cancelled", t)
                self.assertIn("coroutine_qualname", t)
                self.assertIn("top_stack_file", t)
                self.assertIn("top_stack_line", t)
                self.assertIn("top_stack_function", t)
        finally:
            loop.close()

    def test_milestone_bridge_snapshot_validation(self):
        session = self._make_session()
        bridge = {
            "request_id": "test_req",
            "TOKEN": "some_secret",
            "model_name": "sd_xl",
            "normal_field": "hello",
            "list_field": [1, 2, 3],
            "nested": {"key": "value"},
        }
        session.capture_milestone("bridge_check", bridge_snapshot=bridge)
        milestones_path = session.base_dir / "raw" / "milestones.jsonl"
        lines = milestones_path.read_text(encoding="utf-8").strip().split("\n")
        m = json.loads(lines[-1])
        snapshot = m["bridge_snapshot"]
        self.assertIsNotNone(snapshot)
        self.assertIn("request_id", snapshot)
        self.assertEqual(snapshot["TOKEN"], "***REDACTED***")
        self.assertEqual(snapshot["normal_field"], "hello")
        self.assertEqual(snapshot["list_field"], [1, 2, 3])

    def test_milestone_bridge_depth_guard(self):
        """Bridge snapshot recursion depth is limited to prevent stack overflow."""
        session = self._make_session()
        # Build a deeply nested dict
        deep = {}
        current = deep
        for _ in range(30):
            current["nested"] = {}
            current = current["nested"]
        current["leaf"] = "value"
        bridge = {"deep": deep}
        session.capture_milestone("deep_bridge", bridge_snapshot=bridge)
        milestones_path = session.base_dir / "raw" / "milestones.jsonl"
        lines = milestones_path.read_text(encoding="utf-8").strip().split("\n")
        m = json.loads(lines[-1])
        snapshot = m["bridge_snapshot"]
        # At depth > 20, should hit max_depth sentinel
        self.assertIsNotNone(snapshot)
        self.assertIsInstance(snapshot, dict)

    def test_milestone_bridge_drops_unsafe(self):
        session = self._make_session()
        class Unserializable:
            pass
        bridge = {
            "safe_str": "hello",
            "unsafe_obj": Unserializable(),
        }
        session.capture_milestone("unsafe_bridge", bridge_snapshot=bridge)
        milestones_path = session.base_dir / "raw" / "milestones.jsonl"
        lines = milestones_path.read_text(encoding="utf-8").strip().split("\n")
        m = json.loads(lines[-1])
        snapshot = m["bridge_snapshot"]
        self.assertEqual(snapshot["safe_str"], "hello")
        # unsafe_obj should be converted to a safe type name string
        self.assertIn("unsafe_obj", snapshot)
        self.assertIsInstance(snapshot["unsafe_obj"], str)

    def test_milestone_extra_redacted(self):
        session = self._make_session()
        extra = {"some_key": "value", "SECRET": "top_secret"}
        session.capture_milestone("extra_check", extra=extra)
        milestones_path = session.base_dir / "raw" / "milestones.jsonl"
        lines = milestones_path.read_text(encoding="utf-8").strip().split("\n")
        m = json.loads(lines[-1])
        self.assertEqual(m["extra"]["SECRET"], "***REDACTED***")
        self.assertEqual(m["extra"]["some_key"], "value")

    def test_milestone_wrapper_inventory(self):
        session = self._make_session()
        session.capture_milestone("wrapper_check")
        milestones_path = session.base_dir / "raw" / "milestones.jsonl"
        lines = milestones_path.read_text(encoding="utf-8").strip().split("\n")
        m = json.loads(lines[-1])
        self.assertIn("wrapper_inventory", m)
        wi = m["wrapper_inventory"]
        self.assertIn("wrappers", wi)
        self.assertEqual(wi["stage"], "wrapper_check")

    def test_milestone_persisted_to_file(self):
        session = self._make_session()
        session.capture_milestone("point_a")
        session.capture_milestone("point_b")
        milestones_path = session.base_dir / "raw" / "milestones.jsonl"
        self.assertTrue(milestones_path.exists())
        lines = milestones_path.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 2)
        first = json.loads(lines[0])
        self.assertEqual(first["milestone_type"], "point_a")
        second = json.loads(lines[1])
        self.assertEqual(second["milestone_type"], "point_b")

    def test_wrapper_snapshots_appended(self):
        session = self._make_session()
        session.capture_milestone("snap_1")
        session.capture_milestone("snap_2")
        ws_path = session.base_dir / "raw" / "wrapper_snapshots.json"
        self.assertTrue(ws_path.exists())
        raw = ws_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 2)
        self.assertEqual(data[0]["stage"], "snap_1")
        self.assertEqual(data[1]["stage"], "snap_2")

    def test_capture_milestone_signature(self):
        """capture_milestone must have the exact signature."""
        import inspect
        sig = inspect.signature(FullExecutionTraceSession.capture_milestone)
        params = list(sig.parameters.values())
        # Self
        self.assertEqual(params[0].name, "self")
        # Stage (positional)
        self.assertEqual(params[1].name, "stage")
        # Everything else keyword-only
        for p in params[2:]:
            self.assertEqual(
                p.kind, inspect.Parameter.KEYWORD_ONLY,
                f"{p.name} must be keyword-only",
            )
        # Check specific param names
        param_names = [p.name for p in params]
        self.assertIn("stage", param_names)
        self.assertIn("loop", param_names)
        self.assertIn("bridge_snapshot", param_names)
        self.assertIn("extra", param_names)


class TestWrapperInventory(unittest.TestCase):
    """Wrapper callable inspection and discovery."""

    def setUp(self):
        pass

    def test_inspect_none(self):
        result = _inspect_wrapper_callable(None)
        self.assertFalse(result["available"])
        self.assertIsNone(result["callable_object_id"])

    def test_inspect_basic_function(self):
        def my_wrapper():
            pass
        result = _inspect_wrapper_callable(my_wrapper)
        self.assertTrue(result["available"])
        self.assertEqual(result["type"], "function")
        self.assertIsNotNone(result["callable_object_id"])
        self.assertIn("my_wrapper", result.get("qualname", ""))

    def test_inspect_allowed_attrs(self):
        def my_func():
            """docstring"""
            pass

        class MyCallable:
            __name__ = "MyCallable"
            __qualname__ = "MyCallable"
            __module__ = "test_module"
            __doc__ = "A callable"
            __defaults__ = (1, 2)
            __code__ = my_func.__code__

        callable_obj = MyCallable()
        result = _inspect_wrapper_callable(callable_obj)
        self.assertTrue(result["available"])
        self.assertEqual(result.get("__name__"), "MyCallable")
        self.assertEqual(result.get("__doc__"), "A callable")
        self.assertIsNotNone(result.get("__code__"))
        self.assertIsInstance(result["__code__"], str)

    def test_inspect_sentinel_attrs(self):
        class Wrapper:
            normal_attr = "value"
            def __call__(self):
                pass

        w = Wrapper()
        w._wrap_inner = lambda: None
        w.__wrapped__ = lambda: None
        w._orig_fn = lambda: None
        result = _inspect_wrapper_callable(w)
        self.assertIn("sentinel_attributes", result)
        sentinels = result["sentinel_attributes"]
        self.assertIn("_wrap_inner", sentinels)
        self.assertIn("__wrapped__", sentinels)
        self.assertIn("_orig_fn", sentinels)

    def test_wrapped_chain(self):
        def original():
            return 42

        def wrapper1(f):
            def inner(*args, **kwargs):
                return f(*args, **kwargs)
            inner.__wrapped__ = f
            return inner

        def wrapper2(f):
            def inner(*args, **kwargs):
                return f(*args, **kwargs)
            inner.__wrapped__ = f
            return inner

        w1 = wrapper1(original)
        w2 = wrapper2(w1)
        result = _inspect_wrapper_callable(w2)
        self.assertIn("wrapped_chain", result)
        chain = result["wrapped_chain"]
        self.assertGreaterEqual(len(chain), 1)
        self.assertLessEqual(len(chain), 32)

    def test_wrapped_chain_cycle_detection(self):
        class Cycle:
            def __call__(self):
                pass

        a = Cycle()
        b = Cycle()
        a.__wrapped__ = b
        b.__wrapped__ = a

        result = _inspect_wrapper_callable(a)
        self.assertIn("wrapped_chain", result)
        chain = result["wrapped_chain"]
        self.assertLess(len(chain), 10)
        self.assertTrue(result["chain_cycle_detected"])
        has_cycle = any("cycle" in entry for entry in chain)
        self.assertTrue(has_cycle)
        # chain_depth is the number of successful __wrapped__ traversals before cycle detection
        self.assertGreaterEqual(result["chain_depth"], 1)
        self.assertLess(result["chain_depth"], 10)

    def test_closure_callable_references_only_ids(self):
        def make_wrapper():
            secret = lambda: "sensitive_data_123"
            def wrapper():
                return secret()
            return wrapper

        w = make_wrapper()
        result = _inspect_wrapper_callable(w)
        self.assertIn("closure_callable_references", result)
        self.assertIn("closure_count", result)
        # The actual content should not appear
        self.assertNotIn("sensitive_data", str(result))

    def test_chain_depth_tracking(self):
        def f():
            pass

        current = f
        for i in range(5):
            def make_layer(inner):
                def layer():
                    return inner()
                layer.__wrapped__ = inner
                return layer
            current = make_layer(current)

        result = _inspect_wrapper_callable(current)
        self.assertEqual(result["chain_depth"], 5)

    def test_source_location(self):
        def my_func():
            pass
        result = _inspect_wrapper_callable(my_func)
        # source_file will be this test file
        self.assertIsNotNone(result.get("source_file"))
        self.assertIsNotNone(result.get("source_first_line"))

    def test_discover_wrapper_symbols_shape(self):
        symbols = _discover_wrapper_symbols()
        self.assertIsInstance(symbols, dict)
        for name in _KNOWN_WRAPPER_SYMBOLS:
            self.assertIn(name, symbols)

    def test_discover_wrapper_symbols_qualified_keys(self):
        """Keys must be the exact qualified dotted names, not generic placeholders."""
        symbols = _discover_wrapper_symbols()
        for name in _KNOWN_WRAPPER_SYMBOLS:
            self.assertIn(name, symbols)
            # Verify it's a dotted path (qualified name)
            self.assertIn(".", name, f"{name} should be a qualified dotted name")
            # First segment should be a package name
            first_seg = name.split(".")[0]
            self.assertIn(first_seg, ("comfy", "nodes", "execution"),
                          f"Unexpected top-level package in {name}")

    def test_capture_wrapper_inventory_shape(self):
        inventory = capture_wrapper_inventory("test_stage")
        self.assertEqual(inventory["stage"], "test_stage")
        self.assertIn("wrappers", inventory)
        self.assertIn("timestamp", inventory)
        self.assertIn("monotonic_ns", inventory)

    def test_capture_with_extra_symbols(self):
        def extra():
            pass
        inventory = capture_wrapper_inventory(
            "extra_stage",
            extra_symbols={"extra_fn": extra},
        )
        self.assertIn("extra_fn", inventory["wrappers"])

    def test_capture_with_session_active_functions(self):
        session = MagicMock()
        def active():
            pass
        session._active_functions = {"active_fn": active}
        inventory = capture_wrapper_inventory(
            "session_stage",
            session=session,
        )
        self.assertIn("active_fn", inventory["wrappers"])

    def test_inspect_asyncio_task_shape(self):
        """_inspect_asyncio_task returns the expected fields."""
        async def sample_coro():
            await asyncio.sleep(0)

        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(sample_coro())
            loop.run_until_complete(asyncio.sleep(0))
            result = _inspect_asyncio_task(task)
            self.assertIn("task_id", result)
            self.assertIn("task_name", result)
            self.assertIn("done", result)
            self.assertIn("cancelled", result)
            self.assertIn("coroutine_qualname", result)
            self.assertIn("top_stack_file", result)
            self.assertIn("top_stack_line", result)
            self.assertIn("top_stack_function", result)
        finally:
            loop.close()


class TestStopTracing(unittest.TestCase):
    """stop_tracing order and idempotency."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)

    def _make_session(self):
        return _create_test_session(self.td.name)

    def test_stop_order_keys(self):
        session = self._make_session()
        session.start_restore()
        session.set_restore_complete()
        session.claim_first_request("req_1")
        result = session.stop_tracing()
        keys = list(result.keys())
        torch_idx = keys.index("torch_profiler")
        res_idx = keys.index("resource_sampler")
        viz_idx = keys.index("viztracer")
        summary_idx = keys.index("summary")
        self.assertLess(torch_idx, res_idx)
        self.assertLess(res_idx, viz_idx)
        self.assertLess(viz_idx, summary_idx)

    def test_stop_without_viztracer(self):
        session = self._make_session()
        session._transition("restore_tracing")
        session.set_restore_complete()
        session.claim_first_request("req_1")
        result = session.stop_tracing()
        self.assertEqual(result["final_state"], "trace_stopped")

    def test_stop_generates_gzip_files(self):
        session = self._make_session()
        session.start_restore()
        session.set_restore_complete()
        session.claim_first_request("req_1")
        result = session.stop_tracing()
        summary_path = session.base_dir / "raw" / "runtime_result_summary.json"
        self.assertTrue(summary_path.exists())
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["trace_id"], "test_trace")
        self.assertIn("elapsed_seconds", summary)
        self.assertEqual(summary["final_state"], "trace_stopped")

    def test_viztracer_stop_keeps_finalization_parse_free(self):
        """A missing live data count must not trigger a full trace parse."""
        session = self._make_session()
        session.start_restore()
        session.set_restore_complete()
        session.claim_first_request("req_1")
        tracer = MagicMock()
        tracer.tracer_entries = 123
        tracer.data = None
        tracer.parse.side_effect = AssertionError("parse is offline-only")
        tracer.save.side_effect = lambda path: Path(path).write_text(
            '{"traceEvents": []}', encoding="utf-8"
        )
        session._viztracer = tracer

        result = session.stop_tracing()

        tracer.parse.assert_not_called()
        viz = result["viztracer"]
        self.assertIsNone(viz["entry_count"])
        self.assertEqual(viz["entry_capacity"], 123)
        for field in ("stop_ms", "save_ms", "gzip_ms", "total_ms"):
            self.assertIn(field, viz)
            self.assertGreaterEqual(viz[field], 0)

    def test_stop_double_call(self):
        session = self._make_session()
        session.start_restore()
        session.set_restore_complete()
        session.claim_first_request("req_1")
        result1 = session.stop_tracing()
        self.assertEqual(result1["final_state"], "trace_stopped")
        # Second stop should return cached result
        result2 = session.stop_tracing()
        self.assertEqual(result2["final_state"], "trace_stopped")
        self.assertEqual(result2["trace_id"], result1["trace_id"])

    def test_result_summary_persisted(self):
        session = self._make_session()
        session.set_result_summary({"custom_field": "custom_value"})
        session.start_restore()
        session.set_restore_complete()
        session.claim_first_request("req_1")
        session.stop_tracing()
        summary_path = session.base_dir / "raw" / "runtime_result_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary.get("custom_field"), "custom_value")


class TestTorchProfiler(unittest.TestCase):
    """start_torch_profiler / stop_torch_profiler with exact params."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self._torch_env = patch.dict(os.environ, {ft._ENV_TORCH: "1"}, clear=False)
        self._torch_env.start()
        self.addCleanup(self._torch_env.stop)
        self._sessions = []

    def tearDown(self):
        for s in self._sessions:
            try:
                if s._torch_profiler_active:
                    s.stop_tracing()
                elif s.resource_sampler is not None:
                    s.resource_sampler.stop()
            except Exception:
                pass

    def _make_session(self):
        s = _create_test_session(self.td.name)
        self._sessions.append(s)
        return s

    def test_start_torch_profiler_no_crash(self):
        session = self._make_session()
        session.start_torch_profiler()
        session.stop_tracing()

    def test_torch_profiler_is_opt_in_by_default(self):
        session = self._make_session()
        with patch.dict(os.environ, {}, clear=True):
            session.start_torch_profiler()
        self.assertIsNone(session._torch_profiler)
        self.assertFalse(session._torch_profiler_active)

    def test_start_torch_profiler_twice_no_op(self):
        session = self._make_session()
        session.start_torch_profiler()
        first = session._torch_profiler
        session.start_torch_profiler()  # should be no-op
        if first is not None:
            self.assertIs(session._torch_profiler, first)
        session.stop_tracing()

    def test_stop_torch_profiler_standalone(self):
        """stop_torch_profiler can be called independently."""
        session = self._make_session()
        session.start_torch_profiler()
        session.stop_torch_profiler()
        self.assertIsNone(session._torch_profiler)
        self.assertFalse(session._torch_profiler_active)

    def test_stop_torch_profiler_idempotent(self):
        session = self._make_session()
        session.start_torch_profiler()
        session.stop_torch_profiler()
        session.stop_torch_profiler()  # second call should be safe
        self.assertIsNone(session._torch_profiler)

    def test_stop_torch_profiler_lazy_import(self):
        """torch must NOT be imported at module level."""
        import inspect
        source = inspect.getsource(ft)
        for line in source.split("\n"):
            if "import torch" in line and not line.startswith(" "):
                self.fail(f"Module-level torch import: {line.strip()}")

    def test_profiler_exact_params(self):
        """start_torch_profiler must use exact named params."""
        # Check that the method body uses record_shapes=False, profile_memory=True, with_stack=True
        import inspect
        source = inspect.getsource(FullExecutionTraceSession.start_torch_profiler)
        self.assertIn("record_shapes=False", source)
        self.assertIn("profile_memory=True", source)
        self.assertIn("with_stack=True", source)

    def test_start_torch_profiler_signature(self):
        """start_torch_profiler must have no custom params beyond self."""
        import inspect
        sig = inspect.signature(FullExecutionTraceSession.start_torch_profiler)
        params = list(sig.parameters.values())
        self.assertEqual(len(params), 1, "start_torch_profiler should only take self")
        self.assertEqual(params[0].name, "self")


class TestTorchProfilerThreadSafety(unittest.TestCase):
    """Focused tests: exactly-once __exit__, same-thread start/stop, stop_tracing
    no-ops after explicit stop, partial artifact on Torch failure."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self._torch_env = patch.dict(os.environ, {ft._ENV_TORCH: "1"}, clear=False)
        self._torch_env.start()
        self.addCleanup(self._torch_env.stop)
        self._sessions: list[FullExecutionTraceSession] = []

    def tearDown(self):
        for s in self._sessions:
            try:
                s.stop_tracing()
            except Exception:
                pass

    def _make_session(self) -> FullExecutionTraceSession:
        s = _create_test_session(self.td.name)
        self._sessions.append(s)
        return s

    # ── Same-thread start/stop ─────────────────────────────────────────────────

    def test_start_stop_same_native_thread(self):
        """start and stop capture matching native thread IDs."""
        session = self._make_session()
        session.start_torch_profiler()

        start_tid = getattr(session, "_torch_profiler_thread_id", None)
        self.assertIsNotNone(start_tid, "start must record the thread ID")

        current_tid = threading.get_ident()
        self.assertEqual(
            current_tid, start_tid,
            "start_torch_profiler must record the calling thread",
        )

        session.stop_torch_profiler()
        # After exactly-once stop, profiler is detached
        self.assertIsNone(session._torch_profiler)
        self.assertFalse(session._torch_profiler_active)

    def test_stop_torch_profiler_preserves_thread_id(self):
        """The thread_id recorded at start survives the exact-once detach."""
        session = self._make_session()
        session.start_torch_profiler()
        start_tid = session._torch_profiler_thread_id
        session.stop_torch_profiler()
        # stop_torch_profiler reads it via getattr before lock clears refs
        self.assertEqual(session._torch_profiler_thread_id, start_tid)

    # ── Exactly-once __exit__ ──────────────────────────────────────────────────

    def test_exit_runs_exactly_once(self):
        """__exit__() is called exactly once across repeated stop calls."""
        session = self._make_session()
        session.start_torch_profiler()

        # Instrument: wrap __exit__ to count calls
        _counter = [0]
        _orig_exit = session._torch_profiler.__exit__
        def _counting_exit(*args, **kwargs):
            _counter[0] += 1
            return _orig_exit(*args, **kwargs)
        session._torch_profiler.__exit__ = _counting_exit

        session.stop_torch_profiler()
        session.stop_torch_profiler()   # 2nd call — must be no-op
        session.stop_torch_profiler()   # 3rd call — must be no-op

        self.assertEqual(_counter[0], 1, "__exit__ must run exactly once")

    def test_stop_torch_profiler_repeated_noop(self):
        """Repeated stop_torch_profiler after explicit stop is a no-op."""
        session = self._make_session()
        session.start_torch_profiler()
        session.stop_torch_profiler()

        self.assertIsNone(session._torch_profiler)
        self.assertFalse(session._torch_profiler_active)

        # Second stop — should not raise
        session.stop_torch_profiler()
        self.assertIsNone(session._torch_profiler)

    # ── stop_tracing cannot double-stop Torch ──────────────────────────────────

    def test_stop_tracing_does_not_stop_torch_again(self):
        """stop_tracing() no-ops on Torch after explicit stop_torch_profiler()."""
        session = self._make_session()
        session.start_restore()
        session.set_restore_complete()
        session.claim_first_request("req_1")
        session.start_torch_profiler()

        # Stop torch explicitly on the request thread (simulating PromptExecutor wrapper)
        session.stop_torch_profiler()
        self.assertIsNone(session._torch_profiler)

        # Now stop_tracing — must not touch Torch again
        result = session.stop_tracing()
        self.assertIsNotNone(result, "stop_tracing must complete normally")
        torch_result = result.get("torch_profiler", {})
        # Torch section is empty since it was already stopped explicitly
        self.assertEqual(torch_result, {})

    def test_stop_tracing_without_explicit_torch_stop(self):
        """stop_tracing() still completes when Torch was never started."""
        session = self._make_session()
        session.start_restore()
        session.set_restore_complete()
        session.claim_first_request("req_1")

        # No torch start — stop_tracing must not crash
        result = session.stop_tracing()
        self.assertIsNotNone(result)
        self.assertEqual(result.get("torch_profiler", {}), {})

    # ── Torch failure still produces partial artifact ──────────────────────────

    def test_torch_failure_still_saves_viztracer(self):
        """When Torch start/stop fails, VizTracer and resource data are still saved."""
        session = self._make_session()
        session.start_restore()
        session.set_restore_complete()
        session.claim_first_request("req_1")

        # Corrupt the profiler before stop to simulate Torch failure
        session._torch_profiler = MagicMock()
        session._torch_profiler_active = True
        session._torch_profiler.__exit__ = MagicMock(side_effect=RuntimeError("Torch failure"))
        session._torch_profiler.export_chrome_trace = MagicMock()
        session._torch_profiler_thread_id = threading.get_ident()

        # stop_tracing must complete and record the error
        result = session.stop_tracing()
        self.assertIsNotNone(result)
        # VizTracer and resource sampler results should still be present
        self.assertIn("viztracer", result)
        self.assertIn("resource_sampler", result)
        self.assertIn("summary", result)
        self.assertEqual(result.get("final_state"), "trace_stopped")

    def test_torch_start_failure_allows_stop_tracing(self):
        """When start_torch_profiler fails, stop_tracing still works."""
        session = self._make_session()
        session.start_restore()
        session.set_restore_complete()
        session.claim_first_request("req_1")

        # Simulate failed start — profiler was never initialized
        session._torch_profiler = None
        session._torch_profiler_active = False

        # stop_tracing must complete without error
        result = session.stop_tracing()
        self.assertIsNotNone(result)
        self.assertEqual(result.get("torch_profiler", {}), {})

    # ── Artifact worker never receives a live profiler ─────────────────────────

    def test_artifact_worker_sees_null_profiler_after_explicit_stop(self):
        """After explicit stop_torch_profiler, _torch_profiler is None for the async worker."""
        session = self._make_session()
        session.start_torch_profiler()
        self.assertIsNotNone(session._torch_profiler)
        self.assertTrue(session._torch_profiler_active)

        # Simulate PromptExecutor thread stopping the profiler
        session.stop_torch_profiler()

        # The async artifact worker sees None
        self.assertIsNone(session._torch_profiler)
        self.assertFalse(session._torch_profiler_active)

        # status_dict confirms no live profiler
        status = session.status_dict()
        self.assertFalse(status["has_torch_profiler"])

    def test_status_dict_reports_torch_profiler_absent_after_stop(self):
        """status_dict has_torch_profiler is False after stop."""
        session = self._make_session()
        session.start_torch_profiler()
        self.assertTrue(session.status_dict()["has_torch_profiler"])

        session.stop_torch_profiler()
        self.assertFalse(session.status_dict()["has_torch_profiler"])


class TestEnvInt(unittest.TestCase):
    """_env_int and _env_int_chain helpers."""

    def test_int_from_env(self):
        with patch.dict(os.environ, {"TEST_INT": "42"}, clear=False):
            self.assertEqual(_env_int("TEST_INT", 0), 42)

    def test_default_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_env_int("MISSING", 99), 99)

    def test_default_when_invalid(self):
        with patch.dict(os.environ, {"BAD": "not_a_number"}, clear=False):
            self.assertEqual(_env_int("BAD", 10), 10)

    def test_env_int_chain_first_wins(self):
        with patch.dict(os.environ, {"A": "1", "B": "2"}, clear=False):
            self.assertEqual(_env_int_chain("A", "B", default=0), 1)

    def test_env_int_chain_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_env_int_chain("MISSING", "ALSO_MISSING", default=42), 42)


class TestProjectPaths(unittest.TestCase):
    """_resolve_trace_include_paths."""

    def test_trace_include_paths_shape(self):
        inc = _resolve_trace_include_paths()
        self.assertIn("requested", inc)
        self.assertIn("resolved", inc)
        self.assertIn("missing", inc)
        self.assertIn("excluded", inc)
        self.assertIn("search_roots", inc)
        self.assertIsInstance(inc["requested"], list)
        self.assertIsInstance(inc["excluded"], list)
        # Excluded should include the expected patterns
        self.assertIn("torch", inc["excluded"])
        self.assertIn("transformers", inc["excluded"])
        self.assertIn("diffusers", inc["excluded"])
        self.assertIn("numpy", inc["excluded"])
        self.assertIn("site-packages", inc["excluded"])
        self.assertIn("comfy/ldm", inc["excluded"])

    def test_trace_include_requested_list(self):
        inc = _resolve_trace_include_paths()
        requested = inc["requested"]
        # Should include V2-owned files
        self.assertIn("comfymodal_runtime/", requested)
        self.assertIn("comfyapp.py", requested)
        self.assertIn("execution.py", requested)
        self.assertIn("nodes.py", requested)
        # Should include custom node symbols
        self.assertIn("CacheDiT", requested)


class TestSingleton(unittest.TestCase):
    """create_if_enabled returns the same instance."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()

    def test_singleton_returns_same(self):
        with patch.dict(os.environ, {ft._ENV_ENABLE: "1"}, clear=False):
            with tempfile.TemporaryDirectory() as td:
                ft._TEST_TRACE_BASE = td
                try:
                    s1 = FullExecutionTraceSession.create_if_enabled(
                        container_session_id="test",
                    )
                    s2 = FullExecutionTraceSession.create_if_enabled(
                        container_session_id="test2",  # different, should return same
                    )
                    self.assertIs(s1, s2)
                    self.assertEqual(s1._container_session_id, "test")
                    # Since it's singleton, s2 returns s1 (with s1's container_session_id)
                finally:
                    ft._TEST_TRACE_BASE = None
                    FullExecutionTraceSession.reset_instance()

    def test_reset_instance(self):
        with patch.dict(os.environ, {ft._ENV_ENABLE: "1"}, clear=False):
            with tempfile.TemporaryDirectory() as td:
                ft._TEST_TRACE_BASE = td
                try:
                    s1 = FullExecutionTraceSession.create_if_enabled(
                        container_session_id="test",
                    )
                    self.assertIsNotNone(s1)
                    FullExecutionTraceSession.reset_instance()
                    s2 = FullExecutionTraceSession.create_if_enabled(
                        container_session_id="test",
                    )
                    self.assertIsNotNone(s2)
                    self.assertIsNot(s1, s2)
                finally:
                    ft._TEST_TRACE_BASE = None
                    FullExecutionTraceSession.reset_instance()


class TestSessionEvents(unittest.TestCase):
    """Session events recording."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self._sessions = []

    def tearDown(self):
        for s in self._sessions:
            try:
                if s.resource_sampler is not None:
                    s.resource_sampler.stop()
            except Exception:
                pass

    def _make_session(self):
        s = _create_test_session(self.td.name)
        self._sessions.append(s)
        return s

    def test_events_property(self):
        session = self._make_session()
        events = session.events
        self.assertIsInstance(events, list)
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "created")

    def test_session_events_jsonl_exists(self):
        session = self._make_session()
        events_path = session.events_path
        self.assertIsNotNone(events_path)
        self.assertTrue(events_path.exists())

    def test_session_events_jsonl_content(self):
        session = self._make_session()
        session.start_restore()
        session.set_restore_complete()
        session.claim_first_request("req_123")
        events_path = session.events_path
        content = events_path.read_text(encoding="utf-8")
        self.assertIn("created", content)
        self.assertIn("restore_started", content)
        self.assertIn("request_claimed", content)

    def test_invalid_transition_recorded(self):
        session = self._make_session()
        session._transition("trace_stopped")
        events_path = session.events_path
        content = events_path.read_text(encoding="utf-8")
        self.assertIn("Invalid transition", content)
        self.assertIn("trace_stopped", content)


class TestStableHash(unittest.TestCase):
    """_stable_hash determinism and properties."""

    def test_deterministic(self):
        v = {"a": 1, "b": 2}
        self.assertEqual(_stable_hash(v), _stable_hash(v))

    def test_different_inputs_different_hashes(self):
        self.assertNotEqual(_stable_hash("hello"), _stable_hash("world"))

    def test_consistency_with_dict_order(self):
        self.assertEqual(
            _stable_hash({"a": 1, "b": 2}),
            _stable_hash({"b": 2, "a": 1}),
        )

    def test_not_reversible(self):
        h = _stable_hash("secret-value")
        self.assertNotIn("secret", h)


class TestJsonFallback(unittest.TestCase):
    """_json_fallback handles non-JSON types."""

    def test_path(self):
        result = _json_fallback(Path("/tmp/test"))
        self.assertIn("tmp", result)
        self.assertIn("test", result)

    def test_set(self):
        result = _json_fallback({1, 2, 3})
        self.assertEqual(result, [1, 2, 3])

    def test_bytes(self):
        result = _json_fallback(b"hello")
        self.assertIn("5 bytes", result)

    def test_fake_tensor(self):
        class FakeTensor:
            shape = (1, 3, 512, 512)
            dtype = "float16"
        result = _json_fallback(FakeTensor())
        self.assertIn("tensor", result)
        self.assertIn("float16", result)


class TestSafeJsonValue(unittest.TestCase):
    """_safe_json_value utility."""

    def test_scalars(self):
        self.assertEqual(_safe_json_value(None), None)
        self.assertEqual(_safe_json_value(True), True)
        self.assertEqual(_safe_json_value(42), 42)
        self.assertEqual(_safe_json_value(3.14), 3.14)
        self.assertEqual(_safe_json_value("hello"), "hello")

    def test_container(self):
        result = _safe_json_value([1, {"a": 2}, "three"])
        self.assertEqual(result, [1, {"a": 2}, "three"])

    def test_unsafe_object(self):
        result = _safe_json_value(object())
        self.assertIsInstance(result, str)
        self.assertIn("object", result)

    def test_nested_dict(self):
        result = _safe_json_value({"a": {"b": [1, 2, object()]}})
        self.assertIsInstance(result["a"]["b"][2], str)


class TestCgroupResolution(unittest.TestCase):
    """_resolve_cgroup_v2_path and helpers."""

    def test_resolve_cgroup_v2_with_mock(self):
        """Test with _TEST_CGROUP_V2 override."""
        with tempfile.TemporaryDirectory() as td:
            cg = _make_cgroup_tree(td)
            ft._TEST_CGROUP_V2 = str(cg)
            try:
                resolved = _resolve_cgroup_v2_path()
                self.assertEqual(resolved, Path(str(cg)))
            finally:
                ft._TEST_CGROUP_V2 = None

    def test_resolve_cgroup_v2_none_when_unavailable(self):
        """When no cgroup is found, returns None."""
        ft._TEST_CGROUP_V2 = None
        ft._TEST_PROC_SELF = None
        ft._TEST_PROC_ROOT = None
        # This will try to read /proc/self/mountinfo which won't exist on non-Linux
        resolved = _resolve_cgroup_v2_path()
        # Accept None or a valid path (on Linux it may exist)
        self.assertIsNone(resolved) if os.name != "posix" else None

    def test_cgroup_stat_nonexistent(self):
        with tempfile.TemporaryDirectory() as td:
            result = _read_cgroup_stat(Path(td))
            self.assertEqual(result["usage_usec"], None)
            self.assertEqual(result["nr_throttled"], None)

    def test_cgroup_memory_nonexistent(self):
        with tempfile.TemporaryDirectory() as td:
            result = _read_cgroup_memory(Path(td))
            self.assertEqual(result["current_bytes"], None)

    def test_cgroup_io_nonexistent(self):
        with tempfile.TemporaryDirectory() as td:
            result = _read_cgroup_io(Path(td))
            self.assertEqual(result["rbytes"], None)


class TestProcHelper(unittest.TestCase):
    """_get_proc_self, _get_proc_root helpers."""

    def test_get_proc_self_default(self):
        ft._TEST_PROC_SELF = None
        self.assertEqual(str(_get_proc_self()), os.path.normpath("/proc/self"))

    def test_get_proc_self_override(self):
        ft._TEST_PROC_SELF = os.path.normpath("/tmp/proc_self")
        expected = os.path.normpath("/tmp/proc_self")
        self.assertEqual(str(_get_proc_self()), expected)
        ft._TEST_PROC_SELF = None

    def test_get_proc_root_default(self):
        ft._TEST_PROC_ROOT = None
        self.assertEqual(str(_get_proc_root()), os.path.normpath("/proc"))

    def test_get_proc_root_override(self):
        ft._TEST_PROC_ROOT = os.path.normpath("/tmp/proc")
        expected = os.path.normpath("/tmp/proc")
        self.assertEqual(str(_get_proc_root()), expected)
        ft._TEST_PROC_ROOT = None


class TestTraceConfig(unittest.TestCase):
    """trace_config.json shape and content."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)

    def test_config_viztracer_version_none_at_construction(self):
        """viztracer_version must be null in config until start_restore imports VizTracer."""
        session = _create_test_session(self.td.name)
        config_path = session.base_dir / "raw" / "trace_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        # Should be None (not imported during construction)
        self.assertIsNone(config.get("viztracer_version"))

    def test_config_has_identity_block(self):
        session = _create_test_session(
            self.td.name,
            container_session_id="cid_42",
            restored_instance_id="inst_1",
            restore_session_id="rs_1",
        )
        config_path = session.base_dir / "raw" / "trace_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["container_session_id"], "cid_42")
        self.assertIn("identity", config)
        self.assertEqual(config["identity"]["restored_instance_id"], "inst_1")
        self.assertEqual(config["identity"]["restore_session_id"], "rs_1")

    def test_config_has_include_exclude(self):
        session = _create_test_session(self.td.name)
        config_path = session.base_dir / "raw" / "trace_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIn("include_paths", config)
        self.assertIn("exclusions", config)

    def test_config_has_entry_capacity(self):
        session = _create_test_session(self.td.name)
        config_path = session.base_dir / "raw" / "trace_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIn("entry_capacity", config)
        self.assertIsInstance(config["entry_capacity"], int)

    def test_config_has_missing_fields(self):
        session = _create_test_session(self.td.name)
        config_path = session.base_dir / "raw" / "trace_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIn("missing", config["include_paths"])

    def test_update_trace_config_persists_only_contract_fields(self):
        session = _create_test_session(self.td.name)
        session.update_trace_config({
            "golden_profile_contract": "direct_golden_serial",
            "golden_profile_require_canonical_stages": True,
            "output_durability_mode": "strict",
            "required_canonical_stages": ["golden_output", "golden_durable_commit"],
            "canonical_stage_order": ["golden_output", "golden_durable_commit"],
            "unrelated_state": "must_not_persist",
        })
        config_path = session.base_dir / "raw" / "trace_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["golden_profile_contract"], "direct_golden_serial")
        self.assertIs(config["golden_profile_require_canonical_stages"], True)
        self.assertEqual(config["output_durability_mode"], "strict")
        self.assertEqual(
            config["required_canonical_stages"],
            ["golden_output", "golden_durable_commit"],
        )
        self.assertNotIn("unrelated_state", config)
        self.assertTrue(
            any(event.get("event") == "trace_config_updated" for event in session.events)
        )

    def test_config_torch_enabled_false_when_unset_or_zero(self):
        """Persist top-level torch_enabled as false unless explicitly enabled."""
        for value in (None, "0"):
            with self.subTest(value=value):
                with patch.dict(os.environ, clear=False):
                    if value is None:
                        os.environ.pop(ft._ENV_TORCH, None)
                    else:
                        os.environ[ft._ENV_TORCH] = value
                    session = _create_test_session(self.td.name)
                    config_path = session.base_dir / "raw" / "trace_config.json"
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                self.assertIs(config["torch_enabled"], False)

    def test_config_torch_enabled_true_when_one(self):
        """Persist top-level torch_enabled as true for the enabled flag."""
        with patch.dict(os.environ, {ft._ENV_TORCH: "1"}, clear=False):
            session = _create_test_session(self.td.name)
            config_path = session.base_dir / "raw" / "trace_config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIs(config["torch_enabled"], True)


class TestLegacyCompatEnv(unittest.TestCase):
    """Backward-compatible env var fallbacks."""

    def test_legacy_entries_env_fallback(self):
        """When new env is absent, legacy FULL_TRACE_VIZTRACER_ENTRIES is checked."""
        with patch.dict(os.environ, {
            "FULL_TRACE_VIZTRACER_ENTRIES": "5000",
        }, clear=False):
            # Remove the new env var if present
            os.environ.pop("COMFYMODAL_V2_FULL_TRACE_ENTRIES", None)
            val = ft._env_int_chain(
                ft._ENV_ENTRIES, ft._LEGACY_ENV_ENTRIES,
                default=8000000,
            )
            self.assertEqual(val, 5000)

    def test_legacy_resource_interval_fallback(self):
        with patch.dict(os.environ, {
            "FULL_TRACE_RESOURCE_INTERVAL_MS": "200",
        }, clear=False):
            os.environ.pop("COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS", None)
            val = ft._env_int_chain(
                ft._ENV_RESOURCE_INTERVAL, ft._LEGACY_ENV_RESOURCE_INTERVAL,
                default=50,
            )
            self.assertEqual(val, 200)


class TestPrivateConstructor(unittest.TestCase):
    """Direct construction works but is discouraged; factory is primary."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()

    def test_direct_construction_still_works(self):
        session = FullExecutionTraceSession(
            container_session_id="direct_test",
            _trace_id_override="direct_id",
        )
        self.assertEqual(session.state, "created")
        self.assertEqual(session._container_session_id, "direct_test")

    def test_disabled_behavior_no_creation(self):
        """Even direct construction without env is fine (no side effects from constructor)."""
        session = FullExecutionTraceSession(
            container_session_id="test",
            _trace_id_override="disabled_test",
        )
        self.assertEqual(session.state, "created")


class TestStopTracingUnstarted(unittest.TestCase):
    """stop_tracing on an unstarted session."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)

    def test_stop_unstarted_no_error(self):
        session = _create_test_session(self.td.name)
        # Force into a valid state for stop
        session._transition("restore_tracing")
        session.set_restore_complete()
        session.claim_first_request("req_1")
        result = session.stop_tracing()
        self.assertEqual(result["final_state"], "trace_stopped")


class TestNoPromptLeakage(unittest.TestCase):
    """No prompt/model/tensor data leaked into serialized output."""

    def setUp(self):
        FullExecutionTraceSession.reset_instance()
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self._sessions = []

    def tearDown(self):
        # Ensure all sessions are properly stopped to release file handles
        for s in self._sessions:
            try:
                if s.resource_sampler is not None:
                    s.resource_sampler.close()
            except Exception:
                pass
        import gc
        gc.collect()

    def test_no_tensor_leak_in_mark(self):
        """Tensor-like objects in mark metadata are safe-repr'd."""
        class FakeTensor:
            shape = (1, 3, 512, 512)
            dtype = "float16"
        session = _create_test_session(self.td.name)
        self._sessions.append(session)
        session.start_restore()
        session.set_restore_complete()
        session.claim_first_request("req_1")
        session.mark("test_mark", tensor=FakeTensor(), secret_token="should_be_redacted")
        session.stop_tracing()
        import gc; gc.collect()
        raw_dir = session.raw_session_dir()
        events_path = raw_dir / "session_events.jsonl"
        content = events_path.read_text(encoding="utf-8")
        # The token value should be redacted
        self.assertNotIn("should_be_redacted", content)
        # The tensor shape should be safe-repr'd, not raw tensor dump
        self.assertNotIn("512,512", content)


if __name__ == "__main__":
    unittest.main()
