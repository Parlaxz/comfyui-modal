"""FAST_UNIT: C0 child program is spawnable independently of its size."""

from __future__ import annotations

import ast
import hashlib
import json
import multiprocessing as mp
import os
import py_compile
import struct
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
from typing import Any, cast

import pytest

from comfymodal_runtime import golden_io_process_v2 as c0


pytestmark = pytest.mark.fast_unit


def test_child_source_materializes_to_compilable_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    path = c0.write_c0_child_source_file(c0._C0_CHILD_SOURCE)

    assert path.endswith(".py")
    assert open(path, "rb").read() == c0._C0_CHILD_SOURCE.encode("utf-8")
    py_compile.compile(path, doraise=True)


def test_child_source_file_is_content_hashed_and_reused(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    first = c0.write_c0_child_source_file("print('a')")
    second = c0.write_c0_child_source_file("print('a')")
    other = c0.write_c0_child_source_file("print('b')")

    assert first == second
    assert other != first
    assert open(other, "rb").read() == b"print('b')"


def test_child_program_exceeds_argv_spawn_but_file_spawn_has_no_argv():
    # Regression pin: the child program outgrew the kernel single-argument
    # limit (131072 bytes), which broke `python -c` spawn at restore.
    # File spawn carries only a short path in argv.
    size = len(c0._C0_CHILD_SOURCE.encode("utf-8"))
    assert size > 131072
    argv = ["python", "<child-file>", "shm-name", "1", "2", "3", "4"]
    assert max(len(part) for part in argv) < 4096
    assert os.path.basename(c0.__file__) == "golden_io_process_v2.py"


def test_c0_fd_identity_rejects_replaced_checkpoint(tmp_path):
    path = tmp_path / "checkpoint.safetensors"
    path.write_bytes(b"old")
    fd = os.open(path, os.O_RDONLY)
    try:
        stat = os.fstat(fd)
        identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        assert c0._fd_matches_identity(fd, identity)
        path.write_bytes(b"new-content")
        assert not c0._fd_matches_identity(fd, identity)
    finally:
        os.close(fd)


def test_m2_control_has_explicit_shutdown_ack_and_bounded_lifecycle():
    control = c0.C0M2Control(arena_epoch=1)
    try:
        assert control.lifecycle()["readers_expected"] == 4
        result = control.request_exit(timeout_s=0.001)
        assert result["timeout"] is True
        assert control.lifecycle()["command"] == control.COMMAND_EXIT
        assert "_shutdown_readers" in c0._C0_M2_CHILD_SOURCE
        assert '"command": "EXIT"' in c0._C0_M2_CHILD_SOURCE
        assert "process.terminate()" in c0._C0_M2_CHILD_SOURCE
    finally:
        control.close()


def test_m2_reader_error_and_timeout_cancel_all_peers():
    source = c0._C0_M2_CHILD_SOURCE
    assert "m2_reader_timeout" in source
    assert "m2_shutdown_requested" in source
    assert "failed.value = 1" in source
    assert "_shutdown_readers(error, failed_flag=1)" in source
    assert '_terminal("error"' in source
    assert "readers_reaped" in source


def test_m2_coordinator_detects_dead_reader_before_waiting_for_load_done():
    source = c0._C0_M2_CHILD_SOURCE

    assert "process.is_alive()" in source
    assert "process.exitcode" in source
    assert "m2_reader_died:reader_id=%d;pid=%s;exitcode=%s" in source
    assert source.index("process.is_alive()") < source.index("connection.poll(0.01)")
    assert "_shutdown_readers(error, failed_flag=1)" in source


def test_m2_coordinator_commits_final_evidence_before_terminal_markers():
    source = ast.parse(c0._C0_M2_CHILD_SOURCE)
    terminal = next(
        node for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name == "_terminal"
    )
    terminal_source = ast.get_source_segment(c0._C0_M2_CHILD_SOURCE, terminal)
    assert terminal_source is not None

    evidence_index = terminal_source.index("write_evidence(control_buf, payload)")
    state_index = terminal_source.index("write_state(control_buf")
    lifecycle_index = terminal_source.index("write_lifecycle(control_buf")
    assert evidence_index < state_index < lifecycle_index


def _embedded_reader_summary_namespace(platform_name):
    source = ast.parse(c0._C0_M2_CHILD_SOURCE)
    wanted = {"_read_reader_proc_text", "_reader_proc_diagnostics", "reader_summary"}
    functions = cast(list[ast.stmt], [
        node for node in source.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ])
    namespace = {
        "LANES": c0.C0M2Control.LANE_COUNT,
        "sys": SimpleNamespace(platform=platform_name),
        "time": c0.time,
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<m2-reader-summary>", "exec"), namespace)
    return namespace


def test_m2_reader_summary_proc_diagnostics_are_bounded_and_fail_open():
    namespace = _embedded_reader_summary_namespace(sys.platform)
    process = SimpleNamespace(pid=os.getpid(), is_alive=lambda: True, exitcode=None)

    row = namespace["reader_summary"]([process], stage="waiting_load_done")[0]

    assert row["stage"] == "waiting_load_done"
    assert isinstance(row["timestamp_ns"], int)
    assert row["procfs_supported"] is sys.platform.startswith("linux")
    assert row["stat_state"] is None or len(row["stat_state"]) == 1
    for key in ("wchan", "syscall"):
        assert row[key] is None or len(row[key]) <= 256
    assert len(json.dumps(row, separators=(",", ":"))) < 1024

    unsupported = _embedded_reader_summary_namespace("win32")
    unsupported_row = unsupported["reader_summary"]([process])[0]
    assert unsupported_row["procfs_supported"] is False
    assert unsupported_row["wchan"] is None
    assert unsupported_row["stat_state"] is None
    assert unsupported_row["syscall"] is None

    missing = namespace["reader_summary"](
        [SimpleNamespace(pid=0, is_alive=lambda: False, exitcode=1)]
    )[0]
    assert missing["wchan"] is None
    assert missing["stat_state"] is None
    assert missing["syscall"] is None


def test_m2_progress_snapshot_reports_bounded_ownership_and_adapter_shape():
    source = ast.parse(c0._C0_M2_CHILD_SOURCE)
    wanted = {"_adapter_stage_rows", "progress_snapshot"}
    functions = cast(list[ast.stmt], [
        node for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ])
    namespace = {
        "LANES": 4,
        "M2_READER_STAGE_UNAVAILABLE_REASON": "raw_connection_not_authoritative",
        "ownership": [0, 1, 2, 2, 1, 99],
        "completed": SimpleNamespace(value=3),
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<m2-progress>", "exec"), namespace)

    progress = namespace["progress_snapshot"](
        {"total_blocks": 5, "generation": 7},
        [{"reader": 0, "command_sent": True, "response_received": False}],
        stage="waiting_load_done",
    )

    assert progress["completed"] == 3
    assert progress["completed_value"] == 3
    assert progress["claimed_blocks"] == 2
    assert progress["owned_blocks"] == 2
    assert progress["ownership_counts"] == {"0": 1, "1": 2, "2": 2}
    assert progress["total_blocks"] == 5
    assert progress["current_generation"] == 7
    assert progress["adapter_stages"][0]["command_sent"] is True
    assert progress["adapter_stages"][0]["response_received"] is False
    assert progress["reader_stage_diagnostics"] == {
        "available": False,
        "authoritative": False,
        "reason": "raw_connection_not_authoritative",
    }
    assert progress["adapter_stages"][0]["reader_stage"] == "unavailable"
    assert progress["adapter_stages"][0]["reader_stage_authoritative"] is False
    assert progress["adapter_stages"][0]["load_received"] is None
    assert len(progress["adapter_stages"]) == 1


def test_m2_progress_source_records_send_poll_recv_stage_boundaries():
    source = c0._C0_M2_CHILD_SOURCE

    for marker in (
        '"completed_value"', '"ownership_counts"', '"total_blocks"',
        '"current_generation"', '"command_sent_ns"',
        '"response_poll_ready_ns"', '"response_received_ns"',
    ):
        assert marker in source
    assert "connection.send(request)" in source
    assert "connection.poll(0.01)" in source
    assert "connection.recv()" in source


def test_m2_aggregate_derives_child_clock_source_timing_and_phase_sums():
    source = ast.parse(c0._C0_M2_CHILD_SOURCE)
    aggregate = next(
        node for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name == "_aggregate_evidence"
    )
    namespace = {
        "hashlib": hashlib,
        "json": json,
        "_record_key": lambda record: (
            int(record.get("block_id", -1)),
            int(record.get("offset", -1)),
            int(record.get("length", 0)),
        ),
        "_contiguous_ranges": lambda values: [],
        "progress_snapshot": lambda *args, **kwargs: {},
        "reader_summary": lambda *args, **kwargs: [],
        "LANES": 4,
    }
    exec(compile(ast.Module(body=[aggregate], type_ignores=[]),
                 "<m2-aggregate>", "exec"), namespace)

    request = {
        "total_blocks": 2,
        "data_bytes": 12,
        "source_offset": 100,
        "read_bytes": 8,
        "lane_ranges": [(0, 1), (1, 2), (2, 2), (2, 2)],
    }
    result = namespace["_aggregate_evidence"](
        request,
        [{
            "reader": 0,
            "pid": 11,
            "records": [{
                "block_id": 0, "offset": 0, "length": 8,
                "enter_ns": 1_000, "exit_ns": 4_000,
                "map_ns": 10, "gate_wait_ns": 2, "unmap_ns": 3,
            }],
        }, {
            "reader": 1,
            "pid": 12,
            "records": [{
                "block_id": 1, "offset": 8, "length": 4,
                "enter_ns": 2_000, "exit_ns": 7_000,
                "map_ns": 20, "gate_wait_ns": 4, "unmap_ns": 5,
            }],
        }],
    )

    assert result["source_clock_domain"] == "child_perf_counter_ns"
    assert result["source_first_enter_ns"] == 1_000
    assert result["source_last_exit_ns"] == 7_000
    assert result["source_wall_ms"] == pytest.approx(0.006)
    assert result["map_ns_sum"] == 30
    assert result["map_count"] == 2
    assert result["memcpy_ns_sum"] == 8_000
    assert result["memcpy_count"] == 2
    assert result["munmap_ns_sum"] == 8
    assert result["gate_wait_ns_sum"] == 6
    assert result["records"][0]["records_digest_sha1"]
    assert result["records"][0]["source_clock_domain"] == "child_perf_counter_ns"


def test_m2_oversized_control_evidence_is_valid_json_with_truncation_warning():
    source = ast.parse(c0._C0_M2_CHILD_SOURCE)
    write_evidence = next(
        node for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name == "write_evidence"
    )
    namespace = {
        "json": json,
        "struct": struct,
        "LANES": 4,
        "EVIDENCE_BYTES": c0.C0M2Control.EVIDENCE_BYTES,
        "EVIDENCE_OFFSET": c0.C0M2Control.EVIDENCE_OFFSET,
        "EVIDENCE_LENGTH_OFFSET": c0.C0M2Control.EVIDENCE_LENGTH_OFFSET,
    }
    exec(compile(ast.Module(body=[write_evidence], type_ignores=[]),
                 "<m2-write-evidence>", "exec"), namespace)

    payload = {
        "status": "error",
        "error": "m2_reader_timeout",
        "m2_authority": {"module": "m2_source_core", "path": "x" * 400,
                          "expected_sha1": "a" * 40, "observed_sha1": "b" * 40},
        "cleanup": {"readers_expected": 4, "readers_reaped": 0,
                     "descendants_survived": list(range(100)), "reason": "y" * 400},
        "lifecycle": {"terminal_status": 2, "readers_expected": 4,
                       "readers_reaped": 0},
        "progress": {"stage": "reader_timeout", "total_blocks": 65536,
                      "adapter_stages": [{"reader": i, "trace": "z" * 1000}
                                          for i in range(4)]},
        "reader_aggregate": {
            "read_count": 100,
            "read_bytes": 1234,
            "records": [{"reader": i, "records": [{"blob": "q" * 1000}
                                                       for _ in range(100)]}
                         for i in range(4)],
            "reconciliation": {"actual_source_ranges": [[i, i + 1]
                                                            for i in range(1000)]},
        },
        "reader_summary": [{"reader": i, "syscall": "s" * 1000}
                            for i in range(4)],
    }
    buf = bytearray(c0.C0M2Control.SIZE_BYTES)
    namespace["write_evidence"](buf, payload)

    length = struct.unpack_from("<I", buf, c0.C0M2Control.EVIDENCE_LENGTH_OFFSET)[0]
    raw = bytes(buf[c0.C0M2Control.EVIDENCE_OFFSET:
                    c0.C0M2Control.EVIDENCE_OFFSET + length])
    evidence = json.loads(raw)

    assert length <= c0.C0M2Control.EVIDENCE_BYTES
    assert evidence["status"] == "error"
    assert evidence["error"] == "m2_reader_timeout"
    assert evidence["evidence_truncated"] is True
    assert "evidence_truncated" in evidence["evidence_truncation_warning"]
    assert "m2_authority" in evidence
    assert "cleanup" in evidence
    assert "lifecycle" in evidence
    assert "progress" in evidence
    assert "reader_aggregate" in evidence
    assert all("records" not in row for row in evidence["reader_aggregate"]["records"])


def test_m2_minimal_evidence_preserves_authority_identity_fields():
    source = ast.parse(c0._C0_M2_CHILD_SOURCE)
    write_evidence = next(
        node for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name == "write_evidence"
    )
    evidence_bytes = 1200
    namespace = {
        "json": json,
        "struct": struct,
        "LANES": 4,
        "EVIDENCE_BYTES": evidence_bytes,
        "EVIDENCE_OFFSET": c0.C0M2Control.EVIDENCE_OFFSET,
        "EVIDENCE_LENGTH_OFFSET": c0.C0M2Control.EVIDENCE_LENGTH_OFFSET,
    }
    exec(compile(ast.Module(body=[write_evidence], type_ignores=[]),
                 "<m2-write-evidence-minimal>", "exec"), namespace)

    payload = {
        "status": "authority_hash_mismatch",
        "error": "m2_source_core_authority_hash_mismatch",
        "m2_authority": {
            "module": "comfymodal_runtime.m2_source_core",
            "expected_sha1": "a" * 40,
            "observed_sha1": "b" * 40,
            "expected_path": "e" * 400,
            "observed_path": "o" * 400,
            "imported": False,
        },
        "reader_aggregate": {"records": [{"trace": "x" * 4000}] * 4},
        "reader_summary": [{"syscall": "y" * 4000} for _ in range(4)],
    }
    buf = bytearray(c0.C0M2Control.EVIDENCE_OFFSET + evidence_bytes)
    namespace["write_evidence"](
        buf, payload,
    )

    length = struct.unpack_from(
        "<I", buf, c0.C0M2Control.EVIDENCE_LENGTH_OFFSET,
    )[0]
    raw = bytes(buf[c0.C0M2Control.EVIDENCE_OFFSET:
                   c0.C0M2Control.EVIDENCE_OFFSET + length])
    evidence = json.loads(raw)

    assert length <= evidence_bytes
    assert evidence["evidence_truncated"] is True
    assert "evidence_truncated" in evidence["evidence_truncation_warning"]
    authority = evidence["m2_authority"]
    assert authority["expected_sha1"] == "a" * 40
    assert authority["observed_sha1"] == "b" * 40
    assert authority["expected_path"] == "e" * 256
    assert authority["observed_path"] == "o" * 256
    assert authority["imported"] is False


def test_m2_minimal_evidence_preserves_reader_aggregate_proof_summary():
    source = ast.parse(c0._C0_M2_CHILD_SOURCE)
    write_evidence = next(
        node for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name == "write_evidence"
    )
    evidence_bytes = 1200
    namespace = {
        "json": json,
        "struct": struct,
        "LANES": 4,
        "EVIDENCE_BYTES": evidence_bytes,
        "EVIDENCE_OFFSET": c0.C0M2Control.EVIDENCE_OFFSET,
        "EVIDENCE_LENGTH_OFFSET": c0.C0M2Control.EVIDENCE_LENGTH_OFFSET,
    }
    exec(compile(ast.Module(body=[write_evidence], type_ignores=[]),
                 "<m2-write-evidence-reader-aggregate>", "exec"), namespace)

    payload = {
        "status": "done",
        "error": None,
        "reader_aggregate": {
            "read_count": 4,
            "read_bytes": 256,
            "source_clock_domain": "child_perf_counter_ns",
            "source_first_enter_ns": 100,
            "source_last_exit_ns": 700,
            "source_wall_ms": 0.0006,
            "map_ns_sum": 10,
            "map_count": 4,
            "memcpy_ns_sum": 20,
            "memcpy_count": 4,
            "munmap_ns_sum": 30,
            "munmap_count": 4,
            "gate_wait_ns_sum": 40,
            "gate_wait_count": 4,
            "records": [
                {
                    "reader": reader,
                    "records_digest_sha1": chr(97 + reader) * 40,
                    "records": [{"source_range": [reader, reader + 1],
                                 "raw": "x" * 4000}],
                }
                for reader in range(4)
            ],
            "reconciliation": {
                "expected_block_count": 4,
                "expected_bytes": 256,
                "read_count": 4,
                "read_bytes": 256,
                "gap_count": 0,
                "duplicate_count": 0,
                "out_of_range_count": 0,
                "exact_source_ranges": True,
                "exact_once": True,
                "records_digest_sha1": "d" * 40,
                "expected_source_ranges": [[0, 256], [256, 512]],
                "actual_source_ranges": [[0, 1]] * 1000,
            },
        },
        "reader_summary": [{"syscall": "y" * 4000} for _ in range(4)],
    }
    buf = bytearray(c0.C0M2Control.EVIDENCE_OFFSET + evidence_bytes)
    namespace["write_evidence"](buf, payload)

    length = struct.unpack_from(
        "<I", buf, c0.C0M2Control.EVIDENCE_LENGTH_OFFSET,
    )[0]
    raw = bytes(buf[c0.C0M2Control.EVIDENCE_OFFSET:
                   c0.C0M2Control.EVIDENCE_OFFSET + length])
    evidence = json.loads(raw)

    assert length <= evidence_bytes
    assert evidence["evidence_truncated"] is True
    assert "evidence_truncated" in evidence["evidence_truncation_warning"]
    aggregate = evidence["reader_aggregate"]
    assert aggregate["read_count"] == 4
    assert aggregate["read_bytes"] == 256
    assert aggregate["source_clock_domain"] == "child_perf_counter_ns"
    assert aggregate["source_first_enter_ns"] == 100
    assert aggregate["source_last_exit_ns"] == 700
    assert aggregate["source_wall_ms"] == pytest.approx(0.0006)
    assert aggregate["source_phase_totals"] == [[10, 4], [20, 4], [30, 4], [40, 4]]
    assert aggregate["reconciliation"] == {
        "expected_block_count": 4,
        "expected_bytes": 256,
        "read_count": 4,
        "read_bytes": 256,
        "gap_count": 0,
        "duplicate_count": 0,
        "out_of_range_count": 0,
        "exact_source_ranges": True,
        "exact_once": True,
        "records_digest_sha1": "d" * 40,
        "expected_source_ranges": [[0, 256]],
    }
    assert aggregate["records"] == [
        {"reader": reader, "records_digest_sha1": chr(97 + reader) * 40}
        for reader in range(4)
    ]
    assert "actual_source_ranges" not in aggregate["reconciliation"]
    assert all("records" not in row for row in aggregate["records"])


def test_m2_reader_connection_adapter_records_bounded_stage_shape():
    source = ast.parse(c0._C0_M2_CHILD_SOURCE)
    wanted_constants = {
        "M2_DIAG_STAGE_STRIDE", "M2_DIAG_READY_SENT", "M2_DIAG_LOAD_RECEIVED",
        "M2_DIAG_PROCESSING", "M2_DIAG_LOAD_DONE_SENT", "M2_DIAG_ERROR_SENT",
        "M2_DIAG_STAGE_NAMES", "M2_DIAG_MAX_NS",
    }
    nodes = [
        node for node in source.body
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "M2DiagnosticConnection"
        ) or (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id in wanted_constants
                for target in node.targets
            )
        )
    ]
    namespace = {"time": c0.time}
    exec(compile(ast.Module(body=cast(list[ast.stmt], nodes), type_ignores=[]),
                 "<m2-adapter>", "exec"), namespace)

    class FakeConnection:
        def __init__(self):
            self.sent = []
            self.received = [{"command": "LOAD", "generation": 7}]
            self.closed = False

        def send(self, message):
            self.sent.append(message)

        def recv(self):
            return self.received.pop(0)

        def close(self):
            self.closed = True

    context = mp.get_context()
    stride = cast(int, namespace["M2_DIAG_STAGE_STRIDE"])
    adapter_type = cast(Any, namespace["M2DiagnosticConnection"])
    max_ns = cast(int, namespace["M2_DIAG_MAX_NS"])
    state = context.Array("q", [0] * (4 * stride), lock=False)
    connection = FakeConnection()
    adapter = adapter_type(connection, 0, state)
    adapter.send({"command": "READY"})
    assert adapter.recv()["command"] == "LOAD"
    adapter.send({"command": "LOAD_DONE", "status": "error"})
    adapter.close()

    row = {
        "stage_code": int(state[0]),
        "ready_sent_ns": int(state[1]),
        "load_received_ns": int(state[2]),
        "processing_ns": int(state[3]),
        "load_done_sent_ns": int(state[4]),
        "error_sent_ns": int(state[5]),
    }
    assert connection.sent[0]["command"] == "READY"
    assert connection.sent[1]["command"] == "LOAD_DONE"
    assert connection.closed is True
    assert row["stage_code"] == cast(int, namespace["M2_DIAG_ERROR_SENT"])
    assert all(
        timestamp == 0 or 0 < timestamp <= max_ns
        for timestamp in row.values()
    )
    assert row["ready_sent_ns"] <= row["load_received_ns"] <= row["processing_ns"]
    assert row["processing_ns"] <= row["error_sent_ns"]


def test_m2_reader_stage_diagnostics_operate_on_lock_free_state():
    source = ast.parse(c0._C0_M2_CHILD_SOURCE)
    wanted = {"reader_stage_snapshot", "reset_reader_stage_state"}
    functions = cast(list[ast.stmt], [
        node for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ])
    namespace = {
        "LANES": 4,
        "M2_DIAG_STAGE_STRIDE": 6,
        "M2_DIAG_MAX_NS": (1 << 63) - 1,
        "M2_DIAG_READY_SENT": 1,
        "M2_DIAG_STAGE_NAMES": {0: "starting", 1: "ready_sent"},
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]),
                 "<m2-stage-diagnostics>", "exec"), namespace)

    context = mp.get_context()
    state = context.Array("q", [0] * (4 * 6), lock=False)
    assert not hasattr(state, "get_lock")
    state[0:6] = [5, 17, 23, 29, 31, 37]

    before_reset = namespace["reader_stage_snapshot"](state)[0]
    assert before_reset["load_received"] is True
    assert before_reset["error_sent"] is True

    namespace["reset_reader_stage_state"](state)
    after_reset = namespace["reader_stage_snapshot"](state)[0]
    assert after_reset["stage"] == "ready_sent"
    assert after_reset["ready_sent_ns"] == 17
    assert after_reset["load_received"] is False
    assert after_reset["error_sent"] is False


def test_m2_heartbeat_adapter_shape_contains_reader_stages_and_timestamps():
    source = c0._C0_M2_CHILD_SOURCE
    for marker in (
        "M2DiagnosticConnection",
        "reader_stage_state",
        '"ready_sent_ns"',
        '"load_received_ns"',
        '"processing_ns"',
        '"load_done_sent_ns"',
        '"error_sent_ns"',
        "reader_stage_state=reader_stage_state",
    ):
        assert marker in source
    assert "target=m2_source_core.persistent_reader_main" in source
    assert "args=(reader_id, child_conn" in source
    assert "diagnostic_conn = M2DiagnosticConnection" not in source


def test_m2_pacer_value_has_lock_for_persistent_reader_contract():
    source = c0._C0_M2_CHILD_SOURCE

    assert 'last_start = ctx.Value("q", 0, lock=True)' in source
    assert 'last_start = ctx.Value("q", 0, lock=False)' not in source


def test_m2_source_range_reconciliation_is_exact_once_against_load():
    command = c0.C0ModelLoad(
        path="/tmp/model.safetensors", identity=(1, 2, 3, 4), source_offset=128,
        data_bytes=3 * 64 * 1024 * 1024 + 9, read_bytes=64 * 1024 * 1024,
        total_blocks=4, lane_ranges=((0, 1), (1, 2), (2, 3), (3, 4)), generation=1,
    )
    aggregate = {
        "expected_block_count": 4, "expected_bytes": command.data_bytes,
        "expected_block_ranges": [[0, 1], [1, 2], [2, 3], [3, 4]],
        "expected_source_ranges": [[128, 128 + command.data_bytes]],
        "read_count": 4, "read_bytes": command.data_bytes, "min_block": 0,
        "max_block": 3, "gap_count": 0, "duplicate_count": 0,
        "out_of_range_count": 0, "exact_source_ranges": True, "exact_once": True,
    }
    assert c0.reconcile_c0_m2_reader_aggregate(command, aggregate)["ok"]
    aggregate["duplicate_count"] = 1
    assert not c0.reconcile_c0_m2_reader_aggregate(command, aggregate)["ok"]


def test_m2_child_uses_explicit_parent_authority_path_over_runtime_dir(tmp_path):
    control = c0.C0M2Control(arena_epoch=1)
    arena = c0.shared_memory.SharedMemory(create=True, size=1)
    source_path = c0.write_c0_child_source_file(c0._C0_M2_CHILD_SOURCE)
    authority_path = os.path.abspath(
        os.path.join(os.path.dirname(c0.__file__), "m2_source_core.py")
    )
    decoy_runtime = tmp_path / "different-mounted-runtime"
    decoy_runtime.mkdir()
    (decoy_runtime / "m2_source_core.py").write_bytes(b"not-the-parent-authority")
    try:
        argv = [
            sys.executable, source_path, arena.name, "1", control.name,
            str(c0.C0M2Control.SIZE_BYTES), "1", str(control.session_epoch), "0" * 40,
        ]
        env = os.environ.copy()
        env["COMFYMODAL_C0_RUNTIME_DIR"] = str(decoy_runtime)
        env[c0.C0_M2_AUTHORITY_PATH_ENV] = authority_path
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=10, env=env)
        assert completed.returncode != 0
        evidence = control.evidence()
        assert evidence["status"] == "authority_hash_mismatch"
        assert evidence["m2_authority"]["expected_path"] == authority_path
        assert evidence["m2_authority"]["observed_path"] == authority_path
        assert evidence["m2_authority"]["expected_sha1"] == "0" * 40
        authority_source = open(authority_path, "rb").read()
        expected_blob_sha1 = hashlib.sha1(
            (f"blob {len(authority_source)}\0").encode("ascii") + authority_source
        ).hexdigest()
        assert evidence["m2_authority"]["observed_sha1"] == expected_blob_sha1
    finally:
        arena.close()
        arena.unlink()
        control.close()


def test_m2_authority_hash_valid_value_uses_git_blob_identity():
    authority = (os.path.dirname(c0.__file__) + os.sep + "m2_source_core.py")
    with open(authority, "rb") as authority_file:
        source = authority_file.read()
    git_blob_sha1 = hashlib.sha1(
        (f"blob {len(source)}\0").encode("ascii") + source
    ).hexdigest()

    assert c0.M2_SOURCE_CORE_AUTHORITY_SHA1 == "00ddc40a3226208c208c93dd03b3d24417c8eb35"
    assert git_blob_sha1 != hashlib.sha1(source).hexdigest()
    assert 'f"blob {len(authority_source)}\\0".encode("ascii")' in c0._C0_M2_CHILD_SOURCE


def test_m2_child_source_imports_hashlib_before_authority_hashing():
    source = c0._C0_M2_CHILD_SOURCE

    assert "import hashlib" in source
    assert source.index("import hashlib") < source.index("hashlib.sha1(")


def test_child_ready_failure_includes_redacted_bounded_stderr():
    with tempfile.TemporaryFile() as stderr:
        stderr.write(
            b"startup exploded MODAL_TOKEN=secret-value "
            + (b"x" * (c0._C0_CHILD_STARTUP_STDERR_LIMIT + 1000))
        )
        stderr.seek(0)
        ring = cast(Any, object.__new__(c0.SharedArenaRing))
        ring._stderr = stderr
        ring._proc = SimpleNamespace(poll=lambda: 17)

        failure = ring._child_ready_failure("stdout_eof")

    assert failure["error"] == "stdout_eof"
    assert failure["returncode"] == 17
    assert "startup exploded" in failure["stderr"]
    assert "secret-value" not in failure["stderr"]
    assert len(failure["stderr"]) <= c0._C0_CHILD_STARTUP_STDERR_LIMIT


class _FakeM2Control:
    def __init__(self, lifecycle):
        self._lifecycle = dict(lifecycle)
        self.closed = False

    def lifecycle(self):
        return dict(self._lifecycle)

    def evidence(self):
        return {}

    def close(self):
        self.closed = True


def _fake_ring_for_close(m2_shutdown):
    ring = cast(Any, object.__new__(c0.SharedArenaRing))
    ring._close_lock = threading.RLock()
    ring._closed = False
    ring._closing = threading.Event()
    ring._req_cond = threading.Condition()
    ring._registry = type("Registry", (), {"outstanding": 0})()
    ring.control_session = None
    ring._dead = None
    ring._inflight = 0
    ring.child_pid = 123
    ring.epoch = 1
    ring.cleanup_unresolved = False
    ring.cleanup_status = {}
    ring.m2_control = _FakeM2Control(m2_shutdown["lifecycle"])
    ring.m2_shutdown_evidence = dict(m2_shutdown)
    ring._stop_live_sampler = lambda: None
    ring._stop_child = lambda: None
    ring._join_writer = lambda: None
    ring._fd_reconciliation = lambda **kwargs: {}
    ring._preadv_sickness_evidence = lambda: {}
    ring.child_viztracer = None
    ring.child_ready_evidence = None
    ring.runtime_markers = {}
    ring.child_runtime_markers = None
    ring.child_fd_telemetry = None
    ring.unregister_ms = None
    ring.unregister_calls = 0
    ring.release_calls = 0

    def unregister():
        ring.unregister_calls += 1

    def release_mapping():
        ring.release_calls += 1
        return "unlinked"

    ring._unregister = unregister
    ring._release_mapping = release_mapping
    return ring


def _m2_shutdown(*, reaped, survivors):
    return {
        "lifecycle": {
            "readers_expected": 4,
            "readers_reaped": reaped,
            "terminal_status": c0.C0M2Control.TERMINAL_DONE,
        },
        "evidence": {"cleanup": {"descendants_survived": list(survivors)}},
    }


def test_m2_surviving_descendant_retains_arena_and_control():
    ring = _fake_ring_for_close(_m2_shutdown(reaped=4, survivors=[9001]))

    first = ring.close()
    second = ring.close()

    assert first["cleanup_status"] == "cleanup_unresolved"
    assert first["cleanup_incomplete"] is True
    assert first["m2_cleanup"]["status"] == "incomplete"
    assert first["m2_cleanup"]["descendants_survived"] == [9001]
    assert first["mapping_retained"] is True
    assert first["control_retained"] is True
    assert ring.unregister_calls == 0
    assert ring.release_calls == 0
    assert ring.m2_control.closed is False
    assert second == first


def test_m2_incomplete_reader_reap_retains_arena_and_control():
    ring = _fake_ring_for_close(_m2_shutdown(reaped=3, survivors=[]))

    result = ring.close()

    assert result["cleanup_status"] == "cleanup_unresolved"
    assert result["m2_cleanup"]["reason"] == "readers_reaped:3!=4"
    assert ring.unregister_calls == 0
    assert ring.release_calls == 0
    assert ring.m2_control.closed is False


def test_m2_clean_reap_releases_once_and_is_idempotent():
    ring = _fake_ring_for_close(_m2_shutdown(reaped=4, survivors=[]))

    first = ring.close()
    second = ring.close()

    assert first["cleanup_status"] == "released"
    assert first["m2_cleanup"]["status"] == "complete"
    assert first["release_status"] == "unlinked"
    assert ring.unregister_calls == 1
    assert ring.release_calls == 1
    assert ring.m2_control.closed is True
    assert second == first
