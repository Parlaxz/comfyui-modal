"""A CUDA-sterile positioned-read race data collector.

The collector records syscall timings and emits descriptive statistics.  A
local run is not, by itself, evidence of a cold-storage result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import ctypes
import mmap
import statistics
import struct
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Optional, cast


def percentile(values: list[float], percent: float) -> float:
    """Return a percentile using linear interpolation between ranks."""
    if not values:
        return 0.0
    if not 0.0 <= percent <= 100.0:
        raise ValueError("percent must be between 0 and 100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


# ==========================================================================
# ENGINE RESULT CONTRACT
#
# Every engine that feeds the campaign runners must return these keys.  The
# runners' validity gate reads them, and a missing key makes EVERY run in a
# campaign look invalid.
#
# History: `run_worker_model_witness_probe` was added without `pacer` /
# `launch_spacing`.  Every run then failed validation, and because the runner
# retried each slot up to 30 times (a cap meant for transient odin rejections)
# it burned ~300 H100 runs before being stopped.
#
# Guarding this inside each engine is not enough: a future engine written by
# anyone else would silently reintroduce it.  So it is enforced at the SINGLE
# funnel point every engine passes through -- `_run_worker_model` in
# e04_source_race_modal.py -- which turns a silent schema gap into one loud,
# clearly-labelled failure before a campaign can spend a second run.
#
# ADDING A NEW ENGINE?  Call `assert_result_contract(result, engine_name)`
# before returning, or simply include these keys in the returned dict.
# ==========================================================================
_RESULT_CONTRACT_KEYS: tuple[str, ...] = (
    "worker_model",          # identity of the topology that produced the run
    "physical_reads",        # accepted logical read count (must equal expected)
    "reads",                 # per-read telemetry list
    "coverage",              # exact-once coverage proof
    "pacer",                 # {"observed_min_global_claim_gap_ms": float}
    "launch_spacing",        # {"max_simultaneous_in_flight": int, ...}
    "useful_bytes",
    "full_file_wall_ms",
)


def assert_result_contract(result: Any, engine: str) -> None:
    """Fail loudly if an engine result cannot satisfy the campaign validity gate."""
    if not isinstance(result, dict):
        raise RuntimeError(
            f"ENGINE_RESULT_CONTRACT_VIOLATION:{engine}:result is "
            f"{type(result).__name__}, not dict")
    missing = [k for k in _RESULT_CONTRACT_KEYS if k not in result]
    if missing:
        raise RuntimeError(
            f"ENGINE_RESULT_CONTRACT_VIOLATION:{engine}:missing={missing}. "
            "The campaign validity gate reads these keys; without them every "
            "run is rejected as invalid. Required: "
            f"{list(_RESULT_CONTRACT_KEYS)}. "
            "In particular `pacer.observed_min_global_claim_gap_ms` and "
            "`launch_spacing.max_simultaneous_in_flight` must be present."
        )


def sample_stdev(values: list[float]) -> float:
    """Return sample standard deviation, using zero for fewer than two values."""
    return float(statistics.stdev(values)) if len(values) > 1 else 0.0


def _resolve_read_syscall() -> tuple[Callable[[int, memoryview, int], int], str]:
    preadv = getattr(os, "preadv", None)
    if callable(preadv):
        preadv_fn = cast(Callable[[int, list[memoryview], int], int], preadv)

        def read_preadv(fd: int, target: memoryview, offset: int) -> int:
            return int(preadv_fn(fd, [target], offset))

        return read_preadv, "os.preadv"

    pread = getattr(os, "pread", None)
    if callable(pread):
        pread_fn = cast(Callable[[int, int, int], bytes], pread)

        def read_pread(fd: int, target: memoryview, offset: int) -> int:
            data = pread_fn(fd, len(target), offset)
            target[: len(data)] = data
            return len(data)

        return read_pread, "os.pread"

    locks: dict[int, threading.Lock] = {}
    locks_guard = threading.Lock()

    def read_lseek(fd: int, target: memoryview, offset: int) -> int:
        with locks_guard:
            lock = locks.setdefault(fd, threading.Lock())
        with lock:
            saved = os.lseek(fd, 0, os.SEEK_CUR)
            try:
                os.lseek(fd, offset, os.SEEK_SET)
                data = os.read(fd, len(target))
                target[: len(data)] = data
                return len(data)
            finally:
                os.lseek(fd, saved, os.SEEK_SET)

    return read_lseek, "os.lseek+os.read"


def _stats(values: list[float], percentiles: tuple[int, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "count": len(values),
        "mean_ms": float(statistics.mean(values)) if values else 0.0,
        "median_ms": percentile(values, 50),
        "max_ms": max(values) if values else 0.0,
        "stdev_ms": sample_stdev(values),
    }
    for p in percentiles:
        result[f"p{p}_ms"] = percentile(values, p)
    for threshold in (100, 250, 500, 1000):
        result[f"ge_{threshold}"] = sum(value >= threshold for value in values)
    return result


def _fd_id(fd: Any) -> Any:
    return fd if isinstance(fd, (int, float, str, bool, type(None))) else repr(fd)


def run_race_oracle(
    *,
    file_path: str,
    race_width: int,
    logical_qd: int = 2,
    read_bytes: int = 128 * 1024 * 1024,
    fd_mode: str = "independent",
    max_blocks: int | None = None,
    offset_start: int = 0,
    expected_sha256: str | None = None,
    hash_mode: str = "winners_in_order",
    clock_ns=None,
    read_syscall=None,
    fd_opener=None,
    fd_closer=None,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
) -> dict:
    """Run positioned-read races and return a JSON-serializable report."""
    if race_width < 1:
        raise ValueError("race_width must be at least one")
    if logical_qd < 1:
        raise ValueError("logical_qd must be at least one")
    if read_bytes < 1:
        raise ValueError("read_bytes must be at least one")
    if fd_mode not in {"independent", "shared"}:
        raise ValueError("fd_mode must be independent or shared")
    if hash_mode not in {"none", "winners_in_order", "per_block"}:
        raise ValueError("hash_mode must be none, winners_in_order, or per_block")
    if offset_start < 0:
        raise ValueError("offset_start must be non-negative")
    if max_blocks is not None and max_blocks < 0:
        raise ValueError("max_blocks must be non-negative")

    torch_present_before = "torch" in sys.modules
    clock_ns = clock_ns or time.perf_counter_ns
    if read_syscall is None:
        read_syscall, syscall_impl = _resolve_read_syscall()
    else:
        syscall_impl = "injected"
    if fd_mode == "shared" and syscall_impl == "os.lseek+os.read":
        raise RuntimeError("shared fd mode is unsafe with the lseek+read fallback")

    fd_opener = fd_opener or (lambda path: os.open(path, os.O_RDONLY))
    fd_closer = fd_closer or os.close
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    if offset_start > file_size:
        raise ValueError("offset_start cannot exceed file size")

    file_identity = {
        "path": file_path,
        "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }
    blocks: list[dict[str, int]] = []
    offset = offset_start
    while offset < file_size and (max_blocks is None or len(blocks) < max_blocks):
        length = min(read_bytes, file_size - offset)
        blocks.append({"block_index": len(blocks), "offset": offset, "length": length})
        offset += length

    lane_count = logical_qd * race_width
    lane_buffers = [bytearray(read_bytes) for _ in range(lane_count)]
    prepared_views: dict[int, dict[tuple[int, int], memoryview]] = {}
    for block in blocks:
        prepared_views[block["block_index"]] = {
            (slot, racer): memoryview(lane_buffers[slot * race_width + racer])[: block["length"]]
            for slot in range(logical_qd)
            for racer in range(race_width)
        }

    fds: dict[tuple[int, int], Any] = {}
    errors: list[str] = []
    errors_lock = threading.Lock()
    attempt_records: dict[int, list[dict[str, Any]]] = {
        block["block_index"]: [] for block in blocks
    }
    attempt_lock = threading.Lock()
    active_attempts = 0
    active_lock = threading.Lock()
    aborted = threading.Event()
    waves: list[list[dict[str, int]]] = [
        blocks[start : start + logical_qd] for start in range(0, len(blocks), logical_qd)
    ]
    wave_release_ns: dict[int, int] = {}
    wave_finished = [threading.Event() for _ in waves]
    wave_continue = [threading.Event() for _ in waves]
    wave_counts = [0 for _ in waves]
    wave_count_lock = threading.Lock()

    def add_error(message: str) -> None:
        with errors_lock:
            errors.append(message)

    def wave_action(wave_index: int = 0) -> None:
        # The barrier is cyclic; the worker's loop assigns the cycle below.
        del wave_index
        current = len(wave_release_ns)
        wave_release_ns[current] = int(clock_ns())

    barrier = threading.Barrier(lane_count, action=wave_action)

    def mark_wave_done(wave_index: int) -> None:
        with wave_count_lock:
            wave_counts[wave_index] += 1
            if wave_counts[wave_index] == lane_count:
                wave_finished[wave_index].set()

    def abort_barrier(wave_index: int, exc: BaseException) -> None:
        if not aborted.is_set():
            aborted.set()
            add_error(f"wave {wave_index} barrier: {type(exc).__name__}: {exc}")
            try:
                barrier.abort()
            except Exception:
                pass
            for event in wave_finished:
                event.set()
            for event in wave_continue:
                event.set()

    def racer_worker(slot: int, racer: int) -> None:
        nonlocal active_attempts
        lane = (slot, racer)
        for wave_index, wave_blocks in enumerate(waves):
            if aborted.is_set():
                return
            try:
                barrier.wait()
            except threading.BrokenBarrierError as exc:
                abort_barrier(wave_index, exc)
                return

            block = wave_blocks[slot] if slot < len(wave_blocks) else None
            if block is not None:
                block_index = block["block_index"]
                target = prepared_views[block_index][lane]
                fd = fds[lane]
                attempt_submit_ns = int(clock_ns())
                preadv_enter_ns = int(clock_ns())
                raw_bytes = 0
                error_exc: BaseException | None = None
                with active_lock:
                    active_attempts += 1
                try:
                    raw_bytes = int(read_syscall(fd, target, block["offset"]))
                except BaseException as exc:  # record syscall failures as data
                    error_exc = exc
                preadv_exit_ns = int(clock_ns())
                with active_lock:
                    active_attempts -= 1
                error = (
                    f"{type(error_exc).__name__}: {error_exc}" if error_exc is not None else None
                )
                bytes_returned = 0 if error_exc is not None else raw_bytes
                if error is not None:
                    status = "error"
                elif bytes_returned != block["length"]:
                    status = "short"
                else:
                    status = "ok"
                per_attempt_valid = error is None and bytes_returned == block["length"]
                record = {
                    "logical_slot_within_wave": slot,
                    "racer_index": racer,
                    "lane": [slot, racer],
                    "fd_id": _fd_id(fd),
                    "dest_buffer_id": slot * race_width + racer,
                    "attempt_submit_ns": attempt_submit_ns,
                    "preadv_enter_ns": preadv_enter_ns,
                    "preadv_exit_ns": preadv_exit_ns,
                    "physical_preadv_duration_ms": (preadv_exit_ns - preadv_enter_ns) / 1e6,
                    "physical_syscall_ms": (preadv_exit_ns - preadv_enter_ns) / 1e6,
                    "bytes_returned": bytes_returned,
                    "bytes_read": bytes_returned,
                    "status": status,
                    "error": error,
                    "per_attempt_valid": bool(per_attempt_valid),
                    "valid": bool(per_attempt_valid),
                    "is_winner": False,
                    "_candidate": bytes(target) if error is None else b"",
                }
                with attempt_lock:
                    attempt_records[block_index].append(record)
            mark_wave_done(wave_index)
            if wave_index < len(waves) - 1:
                wave_continue[wave_index].wait()

    try:
        if blocks:
            if fd_mode == "shared":
                shared_fd = fd_opener(file_path)
                for slot in range(logical_qd):
                    for racer in range(race_width):
                        fds[(slot, racer)] = shared_fd
            else:
                for slot in range(logical_qd):
                    for racer in range(race_width):
                        fds[(slot, racer)] = fd_opener(file_path)

        threads = [
            threading.Thread(target=racer_worker, args=(slot, racer))
            for slot in range(logical_qd)
            for racer in range(race_width)
        ]
        for thread in threads:
            thread.start()

        # Handoff after every wave preserves each lane's buffer until its
        # winner has been copied and, when requested, hashed.
        winner_hasher = hashlib.sha256() if hash_mode == "winners_in_order" else None
        for wave_index, wave_blocks in enumerate(waves):
            wave_finished[wave_index].wait()
            if aborted.is_set():
                break
            if winner_hasher is not None:
                for block in wave_blocks:
                    records = attempt_records[block["block_index"]]
                    valid = [record for record in records if record["per_attempt_valid"]]
                    if valid:
                        winner_hasher.update(min(valid, key=lambda item: (item["preadv_exit_ns"], item["racer_index"]))["_candidate"])
            if wave_index < len(waves) - 1:
                wave_continue[wave_index].set()
        if aborted.is_set():
            for event in wave_continue:
                event.set()
        for thread in threads:
            thread.join()

        completed_blocks: list[dict[str, Any]] = []
        accepted_ms: list[float] = []
        physical_ms: list[float] = []
        loser_lifetimes: list[float] = []
        winner_indices = {index: 0 for index in range(race_width)}
        accepted_bytes = 0
        cumulative_physical_bytes = 0
        cumulative_attempts = 0
        waves_output: list[dict[str, Any]] = []
        first_start_ns: Optional[int] = None
        last_exit_ns: Optional[int] = None
        last_winner_exit_ns: Optional[int] = None

        for wave_index, wave_blocks in enumerate(waves):
            release_ns = wave_release_ns.get(wave_index)
            wave_output = {
                "wave_index": wave_index,
                "block_indices": [block["block_index"] for block in wave_blocks],
                "wave_release_ns": release_ns,
                "attempts_alive_after_drain": 0,
            }
            waves_output.append(wave_output)
            if release_ns is None:
                add_error(f"wave {wave_index}: missing wave release timestamp")

            for logical_slot, block in enumerate(wave_blocks):
                block_index = block["block_index"]
                records = sorted(
                    attempt_records[block_index], key=lambda item: item["racer_index"]
                )
                valid = [record for record in records if record["per_attempt_valid"]]
                winner = min(valid, key=lambda item: (item["preadv_exit_ns"], item["racer_index"])) if valid else None
                for record in records:
                    physical_ms.append(record["physical_preadv_duration_ms"])
                exits = [record["preadv_exit_ns"] for record in records]
                winner_completion_ns = winner["preadv_exit_ns"] if winner else None
                loser_records = [record for record in records if record is not winner]
                loser_completion_ns = [record["preadv_exit_ns"] for record in loser_records]
                deltas = (
                    [(record["preadv_exit_ns"] - winner["preadv_exit_ns"]) / 1e6 for record in loser_records]
                    if winner
                    else []
                )
                for record in loser_records:
                    record["loser_lifetime_ms"] = (
                        (record["preadv_exit_ns"] - release_ns) / 1e6 if release_ns is not None else 0.0
                    )
                    loser_lifetimes.append(record["loser_lifetime_ms"])
                if winner is None:
                    add_error(f"block {block_index}: no valid winner")
                else:
                    winner["is_winner"] = True
                    accepted_time = (
                        (winner["preadv_exit_ns"] - release_ns) / 1e6 if release_ns is not None else 0.0
                    )
                    accepted_ms.append(accepted_time)
                    accepted_bytes += block["length"]
                    winner_indices[winner["racer_index"]] += 1
                    last_winner_exit_ns = max(
                        last_winner_exit_ns or winner["preadv_exit_ns"], winner["preadv_exit_ns"]
                    )
                if exits:
                    last_exit_ns = max(last_exit_ns or max(exits), max(exits))
                first_start_ns = (
                    release_ns
                    if first_start_ns is None
                    else min(first_start_ns, release_ns) if release_ns is not None else first_start_ns
                )
                with active_lock:
                    alive_after_drain = active_attempts
                if alive_after_drain != 0:
                    add_error(f"block {block_index}: attempts_alive_after_drain={alive_after_drain}")
                block_result: dict[str, Any] = {
                    "block_index": block_index,
                    "logical_index": block_index,
                    "wave_index": wave_index,
                    "logical_slot_within_wave": logical_slot,
                    "file_identity": dict(file_identity),
                    "fd_mode": fd_mode,
                    "offset": block["offset"],
                    "length": block["length"],
                    "race_width": race_width,
                    "wave_release_ns": release_ns,
                    "logical_race_start_ns": release_ns,
                    "race_start_ns": release_ns,
                    "dispatch_skew_ms": (
                        (max(record["preadv_enter_ns"] for record in records) - min(record["preadv_enter_ns"] for record in records)) / 1e6
                        if records
                        else 0.0
                    ),
                    "winner_racer_index": winner["racer_index"] if winner else None,
                    "winner_completion_ns": winner_completion_ns,
                    "winning_completion_timestamp_ns": winner_completion_ns,
                    "accepted_preadv_ms": (
                        (winner_completion_ns - release_ns) / 1e6
                        if winner_completion_ns is not None and release_ns is not None
                        else None
                    ),
                    "loser_completion_ns": loser_completion_ns,
                    "loser_completion_timestamps_ns": loser_completion_ns,
                    "winner_to_loser_end_delta_ms": deltas,
                    "drain_wait_ms": max(0.0, max(deltas)) if deltas else 0.0,
                    "cumulative_attempts_before_block": cumulative_attempts,
                    "cumulative_physical_bytes_before_block": cumulative_physical_bytes,
                    "attempts_alive_after_drain": alive_after_drain,
                    "fighters": records,
                    "physical_racers": records,
                    "_winner_candidate": winner["_candidate"] if winner else None,
                }
                if hash_mode == "per_block" and winner is not None:
                    block_result["winner_sha256"] = hashlib.sha256(winner["_candidate"]).hexdigest()
                completed_blocks.append(block_result)
                cumulative_attempts += len(records)
                cumulative_physical_bytes += sum(record["bytes_returned"] for record in records)

        winner_digest = None
        if hash_mode == "winners_in_order" and winner_hasher is not None:
            winner_digest = winner_hasher.hexdigest()
        elif hash_mode == "per_block":
            digest = hashlib.sha256()
            for block in completed_blocks:
                if block["_winner_candidate"] is not None:
                    digest.update(block["_winner_candidate"])
            winner_digest = digest.hexdigest()
        expected_match = None
        if expected_sha256 is not None and winner_digest is not None:
            expected_match = winner_digest.lower() == expected_sha256.lower()
            if not expected_match:
                add_error("expected_sha256 mismatch")
        for block in completed_blocks:
            block.pop("_winner_candidate", None)
            for record in block["fighters"]:
                record.pop("_candidate", None)

        accepted_stats = _stats(accepted_ms, (90, 95, 99))
        accepted_stats["accepted_sum_ms"] = float(sum(accepted_ms))
        winner_envelope_ms = (
            (last_winner_exit_ns - first_start_ns) / 1e6
            if first_start_ns is not None and last_winner_exit_ns is not None
            else 0.0
        )
        accepted_stats["winner_envelope_ms"] = winner_envelope_ms
        physical_stats = _stats(physical_ms, (95,))
        physical_stats.pop("stdev_ms", None)
        physical_stats.pop("p90_ms", None)
        physical_stats.pop("p99_ms", None)
        physical_stats["loser_count"] = sum(len(block["loser_completion_ns"]) for block in completed_blocks)
        physical_stats["loser_lifetime_mean_ms"] = (
            float(statistics.mean(loser_lifetimes)) if loser_lifetimes else 0.0
        )
        physical_stats["loser_lifetime_max_ms"] = max(loser_lifetimes) if loser_lifetimes else 0.0
        accepted_wave_wall_ms = sum(
            max(
                [block["accepted_preadv_ms"] for block in completed_blocks if block["wave_index"] == wave_index and block["accepted_preadv_ms"] is not None]
                or [0.0]
            )
            for wave_index in range(len(waves))
        )
        attempts_launched = sum(len(block["fighters"]) for block in completed_blocks)
        total_requested = sum(block["length"] * race_width for block in blocks)
        torch_present_after = "torch" in sys.modules
        oracle_imported_torch = not torch_present_before and torch_present_after
        result = {
            "schema_version": 2,
            "config": {
                "file_path": file_path,
                "file_size": file_size,
                "race_width": race_width,
                "logical_qd": logical_qd,
                "read_bytes": read_bytes,
                "fd_mode": fd_mode,
                "block_count": len(blocks),
                "offset_start": offset_start,
                "expected_sha256": expected_sha256,
                "hash_mode": hash_mode,
                "max_physical_concurrency": lane_count,
                "fd_count": len(set(map(repr, fds.values()))) if fd_mode == "shared" else len(fds),
                "unsafe_shared_lseek": False,
                "suitable_for_race_benchmarking": True,
            },
            "env": {
                "platform": platform.system(),
                "syscall_impl": syscall_impl,
                "preadv_available": callable(getattr(os, "preadv", None)),
                "torch_present_before": torch_present_before,
                "torch_present_after": torch_present_after,
                "oracle_imported_torch": oracle_imported_torch,
            },
            "identity": {
                "requested_gpu": requested_gpu,
                "observed_gpu": observed_gpu,
                "platform": platform.system(),
                "syscall_impl": syscall_impl,
                "preadv_available": callable(getattr(os, "preadv", None)),
            },
            "winner_selection_rule": "winner = earliest preadv_exit_ns among attempts with per_attempt_valid == True",
            "content_validation_mode": (
                "expected_sha256 supplied: selected winner must additionally pass it"
                if expected_sha256 is not None
                else "no expected_sha256: whole-run byte correctness is separate and does not participate in winner selection"
            ),
            "metric_definitions": {
                "accepted_wave_wall_ms": "sum over waves of max(accepted_preadv_ms for blocks in that wave); winner completion gates each wave",
                "total_wall_ms": "first wave release through the final physical syscall exit, including loser drain",
                "accepted_sum_ms": "sum of accepted_preadv_ms; this is not a wall figure",
                "dispatch_skew_ms": "max preadv_enter_ns minus min preadv_enter_ns within a block",
                "percentiles": "linear interpolation between adjacent ordered ranks",
            },
            "blocks": completed_blocks,
            "waves": waves_output,
            "accepted": accepted_stats,
            "physical": physical_stats,
            "amplification": {
                "attempts_launched": attempts_launched,
                "attempts_per_accepted_read": attempts_launched / len(accepted_ms) if accepted_ms else 0.0,
                "total_physical_bytes_requested": total_requested,
                "accepted_bytes": accepted_bytes,
                "speculative_amplification_ratio": attempts_launched / len(accepted_ms) if accepted_ms else 0.0,
                "speculative_byte_amplification_ratio": total_requested / accepted_bytes if accepted_bytes else 0.0,
            },
            "winner_distribution": {
                "wins_by_racer_index": winner_indices,
                "racer_win_fraction": {
                    index: count / len(accepted_ms) if accepted_ms else 0.0
                    for index, count in winner_indices.items()
                },
            },
            "wall": {
                "total_wall_ms": (
                    (last_exit_ns - first_start_ns) / 1e6
                    if first_start_ns is not None and last_exit_ns is not None
                    else 0.0
                ),
                "accepted_wave_wall_ms": accepted_wave_wall_ms,
                "total_drain_wait_ms": sum(block["drain_wait_ms"] for block in completed_blocks),
                "winner_envelope_ms": winner_envelope_ms,
            },
            "integrity": {
                "all_blocks_byte_exact": len(accepted_ms) == len(blocks),
                "sha256_checked": winner_digest is not None,
                "winner_sha256": winner_digest,
                "expected_sha256": expected_sha256,
                "expected_sha256_match": expected_match,
                "reference_compare": "match" if expected_match else "mismatch" if expected_match is False else "not_checked",
                "winner_selection_rule": "winner = earliest preadv_exit_ns among attempts with per_attempt_valid == True",
                "content_validation_mode": (
                    "expected_sha256 supplied: selected winner must additionally pass it"
                    if expected_sha256 is not None
                    else "no expected_sha256: whole-run byte correctness is separate and does not participate in winner selection"
                ),
                "errors": errors,
            },
        }
    finally:
        seen: set[int] = set()
        for fd in fds.values():
            marker = id(fd)
            if marker in seen:
                continue
            seen.add(marker)
            try:
                fd_closer(fd)
            except Exception as exc:
                errors.append(f"fd close: {type(exc).__name__}: {exc}")

    if oracle_imported_torch:
        raise RuntimeError("source race oracle imported torch")
    return result


def run_concurrency_probe(
    *,
    file_path: str,
    widths: tuple[int, ...] = (1, 2, 4, 8, 16),
    read_bytes: int = 128 * 1024 * 1024,
    offset_start: int = 0,
    order: str = "forward",
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
) -> dict:
    """One clean simultaneous batch of N distinct-range positioned reads, per N.

    For each N: N workers are released together by a single barrier and each
    reads a DIFFERENT contiguous range (reader i -> offset_start + i*read_bytes).
    Nothing runs inside the measured interval except ``os.preadv`` itself:
    no racing, no winner/loser, no copy, no hashing, no CUDA/H2D/SHM/events,
    no rolling refill and no repeated waves.
    """
    clock_ns = clock_ns or time.perf_counter_ns
    preadv_fn = getattr(os, "preadv", None)
    if not callable(preadv_fn):
        raise RuntimeError("os.preadv unavailable")
    preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)

    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path,
        "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    ordered_widths = sorted({int(n) for n in widths})
    if not ordered_widths or ordered_widths[0] < 1:
        raise ValueError("widths must be positive")
    max_n = ordered_widths[-1]
    # Each N owns its OWN never-reused contiguous block range, so no extent is
    # reread by a later N anywhere in the sweep.
    extents: dict[int, int] = {}
    cursor = 0
    for n in ordered_widths:
        extents[n] = cursor
        cursor += n
    if offset_start + cursor * read_bytes > file_size:
        raise ValueError("sweep extent span exceeds file size")
    if order == "forward":
        sequence = list(ordered_widths)
    elif order == "reverse":
        sequence = list(reversed(ordered_widths))
    else:
        raise ValueError("order must be forward or reverse")

    # Preallocated once, before any timing.  No per-attempt copy is ever made.
    buffers = [bytearray(read_bytes) for _ in range(max_n)]
    views = [memoryview(buffer) for buffer in buffers]

    batches: list[dict[str, Any]] = []
    for n in sequence:
        first_block = extents[n]
        offsets = [
            offset_start + (first_block + index) * read_bytes for index in range(n)
        ]
        fds = [os.open(file_path, os.O_RDONLY) for _ in range(n)]
        release_ns: dict[str, int] = {}
        enters = [0] * n
        exits = [0] * n
        returned = [0] * n

        def _release() -> None:
            release_ns["ns"] = int(clock_ns())

        barrier = threading.Barrier(n, action=_release)

        def _reader(index: int) -> None:
            offset = offsets[index]
            barrier.wait()
            enter = int(clock_ns())
            try:
                got = int(preadv(fds[index], [views[index]], offset))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            enters[index] = enter
            exits[index] = exit_ns
            returned[index] = got

        threads = [
            threading.Thread(target=_reader, args=(index,))
            for index in range(n)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for fd in fds:
            os.close(fd)

        durations = [(exits[i] - enters[i]) / 1e6 for i in range(n)]
        released = release_ns.get("ns")
        median_ms = percentile(durations, 50)
        skew_ms = (max(enters) - min(enters)) / 1e6
        release_makespan_ms = (
            (max(exits) - released) / 1e6 if released is not None else None
        )
        envelope_ms = (max(exits) - min(enters)) / 1e6
        release_to_first_enter_ms = (
            (min(enters) - released) / 1e6 if released is not None else None
        )
        useful_bytes = sum(value for value in returned if value > 0)
        release_seconds = (release_makespan_ms / 1000.0) if release_makespan_ms else 0.0
        envelope_seconds = (envelope_ms / 1000.0) if envelope_ms else 0.0
        batches.append({
            "order": order,
            "n": n,
            "block_range": [first_block, first_block + n - 1],
            "offsets": offsets,
            "lengths": [read_bytes] * n,
            "preadv_ms": durations,
            "mean_ms": statistics.fmean(durations),
            "median_ms": median_ms,
            "min_ms": min(durations),
            "max_ms": max(durations),
            "dispatch_skew_ms": skew_ms,
            "release_to_first_enter_ms": release_to_first_enter_ms,
            "wave_release_ns": released,
            "release_wave_makespan_ms": release_makespan_ms,
            "syscall_envelope_ms": envelope_ms,
            "bytes_returned": returned,
            "useful_bytes": useful_bytes,
            "ranges_distinct_and_non_overlapping": (
                len({(offsets[i], read_bytes) for i in range(n)}) == n
                and all(
                    offsets[i] + read_bytes <= offsets[i + 1]
                    for i in range(n - 1)
                )
            ),
            "all_full_length": all(value == read_bytes for value in returned),
            "release_decimal_gbps": (
                (useful_bytes / release_seconds / 1e9) if release_seconds else None
            ),
            "release_gib_per_s": (
                (useful_bytes / release_seconds / (1024 ** 3)) if release_seconds else None
            ),
            "syscall_envelope_decimal_gbps": (
                (useful_bytes / envelope_seconds / 1e9) if envelope_seconds else None
            ),
            "syscall_envelope_gib_per_s": (
                (useful_bytes / envelope_seconds / (1024 ** 3)) if envelope_seconds else None
            ),
            "scheduler_confounded": bool(median_ms > 0 and skew_ms > 0.25 * median_ms),
        })

    return {
        "schema_version": 1,
        "kind": "source_concurrency_probe",
        "config": {
            "file_path": file_path,
            "read_bytes": read_bytes,
            "offset_start": offset_start,
            "widths": ordered_widths,
            "order": order,
            "extent_first_block_by_n": extents,
            "total_blocks_used": cursor,
            "max_n": max_n,
        },
        "env": {
            "platform": platform.system(),
            "syscall_impl": "os.preadv",
            "preadv_available": callable(getattr(os, "preadv", None)),
        },
        "identity": {
            "requested_gpu": requested_gpu,
            "observed_gpu": observed_gpu,
        },
        "file_identity": file_identity,
        "batches": batches,
    }


def run_rolling_source_probe(
    *,
    file_path: str,
    workers: tuple[int, ...] = (1, 2, 4, 8),
    read_bytes: int = 128 * 1024 * 1024,
    blocks_per_worker: int = 6,
    offset_start: int = 0,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
) -> dict:
    """Rolling source-QD probe: N persistent workers, one contiguous region each.

    Each worker owns one persistent FD, one contiguous non-overlapping file
    region, and one reusable 128 MiB buffer that it reuses immediately after
    each read returns.  A worker issues its next ``os.preadv`` as soon as its
    previous one returns; workers are fully independent and never wait on each
    other or on any downstream GPU state.  Source QD is N -- one active read per
    worker.

    Nothing runs inside the measured interval except ``os.preadv`` itself: no
    copy, no hashing, no mutex, no winner/loser, no CUDA/H2D/SHM/events.
    """
    clock_ns = clock_ns or time.perf_counter_ns
    preadv_fn = getattr(os, "preadv", None)
    if not callable(preadv_fn):
        raise RuntimeError("os.preadv unavailable")
    preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)

    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path,
        "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    ordered = sorted({int(n) for n in workers})
    if not ordered or ordered[0] < 1:
        raise ValueError("workers must be positive")
    if blocks_per_worker < 1:
        raise ValueError("blocks_per_worker must be positive")
    max_n = ordered[-1]
    if offset_start + max_n * blocks_per_worker * read_bytes > file_size:
        raise ValueError("worker region span exceeds file size")

    batches: list[dict[str, Any]] = []
    for n in ordered:
        buffers = [bytearray(read_bytes) for _ in range(n)]
        views = [memoryview(buffer) for buffer in buffers]
        records: list[list[dict[str, Any]]] = [[] for _ in range(n)]
        fds = [os.open(file_path, os.O_RDONLY) for _ in range(n)]
        start_barrier = threading.Barrier(n)

        def _worker(worker_id: int) -> None:
            region_start = offset_start + worker_id * blocks_per_worker * read_bytes
            fd = fds[worker_id]
            previous_exit: int | None = None
            start_barrier.wait()
            for block_index in range(blocks_per_worker):
                offset = region_start + block_index * read_bytes
                view = views[worker_id]
                enter = int(clock_ns())
                try:
                    got = int(preadv(fd, [view], offset))
                except BaseException:
                    got = -1
                exit_ns = int(clock_ns())
                records[worker_id].append({
                    "worker": worker_id,
                    "block_index": block_index,
                    "offset": offset,
                    "bytes_returned": got,
                    "preadv_enter_ns": enter,
                    "preadv_exit_ns": exit_ns,
                    "preadv_ms": (exit_ns - enter) / 1e6,
                    "refill_gap_ms": (
                        None if previous_exit is None else (enter - previous_exit) / 1e6
                    ),
                })
                previous_exit = exit_ns

        threads = [
            threading.Thread(target=_worker, args=(worker_id,))
            for worker_id in range(n)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for fd in fds:
            os.close(fd)

        flat = [record for group in records for record in group]
        durations = [record["preadv_ms"] for record in flat]
        useful_bytes = sum(
            record["bytes_returned"] for record in flat if record["bytes_returned"] > 0
        )
        first_enter = min(record["preadv_enter_ns"] for record in flat)
        last_exit = max(record["preadv_exit_ns"] for record in flat)
        source_wall_ms = (last_exit - first_enter) / 1e6
        wall_seconds = source_wall_ms / 1000.0

        per_worker = []
        for worker_id in range(n):
            group = records[worker_id]
            if not group:
                continue
            worker_bytes = sum(
                record["bytes_returned"] for record in group if record["bytes_returned"] > 0
            )
            worker_wall_ms = (
                max(record["preadv_exit_ns"] for record in group)
                - min(record["preadv_enter_ns"] for record in group)
            ) / 1e6
            gaps = [
                record["refill_gap_ms"]
                for record in group
                if record["refill_gap_ms"] is not None
            ]
            per_worker.append({
                "worker": worker_id,
                "reads": len(group),
                "useful_bytes": worker_bytes,
                "wall_ms": worker_wall_ms,
                "decimal_gbps": (
                    (worker_bytes / (worker_wall_ms / 1000.0) / 1e9)
                    if worker_wall_ms else None
                ),
                "refill_gap_mean_ms": statistics.fmean(gaps) if gaps else None,
                "refill_gap_median_ms": percentile(gaps, 50) if gaps else None,
                "refill_gap_max_ms": max(gaps) if gaps else None,
            })

        # Effective source QD is derived post hoc from the recorded intervals;
        # nothing is sampled inside the timed region.
        events: list[tuple[int, int]] = []
        for record in flat:
            events.append((record["preadv_enter_ns"], 1))
            events.append((record["preadv_exit_ns"], -1))
        events.sort()
        worker_first = [min(r["preadv_enter_ns"] for r in group) for group in records if group]
        worker_last = [max(r["preadv_exit_ns"] for r in group) for group in records if group]
        span_start = max(worker_first) if worker_first else None
        span_end = min(worker_last) if worker_last else None
        concurrent = 0
        max_in_span: int | None = None
        min_in_span: int | None = None
        if span_start is not None and span_end is not None and span_end > span_start:
            for timestamp, delta in events:
                concurrent += delta
                if span_start <= timestamp <= span_end:
                    max_in_span = concurrent if max_in_span is None else max(max_in_span, concurrent)
                    min_in_span = concurrent if min_in_span is None else min(min_in_span, concurrent)

        batches.append({
            "n": n,
            "blocks_per_worker": blocks_per_worker,
            "read_bytes": read_bytes,
            "worker_regions": [
                {
                    "worker": worker_id,
                    "first_offset": offset_start + worker_id * blocks_per_worker * read_bytes,
                    "blocks": blocks_per_worker,
                }
                for worker_id in range(n)
            ],
            "total_reads": len(flat),
            "useful_bytes": useful_bytes,
            "mean_ms": statistics.fmean(durations),
            "median_ms": percentile(durations, 50),
            "p90_ms": percentile(durations, 90),
            "p95_ms": percentile(durations, 95),
            "max_ms": max(durations),
            "min_ms": min(durations),
            "source_wall_ms": source_wall_ms,
            "useful_decimal_gbps": (useful_bytes / wall_seconds / 1e9) if wall_seconds else None,
            "useful_gib_per_s": (
                (useful_bytes / wall_seconds / (1024 ** 3)) if wall_seconds else None
            ),
            "all_full_length": all(
                record["bytes_returned"] == read_bytes for record in flat
            ),
            "per_worker": per_worker,
            "effective_qd_span_ms": (
                (span_end - span_start) / 1e6
                if span_start is not None and span_end is not None else None
            ),
            "effective_qd_max_in_span": max_in_span,
            "effective_qd_min_in_span": min_in_span,
            "effective_qd_fell_below_n": bool(
                min_in_span is not None and min_in_span < n
            ),
            "reads": flat,
        })

    return {
        "schema_version": 1,
        "kind": "rolling_source_probe",
        "config": {
            "file_path": file_path,
            "read_bytes": read_bytes,
            "blocks_per_worker": blocks_per_worker,
            "offset_start": offset_start,
            "workers": ordered,
        },
        "env": {
            "platform": platform.system(),
            "syscall_impl": "os.preadv",
            "preadv_available": callable(getattr(os, "preadv", None)),
        },
        "identity": {
            "requested_gpu": requested_gpu,
            "observed_gpu": observed_gpu,
        },
        "file_identity": file_identity,
        "batches": batches,
    }


def run_geometry_sweep(
    *,
    file_path: str,
    cells: Any = None,
    offset_start: int = 0,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
) -> dict:
    """Run several (read size, QD) rolling cells over distinct regions.

    Each cell is exactly one call to :func:`run_rolling_source_probe` with the
    same architecture; only the read size and worker count differ.  Each cell
    gets its own never-reused contiguous region, so no bytes are read twice
    anywhere in the sweep.
    """
    default_cells = (
        {"read_mib": 128, "qd": 4, "blocks_per_worker": 4},
        {"read_mib": 64, "qd": 8, "blocks_per_worker": 4},
        {"read_mib": 32, "qd": 8, "blocks_per_worker": 4},
        {"read_mib": 32, "qd": 16, "blocks_per_worker": 4},
    )
    cell_specs = tuple(cells) if cells else default_cells

    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path,
        "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    cursor = int(offset_start)
    cell_results: list[dict[str, Any]] = []
    env: dict[str, Any] = {}
    for spec in cell_specs:
        read_mib = int(spec["read_mib"])
        qd = int(spec["qd"])
        blocks_per_worker = int(spec["blocks_per_worker"])
        read_bytes = read_mib * 1024 * 1024
        span = qd * blocks_per_worker * read_bytes
        if cursor + span > file_size:
            cell_results.append({
                "cell": {"read_mib": read_mib, "qd": qd,
                         "blocks_per_worker": blocks_per_worker},
                "status": "error",
                "error": "cell span exceeds file size",
                "region_start": cursor,
            })
            continue
        probe = run_rolling_source_probe(
            file_path=file_path,
            workers=(qd,),
            read_bytes=read_bytes,
            blocks_per_worker=blocks_per_worker,
            offset_start=cursor,
            requested_gpu=requested_gpu,
            observed_gpu=observed_gpu,
        )
        env = probe.get("env") or {}
        batch = probe["batches"][0]
        batch["cell"] = {
            "read_mib": read_mib,
            "qd": qd,
            "blocks_per_worker": blocks_per_worker,
        }
        batch["bytes_in_flight_mib"] = (qd * read_bytes) / 1024 / 1024
        batch["region_start"] = cursor
        cell_results.append(batch)
        cursor += span

    return {
        "schema_version": 1,
        "kind": "geometry_sweep",
        "config": {
            "file_path": file_path,
            "offset_start": offset_start,
            "cells": [
                {
                    "read_mib": int(spec["read_mib"]),
                    "qd": int(spec["qd"]),
                    "blocks_per_worker": int(spec["blocks_per_worker"]),
                }
                for spec in cell_specs
            ],
            "total_span_bytes": cursor - int(offset_start),
        },
        "env": env,
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "cells": cell_results,
    }


def run_fullfile_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int,
    min_launch_gap_ns: int = 0,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
) -> dict:
    """One full-file pass: QD persistent rolling workers cover the whole file once.

    Workers get contiguous, non-overlapping block partitions that together
    cover the entire file exactly once (the final block may be a valid partial
    read).  Same architecture as the rolling probe: one persistent FD and one
    reusable buffer per worker, no barrier after startup, immediate refill, and
    nothing inside the timed interval except ``os.preadv`` itself.

    ``min_launch_gap_ns`` enforces a GLOBAL (all-worker) minimum wall-time gap
    between successive ``preadv`` STARTS.  It gates permission to start only:
    the lock is never held across the wait nor across the syscall itself, so
    reads whose starts are spaced by less than their duration still overlap
    freely.  ``0`` traverses the identical gate with no enforced gap, so the
    control arm is not compared against a structurally different scheduler.
    """
    clock_ns = clock_ns or time.perf_counter_ns
    preadv_fn = getattr(os, "preadv", None)
    if not callable(preadv_fn):
        raise RuntimeError("os.preadv unavailable")
    preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)

    if read_bytes < 1:
        raise ValueError("read_bytes must be positive")
    if qd < 1:
        raise ValueError("qd must be positive")
    if min_launch_gap_ns < 0:
        raise ValueError("min_launch_gap_ns must be non-negative")

    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path,
        "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    total_blocks = (file_size + read_bytes - 1) // read_bytes
    base, extra = divmod(total_blocks, qd)
    assignments: list[tuple[int, int, int]] = []
    block_cursor = 0
    for worker_id in range(qd):
        count = base + (1 if worker_id < extra else 0)
        assignments.append((worker_id, block_cursor, count))
        block_cursor += count

    buffers = [bytearray(read_bytes) for _ in range(qd)]
    views = [memoryview(buffer) for buffer in buffers]
    records: list[list[dict[str, Any]]] = [[] for _ in range(qd)]
    fds = [os.open(file_path, os.O_RDONLY) for _ in range(qd)]
    start_barrier = threading.Barrier(qd)

    # Global inter-launch pacer. The lock protects only the claim of a launch
    # slot; it is released before any wait and long before preadv() is entered.
    launch_lock = threading.Lock()
    last_launch_ns = [0]

    def _gate_launch() -> int:
        while True:
            with launch_lock:
                now = int(clock_ns())
                elapsed = now - last_launch_ns[0]
                if elapsed >= min_launch_gap_ns:
                    last_launch_ns[0] = now
                    return now
                remaining = min_launch_gap_ns - elapsed
            time.sleep(min(remaining / 1e9, 0.001))

    def _worker(worker_id: int, first_block: int, count: int) -> None:
        fd = fds[worker_id]
        view = views[worker_id]
        previous_exit: int | None = None
        start_barrier.wait()
        for step in range(count):
            block_index = first_block + step
            offset = block_index * read_bytes
            length = min(read_bytes, file_size - offset)
            target = view if length == read_bytes else view[:length]
            claim = _gate_launch()
            enter = int(clock_ns())
            try:
                got = int(preadv(fd, [target], offset))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            records[worker_id].append({
                "worker": worker_id,
                "block_index": block_index,
                "offset": offset,
                "length": length,
                "bytes_returned": got,
                "gate_claim_ns": claim,
                "preadv_enter_ns": enter,
                "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6,
                "refill_gap_ms": (
                    None if previous_exit is None else (enter - previous_exit) / 1e6
                ),
            })
            previous_exit = exit_ns

    threads = [
        threading.Thread(target=_worker, args=assignment) for assignment in assignments
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for fd in fds:
        os.close(fd)

    flat = [record for group in records for record in group]
    durations = [record["preadv_ms"] for record in flat]
    useful_bytes = sum(
        record["bytes_returned"] for record in flat if record["bytes_returned"] > 0
    )
    covered_bytes = sum(record["length"] for record in flat)
    first_enter = min(record["preadv_enter_ns"] for record in flat)
    last_exit = max(record["preadv_exit_ns"] for record in flat)
    wall_ms = (last_exit - first_enter) / 1e6
    wall_seconds = wall_ms / 1000.0

    gaps = [r["refill_gap_ms"] for r in flat if r["refill_gap_ms"] is not None]

    events: list[tuple[int, int]] = []
    for record in flat:
        events.append((record["preadv_enter_ns"], 1))
        events.append((record["preadv_exit_ns"], -1))
    events.sort()
    worker_first = [min(r["preadv_enter_ns"] for r in g) for g in records if g]
    worker_last = [max(r["preadv_exit_ns"] for r in g) for g in records if g]
    span_start = max(worker_first) if worker_first else None
    span_end = min(worker_last) if worker_last else None
    concurrent = 0
    max_in_span: int | None = None
    min_in_span: int | None = None
    if span_start is not None and span_end is not None and span_end > span_start:
        for timestamp, delta in events:
            concurrent += delta
            if span_start <= timestamp <= span_end:
                max_in_span = concurrent if max_in_span is None else max(max_in_span, concurrent)
                min_in_span = concurrent if min_in_span is None else min(min_in_span, concurrent)

    def _group(subset: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not subset:
            return None
        group_bytes = sum(r["bytes_returned"] for r in subset if r["bytes_returned"] > 0)
        group_enter = min(r["preadv_enter_ns"] for r in subset)
        group_exit = max(r["preadv_exit_ns"] for r in subset)
        group_span_ms = (group_exit - group_enter) / 1e6
        group_durations = [r["preadv_ms"] for r in subset]
        return {
            "reads": len(subset),
            "useful_bytes": group_bytes,
            "span_ms": group_span_ms,
            "decimal_gbps": (
                (group_bytes / (group_span_ms / 1000.0) / 1e9) if group_span_ms else None
            ),
            "mean_ms": statistics.fmean(group_durations),
            "median_ms": percentile(group_durations, 50),
            "max_ms": max(group_durations),
        }

    by_enter = sorted(flat, key=lambda r: r["preadv_enter_ns"])
    quarter_edges = [
        file_size * 1 // 4,
        file_size * 2 // 4,
        file_size * 3 // 4,
        file_size,
    ]
    progress = {
        "first_read": _group(by_enter[:1]),
        "first_4_reads": _group(by_enter[:4]),
        "first_1gib": _group([r for r in flat if r["offset"] < 1024 ** 3]),
        "quarter_1": _group([r for r in flat if r["offset"] < quarter_edges[0]]),
        "quarter_2": _group([r for r in flat if quarter_edges[0] <= r["offset"] < quarter_edges[1]]),
        "quarter_3": _group([r for r in flat if quarter_edges[1] <= r["offset"] < quarter_edges[2]]),
        "quarter_4": _group([r for r in flat if r["offset"] >= quarter_edges[2]]),
    }

    thresholds = {
        f"ge_{t}": sum(1 for d in durations if d >= t) for t in (100, 250, 500, 1000)
    }

    # ---- launch-spacing / overlap telemetry --------------------------------
    starts = [r["preadv_enter_ns"] for r in by_enter]
    inter_start_ms = [
        (starts[i + 1] - starts[i]) / 1e6 for i in range(len(starts) - 1)
    ]
    active_at_enter = [
        sum(
            1 for other in by_enter
            if other is not r
            and other["preadv_enter_ns"] < r["preadv_enter_ns"] < other["preadv_exit_ns"]
        )
        for r in by_enter
    ]
    span_ns = last_exit - first_enter
    busy_ns = sum(r["preadv_exit_ns"] - r["preadv_enter_ns"] for r in by_enter)
    launch_spacing = {
        "configured_min_gap_ms": min_launch_gap_ns / 1e6,
        "observed_min_inter_start_ms": min(inter_start_ms) if inter_start_ms else None,
        "observed_p5_inter_start_ms": percentile(inter_start_ms, 5) if inter_start_ms else None,
        "observed_median_inter_start_ms": percentile(inter_start_ms, 50) if inter_start_ms else None,
        "observed_p95_inter_start_ms": percentile(inter_start_ms, 95) if inter_start_ms else None,
        "observed_max_inter_start_ms": max(inter_start_ms) if inter_start_ms else None,
        "frac_entered_with_other_active": (
            sum(1 for a in active_at_enter if a >= 1) / len(active_at_enter)
            if active_at_enter else None
        ),
        "active_at_enter_mean": (
            statistics.fmean(active_at_enter) if active_at_enter else None
        ),
        "active_at_enter_max": max(active_at_enter) if active_at_enter else None,
        "mean_effective_concurrency": (busy_ns / span_ns) if span_ns > 0 else None,
        "max_simultaneous_in_flight": max_in_span,
    }
    generation_stats: dict[str, Any] = {}
    for gen in (0, 1, 2, 3, 4):
        subset = [group[gen] for group in records if len(group) > gen]
        if not subset:
            continue
        durs = [r["preadv_ms"] for r in subset]
        generation_stats[f"g{gen}"] = {
            "n": len(subset),
            "mean_ms": statistics.fmean(durs),
            "median_ms": percentile(durs, 50),
            "max_ms": max(durs),
            "ge_250": sum(1 for d in durs if d >= 250),
            "ge_500": sum(1 for d in durs if d >= 500),
            "ge_1000": sum(1 for d in durs if d >= 1000),
        }
    first_launches = [
        {
            "ordinal": i,
            "worker": r["worker"],
            "block_index": r["block_index"],
            "t_rel_ms": (r["preadv_enter_ns"] - first_enter) / 1e6,
            "gap_from_previous_ms": (
                None if i == 0
                else (r["preadv_enter_ns"] - by_enter[i - 1]["preadv_enter_ns"]) / 1e6
            ),
            "preadv_ms": r["preadv_ms"],
            "active_at_enter": active_at_enter[i],
        }
        for i, r in enumerate(by_enter[:4])
    ]

    return {
        "schema_version": 1,
        "kind": "fullfile_probe",
        "config": {
            "file_path": file_path,
            "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024,
            "qd": qd,
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {
            "platform": platform.system(),
            "syscall_impl": "os.preadv",
            "preadv_available": callable(getattr(os, "preadv", None)),
        },
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "physical_reads": len(flat),
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": (useful_bytes / wall_seconds / 1e9) if wall_seconds else None,
        "full_file_gib_per_s": (
            (useful_bytes / wall_seconds / (1024 ** 3)) if wall_seconds else None
        ),
        "mean_ms": statistics.fmean(durations),
        "median_ms": percentile(durations, 50),
        "p90_ms": percentile(durations, 90),
        "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99),
        "max_ms": max(durations),
        "min_ms": min(durations),
        "thresholds": thresholds,
        "median_refill_gap_ms": percentile(gaps, 50) if gaps else None,
        "max_refill_gap_ms": max(gaps) if gaps else None,
        "effective_qd_span_ms": (
            (span_end - span_start) / 1e6
            if span_start is not None and span_end is not None else None
        ),
        "effective_qd_max_in_span": max_in_span,
        "effective_qd_min_in_span": min_in_span,
        "effective_qd_fell_below_qd": bool(min_in_span is not None and min_in_span < qd),
        "worker_partitions": [
            {"worker": worker_id, "first_block": first_block, "blocks": count}
            for worker_id, first_block, count in assignments
        ],
        "coverage": {
            "covers_entire_file_exactly_once": bool(
                covered_bytes == file_size
                and sum(count for _, _, count in assignments) == total_blocks
                and all(
                    assignments[i][1] + assignments[i][2] == assignments[i + 1][1]
                    for i in range(len(assignments) - 1)
                )
            ),
            "ranges_non_overlapping": all(count > 0 for _, _, count in assignments),
            "final_block_is_partial": bool(file_size % read_bytes != 0),
            "all_reads_full_except_final": all(
                r["bytes_returned"] == r["length"] for r in flat
            ),
        },
        "progress": progress,
        "launch_spacing": launch_spacing,
        "generation_stats": generation_stats,
        "first_launches": first_launches,
        "reads": flat,
    }


# ==========================================================================
# Worker-model discriminator: four reader THREADS in one process vs four
# independent one-reader PROCESSES.  Matched QD4 / 64 MiB / 4 ms pacer.
#
# The single treatment variable is the worker model.  File, block size,
# worker count, one-FD-per-worker, one-buffer-per-worker, static contiguous
# range partitioning, read order, the GLOBAL launch pacer, correctness checks
# and telemetry all come from shared code used by both arms.
#
# The pacer primitive is deliberately identical in both arms: one
# process-shared lock plus one process-shared monotonic last-launch
# timestamp, both built from the same ``multiprocessing`` context.  The lock
# guards only the claim of a launch slot; it is released before any sleep and
# long before ``os.preadv`` is entered, so the syscall never overlaps the
# lock and reads spaced closer than their duration still overlap freely.
#
# Worker preparation deliberately does NOT touch payload bytes: buffers are
# allocated empty and FDs are opened, then every worker parks on the ready
# barrier.  The timed region starts at release of the start barrier, so
# process/thread creation latency is excluded from the source wall.
# ==========================================================================

_MW_WORKER_MODELS = ("threads", "processes")


def _mw_gate_launch(pacer_lock, last_launch_ns, min_launch_gap_ns: int, clock_ns):
    """Claim the next GLOBAL launch slot.

    Returns ``(claim_ns, wait_ns, hold_ns)``.  ``wait_ns`` is total time spent
    in the gate (including required spacing sleeps); ``hold_ns`` is how long
    the shared pacer lock was actually held, i.e. the pacer's own control cost.
    """
    entered = int(clock_ns())
    while True:
        with pacer_lock:
            now = int(clock_ns())
            elapsed = now - int(last_launch_ns.value)
            if elapsed >= min_launch_gap_ns:
                last_launch_ns.value = now
                hold_ns = int(clock_ns()) - now
                return now, now - entered, hold_ns
            remaining = min_launch_gap_ns - elapsed
        time.sleep(min(remaining / 1e9, 0.001))


def _mw_read_region(
    *,
    worker_id: int,
    fd: int,
    view: memoryview,
    read_bytes: int,
    first_block: int,
    count: int,
    file_size: int,
    clock_ns,
    last_launch_ns,
    min_launch_gap_ns: int,
) -> list[dict[str, Any]]:
    """Read one worker's static contiguous region behind the global pacer.

    Between the timed release and the last read's exit nothing happens except
    the launch gate and ``os.preadv`` itself -- no per-read IPC anywhere.
    """
    pacer_lock = last_launch_ns.get_lock()
    preadv_fn = getattr(os, "preadv", None)
    if not callable(preadv_fn):
        raise RuntimeError("os.preadv unavailable")
    preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)
    pid = os.getpid()
    tid = threading.get_native_id()
    records: list[dict[str, Any]] = []
    previous_exit: int | None = None
    for step in range(count):
        block_index = first_block + step
        offset = block_index * read_bytes
        length = min(read_bytes, file_size - offset)
        target = view if length == read_bytes else view[:length]
        claim, wait_ns, hold_ns = _mw_gate_launch(
            pacer_lock, last_launch_ns, min_launch_gap_ns, clock_ns
        )
        enter = int(clock_ns())
        try:
            got = int(preadv(fd, [target], offset))
        except BaseException:
            got = -1
        exit_ns = int(clock_ns())
        records.append({
            "worker": worker_id,
            "pid": pid,
            "tid": tid,
            "generation": step,
            "block_index": block_index,
            "offset": offset,
            "length": length,
            "bytes_returned": got,
            "gate_claim_ns": claim,
            "preadv_enter_ns": enter,
            "preadv_exit_ns": exit_ns,
            "preadv_ms": (exit_ns - enter) / 1e6,
            "gate_wait_ms": wait_ns / 1e6,
            "pacer_lock_hold_us": hold_ns / 1e3,
            "refill_gap_ms": (
                None if previous_exit is None else (enter - previous_exit) / 1e6
            ),
        })
        previous_exit = exit_ns
    return records


def _mw_reader_child(args: tuple) -> None:
    """One-reader process body.  CUDA-sterile: os.open, os.preadv, timing only.

    The compact timing records are sent back exactly ONCE, after the read
    workload has finished.  No payload bytes and no per-read IPC cross the
    pipe; only ~30 small record dicts per worker.
    """
    (worker_id, file_path, read_bytes, first_block, count, file_size,
     ready_barrier, start_barrier, last_launch_ns,
     min_launch_gap_ns, ready_timeout_s, child_conn) = args
    payload: dict[str, Any] = {
        "worker": worker_id, "pid": os.getpid(), "status": "ok", "records": [],
    }
    fd = -1
    try:
        buffer = bytearray(read_bytes)
        view = memoryview(buffer)
        fd = os.open(file_path, os.O_RDONLY)
        ready_barrier.wait(ready_timeout_s)
        start_barrier.wait(ready_timeout_s)
        payload["records"] = _mw_read_region(
            worker_id=worker_id,
            fd=fd,
            view=view,
            read_bytes=read_bytes,
            first_block=first_block,
            count=count,
            file_size=file_size,
            clock_ns=time.perf_counter_ns,
            last_launch_ns=last_launch_ns,
            min_launch_gap_ns=min_launch_gap_ns,
        )
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_worker_model_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int,
    worker_model: str,
    min_launch_gap_ns: int = 0,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    pacer_start_method: str = "fork",
) -> dict:
    """One full-file pass with ``qd`` workers under a chosen worker model.

    ``worker_model="threads"`` gives one process with ``qd`` reader threads;
    ``worker_model="processes"`` gives ``qd`` independent one-reader processes.
    Both arms share the identical geometry, pacer primitive and telemetry.
    """
    import multiprocessing as mp  # noqa: PLC0415

    worker_model = str(worker_model).strip().lower()
    if worker_model not in _MW_WORKER_MODELS:
        raise ValueError(f"worker_model must be one of {_MW_WORKER_MODELS}")
    if not callable(getattr(os, "preadv", None)):
        raise RuntimeError("os.preadv unavailable")
    if read_bytes < 1:
        raise ValueError("read_bytes must be positive")
    if qd < 1:
        raise ValueError("qd must be positive")
    if min_launch_gap_ns < 0:
        raise ValueError("min_launch_gap_ns must be non-negative")
    if pacer_start_method not in mp.get_all_start_methods():
        raise RuntimeError(f"start_method_unavailable:{pacer_start_method}")

    clock_ns = clock_ns or time.perf_counter_ns

    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path,
        "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    total_blocks = (file_size + read_bytes - 1) // read_bytes
    base, extra = divmod(total_blocks, qd)
    assignments: list[tuple[int, int, int]] = []
    block_cursor = 0
    for worker_id in range(qd):
        count = base + (1 if worker_id < extra else 0)
        assignments.append((worker_id, block_cursor, count))
        block_cursor += count

    expected_bytes = sum(
        min(read_bytes, file_size - block_index * read_bytes)
        for _, first_block, count in assignments
        for block_index in range(first_block, first_block + count)
    )

    # One pacer primitive, built identically for both arms: a single
    # process-shared monotonic timestamp whose own lock is the launch gate.
    pacer_ctx = mp.get_context(pacer_start_method)
    ready_barrier = pacer_ctx.Barrier(qd + 1)
    start_barrier = pacer_ctx.Barrier(qd + 1)
    last_launch_ns = pacer_ctx.Value("q", 0)

    payloads: list[dict[str, Any]] = [
        {"worker": w, "pid": None, "status": "ok", "records": []} for w in range(qd)
    ]
    keepalive: list[Any] = [None] * qd

    def _thread_body(worker_id: int, first_block: int, count: int) -> None:
        payload: dict[str, Any] = {
            "worker": worker_id, "pid": os.getpid(), "status": "ok", "records": [],
        }
        fd = -1
        try:
            buffer = bytearray(read_bytes)
            view = memoryview(buffer)
            keepalive[worker_id] = buffer
            fd = os.open(file_path, os.O_RDONLY)
            ready_barrier.wait(ready_timeout_s)
            start_barrier.wait(ready_timeout_s)
            payload["records"] = _mw_read_region(
                worker_id=worker_id,
                fd=fd,
                view=view,
                read_bytes=read_bytes,
                first_block=first_block,
                count=count,
                file_size=file_size,
                clock_ns=clock_ns,
                last_launch_ns=last_launch_ns,
                min_launch_gap_ns=min_launch_gap_ns,
            )
        except BaseException as exc:  # noqa: BLE001
            payload["status"] = "error"
            payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
        finally:
            try:
                if fd >= 0:
                    os.close(fd)
            except BaseException:  # noqa: BLE001
                pass
        payloads[worker_id] = payload

    spawn_start_ns = int(clock_ns())
    conns: list[tuple[int, Any]] = []
    procs: list[Any] = []
    threads: list[Any] = []

    if worker_model == "threads":
        threads = [
            threading.Thread(target=_thread_body, args=assignment)  # type: ignore[arg-type]
            for assignment in assignments
        ]
        for thread in threads:
            thread.start()
    else:
        for worker_id, first_block, count in assignments:
            parent_conn, child_conn = pacer_ctx.Pipe(duplex=False)
            proc = cast(Any, pacer_ctx).Process(
                target=_mw_reader_child,
                args=(
                    (worker_id, file_path, read_bytes, first_block, count, file_size,
                     ready_barrier, start_barrier, last_launch_ns,
                     min_launch_gap_ns, ready_timeout_s, child_conn),
                ),
                daemon=True,
            )
            proc.start()
            child_conn.close()
            conns.append((worker_id, parent_conn))
            procs.append(proc)

    barrier_error: str | None = None
    ready_ns: int | None = None
    release_ns: int | None = None
    try:
        ready_barrier.wait(ready_timeout_s)
        ready_ns = int(clock_ns())
        start_barrier.wait(ready_timeout_s)
        release_ns = int(clock_ns())
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    if worker_model == "threads":
        for thread in threads:
            thread.join()
    else:
        for worker_id, parent_conn in conns:
            try:
                payloads[worker_id] = parent_conn.recv()
            except BaseException as exc:  # noqa: BLE001
                payloads[worker_id] = {
                    "worker": worker_id, "pid": None, "status": "error",
                    "error": f"recv_failed:{type(exc).__name__}", "records": [],
                }
        for proc in procs:
            proc.join()
        for _, parent_conn in conns:
            parent_conn.close()

    worker_errors = [
        {"worker": p.get("worker"), "error": p.get("error")}
        for p in payloads if p.get("status") != "ok"
    ]
    per_worker_records = [list(p.get("records") or []) for p in payloads]
    flat = [record for group in per_worker_records for record in group]
    if not flat:
        raise RuntimeError(f"no_records:{barrier_error or 'workers_failed'}")

    durations = [r["preadv_ms"] for r in flat]
    useful_bytes = sum(r["bytes_returned"] for r in flat if r["bytes_returned"] > 0)
    first_enter = min(r["preadv_enter_ns"] for r in flat)
    last_exit = max(r["preadv_exit_ns"] for r in flat)
    wall_ms = (last_exit - first_enter) / 1e6
    wall_seconds = wall_ms / 1000.0

    by_enter = sorted(flat, key=lambda r: r["preadv_enter_ns"])
    for index, record in enumerate(by_enter):
        record["global_launch_gap_ms"] = (
            None if index == 0
            else (record["preadv_enter_ns"] - by_enter[index - 1]["preadv_enter_ns"]) / 1e6
        )
        record["active_at_enter"] = sum(
            1 for other in by_enter
            if other is not record
            and other["preadv_enter_ns"] < record["preadv_enter_ns"] < other["preadv_exit_ns"]
        )

    global_gaps = [
        r["global_launch_gap_ms"] for r in by_enter if r["global_launch_gap_ms"] is not None
    ]
    # The pacer gates the CLAIM, and ``preadv_enter_ns`` is a later clock read,
    # so enter-to-enter gaps can land a hair below the configured floor.  The
    # claim-to-claim gap is the quantity the gate actually guarantees.
    by_claim = sorted(flat, key=lambda r: r["gate_claim_ns"])
    claim_gaps = [
        (by_claim[i]["gate_claim_ns"] - by_claim[i - 1]["gate_claim_ns"]) / 1e6
        for i in range(1, len(by_claim))
    ]
    gate_waits = [r["gate_wait_ms"] for r in flat]
    lock_holds = [r["pacer_lock_hold_us"] for r in flat]
    active_at_enter = [r["active_at_enter"] for r in by_enter]

    events: list[tuple[int, int]] = []
    for record in flat:
        events.append((record["preadv_enter_ns"], 1))
        events.append((record["preadv_exit_ns"], -1))
    events.sort()
    concurrent = 0
    max_in_flight = 0
    for _, delta in events:
        concurrent += delta
        max_in_flight = max(max_in_flight, concurrent)

    span_ns = last_exit - first_enter
    busy_ns = sum(r["preadv_exit_ns"] - r["preadv_enter_ns"] for r in flat)

    worker_stats: list[dict[str, Any]] = []
    for worker_id, first_block, count in assignments:
        group = per_worker_records[worker_id]
        entry: dict[str, Any] = {
            "worker": worker_id,
            "first_block": first_block,
            "blocks": count,
            "reads": len(group),
            "pid": payloads[worker_id].get("pid"),
            "status": payloads[worker_id].get("status"),
        }
        if group:
            group_durations = [r["preadv_ms"] for r in group]
            group_first = min(r["preadv_enter_ns"] for r in group)
            group_last = max(r["preadv_exit_ns"] for r in group)
            entry.update({
                "bytes": sum(r["bytes_returned"] for r in group if r["bytes_returned"] > 0),
                "source_wall_ms": (group_last - group_first) / 1e6,
                "mean_preadv_ms": statistics.fmean(group_durations),
                "median_preadv_ms": percentile(group_durations, 50),
                "worst_preadv_ms": max(group_durations),
                "first_enter_ns": group_first,
                "last_exit_ns": group_last,
            })
        worker_stats.append(entry)

    worker_last = [w["last_exit_ns"] for w in worker_stats if "last_exit_ns" in w]
    completion_spread_ms = (
        (max(worker_last) - min(worker_last)) / 1e6 if len(worker_last) > 1 else None
    )

    ordered = sorted(flat, key=lambda r: (r["offset"], r["length"]))
    no_overlap = all(
        ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
        for i in range(len(ordered) - 1)
    )
    contiguous = all(
        ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
        for i in range(len(ordered) - 1)
    )
    completed_bytes = sum(r["bytes_returned"] for r in flat if r["bytes_returned"] > 0)

    thresholds = {
        f"ge_{t}": sum(1 for d in durations if d >= t)
        for t in (100, 150, 250, 500, 1000)
    }

    worker_pids = sorted({int(r["pid"]) for r in flat if r.get("pid") is not None})
    worker_tids = sorted({int(r["tid"]) for r in flat if r.get("tid") is not None})

    return {
        "schema_version": 1,
        "kind": "worker_model_probe",
        "config": {
            "file_path": file_path,
            "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024,
            "qd": qd,
            "worker_model": worker_model,
            "pacer_start_method": pacer_start_method,
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {
            "platform": platform.system(),
            "syscall_impl": "os.preadv",
            "multiprocessing_start_method": pacer_ctx.get_start_method(),
            "pacer_primitive": (
                "multiprocessing.Value('q').get_lock() shared by both arms"
            ),
        },
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": worker_model,
        "parent_pid": os.getpid(),
        "worker_pids": worker_pids,
        "worker_tids": worker_tids,
        "process_spawn_to_all_ready_ms": (
            (ready_ns - spawn_start_ns) / 1e6 if ready_ns is not None else None
        ),
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": worker_errors,
        "physical_reads": len(flat),
        "useful_bytes": useful_bytes,
        "covered_bytes": sum(r["length"] for r in flat),
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": (useful_bytes / wall_seconds / 1e9) if wall_seconds else None,
        "min_ms": min(durations),
        "p10_ms": percentile(durations, 10),
        "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations),
        "p90_ms": percentile(durations, 90),
        "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99),
        "max_ms": max(durations),
        "std_ms": statistics.pstdev(durations) if len(durations) > 1 else 0.0,
        "thresholds": thresholds,
        "coverage": {
            "expected_bytes": expected_bytes,
            "completed_bytes": completed_bytes,
            "file_size": file_size,
            "bytes_match": completed_bytes == expected_bytes == file_size,
            "reads_expected": total_blocks,
            "reads_completed": len(flat),
            "all_reads_returned_full_length": all(
                r["bytes_returned"] == r["length"] for r in flat
            ),
            "no_overlap": no_overlap,
            "contiguous_cover": contiguous,
            "first_offset": ordered[0]["offset"] if ordered else None,
            "last_end_offset": (
                ordered[-1]["offset"] + ordered[-1]["length"] if ordered else None
            ),
            "all_workers_completed_region": all(
                len(per_worker_records[wid]) == count for wid, _fb, count in assignments
            ),
            "covers_entire_file_exactly_once": bool(
                completed_bytes == expected_bytes
                and completed_bytes == file_size
                and len(flat) == total_blocks
                and no_overlap
                and contiguous
                and all(len(per_worker_records[wid]) == count for wid, _fb, count in assignments)
            ),
        },
        "worker_partitions": [
            {"worker": worker_id, "first_block": first_block, "blocks": count}
            for worker_id, first_block, count in assignments
        ],
        "worker_stats": worker_stats,
        "final_worker_completion_spread_ms": completion_spread_ms,
        "pacer": {
            "configured_min_gap_ms": min_launch_gap_ns / 1e6,
            "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "observed_p10_global_claim_gap_ms": (
                percentile(claim_gaps, 10) if claim_gaps else None
            ),
            "observed_median_global_claim_gap_ms": (
                percentile(claim_gaps, 50) if claim_gaps else None
            ),
            "observed_p95_global_claim_gap_ms": (
                percentile(claim_gaps, 95) if claim_gaps else None
            ),
            "observed_min_global_gap_ms": min(global_gaps) if global_gaps else None,
            "observed_p10_global_gap_ms": percentile(global_gaps, 10) if global_gaps else None,
            "observed_median_global_gap_ms": (
                percentile(global_gaps, 50) if global_gaps else None
            ),
            "observed_p95_global_gap_ms": percentile(global_gaps, 95) if global_gaps else None,
            "gate_wait_mean_ms": statistics.fmean(gate_waits) if gate_waits else None,
            "gate_wait_median_ms": percentile(gate_waits, 50) if gate_waits else None,
            "gate_wait_max_ms": max(gate_waits) if gate_waits else None,
            "gate_wait_total_ms": sum(gate_waits),
            "lock_hold_mean_us": statistics.fmean(lock_holds) if lock_holds else None,
            "lock_hold_median_us": percentile(lock_holds, 50) if lock_holds else None,
            "lock_hold_max_us": max(lock_holds) if lock_holds else None,
        },
        "launch_spacing": {
            "configured_min_gap_ms": min_launch_gap_ns / 1e6,
            "observed_min_inter_start_ms": min(global_gaps) if global_gaps else None,
            "observed_p5_inter_start_ms": (
                percentile(global_gaps, 5) if global_gaps else None
            ),
            "observed_median_inter_start_ms": (
                percentile(global_gaps, 50) if global_gaps else None
            ),
            "observed_p95_inter_start_ms": (
                percentile(global_gaps, 95) if global_gaps else None
            ),
            "observed_max_inter_start_ms": max(global_gaps) if global_gaps else None,
            "frac_entered_with_other_active": (
                sum(1 for a in active_at_enter if a >= 1) / len(active_at_enter)
                if active_at_enter else None
            ),
            "active_at_enter_mean": (
                statistics.fmean(active_at_enter) if active_at_enter else None
            ),
            "active_at_enter_max": max(active_at_enter) if active_at_enter else None,
            "mean_effective_concurrency": (busy_ns / span_ns) if span_ns > 0 else None,
            "max_simultaneous_in_flight": max_in_flight,
            "effective_qd_span_ms": (span_ns / 1e6) if span_ns else None,
        },
        "reads": flat,
    }


# ==========================================================================
# Hedged variant of the PROCESS architecture.
#
# Geometry is unchanged: qd reader processes, one static contiguous region
# each, one original FD + one original 64 MiB buffer each, one global
# process-shared pacer gating every physical attempt (originals AND hedges).
#
# A hedge is a duplicate read of the SAME block on a DIFFERENT FD and a
# different buffer, launched only after ``hedge_delay_ns`` elapses without the
# original completing.  os.preadv is a blocking syscall with no cancellation,
# so the original must be issued by a helper thread for the coordinator to be
# able to return as soon as a hedge wins.
#
# The coordinator still waits for every loser of the block it just finished:
# the original is writing into the buffer the next block needs.  This is the
# known loser-staleness constraint and it is recorded, not hidden.
# ==========================================================================


def _mw_hedge_child(args: tuple) -> None:
    """One hedged reader process: static region, helper thread per attempt."""
    (worker_id, file_path, read_bytes, first_block, count, file_size,
     ready_barrier, start_barrier, last_launch_ns, min_launch_gap_ns,
     hedge_delay_ns, hedge_slots, ready_timeout_s, child_conn) = args
    payload: dict[str, Any] = {
        "worker": worker_id, "pid": os.getpid(), "status": "ok",
        "logical": [], "physical": [],
    }
    opened: list[int] = []
    try:
        preadv_fn = getattr(os, "preadv", None)
        if not callable(preadv_fn):
            raise RuntimeError("os.preadv unavailable")
        preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)

        buffer = bytearray(read_bytes)
        view = memoryview(buffer)
        fd = os.open(file_path, os.O_RDONLY)
        opened.append(fd)
        hedge_buffers = [bytearray(read_bytes) for _ in range(hedge_slots)]
        hedge_views = [memoryview(b) for b in hedge_buffers]
        hedge_fds: list[int] = []
        for _ in range(hedge_slots):
            hfd = os.open(file_path, os.O_RDONLY)
            hedge_fds.append(hfd)
            opened.append(hfd)

        ready_barrier.wait(ready_timeout_s)
        start_barrier.wait(ready_timeout_s)
        pacer_lock = last_launch_ns.get_lock()

        # Canary: a pure-timing thread that performs no I/O and holds no lock.
        # If its ticks stop while the original is inside preadv, the whole
        # process was frozen (case A).  If they continue, any hedge delay is
        # caused by our own synchronization (case B).
        canary_ticks: list[int] = []
        canary_tid_box = [0]
        canary_stop = threading.Event()

        def _canary() -> None:
            canary_tid_box[0] = threading.get_native_id()
            while not canary_stop.is_set():
                canary_ticks.append(int(time.perf_counter_ns()))
                canary_stop.wait(0.010)

        canary_thread = threading.Thread(target=_canary, daemon=True)
        canary_thread.start()

        trace: list[dict[str, Any]] = []
        for step in range(count):
            block_index = first_block + step
            offset = block_index * read_bytes
            length = min(read_bytes, file_size - offset)
            target = view if length == read_bytes else view[:length]

            state: dict[str, Any] = {"winner": None, "hedges": 0}
            lock = threading.Lock()
            done = threading.Event()

            def _attempt(kind: str, afd: int, atarget: memoryview, delay_ns: int) -> None:
                t_first = int(time.perf_counter_ns())
                tid = threading.get_native_id()
                if delay_ns > 0:
                    done.wait(delay_ns / 1e9)
                    if done.is_set():
                        return
                gate_enter = int(time.perf_counter_ns())
                claim, wait_ns, hold_ns = _mw_gate_launch(
                    pacer_lock, last_launch_ns, min_launch_gap_ns, time.perf_counter_ns
                )
                enter = int(time.perf_counter_ns())
                try:
                    got = int(preadv(afd, [atarget], offset))
                except BaseException:
                    got = -1
                exit_ns = int(time.perf_counter_ns())
                lock_wait_start = int(time.perf_counter_ns())
                with lock:
                    lock_acquired = int(time.perf_counter_ns())
                    if kind == "hedge":
                        state["hedges"] += 1
                    payload["physical"].append({
                        "worker": worker_id, "pid": os.getpid(), "tid": tid,
                        "block_index": block_index, "kind": kind,
                        "offset": offset, "length": length,
                        "thread_first_ns": t_first,
                        "gate_enter_ns": gate_enter,
                        "gate_claim_ns": claim,
                        "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                        "preadv_ms": (exit_ns - enter) / 1e6,
                        "gate_wait_ms": wait_ns / 1e6,
                        "lock_wait_ns": lock_acquired - lock_wait_start,
                        "bytes_returned": got,
                    })
                    if state["winner"] is None:
                        state["winner"] = {
                            "kind": kind, "tid": tid, "enter_ns": enter,
                            "exit_ns": exit_ns, "bytes": got,
                        }
                        done.set()

            t_block_start = int(time.perf_counter_ns())
            threads = [threading.Thread(
                target=_attempt, args=("original", fd, target, 0), daemon=True)]
            threads[0].start()
            t_after_orig_start = int(time.perf_counter_ns())
            timed_out = not done.wait(hedge_delay_ns / 1e9)
            t_timeout_return = int(time.perf_counter_ns())
            t_hedge_spawned: int | None = None
            if timed_out:
                for slot in range(hedge_slots):
                    thread = threading.Thread(
                        target=_attempt,
                        args=("hedge", hedge_fds[slot], hedge_views[slot], 0),
                        daemon=True,
                    )
                    threads.append(thread)
                    thread.start()
                t_hedge_spawned = int(time.perf_counter_ns())
            done.wait()
            t_winner_set = int(time.perf_counter_ns())
            for thread in threads:
                thread.join()

            winner = state["winner"] or {}
            payload["logical"].append({
                "worker": worker_id, "pid": os.getpid(), "generation": step,
                "block_index": block_index, "offset": offset, "length": length,
                "bytes_returned": winner.get("bytes"),
                "accepted": winner.get("kind"),
                "logical_enter_ns": winner.get("enter_ns"),
                "logical_exit_ns": winner.get("exit_ns"),
                "logical_ms": (
                    ((winner.get("exit_ns") or 0) - (winner.get("enter_ns") or 0)) / 1e6
                ),
                "hedges_launched": state["hedges"],
            })
            trace.append({
                "worker": worker_id, "pid": os.getpid(),
                "block_index": block_index,
                "hedge_delay_ns": hedge_delay_ns,
                "block_start_ns": t_block_start,
                "after_orig_thread_start_ns": t_after_orig_start,
                "timed_out": bool(timed_out),
                "timeout_return_ns": t_timeout_return,
                "hedge_threads_spawned_ns": t_hedge_spawned,
                "winner_set_ns": t_winner_set,
            })

        canary_stop.set()
        canary_thread.join(timeout=2.0)
        payload["trace"] = trace
        payload["canary_ticks"] = canary_ticks
        payload["canary_tid"] = canary_tid_box[0]
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        for handle in opened:
            try:
                os.close(handle)
            except BaseException:  # noqa: BLE001
                pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_worker_model_hedge_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int,
    hedge_delay_ns: int,
    hedge_slots_per_worker: int = 3,
    min_launch_gap_ns: int = 0,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    pacer_start_method: str = "fork",
) -> dict:
    """Full-file pass, qd reader processes, static regions, delayed hedging."""
    import multiprocessing as mp  # noqa: PLC0415

    if not callable(getattr(os, "preadv", None)):
        raise RuntimeError("os.preadv unavailable")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if min_launch_gap_ns < 0 or hedge_delay_ns < 0:
        raise ValueError("gap and hedge delay must be non-negative")
    if hedge_slots_per_worker < 0:
        raise ValueError("hedge_slots_per_worker must be non-negative")
    if pacer_start_method not in mp.get_all_start_methods():
        raise RuntimeError(f"start_method_unavailable:{pacer_start_method}")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path, "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    total_blocks = (file_size + read_bytes - 1) // read_bytes
    base, extra = divmod(total_blocks, qd)
    assignments: list[tuple[int, int, int]] = []
    cursor = 0
    for worker_id in range(qd):
        count = base + (1 if worker_id < extra else 0)
        assignments.append((worker_id, cursor, count))
        cursor += count
    expected_bytes = sum(
        min(read_bytes, file_size - block_index * read_bytes)
        for _, first_block, count in assignments
        for block_index in range(first_block, first_block + count)
    )

    pacer_ctx = mp.get_context(pacer_start_method)
    ready_barrier = pacer_ctx.Barrier(qd + 1)
    start_barrier = pacer_ctx.Barrier(qd + 1)
    last_launch_ns = pacer_ctx.Value("q", 0)

    payloads: list[dict[str, Any]] = [
        {"worker": w, "pid": None, "status": "ok", "logical": [], "physical": []}
        for w in range(qd)
    ]
    conns: list[tuple[int, Any]] = []
    procs: list[Any] = []
    spawn_start_ns = int(clock_ns())
    for worker_id, first_block, count in assignments:
        parent_conn, child_conn = pacer_ctx.Pipe(duplex=False)
        proc = cast(Any, pacer_ctx).Process(
            target=_mw_hedge_child,
            args=((worker_id, file_path, read_bytes, first_block, count, file_size,
                   ready_barrier, start_barrier, last_launch_ns, min_launch_gap_ns,
                   hedge_delay_ns, hedge_slots_per_worker, ready_timeout_s, child_conn),),
            daemon=True,
        )
        proc.start()
        child_conn.close()
        conns.append((worker_id, parent_conn))
        procs.append(proc)

    barrier_error: str | None = None
    ready_ns: int | None = None
    release_ns: int | None = None
    try:
        ready_barrier.wait(ready_timeout_s)
        ready_ns = int(clock_ns())
        start_barrier.wait(ready_timeout_s)
        release_ns = int(clock_ns())
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    for worker_id, parent_conn in conns:
        try:
            payloads[worker_id] = parent_conn.recv()
        except BaseException as exc:  # noqa: BLE001
            payloads[worker_id] = {
                "worker": worker_id, "pid": None, "status": "error",
                "error": f"recv_failed:{type(exc).__name__}",
                "logical": [], "physical": [],
            }
    for proc in procs:
        proc.join()
    for _, parent_conn in conns:
        parent_conn.close()

    worker_errors = [
        {"worker": p.get("worker"), "error": p.get("error")}
        for p in payloads if p.get("status") != "ok"
    ]
    per_worker_logical = [list(p.get("logical") or []) for p in payloads]
    per_worker_physical = [list(p.get("physical") or []) for p in payloads]
    logical = [r for group in per_worker_logical for r in group]
    physical = [r for group in per_worker_physical for r in group]
    if not logical:
        raise RuntimeError(f"no_logical_records:{barrier_error or 'workers_failed'}")

    durations = [r["logical_ms"] for r in logical]
    useful_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    first_enter = min(r["logical_enter_ns"] for r in logical if r["logical_enter_ns"])
    last_exit = max(r["logical_exit_ns"] for r in logical if r["logical_exit_ns"])
    wall_ms = (last_exit - first_enter) / 1e6
    wall_seconds = wall_ms / 1000.0

    by_enter = sorted(logical, key=lambda r: r["logical_enter_ns"])
    for index, record in enumerate(by_enter):
        record["global_launch_gap_ms"] = (
            None if index == 0
            else (record["logical_enter_ns"] - by_enter[index - 1]["logical_enter_ns"]) / 1e6
        )

    by_claim = sorted(physical, key=lambda r: r["gate_claim_ns"])
    phys_durations = [r["preadv_ms"] for r in physical]
    hedge_attempts = [r for r in physical if r["kind"] == "hedge"]
    hedge_wins = sum(1 for r in logical if r.get("accepted") == "hedge")
    blocks_with_hedge = sum(1 for r in logical if (r.get("hedges_launched") or 0) > 0)

    events: list[tuple[int, int]] = []
    for record in physical:
        events.append((record["preadv_enter_ns"], 1))
        events.append((record["preadv_exit_ns"], -1))
    events.sort()
    concurrent = 0
    max_in_flight = 0
    for _, delta in events:
        concurrent += delta
        max_in_flight = max(max_in_flight, concurrent)

    span_ns = last_exit - first_enter
    busy_ns = sum(r["preadv_exit_ns"] - r["preadv_enter_ns"] for r in physical)

    worker_stats: list[dict[str, Any]] = []
    for worker_id, first_block, count in assignments:
        group = per_worker_logical[worker_id]
        phys = per_worker_physical[worker_id]
        entry: dict[str, Any] = {
            "worker": worker_id, "first_block": first_block, "blocks": count,
            "reads": len(group), "pid": payloads[worker_id].get("pid"),
            "status": payloads[worker_id].get("status"),
        }
        if group:
            group_durations = [r["logical_ms"] for r in group]
            group_first = min(r["preadv_enter_ns"] for r in phys) if phys else min(
                r["logical_enter_ns"] for r in group)
            group_last = max(r["logical_exit_ns"] for r in group)
            entry.update({
                "bytes": sum(r["bytes_returned"] for r in group
                             if (r["bytes_returned"] or 0) > 0),
                "source_wall_ms": (group_last - group_first) / 1e6,
                "mean_preadv_ms": statistics.fmean(group_durations),
                "median_preadv_ms": percentile(group_durations, 50),
                "worst_preadv_ms": max(group_durations),
                "first_enter_ns": group_first,
                "last_exit_ns": group_last,
                "physical_attempts": len(phys),
                "hedges_launched": sum(1 for r in phys if r["kind"] == "hedge"),
            })
        worker_stats.append(entry)

    worker_last = [w["last_exit_ns"] for w in worker_stats if "last_exit_ns" in w]
    completion_spread_ms = (
        (max(worker_last) - min(worker_last)) / 1e6 if len(worker_last) > 1 else None
    )

    ordered = sorted(logical, key=lambda r: (r["offset"], r["length"]))
    no_overlap = all(
        ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
        for i in range(len(ordered) - 1)
    )
    contiguous = all(
        ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
        for i in range(len(ordered) - 1)
    )
    completed_bytes = sum(r["bytes_returned"] for r in logical
                          if (r["bytes_returned"] or 0) > 0)

    thresholds = {
        f"ge_{t}": sum(1 for d in durations if d >= t) for t in (100, 150, 250, 500, 1000)
    }

    return {
        "schema_version": 1,
        "kind": "worker_model_hedge_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "processes_hedged",
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "hedge_delay_ns": hedge_delay_ns,
            "hedge_delay_ms": hedge_delay_ns / 1e6,
            "hedge_slots_per_worker": hedge_slots_per_worker,
            "total_blocks": total_blocks,
        },
        "env": {
            "platform": platform.system(), "syscall_impl": "os.preadv",
            "multiprocessing_start_method": pacer_ctx.get_start_method(),
            "pacer_primitive": "multiprocessing.Value('q').get_lock() shared by all attempts",
        },
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "processes_hedged",
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in logical if r.get("pid") is not None}),
        "process_spawn_to_all_ready_ms": (
            (ready_ns - spawn_start_ns) / 1e6 if ready_ns is not None else None
        ),
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": worker_errors,
        "physical_reads": len(logical),
        "physical_attempts": len(physical),
        "hedge_attempts": len(hedge_attempts),
        "hedge_wins": hedge_wins,
        "blocks_with_hedge": blocks_with_hedge,
        "useful_bytes": useful_bytes,
        "covered_bytes": sum(r["length"] for r in logical),
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": (useful_bytes / wall_seconds / 1e9) if wall_seconds else None,
        "min_ms": min(durations),
        "p10_ms": percentile(durations, 10),
        "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations),
        "p90_ms": percentile(durations, 90),
        "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99),
        "max_ms": max(durations),
        "std_ms": statistics.pstdev(durations) if len(durations) > 1 else 0.0,
        "physical_median_ms": percentile(phys_durations, 50) if phys_durations else None,
        "physical_max_ms": max(phys_durations) if phys_durations else None,
        "thresholds": thresholds,
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "reads_expected": total_blocks, "reads_completed": len(logical),
            "all_reads_returned_full_length": all(
                r["bytes_returned"] == r["length"] for r in logical),
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "first_offset": ordered[0]["offset"] if ordered else None,
            "last_end_offset": (ordered[-1]["offset"] + ordered[-1]["length"]) if ordered else None,
            "all_workers_completed_region": all(
                len(per_worker_logical[wid]) == count for wid, _fb, count in assignments),
            "covers_entire_file_exactly_once": bool(
                completed_bytes == expected_bytes == file_size
                and len(logical) == total_blocks and no_overlap and contiguous
                and all(len(per_worker_logical[wid]) == count
                        for wid, _fb, count in assignments)),
        },
        "worker_partitions": [
            {"worker": worker_id, "first_block": first_block, "blocks": count}
            for worker_id, first_block, count in assignments
        ],
        "worker_stats": worker_stats,
        "final_worker_completion_spread_ms": completion_spread_ms,
        "pacer": {
            "configured_min_gap_ms": min_launch_gap_ns / 1e6,
            "observed_min_global_claim_gap_ms": (
                min((by_claim[i]["gate_claim_ns"] - by_claim[i - 1]["gate_claim_ns"]) / 1e6
                    for i in range(1, len(by_claim)))
                if len(by_claim) > 1 else None
            ),
        },
        "launch_spacing": {
            "mean_effective_concurrency": (busy_ns / span_ns) if span_ns > 0 else None,
            "max_simultaneous_in_flight": max_in_flight,
            "observed_min_inter_start_ms": min(
                (by_enter[i]["logical_enter_ns"] - by_enter[i - 1]["logical_enter_ns"]) / 1e6
                for i in range(1, len(by_enter))) if len(by_enter) > 1 else None,
            "observed_median_inter_start_ms": percentile(
                [r["global_launch_gap_ms"] for r in by_enter
                 if r["global_launch_gap_ms"] is not None], 50),
        },
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": physical,
        "hedge_trace": [t for p in payloads for t in (p.get("trace") or [])],
        "canary_ticks": {str(p.get("worker")): (p.get("canary_ticks") or []) for p in payloads},
        "canary_tid": {str(p.get("worker")): p.get("canary_tid") for p in payloads},
    }


# ==========================================================================
# Freeze-scope witnesses (Test 1).
#
# During the SAME pathological preadv we tick five independent witnesses:
#   1. Python canary thread inside every reader process (no I/O, no locks)
#   2. native pthread canary inside every reader process (no Python in the loop)
#   3. Python canary in an independent control process (never opens the model)
#   4. native pthread canary in that same control process
#   5. Python canary thread in the parent/coordinator process
#
# All five write monotonic timestamps only; no witness performs I/O or takes a
# lock, so a gap in a witness is evidence about scheduling, not about our code.
# Primary source architecture is unchanged: qd reader processes, static regions,
# 64 MiB reads, one global 4.0 ms pacer.  No hedging in this path.
# ==========================================================================


def _nc_load():
    """Load the prebuilt native canary library."""
    lib = ctypes.CDLL(_NATIVE_CANARY_SO)
    lib.nc_start.argtypes = [ctypes.c_void_p, ctypes.c_longlong, ctypes.c_longlong]
    lib.nc_start.restype = ctypes.c_longlong
    lib.nc_stop.restype = ctypes.c_longlong
    lib.nc_self_tid.restype = ctypes.c_longlong
    return lib


def _nc_decode(buf, capacity: int) -> list[int]:
    """Native canary records are sequential 16-byte (wall_ns, seq) pairs."""
    out: list[int] = []
    for index in range(capacity):
        wall, _seq = struct.unpack_from("<qq", buf, _NC_HDR_SIZE + index * _NC_USER_REC)
        if wall <= 0:
            break
        out.append(int(wall))
    return out


def _witness_reader_child(args: tuple) -> None:
    """One reader process: static region + Python canary + native canary."""
    (worker_id, file_path, read_bytes, first_block, count, file_size,
     ready_barrier, start_barrier, last_launch_ns, min_launch_gap_ns,
     ready_timeout_s, canary_capacity, canary_cadence_ns, child_conn) = args
    payload: dict[str, Any] = {
        "worker": worker_id, "pid": os.getpid(), "status": "ok",
        "reads": [], "py_ticks": [], "nc_ticks": [], "nc_tid": None,
    }
    opened: list[int] = []
    nc_buf = None
    nc_lib = None
    py_stop = threading.Event()
    py_thread = None
    try:
        preadv_fn = getattr(os, "preadv", None)
        if not callable(preadv_fn):
            raise RuntimeError("os.preadv unavailable")
        preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)

        buffer = bytearray(read_bytes)
        view = memoryview(buffer)
        fd = os.open(file_path, os.O_RDONLY)
        opened.append(fd)

        nc_buf = mmap.mmap(-1, _NC_HDR_SIZE + canary_capacity * _NC_USER_REC)
        nc_buf[0] = 0
        nc_lib = _nc_load()
        nc_addr = ctypes.addressof(ctypes.c_char.from_buffer(nc_buf))
        nc_lib.nc_start(nc_addr, canary_capacity, canary_cadence_ns)
        payload["nc_tid"] = int(nc_lib.nc_self_tid())

        ticks = payload["py_ticks"]

        def _py_canary() -> None:
            while not py_stop.is_set():
                ticks.append(int(time.perf_counter_ns()))
                py_stop.wait(canary_cadence_ns / 1e9)

        py_thread = threading.Thread(target=_py_canary, daemon=True)
        py_thread.start()

        ready_barrier.wait(ready_timeout_s)
        start_barrier.wait(ready_timeout_s)
        pacer_lock = last_launch_ns.get_lock()

        previous_exit: int | None = None
        for step in range(count):
            block_index = first_block + step
            offset = block_index * read_bytes
            length = min(read_bytes, file_size - offset)
            target = view if length == read_bytes else view[:length]
            claim, wait_ns, _hold = _mw_gate_launch(
                pacer_lock, last_launch_ns, min_launch_gap_ns, time.perf_counter_ns
            )
            enter = int(time.perf_counter_ns())
            try:
                got = int(preadv(fd, [target], offset))
            except BaseException:
                got = -1
            exit_ns = int(time.perf_counter_ns())
            payload["reads"].append({
                "worker": worker_id, "pid": os.getpid(),
                "generation": step, "block_index": block_index,
                "offset": offset, "length": length, "bytes_returned": got,
                "gate_claim_ns": claim, "preadv_enter_ns": enter,
                "preadv_exit_ns": exit_ns, "preadv_ms": (exit_ns - enter) / 1e6,
                "refill_gap_ms": (None if previous_exit is None
                                  else (enter - previous_exit) / 1e6),
            })
            previous_exit = exit_ns

        py_stop.set()
        py_thread.join(timeout=1.0)
        nc_lib.nc_stop()
        payload["nc_ticks"] = _nc_decode(nc_buf, canary_capacity)
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            py_stop.set()
            if py_thread is not None:
                py_thread.join(timeout=1.0)
        except BaseException:  # noqa: BLE001
            pass
        try:
            if nc_lib is not None:
                nc_lib.nc_stop()
        except BaseException:  # noqa: BLE001
            pass
        for handle in opened:
            try:
                os.close(handle)
            except BaseException:  # noqa: BLE001
                pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def _witness_control_child(args: tuple) -> None:
    """Independent control process: canaries only.  Never opens the model file."""
    (stop_value, ready_barrier, start_barrier, guard_ns,
     canary_capacity, canary_cadence_ns, child_conn) = args
    payload: dict[str, Any] = {
        "pid": os.getpid(), "status": "ok",
        "py_ticks": [], "nc_ticks": [], "nc_tid": None,
        "opened_model": False,
    }
    nc_buf = None
    nc_lib = None
    py_stop = threading.Event()
    py_thread = None
    try:
        nc_buf = mmap.mmap(-1, _NC_HDR_SIZE + canary_capacity * _NC_USER_REC)
        nc_buf[0] = 0
        nc_lib = _nc_load()
        nc_addr = ctypes.addressof(ctypes.c_char.from_buffer(nc_buf))
        nc_lib.nc_start(nc_addr, canary_capacity, canary_cadence_ns)
        payload["nc_tid"] = int(nc_lib.nc_self_tid())

        ticks = payload["py_ticks"]

        def _py_canary() -> None:
            while not py_stop.is_set():
                ticks.append(int(time.perf_counter_ns()))
                py_stop.wait(canary_cadence_ns / 1e9)

        py_thread = threading.Thread(target=_py_canary, daemon=True)
        py_thread.start()

        ready_barrier.wait(300.0)
        start_barrier.wait(300.0)
        deadline = time.perf_counter_ns() + guard_ns
        while stop_value.value == 0 and time.perf_counter_ns() < deadline:
            time.sleep(0.05)

        py_stop.set()
        py_thread.join(timeout=1.0)
        nc_lib.nc_stop()
        payload["nc_ticks"] = _nc_decode(nc_buf, canary_capacity)
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            py_stop.set()
            if py_thread is not None:
                py_thread.join(timeout=1.0)
        except BaseException:  # noqa: BLE001
            pass
        try:
            if nc_lib is not None:
                nc_lib.nc_stop()
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_worker_model_witness_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int,
    min_launch_gap_ns: int = 0,
    canary_cadence_ns: int = 10_000_000,
    canary_capacity: int = 20000,
    control_guard_ns: int = 300_000_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    pacer_start_method: str = "fork",
) -> dict:
    """QD reader pass with five independent freeze-scope witnesses (Test 1)."""
    import multiprocessing as mp  # noqa: PLC0415

    if not callable(getattr(os, "preadv", None)):
        raise RuntimeError("os.preadv unavailable")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if min_launch_gap_ns < 0:
        raise ValueError("min_launch_gap_ns must be non-negative")
    if pacer_start_method not in mp.get_all_start_methods():
        raise RuntimeError(f"start_method_unavailable:{pacer_start_method}")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path, "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    total_blocks = (file_size + read_bytes - 1) // read_bytes
    base, extra = divmod(total_blocks, qd)
    assignments: list[tuple[int, int, int]] = []
    cursor = 0
    for worker_id in range(qd):
        count = base + (1 if worker_id < extra else 0)
        assignments.append((worker_id, cursor, count))
        cursor += count
    expected_bytes = sum(
        min(read_bytes, file_size - block_index * read_bytes)
        for _, first_block, count in assignments
        for block_index in range(first_block, first_block + count)
    )

    pacer_ctx = mp.get_context(pacer_start_method)
    ready_barrier = pacer_ctx.Barrier(qd + 2)      # readers + control + parent
    start_barrier = pacer_ctx.Barrier(qd + 2)
    last_launch_ns = pacer_ctx.Value("q", 0)
    stop_value = pacer_ctx.Value("i", 0)

    # ---- parent/coordinator Python canary (witness 5) ----
    parent_ticks: list[int] = []
    parent_stop = threading.Event()

    def _parent_canary() -> None:
        while not parent_stop.is_set():
            parent_ticks.append(int(clock_ns()))
            parent_stop.wait(canary_cadence_ns / 1e9)

    parent_thread = threading.Thread(target=_parent_canary, daemon=True)
    parent_thread.start()

    reader_payloads: list[dict[str, Any]] = [
        {"worker": w, "status": "ok", "reads": [], "py_ticks": [], "nc_ticks": []}
        for w in range(qd)
    ]
    reader_conns: list[tuple[int, Any]] = []
    reader_procs: list[Any] = []
    spawn_start_ns = int(clock_ns())
    for worker_id, first_block, count in assignments:
        parent_conn, child_conn = pacer_ctx.Pipe(duplex=False)
        proc = cast(Any, pacer_ctx).Process(
            target=_witness_reader_child,
            args=((worker_id, file_path, read_bytes, first_block, count, file_size,
                   ready_barrier, start_barrier, last_launch_ns, min_launch_gap_ns,
                   ready_timeout_s, canary_capacity, canary_cadence_ns, child_conn),),
            daemon=True,
        )
        proc.start()
        child_conn.close()
        reader_conns.append((worker_id, parent_conn))
        reader_procs.append(proc)

    control_conn_parent, control_conn_child = pacer_ctx.Pipe(duplex=False)
    control_proc = cast(Any, pacer_ctx).Process(
        target=_witness_control_child,
        args=((stop_value, ready_barrier, start_barrier, control_guard_ns,
               canary_capacity, canary_cadence_ns, control_conn_child),),
        daemon=True,
    )
    control_proc.start()
    control_conn_child.close()

    barrier_error: str | None = None
    ready_ns: int | None = None
    release_ns: int | None = None
    try:
        ready_barrier.wait(ready_timeout_s)
        ready_ns = int(clock_ns())
        start_barrier.wait(ready_timeout_s)
        release_ns = int(clock_ns())
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    control_payload: dict[str, Any] = {"status": "ok", "py_ticks": [], "nc_ticks": []}
    for worker_id, parent_conn in reader_conns:
        try:
            reader_payloads[worker_id] = parent_conn.recv()
        except BaseException as exc:  # noqa: BLE001
            reader_payloads[worker_id] = {
                "worker": worker_id, "status": "error",
                "error": f"recv_failed:{type(exc).__name__}",
                "reads": [], "py_ticks": [], "nc_ticks": [],
            }
    stop_value.value = 1
    try:
        control_payload = control_conn_parent.recv()
    except BaseException as exc:  # noqa: BLE001
        control_payload = {"status": "error", "error": f"recv_failed:{type(exc).__name__}",
                           "py_ticks": [], "nc_ticks": []}
    for proc in reader_procs:
        proc.join()
    control_proc.join(timeout=30.0)
    for _, parent_conn in reader_conns:
        parent_conn.close()
    control_conn_parent.close()
    parent_stop.set()
    parent_thread.join(timeout=1.0)

    worker_errors = [
        {"worker": p.get("worker"), "error": p.get("error")}
        for p in reader_payloads if p.get("status") != "ok"
    ]
    reads = [r for p in reader_payloads for r in (p.get("reads") or [])]
    if not reads:
        raise RuntimeError(f"no_reads:{barrier_error or 'workers_failed'}")

    durations = [r["preadv_ms"] for r in reads]
    useful_bytes = sum(r["bytes_returned"] for r in reads if r["bytes_returned"] > 0)
    first_enter = min(r["preadv_enter_ns"] for r in reads)
    last_exit = max(r["preadv_exit_ns"] for r in reads)
    wall_ms = (last_exit - first_enter) / 1e6

    ordered = sorted(reads, key=lambda r: (r["offset"], r["length"]))
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    completed_bytes = sum(r["bytes_returned"] for r in reads if r["bytes_returned"] > 0)

    by_claim = sorted(reads, key=lambda r: r["gate_claim_ns"])
    claim_gaps = [
        (by_claim[i]["gate_claim_ns"] - by_claim[i - 1]["gate_claim_ns"]) / 1e6
        for i in range(1, len(by_claim))
    ]
    by_enter = sorted(reads, key=lambda r: r["preadv_enter_ns"])
    inter_starts = [
        (by_enter[i]["preadv_enter_ns"] - by_enter[i - 1]["preadv_enter_ns"]) / 1e6
        for i in range(1, len(by_enter))
    ]
    events: list[tuple[int, int]] = []
    for record in reads:
        events.append((record["preadv_enter_ns"], 1))
        events.append((record["preadv_exit_ns"], -1))
    events.sort()
    concurrent = 0
    max_in_flight = 0
    for _, delta in events:
        concurrent += delta
        max_in_flight = max(max_in_flight, concurrent)
    span_ns = last_exit - first_enter
    busy_ns = sum(r["preadv_exit_ns"] - r["preadv_enter_ns"] for r in reads)

    per_worker_stats = []
    for worker_id, first_block, count in assignments:
        group = [r for r in reads if r["worker"] == worker_id]
        entry = {"worker": worker_id, "first_block": first_block, "blocks": count,
                 "reads": len(group), "pid": reader_payloads[worker_id].get("pid"),
                 "nc_tid": reader_payloads[worker_id].get("nc_tid"),
                 "py_ticks": len(reader_payloads[worker_id].get("py_ticks") or []),
                 "nc_ticks": len(reader_payloads[worker_id].get("nc_ticks") or [])}
        if group:
            gms = [r["preadv_ms"] for r in group]
            entry["worst_preadv_ms"] = max(gms)
            entry["median_preadv_ms"] = percentile(gms, 50)
        per_worker_stats.append(entry)

    return {
        "schema_version": 1,
        "kind": "worker_model_witness_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "processes_witness",
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "canary_cadence_ms": canary_cadence_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {
            "platform": platform.system(), "syscall_impl": "os.preadv",
            "multiprocessing_start_method": pacer_ctx.get_start_method(),
        },
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "processes_witness",
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in reads if r.get("pid") is not None}),
        "process_spawn_to_all_ready_ms": (
            (ready_ns - spawn_start_ns) / 1e6 if ready_ns is not None else None
        ),
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": worker_errors,
        "physical_reads": len(reads),
        "useful_bytes": useful_bytes,
        "covered_bytes": sum(r["length"] for r in reads),
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": (
            (useful_bytes / (wall_ms / 1000.0) / 1e9) if wall_ms else None
        ),
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "reads_expected": total_blocks, "reads_completed": len(reads),
            "all_reads_returned_full_length": all(r["bytes_returned"] == r["length"] for r in reads),
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_workers_completed_region": all(
                len([r for r in reads if r["worker"] == wid]) == count
                for wid, _fb, count in assignments),
            "covers_entire_file_exactly_once": bool(
                completed_bytes == expected_bytes == file_size and len(reads) == total_blocks
                and no_overlap and contiguous),
        },
        "worker_partitions": [
            {"worker": worker_id, "first_block": first_block, "blocks": count}
            for worker_id, first_block, count in assignments
        ],
        "worker_stats": per_worker_stats,
        "reads": reads,
        # ---- pacer / spacing (required by the shared validity gate) ----
        "pacer": {
            "configured_min_gap_ms": min_launch_gap_ns / 1e6,
            "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "observed_median_global_claim_gap_ms": (
                percentile(claim_gaps, 50) if claim_gaps else None
            ),
        },
        "launch_spacing": {
            "configured_min_gap_ms": min_launch_gap_ns / 1e6,
            "observed_min_inter_start_ms": min(inter_starts) if inter_starts else None,
            "observed_median_inter_start_ms": (
                percentile(inter_starts, 50) if inter_starts else None
            ),
            "mean_effective_concurrency": (busy_ns / span_ns) if span_ns > 0 else None,
            "max_simultaneous_in_flight": max_in_flight,
        },
        # ---- witnesses ----
        "witness_parent_py_ticks": parent_ticks,
        "witness_reader_py_ticks": {str(w): (reader_payloads[w].get("py_ticks") or [])
                                    for w in range(qd)},
        "witness_reader_nc_ticks": {str(w): (reader_payloads[w].get("nc_ticks") or [])
                                    for w in range(qd)},
        "witness_reader_nc_tid": {str(w): reader_payloads[w].get("nc_tid") for w in range(qd)},
        "witness_control_py_ticks": control_payload.get("py_ticks") or [],
        "witness_control_nc_ticks": control_payload.get("nc_ticks") or [],
        "witness_control_nc_tid": control_payload.get("nc_tid"),
        "witness_control_pid": control_payload.get("pid"),
        "witness_control_status": control_payload.get("status"),
    }


# ==========================================================================
# Test 2 - dedicated 5th hedge PROCESS.
#
# QD4 primary architecture is unchanged (4 reader processes, static contiguous
# regions, 64 MiB reads, one global 4.0 ms pacer).  What changes is ONLY where
# a hedge runs: a single independent process that participates in no normal
# source work, is alive and parked before timing starts, and is triggered by
# the PARENT/coordinator when a logical block crosses the 250 ms threshold.
#
# No hedge threads are created inside a reader process.  A reader uses exactly
# one helper thread per outstanding ORIGINAL read so its coordinator can accept
# a hedge without waiting for the slow syscall; it rotates two buffers so a
# losing original never blocks the next block.
#
# The hedge reads into its own buffer.  Source-only: only completion (bytes)
# matters, so no payload is transferred between processes.
# ==========================================================================


def _hedge_process_child(args: tuple) -> None:
    """Dedicated hedge process: parks on a pipe, serves one duplicate read per request.

    ``hedge_file_path`` may point at a DIFFERENT file than the primary readers
    use.  That is the resource-diversity experiment: if a hedge on a different
    inode returns in normal time while the primary file is stalling, the
    stall is per-inode and resource diversity decouples it.  If it stalls too,
    the coupling is broader than the inode.
    """
    (hedge_file_path, read_bytes, file_size, req_conn, resp_conn,
     ready_barrier, start_barrier, cadence_ns, hedge_shift_blocks, child_conn) = args
    payload: dict[str, Any] = {"status": "ok", "served": [], "py_ticks": [],
                               "pid": os.getpid(), "hedge_file_path": hedge_file_path}
    fd = -1
    py_stop = threading.Event()
    py_thread = None
    try:
        preadv_fn = getattr(os, "preadv", None)
        if not callable(preadv_fn):
            raise RuntimeError("os.preadv unavailable")
        preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)
        buffer = bytearray(read_bytes)
        view = memoryview(buffer)
        fd = os.open(hedge_file_path, os.O_RDONLY)
        hedge_size = int(os.stat(hedge_file_path).st_size)
        payload["hedge_file_size"] = hedge_size

        ticks = payload["py_ticks"]

        def _canary() -> None:
            while not py_stop.is_set():
                ticks.append(int(time.perf_counter_ns()))
                py_stop.wait(cadence_ns / 1e9)

        py_thread = threading.Thread(target=_canary, daemon=True)
        py_thread.start()

        ready_barrier.wait(300.0)
        start_barrier.wait(300.0)
        while True:
            try:
                req = req_conn.recv()
            except EOFError:
                break
            if req is None:
                break
            worker, block_index, seq, offset, length = req
            # clamp into the hedge file so a different-sized file still reads
            limit = max(0, hedge_size - length)
            hedge_offset = offset if offset <= limit else (offset % (limit + 1) if limit else 0)
            # Offset-shift probe: read a DIFFERENT block of the same file.  If a
            # shifted hedge is fast while the original's block stalls, the stall
            # is per-block (a miss fetch), not resource-wide.
            if hedge_shift_blocks:
                shifted = ((block_index + hedge_shift_blocks) * read_bytes)
                if shifted <= limit:
                    hedge_offset = shifted
            target = view if length == read_bytes else view[:length]
            enter = int(time.perf_counter_ns())
            try:
                got = int(preadv(fd, [target], hedge_offset))
            except BaseException:
                got = -1
            exit_ns = int(time.perf_counter_ns())
            payload["served"].append({
                "worker": int(worker), "block_index": int(block_index), "seq": int(seq),
                "offset": int(offset), "hedge_offset": int(hedge_offset),
                "length": int(length),
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
            })
            try:
                resp_conn.send((int(worker), int(block_index), int(seq), enter, exit_ns, got))
            except BaseException:  # noqa: BLE001
                break
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            py_stop.set()
            if py_thread is not None:
                py_thread.join(timeout=1.0)
        except BaseException:  # noqa: BLE001
            pass
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def _hp_reader_child(args: tuple) -> None:
    """Reader with 2-buffer rotation; accepts a hedge published by the parent."""
    (worker_id, file_path, read_bytes, first_block, count, file_size,
     ready_barrier, start_barrier, last_launch_ns, min_launch_gap_ns,
     ready_timeout_s, hedge_slot, hedge_delay_ns, child_conn) = args
    payload: dict[str, Any] = {
        "worker": worker_id, "pid": os.getpid(), "status": "ok",
        "logical": [], "physical": [], "hedge_accepts": 0,
    }
    fds: list[int] = []
    try:
        preadv_fn = getattr(os, "preadv", None)
        if not callable(preadv_fn):
            raise RuntimeError("os.preadv unavailable")
        preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)

        buffers = [bytearray(read_bytes), bytearray(read_bytes)]
        views = [memoryview(buffers[0]), memoryview(buffers[1])]
        fd = os.open(file_path, os.O_RDONLY)
        fds.append(fd)

        ready_barrier.wait(ready_timeout_s)
        start_barrier.wait(ready_timeout_s)
        pacer_lock = last_launch_ns.get_lock()

        outstanding: list[Any] = [None, None]   # thread using each buffer slot

        for step in range(count):
            block_index = first_block + step
            offset = block_index * read_bytes
            length = min(read_bytes, file_size - offset)
            slot = step % 2
            prior = outstanding[slot]
            if prior is not None:
                prior.join()
                outstanding[slot] = None
            view = views[slot]
            target = view if length == read_bytes else view[:length]

            orig: dict[str, Any] = {}
            orig_done = threading.Event()
            orig_entered = threading.Event()

            def _original() -> None:
                claim, wait_ns, _hold = _mw_gate_launch(
                    pacer_lock, last_launch_ns, min_launch_gap_ns, time.perf_counter_ns)
                enter = int(time.perf_counter_ns())
                # Record and signal ENTRY before the syscall.  Publishing only
                # after preadv returns is what previously made the parent see
                # the crossing at the original's completion instead of at the
                # threshold.
                orig["claim"] = claim
                orig["enter"] = enter
                orig["wait_ns"] = wait_ns
                orig_entered.set()
                try:
                    got = int(preadv(fd, [target], offset))
                except BaseException:
                    got = -1
                exit_ns = int(time.perf_counter_ns())
                orig["exit"] = exit_ns
                orig["bytes"] = got
                orig_done.set()

            thread = threading.Thread(target=_original, daemon=True)
            thread.start()
            outstanding[slot] = thread

            # Publish identity + enter so the parent can time the crossing.
            # 5 slots per worker: [generation, block_index, enter_ns,
            # hedge_exit_ns, hedge_bytes].  Keying on (generation, block) makes
            # a late response for a previous block harmless.
            base_idx = worker_id * 5
            orig_entered.wait(5.0)
            hedge_slot[base_idx + 0] = step
            hedge_slot[base_idx + 1] = block_index
            hedge_slot[base_idx + 2] = int(orig.get("enter") or 0)
            hedge_slot[base_idx + 3] = 0
            hedge_slot[base_idx + 4] = 0

            accepted = "original"
            hedge_exit = 0
            hedge_bytes = 0
            while not orig_done.is_set():
                if (int(hedge_slot[base_idx + 3]) > 0
                        and int(hedge_slot[base_idx + 0]) == step
                        and int(hedge_slot[base_idx + 1]) == block_index):
                    hedge_exit = int(hedge_slot[base_idx + 3])
                    hedge_bytes = int(hedge_slot[base_idx + 4])
                    accepted = "hedge"
                    break
                orig_done.wait(0.002)
            # stop the parent considering this block any further
            hedge_slot[base_idx + 2] = 0

            if accepted == "hedge":
                payload["hedge_accepts"] += 1
                winner_exit = int(hedge_exit)
                winner_bytes = int(hedge_bytes)
            else:
                winner_exit = int(orig.get("exit") or 0)
                winner_bytes = int(orig.get("bytes") or 0)

            payload["physical"].append({
                "worker": worker_id, "pid": os.getpid(), "block_index": block_index,
                "kind": "original", "offset": offset, "length": length,
                "gate_claim_ns": int(orig.get("claim") or 0),
                "preadv_enter_ns": int(orig.get("enter") or 0),
                "preadv_exit_ns": int(orig.get("exit") or 0),
                "preadv_ms": ((int(orig.get("exit") or 0) - int(orig.get("enter") or 0)) / 1e6),
                "gate_wait_ms": float(orig.get("wait_ns") or 0) / 1e6,
                "bytes_returned": int(orig.get("bytes") or 0),
            })
            payload["logical"].append({
                "worker": worker_id, "pid": os.getpid(), "generation": step,
                "block_index": block_index, "offset": offset, "length": length,
                "accepted": accepted, "bytes_returned": winner_bytes,
                "logical_enter_ns": int(orig.get("enter") or 0),
                "logical_exit_ns": winner_exit,
                "logical_ms": ((winner_exit - int(orig.get("enter") or 0)) / 1e6),
            })
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        for handle in fds:
            try:
                os.close(handle)
            except BaseException:  # noqa: BLE001
                pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_worker_model_hedge_process_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int,
    hedge_delay_ns: int = 250_000_000,
    hedge_file_path: str | None = None,
    hedge_shift_blocks: int = 0,
    min_launch_gap_ns: int = 0,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    pacer_start_method: str = "fork",
) -> dict:
    """QD4 readers + one dedicated hedge process triggered by the parent."""
    import multiprocessing as mp  # noqa: PLC0415

    if not callable(getattr(os, "preadv", None)):
        raise RuntimeError("os.preadv unavailable")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if pacer_start_method not in mp.get_all_start_methods():
        raise RuntimeError(f"start_method_unavailable:{pacer_start_method}")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {"path": file_path, "size": file_size,
                     "st_dev": getattr(stat_result, "st_dev", None),
                     "st_ino": getattr(stat_result, "st_ino", None),
                     "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)}

    total_blocks = (file_size + read_bytes - 1) // read_bytes
    base, extra = divmod(total_blocks, qd)
    assignments: list[tuple[int, int, int]] = []
    cursor = 0
    for worker_id in range(qd):
        cnt = base + (1 if worker_id < extra else 0)
        assignments.append((worker_id, cursor, cnt))
        cursor += cnt
    expected_bytes = sum(
        min(read_bytes, file_size - block_index * read_bytes)
        for _, first_block, cnt in assignments
        for block_index in range(first_block, first_block + cnt))

    pacer_ctx = mp.get_context(pacer_start_method)
    ready_barrier = pacer_ctx.Barrier(qd + 2)
    start_barrier = pacer_ctx.Barrier(qd + 2)
    last_launch_ns = pacer_ctx.Value("q", 0)
    hedge_slot = pacer_ctx.Array("q", [0] * (qd * 5))

    reader_payloads: list[dict[str, Any]] = [
        {"worker": w, "status": "ok", "logical": [], "physical": [], "hedge_accepts": 0}
        for w in range(qd)]
    reader_conns: list[tuple[int, Any]] = []
    reader_procs: list[Any] = []
    spawn_start_ns = int(clock_ns())
    for worker_id, first_block, cnt in assignments:
        parent_conn, child_conn = pacer_ctx.Pipe(duplex=False)
        proc = cast(Any, pacer_ctx).Process(
            target=_hp_reader_child,
            args=((worker_id, file_path, read_bytes, first_block, cnt, file_size,
                   ready_barrier, start_barrier, last_launch_ns, min_launch_gap_ns,
                   ready_timeout_s, hedge_slot, hedge_delay_ns, child_conn),),
            daemon=True)
        proc.start()
        child_conn.close()
        reader_conns.append((worker_id, parent_conn))
        reader_procs.append(proc)

    # Resource-diversity lever: the hedge may read a DIFFERENT file (different
    # inode) than the primary readers.  Same file by default.
    hedge_target_path = str(hedge_file_path or file_path)

    # Pipe(duplex=False) returns (recv_end, send_end).  Get the direction right:
    # requests go parent -> hedge process, responses hedge process -> parent.
    hedge_req_recv, hedge_req_send = pacer_ctx.Pipe(duplex=False)
    hedge_resp_recv, hedge_resp_send = pacer_ctx.Pipe(duplex=False)
    hedge_conn_parent, hedge_conn_child = pacer_ctx.Pipe(duplex=False)
    hedge_proc = cast(Any, pacer_ctx).Process(
        target=_hedge_process_child,
        args=((hedge_target_path, read_bytes, file_size, hedge_req_recv, hedge_resp_send,
               ready_barrier, start_barrier, 10_000_000, hedge_shift_blocks,
               hedge_conn_child),),
        daemon=True)
    hedge_proc.start()
    hedge_req_recv.close()
    hedge_resp_send.close()
    hedge_conn_child.close()

    barrier_error = None
    release_ns = None
    try:
        ready_barrier.wait(ready_timeout_s)
        start_barrier.wait(ready_timeout_s)
        release_ns = int(clock_ns())
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    # ---- parent-side dispatch: NEVER block on a response ----
    # A dedicated drain thread owns hedge responses, so threshold detection in
    # the main loop stays live continuously even while a slow hedge is in
    # flight.  Previously the main loop called recv() inline, which serialised
    # dispatch behind the slowest in-flight hedge and pushed the trigger out to
    # the original's completion time.
    trigger_lock = threading.Lock()
    triggers: list[dict[str, Any]] = []
    seq = 0
    watched: set[tuple[int, int, int]] = set()
    pending = [0]
    stop_drain = threading.Event()

    def _drain_responses() -> None:
        while not stop_drain.is_set():
            try:
                resp = hedge_resp_recv.recv()
            except (EOFError, OSError):
                break
            if resp is None:
                break
            worker, blk, rseq, h_enter, h_exit, got = resp
            with trigger_lock:
                pending[0] = max(0, pending[0] - 1)
                for entry in triggers:
                    if entry.get("seq") == rseq:
                        entry["hedge_enter_ns"] = int(h_enter)
                        entry["hedge_exit_ns"] = int(h_exit)
                        entry["hedge_ms"] = (int(h_exit) - int(h_enter)) / 1e6
                        entry["served"] = True
                        break
            # publish so the reader can accept it (identity-checked there)
            hedge_slot[int(worker) * 5 + 3] = int(h_exit)
            hedge_slot[int(worker) * 5 + 4] = int(got)

    drain_thread = threading.Thread(target=_drain_responses, daemon=True)
    drain_thread.start()

    max_pending = qd
    busy = True
    while busy:
        busy = any(p.is_alive() for p in reader_procs)
        now = int(clock_ns())
        for worker_id, _fb, _cnt in assignments:
            base = worker_id * 5
            gen = int(hedge_slot[base + 0])
            blk = int(hedge_slot[base + 1])
            ent = int(hedge_slot[base + 2])
            if ent <= 0 or now - ent < hedge_delay_ns:
                continue
            key = (worker_id, gen, blk)
            with trigger_lock:
                if key in watched or pending[0] >= max_pending:
                    continue
                watched.add(key)
                seq += 1
                my_seq = seq
                pending[0] += 1
                triggers.append({
                    "worker": worker_id, "generation": gen, "block_index": blk,
                    "seq": my_seq, "trigger_ns": now, "original_enter_ns": ent,
                    "served": False,
                })
            offset = blk * read_bytes
            length = min(read_bytes, file_size - offset)
            try:
                hedge_req_send.send((worker_id, blk, my_seq, offset, length))
            except BaseException as exc:  # noqa: BLE001
                with trigger_lock:
                    pending[0] = max(0, pending[0] - 1)
                    for entry in triggers:
                        if entry.get("seq") == my_seq:
                            entry["error"] = type(exc).__name__
                            break
        time.sleep(0.001)

    try:
        hedge_req_send.send(None)
    except BaseException:  # noqa: BLE001
        pass
    stop_drain.set()
    try:
        hedge_resp_recv.close()
    except BaseException:  # noqa: BLE001
        pass
    drain_thread.join(timeout=5.0)

    for worker_id, parent_conn in reader_conns:
        try:
            reader_payloads[worker_id] = parent_conn.recv()
        except BaseException as exc:  # noqa: BLE001
            reader_payloads[worker_id] = {
                "worker": worker_id, "status": "error",
                "error": f"recv_failed:{type(exc).__name__}",
                "logical": [], "physical": [], "hedge_accepts": 0}
    hedge_payload: dict[str, Any] = {"status": "ok", "served": [], "py_ticks": []}
    try:
        hedge_payload = hedge_conn_parent.recv()
    except BaseException as exc:  # noqa: BLE001
        hedge_payload = {"status": "error", "error": f"recv_failed:{type(exc).__name__}",
                         "served": [], "py_ticks": []}
    for proc in reader_procs:
        proc.join()
    hedge_proc.join(timeout=30.0)
    for _, parent_conn in reader_conns:
        parent_conn.close()
    hedge_req_send.close()
    hedge_resp_recv.close()
    hedge_conn_parent.close()

    logical = [r for p in reader_payloads for r in (p.get("logical") or [])]
    physical = [r for p in reader_payloads for r in (p.get("physical") or [])]
    if not logical:
        raise RuntimeError(f"no_logical_records:{barrier_error or 'workers_failed'}")

    durations = [r["logical_ms"] for r in logical]
    useful_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    first_enter = min(r["logical_enter_ns"] for r in logical if r["logical_enter_ns"])
    last_exit = max(r["logical_exit_ns"] for r in logical if r["logical_exit_ns"])
    wall_ms = (last_exit - first_enter) / 1e6

    ordered = sorted(logical, key=lambda r: (r["offset"], r["length"]))
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    completed_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)

    worker_stats = []
    for worker_id, first_block, cnt in assignments:
        group = [r for r in logical if r["worker"] == worker_id]
        entry = {"worker": worker_id, "first_block": first_block, "blocks": cnt,
                 "reads": len(group), "pid": reader_payloads[worker_id].get("pid")}
        if group:
            gms = [r["logical_ms"] for r in group]
            entry["last_exit_ns"] = max(r["logical_exit_ns"] for r in group)
            entry["worst_preadv_ms"] = max(gms)
            entry["median_preadv_ms"] = percentile(gms, 50)
        worker_stats.append(entry)

    by_claim = sorted(physical, key=lambda r: r["gate_claim_ns"])
    claim_gaps = [
        (by_claim[i]["gate_claim_ns"] - by_claim[i - 1]["gate_claim_ns"]) / 1e6
        for i in range(1, len(by_claim))
    ]
    ev: list[tuple[int, int]] = []
    for record in physical:
        ev.append((record["preadv_enter_ns"], 1))
        ev.append((record["preadv_exit_ns"], -1))
    for t in hedge_payload.get("served") or []:
        ev.append((int(t["preadv_enter_ns"]), 1))
        ev.append((int(t["preadv_exit_ns"]), -1))
    ev.sort()
    conc = 0
    max_in_flight = 0
    for _, delta in ev:
        conc += delta
        max_in_flight = max(max_in_flight, conc)
    span_ns = last_exit - first_enter
    busy_ns = sum(r["preadv_exit_ns"] - r["preadv_enter_ns"] for r in physical)

    return {
        "schema_version": 1,
        "kind": "worker_model_hedge_process_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "processes_hedge_process",
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "hedge_delay_ns": hedge_delay_ns, "hedge_delay_ms": hedge_delay_ns / 1e6,
            "hedge_file_path": hedge_target_path,
            "hedge_file_is_primary": bool(hedge_target_path == file_path),
            "hedge_shift_blocks": hedge_shift_blocks,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv",
                "multiprocessing_start_method": pacer_ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "processes_hedge_process",
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in logical if r.get("pid") is not None}),
        "hedge_process_pid": hedge_payload.get("pid"),
        "hedge_process_status": hedge_payload.get("status"),
        "process_spawn_to_all_ready_ms": None,
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": [{"worker": p.get("worker"), "error": p.get("error")}
                          for p in reader_payloads if p.get("status") != "ok"],
        "physical_reads": len(logical),
        "useful_bytes": useful_bytes,
        "covered_bytes": sum(r["length"] for r in logical),
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": ((useful_bytes / (wall_ms / 1000.0) / 1e9) if wall_ms else None),
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size,
            "bytes_match": completed_bytes == expected_bytes == file_size,
            "reads_expected": total_blocks, "reads_completed": len(logical),
            "all_reads_returned_full_length": all(
                (r["bytes_returned"] or 0) == r["length"] for r in logical),
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_workers_completed_region": all(
                len([r for r in logical if r["worker"] == wid]) == cnt
                for wid, _fb, cnt in assignments),
            "covers_entire_file_exactly_once": bool(
                completed_bytes == expected_bytes == file_size
                and len(logical) == total_blocks and no_overlap and contiguous),
        },
        "worker_partitions": [{"worker": w, "first_block": fb, "blocks": c}
                              for w, fb, c in assignments],
        "worker_stats": worker_stats,
        "hedge_triggers": triggers,
        "hedge_served": hedge_payload.get("served") or [],
        "hedge_process_py_ticks": hedge_payload.get("py_ticks") or [],
        "hedge_accepts_total": sum(int(p.get("hedge_accepts") or 0) for p in reader_payloads),
        "pacer": {
            "configured_min_gap_ms": min_launch_gap_ns / 1e6,
            "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "observed_median_global_claim_gap_ms": (
                percentile(claim_gaps, 50) if claim_gaps else None),
        },
        "launch_spacing": {
            "configured_min_gap_ms": min_launch_gap_ns / 1e6,
            "mean_effective_concurrency": (busy_ns / span_ns) if span_ns > 0 else None,
            "max_simultaneous_in_flight": max_in_flight,
        },
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": physical,
    }


# ==========================================================================
# GLOBAL GREEDY ALLOCATOR (treatment)
#
# No fixed per-reader regions.  The parent owns the whole file as a queue of
# logical blocks and hands work to whichever reader is free:
#   1. if an in-flight logical block has been outstanding >= rescue_delay and
#      has no rescue running -> give the free reader that SAME block (duplicate)
#   2. otherwise -> the next unstarted block
#
# 4 reader processes, one physical read at a time each => physical QD is
# structurally 4.  First valid completion of a logical block wins; late
# duplicates are stale and cannot overwrite anything.
#
# The allocator performs NO model I/O.  Pacing is a single global
# last-start timestamp: launch immediately if >= gap has elapsed, otherwise
# sleep only the remaining fraction (work-conserving; no post-completion sleep).
# ==========================================================================


def _alloc_gate(pacer_lock, last_start, gap_ns: int, clock_ns):
    """Claim the next global physical start.  Sleep only the remaining fraction."""
    entered = int(clock_ns())
    while True:
        with pacer_lock:
            now = int(clock_ns())
            elapsed = now - int(last_start.value)
            if elapsed >= gap_ns:
                last_start.value = now
                return now, now - entered
            remaining = gap_ns - elapsed
        time.sleep(remaining / 1e9)


def _alloc_reader_child(args: tuple) -> None:
    """One reader: pull a task, do exactly one physical read, report it."""
    (reader_id, file_path, read_bytes, task_recv, result_send,
     pacer_lock, last_start, gap_ns, ready_barrier, start_barrier, child_conn) = args
    payload: dict[str, Any] = {"reader": reader_id, "pid": os.getpid(),
                               "status": "ok", "records": []}
    fd = -1
    try:
        preadv_fn = getattr(os, "preadv", None)
        if not callable(preadv_fn):
            raise RuntimeError("os.preadv unavailable")
        preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)
        buffer = bytearray(read_bytes)
        view = memoryview(buffer)
        fd = os.open(file_path, os.O_RDONLY)
        ready_barrier.wait(300.0)
        start_barrier.wait(300.0)
        while True:
            try:
                task = task_recv.recv()
            except EOFError:
                break
            if task is None:
                break
            block_id, offset, length, kind, seq = task
            target = view if length == read_bytes else view[:length]
            claim, gate_wait_ns = _alloc_gate(
                pacer_lock, last_start, gap_ns, time.perf_counter_ns)
            enter = int(time.perf_counter_ns())
            try:
                got = int(preadv(fd, [target], offset))
            except BaseException:
                got = -1
            exit_ns = int(time.perf_counter_ns())
            payload["records"].append({
                "reader": reader_id, "pid": os.getpid(), "block_id": int(block_id),
                "kind": str(kind), "seq": int(seq), "offset": int(offset),
                "length": int(length), "gate_claim_ns": int(claim),
                "gate_wait_ms": gate_wait_ns / 1e6,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
            })
            try:
                result_send.send((reader_id, int(block_id), str(kind), int(seq),
                                  int(claim), enter, exit_ns, got))
            except BaseException:  # noqa: BLE001
                break
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_greedy_allocator_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int = 4,
    rescue_delay_ns: int = 250_000_000,
    sticky_lanes: bool = True,
    min_launch_gap_ns: int = 4_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    pacer_start_method: str = "fork",
) -> dict:
    """Whole-file pass under the global greedy allocator."""
    import multiprocessing as mp  # noqa: PLC0415

    if not callable(getattr(os, "preadv", None)):
        raise RuntimeError("os.preadv unavailable")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if pacer_start_method not in mp.get_all_start_methods():
        raise RuntimeError(f"start_method_unavailable:{pacer_start_method}")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {"path": file_path, "size": file_size,
                     "st_dev": getattr(stat_result, "st_dev", None),
                     "st_ino": getattr(stat_result, "st_ino", None),
                     "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)}

    total_blocks = (file_size + read_bytes - 1) // read_bytes
    def _blen(bid: int) -> int:
        return min(read_bytes, file_size - bid * read_bytes)
    expected_bytes = sum(_blen(b) for b in range(total_blocks))

    # Four contiguous lanes matching the static ~2 GB-per-reader partitioning.
    # Sticky mode keeps each reader inside its own lane, so the healthy physical
    # offset pattern is identical to the fast static implementation.
    lanes: list[list[int]] = []
    if sticky_lanes:
        _base, _extra = divmod(total_blocks, qd)
        _cursor = 0
        for _lid in range(qd):
            _cnt = _base + (1 if _lid < _extra else 0)
            lanes.append(list(range(_cursor, _cursor + _cnt)))
            _cursor += _cnt
    lane_cursor = [0] * qd

    pacer_ctx = mp.get_context(pacer_start_method)
    ready_barrier = pacer_ctx.Barrier(qd + 1)
    start_barrier = pacer_ctx.Barrier(qd + 1)
    last_start = pacer_ctx.Value("q", 0)
    pacer_lock = last_start.get_lock()

    task_sends: list[Any] = []
    result_recvs: list[Any] = []
    reader_procs: list[Any] = []
    reader_conns: list[Any] = []
    spawn_start_ns = int(clock_ns())
    for rid in range(qd):
        t_recv, t_send = pacer_ctx.Pipe(duplex=False)   # (recv, send)
        r_recv, r_send = pacer_ctx.Pipe(duplex=False)
        conn_parent, conn_child = pacer_ctx.Pipe(duplex=False)
        proc = cast(Any, pacer_ctx).Process(
            target=_alloc_reader_child,
            args=((rid, file_path, read_bytes, t_recv, r_send, pacer_lock,
                   last_start, min_launch_gap_ns, ready_barrier, start_barrier,
                   conn_child),),
            daemon=True)
        proc.start()
        t_recv.close()
        r_send.close()
        conn_child.close()
        task_sends.append(t_send)
        result_recvs.append(r_recv)
        reader_conns.append(conn_parent)
        reader_procs.append(proc)

    barrier_error = None
    release_ns = None
    try:
        ready_barrier.wait(ready_timeout_s)
        start_barrier.wait(ready_timeout_s)
        release_ns = int(clock_ns())
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    state = [{"started": False, "first_start_ns": 0, "completed": False,
              "winner": None, "winner_kind": None, "winner_exit_ns": None,
              "primary_reader": None, "rescue_dispatched": False,
              "rescue_reader": None, "attempts": 0} for _ in range(total_blocks)]
    unstarted = list(range(total_blocks))
    reader_busy = [False] * qd
    reader_current: list[Any] = [None] * qd
    reader_blocks_won = [0] * qd
    reader_free_since = [int(clock_ns())] * qd
    idle_no_work_ms = [0.0] * qd
    dispatches: list[dict[str, Any]] = []
    completed = 0
    stale = 0
    seq = 0
    affinity_breaks = 0
    lane_finish_reassignments = 0
    physical = 0
    in_flight = 0
    max_in_flight = 0
    physical_records: list[dict[str, Any]] = []

    while completed < total_blocks:
        progressed = False
        for rid in range(qd):
            conn = result_recvs[rid]
            while conn.poll(0):
                (_rid, bid, kind, rseq, claim, enter, exit_ns, got) = conn.recv()
                st = state[bid]
                st["attempts"] += 1
                physical += 1
                in_flight -= 1
                physical_records.append({
                    "reader": rid, "block_id": bid, "kind": kind, "seq": rseq,
                    "offset": bid * read_bytes, "length": _blen(bid),
                    "gate_claim_ns": claim, "preadv_enter_ns": enter,
                    "preadv_exit_ns": exit_ns,
                    "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
                })
                if not st["completed"]:
                    st["completed"] = True
                    st["winner"] = rid
                    st["winner_kind"] = kind
                    st["winner_exit_ns"] = exit_ns
                    reader_blocks_won[rid] += 1
                    completed += 1
                else:
                    stale += 1
                reader_busy[rid] = False
                reader_current[rid] = None
                reader_free_since[rid] = int(clock_ns())
                progressed = True

        for rid in range(qd):
            if reader_busy[rid]:
                continue
            now = int(clock_ns())
            target = None
            kind = None
            for bid in range(total_blocks):
                s = state[bid]
                if (not s["completed"] and s["started"]
                        and not s["rescue_dispatched"]
                        and now - s["first_start_ns"] >= rescue_delay_ns):
                    target, kind = bid, "rescue"
                    break
            if target is None:
                if sticky_lanes:
                    # HEALTHY: next contiguous unstarted block from own lane.
                    my_lane = lanes[rid]
                    while lane_cursor[rid] < len(my_lane):
                        cand = my_lane[lane_cursor[rid]]
                        lane_cursor[rid] += 1
                        if not state[cand]["started"]:
                            target, kind = cand, "primary"
                            break
                    if target is None:
                        # BREAK AFFINITY: own lane exhausted, another lane has work.
                        best_lane, best_remaining = None, 0
                        for lid in range(qd):
                            rem = sum(1 for b in lanes[lid]
                                      if not state[b]["started"])
                            if rem > best_remaining:
                                best_lane, best_remaining = lid, rem
                        if best_lane is not None:
                            while lane_cursor[best_lane] < len(lanes[best_lane]):
                                cand = lanes[best_lane][lane_cursor[best_lane]]
                                lane_cursor[best_lane] += 1
                                if not state[cand]["started"]:
                                    target, kind = cand, "primary"
                                    affinity_breaks += 1
                                    lane_finish_reassignments += 1
                                    break
                    if target is None:
                        idle_no_work_ms[rid] += (now - reader_free_since[rid]) / 1e6
                        reader_free_since[rid] = now
                        continue
                    state[target]["started"] = True
                    state[target]["primary_reader"] = rid
                    state[target]["first_start_ns"] = now
                elif unstarted:
                    target, kind = unstarted.pop(0), "primary"
                    state[target]["started"] = True
                    state[target]["primary_reader"] = rid
                    state[target]["first_start_ns"] = now
                else:
                    idle_no_work_ms[rid] += (now - reader_free_since[rid]) / 1e6
                    reader_free_since[rid] = now
                    continue
            if kind == "rescue":
                state[target]["rescue_dispatched"] = True
                state[target]["rescue_reader"] = rid
            seq += 1
            offset = target * read_bytes
            length = _blen(target)
            free_at = reader_free_since[rid]
            try:
                task_sends[rid].send((target, offset, length, kind, seq))
            except BaseException as exc:  # noqa: BLE001
                dispatches.append({"reader": rid, "block_id": target, "kind": kind,
                                   "seq": seq, "error": type(exc).__name__})
                continue
            reader_busy[rid] = True
            reader_current[rid] = (target, kind, seq)
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            dispatches.append({
                "reader": rid, "block_id": target, "kind": kind, "seq": seq,
                "lane_id": rid if sticky_lanes else None,
                "from_own_lane": bool(
                    sticky_lanes and kind == "primary"
                    and target in lanes[rid]),
                "free_at_ns": free_at, "sent_ns": int(clock_ns()),
                "allocator_latency_ms": (int(clock_ns()) - free_at) / 1e6,
            })
        if progressed:
            continue
        time.sleep(0.0005)

    for rid in range(qd):
        try:
            task_sends[rid].send(None)
        except BaseException:  # noqa: BLE001
            pass

    reader_payloads: list[dict[str, Any]] = []
    for rid in range(qd):
        try:
            reader_payloads.append(reader_conns[rid].recv())
        except BaseException as exc:  # noqa: BLE001
            reader_payloads.append({"reader": rid, "status": "error",
                                    "error": f"recv_failed:{type(exc).__name__}",
                                    "records": []})
    for proc in reader_procs:
        proc.join(timeout=60.0)
    for conn in task_sends + result_recvs + reader_conns:
        try:
            conn.close()
        except BaseException:  # noqa: BLE001
            pass

    reader_errors = [{"reader": p.get("reader"), "error": p.get("error")}
                     for p in reader_payloads if p.get("status") != "ok"]
    child_records = [r for p in reader_payloads for r in (p.get("records") or [])]
    if not physical_records:
        raise RuntimeError(f"no_physical_reads:{barrier_error or 'readers_failed'}")

    durations = [r["preadv_ms"] for r in physical_records]
    useful_bytes = sum(r["bytes_returned"] for r in physical_records
                       if (r["bytes_returned"] or 0) > 0)
    covered_bytes = sum(r["length"] for r in physical_records if r["kind"] == "primary"
                        and state[r["block_id"]]["winner_kind"] == "primary")
    first_enter = min(r["preadv_enter_ns"] for r in physical_records)
    last_exit = max(r["preadv_exit_ns"] for r in physical_records)
    wall_ms = (last_exit - first_enter) / 1e6

    # logical view: one record per logical block, from its winning attempt
    logical: list[dict[str, Any]] = []
    for bid in range(total_blocks):
        st = state[bid]
        if not st["completed"]:
            continue
        win = next((r for r in physical_records
                    if r["block_id"] == bid and r["preadv_exit_ns"] == st["winner_exit_ns"]),
                   None)
        logical.append({
            "worker": st["winner"], "block_id": bid,
            "offset": bid * read_bytes, "length": _blen(bid),
            "accepted": st["winner_kind"],
            "bytes_returned": (win or {}).get("bytes_returned", 0),
            "logical_enter_ns": (win or {}).get("preadv_enter_ns", 0),
            "logical_exit_ns": st["winner_exit_ns"],
            "logical_ms": ((st["winner_exit_ns"] - (win or {}).get("preadv_enter_ns", 0)) / 1e6),
        })
    logical.sort(key=lambda r: r["block_id"])

    completed_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    ordered = sorted(logical, key=lambda r: r["offset"])
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    published_once = all(state[b]["attempts"] >= 1 and state[b]["completed"]
                         for b in range(total_blocks))

    claims = sorted(r["gate_claim_ns"] for r in physical_records)
    claim_gaps = [(claims[i] - claims[i - 1]) / 1e6 for i in range(1, len(claims))]
    ev: list[tuple[int, int]] = []
    for r in physical_records:
        ev.append((r["preadv_enter_ns"], 1))
        ev.append((r["preadv_exit_ns"], -1))
    ev.sort()
    conc = 0
    observed_max = 0
    for _, d in ev:
        conc += d
        observed_max = max(observed_max, conc)

    rescues = [d for d in dispatches if d.get("kind") == "rescue"]
    rescue_wins = [b for b in range(total_blocks)
                   if state[b]["winner_kind"] == "rescue"]
    savings = []
    for bid in rescue_wins:
        st = state[bid]
        prim = next((r for r in physical_records
                     if r["block_id"] == bid and r["kind"] == "primary"), None)
        if prim is not None:
            savings.append((prim["preadv_exit_ns"] - st["winner_exit_ns"]) / 1e6)

    return {
        "schema_version": 1,
        "kind": "greedy_allocator_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "greedy_allocator",
            "rescue_delay_ns": rescue_delay_ns, "rescue_delay_ms": rescue_delay_ns / 1e6,
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv",
                "multiprocessing_start_method": pacer_ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "greedy_allocator",
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in physical_records
                               if r.get("pid") is not None}),
        "reader_pids": [p.get("pid") for p in reader_payloads],
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": reader_errors,
        "physical_reads": len(logical),
        "physical_attempts": len(physical_records),
        "physical_amplification": (len(physical_records) / total_blocks),
        "stale_duplicates": stale,
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": ((completed_bytes / (wall_ms / 1000.0) / 1e9)
                                   if wall_ms else None),
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "blocks_expected": total_blocks, "blocks_completed": completed,
            "all_blocks_published_once": published_once,
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_reads_returned_full_length": all(
                (r["bytes_returned"] or 0) == r["length"] for r in logical),
            "covers_entire_file_exactly_once": bool(
                completed == total_blocks and completed_bytes == expected_bytes == file_size
                and no_overlap and contiguous),
        },
        "scheduler": {
            "rescue_eligible_blocks": len({d["block_id"] for d in rescues}),
            "rescue_launches": len(rescues),
            "rescue_wins": len(rescue_wins),
            "rescue_win_rate": (len(rescue_wins) / len(rescues)) if rescues else None,
            "rescue_saved_ms": savings,
            "rescue_saved_median_ms": percentile(savings, 50) if savings else None,
            "rescue_saved_max_ms": max(savings) if savings else None,
            "max_physical_qd_observed": observed_max,
            "max_physical_qd_structural": qd,
            "min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "median_global_claim_gap_ms": percentile(claim_gaps, 50) if claim_gaps else None,
            "reader_blocks_won": reader_blocks_won,
            "idle_no_work_ms": idle_no_work_ms,
            "dispatches": len(dispatches),
            "sticky_lanes": bool(sticky_lanes),
            "lane_sizes": [len(l) for l in lanes] if sticky_lanes else None,
            "affinity_breaks": affinity_breaks,
            "lane_finish_reassignments": lane_finish_reassignments,
            "allocator_latency_median_ms": percentile(
                [d["allocator_latency_ms"] for d in dispatches
                 if d.get("allocator_latency_ms") is not None], 50),
        },
        "pacer": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                  "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None},
        "launch_spacing": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                           "mean_effective_concurrency": None,
                           "max_simultaneous_in_flight": observed_max},
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": physical_records,
        "allocator_dispatches": dispatches,
    }


def _ss_reader_child(args: tuple) -> None:
    """Self-service reader: claim -> gate -> preadv -> publish.

    Normal work never round-trips through the parent process.  All coordination
    happens through tiny shared state, so the healthy loop is exactly::

        claim -> gate -> preadv -> claim -> gate -> preadv ...

    The only exceptional path is the rescue scan, which lets a *free* worker
    re-read a block that has been outstanding past ``rescue_delay_ns``.  Because
    the original worker is inside ``preadv`` while a rescue is claimed, a rescue
    can never be issued by the same process that holds the original.
    """
    (reader_id, file_path, file_size, read_bytes, lane_flat, lane_off, qd, sticky,
     ownership, winner, winner_kind, start_ns, winner_exit_ns, attempts,
     rescue_sent, completed, lock, next_global, last_start, pacer_lock, gap_ns,
     rescue_delay_ns, total_blocks, max_idle_s, ready_barrier, start_barrier,
     child_conn) = args
    payload: dict[str, Any] = {"reader": reader_id, "pid": os.getpid(),
                               "status": "ok", "records": [], "stale": 0,
                               "affinity_breaks": 0, "idle_no_work_ms": 0.0}
    fd = -1
    clock = time.perf_counter_ns
    try:
        preadv_fn = getattr(os, "preadv", None)
        if not callable(preadv_fn):
            raise RuntimeError("os.preadv unavailable")
        preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)
        buffer = bytearray(read_bytes)
        view = memoryview(buffer)
        fd = os.open(file_path, os.O_RDONLY)
        ready_barrier.wait(300.0)
        start_barrier.wait(300.0)
        my_start = int(lane_off[reader_id])
        my_end = int(lane_off[reader_id + 1])
        cursor = my_start
        idle_since = int(clock())
        idle_total = 0.0
        seq = 0
        idle_deadline: float | None = None
        while True:
            with lock:
                if int(completed.value) >= total_blocks:
                    break
            bid = -1
            kind = "primary"
            now = int(clock())
            with lock:
                if rescue_delay_ns > 0:
                    for b in range(total_blocks):
                        if (ownership[b] == 1 and rescue_sent[b] == 0
                                and (now - int(start_ns[b])) >= rescue_delay_ns):
                            rescue_sent[b] = 1
                            bid, kind = b, "rescue"
                            break
                if bid < 0 and sticky:
                    while cursor < my_end:
                        cand = int(lane_flat[cursor])
                        cursor += 1
                        if ownership[cand] == 0:
                            bid = cand
                            break
                    if bid < 0:
                        # Own lane exhausted: break affinity to any lane with work.
                        for lid in range(qd):
                            if lid == reader_id:
                                continue
                            s = int(lane_off[lid])
                            e = int(lane_off[lid + 1])
                            while s < e:
                                cand = int(lane_flat[s])
                                s += 1
                                if ownership[cand] == 0:
                                    bid = cand
                                    payload["affinity_breaks"] += 1
                                    break
                            if bid >= 0:
                                break
                elif bid < 0:
                    b = int(next_global.value)
                    while b < total_blocks:
                        next_global.value = b + 1
                        if ownership[b] == 0:
                            bid = b
                            break
                        b = int(next_global.value)
                if bid >= 0:
                    ownership[bid] = 1
                    start_ns[bid] = now
            if bid >= 0:
                # A successful claim closes the current idle window, so idle
                # time only ever accumulates while genuinely no work exists.
                idle_since = int(clock())
            if bid < 0:
                idle_total += (int(clock()) - idle_since) / 1e6
                idle_since = int(clock())
                with lock:
                    if int(completed.value) >= total_blocks:
                        break
                if idle_deadline is None:
                    idle_deadline = time.monotonic() + max_idle_s
                elif time.monotonic() > idle_deadline:
                    break
                time.sleep(0.0002)
                continue
            idle_deadline = None
            length = min(read_bytes, file_size - bid * read_bytes)
            offset = bid * read_bytes
            target = view if length == read_bytes else view[:length]
            seq += 1
            claim, gate_wait_ns = _alloc_gate(pacer_lock, last_start, gap_ns, clock)
            enter = int(clock())
            try:
                got = int(preadv(fd, [target], offset))
            except BaseException:  # noqa: BLE001
                got = -1
            exit_ns = int(clock())
            with lock:
                attempts[bid] = int(attempts[bid]) + 1
                if winner[bid] == -1:
                    winner[bid] = reader_id
                    winner_kind[bid] = 2 if kind == "rescue" else 1
                    winner_exit_ns[bid] = exit_ns
                    completed.value = int(completed.value) + 1
                else:
                    payload["stale"] += 1
                # 2 == completed: a finished block must never look "outstanding"
                # to the rescue scan again.
                ownership[bid] = 2
            payload["records"].append({
                "reader": reader_id, "pid": os.getpid(), "block_id": int(bid),
                "kind": str(kind), "seq": seq, "offset": offset, "length": length,
                "gate_claim_ns": int(claim), "gate_wait_ms": gate_wait_ns / 1e6,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
            })
        payload["idle_no_work_ms"] = idle_total
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_selfservice_allocator_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int = 4,
    rescue_delay_ns: int = 250_000_000,
    sticky_lanes: bool = True,
    min_launch_gap_ns: int = 4_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    max_idle_s: float = 120.0,
    pacer_start_method: str = "fork",
) -> dict:
    """Whole-file pass with a self-service (no manager round-trip) allocator.

    Each worker atomically claims its next block from shared state, passes the
    global 4 ms start gate, issues ``preadv`` and publishes the result with a
    once-only logical-ownership rule.  The parent only spawns, releases the
    start barrier, joins, and collects one record batch per worker at the end:
    it is on no per-block critical path.
    """
    import multiprocessing as mp  # noqa: PLC0415

    if not callable(getattr(os, "preadv", None)):
        raise RuntimeError("os.preadv unavailable")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if pacer_start_method not in mp.get_all_start_methods():
        raise RuntimeError(f"start_method_unavailable:{pacer_start_method}")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {"path": file_path, "size": file_size,
                     "st_dev": getattr(stat_result, "st_dev", None),
                     "st_ino": getattr(stat_result, "st_ino", None),
                     "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)}

    total_blocks = (file_size + read_bytes - 1) // read_bytes

    def _blen(bid: int) -> int:
        return min(read_bytes, file_size - bid * read_bytes)
    expected_bytes = sum(_blen(b) for b in range(total_blocks))

    lanes: list[list[int]] = []
    if sticky_lanes:
        _base, _extra = divmod(total_blocks, qd)
        _cursor = 0
        for _lid in range(qd):
            _cnt = _base + (1 if _lid < _extra else 0)
            lanes.append(list(range(_cursor, _cursor + _cnt)))
            _cursor += _cnt
    else:
        for _lid in range(qd):
            lanes.append(list(range(_lid, total_blocks, qd)))
    lane_flat_list = [b for l in lanes for b in l]
    lane_off_list = [0]
    for l in lanes:
        lane_off_list.append(lane_off_list[-1] + len(l))

    ctx = mp.get_context(pacer_start_method)
    lock = ctx.Lock()
    # lock=False: raw shared memory, no per-element synchronised wrapper.  Every
    # element access on a default mp.Array takes its own internal lock, which is
    # far too expensive for per-block hot loops.  All consistency is provided by
    # the single explicit `lock` below.
    ownership = ctx.Array("b", total_blocks, lock=False)
    winner = ctx.Array("i", [-1] * total_blocks, lock=False)
    winner_kind = ctx.Array("b", total_blocks, lock=False)
    start_ns = ctx.Array("q", total_blocks, lock=False)
    winner_exit_ns = ctx.Array("q", total_blocks, lock=False)
    attempts = ctx.Array("i", total_blocks, lock=False)
    rescue_sent = ctx.Array("b", total_blocks, lock=False)
    completed = ctx.Value("i", 0, lock=False)
    next_global = ctx.Value("q", 0, lock=False)
    lane_flat = ctx.Array("i", lane_flat_list, lock=False)
    lane_off = ctx.Array("i", lane_off_list, lock=False)
    last_start = ctx.Value("q", 0)
    pacer_lock = last_start.get_lock()
    ready_barrier = ctx.Barrier(qd + 1)
    start_barrier = ctx.Barrier(qd + 1)

    procs: list[Any] = []
    conns: list[Any] = []
    for rid in range(qd):
        conn_parent, conn_child = ctx.Pipe(duplex=False)
        proc = cast(Any, ctx).Process(
            target=_ss_reader_child,
            args=((rid, file_path, file_size, read_bytes, lane_flat, lane_off, qd,
                   sticky_lanes, ownership, winner, winner_kind, start_ns,
                   winner_exit_ns, attempts, rescue_sent, completed, lock,
                   next_global, last_start, pacer_lock, min_launch_gap_ns,
                   rescue_delay_ns, total_blocks, max_idle_s, ready_barrier,
                   start_barrier, conn_child),),
            daemon=True)
        proc.start()
        conn_child.close()
        conns.append(conn_parent)
        procs.append(proc)

    barrier_error = None
    release_ns = None
    try:
        ready_barrier.wait(ready_timeout_s)
        start_barrier.wait(ready_timeout_s)
        release_ns = int(clock_ns())
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    payloads: list[dict[str, Any]] = []
    for rid, proc in enumerate(procs):
        proc.join(timeout=ready_timeout_s)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=30.0)
    for rid, conn in enumerate(conns):
        try:
            payloads.append(conn.recv())
        except BaseException as exc:  # noqa: BLE001
            payloads.append({"reader": rid, "status": "error",
                             "error": f"recv_failed:{type(exc).__name__}",
                             "records": []})
    for conn in conns:
        try:
            conn.close()
        except BaseException:  # noqa: BLE001
            pass

    reader_errors = [{"reader": p.get("reader"), "error": p.get("error")}
                     for p in payloads if p.get("status") != "ok"]
    records = [r for p in payloads for r in (p.get("records") or [])]
    records.sort(key=lambda r: int(r["preadv_enter_ns"]))
    stale = sum(int(p.get("stale") or 0) for p in payloads)
    affinity_breaks = sum(int(p.get("affinity_breaks") or 0) for p in payloads)
    idle_no_work_ms = [float(p.get("idle_no_work_ms") or 0.0) for p in payloads]
    if not records:
        raise RuntimeError(f"no_physical_reads:{barrier_error or 'readers_failed'}")

    durations = [r["preadv_ms"] for r in records]
    useful_bytes = sum(r["bytes_returned"] for r in records if (r["bytes_returned"] or 0) > 0)
    first_enter = min(int(r["preadv_enter_ns"]) for r in records)
    last_exit = max(int(r["preadv_exit_ns"]) for r in records)
    wall_ms = (last_exit - first_enter) / 1e6

    # Logical view: one record per block, taken from its winning attempt.
    logical: list[dict[str, Any]] = []
    reader_blocks_won = [0] * qd
    for bid in range(total_blocks):
        if winner[bid] == -1:
            continue
        exit_ns = int(winner_exit_ns[bid])
        win = next((r for r in records
                    if r["block_id"] == bid and int(r["preadv_exit_ns"]) == exit_ns), None)
        rid = int(winner[bid])
        reader_blocks_won[rid] += 1
        logical.append({
            "worker": rid, "block_id": bid, "offset": bid * read_bytes,
            "length": _blen(bid),
            "accepted": "rescue" if int(winner_kind[bid]) == 2 else "primary",
            "bytes_returned": (win or {}).get("bytes_returned", 0),
            "logical_enter_ns": (win or {}).get("preadv_enter_ns", 0),
            "logical_exit_ns": exit_ns,
            "logical_ms": ((exit_ns - (win or {}).get("preadv_enter_ns", 0)) / 1e6),
        })
    logical.sort(key=lambda r: r["block_id"])
    completed = len(logical)

    completed_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    covered_bytes = sum(r["length"] for r in logical if r["accepted"] == "primary")
    ordered = sorted(logical, key=lambda r: r["offset"])
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    published_once = all(int(attempts[b]) >= 1 and winner[b] != -1
                         for b in range(total_blocks))

    claims = sorted(int(r["gate_claim_ns"]) for r in records)
    claim_gaps = [(claims[i] - claims[i - 1]) / 1e6 for i in range(1, len(claims))]
    ev: list[tuple[int, int]] = []
    for r in records:
        ev.append((int(r["preadv_enter_ns"]), 1))
        ev.append((int(r["preadv_exit_ns"]), -1))
    ev.sort()
    conc = 0
    observed_max = 0
    for _, d in ev:
        conc += d
        observed_max = max(observed_max, conc)

    rescues = [r for r in records if r.get("kind") == "rescue"]
    rescue_wins = [r for r in logical if r["accepted"] == "rescue"]
    savings = []
    for lr in rescue_wins:
        bid = lr["block_id"]
        prim = next((r for r in records
                     if r["block_id"] == bid and r.get("kind") == "primary"), None)
        if prim is not None:
            savings.append((int(prim["preadv_exit_ns"]) - int(lr["logical_exit_ns"])) / 1e6)

    dispatches = [{"reader": int(r["reader"]), "block_id": int(r["block_id"]),
                   "kind": str(r["kind"]), "seq": int(r["seq"]),
                   "lane_id": int(r["reader"]) if sticky_lanes else None,
                   "from_own_lane": bool(
                       sticky_lanes and r.get("kind") == "primary"
                       and int(r["block_id"]) in lanes[int(r["reader"])]),
                   "free_at_ns": None, "sent_ns": int(r["gate_claim_ns"]),
                   "allocator_latency_ms": None} for r in records]

    return {
        "schema_version": 1,
        "kind": "selfservice_allocator_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "selfservice_allocator",
            "rescue_delay_ns": rescue_delay_ns, "rescue_delay_ms": rescue_delay_ns / 1e6,
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv",
                "multiprocessing_start_method": ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "selfservice_allocator",
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in records if r.get("pid") is not None}),
        "reader_pids": [p.get("pid") for p in payloads],
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": reader_errors,
        "physical_reads": len(logical),
        "physical_attempts": len(records),
        "physical_amplification": (len(records) / total_blocks),
        "stale_duplicates": stale,
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "full_file_wall_ms": wall_ms,
        # Effective file throughput uses the *logically published* bytes, so
        # duplicate/rescue returns cannot inflate the reported GB/s.
        "full_file_decimal_gbps": ((completed_bytes / (wall_ms / 1000.0) / 1e9)
                                   if wall_ms else None),
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "blocks_expected": total_blocks, "blocks_completed": completed,
            "all_blocks_published_once": published_once,
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_reads_returned_full_length": all(
                (r["bytes_returned"] or 0) == r["length"] for r in logical),
            "covers_entire_file_exactly_once": bool(
                completed == total_blocks and completed_bytes == expected_bytes == file_size
                and no_overlap and contiguous),
        },
        "scheduler": {
            "selfservice": True,
            "rescue_eligible_blocks": len({r["block_id"] for r in rescues}),
            "rescue_launches": len(rescues),
            "rescue_wins": len(rescue_wins),
            "rescue_win_rate": (len(rescue_wins) / len(rescues)) if rescues else None,
            "rescue_saved_ms": savings,
            "rescue_saved_median_ms": percentile(savings, 50) if savings else None,
            "rescue_saved_max_ms": max(savings) if savings else None,
            "max_physical_qd_observed": observed_max,
            "max_physical_qd_structural": qd,
            "min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "median_global_claim_gap_ms": percentile(claim_gaps, 50) if claim_gaps else None,
            "reader_blocks_won": reader_blocks_won,
            "idle_no_work_ms": idle_no_work_ms,
            "dispatches": len(dispatches),
            "sticky_lanes": bool(sticky_lanes),
            "lane_sizes": [len(l) for l in lanes],
            "affinity_breaks": affinity_breaks,
            "lane_finish_reassignments": affinity_breaks,
            "allocator_latency_median_ms": None,
        },
        "pacer": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                  "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None},
        "launch_spacing": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                           "mean_effective_concurrency": None,
                           "max_simultaneous_in_flight": observed_max},
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": records,
        "allocator_dispatches": dispatches,
    }


def _sr_reader_child(args: tuple) -> None:
    """Self-service reader with split-range rescue reconstruction.

    Primary work is one ordinary buffered ``preadv`` of the whole logical block.
    If a block stays outstanding past ``rescue_delay_ns`` and this worker is free,
    it reconstructs that SAME logical block out of ``sub_count`` contiguous
    subranges into a private side buffer.  The subranges exactly tile the block
    (no gaps, no overlap) and the block is only published once every subrange has
    returned its full length.  No exact-size duplicate of the original is issued.
    """
    (reader_id, file_path, file_size, read_bytes, sub_count, lane_flat, lane_off,
     qd, sticky, ownership, winner, winner_kind, start_ns, winner_exit_ns,
     attempts, rescue_sent, completed, lock, next_global, last_start, pacer_lock,
     gap_ns, rescue_delay_ns, total_blocks, max_idle_s, ready_barrier,
     start_barrier, child_conn) = args
    payload: dict[str, Any] = {"reader": reader_id, "pid": os.getpid(),
                               "status": "ok", "records": [], "stale": 0,
                               "affinity_breaks": 0, "idle_no_work_ms": 0.0}
    fd = -1
    clock = time.perf_counter_ns
    try:
        preadv_fn = getattr(os, "preadv", None)
        if not callable(preadv_fn):
            raise RuntimeError("os.preadv unavailable")
        preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)
        buffer = bytearray(read_bytes)
        view = memoryview(buffer)
        # Preallocated so the rescue path performs no allocation at all.
        side = bytearray(read_bytes)
        side_view = memoryview(side)
        fd = os.open(file_path, os.O_RDONLY)
        ready_barrier.wait(300.0)
        start_barrier.wait(300.0)
        my_start = int(lane_off[reader_id])
        my_end = int(lane_off[reader_id + 1])
        cursor = my_start
        idle_since = int(clock())
        idle_total = 0.0
        seq = 0
        idle_deadline: float | None = None
        while True:
            with lock:
                if int(completed.value) >= total_blocks:
                    break
            bid = -1
            kind = "primary"
            now = int(clock())
            with lock:
                if rescue_delay_ns > 0:
                    for b in range(total_blocks):
                        if (ownership[b] == 1 and rescue_sent[b] == 0
                                and (now - int(start_ns[b])) >= rescue_delay_ns):
                            rescue_sent[b] = 1
                            bid, kind = b, "rescue"
                            break
                if bid < 0 and sticky:
                    while cursor < my_end:
                        cand = int(lane_flat[cursor])
                        cursor += 1
                        if ownership[cand] == 0:
                            bid = cand
                            break
                    if bid < 0:
                        for lid in range(qd):
                            if lid == reader_id:
                                continue
                            s = int(lane_off[lid])
                            e = int(lane_off[lid + 1])
                            while s < e:
                                cand = int(lane_flat[s])
                                s += 1
                                if ownership[cand] == 0:
                                    bid = cand
                                    payload["affinity_breaks"] += 1
                                    break
                            if bid >= 0:
                                break
                elif bid < 0:
                    b = int(next_global.value)
                    while b < total_blocks:
                        next_global.value = b + 1
                        if ownership[b] == 0:
                            bid = b
                            break
                        b = int(next_global.value)
                if bid >= 0:
                    ownership[bid] = 1
                    start_ns[bid] = now
            if bid >= 0:
                idle_since = int(clock())
            if bid < 0:
                idle_total += (int(clock()) - idle_since) / 1e6
                idle_since = int(clock())
                with lock:
                    if int(completed.value) >= total_blocks:
                        break
                if idle_deadline is None:
                    idle_deadline = time.monotonic() + max_idle_s
                elif time.monotonic() > idle_deadline:
                    break
                time.sleep(0.0002)
                continue
            idle_deadline = None
            length = min(read_bytes, file_size - bid * read_bytes)
            offset = bid * read_bytes
            seq += 1
            subs: list[list[float]] = []
            ranges: list[list[int]] = []
            # Reset per attempt: without this the list accumulates across
            # successive rescues by the same worker and misreports subreads.
            sub_ms: list[float] = []
            if kind == "primary":
                claim, gate_wait_ns = _alloc_gate(pacer_lock, last_start, gap_ns, clock)
                enter = int(clock())
                try:
                    got = int(preadv(fd, [view], offset))
                except BaseException:  # noqa: BLE001
                    got = -1
                exit_ns = int(clock())
            else:
                # Exact tiling: base/remainder distribution over the block.
                base = length // sub_count
                rem = length % sub_count
                first_claim = None
                enter = int(clock())
                got = 0
                for i in range(sub_count):
                    off_i = i * base + min(i, rem)
                    len_i = base + (1 if i < rem else 0)
                    if len_i <= 0:
                        continue
                    g, _gw = _alloc_gate(pacer_lock, last_start, gap_ns, clock)
                    if first_claim is None:
                        first_claim = int(g)
                    e_i = int(clock())
                    try:
                        n_i = int(preadv(fd, [side_view[off_i:off_i + len_i]],
                                         offset + off_i))
                    except BaseException:  # noqa: BLE001
                        n_i = -1
                    x_i = int(clock())
                    sub_ms.append((x_i - e_i) / 1e6)
                    ranges.append([off_i, len_i])
                    if n_i > 0:
                        got += n_i
                    if n_i != len_i:
                        got = -1
                        break
                exit_ns = int(clock())
                claim = first_claim if first_claim is not None else enter
                gate_wait_ns = 0
                subs = [sub_ms]
            with lock:
                attempts[bid] = int(attempts[bid]) + 1
                if winner[bid] == -1:
                    winner[bid] = reader_id
                    winner_kind[bid] = 2 if kind == "rescue" else 1
                    winner_exit_ns[bid] = exit_ns
                    completed.value = int(completed.value) + 1
                else:
                    payload["stale"] += 1
                ownership[bid] = 2
            payload["records"].append({
                "reader": reader_id, "pid": os.getpid(), "block_id": int(bid),
                "kind": str(kind), "seq": seq, "offset": offset, "length": length,
                "gate_claim_ns": int(claim), "gate_wait_ms": gate_wait_ns / 1e6,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
                "subread_ms": (subs[0] if subs else []),
                "subranges": (ranges if kind == "rescue" else []),
                "rescue_geometry_ok": bool(
                    kind == "rescue" and sum(r[1] for r in ranges) == length
                    and ranges and ranges[0][0] == 0
                    and all(ranges[i][0] + ranges[i][1] == ranges[i + 1][0]
                            for i in range(len(ranges) - 1))),
            })
        payload["idle_no_work_ms"] = idle_total
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_split_rescue_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int = 4,
    sub_count: int = 2,
    rescue_delay_ns: int = 250_000_000,
    sticky_lanes: bool = True,
    min_launch_gap_ns: int = 4_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    max_idle_s: float = 120.0,
    pacer_start_method: str = "fork",
) -> dict:
    """Whole-file pass where a stalled primary is recovered by a split re-read.

    ``sub_count`` selects the recovery request shape (2 -> 2x64 MiB, 4 -> 4x32 MiB
    for a 128 MiB block).  Normal operation is the Exp-1 self-service architecture.
    """
    import multiprocessing as mp  # noqa: PLC0415

    if not callable(getattr(os, "preadv", None)):
        raise RuntimeError("os.preadv unavailable")
    if read_bytes < 1 or qd < 1 or sub_count < 2:
        raise ValueError("read_bytes, qd, sub_count must be positive (sub_count>=2)")
    if pacer_start_method not in mp.get_all_start_methods():
        raise RuntimeError(f"start_method_unavailable:{pacer_start_method}")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {"path": file_path, "size": file_size,
                     "st_dev": getattr(stat_result, "st_dev", None),
                     "st_ino": getattr(stat_result, "st_ino", None),
                     "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)}
    total_blocks = (file_size + read_bytes - 1) // read_bytes

    def _blen(bid: int) -> int:
        return min(read_bytes, file_size - bid * read_bytes)
    expected_bytes = sum(_blen(b) for b in range(total_blocks))

    lanes: list[list[int]] = []
    if sticky_lanes:
        _base, _extra = divmod(total_blocks, qd)
        _cursor = 0
        for _lid in range(qd):
            _cnt = _base + (1 if _lid < _extra else 0)
            lanes.append(list(range(_cursor, _cursor + _cnt)))
            _cursor += _cnt
    else:
        for _lid in range(qd):
            lanes.append(list(range(_lid, total_blocks, qd)))
    lane_flat_list = [b for l in lanes for b in l]
    lane_off_list = [0]
    for l in lanes:
        lane_off_list.append(lane_off_list[-1] + len(l))

    ctx = mp.get_context(pacer_start_method)
    lock = ctx.Lock()
    ownership = ctx.Array("b", total_blocks, lock=False)
    winner = ctx.Array("i", [-1] * total_blocks, lock=False)
    winner_kind = ctx.Array("b", total_blocks, lock=False)
    start_ns = ctx.Array("q", total_blocks, lock=False)
    winner_exit_ns = ctx.Array("q", total_blocks, lock=False)
    attempts = ctx.Array("i", total_blocks, lock=False)
    rescue_sent = ctx.Array("b", total_blocks, lock=False)
    completed = ctx.Value("i", 0, lock=False)
    next_global = ctx.Value("q", 0, lock=False)
    lane_flat = ctx.Array("i", lane_flat_list, lock=False)
    lane_off = ctx.Array("i", lane_off_list, lock=False)
    last_start = ctx.Value("q", 0)
    pacer_lock = last_start.get_lock()
    ready_barrier = ctx.Barrier(qd + 1)
    start_barrier = ctx.Barrier(qd + 1)

    procs: list[Any] = []
    conns: list[Any] = []
    for rid in range(qd):
        conn_parent, conn_child = ctx.Pipe(duplex=False)
        proc = cast(Any, ctx).Process(
            target=_sr_reader_child,
            args=((rid, file_path, file_size, read_bytes, sub_count, lane_flat,
                   lane_off, qd, sticky_lanes, ownership, winner, winner_kind,
                   start_ns, winner_exit_ns, attempts, rescue_sent, completed,
                   lock, next_global, last_start, pacer_lock, min_launch_gap_ns,
                   rescue_delay_ns, total_blocks, max_idle_s, ready_barrier,
                   start_barrier, conn_child),),
            daemon=True)
        proc.start()
        conn_child.close()
        conns.append(conn_parent)
        procs.append(proc)

    barrier_error = None
    release_ns = None
    try:
        ready_barrier.wait(ready_timeout_s)
        start_barrier.wait(ready_timeout_s)
        release_ns = int(clock_ns())
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    payloads: list[dict[str, Any]] = []
    for rid, proc in enumerate(procs):
        proc.join(timeout=ready_timeout_s)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=30.0)
    for rid, conn in enumerate(conns):
        try:
            payloads.append(conn.recv())
        except BaseException as exc:  # noqa: BLE001
            payloads.append({"reader": rid, "status": "error",
                             "error": f"recv_failed:{type(exc).__name__}",
                             "records": []})
    for conn in conns:
        try:
            conn.close()
        except BaseException:  # noqa: BLE001
            pass

    reader_errors = [{"reader": p.get("reader"), "error": p.get("error")}
                     for p in payloads if p.get("status") != "ok"]
    records = [r for p in payloads for r in (p.get("records") or [])]
    records.sort(key=lambda r: int(r["preadv_enter_ns"]))
    stale = sum(int(p.get("stale") or 0) for p in payloads)
    affinity_breaks = sum(int(p.get("affinity_breaks") or 0) for p in payloads)
    idle_no_work_ms = [float(p.get("idle_no_work_ms") or 0.0) for p in payloads]
    if not records:
        raise RuntimeError(f"no_physical_reads:{barrier_error or 'readers_failed'}")

    durations = [r["preadv_ms"] for r in records]
    useful_bytes = sum(r["bytes_returned"] for r in records if (r["bytes_returned"] or 0) > 0)
    first_enter = min(int(r["preadv_enter_ns"]) for r in records)
    last_exit = max(int(r["preadv_exit_ns"]) for r in records)
    wall_ms = (last_exit - first_enter) / 1e6

    logical: list[dict[str, Any]] = []
    reader_blocks_won = [0] * qd
    for bid in range(total_blocks):
        if winner[bid] == -1:
            continue
        exit_ns = int(winner_exit_ns[bid])
        win = next((r for r in records
                    if r["block_id"] == bid and int(r["preadv_exit_ns"]) == exit_ns), None)
        rid = int(winner[bid])
        reader_blocks_won[rid] += 1
        logical.append({
            "worker": rid, "block_id": bid, "offset": bid * read_bytes,
            "length": _blen(bid),
            "accepted": "rescue" if int(winner_kind[bid]) == 2 else "primary",
            "bytes_returned": (win or {}).get("bytes_returned", 0),
            "logical_enter_ns": (win or {}).get("preadv_enter_ns", 0),
            "logical_exit_ns": exit_ns,
            "logical_ms": ((exit_ns - (win or {}).get("preadv_enter_ns", 0)) / 1e6),
        })
    logical.sort(key=lambda r: r["block_id"])
    completed = len(logical)

    completed_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    covered_bytes = sum(r["length"] for r in logical if r["accepted"] == "primary")
    ordered = sorted(logical, key=lambda r: r["offset"])
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    published_once = all(int(attempts[b]) >= 1 and winner[b] != -1
                         for b in range(total_blocks))

    claims = sorted(int(r["gate_claim_ns"]) for r in records)
    claim_gaps = [(claims[i] - claims[i - 1]) / 1e6 for i in range(1, len(claims))]
    ev: list[tuple[int, int]] = []
    for r in records:
        ev.append((int(r["preadv_enter_ns"]), 1))
        ev.append((int(r["preadv_exit_ns"]), -1))
    ev.sort()
    conc = 0
    observed_max = 0
    for _, d in ev:
        conc += d
        observed_max = max(observed_max, conc)

    rescues = [r for r in records if r.get("kind") == "rescue"]
    rescue_wins = [r for r in logical if r["accepted"] == "rescue"]
    rescue_events: list[dict[str, Any]] = []
    for rr in rescues:
        bid = rr["block_id"]
        prim = next((r for r in records
                     if r["block_id"] == bid and r.get("kind") == "primary"), None)
        won = int(winner[bid]) == int(rr["reader"])
        prim_exit = int(prim["preadv_exit_ns"]) if prim else None
        prim_enter = int(prim["preadv_enter_ns"]) if prim else None
        prim_alive_at_start = bool(prim and prim_exit is not None
                                   and int(rr["preadv_enter_ns"]) < prim_exit)
        rescue_events.append({
            "block_id": bid, "reader": int(rr["reader"]),
            "primary_reader": int(prim["reader"]) if prim else None,
            "primary_ms": ((prim_exit - prim_enter) / 1e6) if prim else None,
            "primary_still_running_when_rescue_began": prim_alive_at_start,
            "rescue_start_after_primary_ms": (
                (int(rr["preadv_enter_ns"]) - prim_enter) / 1e6 if prim else None),
            "subread_ms": rr.get("subread_ms") or [],
            "subranges": rr.get("subranges") or [],
            "rescue_geometry_ok": bool(rr.get("rescue_geometry_ok")),
            "rescue_total_ms": rr["preadv_ms"],
            "rescue_bytes": rr.get("bytes_returned"),
            "expected_bytes": rr.get("length"),
            "exact_bytes": rr.get("bytes_returned") == rr.get("length"),
            "winner": "rescue" if won else "primary",
            "ms_saved": (((prim_exit - int(rr["preadv_exit_ns"])) / 1e6)
                         if (won and prim_exit is not None) else None),
        })

    dispatches = [{"reader": int(r["reader"]), "block_id": int(r["block_id"]),
                   "kind": str(r["kind"]), "seq": int(r["seq"]),
                   "lane_id": int(r["reader"]) if sticky_lanes else None,
                   "from_own_lane": bool(
                       sticky_lanes and r.get("kind") == "primary"
                       and int(r["block_id"]) in lanes[int(r["reader"])]),
                   "free_at_ns": None, "sent_ns": int(r["gate_claim_ns"]),
                   "allocator_latency_ms": None} for r in records]

    return {
        "schema_version": 1,
        "kind": "split_rescue_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "split_rescue",
            "sub_count": sub_count,
            "split_arm": f"{sub_count}x{read_bytes // sub_count // 1024 // 1024}",
            "rescue_delay_ns": rescue_delay_ns, "rescue_delay_ms": rescue_delay_ns / 1e6,
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv",
                "multiprocessing_start_method": ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "split_rescue",
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in records if r.get("pid") is not None}),
        "reader_pids": [p.get("pid") for p in payloads],
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": reader_errors,
        "physical_reads": len(logical),
        "physical_attempts": len(records),
        "physical_amplification": (len(records) / total_blocks),
        "stale_duplicates": stale,
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": ((completed_bytes / (wall_ms / 1000.0) / 1e9)
                                   if wall_ms else None),
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "blocks_expected": total_blocks, "blocks_completed": completed,
            "all_blocks_published_once": published_once,
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_reads_returned_full_length": all(
                (r["bytes_returned"] or 0) == r["length"] for r in logical),
            "covers_entire_file_exactly_once": bool(
                completed == total_blocks and completed_bytes == expected_bytes == file_size
                and no_overlap and contiguous),
        },
        "scheduler": {
            "selfservice": True,
            "split_arm": f"{sub_count}x{read_bytes // sub_count // 1024 // 1024}",
            "sub_count": sub_count,
            "rescue_eligible_blocks": len({r["block_id"] for r in rescues}),
            "rescue_launches": len(rescues),
            "rescue_wins": len(rescue_wins),
            "rescue_win_rate": (len(rescue_wins) / len(rescues)) if rescues else None,
            "rescue_saved_ms": [e["ms_saved"] for e in rescue_events if e["ms_saved"] is not None],
            "rescue_saved_median_ms": percentile(
                [e["ms_saved"] for e in rescue_events if e["ms_saved"] is not None], 50)
                if any(e["ms_saved"] is not None for e in rescue_events) else None,
            "rescue_saved_max_ms": max([e["ms_saved"] for e in rescue_events
                                        if e["ms_saved"] is not None], default=None),
            "max_physical_qd_observed": observed_max,
            "max_physical_qd_structural": qd,
            "min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "median_global_claim_gap_ms": percentile(claim_gaps, 50) if claim_gaps else None,
            "reader_blocks_won": reader_blocks_won,
            "idle_no_work_ms": idle_no_work_ms,
            "dispatches": len(dispatches),
            "sticky_lanes": bool(sticky_lanes),
            "lane_sizes": [len(l) for l in lanes],
            "affinity_breaks": affinity_breaks,
            "lane_finish_reassignments": affinity_breaks,
            "allocator_latency_median_ms": None,
        },
        "pacer": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                  "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None},
        "launch_spacing": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                           "mean_effective_concurrency": None,
                           "max_simultaneous_in_flight": observed_max},
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": records,
        "allocator_dispatches": dispatches,
        "rescue_events": rescue_events,
    }


# --- mmap read-path support -------------------------------------------------
# Prior art in this repo: `.slim/worktrees/rx3/tools/benchmark_source_io_e14.py`
# sliced the mapping (`mapping[pos:pos+count]`), which materialises a Python bytes
# object proportional to the block.  These arms deliberately copy through the
# buffer protocol with a C-level memcpy into a preallocated destination instead.

_PAGE = 4096
_PROT_NONE = 0
_PROT_READ = 1
_MAP_SHARED = 1
_MAP_PRIVATE = 2
_MAP_FIXED = 0x10
_MAP_ANONYMOUS = 0x20
_MAP_POPULATE = 0x08000  # Linux
_MADV_WILLNEED = 3

try:
    import ctypes as _ct

    _LIBC = _ct.CDLL(None, use_errno=True)
    _LIBC.memcpy.restype = _ct.c_void_p
    _LIBC.memcpy.argtypes = [_ct.c_void_p, _ct.c_void_p, _ct.c_size_t]
    _LIBC.madvise.restype = _ct.c_int
    _LIBC.madvise.argtypes = [_ct.c_void_p, _ct.c_size_t, _ct.c_int]
    _LIBC.mmap.restype = _ct.c_void_p
    _LIBC.mmap.argtypes = [_ct.c_void_p, _ct.c_size_t, _ct.c_int, _ct.c_int,
                           _ct.c_int, _ct.c_longlong]
    _LIBC.munmap.restype = _ct.c_int
    _LIBC.munmap.argtypes = [_ct.c_void_p, _ct.c_size_t]
except BaseException:  # noqa: BLE001
    _LIBC = None


def _make_cpu_clock_probes() -> list[tuple[str, Any]]:
    """Candidate CPU-time sources, most precise first; each returns int nanoseconds.

    gVisor stubs some clocks: `time.thread_time_ns()` (CLOCK_THREAD_CPUTIME_ID)
    and `time.process_time_ns()` (CLOCK_PROCESS_CPUTIME_ID) can both fail to
    advance.  Callers MUST verify a probe actually advances across real CPU work
    before trusting it, otherwise a stubbed clock is silently read as zero CPU.
    """
    probes: list[tuple[str, Any]] = []

    if hasattr(time, "thread_time_ns"):
        probes.append(("thread", lambda: int(time.thread_time_ns())))
    if hasattr(time, "process_time_ns"):
        probes.append(("process", lambda: int(time.process_time_ns())))

    # getrusage: struct rusage starts with ru_utime then ru_stime, two 16-byte
    # struct timevals on 64-bit.  RUSAGE_THREAD=1 (Linux), RUSAGE_SELF=0.
    if _LIBC is not None and hasattr(_LIBC, "getrusage"):
        try:
            import struct as _struct  # noqa: PLC0415
            _LIBC.getrusage.restype = _ct.c_int
            _LIBC.getrusage.argtypes = [_ct.c_int, _ct.c_void_p]

            def _rusage_ns(who: int) -> int:
                buf = _ct.create_string_buffer(256)
                if _LIBC.getrusage(who, _ct.byref(buf)) != 0:
                    return 0
                ut = _struct.unpack_from("<qq", buf, 0)
                st = _struct.unpack_from("<qq", buf, 16)
                return int((ut[0] + st[0]) * 1_000_000_000 + (ut[1] + st[1]) * 1000)

            probes.append(("rusage_thread", lambda: _rusage_ns(1)))
            probes.append(("rusage_self", lambda: _rusage_ns(0)))
        except BaseException:  # noqa: BLE001
            pass

    # /proc/self/stat utime(14)+stime(15), in clock ticks.
    try:
        _hz = float(os.sysconf("SC_CLK_TCK")) or 100.0
    except BaseException:  # noqa: BLE001
        _hz = 100.0
    _ns_per_tick = 1_000_000_000.0 / _hz

    def _procstat_ns() -> int:
        with open("/proc/self/stat", "rb") as fh:
            parts = fh.read().rsplit(b")", 1)[1].split()
        return int((int(parts[11]) + int(parts[12])) * _ns_per_tick)

    probes.append(("procstat", _procstat_ns))
    return probes


def _slot_still_mapped(base: int, length: int) -> bool:
    """Real leak check: is any part of [base, base+length) still in /proc/self/maps?"""
    if not base or length <= 0:
        return False
    try:
        with open("/proc/self/maps", "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                head = line.split(None, 1)[0]
                if "-" not in head:
                    continue
                lo_s, hi_s = head.split("-", 1)
                lo, hi = int(lo_s, 16), int(hi_s, 16)
                if lo < base + length and base < hi:
                    return True
    except BaseException:  # noqa: BLE001
        return False
    return False


def _cpu_topology(cpus: list[int]) -> dict[str, Any]:
    """Best-effort physical-core topology for the given logical CPUs.

    gVisor may not expose /sys topology; report exactly what is readable and
    flag when it is unavailable rather than guessing.
    """
    out: dict[str, Any] = {"available": False, "core_ids": None, "packages": None,
                           "siblings": None, "distinct_physical_cores": None,
                           "note": None}
    core_ids, pkgs, sibs = {}, {}, {}
    for c in cpus:
        base = f"/sys/devices/system/cpu/cpu{c}/topology"
        try:
            with open(f"{base}/core_id") as fh:
                core_ids[c] = int(fh.read().strip())
            with open(f"{base}/physical_package_id") as fh:
                pkgs[c] = int(fh.read().strip())
            with open(f"{base}/thread_siblings_list") as fh:
                sibs[c] = fh.read().strip()
        except BaseException:  # noqa: BLE001
            return out
    out["available"] = True
    out["core_ids"] = core_ids
    out["packages"] = pkgs
    out["siblings"] = sibs
    out["distinct_physical_cores"] = len({(pkgs[c], core_ids[c]) for c in cpus})
    out["note"] = ("distinct (package,core) pairs among the assigned CPUs"
                   if out["distinct_physical_cores"] == len(cpus)
                   else "assigned CPUs share physical cores (SMT siblings)")
    return out


def _fault_counters():
    """(minor, major) page faults for this process, or (None, None)."""
    try:
        with open("/proc/self/stat", "rb") as fh:
            parts = fh.read().rsplit(b")", 1)[1].split()
        return int(parts[7]), int(parts[9])
    except BaseException:  # noqa: BLE001
        return None, None


def _shared_region_report(objs: dict) -> list[dict]:
    """Real address and size of each shared object, for memory-layout auditing."""
    out = []
    for name, obj in objs.items():
        addr = size = None
        for cand in (obj, getattr(obj, "get_obj", lambda: None)()):
            if cand is None:
                continue
            try:
                addr = _ct.addressof(cand)
                size = _ct.sizeof(cand)
                break
            except BaseException:  # noqa: BLE001
                continue
        out.append({"name": name, "addr": addr, "bytes": size})
    return out


def _mm_reader_child(args: tuple) -> None:
    """Self-service reader over an alternate mmap read path.

    mode="m0" persistent read-only mapping + C-level memcpy
    mode="m1" as m0 plus madvise(MADV_WILLNEED) on the exact upcoming range
    mode="m2" exact page-aligned window mmap with MAP_POPULATE, then memcpy+munmap
    """
    (reader_id, file_path, file_size, read_bytes, mmap_mode, lane_flat, lane_off,
     qd, sticky, ownership, winner, winner_kind, start_ns, winner_exit_ns,
     attempts, completed, lock, next_global, last_start, pacer_lock, gap_ns,
     total_blocks, max_idle_s, ready_count, go, child_conn) = args
    payload: dict[str, Any] = {"reader": reader_id, "pid": os.getpid(),
                               "status": "ok", "records": [], "stale": 0,
                               "affinity_breaks": 0, "idle_no_work_ms": 0.0,
                               "minor_faults": None, "major_faults": None}
    fd = -1
    mm_obj = None
    mm_base = 0
    clock = time.perf_counter_ns
    try:
        if _LIBC is None:
            raise RuntimeError("libc_unavailable")
        dest = bytearray(read_bytes)
        dest_addr = _ct.addressof(_ct.c_char.from_buffer(dest))
        fd = os.open(file_path, os.O_RDONLY)
        if mmap_mode in ("m0", "m1"):
            # Persistent read-only mapping taken through libc so we own the raw
            # address: ctypes.from_buffer() needs a *writable* buffer and rejects
            # an ACCESS_READ mmap.  No MAP_POPULATE, so pages fault in on demand.
            mm_base = int(_LIBC.mmap(None, file_size, _PROT_READ,
                                     _MAP_PRIVATE, fd, 0))
            if mm_base in (0, -1) or mm_base == 0xFFFFFFFFFFFFFFFF:
                raise OSError(f"persistent_mmap_failed errno={_ct.get_errno()}")
        f0 = _fault_counters()
        with lock:
            ready_count.value = int(ready_count.value) + 1
        while int(go.value) == 0:
            time.sleep(0.001)
        my_start = int(lane_off[reader_id])
        my_end = int(lane_off[reader_id + 1])
        cursor = my_start
        idle_since = int(clock())
        idle_total = 0.0
        seq = 0
        idle_deadline: float | None = None
        while True:
            with lock:
                if int(completed.value) >= total_blocks:
                    break
            bid = -1
            now = int(clock())
            with lock:
                if sticky:
                    while cursor < my_end:
                        cand = int(lane_flat[cursor])
                        cursor += 1
                        if ownership[cand] == 0:
                            bid = cand
                            break
                    if bid < 0:
                        for lid in range(qd):
                            if lid == reader_id:
                                continue
                            s = int(lane_off[lid])
                            e = int(lane_off[lid + 1])
                            while s < e:
                                cand = int(lane_flat[s])
                                s += 1
                                if ownership[cand] == 0:
                                    bid = cand
                                    payload["affinity_breaks"] += 1
                                    break
                            if bid >= 0:
                                break
                else:
                    b = int(next_global.value)
                    while b < total_blocks:
                        next_global.value = b + 1
                        if ownership[b] == 0:
                            bid = b
                            break
                        b = int(next_global.value)
                if bid >= 0:
                    ownership[bid] = 1
                    start_ns[bid] = now
            if bid >= 0:
                idle_since = int(clock())
            if bid < 0:
                idle_total += (int(clock()) - idle_since) / 1e6
                idle_since = int(clock())
                with lock:
                    if int(completed.value) >= total_blocks:
                        break
                if idle_deadline is None:
                    idle_deadline = time.monotonic() + max_idle_s
                elif time.monotonic() > idle_deadline:
                    break
                time.sleep(0.0002)
                continue
            idle_deadline = None
            length = min(read_bytes, file_size - bid * read_bytes)
            offset = bid * read_bytes
            seq += 1
            claim, gate_wait_ns = _alloc_gate(pacer_lock, last_start, gap_ns, clock)
            enter = int(clock())
            advice_ms = 0.0
            map_ms = 0.0
            unmap_ms = 0.0
            copy_ms = 0.0
            err = None
            try:
                if mmap_mode == "m0":
                    t = int(clock())
                    _LIBC.memcpy(dest_addr, mm_base + offset, length)
                    copy_ms = (int(clock()) - t) / 1e6
                elif mmap_mode == "m1":
                    a_start = offset & ~(_PAGE - 1)
                    a_len = ((offset + length - a_start + _PAGE - 1) // _PAGE) * _PAGE
                    t = int(clock())
                    _LIBC.madvise(mm_base + a_start, a_len, _MADV_WILLNEED)
                    advice_ms = (int(clock()) - t) / 1e6
                    t = int(clock())
                    _LIBC.memcpy(dest_addr, mm_base + offset, length)
                    copy_ms = (int(clock()) - t) / 1e6
                else:  # m2: exact window, populated
                    w_start = offset & ~(_PAGE - 1)
                    w_len = ((offset + length - w_start + _PAGE - 1) // _PAGE) * _PAGE
                    t = int(clock())
                    addr = _LIBC.mmap(None, w_len, _PROT_READ,
                                      _MAP_PRIVATE | _MAP_POPULATE, fd, w_start)
                    if addr in (0, None) or addr == 0xFFFFFFFFFFFFFFFF:
                        raise OSError(f"mmap_failed errno={_ct.get_errno()}")
                    map_ms = (int(clock()) - t) / 1e6
                    t = int(clock())
                    _LIBC.memcpy(dest_addr, int(addr) + (offset - w_start), length)
                    copy_ms = (int(clock()) - t) / 1e6
                    t = int(clock())
                    _LIBC.munmap(int(addr), w_len)
                    unmap_ms = (int(clock()) - t) / 1e6
                got = length
            except BaseException as exc:  # noqa: BLE001
                got = -1
                err = f"{type(exc).__name__}:{str(exc)[:200]}"
            exit_ns = int(clock())
            with lock:
                attempts[bid] = int(attempts[bid]) + 1
                if winner[bid] == -1:
                    winner[bid] = reader_id
                    winner_kind[bid] = 1
                    winner_exit_ns[bid] = exit_ns
                    completed.value = int(completed.value) + 1
                else:
                    payload["stale"] += 1
                ownership[bid] = 2
            payload["records"].append({
                "reader": reader_id, "pid": os.getpid(), "block_id": int(bid),
                "kind": "primary", "seq": seq, "offset": offset, "length": length,
                "gate_claim_ns": int(claim), "gate_wait_ms": gate_wait_ns / 1e6,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
                "advice_ms": advice_ms, "map_ms": map_ms, "copy_ms": copy_ms,
                "unmap_ms": unmap_ms, "error": err,
            })
        payload["idle_no_work_ms"] = idle_total
        f1 = _fault_counters()
        if f0[0] is not None and f1[0] is not None:
            payload["minor_faults"] = f1[0] - f0[0]
            payload["major_faults"] = f1[1] - f0[1]
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            if mm_obj is not None:
                mm_obj.close()
        except BaseException:  # noqa: BLE001
            pass
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_mmap_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int = 4,
    mmap_mode: str = "m0",
    sticky_lanes: bool = True,
    min_launch_gap_ns: int = 4_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    max_idle_s: float = 120.0,
    pacer_start_method: str = "fork",
) -> dict:
    """Whole-file pass over an alternate mmap read path (see `_mm_reader_child`)."""
    import multiprocessing as mp  # noqa: PLC0415

    if mmap_mode not in ("m0", "m1", "m2"):
        raise ValueError("mmap_mode must be m0, m1 or m2")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if pacer_start_method not in mp.get_all_start_methods():
        raise RuntimeError(f"start_method_unavailable:{pacer_start_method}")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {"path": file_path, "size": file_size,
                     "st_dev": getattr(stat_result, "st_dev", None),
                     "st_ino": getattr(stat_result, "st_ino", None),
                     "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)}
    total_blocks = (file_size + read_bytes - 1) // read_bytes

    def _blen(bid: int) -> int:
        return min(read_bytes, file_size - bid * read_bytes)
    expected_bytes = sum(_blen(b) for b in range(total_blocks))

    lanes: list[list[int]] = []
    if sticky_lanes:
        _base, _extra = divmod(total_blocks, qd)
        _cursor = 0
        for _lid in range(qd):
            _cnt = _base + (1 if _lid < _extra else 0)
            lanes.append(list(range(_cursor, _cursor + _cnt)))
            _cursor += _cnt
    else:
        for _lid in range(qd):
            lanes.append(list(range(_lid, total_blocks, qd)))
    lane_flat_list = [b for l in lanes for b in l]
    lane_off_list = [0]
    for l in lanes:
        lane_off_list.append(lane_off_list[-1] + len(l))

    ctx = mp.get_context(pacer_start_method)
    lock = ctx.Lock()
    ownership = ctx.Array("b", total_blocks, lock=False)
    winner = ctx.Array("i", [-1] * total_blocks, lock=False)
    winner_kind = ctx.Array("b", total_blocks, lock=False)
    start_ns = ctx.Array("q", total_blocks, lock=False)
    winner_exit_ns = ctx.Array("q", total_blocks, lock=False)
    attempts = ctx.Array("i", total_blocks, lock=False)
    completed = ctx.Value("i", 0, lock=False)
    next_global = ctx.Value("q", 0, lock=False)
    lane_flat = ctx.Array("i", lane_flat_list, lock=False)
    lane_off = ctx.Array("i", lane_off_list, lock=False)
    last_start = ctx.Value("q", 0)
    pacer_lock = last_start.get_lock()
    ready_count = ctx.Value("i", 0, lock=False)
    go = ctx.Value("i", 0, lock=False)

    procs: list[Any] = []
    conns: list[Any] = []
    for rid in range(qd):
        conn_parent, conn_child = ctx.Pipe(duplex=False)
        proc = cast(Any, ctx).Process(
            target=_mm_reader_child,
            args=((rid, file_path, file_size, read_bytes, mmap_mode, lane_flat,
                   lane_off, qd, sticky_lanes, ownership, winner, winner_kind,
                   start_ns, winner_exit_ns, attempts, completed, lock,
                   next_global, last_start, pacer_lock, min_launch_gap_ns,
                   total_blocks, max_idle_s, ready_count, go, conn_child),),
            daemon=True)
        proc.start()
        conn_child.close()
        conns.append(conn_parent)
        procs.append(proc)

    # Polled readiness rather than a Barrier: a reader that dies during setup is
    # detected immediately instead of surfacing as a 300 s BrokenBarrierError.
    barrier_error = None
    release_ns = None
    deadline = time.monotonic() + ready_timeout_s
    try:
        while int(ready_count.value) < qd:
            dead = [i for i, pr in enumerate(procs) if not pr.is_alive()]
            if dead:
                errs = []
                for i in dead:
                    try:
                        errs.append({i: conns[i].recv()})
                    except BaseException as exc:  # noqa: BLE001
                        errs.append({i: f"no_payload:{type(exc).__name__}"})
                raise RuntimeError(f"reader_died_during_setup:{dead}:{errs}")
            if time.monotonic() > deadline:
                raise TimeoutError("readers_not_ready")
            time.sleep(0.002)
        release_ns = int(clock_ns())
        go.value = 1
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    payloads: list[dict[str, Any]] = []
    for rid, proc in enumerate(procs):
        proc.join(timeout=ready_timeout_s)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=30.0)
    for rid, conn in enumerate(conns):
        try:
            payloads.append(conn.recv())
        except BaseException as exc:  # noqa: BLE001
            payloads.append({"reader": rid, "status": "error",
                             "error": f"recv_failed:{type(exc).__name__}",
                             "records": []})
    for conn in conns:
        try:
            conn.close()
        except BaseException:  # noqa: BLE001
            pass

    reader_errors = [{"reader": p.get("reader"), "error": p.get("error")}
                     for p in payloads if p.get("status") != "ok"]
    records = [r for p in payloads for r in (p.get("records") or [])]
    records.sort(key=lambda r: int(r["preadv_enter_ns"]))
    stale = sum(int(p.get("stale") or 0) for p in payloads)
    affinity_breaks = sum(int(p.get("affinity_breaks") or 0) for p in payloads)
    idle_no_work_ms = [float(p.get("idle_no_work_ms") or 0.0) for p in payloads]
    if not records:
        raise RuntimeError(f"no_reads:{barrier_error or 'readers_failed'}")

    durations = [r["preadv_ms"] for r in records]
    useful_bytes = sum(r["bytes_returned"] for r in records if (r["bytes_returned"] or 0) > 0)
    first_enter = min(int(r["preadv_enter_ns"]) for r in records)
    last_exit = max(int(r["preadv_exit_ns"]) for r in records)
    wall_ms = (last_exit - first_enter) / 1e6

    logical: list[dict[str, Any]] = []
    reader_blocks_won = [0] * qd
    for bid in range(total_blocks):
        if winner[bid] == -1:
            continue
        exit_ns = int(winner_exit_ns[bid])
        win = next((r for r in records
                    if r["block_id"] == bid and int(r["preadv_exit_ns"]) == exit_ns), None)
        rid = int(winner[bid])
        reader_blocks_won[rid] += 1
        logical.append({
            "worker": rid, "block_id": bid, "offset": bid * read_bytes,
            "length": _blen(bid), "accepted": "primary",
            "bytes_returned": (win or {}).get("bytes_returned", 0),
            "logical_enter_ns": (win or {}).get("preadv_enter_ns", 0),
            "logical_exit_ns": exit_ns,
            "logical_ms": ((exit_ns - (win or {}).get("preadv_enter_ns", 0)) / 1e6),
        })
    logical.sort(key=lambda r: r["block_id"])
    completed = len(logical)

    completed_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    covered_bytes = sum(r["length"] for r in logical)
    ordered = sorted(logical, key=lambda r: r["offset"])
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    published_once = all(int(attempts[b]) >= 1 and winner[b] != -1
                         for b in range(total_blocks))

    claims = sorted(int(r["gate_claim_ns"]) for r in records)
    claim_gaps = [(claims[i] - claims[i - 1]) / 1e6 for i in range(1, len(claims))]
    ev: list[tuple[int, int]] = []
    for r in records:
        ev.append((int(r["preadv_enter_ns"]), 1))
        ev.append((int(r["preadv_exit_ns"]), -1))
    ev.sort()
    conc = 0
    observed_max = 0
    for _, d in ev:
        conc += d
        observed_max = max(observed_max, conc)

    advice = [float(r.get("advice_ms") or 0.0) for r in records]
    maps = [float(r.get("map_ms") or 0.0) for r in records]
    copies = [float(r.get("copy_ms") or 0.0) for r in records]
    unmaps = [float(r.get("unmap_ms") or 0.0) for r in records]

    return {
        "schema_version": 1,
        "kind": "mmap_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "mmap_path", "mmap_mode": mmap_mode,
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": f"mmap:{mmap_mode}",
                "multiprocessing_start_method": ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "mmap_path",
        "mmap_mode": mmap_mode,
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in records if r.get("pid") is not None}),
        "reader_pids": [p.get("pid") for p in payloads],
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": reader_errors,
        "physical_reads": len(logical),
        "physical_attempts": len(records),
        "physical_amplification": (len(records) / total_blocks),
        "stale_duplicates": stale,
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": ((completed_bytes / (wall_ms / 1000.0) / 1e9)
                                   if wall_ms else None),
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "blocks_expected": total_blocks, "blocks_completed": completed,
            "all_blocks_published_once": published_once,
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_reads_returned_full_length": all(
                (r["bytes_returned"] or 0) == r["length"] for r in logical),
            "covers_entire_file_exactly_once": bool(
                completed == total_blocks and completed_bytes == expected_bytes == file_size
                and no_overlap and contiguous),
        },
        "scheduler": {
            "selfservice": True, "mmap_mode": mmap_mode,
            "max_physical_qd_observed": observed_max,
            "max_physical_qd_structural": qd,
            "min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "median_global_claim_gap_ms": percentile(claim_gaps, 50) if claim_gaps else None,
            "reader_blocks_won": reader_blocks_won,
            "idle_no_work_ms": idle_no_work_ms,
            "dispatches": len(records),
            "sticky_lanes": bool(sticky_lanes),
            "lane_sizes": [len(l) for l in lanes],
            "affinity_breaks": affinity_breaks,
            "allocator_latency_median_ms": None,
        },
        "pacer": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                  "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None},
        "launch_spacing": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                           "mean_effective_concurrency": None,
                           "max_simultaneous_in_flight": observed_max},
        "mmap_timing": {
            "advice_median_ms": percentile(advice, 50), "advice_max_ms": max(advice),
            "map_median_ms": percentile(maps, 50), "map_max_ms": max(maps),
            "copy_median_ms": percentile(copies, 50), "copy_max_ms": max(copies),
            "unmap_median_ms": percentile(unmaps, 50), "unmap_max_ms": max(unmaps),
        },
        "faults": {
            "minor_total": sum(int(p.get("minor_faults") or 0) for p in payloads),
            "major_total": sum(int(p.get("major_faults") or 0) for p in payloads),
            "per_reader": [{"reader": p.get("reader"),
                            "minor": p.get("minor_faults"),
                            "major": p.get("major_faults")} for p in payloads],
        },
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": records,
        "allocator_dispatches": [],
    }


def _od_reader_child(args: tuple) -> None:
    """Buffered worker that can also hold the prearmed O_DIRECT spare role.

    Healthy state: qd buffered workers do all normal work; one spare is dormant.
    On a >=250 ms still-running primary the spare re-reads the SAME logical block
    with O_DIRECT (pre-opened FD, preallocated page-aligned buffer - nothing is
    created on the rescue path).

    Lifetime rule (deliberately different from the old slot_busy design):
      * a rescue win publishes immediately and the stale original may never
        overwrite current state;
      * the promoted spare becomes a normal buffered worker while the original
        is still stuck, so useful concurrency stays at qd;
      * the returning stale original then takes over the spare role, so the
        spare slot is refilled instead of being lost.
    """
    (reader_id, file_path, file_size, read_bytes, is_spare, lane_flat, lane_off,
     qd, sticky, ownership, winner, winner_kind, start_ns, winner_exit_ns,
     attempts, rescue_sent, completed, lock, next_global, last_start, pacer_lock,
     gap_ns, rescue_delay_ns, total_blocks, max_idle_s, spare_promoted,
     spare_refilled, ready_count, go, child_conn) = args
    payload: dict[str, Any] = {"reader": reader_id, "pid": os.getpid(),
                               "status": "ok", "records": [], "stale": 0,
                               "affinity_breaks": 0, "idle_no_work_ms": 0.0,
                               "role_flips": 0}
    fd_buf = -1
    fd_dir = -1
    abuf = None
    clock = time.perf_counter_ns
    try:
        if _LIBC is None:
            raise RuntimeError("libc_unavailable")
        preadv_fn = getattr(os, "preadv", None)
        if not callable(preadv_fn):
            raise RuntimeError("os.preadv unavailable")
        od_events: list[dict[str, Any]] = []
        buf = bytearray(read_bytes)
        view = memoryview(buf)
        # Prearmed O_DIRECT resources: page-aligned anonymous buffer + O_DIRECT FD.
        abuf = mmap.mmap(-1, read_bytes + _PAGE)
        aaddr = _ct.addressof(_ct.c_char.from_buffer(abuf))
        av = memoryview(abuf)
        # Provenance: record real addresses so buffer independence is demonstrated,
        # not assumed.  buf is the buffered primary destination, abuf the O_DIRECT
        # rescue destination; both are private per-process mappings.
        payload["buf_addr"] = _ct.addressof(_ct.c_char.from_buffer(buf))
        payload["buf_len"] = len(buf)
        payload["abuf_addr"] = aaddr
        payload["abuf_len"] = len(abuf)
        fd_buf = os.open(file_path, os.O_RDONLY)
        try:
            fd_dir = os.open(file_path, os.O_RDONLY | getattr(os, "O_DIRECT", 0))
        except BaseException:  # noqa: BLE001
            fd_dir = -1
        with lock:
            ready_count.value = int(ready_count.value) + 1
        while int(go.value) == 0:
            time.sleep(0.001)
        my_start = int(lane_off[reader_id]) if reader_id < qd else 0
        my_end = int(lane_off[reader_id + 1]) if reader_id < qd else 0
        cursor = my_start
        role = "spare" if is_spare else "worker"
        idle_since = int(clock())
        idle_total = 0.0
        seq = 0
        idle_deadline: float | None = None
        while True:
            with lock:
                if int(completed.value) >= total_blocks:
                    break
            if role == "spare":
                target = -1
                now = int(clock())
                with lock:
                    if rescue_delay_ns > 0:
                        for b in range(total_blocks):
                            if (ownership[b] == 1 and rescue_sent[b] == 0
                                    and (now - int(start_ns[b])) >= rescue_delay_ns):
                                rescue_sent[b] = 1
                                target = b
                                break
                if target < 0:
                    time.sleep(0.0005)
                    continue
                length = min(read_bytes, file_size - target * read_bytes)
                offset = target * read_bytes
                seq += 1
                rounded = ((length + _PAGE - 1) // _PAGE) * _PAGE
                enter = int(clock())
                got = -1
                err = None
                try:
                    if fd_dir < 0:
                        raise OSError("odirect_fd_unavailable")
                    got = int(preadv_fn(fd_dir, [av[0:rounded]], offset))
                except BaseException as exc:  # noqa: BLE001
                    err = f"{type(exc).__name__}:{str(exc)[:160]}"
                exit_ns = int(clock())
                valid = (got >= length)
                won = False
                with lock:
                    attempts[target] = int(attempts[target]) + 1
                    if valid and winner[target] == -1:
                        winner[target] = reader_id
                        winner_kind[target] = 2
                        winner_exit_ns[target] = exit_ns
                        completed.value = int(completed.value) + 1
                        won = True
                    else:
                        payload["stale"] += 1
                    if winner[target] != -1:
                        ownership[target] = 2
                    if won:
                        spare_promoted.value = 1
                od_events.append({
                    "block_id": int(target), "kind": "odirect_rescue",
                    "reader": reader_id, "enter_ns": enter, "exit_ns": exit_ns,
                    "odirect_ms": (exit_ns - enter) / 1e6,
                    "bytes": got, "expected": length, "valid": bool(valid),
                    "won": bool(won), "error": err,
                    "alignment_rounded_bytes": int(rounded - length),
                })
                payload["records"].append({
                    "reader": reader_id, "pid": os.getpid(),
                    "block_id": int(target), "kind": "rescue", "seq": seq,
                    "offset": offset, "length": length, "gate_claim_ns": enter,
                    "gate_wait_ms": 0.0, "preadv_enter_ns": enter,
                    "preadv_exit_ns": exit_ns,
                    "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
                })
                if won:
                    role = "worker"
                    payload["role_flips"] += 1
                continue
            # --- normal buffered worker -------------------------------------
            bid = -1
            now = int(clock())
            with lock:
                if sticky and reader_id < qd:
                    while cursor < my_end:
                        cand = int(lane_flat[cursor])
                        cursor += 1
                        if ownership[cand] == 0:
                            bid = cand
                            break
                    if bid < 0:
                        for lid in range(qd):
                            if lid == reader_id:
                                continue
                            s = int(lane_off[lid])
                            e = int(lane_off[lid + 1])
                            while s < e:
                                cand = int(lane_flat[s])
                                s += 1
                                if ownership[cand] == 0:
                                    bid = cand
                                    payload["affinity_breaks"] += 1
                                    break
                            if bid >= 0:
                                break
                else:
                    b = int(next_global.value)
                    while b < total_blocks:
                        next_global.value = b + 1
                        if ownership[b] == 0:
                            bid = b
                            break
                        b = int(next_global.value)
                if bid >= 0:
                    ownership[bid] = 1
                    start_ns[bid] = now
            if bid >= 0:
                idle_since = int(clock())
            if bid < 0:
                idle_total += (int(clock()) - idle_since) / 1e6
                idle_since = int(clock())
                with lock:
                    if int(completed.value) >= total_blocks:
                        break
                if idle_deadline is None:
                    idle_deadline = time.monotonic() + max_idle_s
                elif time.monotonic() > idle_deadline:
                    break
                time.sleep(0.0002)
                continue
            idle_deadline = None
            length = min(read_bytes, file_size - bid * read_bytes)
            offset = bid * read_bytes
            seq += 1
            claim, gate_wait_ns = _alloc_gate(pacer_lock, last_start, gap_ns, clock)
            enter = int(clock())
            try:
                got = int(preadv_fn(fd_buf, [view if length == read_bytes
                                             else view[:length]], offset))
            except BaseException:  # noqa: BLE001
                got = -1
            exit_ns = int(clock())
            stale_here = False
            with lock:
                attempts[bid] = int(attempts[bid]) + 1
                if winner[bid] == -1:
                    winner[bid] = reader_id
                    winner_kind[bid] = 1
                    winner_exit_ns[bid] = exit_ns
                    completed.value = int(completed.value) + 1
                else:
                    payload["stale"] += 1
                    stale_here = True
                ownership[bid] = 2
            payload["records"].append({
                "reader": reader_id, "pid": os.getpid(), "block_id": int(bid),
                "kind": "primary", "seq": seq, "offset": offset, "length": length,
                "gate_claim_ns": int(claim), "gate_wait_ms": gate_wait_ns / 1e6,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
            })
            if stale_here:
                take = False
                with lock:
                    if int(spare_promoted.value) == 1 and int(spare_refilled.value) == 0:
                        spare_refilled.value = 1
                        take = True
                if take:
                    role = "spare"
                    payload["role_flips"] += 1
        payload["idle_no_work_ms"] = idle_total
        payload["odirect_events"] = od_events
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        for h in (abuf,):
            try:
                if h is not None:
                    h.close()
            except BaseException:  # noqa: BLE001
                pass
        for fdx in (fd_buf, fd_dir):
            try:
                if fdx >= 0:
                    os.close(fdx)
            except BaseException:  # noqa: BLE001
                pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_odirect_rescue_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int = 4,
    rescue_delay_ns: int = 250_000_000,
    sticky_lanes: bool = True,
    min_launch_gap_ns: int = 4_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    max_idle_s: float = 120.0,
    pacer_start_method: str = "fork",
) -> dict:
    """qd buffered preadv workers plus one dormant, prearmed O_DIRECT spare."""
    import multiprocessing as mp  # noqa: PLC0415

    preadv_fn = getattr(os, "preadv", None)
    if not callable(preadv_fn):
        raise RuntimeError("os.preadv unavailable")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if pacer_start_method not in mp.get_all_start_methods():
        raise RuntimeError(f"start_method_unavailable:{pacer_start_method}")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {"path": file_path, "size": file_size,
                     "st_dev": getattr(stat_result, "st_dev", None),
                     "st_ino": getattr(stat_result, "st_ino", None),
                     "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)}
    total_blocks = (file_size + read_bytes - 1) // read_bytes

    def _blen(bid: int) -> int:
        return min(read_bytes, file_size - bid * read_bytes)
    expected_bytes = sum(_blen(b) for b in range(total_blocks))

    lanes: list[list[int]] = []
    if sticky_lanes:
        _base, _extra = divmod(total_blocks, qd)
        _cursor = 0
        for _lid in range(qd):
            _cnt = _base + (1 if _lid < _extra else 0)
            lanes.append(list(range(_cursor, _cursor + _cnt)))
            _cursor += _cnt
    else:
        for _lid in range(qd):
            lanes.append(list(range(_lid, total_blocks, qd)))
    lane_flat_list = [b for l in lanes for b in l]
    lane_off_list = [0]
    for l in lanes:
        lane_off_list.append(lane_off_list[-1] + len(l))

    ctx = mp.get_context(pacer_start_method)
    lock = ctx.Lock()
    ownership = ctx.Array("b", total_blocks, lock=False)
    winner = ctx.Array("i", [-1] * total_blocks, lock=False)
    winner_kind = ctx.Array("b", total_blocks, lock=False)
    start_ns = ctx.Array("q", total_blocks, lock=False)
    winner_exit_ns = ctx.Array("q", total_blocks, lock=False)
    attempts = ctx.Array("i", total_blocks, lock=False)
    rescue_sent = ctx.Array("b", total_blocks, lock=False)
    completed = ctx.Value("i", 0, lock=False)
    next_global = ctx.Value("q", 0, lock=False)
    lane_flat = ctx.Array("i", lane_flat_list, lock=False)
    lane_off = ctx.Array("i", lane_off_list, lock=False)
    last_start = ctx.Value("q", 0)
    pacer_lock = last_start.get_lock()
    spare_promoted = ctx.Value("i", 0, lock=False)
    spare_refilled = ctx.Value("i", 0, lock=False)
    ready_count = ctx.Value("i", 0, lock=False)
    go = ctx.Value("i", 0, lock=False)

    procs: list[Any] = []
    conns: list[Any] = []
    for rid in range(qd + 1):  # qd workers + 1 spare
        conn_parent, conn_child = ctx.Pipe(duplex=False)
        proc = cast(Any, ctx).Process(
            target=_od_reader_child,
            args=((rid, file_path, file_size, read_bytes, rid == qd, lane_flat,
                   lane_off, qd, sticky_lanes, ownership, winner, winner_kind,
                   start_ns, winner_exit_ns, attempts, rescue_sent, completed,
                   lock, next_global, last_start, pacer_lock, min_launch_gap_ns,
                   rescue_delay_ns, total_blocks, max_idle_s, spare_promoted,
                   spare_refilled, ready_count, go, conn_child),),
            daemon=True)
        proc.start()
        conn_child.close()
        conns.append(conn_parent)
        procs.append(proc)

    barrier_error = None
    release_ns = None
    deadline = time.monotonic() + ready_timeout_s
    try:
        while int(ready_count.value) < qd + 1:
            dead = [i for i, pr in enumerate(procs) if not pr.is_alive()]
            if dead:
                raise RuntimeError(f"reader_died_during_setup:{dead}")
            if time.monotonic() > deadline:
                raise TimeoutError("readers_not_ready")
            time.sleep(0.002)
        release_ns = int(clock_ns())
        go.value = 1
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    payloads: list[dict[str, Any]] = []
    for rid, proc in enumerate(procs):
        proc.join(timeout=ready_timeout_s)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=30.0)
    for rid, conn in enumerate(conns):
        try:
            payloads.append(conn.recv())
        except BaseException as exc:  # noqa: BLE001
            payloads.append({"reader": rid, "status": "error",
                             "error": f"recv_failed:{type(exc).__name__}",
                             "records": []})
    for conn in conns:
        try:
            conn.close()
        except BaseException:  # noqa: BLE001
            pass

    reader_errors = [{"reader": p.get("reader"), "error": p.get("error")}
                     for p in payloads if p.get("status") != "ok"]
    records = [r for p in payloads for r in (p.get("records") or [])]
    records.sort(key=lambda r: int(r["preadv_enter_ns"]))
    stale = sum(int(p.get("stale") or 0) for p in payloads)
    affinity_breaks = sum(int(p.get("affinity_breaks") or 0) for p in payloads)
    idle_no_work_ms = [float(p.get("idle_no_work_ms") or 0.0) for p in payloads]
    role_flips = sum(int(p.get("role_flips") or 0) for p in payloads)
    if not records:
        raise RuntimeError(f"no_reads:{barrier_error or 'readers_failed'}")

    durations = [r["preadv_ms"] for r in records]
    useful_bytes = sum(r["bytes_returned"] for r in records if (r["bytes_returned"] or 0) > 0)
    first_enter = min(int(r["preadv_enter_ns"]) for r in records)
    last_exit = max(int(r["preadv_exit_ns"]) for r in records)
    wall_ms = (last_exit - first_enter) / 1e6

    logical: list[dict[str, Any]] = []
    reader_blocks_won = [0] * (qd + 1)
    for bid in range(total_blocks):
        if winner[bid] == -1:
            continue
        exit_ns = int(winner_exit_ns[bid])
        win = next((r for r in records
                    if r["block_id"] == bid and int(r["preadv_exit_ns"]) == exit_ns), None)
        rid = int(winner[bid])
        if 0 <= rid < len(reader_blocks_won):
            reader_blocks_won[rid] += 1
        logical.append({
            "worker": rid, "block_id": bid, "offset": bid * read_bytes,
            "length": _blen(bid),
            "accepted": "rescue" if int(winner_kind[bid]) == 2 else "primary",
            "bytes_returned": (win or {}).get("bytes_returned", 0),
            "logical_enter_ns": (win or {}).get("preadv_enter_ns", 0),
            "logical_exit_ns": exit_ns,
            "logical_ms": ((exit_ns - (win or {}).get("preadv_enter_ns", 0)) / 1e6),
        })
    logical.sort(key=lambda r: r["block_id"])
    completed = len(logical)

    completed_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    covered_bytes = sum(r["length"] for r in logical)
    ordered = sorted(logical, key=lambda r: r["offset"])
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    published_once = all(int(attempts[b]) >= 1 and winner[b] != -1
                         for b in range(total_blocks))

    claims = sorted(int(r["gate_claim_ns"]) for r in records)
    claim_gaps = [(claims[i] - claims[i - 1]) / 1e6 for i in range(1, len(claims))]
    ev: list[tuple[int, int]] = []
    for r in records:
        ev.append((int(r["preadv_enter_ns"]), 1))
        ev.append((int(r["preadv_exit_ns"]), -1))
    ev.sort()
    conc = 0
    observed_max = 0
    for _, d in ev:
        conc += d
        observed_max = max(observed_max, conc)

    od_events = [e for p in payloads for e in (p.get("odirect_events") or [])]
    rescue_wins = [r for r in logical if r["accepted"] == "rescue"]
    savings = []
    for lr in rescue_wins:
        bid = lr["block_id"]
        prim = next((r for r in records
                     if r["block_id"] == bid and r.get("kind") == "primary"), None)
        if prim is not None:
            savings.append((int(prim["preadv_exit_ns"]) - int(lr["logical_exit_ns"])) / 1e6)

    # raw primary tails (every buffered attempt, winner or not)
    raw_primary = [r["preadv_ms"] for r in records if r.get("kind") == "primary"]

    return {
        "schema_version": 1,
        "kind": "odirect_rescue_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "odirect_rescue",
            "rescue_delay_ns": rescue_delay_ns, "rescue_delay_ms": rescue_delay_ns / 1e6,
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv+O_DIRECT",
                "multiprocessing_start_method": ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "odirect_rescue",
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in records if r.get("pid") is not None}),
        "reader_pids": [p.get("pid") for p in payloads],
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": reader_errors,
        "physical_reads": len(logical),
        "physical_attempts": len(records),
        "physical_amplification": (len(records) / total_blocks),
        "stale_duplicates": stale,
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": ((completed_bytes / (wall_ms / 1000.0) / 1e9)
                                   if wall_ms else None),
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000)},
        "raw_primary_thresholds": {f"ge_{t}": sum(1 for d in raw_primary if d >= t)
                                   for t in (250, 500, 1000)},
        "logical_thresholds": {f"ge_{t}": sum(1 for r in logical
                                              if (r.get("logical_ms") or 0) >= t)
                               for t in (250, 500, 1000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "blocks_expected": total_blocks, "blocks_completed": completed,
            "all_blocks_published_once": published_once,
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_reads_returned_full_length": all(
                (r["bytes_returned"] or 0) == r["length"] for r in logical),
            "covers_entire_file_exactly_once": bool(
                completed == total_blocks and completed_bytes == expected_bytes == file_size
                and no_overlap and contiguous),
        },
        "scheduler": {
            "selfservice": True,
            "rescue_eligible_blocks": len({e["block_id"] for e in od_events}),
            "rescue_launches": len(od_events),
            "rescue_wins": len(rescue_wins),
            "rescue_win_rate": (len(rescue_wins) / len(od_events)) if od_events else None,
            "rescue_saved_ms": savings,
            "rescue_saved_median_ms": percentile(savings, 50) if savings else None,
            "rescue_saved_max_ms": max(savings) if savings else None,
            "odirect_errors": sum(1 for e in od_events if e.get("error")),
            "role_flips": role_flips,
            "spare_promoted": int(spare_promoted.value),
            "spare_refilled": int(spare_refilled.value),
            "max_physical_qd_observed": observed_max,
            "max_physical_qd_structural": qd + 1,
            "min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "median_global_claim_gap_ms": percentile(claim_gaps, 50) if claim_gaps else None,
            "reader_blocks_won": reader_blocks_won,
            "idle_no_work_ms": idle_no_work_ms,
            "dispatches": len(records),
            "sticky_lanes": bool(sticky_lanes),
            "lane_sizes": [len(l) for l in lanes],
            "affinity_breaks": affinity_breaks,
            "allocator_latency_median_ms": None,
        },
        "pacer": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                  "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None},
        "launch_spacing": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                           "mean_effective_concurrency": None,
                           "max_simultaneous_in_flight": observed_max},
        "memory_layout": {
            "note": ("Publication is metadata-only. The only shared objects are small "
                     "integer arrays; no payload bytes are ever placed in shared memory "
                     "and no winner-copy of payload bytes occurs."),
            "per_reader": [{
                "reader": p.get("reader"), "pid": p.get("pid"),
                "buffered_dest_addr": p.get("buf_addr"),
                "buffered_dest_len": p.get("buf_len"),
                "odirect_dest_addr": p.get("abuf_addr"),
                "odirect_dest_len": p.get("abuf_len"),
                "intra_process_overlap": bool(
                    p.get("buf_addr") is not None and p.get("abuf_addr") is not None
                    and p["buf_addr"] < p["abuf_addr"] + (p.get("abuf_len") or 0)
                    and p["abuf_addr"] < p["buf_addr"] + (p.get("buf_len") or 0)),
            } for p in payloads],
            "shared_metadata_regions": _shared_region_report(
                {"ownership": ownership, "winner": winner, "winner_kind": winner_kind,
                 "start_ns": start_ns, "winner_exit_ns": winner_exit_ns,
                 "attempts": attempts, "rescue_sent": rescue_sent,
                 "lane_flat": lane_flat, "lane_off": lane_off,
                 "completed": completed, "next_global": next_global,
                 "last_start": last_start, "spare_promoted": spare_promoted,
                 "spare_refilled": spare_refilled}),
        },
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": records,
        "allocator_dispatches": [],
        "rescue_events": [],
    }


def _wp_reader_child(args: tuple) -> None:
    """Coordination-light QD reader that records full per-read phase timestamps.

    Telemetry is preallocated shared memory written by slot index (allocated inside
    the existing claim critical section).  There is no per-read console logging, no
    JSON serialisation, and no allocation on the hot path.

    Phase boundaries per physical read (10 int64 timestamps):
      0 worker_ready        1 claim_begin      2 claim_end
      3 pacer_wait_begin    4 pacer_wait_end   5 preadv_enter
      6 preadv_exit         7 publish_begin    8 publish_end
      9 worker_ready_again
    """
    (reader_id, file_path, file_size, read_bytes, lane_flat, lane_off, qd, sticky,
     ownership, winner, winner_kind, start_ns, winner_exit_ns, attempts, completed,
     lock, next_global, last_start, pacer_lock, gap_ns, total_blocks, max_idle_s,
     slot_ctr, ts, meta, ready_count, go, child_conn) = args
    payload: dict[str, Any] = {"reader": reader_id, "pid": os.getpid(),
                               "status": "ok", "records": [], "stale": 0,
                               "affinity_breaks": 0, "idle_no_work_ms": 0.0,
                               "unstarted": int(total_blocks)}
    fd = -1
    clock = time.perf_counter_ns
    try:
        preadv_fn = getattr(os, "preadv", None)
        if not callable(preadv_fn):
            raise RuntimeError("os.preadv unavailable")
        buf = bytearray(read_bytes)
        view = memoryview(buf)
        fd = os.open(file_path, os.O_RDONLY)
        with lock:
            ready_count.value = int(ready_count.value) + 1
        while int(go.value) == 0:
            time.sleep(0.001)
        my_start = int(lane_off[reader_id])
        my_end = int(lane_off[reader_id + 1])
        cursor = my_start
        idle_total = 0.0
        idle_deadline: float | None = None
        t_ready = int(clock())
        while True:
            with lock:
                if int(completed.value) >= total_blocks:
                    break
            bid = -1
            t_claim_begin = int(clock())
            unstarted_after = int(completed.value)
            with lock:
                if sticky:
                    while cursor < my_end:
                        cand = int(lane_flat[cursor])
                        cursor += 1
                        if ownership[cand] == 0:
                            bid = cand
                            break
                    if bid < 0:
                        for lid in range(qd):
                            if lid == reader_id:
                                continue
                            s = int(lane_off[lid])
                            e = int(lane_off[lid + 1])
                            while s < e:
                                cand = int(lane_flat[s])
                                s += 1
                                if ownership[cand] == 0:
                                    bid = cand
                                    payload["affinity_breaks"] += 1
                                    break
                            if bid >= 0:
                                break
                else:
                    b = int(next_global.value)
                    while b < total_blocks:
                        next_global.value = b + 1
                        if ownership[b] == 0:
                            bid = b
                            break
                        b = int(next_global.value)
                t_claim_end = int(clock())
                if bid >= 0:
                    ownership[bid] = 1
                    start_ns[bid] = t_claim_end
                    slot = int(slot_ctr.value)
                    slot_ctr.value = slot + 1
                    unstarted_after = int(completed.value)
            if bid < 0:
                idle_total += (int(clock()) - t_ready) / 1e6
                t_ready = int(clock())
                with lock:
                    if int(completed.value) >= total_blocks:
                        break
                if idle_deadline is None:
                    idle_deadline = time.monotonic() + max_idle_s
                elif time.monotonic() > idle_deadline:
                    break
                time.sleep(0.0002)
                continue
            idle_deadline = None
            length = min(read_bytes, file_size - bid * read_bytes)
            offset = bid * read_bytes
            target = view if length == read_bytes else view[:length]
            t_pw_begin = int(clock())
            claim, gate_wait_ns = _alloc_gate(pacer_lock, last_start, gap_ns, clock)
            t_pw_end = int(claim)
            t_enter = int(clock())
            try:
                got = int(preadv_fn(fd, [target], offset))
            except BaseException:  # noqa: BLE001
                got = -1
            t_exit = int(clock())
            t_pub_begin = int(clock())
            stale_here = False
            with lock:
                attempts[bid] = int(attempts[bid]) + 1
                if winner[bid] == -1:
                    winner[bid] = reader_id
                    winner_kind[bid] = 1
                    winner_exit_ns[bid] = t_exit
                    completed.value = int(completed.value) + 1
                else:
                    payload["stale"] += 1
                    stale_here = True
                ownership[bid] = 2
            t_pub_end = int(clock())
            if 0 <= slot < (len(ts) // 10):
                b10 = slot * 10
                ts[b10 + 0] = t_ready
                ts[b10 + 1] = t_claim_begin
                ts[b10 + 2] = t_claim_end
                ts[b10 + 3] = t_pw_begin
                ts[b10 + 4] = t_pw_end
                ts[b10 + 5] = t_enter
                ts[b10 + 6] = t_exit
                ts[b10 + 7] = t_pub_begin
                ts[b10 + 8] = t_pub_end
                ts[b10 + 9] = 0  # filled on the next loop entry
                m7 = slot * 7
                meta[m7 + 0] = bid
                meta[m7 + 1] = reader_id
                meta[m7 + 2] = 2 if stale_here else 0
                meta[m7 + 3] = unstarted_after
                meta[m7 + 4] = int(last_start.value)
                meta[m7 + 5] = slot
                meta[m7 + 6] = offset
            t_ready = int(clock())
            if 0 <= slot < (len(ts) // 10):
                ts[slot * 10 + 9] = t_ready
            payload["records"].append({
                "reader": reader_id, "pid": os.getpid(), "block_id": int(bid),
                "kind": "primary", "seq": int(slot), "offset": offset,
                "length": length, "gate_claim_ns": t_pw_end,
                "gate_wait_ms": gate_wait_ns / 1e6,
                "preadv_enter_ns": t_enter, "preadv_exit_ns": t_exit,
                "preadv_ms": (t_exit - t_enter) / 1e6, "bytes_returned": got,
            })
        payload["idle_no_work_ms"] = idle_total
        with lock:
            payload["unstarted"] = int(total_blocks) - int(completed.value)
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_wall_profile_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int = 4,
    sticky_lanes: bool = True,
    min_launch_gap_ns: int = 4_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    max_idle_s: float = 120.0,
    pacer_start_method: str = "fork",
) -> dict:
    """Whole-file pass with full per-read phase telemetry for source-wall accounting."""
    import multiprocessing as mp  # noqa: PLC0415

    if not callable(getattr(os, "preadv", None)):
        raise RuntimeError("os.preadv unavailable")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if pacer_start_method not in mp.get_all_start_methods():
        raise RuntimeError(f"start_method_unavailable:{pacer_start_method}")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {"path": file_path, "size": file_size,
                     "st_dev": getattr(stat_result, "st_dev", None),
                     "st_ino": getattr(stat_result, "st_ino", None),
                     "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)}
    total_blocks = (file_size + read_bytes - 1) // read_bytes
    max_reads = total_blocks * 3 + 16

    def _blen(bid: int) -> int:
        return min(read_bytes, file_size - bid * read_bytes)
    expected_bytes = sum(_blen(b) for b in range(total_blocks))

    lanes: list[list[int]] = []
    if sticky_lanes:
        _base, _extra = divmod(total_blocks, qd)
        _cursor = 0
        for _lid in range(qd):
            _cnt = _base + (1 if _lid < _extra else 0)
            lanes.append(list(range(_cursor, _cursor + _cnt)))
            _cursor += _cnt
    else:
        for _lid in range(qd):
            lanes.append(list(range(_lid, total_blocks, qd)))
    lane_flat_list = [b for l in lanes for b in l]
    lane_off_list = [0]
    for l in lanes:
        lane_off_list.append(lane_off_list[-1] + len(l))

    ctx = mp.get_context(pacer_start_method)
    lock = ctx.Lock()
    ownership = ctx.Array("b", total_blocks, lock=False)
    winner = ctx.Array("i", [-1] * total_blocks, lock=False)
    winner_kind = ctx.Array("b", total_blocks, lock=False)
    start_ns = ctx.Array("q", total_blocks, lock=False)
    winner_exit_ns = ctx.Array("q", total_blocks, lock=False)
    attempts = ctx.Array("i", total_blocks, lock=False)
    completed = ctx.Value("i", 0, lock=False)
    next_global = ctx.Value("q", 0, lock=False)
    lane_flat = ctx.Array("i", lane_flat_list, lock=False)
    lane_off = ctx.Array("i", lane_off_list, lock=False)
    last_start = ctx.Value("q", 0)
    pacer_lock = last_start.get_lock()
    slot_ctr = ctx.Value("i", 0, lock=False)
    ready_count = ctx.Value("i", 0, lock=False)
    go = ctx.Value("i", 0, lock=False)
    ts = ctx.Array("q", max_reads * 10, lock=False)
    meta = ctx.Array("q", max_reads * 7, lock=False)

    procs: list[Any] = []
    conns: list[Any] = []
    for rid in range(qd):
        conn_parent, conn_child = ctx.Pipe(duplex=False)
        proc = cast(Any, ctx).Process(
            target=_wp_reader_child,
            args=((rid, file_path, file_size, read_bytes, lane_flat, lane_off, qd,
                   sticky_lanes, ownership, winner, winner_kind, start_ns,
                   winner_exit_ns, attempts, completed, lock, next_global,
                   last_start, pacer_lock, min_launch_gap_ns, total_blocks,
                   max_idle_s, slot_ctr, ts, meta, ready_count, go, conn_child),),
            daemon=True)
        proc.start()
        conn_child.close()
        conns.append(conn_parent)
        procs.append(proc)

    barrier_error = None
    release_ns = None
    deadline = time.monotonic() + ready_timeout_s
    try:
        while int(ready_count.value) < qd:
            dead = [i for i, pr in enumerate(procs) if not pr.is_alive()]
            if dead:
                errs = []
                for i in dead:
                    try:
                        errs.append({i: conns[i].recv()})
                    except BaseException as exc:  # noqa: BLE001
                        errs.append({i: f"no_payload:{type(exc).__name__}"})
                raise RuntimeError(f"reader_died_during_setup:{dead}:{errs}")
            if time.monotonic() > deadline:
                raise TimeoutError("readers_not_ready")
            time.sleep(0.002)
        release_ns = int(clock_ns())
        go.value = 1
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    payloads: list[dict[str, Any]] = []
    for rid, proc in enumerate(procs):
        proc.join(timeout=ready_timeout_s)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=30.0)
    for rid, conn in enumerate(conns):
        try:
            payloads.append(conn.recv())
        except BaseException as exc:  # noqa: BLE001
            payloads.append({"reader": rid, "status": "error",
                             "error": f"recv_failed:{type(exc).__name__}",
                             "records": []})
    for conn in conns:
        try:
            conn.close()
        except BaseException:  # noqa: BLE001
            pass

    n_slots = int(slot_ctr.value)
    reader_errors = [{"reader": p.get("reader"), "error": p.get("error")}
                     for p in payloads if p.get("status") != "ok"]
    records = [r for p in payloads for r in (p.get("records") or [])]
    records.sort(key=lambda r: int(r["preadv_enter_ns"]))
    stale = sum(int(p.get("stale") or 0) for p in payloads)
    affinity_breaks = sum(int(p.get("affinity_breaks") or 0) for p in payloads)
    idle_no_work_ms = [float(p.get("idle_no_work_ms") or 0.0) for p in payloads]
    if not records:
        raise RuntimeError(f"no_reads:{barrier_error or 'readers_failed'}")

    # Bounded telemetry dump: one flat array per read, no nested JSON per read.
    telemetry: list[list[int]] = []
    for s in range(min(n_slots, max_reads)):
        b10, m7 = s * 10, s * 7
        if int(ts[b10 + 5]) == 0:
            continue
        telemetry.append([
            int(meta[m7 + 1]), int(meta[m7 + 0]), int(meta[m7 + 2]),
            int(meta[m7 + 3]), int(meta[m7 + 4]), int(meta[m7 + 6]),
            int(ts[b10 + 0]), int(ts[b10 + 1]), int(ts[b10 + 2]),
            int(ts[b10 + 3]), int(ts[b10 + 4]), int(ts[b10 + 5]),
            int(ts[b10 + 6]), int(ts[b10 + 7]), int(ts[b10 + 8]),
            int(ts[b10 + 9]),
        ])

    durations = [r["preadv_ms"] for r in records]
    useful_bytes = sum(r["bytes_returned"] for r in records if (r["bytes_returned"] or 0) > 0)
    first_enter = min(int(r["preadv_enter_ns"]) for r in records)
    last_exit = max(int(r["preadv_exit_ns"]) for r in records)
    wall_ms = (last_exit - first_enter) / 1e6

    logical: list[dict[str, Any]] = []
    reader_blocks_won = [0] * qd
    for bid in range(total_blocks):
        if winner[bid] == -1:
            continue
        exit_ns = int(winner_exit_ns[bid])
        win = next((r for r in records
                    if r["block_id"] == bid and int(r["preadv_exit_ns"]) == exit_ns), None)
        rid = int(winner[bid])
        reader_blocks_won[rid] += 1
        logical.append({
            "worker": rid, "block_id": bid, "offset": bid * read_bytes,
            "length": _blen(bid), "accepted": "primary",
            "bytes_returned": (win or {}).get("bytes_returned", 0),
            "logical_enter_ns": (win or {}).get("preadv_enter_ns", 0),
            "logical_exit_ns": exit_ns,
            "logical_ms": ((exit_ns - (win or {}).get("preadv_enter_ns", 0)) / 1e6),
        })
    logical.sort(key=lambda r: r["block_id"])
    completed = len(logical)

    completed_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    covered_bytes = sum(r["length"] for r in logical)
    ordered = sorted(logical, key=lambda r: r["offset"])
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    published_once = all(int(attempts[b]) >= 1 and winner[b] != -1
                         for b in range(total_blocks))

    claims = sorted(int(r["gate_claim_ns"]) for r in records)
    claim_gaps = [(claims[i] - claims[i - 1]) / 1e6 for i in range(1, len(claims))]

    return {
        "schema_version": 1,
        "kind": "wall_profile_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "wall_profile",
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv",
                "multiprocessing_start_method": ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "wall_profile",
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in records if r.get("pid") is not None}),
        "reader_pids": [p.get("pid") for p in payloads],
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": reader_errors,
        "physical_reads": len(logical),
        "physical_attempts": len(records),
        "physical_amplification": (len(records) / total_blocks),
        "stale_duplicates": stale,
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": ((completed_bytes / (wall_ms / 1000.0) / 1e9)
                                   if wall_ms else None),
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "blocks_expected": total_blocks, "blocks_completed": completed,
            "all_blocks_published_once": published_once,
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_reads_returned_full_length": all(
                (r["bytes_returned"] or 0) == r["length"] for r in logical),
            "covers_entire_file_exactly_once": bool(
                completed == total_blocks and completed_bytes == expected_bytes == file_size
                and no_overlap and contiguous),
        },
        "scheduler": {
            "selfservice": True,
            "max_physical_qd_observed": None,
            "max_physical_qd_structural": qd,
            "min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "median_global_claim_gap_ms": percentile(claim_gaps, 50) if claim_gaps else None,
            "reader_blocks_won": reader_blocks_won,
            "idle_no_work_ms": idle_no_work_ms,
            "dispatches": len(records),
            "sticky_lanes": bool(sticky_lanes),
            "lane_sizes": [len(l) for l in lanes],
            "affinity_breaks": affinity_breaks,
            "allocator_latency_median_ms": None,
        },
        "pacer": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                  "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None},
        "launch_spacing": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                           "mean_effective_concurrency": None,
                           "max_simultaneous_in_flight": None},
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": records,
        "allocator_dispatches": [],
        "rescue_events": [],
        # Flat per-read phase telemetry, ordered by read index.
        "profile_columns": ["reader", "block", "kind", "unstarted_after_claim",
                            "last_start_at_claim", "offset", "worker_ready",
                            "claim_begin", "claim_end", "pacer_wait_begin",
                            "pacer_wait_end", "preadv_enter", "preadv_exit",
                            "publish_begin", "publish_end", "worker_ready_again"],
        "profile_rows": telemetry,
    }


def _m0r_child(args: tuple) -> None:
    """One of qd paired dormant M0 rescuers, each bound to exactly one primary.

    Every primary reader has its OWN prearmed persistent mmap + private destination,
    so a sick rescue can never queue behind another rescue: rescuer i watches only
    partner i's current block.  Healthy state stays QD4 because rescuers are dormant
    and take no normal work.

    Rescue path is pure M0: persistent mapping opened before timed work, no
    MADV_WILLNEED, no MAP_POPULATE, no Python slicing, one C-level memcpy into a
    preallocated destination, nothing allocated on the critical path.
    """
    (rescuer_id, partner_id, file_path, file_size, read_bytes, mmap_mode_unused,
     ownership, winner, winner_kind, start_ns, winner_exit_ns, attempts,
     rescue_sent, completed, lock, cur_block, cur_enter_ns, total_blocks,
     rescue_delay_ns, max_idle_s, ready_count, go, child_conn) = args
    payload: dict[str, Any] = {"reader": rescuer_id, "pid": os.getpid(),
                               "status": "ok", "records": [], "stale": 0,
                               "affinity_breaks": 0, "idle_no_work_ms": 0.0,
                               "m0_events": []}
    fd = -1
    mm_base = 0
    clock = time.perf_counter_ns
    try:
        if _LIBC is None:
            raise RuntimeError("libc_unavailable")
        dest = bytearray(read_bytes)
        dest_addr = _ct.addressof(_ct.c_char.from_buffer(dest))
        fd = os.open(file_path, os.O_RDONLY)
        # Prearmed persistent read-only mapping (libc so we own the address).
        mm_base = int(_LIBC.mmap(None, file_size, _PROT_READ, _MAP_PRIVATE, fd, 0))
        if mm_base in (0, -1) or mm_base == 0xFFFFFFFFFFFFFFFF:
            raise OSError(f"persistent_mmap_failed errno={_ct.get_errno()}")
        with lock:
            ready_count.value = int(ready_count.value) + 1
        while int(go.value) == 0:
            time.sleep(0.001)
        idle_deadline: float | None = None
        while True:
            with lock:
                if int(completed.value) >= total_blocks:
                    break
            b = int(cur_block[partner_id])
            t0 = int(cur_enter_ns[partner_id])
            now = int(clock())
            trigger = (b >= 0 and t0 > 0 and (now - t0) >= rescue_delay_ns
                       and int(rescue_sent[b]) == 0)
            if not trigger:
                if idle_deadline is None:
                    idle_deadline = time.monotonic() + max_idle_s
                elif time.monotonic() > idle_deadline:
                    break
                time.sleep(0.00025)
                continue
            idle_deadline = None
            detect_ns = int(clock())
            with lock:
                if int(rescue_sent[b]) != 0 or winner[b] != -1:
                    continue
                rescue_sent[b] = 1
                take = True
            if not take:
                continue
            length = min(read_bytes, file_size - b * read_bytes)
            offset = b * read_bytes
            enter = int(clock())
            got = -1
            err = None
            try:
                _LIBC.memcpy(dest_addr, mm_base + offset, length)
                got = length
            except BaseException as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}:{str(exc)[:160]}"
            exit_ns = int(clock())
            won = False
            with lock:
                attempts[b] = int(attempts[b]) + 1
                if err is None and winner[b] == -1:
                    winner[b] = rescuer_id
                    winner_kind[b] = 3
                    winner_exit_ns[b] = exit_ns
                    completed.value = int(completed.value) + 1
                    won = True
                else:
                    payload["stale"] += 1
                if winner[b] != -1:
                    ownership[b] = 2
            payload["m0_events"].append({
                "block_id": int(b), "rescuer": rescuer_id, "partner": partner_id,
                "threshold_cross_ns": t0 + rescue_delay_ns,
                "detect_ns": detect_ns, "enter_ns": enter, "exit_ns": exit_ns,
                "m0_ms": (exit_ns - enter) / 1e6,
                "detect_latency_ms": (detect_ns - (t0 + rescue_delay_ns)) / 1e6,
                "enter_rel_threshold_ms": (enter - (t0 + rescue_delay_ns)) / 1e6,
                "bytes": got, "expected": length, "won": bool(won), "error": err,
            })
            payload["records"].append({
                "reader": rescuer_id, "pid": os.getpid(), "block_id": int(b),
                "kind": "rescue", "seq": len(payload["records"]),
                "offset": offset, "length": length, "gate_claim_ns": enter,
                "gate_wait_ms": 0.0, "preadv_enter_ns": enter,
                "preadv_exit_ns": exit_ns, "preadv_ms": (exit_ns - enter) / 1e6,
                "bytes_returned": got,
            })
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            if mm_base:
                _LIBC.munmap(mm_base, file_size)
        except BaseException:  # noqa: BLE001
            pass
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def _m0p_child(args: tuple) -> None:
    """Buffered self-service primary; publishes its current block for its rescuer."""
    (reader_id, file_path, file_size, read_bytes, lane_flat, lane_off, qd, sticky,
     ownership, winner, winner_kind, start_ns, winner_exit_ns, attempts,
     completed, lock, next_global, last_start, pacer_lock, gap_ns, total_blocks,
     max_idle_s, cur_block, cur_enter_ns, ready_count, go, child_conn) = args
    payload: dict[str, Any] = {"reader": reader_id, "pid": os.getpid(),
                               "status": "ok", "records": [], "stale": 0,
                               "affinity_breaks": 0, "idle_no_work_ms": 0.0}
    fd = -1
    clock = time.perf_counter_ns
    try:
        preadv_fn = getattr(os, "preadv", None)
        if not callable(preadv_fn):
            raise RuntimeError("os.preadv unavailable")
        buf = bytearray(read_bytes)
        view = memoryview(buf)
        fd = os.open(file_path, os.O_RDONLY)
        with lock:
            ready_count.value = int(ready_count.value) + 1
        while int(go.value) == 0:
            time.sleep(0.001)
        my_start = int(lane_off[reader_id])
        my_end = int(lane_off[reader_id + 1])
        cursor = my_start
        idle_total = 0.0
        idle_deadline: float | None = None
        while True:
            with lock:
                if int(completed.value) >= total_blocks:
                    break
            bid = -1
            now = int(clock())
            with lock:
                if sticky:
                    while cursor < my_end:
                        cand = int(lane_flat[cursor])
                        cursor += 1
                        if ownership[cand] == 0:
                            bid = cand
                            break
                    if bid < 0:
                        for lid in range(qd):
                            if lid == reader_id:
                                continue
                            s = int(lane_off[lid])
                            e = int(lane_off[lid + 1])
                            while s < e:
                                cand = int(lane_flat[s])
                                s += 1
                                if ownership[cand] == 0:
                                    bid = cand
                                    payload["affinity_breaks"] += 1
                                    break
                            if bid >= 0:
                                break
                else:
                    b = int(next_global.value)
                    while b < total_blocks:
                        next_global.value = b + 1
                        if ownership[b] == 0:
                            bid = b
                            break
                        b = int(next_global.value)
                if bid >= 0:
                    ownership[bid] = 1
                    start_ns[bid] = now
                    cur_block[reader_id] = bid
            if bid < 0:
                idle_total += (int(clock()) - now) / 1e6
                with lock:
                    if int(completed.value) >= total_blocks:
                        break
                if idle_deadline is None:
                    idle_deadline = time.monotonic() + max_idle_s
                elif time.monotonic() > idle_deadline:
                    break
                time.sleep(0.0002)
                continue
            idle_deadline = None
            length = min(read_bytes, file_size - bid * read_bytes)
            offset = bid * read_bytes
            claim, gate_wait_ns = _alloc_gate(pacer_lock, last_start, gap_ns, clock)
            enter = int(clock())
            # Publish the in-flight marker for the paired rescuer.
            cur_enter_ns[reader_id] = enter
            try:
                got = int(preadv_fn(fd, [view if length == read_bytes
                                         else view[:length]], offset))
            except BaseException:  # noqa: BLE001
                got = -1
            exit_ns = int(clock())
            with lock:
                attempts[bid] = int(attempts[bid]) + 1
                if winner[bid] == -1:
                    winner[bid] = reader_id
                    winner_kind[bid] = 1
                    winner_exit_ns[bid] = exit_ns
                    completed.value = int(completed.value) + 1
                else:
                    payload["stale"] += 1
                ownership[bid] = 2
                cur_block[reader_id] = -1
                cur_enter_ns[reader_id] = 0
            payload["records"].append({
                "reader": reader_id, "pid": os.getpid(), "block_id": int(bid),
                "kind": "primary", "seq": len(payload["records"]),
                "offset": offset, "length": length, "gate_claim_ns": int(claim),
                "gate_wait_ms": gate_wait_ns / 1e6, "preadv_enter_ns": enter,
                "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
            })
        payload["idle_no_work_ms"] = idle_total
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_m0_rescue_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int = 4,
    rescue_delay_ns: int = 250_000_000,
    sticky_lanes: bool = True,
    min_launch_gap_ns: int = 4_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    max_idle_s: float = 120.0,
    pacer_start_method: str = "fork",
) -> dict:
    """qd buffered preadv primaries, each with its own dormant prearmed M0 rescuer."""
    import multiprocessing as mp  # noqa: PLC0415

    if not callable(getattr(os, "preadv", None)):
        raise RuntimeError("os.preadv unavailable")
    if _LIBC is None:
        raise RuntimeError("libc_unavailable")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if pacer_start_method not in mp.get_all_start_methods():
        raise RuntimeError(f"start_method_unavailable:{pacer_start_method}")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {"path": file_path, "size": file_size,
                     "st_dev": getattr(stat_result, "st_dev", None),
                     "st_ino": getattr(stat_result, "st_ino", None),
                     "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)}
    total_blocks = (file_size + read_bytes - 1) // read_bytes

    def _blen(bid: int) -> int:
        return min(read_bytes, file_size - bid * read_bytes)
    expected_bytes = sum(_blen(b) for b in range(total_blocks))

    lanes: list[list[int]] = []
    if sticky_lanes:
        _base, _extra = divmod(total_blocks, qd)
        _cursor = 0
        for _lid in range(qd):
            _cnt = _base + (1 if _lid < _extra else 0)
            lanes.append(list(range(_cursor, _cursor + _cnt)))
            _cursor += _cnt
    else:
        for _lid in range(qd):
            lanes.append(list(range(_lid, total_blocks, qd)))
    lane_flat_list = [b for l in lanes for b in l]
    lane_off_list = [0]
    for l in lanes:
        lane_off_list.append(lane_off_list[-1] + len(l))

    ctx = mp.get_context(pacer_start_method)
    lock = ctx.Lock()
    ownership = ctx.Array("b", total_blocks, lock=False)
    winner = ctx.Array("i", [-1] * total_blocks, lock=False)
    winner_kind = ctx.Array("b", total_blocks, lock=False)
    start_ns = ctx.Array("q", total_blocks, lock=False)
    winner_exit_ns = ctx.Array("q", total_blocks, lock=False)
    attempts = ctx.Array("i", total_blocks, lock=False)
    rescue_sent = ctx.Array("b", total_blocks, lock=False)
    completed = ctx.Value("i", 0, lock=False)
    next_global = ctx.Value("q", 0, lock=False)
    lane_flat = ctx.Array("i", lane_flat_list, lock=False)
    lane_off = ctx.Array("i", lane_off_list, lock=False)
    last_start = ctx.Value("q", 0)
    pacer_lock = last_start.get_lock()
    cur_block = ctx.Array("i", [-1] * qd, lock=False)
    cur_enter_ns = ctx.Array("q", [0] * qd, lock=False)
    ready_count = ctx.Value("i", 0, lock=False)
    go = ctx.Value("i", 0, lock=False)

    procs: list[Any] = []
    conns: list[Any] = []
    for rid in range(qd):
        cp, cc = ctx.Pipe(duplex=False)
        p = cast(Any, ctx).Process(
            target=_m0p_child,
            args=((rid, file_path, file_size, read_bytes, lane_flat, lane_off, qd,
                   sticky_lanes, ownership, winner, winner_kind, start_ns,
                   winner_exit_ns, attempts, completed, lock, next_global,
                   last_start, pacer_lock, min_launch_gap_ns, total_blocks,
                   max_idle_s, cur_block, cur_enter_ns, ready_count, go, cc),),
            daemon=True)
        p.start(); cc.close(); conns.append(cp); procs.append(p)
    for rid in range(qd):
        cp, cc = ctx.Pipe(duplex=False)
        p = cast(Any, ctx).Process(
            target=_m0r_child,
            args=((rid, rid, file_path, file_size, read_bytes, "m0", ownership,
                   winner, winner_kind, start_ns, winner_exit_ns, attempts,
                   rescue_sent, completed, lock, cur_block, cur_enter_ns,
                   total_blocks, rescue_delay_ns, max_idle_s, ready_count, go, cc),),
            daemon=True)
        p.start(); cc.close(); conns.append(cp); procs.append(p)

    barrier_error = None
    release_ns = None
    deadline = time.monotonic() + ready_timeout_s
    try:
        while int(ready_count.value) < 2 * qd:
            dead = [i for i, pr in enumerate(procs) if not pr.is_alive()]
            if dead:
                errs = []
                for i in dead:
                    try:
                        errs.append({i: conns[i].recv()})
                    except BaseException as exc:  # noqa: BLE001
                        errs.append({i: f"no_payload:{type(exc).__name__}"})
                raise RuntimeError(f"reader_died_during_setup:{dead}:{errs}")
            if time.monotonic() > deadline:
                raise TimeoutError("readers_not_ready")
            time.sleep(0.002)
        release_ns = int(clock_ns())
        go.value = 1
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    payloads: list[dict[str, Any]] = []
    for rid, proc in enumerate(procs):
        proc.join(timeout=ready_timeout_s)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=30.0)
    for rid, conn in enumerate(conns):
        try:
            payloads.append(conn.recv())
        except BaseException as exc:  # noqa: BLE001
            payloads.append({"reader": rid, "status": "error",
                             "error": f"recv_failed:{type(exc).__name__}",
                             "records": []})
    for conn in conns:
        try:
            conn.close()
        except BaseException:  # noqa: BLE001
            pass

    reader_errors = [{"reader": p.get("reader"), "error": p.get("error")}
                     for p in payloads if p.get("status") != "ok"]
    records = [r for p in payloads for r in (p.get("records") or [])]
    records.sort(key=lambda r: int(r["preadv_enter_ns"]))
    stale = sum(int(p.get("stale") or 0) for p in payloads)
    affinity_breaks = sum(int(p.get("affinity_breaks") or 0) for p in payloads)
    idle_no_work_ms = [float(p.get("idle_no_work_ms") or 0.0) for p in payloads]
    m0_events = [e for p in payloads for e in (p.get("m0_events") or [])]
    if not records:
        raise RuntimeError(f"no_reads:{barrier_error or 'readers_failed'}")

    durations = [r["preadv_ms"] for r in records]
    useful_bytes = sum(r["bytes_returned"] for r in records if (r["bytes_returned"] or 0) > 0)
    first_enter = min(int(r["preadv_enter_ns"]) for r in records)
    last_exit = max(int(r["preadv_exit_ns"]) for r in records)
    wall_ms = (last_exit - first_enter) / 1e6

    logical: list[dict[str, Any]] = []
    reader_blocks_won = [0] * (2 * qd)
    for bid in range(total_blocks):
        if winner[bid] == -1:
            continue
        exit_ns = int(winner_exit_ns[bid])
        win = next((r for r in records
                    if r["block_id"] == bid and int(r["preadv_exit_ns"]) == exit_ns), None)
        rid = int(winner[bid])
        if 0 <= rid < len(reader_blocks_won):
            reader_blocks_won[rid] += 1
        logical.append({
            "worker": rid, "block_id": bid, "offset": bid * read_bytes,
            "length": _blen(bid),
            "accepted": ("m0_rescue" if int(winner_kind[bid]) == 3 else "primary"),
            "bytes_returned": (win or {}).get("bytes_returned", 0),
            "logical_enter_ns": (win or {}).get("preadv_enter_ns", 0),
            "logical_exit_ns": exit_ns,
            "logical_ms": ((exit_ns - (win or {}).get("preadv_enter_ns", 0)) / 1e6),
        })
    logical.sort(key=lambda r: r["block_id"])
    completed = len(logical)

    completed_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    covered_bytes = sum(r["length"] for r in logical)
    ordered = sorted(logical, key=lambda r: r["offset"])
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    published_once = all(int(attempts[b]) >= 1 and winner[b] != -1
                         for b in range(total_blocks))

    claims = sorted(int(r["gate_claim_ns"]) for r in records if r.get("kind") == "primary")
    claim_gaps = [(claims[i] - claims[i - 1]) / 1e6 for i in range(1, len(claims))]
    ev: list[tuple[int, int]] = []
    for r in records:
        ev.append((int(r["preadv_enter_ns"]), 1))
        ev.append((int(r["preadv_exit_ns"]), -1))
    ev.sort()
    conc = 0
    observed_max = 0
    for _, dd in ev:
        conc += dd
        observed_max = max(observed_max, conc)

    prim_by_block = {r["block_id"]: r for r in records if r.get("kind") == "primary"}
    for e in m0_events:
        prim = prim_by_block.get(e["block_id"])
        e["primary_ms"] = prim["preadv_ms"] if prim else None
        e["primary_still_alive_at_m0_exit"] = bool(
            prim is not None and int(e["exit_ns"]) < int(prim["preadv_exit_ns"]))
        e["ms_saved"] = (((int(prim["preadv_exit_ns"]) - int(e["exit_ns"])) / 1e6)
                         if prim is not None else None)
    raw_primary = [r["preadv_ms"] for r in records if r.get("kind") == "primary"]

    return {
        "schema_version": 1,
        "kind": "m0_rescue_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "m0_rescue",
            "rescue_delay_ns": rescue_delay_ns, "rescue_delay_ms": rescue_delay_ns / 1e6,
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
            "rescuers": qd, "paired": True,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv+mmap_memcpy",
                "multiprocessing_start_method": ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "m0_rescue",
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in records if r.get("pid") is not None}),
        "reader_pids": [p.get("pid") for p in payloads],
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": reader_errors,
        "physical_reads": len(logical),
        "physical_attempts": len(records),
        "physical_amplification": (len(records) / total_blocks),
        "stale_duplicates": stale,
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": ((completed_bytes / (wall_ms / 1000.0) / 1e9)
                                   if wall_ms else None),
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000)},
        "raw_primary_thresholds": {f"ge_{t}": sum(1 for d in raw_primary if d >= t)
                                   for t in (250, 500, 1000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "blocks_expected": total_blocks, "blocks_completed": completed,
            "all_blocks_published_once": published_once,
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_reads_returned_full_length": all(
                (r["bytes_returned"] or 0) == r["length"] for r in logical),
            "covers_entire_file_exactly_once": bool(
                completed == total_blocks and completed_bytes == expected_bytes == file_size
                and no_overlap and contiguous),
        },
        "scheduler": {
            "selfservice": True,
            "rescue_eligible_blocks": len({e["block_id"] for e in m0_events}),
            "rescue_launches": len(m0_events),
            "rescue_wins": sum(1 for e in m0_events if e.get("won")),
            "rescue_win_rate": ((sum(1 for e in m0_events if e.get("won")) / len(m0_events))
                                if m0_events else None),
            "m0_errors": sum(1 for e in m0_events if e.get("error")),
            "max_physical_qd_observed": observed_max,
            "max_physical_qd_structural": 2 * qd,
            "min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "median_global_claim_gap_ms": percentile(claim_gaps, 50) if claim_gaps else None,
            "reader_blocks_won": reader_blocks_won,
            "idle_no_work_ms": idle_no_work_ms,
            "dispatches": len(records),
            "sticky_lanes": bool(sticky_lanes),
            "lane_sizes": [len(l) for l in lanes],
            "affinity_breaks": affinity_breaks,
            "allocator_latency_median_ms": None,
        },
        "pacer": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                  "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None},
        "launch_spacing": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                           "mean_effective_concurrency": None,
                           "max_simultaneous_in_flight": observed_max},
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": records,
        "allocator_dispatches": [],
        "m0_events": m0_events,
    }


def _mm2_load_native():
    """Load /opt/source_touch.so once per process and cache the function objects."""
    if _LIBC is None:
        return None
    try:
        lib = _ct.CDLL("/opt/source_touch.so")
    except BaseException:  # noqa: BLE001
        return None
    lib.st_touch_pages.restype = _ct.c_long
    lib.st_touch_pages.argtypes = [_ct.c_void_p, _ct.c_size_t, _ct.c_size_t]
    lib.st_touch_lines.restype = _ct.c_long
    lib.st_touch_lines.argtypes = [_ct.c_void_p, _ct.c_size_t, _ct.c_size_t]
    lib.st_reduce_full.restype = _ct.c_long
    lib.st_reduce_full.argtypes = [_ct.c_void_p, _ct.c_size_t]
    return lib


def _mm2_child(args: tuple) -> None:
    """Pure-CPU mmap source reader.

    mmap_mode="persistent"  M0: one whole-file mapping per process, C memcpy consumer.
    mmap_mode="window"      M2: exact-window MAP_POPULATE mapping per block (flag is
                            accepted-but-inert in this runtime; the real difference is
                            the repeated mapping lifecycle).

    consume_mode:
      "memcpy"  copy the block into a preallocated private bytearray (M0 semantics)
      "d0"      native page-materialization probe  (st_touch_pages)
      "d1"      native cache-line probe            (st_touch_lines)
      "d2"      native full-byte direct consumer   (st_reduce_full)

    consume_mode != "memcpy" is the ZERO-COPY path: no destination buffer exists and no
    payload byte is ever copied.
    """
    (reader_id, file_path, file_size, read_bytes, mmap_mode, consume_mode, touch_ahead,
     lane_flat, lane_off, qd, sticky, ownership, winner, winner_kind, start_ns,
     winner_exit_ns, attempts, completed, lock, next_global, last_start, pacer_lock,
     gap_ns, total_blocks, max_idle_s, consumer_pos, touch_pos, touch_events,
     ready_count, go, child_conn, staging) = args
    payload: dict[str, Any] = {"reader": reader_id, "pid": os.getpid(),
                               "status": "ok", "records": [], "stale": 0,
                               "affinity_breaks": 0, "idle_no_work_ms": 0.0,
                               "touch_events": [], "payload_copy_bytes": 0,
                               "dest_allocated": False, "staging_wait_ms": 0.0,
                               "staging_wait_events": 0, "staging_published": 0}
    fd = -1
    mm_base = 0
    clock = time.perf_counter_ns
    try:
        if _LIBC is None:
            raise RuntimeError("libc_unavailable")
        lib = _mm2_load_native()
        if lib is None:
            raise RuntimeError("source_touch_so_unavailable")
        zero_copy = consume_mode != "memcpy"
        dest_addr = 0
        if not zero_copy:
            if staging is None:
                dest = bytearray(read_bytes)
                dest_addr = _ct.addressof(_ct.c_char.from_buffer(dest))
            else:
                # Additive seam: write produced bytes into the caller's shared
                # staging region instead of a process-private bytearray.
                dest = None
                dest_addr = 0
                stage_published = staging["published"][reader_id]
                stage_consumed = staging["consumed"][reader_id]
                stage_off = staging["slot_off"][reader_id]
                stage_len = staging["slot_len"][reader_id]
                stage_slots = int(staging["slots"])
                stage_lane_base = (int(staging["seg_base"])
                                   + reader_id * int(staging["lane_bytes"]))
            payload["dest_allocated"] = True
        fd = os.open(file_path, os.O_RDONLY)
        if mmap_mode == "persistent":
            mm_base = int(_LIBC.mmap(None, file_size, _PROT_READ, _MAP_PRIVATE, fd, 0))
            if mm_base in (0, -1) or mm_base == 0xFFFFFFFFFFFFFFFF:
                raise OSError(f"persistent_mmap_failed errno={_ct.get_errno()}")
        with lock:
            ready_count.value = int(ready_count.value) + 1
        while int(go.value) == 0:
            time.sleep(0.001)

        stop_touch = [False]

        def _toucher():
            """Walk ahead in this reader's own lane, materializing pages early."""
            try:
                while not stop_touch[0]:
                    b = -1
                    with lock:
                        if int(completed.value) >= total_blocks:
                            break
                        tp = int(touch_pos[reader_id])
                        cp = int(consumer_pos[reader_id])
                        lane = lanes_local[reader_id]
                        if tp < len(lane) and (tp - cp) <= touch_ahead:
                            b = lane[tp]
                            touch_pos[reader_id] = tp + 1
                    if b < 0:
                        time.sleep(0.0002)
                        continue
                    length = min(read_bytes, file_size - b * read_bytes)
                    if mmap_mode == "persistent":
                        ptr = mm_base + b * read_bytes
                        t0 = int(clock())
                        sink = int(lib.st_touch_pages(_ct.c_void_p(ptr),
                                                      _ct.c_size_t(length), 4096))
                        t1 = int(clock())
                        payload["touch_events"].append({
                            "block_id": int(b), "touch_start_ns": t0, "touch_end_ns": t1,
                            "touch_ms": (t1 - t0) / 1e6, "sink": sink})
            except BaseException as exc:  # noqa: BLE001
                payload["touch_error"] = f"{type(exc).__name__}:{str(exc)[:160]}"

        lanes_local = []
        for _lid in range(qd):
            _s = int(lane_off[_lid])
            _e = int(lane_off[_lid + 1])
            lanes_local.append([int(lane_flat[_i]) for _i in range(_s, _e)])
        thr = None
        if touch_ahead > 0 and mmap_mode == "persistent":
            thr = threading.Thread(target=_toucher, daemon=True)
            thr.start()

        my_lane = lanes_local[reader_id]
        cursor = 0
        idle_total = 0.0
        idle_deadline: float | None = None
        slot_wait_ms = 0.0
        slot_wait_events = 0
        stage_seq = 0
        while True:
            with lock:
                if int(completed.value) >= total_blocks:
                    break
            bid = -1
            now = int(clock())
            with lock:
                while cursor < len(my_lane):
                    cand = my_lane[cursor]
                    cursor += 1
                    if ownership[cand] == 0:
                        bid = cand
                        break
                if bid < 0:
                    for lid in range(qd):
                        if lid == reader_id:
                            continue
                        for cand in lanes_local[lid]:
                            if ownership[cand] == 0:
                                bid = cand
                                payload["affinity_breaks"] += 1
                                break
                        if bid >= 0:
                            break
                if bid >= 0:
                    ownership[bid] = 1
                    start_ns[bid] = now
                    consumer_pos[reader_id] = cursor - 1
            if bid < 0:
                idle_total += (int(clock()) - now) / 1e6
                with lock:
                    if int(completed.value) >= total_blocks:
                        break
                if idle_deadline is None:
                    idle_deadline = time.monotonic() + max_idle_s
                elif time.monotonic() > idle_deadline:
                    break
                time.sleep(0.0002)
                continue
            idle_deadline = None
            length = min(read_bytes, file_size - bid * read_bytes)
            offset = bid * read_bytes
            claim, gate_wait_ns = _alloc_gate(pacer_lock, last_start, gap_ns, clock)
            map_ms = 0.0
            unmap_ms = 0.0
            win_addr = 0
            if mmap_mode == "window":
                w_start = offset & ~(_PAGE - 1)
                w_len = ((offset + length - w_start + _PAGE - 1) // _PAGE) * _PAGE
                t = int(clock())
                win_addr = int(_LIBC.mmap(None, w_len, _PROT_READ,
                                          _MAP_PRIVATE | _MAP_POPULATE, fd, w_start))
                map_ms = (int(clock()) - t) / 1e6
                if win_addr in (0, -1) or win_addr == 0xFFFFFFFFFFFFFFFF:
                    with lock:
                        completed.value = int(completed.value) + 1
                        ownership[bid] = 2
                    continue
                ptr = win_addr + (offset - w_start)
            else:
                ptr = mm_base + offset
            mem_dest = dest_addr
            if staging is not None:
                stage_seq = int(stage_published.value)
                if stage_seq - int(stage_consumed.value) >= stage_slots:
                    wait_t0 = int(clock())
                    while stage_seq - int(stage_consumed.value) >= stage_slots:
                        time.sleep(0.0001)
                    slot_wait_ms += (int(clock()) - wait_t0) / 1e6
                    slot_wait_events += 1
                stage_i = stage_seq % stage_slots
                stage_off[stage_i] = offset
                stage_len[stage_i] = length
                mem_dest = stage_lane_base + stage_i * read_bytes
            enter = int(clock())
            sink = 0
            err = None
            try:
                if consume_mode == "memcpy":
                    _LIBC.memcpy(mem_dest, ptr, length)
                elif consume_mode == "d0":
                    sink = int(lib.st_touch_pages(_ct.c_void_p(ptr),
                                                  _ct.c_size_t(length), 4096))
                elif consume_mode == "d1":
                    sink = int(lib.st_touch_lines(_ct.c_void_p(ptr),
                                                  _ct.c_size_t(length), 64))
                else:
                    sink = int(lib.st_reduce_full(_ct.c_void_p(ptr),
                                                  _ct.c_size_t(length)))
                got = length
            except BaseException as exc:  # noqa: BLE001
                got = -1
                err = f"{type(exc).__name__}:{str(exc)[:160]}"
            exit_ns = int(clock())
            if staging is not None:
                # Publish only after the native memcpy has fully returned.
                stage_published.value = stage_seq + 1
            if mmap_mode == "window" and win_addr:
                t = int(clock())
                _LIBC.munmap(win_addr, ((offset + length - (offset & ~(_PAGE - 1))
                                         + _PAGE - 1) // _PAGE) * _PAGE)
                unmap_ms = (int(clock()) - t) / 1e6
            with lock:
                attempts[bid] = int(attempts[bid]) + 1
                if winner[bid] == -1:
                    winner[bid] = reader_id
                    winner_kind[bid] = 1
                    winner_exit_ns[bid] = exit_ns
                    completed.value = int(completed.value) + 1
                else:
                    payload["stale"] += 1
                ownership[bid] = 2
            payload["records"].append({
                "reader": reader_id, "pid": os.getpid(), "block_id": int(bid),
                "kind": "primary", "seq": len(payload["records"]),
                "offset": offset, "length": length, "gate_claim_ns": int(claim),
                "gate_wait_ms": gate_wait_ns / 1e6,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
                "map_ms": map_ms, "unmap_ms": unmap_ms, "sink": sink, "error": err,
                "consume_mode": consume_mode,
            })
        stop_touch[0] = True
        if thr is not None:
            thr.join(timeout=5.0)
        payload["idle_no_work_ms"] = idle_total
        payload["payload_copy_bytes"] = (0 if zero_copy
                                         else sum(int(r["length"]) for r in payload["records"]))
        payload["staging_wait_ms"] = float(slot_wait_ms)
        payload["staging_wait_events"] = int(slot_wait_events)
        payload["staging_published"] = (
            int(stage_published.value) if staging is not None else 0)
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            if mm_base:
                _LIBC.munmap(mm_base, file_size)
        except BaseException:  # noqa: BLE001
            pass
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_mmap_source_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int = 4,
    mmap_mode: str = "persistent",
    consume_mode: str = "memcpy",
    touch_ahead: int = 0,
    sticky_lanes: bool = True,
    staging: dict | None = None,
    on_ready: Callable[[], None] | None = None,
    min_launch_gap_ns: int = 4_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    max_idle_s: float = 120.0,
    pacer_start_method: str = "fork",
) -> dict:
    """Pure-CPU mmap primary source pass (no preadv payload path, no GPU, no CUDA)."""
    import multiprocessing as mp  # noqa: PLC0415

    if _LIBC is None:
        raise RuntimeError("libc_unavailable")
    if mmap_mode not in ("persistent", "window"):
        raise ValueError("mmap_mode must be persistent or window")
    if consume_mode not in ("memcpy", "d0", "d1", "d2"):
        raise ValueError("consume_mode must be memcpy, d0, d1 or d2")
    if touch_ahead < 0 or touch_ahead > 2:
        raise ValueError("touch_ahead must be 0, 1 or 2")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {"path": file_path, "size": file_size,
                     "st_dev": getattr(stat_result, "st_dev", None),
                     "st_ino": getattr(stat_result, "st_ino", None),
                     "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)}
    total_blocks = (file_size + read_bytes - 1) // read_bytes

    def _blen(bid: int) -> int:
        return min(read_bytes, file_size - bid * read_bytes)
    expected_bytes = sum(_blen(b) for b in range(total_blocks))

    lanes: list[list[int]] = []
    if sticky_lanes:
        _base, _extra = divmod(total_blocks, qd)
        _cursor = 0
        for _lid in range(qd):
            _cnt = _base + (1 if _lid < _extra else 0)
            lanes.append(list(range(_cursor, _cursor + _cnt)))
            _cursor += _cnt
    else:
        for _lid in range(qd):
            lanes.append(list(range(_lid, total_blocks, qd)))
    lane_flat_list = [b for l in lanes for b in l]
    lane_off_list = [0]
    for l in lanes:
        lane_off_list.append(lane_off_list[-1] + len(l))

    ctx = mp.get_context(pacer_start_method)
    lock = ctx.Lock()
    ownership = ctx.Array("b", total_blocks, lock=False)
    winner = ctx.Array("i", [-1] * total_blocks, lock=False)
    winner_kind = ctx.Array("b", total_blocks, lock=False)
    start_ns = ctx.Array("q", total_blocks, lock=False)
    winner_exit_ns = ctx.Array("q", total_blocks, lock=False)
    attempts = ctx.Array("i", total_blocks, lock=False)
    completed = ctx.Value("i", 0, lock=False)
    next_global = ctx.Value("q", 0, lock=False)
    lane_flat = ctx.Array("i", lane_flat_list, lock=False)
    lane_off = ctx.Array("i", lane_off_list, lock=False)
    last_start = ctx.Value("q", 0)
    pacer_lock = last_start.get_lock()
    consumer_pos = ctx.Array("i", [-1] * qd, lock=False)
    touch_pos = ctx.Array("i", [0] * qd, lock=False)
    ready_count = ctx.Value("i", 0, lock=False)
    go = ctx.Value("i", 0, lock=False)

    procs: list[Any] = []
    conns: list[Any] = []
    for rid in range(qd):
        cp, cc = ctx.Pipe(duplex=False)
        p = cast(Any, ctx).Process(
            target=_mm2_child,
            args=((rid, file_path, file_size, read_bytes, mmap_mode, consume_mode,
                   touch_ahead, lane_flat, lane_off, qd, sticky_lanes, ownership,
                   winner, winner_kind, start_ns, winner_exit_ns, attempts, completed,
                   lock, next_global, last_start, pacer_lock, min_launch_gap_ns,
                   total_blocks, max_idle_s, consumer_pos, touch_pos, None,
                   ready_count, go, cc, staging),),
            daemon=True)
        p.start(); cc.close(); conns.append(cp); procs.append(p)

    barrier_error = None
    release_ns = None
    deadline = time.monotonic() + ready_timeout_s
    try:
        while int(ready_count.value) < qd:
            dead = [i for i, pr in enumerate(procs) if not pr.is_alive()]
            if dead:
                errs = []
                for i in dead:
                    try:
                        errs.append({i: conns[i].recv()})
                    except BaseException as exc:  # noqa: BLE001
                        errs.append({i: f"no_payload:{type(exc).__name__}"})
                raise RuntimeError(f"reader_died_during_setup:{dead}:{errs}")
            if time.monotonic() > deadline:
                raise TimeoutError("readers_not_ready")
            time.sleep(0.002)
        if on_ready is not None:
            # Post-fork, pre-source setup hook (CUDA context + host
            # registration).  Readers are parked on `go`.
            on_ready()
        release_ns = int(clock_ns())
        go.value = 1
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    payloads: list[dict[str, Any]] = []
    for rid, proc in enumerate(procs):
        proc.join(timeout=ready_timeout_s)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=30.0)
    for rid, conn in enumerate(conns):
        try:
            payloads.append(conn.recv())
        except BaseException as exc:  # noqa: BLE001
            payloads.append({"reader": rid, "status": "error",
                             "error": f"recv_failed:{type(exc).__name__}",
                             "records": []})
    for conn in conns:
        try:
            conn.close()
        except BaseException:  # noqa: BLE001
            pass

    reader_errors = [{"reader": p.get("reader"), "error": p.get("error")}
                     for p in payloads if p.get("status") != "ok"]
    records = [r for p in payloads for r in (p.get("records") or [])]
    records.sort(key=lambda r: int(r["preadv_enter_ns"]))
    stale = sum(int(p.get("stale") or 0) for p in payloads)
    affinity_breaks = sum(int(p.get("affinity_breaks") or 0) for p in payloads)
    idle_no_work_ms = [float(p.get("idle_no_work_ms") or 0.0) for p in payloads]
    touch_events = [e for p in payloads for e in (p.get("touch_events") or [])]
    if not records:
        raise RuntimeError(
            f"no_reads:{barrier_error or 'readers_failed'}:errors={reader_errors}")

    durations = [r["preadv_ms"] for r in records]
    useful_bytes = sum(r["bytes_returned"] for r in records if (r["bytes_returned"] or 0) > 0)
    first_enter = min(int(r["preadv_enter_ns"]) for r in records)
    last_exit = max(int(r["preadv_exit_ns"]) for r in records)
    wall_ms = (last_exit - first_enter) / 1e6

    logical: list[dict[str, Any]] = []
    reader_blocks_won = [0] * qd
    for bid in range(total_blocks):
        if winner[bid] == -1:
            continue
        exit_ns = int(winner_exit_ns[bid])
        win = next((r for r in records
                    if r["block_id"] == bid and int(r["preadv_exit_ns"]) == exit_ns), None)
        rid = int(winner[bid])
        reader_blocks_won[rid] += 1
        logical.append({
            "worker": rid, "block_id": bid, "offset": bid * read_bytes,
            "length": _blen(bid), "accepted": "primary",
            "bytes_returned": (win or {}).get("bytes_returned", 0),
            "logical_enter_ns": (win or {}).get("preadv_enter_ns", 0),
            "logical_exit_ns": exit_ns,
            "logical_ms": ((exit_ns - (win or {}).get("preadv_enter_ns", 0)) / 1e6),
        })
    logical.sort(key=lambda r: r["block_id"])
    completed_n = len(logical)

    completed_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    covered_bytes = sum(r["length"] for r in logical)
    ordered = sorted(logical, key=lambda r: r["offset"])
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    published_once = all(int(attempts[b]) >= 1 and winner[b] != -1
                         for b in range(total_blocks))

    claims = sorted(int(r["gate_claim_ns"]) for r in records)
    claim_gaps = [(claims[i] - claims[i - 1]) / 1e6 for i in range(1, len(claims))]
    ev: list[tuple[int, int]] = []
    for r in records:
        ev.append((int(r["preadv_enter_ns"]), 1))
        ev.append((int(r["preadv_exit_ns"]), -1))
    ev.sort()
    conc = 0
    observed_max = 0
    for _, dd in ev:
        conc += dd
        observed_max = max(observed_max, conc)

    # Toucher/consumer relationship per block.
    touch_by_block = {e["block_id"]: e for e in touch_events}
    relationship = []
    for r in records:
        b = r["block_id"]
        te = touch_by_block.get(b)
        if te is None:
            continue
        relationship.append({
            "block_id": b,
            "touch_ms": te["touch_ms"],
            "consumer_ms": r["preadv_ms"],
            "lead_ms": (int(r["preadv_enter_ns"]) - int(te["touch_end_ns"])) / 1e6,
            "state": ("READY_AHEAD" if int(te["touch_end_ns"]) <= int(r["preadv_enter_ns"])
                      else "CONSUMER_CAUGHT_TOUCHER"),
            "toucher_sick": bool(te["touch_ms"] >= 250.0),
        })

    return {
        "schema_version": 1,
        "kind": "mmap_source_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "mmap_source", "mmap_mode": mmap_mode,
            "consume_mode": consume_mode, "touch_ahead": touch_ahead,
            "zero_copy": consume_mode != "memcpy",
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": f"mmap:{mmap_mode}+{consume_mode}",
                "multiprocessing_start_method": ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "mmap_source",
        "mmap_mode": mmap_mode,
        "consume_mode": consume_mode,
        "touch_ahead": touch_ahead,
        "payload_copy_bytes": sum(int(p.get("payload_copy_bytes") or 0) for p in payloads),
        "payload_copy_bytes_per_block": (0.0 if consume_mode != "memcpy"
                                         else read_bytes),
        "dest_allocated": any(bool(p.get("dest_allocated")) for p in payloads),
        "staging": {
            "enabled": staging is not None,
            "slots": (int(staging["slots"]) if staging is not None else 0),
            "bytes": (int(staging["bytes"]) if staging is not None else 0),
            "wait_ms_total": sum(float(p.get("staging_wait_ms") or 0) for p in payloads),
            "wait_events_total": sum(int(p.get("staging_wait_events") or 0) for p in payloads),
            "published_total": sum(int(p.get("staging_published") or 0) for p in payloads),
            "reader_wait_ms": [float(p.get("staging_wait_ms") or 0) for p in payloads],
            "reader_published": [int(p.get("staging_published") or 0) for p in payloads],
        },
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in records if r.get("pid") is not None}),
        "reader_pids": [p.get("pid") for p in payloads],
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": reader_errors,
        "physical_reads": len(logical),
        "physical_attempts": len(records),
        "physical_amplification": (len(records) / total_blocks),
        "stale_duplicates": stale,
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": ((completed_bytes / (wall_ms / 1000.0) / 1e9)
                                   if wall_ms else None),
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000, 2000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "blocks_expected": total_blocks, "blocks_completed": completed_n,
            "all_blocks_published_once": published_once,
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_reads_returned_full_length": all(
                (r["bytes_returned"] or 0) == r["length"] for r in logical),
            "covers_entire_file_exactly_once": bool(
                completed_n == total_blocks and completed_bytes == expected_bytes == file_size
                and no_overlap and contiguous),
        },
        "scheduler": {
            "selfservice": True,
            "max_physical_qd_observed": observed_max,
            "max_physical_qd_structural": qd,
            "min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "median_global_claim_gap_ms": percentile(claim_gaps, 50) if claim_gaps else None,
            "reader_blocks_won": reader_blocks_won,
            "idle_no_work_ms": idle_no_work_ms,
            "dispatches": len(records),
            "sticky_lanes": bool(sticky_lanes),
            "lane_sizes": [len(l) for l in lanes],
            "affinity_breaks": affinity_breaks,
            "allocator_latency_median_ms": None,
            "touch_events": len(touch_events),
            "touch_concurrency_note": ("toucher threads add real backing fetches; the "
                                       "consumer concurrency below is NOT total source "
                                       "activity when touch_ahead > 0"),
            "consumer_concurrency_max": observed_max,
        },
        "pacer": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                  "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None},
        "launch_spacing": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                           "mean_effective_concurrency": None,
                           "max_simultaneous_in_flight": observed_max},
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": records,
        "allocator_dispatches": [],
        "touch_events": touch_events,
        "touch_relationship": relationship,
    }


def _mlc_child(args: tuple) -> None:
    """One of three mmap LIFE-CYCLE architectures, identical consumer everywhere.

    lifecycle="whole"      A: mmap the whole file once, keep alive, memcpy assigned ranges.
    lifecycle="segmented"  B: one exact mmap per 64 MiB window created up front for this
                              reader's lane, all kept alive for the whole run, then memcpy.
                              Mapping creation must NOT touch payload.
    lifecycle="fresh"      C: current M2 behaviour - map exact window, memcpy, munmap, repeat.

    All three use the same native memcpy into the same kind of preallocated destination.
    MAP_POPULATE is only applied when populate=True (sanity check); otherwise never.
    """
    (reader_id, file_path, file_size, read_bytes, lifecycle, populate, lane_flat,
     lane_off, qd, sticky, ownership, winner, winner_kind, start_ns, winner_exit_ns,
     attempts, completed, lock, next_global, last_start, pacer_lock, gap_ns,
     total_blocks, max_idle_s, prep_ns, live_maps, map_bytes, map_errors,
     unmap_errors, ready_count, go, child_conn, map_shared, cpu_instrument,
     affinity, fixed_va, staging) = args
    payload: dict[str, Any] = {"reader": reader_id, "pid": os.getpid(),
                               "status": "ok", "records": [], "stale": 0,
                               "affinity_breaks": 0, "idle_no_work_ms": 0.0,
                               "claimed": 0, "exit_reason": None,
                               "lane_len": 0, "prep_maps": 0,
                               "affinity": None, "fixed_va": None,
                               "staging_wait_ms": 0.0, "staging_wait_events": 0,
                               "staging_published": 0}
    fd = -1
    replacements = 0
    replacement_errors = 0
    slot_base = 0
    slot_len = 0
    clock = time.perf_counter_ns
    maps: list[tuple[int, int, int]] = []   # (addr, length, block_or_-1)
    try:
        if _LIBC is None:
            raise RuntimeError("libc_unavailable")
        if staging is None:
            dest = bytearray(read_bytes)
            dest_addr = _ct.addressof(_ct.c_char.from_buffer(dest))
            stage_published = None
        else:
            # Additive seam: write produced bytes into the caller's shared
            # staging region instead of a process-private bytearray.  The
            # source algorithm, scheduling, FD lifetime and timing are unchanged.
            dest = None
            dest_addr = 0
            stage_published = staging["published"][reader_id]
            stage_consumed = staging["consumed"][reader_id]
            stage_off = staging["slot_off"][reader_id]
            stage_len = staging["slot_len"][reader_id]
            stage_slots = int(staging["slots"])
            stage_lane_base = int(staging["seg_base"]) + reader_id * int(staging["lane_bytes"])
        fd = os.open(file_path, os.O_RDONLY)
        my_start = int(lane_off[reader_id])
        my_end = int(lane_off[reader_id + 1])
        # NOTE: prot and flags are separate arguments. Building the flags word with
        # _PROT_READ in it produced MAP_SHARED|MAP_PRIVATE (3) -> EINVAL for every map.
        # MAP_SHARED vs MAP_PRIVATE is the ONLY difference between the A/B arms;
        # both are PROT_READ so neither can write back to the file.
        map_flags = (_MAP_SHARED if map_shared else _MAP_PRIVATE) | (
            _MAP_POPULATE if populate else 0)

        # ---- CPU affinity (arm B): pin THIS reader to one distinct allowed CPU ----
        aff: dict[str, Any] = {"supported": False, "allowed": None, "n_allowed": None,
                               "assigned": None, "set_ok": False, "errno": None,
                               "after": None}
        if affinity:
            getter = getattr(os, "sched_getaffinity", None)
            setter = getattr(os, "sched_setaffinity", None)
            if getter is None or setter is None:
                aff["errno"] = "sched_getaffinity/sched_setaffinity unavailable"
            else:
                try:
                    allowed = sorted(int(c) for c in getter(0))
                    aff["supported"] = True
                    aff["allowed"] = allowed
                    aff["n_allowed"] = len(allowed)
                    if allowed:
                        target = allowed[reader_id % len(allowed)]
                        aff["assigned"] = target
                        try:
                            setter(0, {target})
                            aff["set_ok"] = True
                            aff["after"] = sorted(int(c) for c in getter(0))
                        except BaseException as exc:  # noqa: BLE001
                            aff["errno"] = f"{type(exc).__name__}:{exc}"
                    aff["topology"] = _cpu_topology(allowed[:qd] if allowed else [])
                except BaseException as exc:  # noqa: BLE001
                    aff["errno"] = f"{type(exc).__name__}:{exc}"
        payload["affinity"] = aff

        # ---- preparation phase (mapping creation; no payload dereference) ----
        prep_t0 = int(clock())
        seg_addr: dict[int, int] = {}
        whole_base = 0
        if fixed_va:
            # Reserve ONE VA range that THIS reader exclusively owns, then only ever
            # MAP_FIXED inside it.  Never MAP_FIXED over an arbitrary address.
            slot_len = ((read_bytes + _PAGE - 1) // _PAGE) * _PAGE
            slot_base = int(_LIBC.mmap(None, slot_len, _PROT_NONE,
                                       _MAP_PRIVATE | _MAP_ANONYMOUS, -1, 0))
            if slot_base in (0, -1) or slot_base == 0xFFFFFFFFFFFFFFFF:
                raise OSError(f"fixed_va_reserve_failed errno={_ct.get_errno()}")
            if slot_base % _PAGE:
                raise OSError(f"fixed_va_reserve_unaligned base={slot_base}")
            maps.append((slot_base, slot_len, -2))   # -2 marks the owned reservation
        if lifecycle == "whole":
            whole_base = int(_LIBC.mmap(None, file_size, _PROT_READ,
                                        _MAP_PRIVATE | (_MAP_POPULATE if populate else 0),
                                        fd, 0))
            if whole_base in (0, -1) or whole_base == 0xFFFFFFFFFFFFFFFF:
                with lock:
                    map_errors.value = int(map_errors.value) + 1
                raise OSError(f"whole_mmap_failed errno={_ct.get_errno()}")
            maps.append((whole_base, file_size, -1))
        elif lifecycle == "segmented":
            for b in range(my_start, my_end):
                off = b * read_bytes
                length = min(read_bytes, file_size - off)
                w_len = ((length + _PAGE - 1) // _PAGE) * _PAGE
                addr = int(_LIBC.mmap(None, w_len, _PROT_READ, map_flags, fd, off))
                if addr in (0, -1) or addr == 0xFFFFFFFFFFFFFFFF:
                    with lock:
                        map_errors.value = int(map_errors.value) + 1
                    raise OSError(f"seg_mmap_failed block={b} errno={_ct.get_errno()}")
                seg_addr[b] = addr
                maps.append((addr, w_len, b))
        prep_t1 = int(clock())
        with lock:
            prep_ns[reader_id] = prep_t1 - prep_t0
            live_maps.value = int(live_maps.value) + len(maps)
            map_bytes.value = int(map_bytes.value) + sum(m[1] for m in maps)
        peak_maps_local = len(maps)

        # CPU clock for the memcpy CPU-vs-wall measurement (OPT-IN: with
        # cpu_instrument=False the source path below is byte-identical).  gVisor
        # stubs some clocks, so a candidate is accepted ONLY if it advances
        # across real CPU work; otherwise it would be read as zero CPU forever.
        cpu_clock = None
        cpu_clock_kind = "unavailable"
        cpu_probe_notes: list[str] = []
        if cpu_instrument:
            for _kind, _fn in _make_cpu_clock_probes():
                try:
                    _a = int(_fn())
                    _ = sum(range(2_000_000))   # tens of ms of real CPU work
                    _b = int(_fn())
                except BaseException as exc:  # noqa: BLE001
                    cpu_probe_notes.append(f"{_kind}:error:{type(exc).__name__}")
                    continue
                if _b > _a:
                    cpu_clock = _fn
                    cpu_clock_kind = _kind
                    break
                cpu_probe_notes.append(f"{_kind}:stuck")

        with lock:
            ready_count.value = int(ready_count.value) + 1
        while int(go.value) == 0:
            time.sleep(0.001)

        # ---- consumption phase ----
        my_lane = [int(lane_flat[i]) for i in range(my_start, my_end)]
        payload["lane_len"] = len(my_lane)
        payload["prep_maps"] = len(maps)
        cursor = 0
        idle_total = 0.0
        idle_deadline: float | None = None
        first_enter = 0
        last_exit = 0
        cpu_first = 0
        cpu_last = 0
        fresh_map_ms = 0.0
        fresh_unmap_ms = 0.0
        slot_wait_ms = 0.0
        slot_wait_events = 0
        stage_seq = 0
        while True:
            with lock:
                if int(completed.value) >= total_blocks:
                    payload["exit_reason"] = "completed_at_loop_top"
                    break
            bid = -1
            now = int(clock())
            with lock:
                while cursor < len(my_lane):
                    cand = my_lane[cursor]
                    cursor += 1
                    if ownership[cand] == 0:
                        bid = cand
                        break
                if bid < 0:
                    for lid in range(qd):
                        if lid == reader_id:
                            continue
                        s = int(lane_off[lid])
                        e = int(lane_off[lid + 1])
                        for i in range(s, e):
                            cand = int(lane_flat[i])
                            if ownership[cand] == 0:
                                bid = cand
                                payload["affinity_breaks"] += 1
                                break
                        if bid >= 0:
                            break
                if bid >= 0:
                    ownership[bid] = 1
                    start_ns[bid] = now
                    payload["claimed"] += 1
            if bid < 0:
                idle_total += (int(clock()) - now) / 1e6
                with lock:
                    if int(completed.value) >= total_blocks:
                        payload["exit_reason"] = "completed_while_idle"
                        break
                if idle_deadline is None:
                    idle_deadline = time.monotonic() + max_idle_s
                elif time.monotonic() > idle_deadline:
                    payload["exit_reason"] = "idle_timeout"
                    break
                time.sleep(0.0002)
                continue
            idle_deadline = None
            length = min(read_bytes, file_size - bid * read_bytes)
            offset = bid * read_bytes
            claim, gate_wait_ns = _alloc_gate(pacer_lock, last_start, gap_ns, clock)
            map_ms = 0.0
            unmap_ms = 0.0
            win_addr = 0
            win_len = 0
            if lifecycle == "whole":
                ptr = whole_base + offset
            elif lifecycle == "segmented":
                ptr = seg_addr[bid]
            else:
                w_len = ((length + _PAGE - 1) // _PAGE) * _PAGE
                t = int(clock())
                if fixed_va:
                    # Replace the previous window AT our owned slot.  Never any
                    # other address: the target is exactly slot_base.
                    win_addr = int(_LIBC.mmap(slot_base, w_len, _PROT_READ,
                                              map_flags | _MAP_FIXED, fd, offset))
                else:
                    win_addr = int(_LIBC.mmap(None, w_len, _PROT_READ, map_flags, fd, offset))
                map_ms = (int(clock()) - t) / 1e6
                if win_addr in (0, -1) or win_addr == 0xFFFFFFFFFFFFFFFF:
                    if fixed_va:
                        replacement_errors += 1
                    with lock:
                        map_errors.value = int(map_errors.value) + 1
                        completed.value = int(completed.value) + 1
                        ownership[bid] = 2
                    continue
                if fixed_va:
                    if win_addr != slot_base:
                        # MAP_FIXED did not honour the owned slot -> do not touch
                        # memory at an unknown address; fail this reader loudly.
                        replacement_errors += 1
                        raise OSError(
                            f"fixed_va_addr_mismatch got={win_addr} want={slot_base}")
                    replacements += 1
                ptr = win_addr
                win_len = w_len
                fresh_map_ms += map_ms
            mem_dest = dest_addr
            if staging is not None:
                stage_seq = int(stage_published.value)
                if stage_seq - int(stage_consumed.value) >= stage_slots:
                    wait_t0 = int(clock())
                    while stage_seq - int(stage_consumed.value) >= stage_slots:
                        time.sleep(0.0001)
                    slot_wait_ms += (int(clock()) - wait_t0) / 1e6
                    slot_wait_events += 1
                stage_i = stage_seq % stage_slots
                stage_off[stage_i] = offset
                stage_len[stage_i] = length
                mem_dest = stage_lane_base + stage_i * read_bytes
            cpu_t0 = int(cpu_clock()) if cpu_clock is not None else 0
            enter = int(clock())
            err = None
            try:
                _LIBC.memcpy(mem_dest, ptr, length)
                got = length
            except BaseException as exc:  # noqa: BLE001
                got = -1
                err = f"{type(exc).__name__}:{str(exc)[:160]}"
            exit_ns = int(clock())
            if staging is not None:
                # Publish only after the native memcpy has fully returned, so a
                # consumer can never observe a partially written slot.
                stage_published.value = stage_seq + 1
            cpu_t1 = int(cpu_clock()) if cpu_clock is not None else 0
            if lifecycle == "fresh" and win_addr and not fixed_va:
                t = int(clock())
                _LIBC.munmap(win_addr, win_len)
                unmap_ms = (int(clock()) - t) / 1e6
                fresh_unmap_ms += unmap_ms
            if first_enter == 0:
                first_enter = enter
                cpu_first = cpu_t1
            last_exit = exit_ns
            cpu_last = cpu_t1
            with lock:
                attempts[bid] = int(attempts[bid]) + 1
                if winner[bid] == -1:
                    winner[bid] = reader_id
                    winner_kind[bid] = 1
                    winner_exit_ns[bid] = exit_ns
                    completed.value = int(completed.value) + 1
                else:
                    payload["stale"] += 1
                ownership[bid] = 2
            payload["records"].append({
                "reader": reader_id, "pid": os.getpid(), "block_id": int(bid),
                "kind": "primary", "seq": len(payload["records"]),
                "offset": offset, "length": length, "gate_claim_ns": int(claim),
                "gate_wait_ms": gate_wait_ns / 1e6,
                "map_ms": map_ms, "unmap_ms": unmap_ms,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
                "error": err, "lifecycle": lifecycle,
                "cpu_ms": ((cpu_t1 - cpu_t0) / 1e6) if cpu_clock is not None else None,
                "cpu_fraction": (((cpu_t1 - cpu_t0) / (exit_ns - enter))
                                 if (cpu_clock is not None and exit_ns > enter) else None),
                "cpu_clock": cpu_clock_kind,
            })
        payload["idle_no_work_ms"] = idle_total
        payload["first_enter_ns"] = first_enter
        payload["last_exit_ns"] = last_exit
        payload["fresh_map_ms"] = fresh_map_ms
        payload["staging_wait_ms"] = float(slot_wait_ms)
        payload["staging_wait_events"] = int(slot_wait_events)
        payload["staging_published"] = (
            int(stage_published.value) if staging is not None else 0)
        payload["fixed_va"] = {
            "enabled": bool(fixed_va),
            "slot_base": slot_base,
            "slot_len": slot_len,
            "slot_aligned": (slot_base % _PAGE == 0) if fixed_va else None,
            "replacements": replacements,
            "replacement_errors": replacement_errors,
            "peak_live_mappings": 1 if fixed_va else 0,
            # REAL leak check performed after cleanup, not an assertion.
            "final_live_mappings": int(bool(payload.get("slot_leaked_after_cleanup"))),
            "slot_leaked_after_cleanup": bool(payload.get("slot_leaked_after_cleanup")),
        }
        payload["fresh_unmap_ms"] = fresh_unmap_ms
        # Whole-window CPU consumption (robust even when the clock is coarse):
        # summed across readers this answers "is the wall CPU work or waiting".
        payload["cpu_ns_window"] = ((cpu_last - cpu_first)
                                    if (cpu_clock is not None and cpu_last >= cpu_first)
                                    else None)
        payload["cpu_probe_notes"] = cpu_probe_notes
        payload["peak_maps_local"] = peak_maps_local
        payload["cpu_clock_kind"] = cpu_clock_kind

        # ---- cleanup phase ----
        cleanup_t0 = int(clock())
        for addr, ln, _b in maps:
            try:
                _LIBC.munmap(addr, ln)
            except BaseException:  # noqa: BLE001
                with lock:
                    unmap_errors.value = int(unmap_errors.value) + 1
        cleanup_t1 = int(clock())
        payload["cleanup_ns"] = cleanup_t1 - cleanup_t0
        payload["slot_leaked_after_cleanup"] = (
            _slot_still_mapped(slot_base, slot_len) if fixed_va else False)
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        for addr, ln, _b in maps:
            try:
                _LIBC.munmap(addr, ln)
            except BaseException:  # noqa: BLE001
                pass
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_mmap_lifecycle_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int = 4,
    lifecycle: str = "fresh",
    populate: bool = False,
    map_shared: bool = False,
    cpu_instrument: bool = False,
    affinity: bool = False,
    fixed_va: bool = False,
    sticky_lanes: bool = True,
    staging: dict | None = None,
    on_ready: Callable[[], None] | None = None,
    min_launch_gap_ns: int = 4_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    max_idle_s: float = 120.0,
    pacer_start_method: str = "fork",
) -> dict:
    """Compare mmap life-cycle architectures with an identical memcpy consumer."""
    import multiprocessing as mp  # noqa: PLC0415

    if _LIBC is None:
        raise RuntimeError("libc_unavailable")
    if lifecycle not in ("whole", "segmented", "fresh"):
        raise ValueError("lifecycle must be whole, segmented or fresh")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if read_bytes % _PAGE:
        raise ValueError("read_bytes must be a multiple of the page size")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {"path": file_path, "size": file_size,
                     "st_dev": getattr(stat_result, "st_dev", None),
                     "st_ino": getattr(stat_result, "st_ino", None),
                     "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)}
    total_blocks = (file_size + read_bytes - 1) // read_bytes

    def _blen(bid: int) -> int:
        return min(read_bytes, file_size - bid * read_bytes)
    expected_bytes = sum(_blen(b) for b in range(total_blocks))

    lanes: list[list[int]] = []
    if sticky_lanes:
        _base, _extra = divmod(total_blocks, qd)
        _cursor = 0
        for _lid in range(qd):
            _cnt = _base + (1 if _lid < _extra else 0)
            lanes.append(list(range(_cursor, _cursor + _cnt)))
            _cursor += _cnt
    else:
        for _lid in range(qd):
            lanes.append(list(range(_lid, total_blocks, qd)))
    lane_flat_list = [b for l in lanes for b in l]
    lane_off_list = [0]
    for l in lanes:
        lane_off_list.append(lane_off_list[-1] + len(l))

    ctx = mp.get_context(pacer_start_method)
    lock = ctx.Lock()
    ownership = ctx.Array("b", total_blocks, lock=False)
    winner = ctx.Array("i", [-1] * total_blocks, lock=False)
    winner_kind = ctx.Array("b", total_blocks, lock=False)
    start_ns = ctx.Array("q", total_blocks, lock=False)
    winner_exit_ns = ctx.Array("q", total_blocks, lock=False)
    attempts = ctx.Array("i", total_blocks, lock=False)
    completed = ctx.Value("i", 0, lock=False)
    next_global = ctx.Value("q", 0, lock=False)
    lane_flat = ctx.Array("i", lane_flat_list, lock=False)
    lane_off = ctx.Array("i", lane_off_list, lock=False)
    last_start = ctx.Value("q", 0)
    pacer_lock = last_start.get_lock()
    prep_ns = ctx.Array("q", [0] * qd, lock=False)
    live_maps = ctx.Value("i", 0, lock=False)
    map_bytes = ctx.Value("q", 0, lock=False)
    map_errors = ctx.Value("i", 0, lock=False)
    unmap_errors = ctx.Value("i", 0, lock=False)
    ready_count = ctx.Value("i", 0, lock=False)
    go = ctx.Value("i", 0, lock=False)

    procs: list[Any] = []
    conns: list[Any] = []
    for rid in range(qd):
        cp, cc = ctx.Pipe(duplex=False)
        p = cast(Any, ctx).Process(
            target=_mlc_child,
            args=((rid, file_path, file_size, read_bytes, lifecycle, populate,
                   lane_flat, lane_off, qd, sticky_lanes, ownership, winner,
                   winner_kind, start_ns, winner_exit_ns, attempts, completed, lock,
                   next_global, last_start, pacer_lock, min_launch_gap_ns,
                   total_blocks, max_idle_s, prep_ns, live_maps, map_bytes,
                   map_errors, unmap_errors, ready_count, go, cc,
                   bool(map_shared), bool(cpu_instrument),
                   bool(affinity), bool(fixed_va), staging),),
            daemon=True)
        p.start(); cc.close(); conns.append(cp); procs.append(p)

    barrier_error = None
    release_ns = None
    deadline = time.monotonic() + ready_timeout_s
    try:
        while int(ready_count.value) < qd:
            dead = [i for i, pr in enumerate(procs) if not pr.is_alive()]
            if dead:
                errs = []
                for i in dead:
                    try:
                        errs.append({i: conns[i].recv()})
                    except BaseException as exc:  # noqa: BLE001
                        errs.append({i: f"no_payload:{type(exc).__name__}"})
                raise RuntimeError(f"reader_died_during_setup:{dead}:{errs}")
            if time.monotonic() > deadline:
                raise TimeoutError("readers_not_ready")
            time.sleep(0.002)
        if on_ready is not None:
            # Post-fork, pre-source setup hook (e.g. CUDA context + host
            # registration).  Readers are parked on `go`, so this cannot be
            # attributed to source production.  With on_ready=None the path is
            # byte-identical to the frozen harness.
            on_ready()
        release_ns = int(clock_ns())
        go.value = 1
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    payloads: list[dict[str, Any]] = []
    for rid, proc in enumerate(procs):
        proc.join(timeout=ready_timeout_s)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=30.0)
    for rid, conn in enumerate(conns):
        try:
            payloads.append(conn.recv())
        except BaseException as exc:  # noqa: BLE001
            payloads.append({"reader": rid, "status": "error",
                             "error": f"recv_failed:{type(exc).__name__}",
                             "records": []})
    for conn in conns:
        try:
            conn.close()
        except BaseException:  # noqa: BLE001
            pass

    reader_errors = [{"reader": p.get("reader"), "error": p.get("error")}
                     for p in payloads if p.get("status") != "ok"]
    records = [r for p in payloads for r in (p.get("records") or [])]
    records.sort(key=lambda r: int(r["preadv_enter_ns"]))
    stale = sum(int(p.get("stale") or 0) for p in payloads)
    affinity_breaks = sum(int(p.get("affinity_breaks") or 0) for p in payloads)
    idle_no_work_ms = [float(p.get("idle_no_work_ms") or 0.0) for p in payloads]
    prep_total_ms = sum(int(prep_ns[i]) for i in range(qd)) / 1e6
    prep_max_ms = (max(int(prep_ns[i]) for i in range(qd)) / 1e6) if qd else 0.0
    cleanup_total_ms = sum(int(p.get("cleanup_ns") or 0) for p in payloads) / 1e6
    cleanup_max_ms = (max((int(p.get("cleanup_ns") or 0) for p in payloads),
                          default=0) / 1e6)
    if not records:
        diag = [{"r": p.get("reader"), "st": p.get("status"),
                 "claimed": p.get("claimed"), "why": p.get("exit_reason"),
                 "lane": p.get("lane_len"), "prep": p.get("prep_maps"),
                 "rec": len(p.get("records") or []), "err": p.get("error")}
                for p in payloads]
        raise RuntimeError(
            f"no_reads:{barrier_error or 'readers_failed'}:errors={reader_errors}:diag={diag}")

    durations = [r["preadv_ms"] for r in records]
    useful_bytes = sum(r["bytes_returned"] for r in records if (r["bytes_returned"] or 0) > 0)
    first_enter = min(int(r["preadv_enter_ns"]) for r in records)
    last_exit = max(int(r["preadv_exit_ns"]) for r in records)
    wall_ms = (last_exit - first_enter) / 1e6

    logical: list[dict[str, Any]] = []
    reader_blocks_won = [0] * qd
    for bid in range(total_blocks):
        if winner[bid] == -1:
            continue
        exit_ns = int(winner_exit_ns[bid])
        win = next((r for r in records
                    if r["block_id"] == bid and int(r["preadv_exit_ns"]) == exit_ns), None)
        rid = int(winner[bid])
        reader_blocks_won[rid] += 1
        logical.append({
            "worker": rid, "block_id": bid, "offset": bid * read_bytes,
            "length": _blen(bid), "accepted": "primary",
            "bytes_returned": (win or {}).get("bytes_returned", 0),
            "logical_enter_ns": (win or {}).get("preadv_enter_ns", 0),
            "logical_exit_ns": exit_ns,
            "logical_ms": ((exit_ns - (win or {}).get("preadv_enter_ns", 0)) / 1e6),
        })
    logical.sort(key=lambda r: r["block_id"])
    completed_n = len(logical)

    completed_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    covered_bytes = sum(r["length"] for r in logical)
    ordered = sorted(logical, key=lambda r: r["offset"])
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    published_once = all(int(attempts[b]) >= 1 and winner[b] != -1
                         for b in range(total_blocks))

    claims = sorted(int(r["gate_claim_ns"]) for r in records)
    claim_gaps = [(claims[i] - claims[i - 1]) / 1e6 for i in range(1, len(claims))]
    ev: list[tuple[int, int]] = []
    for r in records:
        ev.append((int(r["preadv_enter_ns"]), 1))
        ev.append((int(r["preadv_exit_ns"]), -1))
    ev.sort()
    conc = 0
    observed_max = 0
    for _, dd in ev:
        conc += dd
        observed_max = max(observed_max, conc)

    # operation cost by arm semantics
    def _op(r: dict) -> float:
        if lifecycle == "fresh":
            return float(r.get("map_ms") or 0) + float(r.get("preadv_ms") or 0) \
                + float(r.get("unmap_ms") or 0)
        return float(r.get("preadv_ms") or 0)

    ops = [_op(r) for r in records]
    first_use_inclusive_ms = prep_max_ms + wall_ms + cleanup_max_ms

    # Aggregate CPU consumption over the measured source window, summed across
    # readers.  Robust even when the only working clock is coarse (tick-based):
    # a value near the reader count means CPU-bound, near zero means waiting.
    cpu_clock_kind = payloads[0].get("cpu_clock_kind") if payloads else "unavailable"
    _cw = [p.get("cpu_ns_window") for p in payloads]
    cpu_window_available = any(v is not None for v in _cw)
    cpu_window_ns_total = sum(int(v) for v in _cw if v is not None)
    cpu_agg_fraction = ((cpu_window_ns_total / 1e6) / wall_ms
                        if (cpu_window_available and wall_ms) else None)

    return {
        "schema_version": 1,
        "kind": "mmap_lifecycle_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "mmap_lifecycle", "lifecycle": lifecycle,
            "populate": bool(populate),
            "map_shared": bool(map_shared),
            "cpu_instrument": bool(cpu_instrument),
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(),
                "syscall_impl": f"mmap:{lifecycle}" + ("+POPULATE" if populate else ""),
                "multiprocessing_start_method": ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "mmap_lifecycle",
        "lifecycle": lifecycle,
        "populate": bool(populate),
        "map_shared": bool(map_shared),
        "cpu_instrument": bool(cpu_instrument),
        "cpu_clock_kind": (payloads[0].get("cpu_clock_kind") if payloads else "unavailable"),
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in records if r.get("pid") is not None}),
        "reader_pids": [p.get("pid") for p in payloads],
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": reader_errors,
        "physical_reads": len(logical),
        "physical_attempts": len(records),
        "physical_amplification": (len(records) / total_blocks),
        "stale_duplicates": stale,
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "full_file_wall_ms": wall_ms,
        "full_file_decimal_gbps": ((completed_bytes / (wall_ms / 1000.0) / 1e9)
                                   if wall_ms else None),
        "cpu_aggregate": {
            "clock_kind": cpu_clock_kind,
            "cpu_ms_window_total": (cpu_window_ns_total / 1e6) if cpu_window_available else None,
            "wall_ms": wall_ms,
            "aggregate_cpu_fraction_of_wall": cpu_agg_fraction,
            "probe_notes": [p.get("cpu_probe_notes") for p in payloads],
        },
        "affinity": bool(affinity),
        "affinity_audit": [p.get("affinity") for p in payloads],
        "fixed_va": bool(fixed_va),
        "fixed_va_telemetry": {
            "enabled": bool(fixed_va),
            "slots": [p.get("fixed_va") for p in payloads],
            "replacements_total": sum(int((p.get("fixed_va") or {}).get("replacements") or 0)
                                      for p in payloads),
            "replacement_errors_total": sum(
                int((p.get("fixed_va") or {}).get("replacement_errors") or 0)
                for p in payloads),
            "peak_live_mappings": max(
                (int((p.get("fixed_va") or {}).get("peak_live_mappings") or 0)
                 for p in payloads), default=0),
            "final_live_mappings": max(
                (int((p.get("fixed_va") or {}).get("final_live_mappings") or 0)
                 for p in payloads), default=0),
        },
        "fully_cleaned_wall_ms": wall_ms + cleanup_max_ms,
        "staging": {
            "enabled": staging is not None,
            "slots": (int(staging["slots"]) if staging is not None else 0),
            "bytes": (int(staging["bytes"]) if staging is not None else 0),
            "wait_ms_total": sum(float(p.get("staging_wait_ms") or 0) for p in payloads),
            "wait_events_total": sum(int(p.get("staging_wait_events") or 0) for p in payloads),
            "published_total": sum(int(p.get("staging_published") or 0) for p in payloads),
            "reader_wait_ms": [float(p.get("staging_wait_ms") or 0) for p in payloads],
            "reader_published": [int(p.get("staging_published") or 0) for p in payloads],
        },
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000, 2000)},
        "op_thresholds": {f"ge_{t}": sum(1 for d in ops if d >= t)
                          for t in (100, 150, 250, 500, 1000, 2000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "blocks_expected": total_blocks, "blocks_completed": completed_n,
            "all_blocks_published_once": published_once,
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_reads_returned_full_length": all(
                (r["bytes_returned"] or 0) == r["length"] for r in logical),
            "covers_entire_file_exactly_once": bool(
                completed_n == total_blocks and completed_bytes == expected_bytes == file_size
                and no_overlap and contiguous),
        },
        "scheduler": {
            "selfservice": True,
            "max_physical_qd_observed": observed_max,
            "max_physical_qd_structural": qd,
            "min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "median_global_claim_gap_ms": percentile(claim_gaps, 50) if claim_gaps else None,
            "reader_blocks_won": reader_blocks_won,
            "idle_no_work_ms": idle_no_work_ms,
            "dispatches": len(records),
            "sticky_lanes": bool(sticky_lanes),
            "lane_sizes": [len(l) for l in lanes],
            "affinity_breaks": affinity_breaks,
            "allocator_latency_median_ms": None,
        },
        "lifecycle_costs": {
            "prep_map_wall_ms_total": prep_total_ms,
            "prep_map_wall_ms_max_reader": prep_max_ms,
            "consume_wall_ms": wall_ms,
            "cleanup_unmap_wall_ms_total": cleanup_total_ms,
            "cleanup_unmap_wall_ms_max_reader": cleanup_max_ms,
            "first_use_inclusive_wall_ms": first_use_inclusive_ms,
            "steady_source_wall_ms": wall_ms,
            "live_mappings": int(live_maps.value),
            "mapping_bytes": int(map_bytes.value),
            "peak_mappings_per_reader_max": max((int(p.get("peak_maps_local") or 0)
                                                 for p in payloads), default=0),
            "map_errors": int(map_errors.value),
            "unmap_errors": int(unmap_errors.value),
            "fresh_map_ms_total": sum(float(p.get("fresh_map_ms") or 0) for p in payloads),
            "fresh_unmap_ms_total": sum(float(p.get("fresh_unmap_ms") or 0) for p in payloads),
        },
        "pacer": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                  "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None},
        "launch_spacing": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                           "mean_effective_concurrency": None,
                           "max_simultaneous_in_flight": observed_max},
        "reader_diagnostics": [
            {"reader": p.get("reader"), "status": p.get("status"),
             "claimed": p.get("claimed"), "exit_reason": p.get("exit_reason"),
             "lane_len": p.get("lane_len"), "prep_maps": p.get("prep_maps"),
             "records": len(p.get("records") or []), "error": p.get("error")}
            for p in payloads],
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": records,
        "allocator_dispatches": [],
        "rescue_events": [],
    }


def _du_child(args: tuple) -> None:
    """Deferred-unmap reader: mmap -> memcpy -> enqueue retire -> continue.

    Identical geometry to lifecycle="fresh" (exact window, MAP_PRIVATE, no
    populate) EXCEPT that ``munmap`` is removed from the source critical path.
    A bounded background reaper THREAD inside this process (sharing the address
    space) performs the munmap.  The retirement backlog is capped at
    ``max_retired`` mappings per reader; when full, the source worker waits for
    retirement capacity and records that wait.  VMA accumulation is therefore
    bounded.  A mapping is only retired AFTER its memcpy has fully returned, so
    the source worker never destroys a mapping it is still copying from.

    Two clocks are exposed:
      source_last_exit_ns  final memcpy exit  -> source payload ready
      drained_ns           every deferred munmap complete -> fully drained
    """
    (reader_id, file_path, file_size, read_bytes, lane_flat, lane_off, qd, sticky,
     ownership, winner, winner_kind, start_ns, winner_exit_ns, attempts, completed,
     lock, next_global, last_start, pacer_lock, gap_ns, total_blocks, max_idle_s,
     prep_ns, live_maps, map_bytes, map_errors, unmap_errors, ready_count, go,
     child_conn, max_retired) = args
    payload: dict[str, Any] = {"reader": reader_id, "pid": os.getpid(),
                               "status": "ok", "records": [], "stale": 0,
                               "affinity_breaks": 0, "idle_no_work_ms": 0.0,
                               "claimed": 0, "exit_reason": None,
                               "lane_len": 0, "prep_maps": 0}
    fd = -1
    clock = time.perf_counter_ns
    reaper = None
    try:
        if _LIBC is None:
            raise RuntimeError("libc_unavailable")
        dest = bytearray(read_bytes)
        dest_addr = _ct.addressof(_ct.c_char.from_buffer(dest))
        fd = os.open(file_path, os.O_RDONLY)      # persistent FD, opened once
        my_start = int(lane_off[reader_id])
        my_end = int(lane_off[reader_id + 1])
        # MAP_POPULATE removed: plain private read-only mapping.
        map_flags = _MAP_PRIVATE

        # ---- bounded retirement queue + in-process reaper thread ----
        retired: list[tuple[int, int]] = []
        outstanding: dict[int, int] = {}          # addr -> len, not yet munmapped
        cv = threading.Condition()
        st: dict[str, Any] = {"stop": False, "munmaps": 0, "wall_ns": 0,
                              "max_depth": 0, "depth_sum": 0, "depth_samples": 0,
                              "backpressure": 0, "wait_ns": 0, "inflight": 0,
                              "live_peak": 0}

        def _reaper_body() -> None:
            while True:
                with cv:
                    while not retired and not st["stop"]:
                        cv.wait(0.001)
                    if not retired:
                        return
                    addr, ln = retired.pop(0)
                    st["inflight"] += 1
                    cv.notify_all()
                t0 = int(clock())
                try:
                    _LIBC.munmap(addr, ln)
                except BaseException:  # noqa: BLE001
                    with lock:
                        unmap_errors.value = int(unmap_errors.value) + 1
                dt = int(clock()) - t0
                with cv:
                    st["wall_ns"] += dt
                    st["munmaps"] += 1
                    st["inflight"] -= 1
                    outstanding.pop(addr, None)
                    cv.notify_all()

        def _enqueue(addr: int, ln: int) -> float:
            """Retire one mapping.  Blocks (and records it) if the queue is full."""
            t0 = int(clock())
            waited = False
            with cv:
                if len(retired) >= max_retired:
                    st["backpressure"] += 1
                while len(retired) >= max_retired:
                    cv.wait(0.0005)
                    waited = True
                retired.append((addr, ln))
                outstanding[addr] = ln
                d = len(retired)
                st["depth_sum"] += d
                st["depth_samples"] += 1
                if d > st["max_depth"]:
                    st["max_depth"] = d
                live_now = d + st["inflight"]
                if live_now > st["live_peak"]:
                    st["live_peak"] = live_now
                cv.notify_all()
            dt = int(clock()) - t0
            if waited:
                st["wait_ns"] += dt
            return dt / 1e6

        # ---- preparation phase (no payload dereference) ----
        prep_t0 = int(clock())
        prep_t1 = int(clock())
        with lock:
            prep_ns[reader_id] = prep_t1 - prep_t0
        reaper = threading.Thread(target=_reaper_body, daemon=True)
        reaper.start()

        with lock:
            ready_count.value = int(ready_count.value) + 1
        while int(go.value) == 0:
            time.sleep(0.001)

        # ---- consumption phase ----
        my_lane = [int(lane_flat[i]) for i in range(my_start, my_end)]
        payload["lane_len"] = len(my_lane)
        cursor = 0
        idle_total = 0.0
        idle_deadline: float | None = None
        first_enter = 0
        last_exit = 0
        fresh_map_ms = 0.0
        while True:
            with lock:
                if int(completed.value) >= total_blocks:
                    payload["exit_reason"] = "completed_at_loop_top"
                    break
            bid = -1
            now = int(clock())
            with lock:
                while cursor < len(my_lane):
                    cand = my_lane[cursor]
                    cursor += 1
                    if ownership[cand] == 0:
                        bid = cand
                        break
                if bid < 0:
                    for lid in range(qd):
                        if lid == reader_id:
                            continue
                        s = int(lane_off[lid])
                        e = int(lane_off[lid + 1])
                        for i in range(s, e):
                            cand = int(lane_flat[i])
                            if ownership[cand] == 0:
                                bid = cand
                                payload["affinity_breaks"] += 1
                                break
                        if bid >= 0:
                            break
                if bid >= 0:
                    ownership[bid] = 1
                    start_ns[bid] = now
                    payload["claimed"] += 1
            if bid < 0:
                idle_total += (int(clock()) - now) / 1e6
                with lock:
                    if int(completed.value) >= total_blocks:
                        payload["exit_reason"] = "completed_while_idle"
                        break
                if idle_deadline is None:
                    idle_deadline = time.monotonic() + max_idle_s
                elif time.monotonic() > idle_deadline:
                    payload["exit_reason"] = "idle_timeout"
                    break
                time.sleep(0.0002)
                continue
            idle_deadline = None
            length = min(read_bytes, file_size - bid * read_bytes)
            offset = bid * read_bytes
            claim, gate_wait_ns = _alloc_gate(pacer_lock, last_start, gap_ns, clock)
            w_len = ((length + _PAGE - 1) // _PAGE) * _PAGE
            t = int(clock())
            win_addr = int(_LIBC.mmap(None, w_len, _PROT_READ, map_flags, fd, offset))
            map_ms = (int(clock()) - t) / 1e6
            if win_addr in (0, -1) or win_addr == 0xFFFFFFFFFFFFFFFF:
                with lock:
                    map_errors.value = int(map_errors.value) + 1
                    completed.value = int(completed.value) + 1
                    ownership[bid] = 2
                continue
            fresh_map_ms += map_ms
            enter = int(clock())
            err = None
            try:
                _LIBC.memcpy(dest_addr, win_addr, length)
                got = length
            except BaseException as exc:  # noqa: BLE001
                got = -1
                err = f"{type(exc).__name__}:{str(exc)[:160]}"
            exit_ns = int(clock())
            # munmap is NOT on the source path: retire and keep going.
            retire_wait_ms = _enqueue(win_addr, w_len)
            if first_enter == 0:
                first_enter = enter
            last_exit = exit_ns
            with lock:
                attempts[bid] = int(attempts[bid]) + 1
                if winner[bid] == -1:
                    winner[bid] = reader_id
                    winner_kind[bid] = 1
                    winner_exit_ns[bid] = exit_ns
                    completed.value = int(completed.value) + 1
                else:
                    payload["stale"] += 1
                ownership[bid] = 2
            payload["records"].append({
                "reader": reader_id, "pid": os.getpid(), "block_id": int(bid),
                "kind": "primary", "seq": len(payload["records"]),
                "offset": offset, "length": length, "gate_claim_ns": int(claim),
                "gate_wait_ms": gate_wait_ns / 1e6,
                "map_ms": map_ms, "unmap_ms": 0.0,
                "retire_wait_ms": retire_wait_ms,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6, "bytes_returned": got,
                "error": err, "lifecycle": "deferred_unmap",
            })
        payload["idle_no_work_ms"] = idle_total
        payload["first_enter_ns"] = first_enter
        payload["source_last_exit_ns"] = last_exit
        payload["fresh_map_ms"] = fresh_map_ms

        # ---- drain phase: wait for every deferred munmap to complete ----
        with cv:
            payload["munmaps_during_source"] = st["munmaps"]
            payload["pending_at_source_end"] = len(retired) + st["inflight"]
        with cv:
            while retired or st["inflight"]:
                cv.wait(0.001)
            st["stop"] = True
            cv.notify_all()
        if reaper is not None:
            reaper.join(timeout=30.0)
        payload["drained_ns"] = int(clock())
        payload["reaper"] = dict(st)
        payload["outstanding_after_drain"] = len(outstanding)
        payload["peak_maps_local"] = st["live_peak"]
    except BaseException as exc:  # noqa: BLE001
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        try:
            if reaper is not None and reaper.is_alive():
                with cv:
                    st["stop"] = True
                    cv.notify_all()
                reaper.join(timeout=10.0)
        except BaseException:  # noqa: BLE001
            pass
        try:
            if fd >= 0:
                os.close(fd)
        except BaseException:  # noqa: BLE001
            pass
        try:
            child_conn.send(payload)
            child_conn.close()
        except BaseException:  # noqa: BLE001
            pass


def run_deferred_unmap_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int = 4,
    max_retired: int = 2,
    sticky_lanes: bool = True,
    min_launch_gap_ns: int = 4_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    max_idle_s: float = 120.0,
    pacer_start_method: str = "fork",
) -> dict:
    """Fresh-window mmap with munmap moved OFF the source critical path.

    Geometry is identical to lifecycle="fresh" (exact window -> native memcpy),
    but each reader retires its mapping to a bounded backlog (``max_retired``)
    served by an in-process reaper thread instead of calling munmap inline.
    Reports BOTH the source-ready wall (final memcpy) and the fully-drained wall
    (every deferred munmap complete), so a source-path win that merely defers
    cleanup cannot be mistaken for a real total-work win.
    """
    import multiprocessing as mp  # noqa: PLC0415

    if _LIBC is None:
        raise RuntimeError("libc_unavailable")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if read_bytes % _PAGE:
        raise ValueError("read_bytes must be a multiple of the page size")
    if max_retired < 1:
        raise ValueError("max_retired must be >= 1")

    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {"path": file_path, "size": file_size,
                     "st_dev": getattr(stat_result, "st_dev", None),
                     "st_ino": getattr(stat_result, "st_ino", None),
                     "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)}
    total_blocks = (file_size + read_bytes - 1) // read_bytes

    def _blen(bid: int) -> int:
        return min(read_bytes, file_size - bid * read_bytes)
    expected_bytes = sum(_blen(b) for b in range(total_blocks))

    lanes: list[list[int]] = []
    if sticky_lanes:
        _base, _extra = divmod(total_blocks, qd)
        _cursor = 0
        for _lid in range(qd):
            _cnt = _base + (1 if _lid < _extra else 0)
            lanes.append(list(range(_cursor, _cursor + _cnt)))
            _cursor += _cnt
    else:
        for _lid in range(qd):
            lanes.append(list(range(_lid, total_blocks, qd)))
    lane_flat_list = [b for l in lanes for b in l]
    lane_off_list = [0]
    for l in lanes:
        lane_off_list.append(lane_off_list[-1] + len(l))

    ctx = mp.get_context(pacer_start_method)
    lock = ctx.Lock()
    ownership = ctx.Array("b", total_blocks, lock=False)
    winner = ctx.Array("i", [-1] * total_blocks, lock=False)
    winner_kind = ctx.Array("b", total_blocks, lock=False)
    start_ns = ctx.Array("q", total_blocks, lock=False)
    winner_exit_ns = ctx.Array("q", total_blocks, lock=False)
    attempts = ctx.Array("i", total_blocks, lock=False)
    completed = ctx.Value("i", 0, lock=False)
    next_global = ctx.Value("q", 0, lock=False)
    lane_flat = ctx.Array("i", lane_flat_list, lock=False)
    lane_off = ctx.Array("i", lane_off_list, lock=False)
    last_start = ctx.Value("q", 0)
    pacer_lock = last_start.get_lock()
    prep_ns = ctx.Array("q", [0] * qd, lock=False)
    live_maps = ctx.Value("i", 0, lock=False)
    map_bytes = ctx.Value("q", 0, lock=False)
    map_errors = ctx.Value("i", 0, lock=False)
    unmap_errors = ctx.Value("i", 0, lock=False)
    ready_count = ctx.Value("i", 0, lock=False)
    go = ctx.Value("i", 0, lock=False)

    procs: list[Any] = []
    conns: list[Any] = []
    for rid in range(qd):
        cp, cc = ctx.Pipe(duplex=False)
        p = cast(Any, ctx).Process(
            target=_du_child,
            args=((rid, file_path, file_size, read_bytes, lane_flat, lane_off, qd,
                   sticky_lanes, ownership, winner, winner_kind, start_ns,
                   winner_exit_ns, attempts, completed, lock, next_global,
                   last_start, pacer_lock, min_launch_gap_ns, total_blocks,
                   max_idle_s, prep_ns, live_maps, map_bytes, map_errors,
                   unmap_errors, ready_count, go, cc, max_retired),),
            daemon=True)
        p.start(); cc.close(); conns.append(cp); procs.append(p)

    barrier_error = None
    release_ns = None
    deadline = time.monotonic() + ready_timeout_s
    try:
        while int(ready_count.value) < qd:
            dead = [i for i, pr in enumerate(procs) if not pr.is_alive()]
            if dead:
                errs = []
                for i in dead:
                    try:
                        errs.append({i: conns[i].recv()})
                    except BaseException as exc:  # noqa: BLE001
                        errs.append({i: f"no_payload:{type(exc).__name__}"})
                raise RuntimeError(f"reader_died_during_setup:{dead}:{errs}")
            if time.monotonic() > deadline:
                raise TimeoutError("readers_not_ready")
            time.sleep(0.002)
        release_ns = int(clock_ns())
        go.value = 1
    except BaseException as exc:  # noqa: BLE001
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"

    payloads: list[dict[str, Any]] = []
    for rid, proc in enumerate(procs):
        proc.join(timeout=ready_timeout_s)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=30.0)
    for rid, conn in enumerate(conns):
        try:
            payloads.append(conn.recv())
        except BaseException as exc:  # noqa: BLE001
            payloads.append({"reader": rid, "status": "error",
                             "error": f"recv_failed:{type(exc).__name__}",
                             "records": []})
    for conn in conns:
        try:
            conn.close()
        except BaseException:  # noqa: BLE001
            pass

    reader_errors = [{"reader": p.get("reader"), "error": p.get("error")}
                     for p in payloads if p.get("status") != "ok"]
    records = [r for p in payloads for r in (p.get("records") or [])]
    records.sort(key=lambda r: int(r["preadv_enter_ns"]))
    stale = sum(int(p.get("stale") or 0) for p in payloads)
    affinity_breaks = sum(int(p.get("affinity_breaks") or 0) for p in payloads)
    idle_no_work_ms = [float(p.get("idle_no_work_ms") or 0.0) for p in payloads]
    prep_total_ms = sum(int(prep_ns[i]) for i in range(qd)) / 1e6
    prep_max_ms = (max(int(prep_ns[i]) for i in range(qd)) / 1e6) if qd else 0.0
    if not records:
        diag = [{"r": p.get("reader"), "st": p.get("status"),
                 "claimed": p.get("claimed"), "why": p.get("exit_reason"),
                 "lane": p.get("lane_len"), "rec": len(p.get("records") or []),
                 "err": p.get("error")} for p in payloads]
        raise RuntimeError(
            f"no_reads:{barrier_error or 'readers_failed'}:errors={reader_errors}:diag={diag}")

    durations = [r["preadv_ms"] for r in records]
    useful_bytes = sum(r["bytes_returned"] for r in records if (r["bytes_returned"] or 0) > 0)
    first_enter = min(int(r["preadv_enter_ns"]) for r in records)
    source_last_exit = max(int(p.get("source_last_exit_ns") or 0) for p in payloads)
    drained_ns = max(int(p.get("drained_ns") or 0) for p in payloads)
    wall_ms = (source_last_exit - first_enter) / 1e6
    drained_wall_ms = (drained_ns - first_enter) / 1e6

    logical: list[dict[str, Any]] = []
    reader_blocks_won = [0] * qd
    for bid in range(total_blocks):
        if winner[bid] == -1:
            continue
        exit_ns = int(winner_exit_ns[bid])
        win = next((r for r in records
                    if r["block_id"] == bid and int(r["preadv_exit_ns"]) == exit_ns), None)
        rid = int(winner[bid])
        reader_blocks_won[rid] += 1
        logical.append({
            "worker": rid, "block_id": bid, "offset": bid * read_bytes,
            "length": _blen(bid), "accepted": "primary",
            "bytes_returned": (win or {}).get("bytes_returned", 0),
            "logical_enter_ns": (win or {}).get("preadv_enter_ns", 0),
            "logical_exit_ns": exit_ns,
            "logical_ms": ((exit_ns - (win or {}).get("preadv_enter_ns", 0)) / 1e6),
        })
    logical.sort(key=lambda r: r["block_id"])
    completed_n = len(logical)

    completed_bytes = sum(r["bytes_returned"] for r in logical if (r["bytes_returned"] or 0) > 0)
    covered_bytes = sum(r["length"] for r in logical)
    ordered = sorted(logical, key=lambda r: r["offset"])
    no_overlap = all(ordered[i]["offset"] + ordered[i]["length"] <= ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    contiguous = all(ordered[i]["offset"] + ordered[i]["length"] == ordered[i + 1]["offset"]
                     for i in range(len(ordered) - 1))
    published_once = all(int(attempts[b]) >= 1 and winner[b] != -1
                         for b in range(total_blocks))

    claims = sorted(int(r["gate_claim_ns"]) for r in records)
    claim_gaps = [(claims[i] - claims[i - 1]) / 1e6 for i in range(1, len(claims))]
    ev: list[tuple[int, int]] = []
    for r in records:
        ev.append((int(r["preadv_enter_ns"]), 1))
        ev.append((int(r["preadv_exit_ns"]), -1))
    ev.sort()
    conc = 0
    observed_max = 0
    for _, dd in ev:
        conc += dd
        observed_max = max(observed_max, conc)

    # Source-path operation cost: map + memcpy (+ any retirement backpressure wait).
    def _op(r: dict) -> float:
        return (float(r.get("map_ms") or 0) + float(r.get("preadv_ms") or 0)
                + float(r.get("retire_wait_ms") or 0))

    ops = [_op(r) for r in records]

    reapers = [dict(p.get("reaper") or {}) for p in payloads]
    r_wait_ns = sum(int(x.get("wait_ns") or 0) for x in reapers)
    r_wall_ns = sum(int(x.get("wall_ns") or 0) for x in reapers)
    r_munmaps = sum(int(x.get("munmaps") or 0) for x in reapers)
    r_bp = sum(int(x.get("backpressure") or 0) for x in reapers)
    r_maxd = max((int(x.get("max_depth") or 0) for x in reapers), default=0)
    r_dsum = sum(int(x.get("depth_sum") or 0) for x in reapers)
    r_dn = sum(int(x.get("depth_samples") or 0) for x in reapers)
    r_peak = max((int(x.get("live_peak") or 0) for x in reapers), default=0)
    munmaps_during_source = sum(int(p.get("munmaps_during_source") or 0) for p in payloads)
    pending_at_source_end = sum(int(p.get("pending_at_source_end") or 0) for p in payloads)
    leaks = sum(int(p.get("outstanding_after_drain") or 0) for p in payloads)

    return {
        "schema_version": 1,
        "kind": "deferred_unmap_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "worker_model": "deferred_unmap", "lifecycle": "fresh",
            "deferred_unmap": True, "max_retired_per_reader": max_retired,
            "populate": False,
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(),
                "syscall_impl": "mmap:fresh+deferred_munmap",
                "multiprocessing_start_method": ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "worker_model": "deferred_unmap",
        "lifecycle": "fresh",
        "deferred_unmap": True,
        "max_retired_per_reader": max_retired,
        "populate": False,
        "parent_pid": os.getpid(),
        "worker_pids": sorted({int(r["pid"]) for r in records if r.get("pid") is not None}),
        "reader_pids": [p.get("pid") for p in payloads],
        "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": reader_errors,
        "physical_reads": len(logical),
        "physical_attempts": len(records),
        "physical_amplification": (len(records) / total_blocks),
        "stale_duplicates": stale,
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        # Honest total: the DRAINED wall is what the contract reports, so a run
        # cannot look faster merely because cleanup was deferred past the timer.
        "full_file_wall_ms": drained_wall_ms,
        "full_file_decimal_gbps": ((completed_bytes / (drained_wall_ms / 1000.0) / 1e9)
                                   if drained_wall_ms else None),
        "source_ready_wall_ms": wall_ms,
        "source_ready_decimal_gbps": ((completed_bytes / (wall_ms / 1000.0) / 1e9)
                                      if wall_ms else None),
        "fully_drained_wall_ms": drained_wall_ms,
        "fully_drained_decimal_gbps": ((completed_bytes / (drained_wall_ms / 1000.0) / 1e9)
                                       if drained_wall_ms else None),
        "final_drain_penalty_ms": drained_wall_ms - wall_ms,
        "min_ms": min(durations), "median_ms": percentile(durations, 50),
        "mean_ms": statistics.fmean(durations), "p95_ms": percentile(durations, 95),
        "p99_ms": percentile(durations, 99), "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 150, 250, 500, 1000, 2000)},
        "op_thresholds": {f"ge_{t}": sum(1 for d in ops if d >= t)
                          for t in (100, 150, 250, 500, 1000, 2000)},
        "coverage": {
            "expected_bytes": expected_bytes, "completed_bytes": completed_bytes,
            "file_size": file_size, "bytes_match": completed_bytes == expected_bytes == file_size,
            "blocks_expected": total_blocks, "blocks_completed": completed_n,
            "all_blocks_published_once": published_once,
            "no_overlap": no_overlap, "contiguous_cover": contiguous,
            "all_reads_returned_full_length": all(
                (r["bytes_returned"] or 0) == r["length"] for r in logical),
            "covers_entire_file_exactly_once": bool(
                completed_n == total_blocks and completed_bytes == expected_bytes == file_size
                and no_overlap and contiguous),
        },
        "scheduler": {
            "selfservice": True,
            "max_physical_qd_observed": observed_max,
            "max_physical_qd_structural": qd,
            "min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None,
            "median_global_claim_gap_ms": percentile(claim_gaps, 50) if claim_gaps else None,
            "reader_blocks_won": reader_blocks_won,
            "idle_no_work_ms": idle_no_work_ms,
            "dispatches": len(records),
            "sticky_lanes": bool(sticky_lanes),
            "lane_sizes": [len(l) for l in lanes],
            "affinity_breaks": affinity_breaks,
            "allocator_latency_median_ms": None,
        },
        "lifecycle_costs": {
            "prep_map_wall_ms_total": prep_total_ms,
            "prep_map_wall_ms_max_reader": prep_max_ms,
            "consume_wall_ms": wall_ms,
            "cleanup_unmap_wall_ms_total": 0.0,
            "cleanup_unmap_wall_ms_max_reader": 0.0,
            "first_use_inclusive_wall_ms": prep_max_ms + drained_wall_ms,
            "steady_source_wall_ms": wall_ms,
            "live_mappings": int(live_maps.value),
            "mapping_bytes": int(map_bytes.value),
            "peak_mappings_per_reader_max": r_peak,
            "map_errors": int(map_errors.value),
            "unmap_errors": int(unmap_errors.value),
            "fresh_map_ms_total": sum(float(p.get("fresh_map_ms") or 0) for p in payloads),
            "fresh_unmap_ms_total": 0.0,
        },
        "deferred_unmap_telemetry": {
            "max_retired_per_reader": max_retired,
            "reaper_queue_wait_ms_total": r_wait_ns / 1e6,
            "queue_full_events": r_bp,
            "max_queue_depth": r_maxd,
            "avg_queue_depth": (r_dsum / r_dn) if r_dn else 0.0,
            "munmap_reaper_wall_ms_total": r_wall_ns / 1e6,
            "munmap_reaper_cpu_ms_total": r_wall_ns / 1e6,
            "munmaps_completed_total": r_munmaps,
            "munmaps_completed_during_source_work": munmaps_during_source,
            "munmaps_remaining_at_source_completion": pending_at_source_end,
            "live_mapping_peak": r_peak,
            "mapping_leaks_after_drain": leaks,
            "map_errors": int(map_errors.value),
            "unmap_errors": int(unmap_errors.value),
            "source_ready_wall_ms": wall_ms,
            "fully_drained_wall_ms": drained_wall_ms,
            "final_drain_penalty_ms": drained_wall_ms - wall_ms,
        },
        "pacer": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                  "observed_min_global_claim_gap_ms": min(claim_gaps) if claim_gaps else None},
        "launch_spacing": {"configured_min_gap_ms": min_launch_gap_ns / 1e6,
                           "mean_effective_concurrency": None,
                           "max_simultaneous_in_flight": observed_max},
        "reader_diagnostics": [
            {"reader": p.get("reader"), "status": p.get("status"),
             "claimed": p.get("claimed"), "exit_reason": p.get("exit_reason"),
             "lane_len": p.get("lane_len"), "records": len(p.get("records") or []),
             "munmaps": int((p.get("reaper") or {}).get("munmaps") or 0),
             "outstanding_after_drain": int(p.get("outstanding_after_drain") or 0),
             "error": p.get("error")}
            for p in payloads],
        "logical_reads": logical,
        "reads": logical,
        "physical_attempts_log": records,
        "allocator_dispatches": [],
        "rescue_events": [],
    }


def run_startup_arm_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int,
    arm: str,
    stagger_ms: int = 250,
    primer_bytes: int | None = None,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
) -> dict:
    """One full-region pass with an arm-specific startup discipline.

    arm="control"   all workers release together into the measured region
                    (existing behaviour: first-touch and max concurrency coincide).
    arm="staggered" worker i's FIRST read begins at i*stagger_ms; rolling after.
    arm="primed"    each worker performs one untimed primer read from its own
                    private region, then all release together into the measured
                    region (first measured read is post-primer).

    Architecture is otherwise unchanged: one persistent FD and one reusable
    buffer per worker, contiguous non-overlapping partitions, immediate refill,
    and nothing inside the timed interval except ``os.preadv``.
    """
    clock_ns = clock_ns or time.perf_counter_ns
    preadv_fn = getattr(os, "preadv", None)
    if not callable(preadv_fn):
        raise RuntimeError("os.preadv unavailable")
    preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)

    if arm not in {"control", "staggered", "primed", "global_primed"}:
        raise ValueError("arm must be control, staggered, or primed")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")

    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path,
        "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    total_blocks = (file_size + read_bytes - 1) // read_bytes
    if arm == "primed":
        # Each worker gets ONE primer of ``primer_bytes`` (default read_bytes).
        # Primers occupy the tail of the file, so no measured extent is ever a
        # primer extent.
        pbytes = int(primer_bytes) if primer_bytes else read_bytes
        primer_total = qd * pbytes
        if primer_total >= file_size:
            raise ValueError("primer region exceeds file size")
        measured_end = file_size - primer_total
        measured_blocks = list(range(0, (measured_end + read_bytes - 1) // read_bytes))
        primer_offsets = [(measured_end + i * pbytes, pbytes) for i in range(qd)]
    elif arm == "global_primed":
        # Exactly ONE primer block, performed by worker 0 only.
        pbytes = int(primer_bytes) if primer_bytes else read_bytes
        if pbytes >= file_size:
            raise ValueError("primer region exceeds file size")
        measured_end = file_size - pbytes
        measured_blocks = list(range(0, (measured_end + read_bytes - 1) // read_bytes))
        primer_offsets = [(measured_end, pbytes)]
    else:
        primer_offsets = []
        measured_blocks = list(range(0, total_blocks))
    if len(measured_blocks) < qd:
        raise ValueError("measured region too small for qd workers")

    base, extra = divmod(len(measured_blocks), qd)
    assignments: list[tuple[int, int, int, tuple[int, int] | None]] = []
    cursor = 0
    for worker_id in range(qd):
        count = base + (1 if worker_id < extra else 0)
        if arm == "primed":
            primer = primer_offsets[worker_id]
        elif arm == "global_primed":
            primer = primer_offsets[0] if worker_id == 0 else None
        else:
            primer = None
        assignments.append((worker_id, cursor, count, primer))
        cursor += count

    buffers = [bytearray(read_bytes) for _ in range(qd)]
    views = [memoryview(buffer) for buffer in buffers]
    records: list[list[dict[str, Any]]] = [[] for _ in range(qd)]
    primer_results: dict[int, dict[str, Any]] = {}
    fds = [os.open(file_path, os.O_RDONLY) for _ in range(qd)]
    release_barrier = threading.Barrier(qd)
    stagger_ns = int(stagger_ms) * 1_000_000
    t0 = int(clock_ns())

    def _worker(worker_id: int, start_idx: int, count: int, primer: tuple[int, int] | None) -> None:
        fd = fds[worker_id]
        view = views[worker_id]
        if primer is not None:
            offset, length = primer
            target = view if length >= read_bytes else view[:length]
            enter = int(clock_ns())
            try:
                got = int(preadv(fd, [target], offset))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            primer_results[worker_id] = {
                "worker": worker_id, "offset": offset, "length": length,
                "bytes_returned": got, "preadv_ms": (exit_ns - enter) / 1e6,
                "enter_ns": enter, "exit_ns": exit_ns,
            }
        if arm == "staggered":
            target_ns = t0 + worker_id * stagger_ns
            while True:
                now = int(clock_ns())
                if now >= target_ns:
                    break
                time.sleep(min(0.05, (target_ns - now) / 1e9))
        else:
            release_barrier.wait()
        previous_exit: int | None = None
        prior = 1 if primer is not None else 0
        for step in range(count):
            block_index = measured_blocks[start_idx + step]
            offset = block_index * read_bytes
            length = min(read_bytes, file_size - offset)
            target = view if length == read_bytes else view[:length]
            enter = int(clock_ns())
            try:
                got = int(preadv(fd, [target], offset))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            records[worker_id].append({
                "worker": worker_id, "gen": step, "prior_reads": prior,
                "block_index": block_index, "offset": offset, "length": length,
                "bytes_returned": got,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6,
                "refill_gap_ms": (
                    None if previous_exit is None else (enter - previous_exit) / 1e6
                ),
                "is_primer": False,
            })
            previous_exit = exit_ns

    threads = [
        threading.Thread(target=_worker, args=assignment) for assignment in assignments
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for fd in fds:
        os.close(fd)

    flat = [record for group in records for record in group]
    durations = [record["preadv_ms"] for record in flat]
    useful_bytes = sum(r["bytes_returned"] for r in flat if r["bytes_returned"] > 0)
    covered_bytes = sum(r["length"] for r in flat)
    first_enter = min(r["preadv_enter_ns"] for r in flat)
    last_exit = max(r["preadv_exit_ns"] for r in flat)
    wall_ms = (last_exit - first_enter) / 1e6
    wall_seconds = wall_ms / 1000.0
    gaps = [r["refill_gap_ms"] for r in flat if r["refill_gap_ms"] is not None]

    events: list[tuple[int, int]] = []
    for r in flat:
        events.append((r["preadv_enter_ns"], 1))
        events.append((r["preadv_exit_ns"], -1))
    events.sort()
    worker_first = [min(r["preadv_enter_ns"] for r in g) for g in records if g]
    worker_last = [max(r["preadv_exit_ns"] for r in g) for g in records if g]
    span_start = max(worker_first) if worker_first else None
    span_end = min(worker_last) if worker_last else None
    concurrent = 0
    max_in_span: int | None = None
    min_in_span: int | None = None
    if span_start is not None and span_end is not None and span_end > span_start:
        for ts, delta in events:
            concurrent += delta
            if span_start <= ts <= span_end:
                max_in_span = concurrent if max_in_span is None else max(max_in_span, concurrent)
                min_in_span = concurrent if min_in_span is None else min(min_in_span, concurrent)

    return {
        "schema_version": 1,
        "kind": "startup_arm_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd, "arm": arm,
            "stagger_ms": stagger_ms if arm == "staggered" else 0,
            "total_blocks": total_blocks,
            "measured_blocks": len(measured_blocks),
            "primer_offsets": primer_offsets,
            "primer_bytes": primer_bytes,
        },
        "env": {
            "platform": platform.system(), "syscall_impl": "os.preadv",
            "preadv_available": callable(getattr(os, "preadv", None)),
        },
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "physical_reads": len(flat),
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "measured_wall_ms": wall_ms,
        "measured_decimal_gbps": (useful_bytes / wall_seconds / 1e9) if wall_seconds else None,
        "mean_ms": statistics.fmean(durations),
        "median_ms": percentile(durations, 50),
        "p90_ms": percentile(durations, 90),
        "p95_ms": percentile(durations, 95),
        "max_ms": max(durations),
        "min_ms": min(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 250, 500, 1000, 2000, 5000)},
        "median_refill_gap_ms": percentile(gaps, 50) if gaps else None,
        "max_refill_gap_ms": max(gaps) if gaps else None,
        "effective_qd_min_in_span": min_in_span,
        "effective_qd_max_in_span": max_in_span,
        "first_read_enter_rel_ms_by_worker": {
            w: (min(r["preadv_enter_ns"] for r in g) - first_enter) / 1e6
            for w, g in enumerate(records) if g
        },
        "worker_partitions": [
            {"worker": w, "first_measured_index": s, "blocks": c, "primer": p}
            for w, s, c, p in assignments
        ],
        "primer_results": primer_results,
        "primer_useful_bytes": sum(
            v["bytes_returned"] for v in primer_results.values() if v["bytes_returned"] > 0
        ),
        "reads": flat,
    }


def run_primer_mechanism_probe(
    *,
    file_path: str,
    arm: str,
    read_bytes: int = 64 * 1024 * 1024,
    qd: int = 4,
    wait_target_ms: float = 135.0,
    primer_size_override: int | None = None,
    primer_count_override: int | None = None,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
) -> dict:
    """One measured pass after an arm-specific per-worker primer treatment.

    Arms (per worker):
      A  1 x 16 MiB primer
      B  4 sequential x 16 MiB primers  (64 MiB total, no 64 MiB syscall)
      C  16 sequential x 4 MiB primers  (64 MiB total)
      D  1 x 16 MiB primer + passive wait to a target pre-measured elapsed time
      E  1 x 64 MiB primer

    A common primer region of ``qd * read_bytes`` is reserved at the tail of the
    file for EVERY arm, so the measured region is byte-identical across arms.
    Measured architecture is unchanged: one persistent FD and one reusable
    buffer per worker, contiguous partitions, simultaneous release, rolling
    refill, and nothing inside the timed interval except ``os.preadv``.
    """
    clock_ns = clock_ns or time.perf_counter_ns
    preadv_fn = getattr(os, "preadv", None)
    if not callable(preadv_fn):
        raise RuntimeError("os.preadv unavailable")
    preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)

    mib = 1024 * 1024
    arm_specs = {"A": (16 * mib, 1), "B": (16 * mib, 4), "C": (4 * mib, 16),
                 "D": (16 * mib, 1), "E": (64 * mib, 1)}
    if arm not in arm_specs:
        raise ValueError("arm must be A, B, C, D, or E")
    primer_size, primer_count = arm_specs[arm]
    if primer_size_override:
        primer_size = int(primer_size_override)
    if primer_count_override:
        primer_count = int(primer_count_override)
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")

    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path, "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    allotment = read_bytes                      # per-worker primer allotment
    primer_region = qd * allotment
    if primer_region >= file_size:
        raise ValueError("primer region exceeds file size")
    if primer_size * primer_count > allotment:
        raise ValueError("primer sequence exceeds per-worker allotment")
    measured_end = file_size - primer_region
    measured_blocks = list(range(0, (measured_end + read_bytes - 1) // read_bytes))
    allotment_starts = [measured_end + i * allotment for i in range(qd)]
    if len(measured_blocks) < qd:
        raise ValueError("measured region too small for qd workers")

    base, extra = divmod(len(measured_blocks), qd)
    assignments = []
    cursor = 0
    for worker_id in range(qd):
        count = base + (1 if worker_id < extra else 0)
        assignments.append((worker_id, cursor, count, allotment_starts[worker_id]))
        cursor += count

    buffers = [bytearray(read_bytes) for _ in range(qd)]
    views = [memoryview(buffer) for buffer in buffers]
    records: list[list[dict[str, Any]]] = [[] for _ in range(qd)]
    primer_records: list[list[dict[str, Any]]] = [[] for _ in range(qd)]
    fds = [os.open(file_path, os.O_RDONLY) for _ in range(qd)]
    release_barrier = threading.Barrier(qd)
    first_enters: list[int] = []
    first_enter_lock = threading.Lock()
    wait_target_ns = int(wait_target_ms * 1_000_000)

    def _worker(worker_id: int, start_idx: int, count: int, allotment_start: int) -> None:
        fd = fds[worker_id]
        view = views[worker_id]
        for ordinal in range(primer_count):
            offset = allotment_start + ordinal * primer_size
            target = view if primer_size >= read_bytes else view[:primer_size]
            enter = int(clock_ns())
            if ordinal == 0:
                with first_enter_lock:
                    first_enters.append(enter)
            try:
                got = int(preadv(fd, [target], offset))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            primer_records[worker_id].append({
                "worker": worker_id, "ordinal": ordinal, "size": primer_size,
                "offset": offset, "bytes_returned": got,
                "enter_ns": enter, "exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6,
            })
        if arm == "D":
            with first_enter_lock:
                phase_start = min(first_enters) if first_enters else int(clock_ns())
            deadline = phase_start + wait_target_ns
            while int(clock_ns()) < deadline:
                time.sleep(0.001)
        release_barrier.wait()
        previous_exit: int | None = None
        for step in range(count):
            block_index = measured_blocks[start_idx + step]
            offset = block_index * read_bytes
            length = min(read_bytes, file_size - offset)
            target = view if length == read_bytes else view[:length]
            enter = int(clock_ns())
            try:
                got = int(preadv(fd, [target], offset))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            records[worker_id].append({
                "worker": worker_id, "gen": step, "block_index": block_index,
                "offset": offset, "length": length, "bytes_returned": got,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6,
                "refill_gap_ms": (
                    None if previous_exit is None else (enter - previous_exit) / 1e6
                ),
            })
            previous_exit = exit_ns

    threads = [threading.Thread(target=_worker, args=a) for a in assignments]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for fd in fds:
        os.close(fd)

    flat = [r for group in records for r in group]
    primers = [p for group in primer_records for p in group]
    durations = [r["preadv_ms"] for r in flat]
    useful_bytes = sum(r["bytes_returned"] for r in flat if r["bytes_returned"] > 0)
    covered_bytes = sum(r["length"] for r in flat)
    measured_start = min(r["preadv_enter_ns"] for r in flat)
    last_exit = max(r["preadv_exit_ns"] for r in flat)
    measured_wall_ms = (last_exit - measured_start) / 1e6

    primer_enter = min(p["enter_ns"] for p in primers)
    primer_exit = max(p["exit_ns"] for p in primers)
    primer_io_wall_ms = (primer_exit - primer_enter) / 1e6
    artificial_wait_ms = max(0.0, (measured_start - primer_exit) / 1e6)
    pretreatment_wall_ms = (measured_start - primer_enter) / 1e6
    total_source_wall_ms = pretreatment_wall_ms + measured_wall_ms
    measured_seconds = measured_wall_ms / 1000.0
    total_seconds = total_source_wall_ms / 1000.0

    gaps = [r["refill_gap_ms"] for r in flat if r["refill_gap_ms"] is not None]
    primer_ms = [p["preadv_ms"] for p in primers]

    events: list[tuple[int, int]] = []
    for r in flat:
        events.append((r["preadv_enter_ns"], 1))
        events.append((r["preadv_exit_ns"], -1))
    events.sort()
    worker_first = [min(r["preadv_enter_ns"] for r in g) for g in records if g]
    worker_last = [max(r["preadv_exit_ns"] for r in g) for g in records if g]
    span_start = max(worker_first) if worker_first else None
    span_end = min(worker_last) if worker_last else None
    concurrent = 0
    max_in_span: int | None = None
    min_in_span: int | None = None
    if span_start is not None and span_end is not None and span_end > span_start:
        for ts, delta in events:
            concurrent += delta
            if span_start <= ts <= span_end:
                max_in_span = concurrent if max_in_span is None else max(max_in_span, concurrent)
                min_in_span = concurrent if min_in_span is None else min(min_in_span, concurrent)

    # cumulative-bytes analysis for the multi-syscall arms
    cumulative = []
    for group in primer_records:
        done = 0
        for p in group:
            cumulative.append({"cumulative_before": done, "preadv_ms": p["preadv_ms"],
                               "ordinal": p["ordinal"], "worker": p["worker"]})
            done += p["size"]

    return {
        "schema_version": 1,
        "kind": "primer_mechanism_probe",
        "config": {
            "file_path": file_path, "arm": arm,
            "read_bytes": read_bytes, "read_mib": read_bytes / mib, "qd": qd,
            "primer_size": primer_size, "primer_count": primer_count,
            "primer_size_mib": primer_size / mib,
            "wait_target_ms": wait_target_ms if arm == "D" else 0.0,
            "measured_blocks": len(measured_blocks),
            "measured_end": measured_end,
            "primer_region_bytes": primer_region,
            "allotment_starts": allotment_starts,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv",
                "preadv_available": callable(getattr(os, "preadv", None))},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "primer_syscalls": len(primers),
        "primer_bytes": sum(p["size"] for p in primers),
        "primer_io_wall_ms": primer_io_wall_ms,
        "artificial_wait_ms": artificial_wait_ms,
        "pretreatment_wall_ms": pretreatment_wall_ms,
        "measured_wall_ms": measured_wall_ms,
        "total_source_wall_ms": total_source_wall_ms,
        "physical_reads": len(flat),
        "useful_bytes": useful_bytes,
        "covered_bytes": covered_bytes,
        "measured_decimal_gbps": (useful_bytes / measured_seconds / 1e9) if measured_seconds else None,
        "effective_total_gbps": (useful_bytes / total_seconds / 1e9) if total_seconds else None,
        "mean_ms": statistics.fmean(durations),
        "median_ms": percentile(durations, 50),
        "p95_ms": percentile(durations, 95),
        "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 250, 500, 1000)},
        "median_refill_gap_ms": percentile(gaps, 50) if gaps else None,
        "max_refill_gap_ms": max(gaps) if gaps else None,
        "effective_qd_min_in_span": min_in_span,
        "effective_qd_max_in_span": max_in_span,
        "primer_median_ms": percentile(primer_ms, 50) if primer_ms else None,
        "primer_max_ms": max(primer_ms) if primer_ms else None,
        "primer_thresholds": {f"ge_{t}": sum(1 for d in primer_ms if d >= t)
                              for t in (100, 250, 500, 1000)},
        "primer_cumulative": cumulative,
        "primer_records": primers,
        "reads": flat,
    }


_RECORDER_THRESHOLDS_MS = (250, 500, 1000, 2000, 5000)


def _read_text(path: str, limit: int = 4096) -> str:
    try:
        with open(path, "r") as handle:
            return handle.read(limit).strip()
    except Exception as exc:  # noqa: BLE001
        return f"<unavailable:{type(exc).__name__}>"


def _proc_state(tid: int) -> str:
    raw = _read_text(f"/proc/self/task/{tid}/stat", 2048)
    if raw.startswith("<unavailable"):
        return raw
    try:
        return raw[raw.rfind(")") + 2:].split()[0]
    except Exception:
        return "<parse_error>"


def _ctxt_switches(tid: int) -> dict:
    raw = _read_text(f"/proc/self/task/{tid}/status", 8192)
    out = {}
    for line in raw.splitlines():
        if line.startswith(("voluntary_ctxt_switches", "nonvoluntary_ctxt_switches")):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def _psi(path: str) -> str:
    return _read_text(path, 512)


def run_flight_recorder_probe(
    *,
    file_path: str,
    read_bytes: int = 64 * 1024 * 1024,
    qd: int = 4,
    sample_ms: int = 15,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
) -> dict:
    """Pure rolling source probe + minimally invasive Linux flight recorder.

    Same measured architecture as the full-file probe (no primer): one
    persistent FD and one reusable buffer per worker, contiguous partitions,
    simultaneous release, rolling refill, timer exactly enter->preadv->exit.

    A single monitor thread samples Linux/container state every ``sample_ms``
    into an in-memory ring buffer, and captures richer snapshots only when an
    outstanding preadv crosses 250/500/1000/2000/5000 ms and immediately after
    it returns.  No locks or bookkeeping sit inside the timed interval.
    """
    clock_ns = clock_ns or time.perf_counter_ns
    preadv_fn = getattr(os, "preadv", None)
    if not callable(preadv_fn):
        raise RuntimeError("os.preadv unavailable")
    preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")

    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path, "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    recorder_on = bool(sample_ms and int(sample_ms) > 0)
    total_blocks = (file_size + read_bytes - 1) // read_bytes
    measured_blocks = list(range(0, total_blocks))
    base, extra = divmod(len(measured_blocks), qd)
    assignments = []
    cursor = 0
    for worker_id in range(qd):
        count = base + (1 if worker_id < extra else 0)
        assignments.append((worker_id, cursor, count))
        cursor += count

    # ---- capability probe + static identity ----
    caps = {}
    for name, path in (
        ("task_stat", "/proc/self/task/1/stat"),
        ("task_wchan", "/proc/self/task/1/wchan"),
        ("task_schedstat", "/proc/self/task/1/schedstat"),
        ("task_status", "/proc/self/task/1/status"),
        ("task_syscall", "/proc/self/task/1/syscall"),
        ("task_stack", "/proc/self/task/1/stack"),
        ("psi_io", "/proc/pressure/io"),
        ("psi_cpu", "/proc/pressure/cpu"),
        ("psi_memory", "/proc/pressure/memory"),
        ("proc_io", "/proc/self/io"),
        ("cgroup_io_stat", "/sys/fs/cgroup/io.stat"),
        ("cgroup_io_pressure", "/sys/fs/cgroup/io.pressure"),
        ("cgroup_memory_stat", "/sys/fs/cgroup/memory.stat"),
        ("cgroup_memory_events", "/sys/fs/cgroup/memory.events"),
        ("cgroup_cpu_pressure", "/sys/fs/cgroup/cpu.pressure"),
        ("mountinfo", "/proc/self/mountinfo"),
        ("cgroup_path", "/proc/self/cgroup"),
    ):
        caps[name] = not _read_text(path, 256).startswith("<unavailable")
    static_identity = {
        "capabilities": caps,
        "kernel": platform.release(),
        "cgroup": _read_text("/proc/self/cgroup", 512),
        "mountinfo_model_line": [
            line for line in _read_text("/proc/self/mountinfo", 200000).splitlines()
            if "/root/models" in line
        ][:3],
        "psi_io_initial": _psi("/proc/pressure/io"),
        "psi_cpu_initial": _psi("/proc/pressure/cpu"),
        "cgroup_io_stat_initial": _read_text("/sys/fs/cgroup/io.stat", 2048),
        "proc_io_initial": _read_text("/proc/self/io", 1024),
    }

    buffers = [bytearray(read_bytes) for _ in range(qd)]
    views = [memoryview(buffer) for buffer in buffers]
    records: list[list[dict[str, Any]]] = [[] for _ in range(qd)]
    fds = [os.open(file_path, os.O_RDONLY) for _ in range(qd)]
    release_barrier = threading.Barrier(qd)

    tids: dict[int, int] = {}
    outstanding: dict[int, dict[str, Any]] = {}
    monitor_lock = threading.Lock()
    samples: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    max_samples = 6000
    stop_monitor = threading.Event()

    def _worker_snapshot() -> dict[str, Any]:
        out: dict[str, Any] = {}
        for worker_id, tid in list(tids.items()):
            out[str(worker_id)] = {
                "tid": tid,
                "state": _proc_state(tid),
                "wchan": _read_text(f"/proc/self/task/{tid}/wchan", 128),
                "syscall": _read_text(f"/proc/self/task/{tid}/syscall", 256),
                "schedstat": _read_text(f"/proc/self/task/{tid}/schedstat", 256),
                "ctxt": _ctxt_switches(tid),
            }
        return out

    def _shared_state() -> dict[str, Any]:
        return {
            "psi_io": _psi("/proc/pressure/io"),
            "psi_cpu": _psi("/proc/pressure/cpu"),
            "psi_memory": _psi("/proc/pressure/memory"),
            "proc_io": _read_text("/proc/self/io", 1024),
            "cgroup_io_pressure": _read_text("/sys/fs/cgroup/io.pressure", 1024),
            "cgroup_io_stat": _read_text("/sys/fs/cgroup/io.stat", 2048),
            "cgroup_memory_events": _read_text("/sys/fs/cgroup/memory.events", 1024),
        }

    def _stacks() -> dict[str, str]:
        if not caps.get("task_stack"):
            return {}
        return {
            str(worker_id): _read_text(f"/proc/self/task/{tid}/stack", 1200)
            for worker_id, tid in list(tids.items())
        }

    def _monitor() -> None:
        while not stop_monitor.is_set():
            now = int(clock_ns())
            sample = {"t_ns": now, "workers": _worker_snapshot()}
            sample.update(_shared_state())
            with monitor_lock:
                samples.append(sample)
                if len(samples) > max_samples:
                    samples.pop(0)
                for worker_id, info in list(outstanding.items()):
                    elapsed_ms = (now - info["enter_ns"]) / 1e6
                    for threshold in _RECORDER_THRESHOLDS_MS:
                        if elapsed_ms >= threshold and threshold not in info["fired"]:
                            info["fired"].add(threshold)
                            snapshots.append({
                                "kind": "threshold",
                                "threshold_ms": threshold,
                                "worker": worker_id,
                                "elapsed_ms": elapsed_ms,
                                "offset": info["offset"],
                                "t_ns": now,
                                "workers": _worker_snapshot(),
                                "shared": _shared_state(),
                                "stacks": _stacks(),
                            })
            stop_monitor.wait(sample_ms / 1000.0)

    def _worker(worker_id: int, start_idx: int, count: int) -> None:
        tids[worker_id] = threading.get_native_id()
        fd = fds[worker_id]
        view = views[worker_id]
        release_barrier.wait()
        previous_exit: int | None = None
        for step in range(count):
            block_index = measured_blocks[start_idx + step]
            offset = block_index * read_bytes
            length = min(read_bytes, file_size - offset)
            target = view if length == read_bytes else view[:length]
            if recorder_on:
                outstanding[worker_id] = {
                    "enter_ns": int(clock_ns()), "offset": offset,
                    "length": length, "fired": set(),
                }
                enter = outstanding[worker_id]["enter_ns"]
            else:
                enter = int(clock_ns())
            try:
                got = int(preadv(fd, [target], offset))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            info = outstanding.pop(worker_id, None) if recorder_on else None
            fired = sorted(info["fired"]) if info else []
            if fired:
                snapshots.append({
                    "kind": "post_completion",
                    "worker": worker_id,
                    "offset": offset,
                    "preadv_ms": (exit_ns - enter) / 1e6,
                    "fired_thresholds": fired,
                    "t_ns": exit_ns,
                    "workers": _worker_snapshot(),
                    "shared": _shared_state(),
                    "stacks": _stacks(),
                })
            records[worker_id].append({
                "worker": worker_id, "gen": step, "block_index": block_index,
                "offset": offset, "length": length, "bytes_returned": got,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6,
                "fired_thresholds": fired,
                "refill_gap_ms": (
                    None if previous_exit is None else (enter - previous_exit) / 1e6
                ),
            })
            previous_exit = exit_ns

    monitor_thread = None
    if recorder_on:
        monitor_thread = threading.Thread(target=_monitor, daemon=True)
        monitor_thread.start()
    threads = [threading.Thread(target=_worker, args=a) for a in assignments]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    stop_monitor.set()
    if monitor_thread is not None:
        monitor_thread.join(timeout=2.0)
    for fd in fds:
        os.close(fd)

    flat = [r for group in records for r in group]
    durations = [r["preadv_ms"] for r in flat]
    useful_bytes = sum(r["bytes_returned"] for r in flat if r["bytes_returned"] > 0)
    first_enter = min(r["preadv_enter_ns"] for r in flat)
    last_exit = max(r["preadv_exit_ns"] for r in flat)
    wall_ms = (last_exit - first_enter) / 1e6
    gaps = [r["refill_gap_ms"] for r in flat if r["refill_gap_ms"] is not None]
    slow = [r for r in flat if r["preadv_ms"] >= 250]

    return {
        "schema_version": 1,
        "kind": "flight_recorder_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "sample_ms": sample_ms, "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv",
                "preadv_available": callable(getattr(os, "preadv", None))},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "static_identity": static_identity,
        "physical_reads": len(flat),
        "useful_bytes": useful_bytes,
        "wall_ms": wall_ms,
        "decimal_gbps": (useful_bytes / (wall_ms / 1000.0) / 1e9) if wall_ms else None,
        "mean_ms": statistics.fmean(durations),
        "median_ms": percentile(durations, 50),
        "p95_ms": percentile(durations, 95),
        "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 250, 500, 1000)},
        "median_refill_gap_ms": percentile(gaps, 50) if gaps else None,
        "max_refill_gap_ms": max(gaps) if gaps else None,
        "slow_read_count": len(slow),
        "sample_count": len(samples),
        "snapshot_count": len(snapshots),
        "samples": samples,
        "snapshots": snapshots,
        "reads": flat,
    }


def run_cross_source_probe(
    *,
    file_path: str,
    alternate_file_path: str | None = None,
    read_bytes: int = 64 * 1024 * 1024,
    qd: int = 4,
    probe_bytes: int = 4 * 1024 * 1024,
    trigger_ms: int = 250,
    clean_probe_at_ms: int = 0,
    local_file_bytes: int = 16 * 1024 * 1024,
    heartbeat_ms: int = 5,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
) -> dict:
    """Pure rolling source probe + triggered cross-source localization probes.

    Normal workload is unchanged (64 MiB reads, QD, no primer).  When any normal
    ``os.preadv`` stays outstanding past ``trigger_ms``, ONE diagnostic probe set
    fires (per episode) on its own threads/FDs/buffers:

      A  fresh FD, same model file, 4 MiB, non-overlapping range
      B  fresh FD, same model file, SAME range as a currently blocked request
      C  fresh FD, different file on the same model Volume, 4 MiB
      D  fresh FD, local container/tmpfs file, 4 MiB
      E  userspace heartbeat thread (periodic monotonic counter)

    Diagnostic bytes are never counted as measured model bytes.  All timestamps
    use the same monotonic clock as normal read telemetry.
    """
    clock_ns = clock_ns or time.perf_counter_ns
    preadv_fn = getattr(os, "preadv", None)
    if not callable(preadv_fn):
        raise RuntimeError("os.preadv unavailable")
    preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")

    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path, "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    alternate_identity = None
    if alternate_file_path and os.path.isfile(alternate_file_path):
        alt_stat = os.stat(alternate_file_path)
        alternate_identity = {
            "path": alternate_file_path, "size": int(alt_stat.st_size),
            "st_dev": getattr(alt_stat, "st_dev", None),
            "st_ino": getattr(alt_stat, "st_ino", None),
        }
    else:
        alternate_file_path = None

    local_path = os.path.join(tempfile.gettempdir(), "c0_local_probe.bin")
    with open(local_path, "wb") as handle:
        handle.write(b"\x5a" * int(local_file_bytes))
    local_stat = os.stat(local_path)
    local_identity = {
        "path": local_path, "size": int(local_stat.st_size),
        "st_dev": getattr(local_stat, "st_dev", None),
        "st_ino": getattr(local_stat, "st_ino", None),
        "tmpdir": tempfile.gettempdir(),
    }

    total_blocks = (file_size + read_bytes - 1) // read_bytes
    measured_blocks = list(range(0, total_blocks))
    base, extra = divmod(len(measured_blocks), qd)
    assignments = []
    cursor = 0
    for worker_id in range(qd):
        count = base + (1 if worker_id < extra else 0)
        assignments.append((worker_id, cursor, count))
        cursor += count

    buffers = [bytearray(read_bytes) for _ in range(qd)]
    views = [memoryview(buffer) for buffer in buffers]
    records: list[list[dict[str, Any]]] = [[] for _ in range(qd)]
    fds = [os.open(file_path, os.O_RDONLY) for _ in range(qd)]
    release_barrier = threading.Barrier(qd)

    outstanding: dict[int, dict[str, Any]] = {}
    lock = threading.Lock()
    probe_sets: list[dict[str, Any]] = []
    heartbeat: list[tuple[int, int]] = []
    stop = threading.Event()
    run_start_ns = int(clock_ns())

    def _run_probe_set(trigger_ns: int, blocked_snapshot: dict[str, Any], kind: str) -> None:
        results: dict[str, Any] = {}
        results_lock = threading.Lock()

        def _probe(name: str, path: str, offset: int, length: int) -> None:
            try:
                fd = os.open(path, os.O_RDONLY)
            except Exception as exc:  # noqa: BLE001
                with results_lock:
                    results[name] = {"name": name, "status": "open_error",
                                     "error": f"{type(exc).__name__}:{exc}"[:200]}
                return
            buf = bytearray(length)
            view = memoryview(buf)
            enter = int(clock_ns())
            try:
                got = int(preadv(fd, [view], offset))
            except BaseException as exc:  # noqa: BLE001
                got = -1
            exit_ns = int(clock_ns())
            try:
                os.close(fd)
            except Exception:
                pass
            with results_lock:
                results[name] = {
                    "name": name, "path": path, "offset": offset, "length": length,
                    "bytes_returned": got, "enter_ns": enter, "exit_ns": exit_ns,
                    "latency_ms": (exit_ns - enter) / 1e6,
                    "status": "ok" if got == length else "short",
                }

        specs: list[tuple[str, str, int, int]] = []
        # A: fresh FD, same file, non-overlapping range
        if file_size >= probe_bytes:
            specs.append(("A_same_file_fresh_fd", file_path,
                          max(0, file_size - probe_bytes), probe_bytes))
        # B: fresh FD, same file, same range as a blocked request
        if blocked_snapshot:
            first = next(iter(blocked_snapshot.values()))
            specs.append(("B_same_range_fresh_fd", file_path,
                          int(first["offset"]), min(probe_bytes, int(first["length"]))))
        # C: different file on the same Volume
        if alternate_file_path:
            specs.append(("C_other_volume_file", alternate_file_path, 0, probe_bytes))
        # D: local container/tmpfs file
        specs.append(("D_local_file", local_path, 0, probe_bytes))

        threads = [threading.Thread(target=_probe, args=spec) for spec in specs]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        with lock:
            probe_sets.append({
                "kind": kind,
                "trigger_ns": trigger_ns,
                "blocked": blocked_snapshot,
                "results": results,
            })

    def _heartbeat() -> None:
        counter = 0
        while not stop.is_set():
            heartbeat.append((int(clock_ns()), counter))
            counter += 1
            stop.wait(heartbeat_ms / 1000.0)

    def _monitor() -> None:
        armed = True
        clean_fired = False
        while not stop.is_set():
            now = int(clock_ns())
            with lock:
                snapshot = {
                    str(w): {"offset": info["offset"], "length": info["length"],
                             "elapsed_ms": (now - info["enter_ns"]) / 1e6}
                    for w, info in outstanding.items()
                }
            if armed and snapshot:
                if any(v["elapsed_ms"] >= trigger_ms for v in snapshot.values()):
                    armed = False
                    threading.Thread(target=_run_probe_set,
                                     args=(now, snapshot, "pathological"),
                                     daemon=True).start()
            elif not snapshot:
                armed = True
            if (clean_probe_at_ms and not clean_fired
                    and (now - run_start_ns) / 1e6 >= clean_probe_at_ms and not snapshot):
                clean_fired = True
                threading.Thread(target=_run_probe_set,
                                 args=(now, {}, "clean_reference"), daemon=True).start()
            stop.wait(0.010)

    def _worker(worker_id: int, start_idx: int, count: int) -> None:
        fd = fds[worker_id]
        view = views[worker_id]
        release_barrier.wait()
        previous_exit: int | None = None
        for step in range(count):
            block_index = measured_blocks[start_idx + step]
            offset = block_index * read_bytes
            length = min(read_bytes, file_size - offset)
            target = view if length == read_bytes else view[:length]
            with lock:
                outstanding[worker_id] = {
                    "enter_ns": int(clock_ns()), "offset": offset, "length": length,
                }
                enter = outstanding[worker_id]["enter_ns"]
            try:
                got = int(preadv(fd, [target], offset))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            with lock:
                outstanding.pop(worker_id, None)
            records[worker_id].append({
                "worker": worker_id, "gen": step, "block_index": block_index,
                "offset": offset, "length": length, "bytes_returned": got,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6,
                "refill_gap_ms": (
                    None if previous_exit is None else (enter - previous_exit) / 1e6
                ),
            })
            previous_exit = exit_ns

    hb_thread = threading.Thread(target=_heartbeat, daemon=True)
    hb_thread.start()
    mon_thread = threading.Thread(target=_monitor, daemon=True)
    mon_thread.start()
    threads = [threading.Thread(target=_worker, args=a) for a in assignments]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    time.sleep(0.05)
    stop.set()
    hb_thread.join(timeout=1.0)
    mon_thread.join(timeout=1.0)
    for fd in fds:
        os.close(fd)

    flat = [r for group in records for r in group]
    durations = [r["preadv_ms"] for r in flat]
    useful_bytes = sum(r["bytes_returned"] for r in flat if r["bytes_returned"] > 0)
    first_enter = min(r["preadv_enter_ns"] for r in flat)
    last_exit = max(r["preadv_exit_ns"] for r in flat)
    wall_ms = (last_exit - first_enter) / 1e6
    gaps = [r["refill_gap_ms"] for r in flat if r["refill_gap_ms"] is not None]

    hb_gaps = [
        (heartbeat[i + 1][0] - heartbeat[i][0]) / 1e6
        for i in range(len(heartbeat) - 1)
    ]

    return {
        "schema_version": 1,
        "kind": "cross_source_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "probe_bytes": probe_bytes, "trigger_ms": trigger_ms,
            "clean_probe_at_ms": clean_probe_at_ms, "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv",
                "preadv_available": callable(getattr(os, "preadv", None)),
                "kernel": platform.release()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "alternate_identity": alternate_identity,
        "local_identity": local_identity,
        "physical_reads": len(flat),
        "useful_bytes": useful_bytes,
        "wall_ms": wall_ms,
        "decimal_gbps": (useful_bytes / (wall_ms / 1000.0) / 1e9) if wall_ms else None,
        "median_ms": percentile(durations, 50),
        "p95_ms": percentile(durations, 95),
        "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 250, 500, 1000)},
        "median_refill_gap_ms": percentile(gaps, 50) if gaps else None,
        "heartbeat_samples": len(heartbeat),
        "heartbeat_max_gap_ms": max(hb_gaps) if hb_gaps else None,
        "heartbeat_median_gap_ms": percentile(hb_gaps, 50) if hb_gaps else None,
        "probe_set_count": len(probe_sets),
        "probe_sets": probe_sets,
        "heartbeat": heartbeat[:400],
        "reads": flat,
    }


# ---------------------------------------------------------------------------
# Always-on sentinel instrumentation.
#
# Design rule: NO diagnostic resource may be created in response to sickness.
# Every sentinel thread, FD and buffer is created and running BEFORE the source
# workers start.  A separate-PID CPU canary spins with no I/O at all.
# ---------------------------------------------------------------------------

_SENTINEL_BYTES = 256 * 1024
_SENTINEL_CADENCE_MS = 25
_HEARTBEAT_CADENCE_MS = 2
_CANARY_FAST_MS = 2
_CANARY_CPU_MS = 50
_CANARY_MAX_FAST = 40000
_CANARY_MAX_CPU = 2000
_CANARY_FAST_OFF = 64
_CANARY_CPU_OFF = _CANARY_FAST_OFF + _CANARY_MAX_FAST * 16
_CANARY_SIZE = _CANARY_CPU_OFF + _CANARY_MAX_CPU * 16

# Same-PID native pthread canary (see native_canary.c).
_NATIVE_CANARY_SO = "/opt/native_canary.so"
_NC_HDR_SIZE = 128
_NC_CAPACITY = 200000
_NC_CADENCE_MS = 2
_NC_SYS_CAPACITY = 50000
_NC_SYS_CADENCE_MS = 3
_NC_USER_REC = 16
_NC_SYS_REC = 32
_NC_FUTEX_REC = 48
_NC_FUTEX_CAPACITY = 50000
_NC_FUTEX_TIMEOUT_MS = 2


def _clock_calibration(iterations: int = 20000) -> dict[str, Any]:
    """Classify which clocks are syscall-backed (vDSO fast vs syscall slow)."""
    def _per_op(fn) -> float:
        start = time.perf_counter_ns()
        for _ in range(iterations):
            fn()
        return (time.perf_counter_ns() - start) / iterations

    return {
        "iterations": iterations,
        "perf_counter_ns_ns_per_op": _per_op(time.perf_counter_ns),
        "monotonic_ns_ns_per_op": _per_op(time.monotonic_ns),
        "process_time_ns_ns_per_op": _per_op(time.process_time_ns),
        "getpid_ns_per_op": _per_op(os.getpid),
        "stat_ns_per_op": _per_op(lambda: os.stat(".")),
    }


def _canary_child(shm, fast_ns: int, cpu_ns: int) -> None:
    """Separate-PID CPU canary.  Pure userspace spin, no I/O, no disk."""
    n_fast = 0
    n_cpu = 0
    next_cpu = time.perf_counter_ns()
    while shm[0] == 0:
        wall = time.perf_counter_ns()
        if n_fast < _CANARY_MAX_FAST:
            struct.pack_into("<qq", shm, _CANARY_FAST_OFF + n_fast * 16, wall, n_fast)
            n_fast += 1
        if wall >= next_cpu and n_cpu < _CANARY_MAX_CPU:
            cpu = time.process_time_ns()
            struct.pack_into("<qq", shm, _CANARY_CPU_OFF + n_cpu * 16, wall, cpu)
            n_cpu += 1
            next_cpu = wall + cpu_ns
        target = wall + fast_ns
        while time.perf_counter_ns() < target:
            if shm[0] != 0:
                break
    struct.pack_into("<q", shm, 8, n_fast)
    struct.pack_into("<q", shm, 16, n_cpu)
    os._exit(0)


def run_sentinel_probe(
    *,
    file_path: str,
    alternate_file_path: str | None = None,
    read_bytes: int = 64 * 1024 * 1024,
    qd: int = 4,
    sentinel_bytes: int = _SENTINEL_BYTES,
    sentinel_cadence_ms: int = _SENTINEL_CADENCE_MS,
    heartbeat_cadence_ms: int = _HEARTBEAT_CADENCE_MS,
    settle_ms: int = 150,
    recovery_ms: int = 1000,
    diagnostics: bool = True,
    native_canary: bool = True,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
) -> dict:
    """Normal 64 MiB x QD4 source workload observed THROUGH already-running sentinels.

    Everything diagnostic is created and running before the source workers start:
      canary  : separate PID, pure userspace spin, records perf_counter + process_time
      heartbeat: main-process thread, records perf_counter + process_time
      A/B/C   : pre-opened FD + preallocated buffer + fixed range, low-cadence reads
                A = same model file, B = alternate file on same Volume, C = local tmpfs
    """
    clock_ns = clock_ns or time.perf_counter_ns
    preadv_fn = getattr(os, "preadv", None)
    if not callable(preadv_fn):
        raise RuntimeError("os.preadv unavailable")
    preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")

    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path, "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    alternate_identity = None
    if alternate_file_path and os.path.isfile(alternate_file_path):
        alt_stat = os.stat(alternate_file_path)
        alternate_identity = {
            "path": alternate_file_path, "size": int(alt_stat.st_size),
            "st_dev": getattr(alt_stat, "st_dev", None),
            "st_ino": getattr(alt_stat, "st_ino", None),
        }
    else:
        alternate_file_path = None

    local_path = os.path.join(tempfile.gettempdir(), "c0_sentinel_local.bin")
    with open(local_path, "wb") as handle:
        handle.write(b"\x5a" * max(sentinel_bytes, 4 * 1024 * 1024))
    local_stat = os.stat(local_path)
    local_identity = {
        "path": local_path, "size": int(local_stat.st_size),
        "st_dev": getattr(local_stat, "st_dev", None),
        "st_ino": getattr(local_stat, "st_ino", None),
        "tmpdir": tempfile.gettempdir(),
    }

    total_blocks = (file_size + read_bytes - 1) // read_bytes
    measured_blocks = list(range(0, total_blocks))
    base, extra = divmod(len(measured_blocks), qd)
    assignments = []
    cursor = 0
    for worker_id in range(qd):
        count = base + (1 if worker_id < extra else 0)
        assignments.append((worker_id, cursor, count))
        cursor += count

    stop = threading.Event()
    lock = threading.Lock()
    records: list[list[dict[str, Any]]] = [[] for _ in range(qd)]
    worker_tids: dict[int, int] = {}
    native_records: list[tuple[int, int]] = []
    u_child_records: list[Any] = []
    s_main_records: list[Any] = []
    s_child_records: list[Any] = []
    b_main_records: list[Any] = []
    b_child_records: list[Any] = []
    sentinel_records: dict[str, list[tuple[int, int, int, int]]] = {}
    hb_records: list[tuple[int, int, int]] = []

    # ---- all diagnostic resources created and opened BEFORE the workers ----
    sentinel_specs: list[tuple[str, str, int, int, int, memoryview]] = []
    sentinel_fds: list[int] = []
    if diagnostics:
        raw_specs: list[tuple[str, str, int, int]] = []
        if file_size >= sentinel_bytes:
            # fixed range at the tail of the file; may overlap the late worker sweep
            raw_specs.append(("A_same_file", file_path, file_size - sentinel_bytes, sentinel_bytes))
        if alternate_file_path:
            raw_specs.append(("B_other_volume_file", alternate_file_path, 0, sentinel_bytes))
        raw_specs.append(("C_tmpfs_local", local_path, 0, sentinel_bytes))
        for name, path, offset, length in raw_specs:
            fd = os.open(path, os.O_RDONLY)
            buf = bytearray(length)
            sentinel_fds.append(fd)
            sentinel_specs.append((name, path, offset, length, fd, memoryview(buf)))
            sentinel_records[name] = []

    canary: dict[str, Any] = {"mode": "disabled"}
    shm = None
    canary_pid = None
    fork_fn = cast(Callable[[], int] | None, getattr(os, "fork", None))
    if diagnostics:
        if not callable(fork_fn):
            canary = {"mode": "unavailable", "error": "os.fork missing"}
        else:
            try:
                shm = mmap.mmap(-1, _CANARY_SIZE)
                shm[0] = 0
                canary_pid = int(fork_fn())
                if canary_pid == 0:
                    try:
                        _canary_child(shm, _CANARY_FAST_MS * 1_000_000,
                                      _CANARY_CPU_MS * 1_000_000)
                    except BaseException:
                        os._exit(1)
                canary = {"mode": "separate_pid", "pid": canary_pid}
            except Exception as exc:  # noqa: BLE001
                canary = {"mode": "fork_failed", "error": f"{type(exc).__name__}:{exc}"[:200]}

    # ---- 2x2 execution/syscall matrix (all four created before any worker) ----
    native: dict[str, Any] = {"mode": "disabled"}
    nc_lib = None
    nc_bufs: dict[str, Any] = {}
    nc_child_pid = None
    if native_canary:
        try:
            nc_lib = ctypes.CDLL(_NATIVE_CANARY_SO)
            for _fn in ("nc_start", "nc_start_syscall", "nc_start_futex"):
                getattr(nc_lib, _fn).argtypes = [ctypes.c_void_p, ctypes.c_longlong,
                                                 ctypes.c_longlong]
                getattr(nc_lib, _fn).restype = ctypes.c_longlong
            for _fn in ("nc_stop", "nc_stop_syscall", "nc_stop_futex", "nc_self_pid",
                        "nc_self_tid", "nc_syscall_number"):
                getattr(nc_lib, _fn).restype = ctypes.c_longlong
            for _fn in ("nc_calibrate_monotonic_ns", "nc_calibrate_syscall_ns"):
                getattr(nc_lib, _fn).argtypes = [ctypes.c_longlong]
                getattr(nc_lib, _fn).restype = ctypes.c_double

            nc_mono = float(nc_lib.nc_calibrate_monotonic_ns(20000))
            nc_sys = float(nc_lib.nc_calibrate_syscall_ns(20000))
            nc_bufs = {
                "u_main": mmap.mmap(-1, _NC_HDR_SIZE + _NC_CAPACITY * _NC_USER_REC),
                "s_main": mmap.mmap(-1, _NC_HDR_SIZE + _NC_SYS_CAPACITY * _NC_SYS_REC),
                "u_child": mmap.mmap(-1, _NC_HDR_SIZE + _NC_CAPACITY * _NC_USER_REC),
                "s_child": mmap.mmap(-1, _NC_HDR_SIZE + _NC_SYS_CAPACITY * _NC_SYS_REC),
                "b_main": mmap.mmap(-1, _NC_HDR_SIZE + _NC_FUTEX_CAPACITY * _NC_FUTEX_REC),
                "b_child": mmap.mmap(-1, _NC_HDR_SIZE + _NC_FUTEX_CAPACITY * _NC_FUTEX_REC),
            }
            for _m in nc_bufs.values():
                _m[0] = 0
            nc_addr = {k: ctypes.addressof(ctypes.c_char.from_buffer(v))
                       for k, v in nc_bufs.items()}

            # fork BEFORE starting our own canaries (never fork a threaded process)
            nc_fork = cast(Callable[[], int] | None, getattr(os, "fork", None))
            if callable(nc_fork):
                nc_child_pid = int(nc_fork())
                if nc_child_pid == 0:
                    # child: U_CHILD (pure userspace) + S_CHILD (same syscall as S_MAIN)
                    try:
                        nc_lib.nc_start(nc_addr["u_child"], _NC_CAPACITY,
                                        _NC_CADENCE_MS * 1_000_000)
                        nc_lib.nc_start_syscall(nc_addr["s_child"], _NC_SYS_CAPACITY,
                                                _NC_SYS_CADENCE_MS * 1_000_000)
                        nc_lib.nc_start_futex(nc_addr["b_child"], _NC_FUTEX_CAPACITY,
                                              _NC_FUTEX_TIMEOUT_MS * 1_000_000)
                        while nc_bufs["u_child"][0] == 0:
                            time.sleep(0.005)
                        nc_lib.nc_stop()
                        nc_lib.nc_stop_syscall()
                        nc_lib.nc_stop_futex()
                    except BaseException:
                        pass
                    os._exit(0)

            rc_u = int(nc_lib.nc_start(nc_addr["u_main"], _NC_CAPACITY,
                                       _NC_CADENCE_MS * 1_000_000))
            rc_s = int(nc_lib.nc_start_syscall(nc_addr["s_main"], _NC_SYS_CAPACITY,
                                               _NC_SYS_CADENCE_MS * 1_000_000))
            rc_b = int(nc_lib.nc_start_futex(nc_addr["b_main"], _NC_FUTEX_CAPACITY,
                                             _NC_FUTEX_TIMEOUT_MS * 1_000_000))
            native = {
                "mode": "matrix_2x2",
                "syscall_number": int(nc_lib.nc_syscall_number()),
                "syscall_name": "SYS_gettid",
                "clock_monotonic_ns_per_call": nc_mono,
                "clock_syscall_ns_per_call": nc_sys,
                "caller_pid": int(nc_lib.nc_self_pid()),
                "caller_tid": int(nc_lib.nc_self_tid()),
                "python_pid": int(os.getpid()),
                "main_tid": int(threading.get_native_id()),
                "child_pid": nc_child_pid,
                "start_rc": {"u_main": rc_u, "s_main": rc_s, "b_main": rc_b},
                "futex_timeout_ms": _NC_FUTEX_TIMEOUT_MS,
                "u_cadence_ms": _NC_CADENCE_MS,
                "s_cadence_ms": _NC_SYS_CADENCE_MS,
            }
        except Exception as exc:  # noqa: BLE001
            native = {"mode": "failed", "error": f"{type(exc).__name__}:{exc}"[:300]}

    def _sentinel_loop(name: str, fd: int, view: memoryview, offset: int, cadence_ns: int) -> None:
        out = sentinel_records[name]
        next_issue = int(clock_ns())
        while not stop.is_set():
            target = next_issue
            enter = int(clock_ns())
            try:
                got = int(preadv(fd, [view], offset))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            with lock:
                out.append((target, enter, exit_ns, got))
            next_issue = target + cadence_ns
            now = int(clock_ns())
            if next_issue > now:
                stop.wait(min((next_issue - now) / 1e9, 0.05))
            else:
                next_issue = now

    def _heartbeat_loop(cadence_ns: int) -> None:
        next_t = int(clock_ns())
        seq = 0
        while not stop.is_set():
            wall = int(clock_ns())
            cpu = int(time.process_time_ns())
            with lock:
                hb_records.append((wall, cpu, seq))
            seq += 1
            next_t += cadence_ns
            now = int(clock_ns())
            if next_t > now:
                stop.wait(min((next_t - now) / 1e9, 0.05))
            else:
                next_t = now

    # ---- start diagnostics, let them settle, THEN start the source workers ----
    diag_threads: list[threading.Thread] = []
    if diagnostics:
        hb_thread = threading.Thread(
            target=_heartbeat_loop, args=(heartbeat_cadence_ms * 1_000_000,), daemon=True)
        hb_thread.start()
        diag_threads.append(hb_thread)
        for name, _path, offset, _length, fd, view in sentinel_specs:
            thread = threading.Thread(
                target=_sentinel_loop,
                args=(name, fd, view, offset, sentinel_cadence_ms * 1_000_000),
                daemon=True)
            thread.start()
            diag_threads.append(thread)
    if settle_ms > 0:
        time.sleep(settle_ms / 1000.0)

    buffers = [bytearray(read_bytes) for _ in range(qd)]
    views = [memoryview(buffer) for buffer in buffers]
    fds = [os.open(file_path, os.O_RDONLY) for _ in range(qd)]
    release_barrier = threading.Barrier(qd)

    def _worker(worker_id: int, start_idx: int, count: int) -> None:
        fd = fds[worker_id]
        view = views[worker_id]
        with lock:
            worker_tids[worker_id] = int(threading.get_native_id())
        release_barrier.wait()
        previous_exit: int | None = None
        for step in range(count):
            block_index = measured_blocks[start_idx + step]
            offset = block_index * read_bytes
            length = min(read_bytes, file_size - offset)
            target = view if length == read_bytes else view[:length]
            enter = int(clock_ns())
            try:
                got = int(preadv(fd, [target], offset))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            records[worker_id].append({
                "worker": worker_id, "gen": step, "block_index": block_index,
                "offset": offset, "length": length, "bytes_returned": got,
                "preadv_enter_ns": enter, "preadv_exit_ns": exit_ns,
                "preadv_ms": (exit_ns - enter) / 1e6,
                "refill_gap_ms": (
                    None if previous_exit is None else (enter - previous_exit) / 1e6
                ),
            })
            previous_exit = exit_ns

    threads = [threading.Thread(target=_worker, args=a) for a in assignments]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if diagnostics:
        time.sleep(recovery_ms / 1000.0)
    stop.set()
    for thread in diag_threads:
        thread.join(timeout=2.0)
    for fd in fds:
        os.close(fd)
    for fd in sentinel_fds:
        os.close(fd)

    canary_fast: list[tuple[int, int]] = []
    canary_cpu: list[tuple[int, int]] = []
    if shm is not None:
        shm[0] = 1
        try:
            if canary_pid:
                os.waitpid(canary_pid, 0)
        except Exception:
            pass
        try:
            n_fast, n_cpu = struct.unpack_from("<qq", shm, 8)
            n_fast = max(0, min(int(n_fast), _CANARY_MAX_FAST))
            n_cpu = max(0, min(int(n_cpu), _CANARY_MAX_CPU))
            canary_fast = [struct.unpack_from("<qq", shm, _CANARY_FAST_OFF + i * 16)
                           for i in range(n_fast)]
            canary_cpu = [struct.unpack_from("<qq", shm, _CANARY_CPU_OFF + i * 16)
                          for i in range(n_cpu)]
            canary["fast_samples"] = n_fast
            canary["cpu_samples"] = n_cpu
        except Exception as exc:  # noqa: BLE001
            canary["read_error"] = f"{type(exc).__name__}:{exc}"[:200]
        shm.close()

    if nc_lib is not None and nc_bufs:
        # stop the child first, then our own canaries, then collect all four rings
        try:
            if nc_child_pid:
                nc_bufs["u_child"][0] = 1
                nc_bufs["s_child"][0] = 1
                nc_bufs["b_child"][0] = 1
        except Exception:
            pass
        try:
            native["stop_rc"] = {"u_main": int(nc_lib.nc_stop()),
                                 "s_main": int(nc_lib.nc_stop_syscall()),
                                 "b_main": int(nc_lib.nc_stop_futex())}
        except Exception as exc:  # noqa: BLE001
            native["stop_error"] = f"{type(exc).__name__}:{exc}"[:200]
        try:
            if nc_child_pid:
                os.waitpid(nc_child_pid, 0)
        except Exception:
            pass
        for _key, _mm in nc_bufs.items():
            try:
                _count, _over, _cap = struct.unpack_from("<qqq", _mm, 8)
                _tid, _pid = struct.unpack_from("<qq", _mm, 32)
                _count = max(0, min(int(_count), int(_cap)))
                if _key.startswith("u_"):
                    _recs: list[Any] = [
                        struct.unpack_from("<qq", _mm, _NC_HDR_SIZE + i * _NC_USER_REC)
                        for i in range(_count)
                    ]
                elif _key.startswith("b_"):
                    _recs = [
                        struct.unpack_from("<qqqqqq", _mm, _NC_HDR_SIZE + i * _NC_FUTEX_REC)
                        for i in range(_count)
                    ]
                else:
                    _recs = [
                        struct.unpack_from("<qqqq", _mm, _NC_HDR_SIZE + i * _NC_SYS_REC)
                        for i in range(_count)
                    ]
                native[_key] = {"count": _count, "overflow": int(_over),
                                "tid": int(_tid), "pid": int(_pid)}
                if _key == "u_main":
                    native_records = _recs
                elif _key == "u_child":
                    u_child_records = _recs
                elif _key == "s_main":
                    s_main_records = _recs
                elif _key == "s_child":
                    s_child_records = _recs
                elif _key == "b_main":
                    b_main_records = _recs
                else:
                    b_child_records = _recs
            except Exception as exc:  # noqa: BLE001
                native[f"{_key}_error"] = f"{type(exc).__name__}:{exc}"[:200]
            try:
                _mm.close()
            except Exception:
                pass

    flat = [r for group in records for r in group]
    durations = [r["preadv_ms"] for r in flat]
    useful_bytes = sum(r["bytes_returned"] for r in flat if r["bytes_returned"] > 0)
    first_enter = min(r["preadv_enter_ns"] for r in flat)
    last_exit = max(r["preadv_exit_ns"] for r in flat)
    wall_ms = (last_exit - first_enter) / 1e6
    gaps = [r["refill_gap_ms"] for r in flat if r["refill_gap_ms"] is not None]
    native_gaps = [
        (native_records[i + 1][0] - native_records[i][0]) / 1e6
        for i in range(len(native_records) - 1)
    ]

    def _gap_list(recs: list[Any]) -> list[float]:
        return [(recs[i + 1][0] - recs[i][0]) / 1e6 for i in range(len(recs) - 1)]

    def _sched_lat(recs: list[Any]) -> tuple[Any, Any, Any, Any]:
        if not recs:
            return (None, None, None, None)
        sch = [(r[1] - r[0]) / 1e6 for r in recs]
        lat = [(r[2] - r[1]) / 1e6 for r in recs]
        return (percentile(sch, 50), max(sch), percentile(lat, 50), max(lat))

    u_child_gaps = _gap_list(u_child_records)
    s_main_stats = _sched_lat(s_main_records)
    s_child_stats = _sched_lat(s_child_records)

    def _futex_stats(recs: list[Any]) -> dict[str, Any]:
        if not recs:
            return {"n": 0}
        blocking = [(r[2] - r[1]) / 1e6 for r in recs]
        timeout = [r[5] / 1e6 for r in recs]
        excess = [b - t for b, t in zip(blocking, timeout)]
        sched = [(r[1] - r[0]) / 1e6 for r in recs]
        return {
            "n": len(recs),
            "configured_timeout_ms": timeout[0] if timeout else None,
            "median_blocking_ms": percentile(blocking, 50),
            "p95_blocking_ms": percentile(blocking, 95),
            "max_blocking_ms": max(blocking),
            "median_excess_ms": percentile(excess, 50),
            "max_excess_ms": max(excess),
            "median_sched_ms": percentile(sched, 50),
            "max_sched_ms": max(sched),
        }

    b_main_stats = _futex_stats(b_main_records)
    b_child_stats = _futex_stats(b_child_records)

    sentinels_out: dict[str, Any] = {}
    for name, path, offset, length, _fd, _view in sentinel_specs:
        rows = sentinel_records[name]
        sched = [(enter - target) / 1e6 for target, enter, _x, _g in rows]
        lat = [(exit_ns - enter) / 1e6 for _t, enter, exit_ns, _g in rows]
        sentinels_out[name] = {
            "path": path, "offset": offset, "length": length,
            "samples": len(rows),
            "max_scheduling_delay_ms": max(sched) if sched else None,
            "median_scheduling_delay_ms": percentile(sched, 50) if sched else None,
            "max_syscall_latency_ms": max(lat) if lat else None,
            "median_syscall_latency_ms": percentile(lat, 50) if lat else None,
            "records": rows,
        }

    hb_gaps = [
        (hb_records[i + 1][0] - hb_records[i][0]) / 1e6
        for i in range(len(hb_records) - 1)
    ]
    canary_gaps = [
        (canary_fast[i + 1][0] - canary_fast[i][0]) / 1e6
        for i in range(len(canary_fast) - 1)
    ]

    return {
        "schema_version": 1,
        "kind": "sentinel_probe",
        "diagnostics_enabled": bool(diagnostics),
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "sentinel_bytes": sentinel_bytes, "sentinel_cadence_ms": sentinel_cadence_ms,
            "heartbeat_cadence_ms": heartbeat_cadence_ms,
            "settle_ms": settle_ms, "recovery_ms": recovery_ms,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv",
                "preadv_available": callable(getattr(os, "preadv", None)),
                "kernel": platform.release()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "alternate_identity": alternate_identity,
        "local_identity": local_identity,
        "clock_calibration": _clock_calibration() if diagnostics else None,
        "physical_reads": len(flat),
        "useful_bytes": useful_bytes,
        "wall_ms": wall_ms,
        "decimal_gbps": (useful_bytes / (wall_ms / 1000.0) / 1e9) if wall_ms else None,
        "median_ms": percentile(durations, 50),
        "p95_ms": percentile(durations, 95),
        "max_ms": max(durations),
        "thresholds": {f"ge_{t}": sum(1 for d in durations if d >= t)
                       for t in (100, 250, 500, 1000)},
        "median_refill_gap_ms": percentile(gaps, 50) if gaps else None,
        "max_refill_gap_ms": max(gaps) if gaps else None,
        "canary": canary,
        "canary_fast": canary_fast,
        "canary_cpu": canary_cpu,
        "native": native,
        "native_records": native_records,
        "native_max_gap_ms": max(native_gaps) if native_gaps else None,
        "native_median_gap_ms": percentile(native_gaps, 50) if native_gaps else None,
        "u_child_records": u_child_records,
        "u_child_max_gap_ms": max(u_child_gaps) if u_child_gaps else None,
        "u_child_median_gap_ms": percentile(u_child_gaps, 50) if u_child_gaps else None,
        "s_main_records": s_main_records,
        "s_main_median_sched_ms": s_main_stats[0],
        "s_main_max_sched_ms": s_main_stats[1],
        "s_main_median_latency_ms": s_main_stats[2],
        "s_main_max_latency_ms": s_main_stats[3],
        "s_child_records": s_child_records,
        "s_child_median_sched_ms": s_child_stats[0],
        "s_child_max_sched_ms": s_child_stats[1],
        "s_child_median_latency_ms": s_child_stats[2],
        "s_child_max_latency_ms": s_child_stats[3],
        "b_main_records": b_main_records,
        "b_child_records": b_child_records,
        "b_main_stats": b_main_stats,
        "b_child_stats": b_child_stats,
        "worker_tids": {str(k): v for k, v in worker_tids.items()},
        "canary_max_gap_ms": max(canary_gaps) if canary_gaps else None,
        "canary_median_gap_ms": percentile(canary_gaps, 50) if canary_gaps else None,
        "heartbeat": hb_records,
        "heartbeat_max_gap_ms": max(hb_gaps) if hb_gaps else None,
        "heartbeat_median_gap_ms": percentile(hb_gaps, 50) if hb_gaps else None,
        "sentinels": sentinels_out,
        "reads": flat,
    }


def run_hedge_probe(
    *,
    file_path: str,
    read_bytes: int,
    qd: int = 4,
    min_launch_gap_ns: int = 0,
    hedge_delay_ns: int = 0,
    hedge_slots_per_worker: int = 3,
    settle_ms: int = 0,
    poll_ns: int = 1_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
) -> dict:
    """Full-file pass with QD logical workers, a global start pacer and ONE bounded
    delayed-rescue lane.

    Threading model (required by the logical-race semantics): ``os.preadv`` is a
    blocking syscall with no cancellation, so a logical worker that itself issued
    the original attempt could never return early when a rescue won.  Therefore:

      * 4 coordinator threads  - own the per-worker block loop and the logical clock
      * 4 attempt threads      - issue the ORIGINAL preadv for their coordinator
      * 1 rescue thread        - the single bounded rescue lane

    Physical in-flight is therefore at most ``qd`` originals + 1 rescue = 5.

    All physical attempts (originals AND rescues) pass through the SAME global
    start-to-start pacer.  Logical latency is always measured from the original
    attempt's start T0, so the hedge delay counts against it.
    """
    clock_ns = clock_ns or time.perf_counter_ns
    preadv_fn = getattr(os, "preadv", None)
    if not callable(preadv_fn):
        raise RuntimeError("os.preadv unavailable")
    preadv = cast(Callable[[int, list[memoryview], int], int], preadv_fn)
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    if min_launch_gap_ns < 0 or hedge_delay_ns < 0:
        raise ValueError("gaps and delays must be non-negative")

    stat_result = os.stat(file_path)
    file_size = int(stat_result.st_size)
    file_identity = {
        "path": file_path, "size": file_size,
        "st_dev": getattr(stat_result, "st_dev", None),
        "st_ino": getattr(stat_result, "st_ino", None),
        "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None),
    }

    total_blocks = (file_size + read_bytes - 1) // read_bytes
    base, extra = divmod(total_blocks, qd)
    assignments: list[tuple[int, int, int]] = []
    cur = 0
    for w in range(qd):
        c = base + (1 if w < extra else 0)
        assignments.append((w, cur, c))
        cur += c

    orig_buffers = [bytearray(read_bytes) for _ in range(qd)]
    orig_views = [memoryview(b) for b in orig_buffers]
    orig_fds = [os.open(file_path, os.O_RDONLY) for _ in range(qd)]

    # Independent hedge resources: `hedge_slots_per_worker` private FD + buffer +
    # attempt state PER LOGICAL WORKER.  A hedge for worker w can only use w's own
    # pool, so hedge A can never suppress hedge B.  Within a worker's pool a slot is
    # occupied only while its hedge attempt is physically in flight; a COMPLETED
    # hedge frees its slot immediately even if that worker's ORIGINAL attempt is
    # still stuck.
    n_slots = max(1, int(hedge_slots_per_worker))
    hedge_fds = [os.open(file_path, os.O_RDONLY) for _ in range(qd * n_slots)]
    hedge_buffers = [bytearray(read_bytes) for _ in range(qd * n_slots)]
    hedge_views = [memoryview(b) for b in hedge_buffers]
    hedge_free: list[list[int]] = [
        [w * n_slots + k for k in range(n_slots)] for w in range(qd)
    ]

    # ---- single global start-to-start pacer (originals AND rescues) ----------
    pacer_lock = threading.Lock()
    last_launch_ns = [0]

    def _gate() -> int:
        while True:
            with pacer_lock:
                now = int(clock_ns())
                elapsed = now - last_launch_ns[0]
                if elapsed >= min_launch_gap_ns:
                    last_launch_ns[0] = now
                    return now
                remaining = min_launch_gap_ns - elapsed
            time.sleep(min(remaining / 1e9, 0.001))

    state_lock = threading.Lock()
    stop = threading.Event()
    cur_state: list[dict[str, Any] | None] = [None] * qd
    states: list[dict[str, Any]] = []
    physical: list[dict[str, Any]] = []
    counters = {"eligible": 0, "launched": 0, "lane_busy": 0, "suppressed": 0}
    logical_seq = [0]

    orig_go = [threading.Event() for _ in range(qd)]
    orig_started = [threading.Event() for _ in range(qd)]
    finished = [threading.Event() for _ in range(qd)]

    hedge_lock = threading.Lock()
    hedge_go = [threading.Event() for _ in range(qd * n_slots)]
    hedge_req: list[dict[str, Any] | None] = [None] * (qd * n_slots)

    def _attempt_thread(w: int) -> None:
        view = orig_views[w]
        fd = orig_fds[w]
        while not stop.is_set():
            if not orig_go[w].wait(timeout=0.05):
                continue
            orig_go[w].clear()
            st = cur_state[w]
            if st is None:
                continue
            claim = _gate()
            enter = int(clock_ns())
            st["t0_ns"] = enter
            st["orig_gate_claim_ns"] = claim
            orig_started[w].set()
            length = st["length"]
            target = view if length == read_bytes else view[:length]
            try:
                got = int(preadv(fd, [target], st["offset"]))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            with state_lock:
                st["orig_exit_ns"] = exit_ns
                st["orig_bytes"] = got
                physical.append({"kind": "orig", "worker": w,
                                 "logical_id": st["logical_id"],
                                 "offset": st["offset"], "length": length,
                                 "gate_claim_ns": claim, "enter_ns": enter,
                                 "exit_ns": exit_ns,
                                 "preadv_ms": (exit_ns - enter) / 1e6,
                                 "won": st["winner"] is None})
                if st["winner"] is None:
                    st["winner"] = "orig"
                    st["accepted_ns"] = exit_ns
                    finished[w].set()

    def _hedge_thread(slot_id: int) -> None:
        fd = hedge_fds[slot_id]
        view = hedge_views[slot_id]
        owner = slot_id // n_slots
        while not stop.is_set():
            if not hedge_go[slot_id].wait(timeout=0.05):
                continue
            hedge_go[slot_id].clear()
            req = hedge_req[slot_id]
            if req is None:
                continue
            w = int(req["worker"])
            st: dict[str, Any] = req["state"]
            length = st["length"]
            claim = _gate()
            enter = int(clock_ns())
            st["hedge_actual_launch_ns"] = enter
            st["hedge_resource_ready_ns"] = req["ready_ns"]
            st["rescue_gate_claim_ns"] = claim
            target = view if length == read_bytes else view[:length]
            try:
                got = int(preadv(fd, [target], st["offset"]))
            except BaseException:
                got = -1
            exit_ns = int(clock_ns())
            with state_lock:
                st["rescue_exit_ns"] = exit_ns
                st["rescue_bytes"] = got
                physical.append({"kind": "rescue", "worker": w,
                                 "logical_id": st["logical_id"],
                                 "offset": st["offset"], "length": length,
                                 "gate_claim_ns": claim, "enter_ns": enter,
                                 "exit_ns": exit_ns,
                                 "preadv_ms": (exit_ns - enter) / 1e6,
                                 "won": st["winner"] is None})
                if st["winner"] is None:
                    st["winner"] = "rescue"
                    st["accepted_ns"] = exit_ns
                    finished[w].set()
            hedge_req[slot_id] = None
            with hedge_lock:
                hedge_free[owner].append(slot_id)

    def _coord_thread(w: int, first_block: int, count: int) -> None:
        period = poll_ns / 1e9
        for step in range(count):
            blk = first_block + step
            offset = blk * read_bytes
            length = min(read_bytes, file_size - offset)
            with state_lock:
                logical_seq[0] += 1
                st: dict[str, Any] = {
                    "worker": w, "logical_id": logical_seq[0], "block_index": blk,
                    "offset": offset, "length": length, "winner": None,
                    "accepted_ns": None, "t0_ns": None, "orig_exit_ns": None,
                    "rescue_exit_ns": None, "hedge_launched": False,
                    "hedge_eligible_ns": None, "hedge_actual_launch_ns": None,
                }
                cur_state[w] = st
                states.append(st)
            orig_started[w].clear()
            finished[w].clear()
            orig_go[w].set()
            if not orig_started[w].wait(timeout=30.0):
                stop.set()
                return
            t0 = st["t0_ns"]
            while not finished[w].is_set():
                now = int(clock_ns())
                if (hedge_delay_ns and not st["hedge_launched"]
                        and now - t0 >= hedge_delay_ns):
                    st["hedge_launched"] = True
                    st["hedge_eligible_ns"] = now
                    counters["eligible"] += 1
                    slot_id = None
                    with hedge_lock:
                        if hedge_free[w]:
                            slot_id = hedge_free[w].pop()
                    if slot_id is not None:
                        counters["launched"] += 1
                        st["hedge_slot"] = slot_id
                        hedge_req[slot_id] = {"worker": w, "state": st,
                                              "ready_ns": int(clock_ns())}
                        hedge_go[slot_id].set()
                    else:
                        counters["lane_busy"] += 1
                        counters["suppressed"] += 1
                time.sleep(period)

    if settle_ms > 0:
        time.sleep(settle_ms / 1000.0)

    attempt_threads = [threading.Thread(target=_attempt_thread, args=(w,))
                       for w in range(qd)]
    hedge_threads = [threading.Thread(target=_hedge_thread, args=(s,))
                     for s in range(qd * n_slots)]
    coords = [threading.Thread(target=_coord_thread, args=a) for a in assignments]
    for t in attempt_threads + hedge_threads:
        t.start()
    for t in coords:
        t.start()
    for t in coords:
        t.join()
    # grace period so a late rescue / late original can be observed
    time.sleep(0.5)
    stop.set()
    for t in attempt_threads + hedge_threads:
        t.join(timeout=2.0)
    for fd in orig_fds + hedge_fds:
        os.close(fd)

    # ---- derived logical records ------------------------------------------
    logical_records: list[dict[str, Any]] = []
    for st in states:
        t0 = st["t0_ns"]
        accepted = st["accepted_ns"]
        logical_ms = ((accepted - t0) / 1e6) if (t0 and accepted) else None
        saved = None
        if (st["winner"] == "rescue" and st["orig_exit_ns"] is not None
                and st["rescue_exit_ns"] is not None):
            saved = (st["orig_exit_ns"] - st["rescue_exit_ns"]) / 1e6
        logical_records.append({
            "worker": st["worker"], "logical_id": st["logical_id"],
            "block_index": st["block_index"], "offset": st["offset"],
            "length": st["length"], "t0_ns": t0,
            "accepted_ns": accepted, "logical_ms": logical_ms,
            "winner": st["winner"], "rescue_win": st["winner"] == "rescue",
            "hedge_launched": st["hedge_launched"],
            "hedge_eligible_ns": st["hedge_eligible_ns"],
            "hedge_actual_launch_ns": st["hedge_actual_launch_ns"],
            "pacer_extra_wait_ms": (
                (st["hedge_actual_launch_ns"] - st["hedge_eligible_ns"]) / 1e6
                if st["hedge_eligible_ns"] and st["hedge_actual_launch_ns"] else None),
            "orig_exit_ns": st["orig_exit_ns"],
            "rescue_exit_ns": st["rescue_exit_ns"],
            "orig_censored": st["orig_exit_ns"] is None,
            "time_saved_ms": saved,
        })

    logical_ms_all = [r["logical_ms"] for r in logical_records
                      if r["logical_ms"] is not None]
    orig_ms = [p["preadv_ms"] for p in physical if p["kind"] == "orig"]
    resc_ms = [p["preadv_ms"] for p in physical if p["kind"] == "rescue"]
    winners = [r for r in logical_records if r["rescue_win"]]
    saved_ms = [r["time_saved_ms"] for r in winners if r["time_saved_ms"] is not None]

    starts = sorted(p["enter_ns"] for p in physical)
    inter = [(starts[i + 1] - starts[i]) / 1e6 for i in range(len(starts) - 1)]
    active_at_enter = [
        sum(1 for q in physical
            if q is not p and q["enter_ns"] < p["enter_ns"] < q["exit_ns"])
        for p in physical
    ]
    by_enter = sorted(physical, key=lambda p: p["enter_ns"])
    first_launches = [
        {"ordinal": i, "kind": q["kind"], "worker": q["worker"],
         "t_rel_ms": (q["enter_ns"] - starts[0]) / 1e6,
         "gap_from_previous_ms": (None if i == 0
                                  else (q["enter_ns"] - by_enter[i - 1]["enter_ns"]) / 1e6),
         "preadv_ms": q["preadv_ms"], "active_at_enter": active_at_enter[
             physical.index(q)]}
        for i, q in enumerate(by_enter[:8])
    ] if by_enter else []

    wall_ms = ((max(p["exit_ns"] for p in physical) - starts[0]) / 1e6
               if physical else 0.0)

    thresholds = {f"ge_{t}": sum(1 for d in logical_ms_all if d >= t)
                  for t in (100, 250, 500, 1000, 2000)}
    physical_thresholds = {f"ge_{t}": sum(1 for d in orig_ms if d >= t)
                           for t in (100, 250, 500, 1000, 2000)}

    return {
        "schema_version": 1,
        "kind": "hedge_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes,
            "read_mib": read_bytes / 1024 / 1024, "qd": qd,
            "min_launch_gap_ns": min_launch_gap_ns,
            "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "hedge_delay_ns": hedge_delay_ns,
            "hedge_delay_ms": hedge_delay_ns / 1e6,
            "total_blocks": total_blocks, "threads": qd + qd + 1,
        },
        "env": {"platform": platform.system(), "syscall_impl": "os.preadv"},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": file_identity,
        "logical_reads": len(logical_records),
        "logical_ms": logical_ms_all,
        "logical_thresholds": thresholds,
        "logical_median_ms": percentile(logical_ms_all, 50) if logical_ms_all else None,
        "logical_mean_ms": (statistics.fmean(logical_ms_all) if logical_ms_all else None),
        "logical_max_ms": max(logical_ms_all) if logical_ms_all else None,
        "physical_attempts": len(physical),
        "orig_attempts": len(orig_ms),
        "rescue_attempts": len(resc_ms),
        "orig_median_ms": percentile(orig_ms, 50) if orig_ms else None,
        "orig_mean_ms": statistics.fmean(orig_ms) if orig_ms else None,
        "orig_p95_ms": percentile(orig_ms, 95) if orig_ms else None,
        "orig_max_ms": max(orig_ms) if orig_ms else None,
        "orig_thresholds": physical_thresholds,
        "rescue_median_ms": percentile(resc_ms, 50) if resc_ms else None,
        "rescue_mean_ms": statistics.fmean(resc_ms) if resc_ms else None,
        "rescue_p95_ms": percentile(resc_ms, 95) if resc_ms else None,
        "rescue_max_ms": max(resc_ms) if resc_ms else None,
        "hedge": {
            "eligible": counters["eligible"], "launched": counters["launched"],
            "lane_busy": counters["lane_busy"],
            "suppressed_resource_busy": counters["suppressed"],
            "hedge_slots_per_worker": n_slots,
            "rescue_wins": len(winners),
            "rescue_win_rate": (len(winners) / counters["launched"]
                                if counters["launched"] else None),
            "launched_pct_of_logical": (
                100.0 * counters["launched"] / len(logical_records)
                if logical_records else None),
            "amplification": (len(physical) / len(logical_records)
                              if logical_records else None),
            "median_time_saved_ms": percentile(saved_ms, 50) if saved_ms else None,
            "mean_time_saved_ms": (statistics.fmean(saved_ms) if saved_ms else None),
            "max_time_saved_ms": max(saved_ms) if saved_ms else None,
            "censored_originals": sum(1 for r in logical_records if r["orig_censored"]),
            "median_pacer_extra_wait_ms": percentile(
                [r["pacer_extra_wait_ms"] for r in logical_records
                 if r["pacer_extra_wait_ms"] is not None], 50),
        },
        "min_attempt_gap_ms": min(inter) if inter else None,
        "p10_attempt_gap_ms": percentile(inter, 10) if inter else None,
        "median_attempt_gap_ms": percentile(inter, 50) if inter else None,
        "p95_attempt_gap_ms": percentile(inter, 95) if inter else None,
        "max_attempt_gap_ms": max(inter) if inter else None,
        "max_simultaneous_in_flight": _max_overlap(physical),
        "full_file_wall_ms": wall_ms,
        "first_launches": first_launches,
        "logical_records": logical_records,
        "physical_records": physical,
    }


def _max_overlap(physical: list[dict[str, Any]]) -> int | None:
    if not physical:
        return None
    events: list[tuple[int, int]] = []
    for p in physical:
        events.append((p["enter_ns"], 1))
        events.append((p["exit_ns"], -1))
    events.sort()
    cur = best = 0
    for _t, d in events:
        cur += d
        best = max(best, cur)
    return best


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, dest="file_path")
    parser.add_argument("--width", required=True, type=int, dest="race_width")
    parser.add_argument("--logical-qd", type=int, default=2)
    parser.add_argument("--read-bytes", type=int, default=128 * 1024 * 1024)
    parser.add_argument("--fd-mode", choices=("independent", "shared"), default="independent")
    parser.add_argument("--max-blocks", type=int)
    parser.add_argument("--hash-mode", choices=("none", "winners_in_order", "per_block"), default="winners_in_order")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--out")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    report = run_race_oracle(
        file_path=args.file_path,
        race_width=args.race_width,
        logical_qd=args.logical_qd,
        read_bytes=args.read_bytes,
        fd_mode=args.fd_mode,
        max_blocks=args.max_blocks,
        expected_sha256=args.expected_sha256,
        hash_mode=args.hash_mode,
    )
    accepted = report["accepted"]
    physical = report["physical"]
    print(
        "accepted mean/median/p95/max: "
        f"{accepted['mean_ms']:.3f}/{accepted['median_ms']:.3f}/{accepted['p95_ms']:.3f}/{accepted['max_ms']:.3f} ms"
    )
    print(
        "physical mean/median/max: "
        f"{physical['mean_ms']:.3f}/{physical['median_ms']:.3f}/{physical['max_ms']:.3f} ms"
    )
    print(f"amplification ratio: {report['amplification']['speculative_byte_amplification_ratio']:.3f}")
    print(f"winner distribution: {report['winner_distribution']['wins_by_racer_index']}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
