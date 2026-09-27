"""Canonical M2 mmap/process source engine.

This module deliberately contains only the exact-window MAP_PRIVATE reader,
its four-process scheduler, and the shared-staging publication protocol.  The
oracle may request detailed records; production requests only the shared
correctness state and waits for every child to exit before returning.
"""

from __future__ import annotations

import ctypes as _ct
import collections
import os
import platform
import statistics
import time
from typing import Any, Callable, cast

_PAGE = 4096
_PROT_READ = 1
_MAP_PRIVATE = 2
_MAP_POPULATE = 0x08000

try:
    _LIBC = _ct.CDLL(None, use_errno=True)
    _LIBC.memcpy.restype = _ct.c_void_p
    _LIBC.memcpy.argtypes = [_ct.c_void_p, _ct.c_void_p, _ct.c_size_t]
    _LIBC.mmap.restype = _ct.c_void_p
    _LIBC.mmap.argtypes = [
        _ct.c_void_p, _ct.c_size_t, _ct.c_int, _ct.c_int, _ct.c_int, _ct.c_longlong
    ]
    _LIBC.munmap.restype = _ct.c_int
    _LIBC.munmap.argtypes = [_ct.c_void_p, _ct.c_size_t]
except BaseException:  # pragma: no cover - platform capability
    _LIBC = None


def _percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percent / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


def _alloc_gate(pacer_lock: Any, last_start: Any, gap_ns: int, clock_ns: Callable[[], int]):
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


def _load_native():
    if _LIBC is None:
        return None
    try:
        lib = _ct.CDLL("/opt/source_touch.so")
    except BaseException:
        return None
    lib.st_touch_pages.restype = _ct.c_long
    lib.st_touch_pages.argtypes = [_ct.c_void_p, _ct.c_size_t, _ct.c_size_t]
    lib.st_touch_lines.restype = _ct.c_long
    lib.st_touch_lines.argtypes = [_ct.c_void_p, _ct.c_size_t, _ct.c_size_t]
    lib.st_reduce_full.restype = _ct.c_long
    lib.st_reduce_full.argtypes = [_ct.c_void_p, _ct.c_size_t]
    return lib


def _reader(args: tuple) -> None:
    (
        reader_id, file_path, file_size, read_bytes, mmap_mode, consume_mode,
        source_offset, touch_ahead, lane_flat, lane_off, qd, sticky, ownership, winner,
        winner_kind, start_ns, winner_exit_ns, attempts, completed, lock,
        next_global, last_start, pacer_lock, gap_ns, total_blocks, max_idle_s,
        consumer_pos, touch_pos, ready_count, go, child_conn, staging,
        diagnostics, worker_status, read_enter_ns, read_exit_ns,
        staging_wait_ns, staging_wait_events,
    ) = args
    payload: dict[str, Any] = {
        "reader": reader_id, "pid": os.getpid(), "status": "ok", "records": [],
        "stale": 0, "affinity_breaks": 0, "idle_no_work_ms": 0.0,
        "touch_events": [], "payload_copy_bytes": 0, "dest_allocated": False,
        "staging_wait_ms": 0.0, "staging_wait_events": 0, "staging_published": 0,
    }
    fd = -1
    mm_base = 0
    mapped_size = int(source_offset) + int(file_size)
    try:
        if _LIBC is None:
            raise RuntimeError("libc_unavailable")
        lib = _load_native() if consume_mode != "memcpy" else None
        if consume_mode != "memcpy" and lib is None:
            raise RuntimeError("source_touch_so_unavailable")
        zero_copy = consume_mode != "memcpy"
        dest = None
        dest_addr = 0
        stage_published = None
        stage_consumed = None
        stage_off = None
        stage_len = None
        stage_slots = 0
        stage_lane_base = 0
        if not zero_copy:
            if staging is None:
                dest = bytearray(read_bytes)
                dest_addr = _ct.addressof(_ct.c_char.from_buffer(dest))
            else:
                stage_published = staging["published"][reader_id]
                stage_consumed = staging["consumed"][reader_id]
                stage_off = staging["slot_off"][reader_id]
                stage_len = staging["slot_len"][reader_id]
                stage_slots = int(staging["slots"])
                stage_lane_base = int(staging["seg_base"]) + reader_id * int(staging["lane_bytes"])
            payload["dest_allocated"] = True
        fd = os.open(file_path, os.O_RDONLY)
        if mmap_mode == "persistent":
            mm_base = int(_LIBC.mmap(None, mapped_size, _PROT_READ, _MAP_PRIVATE, fd, 0))
            if mm_base in (0, -1) or mm_base == 0xFFFFFFFFFFFFFFFF:
                raise OSError(f"persistent_mmap_failed errno={_ct.get_errno()}")
        with lock:
            ready_count.value = int(ready_count.value) + 1
        while int(go.value) == 0:
            time.sleep(0.001)

        lanes_local = []
        for lane in range(qd):
            start = int(lane_off[lane])
            end = int(lane_off[lane + 1])
            lanes_local.append([int(lane_flat[index]) for index in range(start, end)])
        my_lane = lanes_local[reader_id]
        cursor = 0
        idle_total = 0.0
        idle_deadline: float | None = None
        stage_seq = 0
        while True:
            with lock:
                if int(completed.value) >= total_blocks:
                    break
            bid = -1
            now = int(time.perf_counter_ns())
            with lock:
                while cursor < len(my_lane):
                    candidate = my_lane[cursor]
                    cursor += 1
                    if ownership[candidate] == 0:
                        bid = candidate
                        break
                if bid < 0:
                    for lane in range(qd):
                        if lane == reader_id:
                            continue
                        for candidate in lanes_local[lane]:
                            if ownership[candidate] == 0:
                                bid = candidate
                                payload["affinity_breaks"] += 1
                                break
                        if bid >= 0:
                            break
                if bid >= 0:
                    ownership[bid] = 1
                    start_ns[bid] = now
                    consumer_pos[reader_id] = cursor - 1
            if bid < 0:
                idle_total += (int(time.perf_counter_ns()) - now) / 1e6
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
            destination_offset = bid * read_bytes
            offset = int(source_offset) + destination_offset
            claim, gate_wait_ns = _alloc_gate(pacer_lock, last_start, gap_ns, time.perf_counter_ns)
            win_addr = 0
            win_len = 0
            if mmap_mode == "window":
                window_start = offset & ~(_PAGE - 1)
                win_len = ((offset + length - window_start + _PAGE - 1) // _PAGE) * _PAGE
                map_started = time.perf_counter_ns()
                win_addr = int(_LIBC.mmap(
                    None, win_len, _PROT_READ, _MAP_PRIVATE | _MAP_POPULATE, fd, window_start
                ))
                map_ms = (time.perf_counter_ns() - map_started) / 1e6
                if win_addr in (0, -1) or win_addr == 0xFFFFFFFFFFFFFFFF:
                    with lock:
                        worker_status[reader_id] = -1
                        completed.value = int(completed.value) + 1
                        ownership[bid] = 2
                    continue
                ptr = win_addr + offset - window_start
            else:
                ptr = mm_base + offset
                map_ms = 0.0
            mem_dest = dest_addr
            if staging is not None:
                assert stage_published is not None
                assert stage_consumed is not None
                assert stage_off is not None
                assert stage_len is not None
                stage_seq = int(stage_published.value)
                if stage_seq - int(stage_consumed.value) >= stage_slots:
                    wait_start = int(time.perf_counter_ns())
                    while stage_seq - int(stage_consumed.value) >= stage_slots:
                        time.sleep(0.0001)
                    wait_ns = int(time.perf_counter_ns()) - wait_start
                    payload["staging_wait_ms"] += wait_ns / 1e6
                    payload["staging_wait_events"] += 1
                    staging_wait_ns[reader_id] += int(wait_ns)
                    staging_wait_events[reader_id] += 1
                stage_index = stage_seq % stage_slots
                stage_off[stage_index] = destination_offset
                stage_len[stage_index] = length
                mem_dest = stage_lane_base + stage_index * read_bytes
            enter = int(time.perf_counter_ns())
            error = None
            try:
                if consume_mode == "memcpy":
                    _LIBC.memcpy(mem_dest, ptr, length)
                elif consume_mode == "d0":
                    assert lib is not None
                    lib.st_touch_pages(_ct.c_void_p(ptr), _ct.c_size_t(length), 4096)
                elif consume_mode == "d1":
                    assert lib is not None
                    lib.st_touch_lines(_ct.c_void_p(ptr), _ct.c_size_t(length), 64)
                else:
                    assert lib is not None
                    lib.st_reduce_full(_ct.c_void_p(ptr), _ct.c_size_t(length))
                got = length
            except BaseException as exc:
                got = -1
                error = f"{type(exc).__name__}:{str(exc)[:160]}"
                worker_status[reader_id] = -1
            exit_ns = int(time.perf_counter_ns())
            read_enter_ns[bid] = enter
            read_exit_ns[bid] = exit_ns
            if staging is not None:
                assert stage_published is not None
                stage_published.value = stage_seq + 1
            if win_addr:
                assert _LIBC is not None
                unmap_started = time.perf_counter_ns()
                _LIBC.munmap(win_addr, win_len)
                unmap_ms = (time.perf_counter_ns() - unmap_started) / 1e6
            else:
                unmap_ms = 0.0
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
            if diagnostics:
                payload["records"].append({
                    "reader": reader_id, "pid": os.getpid(), "block_id": int(bid),
                    "kind": "primary", "seq": len(payload["records"]),
                    "offset": offset, "length": length, "gate_claim_ns": int(claim),
                    "gate_wait_ms": gate_wait_ns / 1e6, "preadv_enter_ns": enter,
                    "preadv_exit_ns": exit_ns, "preadv_ms": (exit_ns - enter) / 1e6,
                    "bytes_returned": got, "map_ms": map_ms, "unmap_ms": unmap_ms,
                    "sink": 0, "error": error, "consume_mode": consume_mode,
                })
        payload["idle_no_work_ms"] = idle_total
        if staging is not None:
            assert stage_published is not None
            payload["staging_wait_ms"] = float(payload["staging_wait_ms"])
            payload["staging_published"] = int(stage_published.value)
    except BaseException as exc:
        worker_status[reader_id] = -1
        payload["status"] = "error"
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
    finally:
        if mm_base:
            try:
                assert _LIBC is not None
                _LIBC.munmap(mm_base, mapped_size)
            except BaseException:
                pass
        if fd >= 0:
            try:
                os.close(fd)
            except BaseException:
                pass
        if child_conn is not None:
            try:
                child_conn.send(payload)
                child_conn.close()
            except BaseException:
                pass


def _persistent_reader_close_fds(fd_cache: collections.OrderedDict) -> None:
    for value in tuple(fd_cache.values()):
        fd = value[0] if isinstance(value, tuple) else value
        try:
            os.close(fd)
        except OSError:
            pass
    fd_cache.clear()


def _persistent_reader_fd(
    fd_cache: collections.OrderedDict,
    path: str,
    identity: tuple[int, int, int, int],
    cache_limit: int,
) -> int:
    cached = fd_cache.get(path)
    if cached is not None:
        fd, cached_identity = cached
        if cached_identity == identity:
            fd_cache.move_to_end(path)
            return int(fd)
        try:
            os.close(fd)
        except OSError:
            pass
        fd_cache.pop(path, None)
    fd = os.open(path, os.O_RDONLY)
    fd_cache[path] = (fd, identity)
    fd_cache.move_to_end(path)
    while len(fd_cache) > max(1, int(cache_limit)):
        _old_path, (old_fd, _old_identity) = fd_cache.popitem(last=False)
        try:
            os.close(old_fd)
        except OSError:
            pass
    return int(fd)


def _persistent_reader_load(
    reader_id: int,
    request: dict[str, Any],
    staging: dict[str, Any],
    fd_cache: collections.OrderedDict,
    fd_cache_limit: int,
    ownership: Any,
    completed: Any,
    failed: Any,
    scheduler_lock: Any,
    last_start: Any,
    pacer_lock: Any,
) -> dict[str, Any]:
    if _LIBC is None:
        raise RuntimeError("libc_unavailable")
    path = str(request["path"])
    source_offset = int(request["source_offset"])
    data_bytes = int(request["data_bytes"])
    read_bytes = int(request["read_bytes"])
    identity_values = tuple(int(value) for value in request["identity"])
    if len(identity_values) != 4:
        raise RuntimeError("persistent_reader_file_identity_invalid")
    identity = (
        identity_values[0], identity_values[1], identity_values[2], identity_values[3]
    )
    cached = fd_cache.get(path)
    fd_cache_hit = bool(cached is not None and cached[1] == identity)
    fd = _persistent_reader_fd(fd_cache, path, identity, fd_cache_limit)
    published = staging["published"][reader_id]
    consumed = staging["consumed"][reader_id]
    slot_off = staging["slot_off"][reader_id]
    slot_len = staging["slot_len"][reader_id]
    slots = int(staging["slots"])
    lane_base = int(staging["seg_base"]) + reader_id * int(staging["lane_bytes"])
    lane_ranges = [tuple(int(value) for value in bounds) for bounds in request["lane_ranges"]]
    total_blocks = int(request["total_blocks"])
    min_launch_gap_ns = int(request["min_launch_gap_ns"])
    own_start, own_end = lane_ranges[reader_id]
    cursor = own_start
    first_enter = 0
    last_exit = 0
    bytes_read = 0
    affinity_breaks = 0
    idle_wait_ns = 0
    records: list[dict[str, int]] = []
    while True:
        wait_started = time.perf_counter_ns()
        block_id = -1
        with scheduler_lock:
            if int(failed.value):
                raise RuntimeError("persistent_reader_peer_failed")
            if int(completed.value) >= total_blocks:
                break
            while cursor < own_end:
                candidate = cursor
                cursor += 1
                if int(ownership[candidate]) == 0:
                    block_id = candidate
                    break
            if block_id < 0:
                for lane, (start, end) in enumerate(lane_ranges):
                    if lane == reader_id:
                        continue
                    for candidate in range(start, end):
                        if int(ownership[candidate]) == 0:
                            block_id = candidate
                            affinity_breaks += 1
                            break
                    if block_id >= 0:
                        break
            if block_id >= 0:
                ownership[block_id] = 1
        if block_id < 0:
            idle_wait_ns += time.perf_counter_ns() - wait_started
            time.sleep(0.0002)
            continue

        length = min(read_bytes, data_bytes - block_id * read_bytes)
        if length <= 0:
            raise RuntimeError(f"persistent_reader_block_out_of_range:{block_id}")
        destination_offset = block_id * read_bytes
        absolute_offset = source_offset + destination_offset
        window_start = absolute_offset & ~(_PAGE - 1)
        window_len = ((absolute_offset + length - window_start + _PAGE - 1) // _PAGE) * _PAGE
        claim_ns, gate_wait_ns = _alloc_gate(
            pacer_lock, last_start, min_launch_gap_ns, time.perf_counter_ns
        )
        map_started = time.perf_counter_ns()
        window = int(_LIBC.mmap(
            None, window_len, _PROT_READ, _MAP_PRIVATE, fd, window_start
        ))
        map_ns = time.perf_counter_ns() - map_started
        if window in (0, -1) or window == 0xFFFFFFFFFFFFFFFF:
            raise OSError(f"persistent_mmap_failed errno={_ct.get_errno()}")
        try:
            sequence = int(published.value)
            while sequence - int(consumed.value) >= slots:
                if int(staging["alive"].value) == 0:
                    raise RuntimeError("persistent_reader_staging_stopped")
                if int(failed.value):
                    raise RuntimeError("persistent_reader_peer_failed")
                time.sleep(0.0001)
            if int(failed.value):
                raise RuntimeError("persistent_reader_peer_failed")
            slot = sequence % slots
            slot_off[slot] = destination_offset
            slot_len[slot] = length
            entered = int(time.perf_counter_ns())
            _LIBC.memcpy(
                lane_base + slot * read_bytes,
                window + absolute_offset - window_start,
                length,
            )
            exited = int(time.perf_counter_ns())
            # Publish as soon as memcpy completes so H2D can overlap munmap.
            published.value = sequence + 1
        finally:
            unmap_started = time.perf_counter_ns()
            _LIBC.munmap(window, window_len)
            unmap_ns = time.perf_counter_ns() - unmap_started
        if first_enter == 0:
            first_enter = entered
        last_exit = exited
        bytes_read += length
        with scheduler_lock:
            ownership[block_id] = 2
            completed.value = int(completed.value) + 1
        records.append({
            "block_id": block_id,
            "offset": destination_offset,
            "length": length,
            "gate_claim_ns": int(claim_ns),
            "gate_wait_ns": int(gate_wait_ns),
            "map_ns": int(map_ns),
            "enter_ns": entered,
            "exit_ns": exited,
            "unmap_ns": int(unmap_ns),
        })
    return {
        "reader": int(reader_id),
        "pid": int(os.getpid()),
        "status": "ok",
        "first_enter_ns": first_enter,
        "last_exit_ns": last_exit,
        "read_count": len(records),
        "read_bytes": bytes_read,
        "fd_cache_hit": fd_cache_hit,
        "affinity_breaks": affinity_breaks,
        "idle_wait_ns": idle_wait_ns,
        "records": records,
    }


def persistent_reader_main(
    reader_id: int,
    command_conn: Any,
    staging: dict[str, Any],
    fd_cache_limit: int = 4,
    ownership: Any = None,
    completed: Any = None,
    failed: Any = None,
    scheduler_lock: Any = None,
    last_start: Any = None,
    pacer_lock: Any = None,
) -> None:
    """Run one CUDA-sterile reader for the lifetime of the container."""
    fd_cache: collections.OrderedDict = collections.OrderedDict()
    try:
        command_conn.send({"command": "READY", "reader": int(reader_id), "pid": os.getpid()})
        while True:
            request = command_conn.recv()
            command = str(request.get("command", ""))
            if command == "EXIT":
                return
            if command == "INVALIDATE_FDS":
                _persistent_reader_close_fds(fd_cache)
                command_conn.send({"command": "INVALIDATE_FDS_DONE", "reader": int(reader_id)})
                continue
            if command != "LOAD":
                command_conn.send({
                    "command": "LOAD_DONE",
                    "generation": request.get("generation"),
                    "reader": int(reader_id),
                    "status": "error",
                    "error": f"unknown_reader_command:{command}",
                })
                continue
            try:
                payload = _persistent_reader_load(
                    reader_id,
                    request,
                    staging,
                    fd_cache,
                    fd_cache_limit,
                    ownership,
                    completed,
                    failed,
                    scheduler_lock,
                    last_start,
                    pacer_lock,
                )
            except BaseException as exc:
                if failed is not None:
                    if scheduler_lock is None:
                        failed.value = 1
                    else:
                        with scheduler_lock:
                            failed.value = 1
                payload = {
                    "reader": int(reader_id),
                    "pid": int(os.getpid()),
                    "status": "error",
                    "error": f"{type(exc).__name__}:{str(exc)[:400]}",
                    "first_enter_ns": 0,
                    "last_exit_ns": 0,
                    "read_count": 0,
                    "read_bytes": 0,
                    "records": [],
                }
            command_conn.send({
                "command": "LOAD_DONE",
                "generation": request.get("generation"),
                **payload,
            })
    finally:
        _persistent_reader_close_fds(fd_cache)
        try:
            command_conn.close()
        except BaseException:
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
    on_post_fork: Callable[[], None] | None = None,
    on_ready: Callable[[], None] | None = None,
    min_launch_gap_ns: int = 4_000_000,
    requested_gpu: str | None = None,
    observed_gpu: str | None = None,
    clock_ns=None,
    ready_timeout_s: float = 300.0,
    max_idle_s: float = 120.0,
    pacer_start_method: str = "fork",
    diagnostics: bool = True,
    source_offset: int = 0,
    source_size: int | None = None,
) -> dict[str, Any]:
    """Run the frozen M2 source pass with optional benchmark telemetry."""
    import multiprocessing as mp

    del touch_ahead  # M2 production and the frozen mmap arm do not pre-touch.
    if _LIBC is None:
        raise RuntimeError("libc_unavailable")
    if mmap_mode not in ("persistent", "window"):
        raise ValueError("mmap_mode must be persistent or window")
    if consume_mode not in ("memcpy", "d0", "d1", "d2"):
        raise ValueError("consume_mode must be memcpy, d0, d1 or d2")
    if read_bytes < 1 or qd < 1:
        raise ValueError("read_bytes and qd must be positive")
    clock_ns = clock_ns or time.perf_counter_ns
    stat_result = os.stat(file_path)
    full_file_size = int(stat_result.st_size)
    source_offset = int(source_offset)
    file_size = full_file_size - source_offset if source_size is None else int(source_size)
    if source_offset < 0 or file_size < 1 or source_offset + file_size > full_file_size:
        raise ValueError("source range is outside the file")
    total_blocks = (file_size + read_bytes - 1) // read_bytes
    expected_bytes = file_size
    lanes: list[list[int]] = []
    if sticky_lanes:
        base, extra = divmod(total_blocks, qd)
        cursor = 0
        for lane in range(qd):
            count = base + (1 if lane < extra else 0)
            lanes.append(list(range(cursor, cursor + count)))
            cursor += count
    else:
        lanes = [list(range(lane, total_blocks, qd)) for lane in range(qd)]
    lane_flat_list = [block for lane in lanes for block in lane]
    lane_off_list = [0]
    for lane in lanes:
        lane_off_list.append(lane_off_list[-1] + len(lane))
    ctx = mp.get_context(pacer_start_method)
    lock = ctx.Lock()
    ownership = ctx.Array("b", total_blocks, lock=False)
    winner = ctx.Array("i", [-1] * total_blocks, lock=False)
    winner_kind = ctx.Array("b", total_blocks, lock=False)
    start_ns = ctx.Array("q", total_blocks, lock=False)
    winner_exit_ns = ctx.Array("q", total_blocks, lock=False)
    attempts = ctx.Array("i", total_blocks, lock=False)
    read_enter_ns = ctx.Array("q", total_blocks, lock=False)
    read_exit_ns = ctx.Array("q", total_blocks, lock=False)
    staging_wait_ns = ctx.Array("q", [0] * qd, lock=False)
    staging_wait_events = ctx.Array("i", [0] * qd, lock=False)
    worker_status = ctx.Array("b", [0] * qd, lock=False)
    completed = ctx.Value("i", 0, lock=False)
    next_global = ctx.Value("q", 0, lock=False)
    last_start = ctx.Value("q", 0)
    pacer_lock = last_start.get_lock()
    consumer_pos = ctx.Array("i", [-1] * qd, lock=False)
    touch_pos = ctx.Array("i", [0] * qd, lock=False)
    lane_flat = ctx.Array("i", lane_flat_list, lock=False)
    lane_off = ctx.Array("i", lane_off_list, lock=False)
    ready_count = ctx.Value("i", 0, lock=False)
    go = ctx.Value("i", 0, lock=False)
    processes: list[Any] = []
    connections: list[Any] = []
    started = time.perf_counter()
    for reader_id in range(qd):
        parent_conn, child_conn = ctx.Pipe(duplex=False) if diagnostics else (None, None)
        process = cast(Any, ctx).Process(
            target=_reader,
            args=((
                reader_id, file_path, file_size, read_bytes, mmap_mode, consume_mode,
                source_offset, 0, lane_flat, lane_off, qd, sticky_lanes,
                ownership, winner, winner_kind, start_ns, winner_exit_ns, attempts,
                completed, lock, next_global, last_start, pacer_lock,
                min_launch_gap_ns, total_blocks, max_idle_s, consumer_pos, touch_pos,
                ready_count, go, child_conn, staging, diagnostics, worker_status,
                read_enter_ns, read_exit_ns, staging_wait_ns, staging_wait_events,
            ),),
            daemon=True,
        )
        process.start()
        if child_conn is not None:
            child_conn.close()
        if parent_conn is not None:
            connections.append(parent_conn)
        processes.append(process)
    if on_post_fork is not None:
        on_post_fork()
    fork_done = time.perf_counter()
    deadline = time.monotonic() + ready_timeout_s
    barrier_error = None
    release_ns = None
    try:
        while int(ready_count.value) < qd:
            if any(not process.is_alive() for process in processes):
                raise RuntimeError("reader_died_during_setup")
            if time.monotonic() > deadline:
                raise TimeoutError("readers_not_ready")
            time.sleep(0.002)
        ready_done = time.perf_counter()
        if on_ready is not None:
            on_ready()
        release_ns = int(clock_ns())
        go.value = 1
        source_release_done = time.perf_counter()
    except BaseException as exc:
        barrier_error = f"{type(exc).__name__}:{str(exc)[:200]}"
        ready_done = time.perf_counter()
        source_release_done = ready_done
    for process in processes:
        process.join(timeout=30.0 if barrier_error else ready_timeout_s)
        if process.is_alive():
            process.terminate()
            process.join(timeout=30.0)
    join_done = time.perf_counter()
    payloads: list[dict[str, Any]] = []
    if diagnostics:
        for reader_id, connection in enumerate(connections):
            try:
                payloads.append(connection.recv())
            except BaseException as exc:
                payloads.append({"reader": reader_id, "status": "error", "records": [], "error": str(exc)})
            connection.close()
    records = [record for payload in payloads for record in (payload.get("records") or [])]
    records.sort(key=lambda record: int(record["preadv_enter_ns"]))
    logical: list[dict[str, Any]] = []
    for block_id in range(total_blocks):
        reader_id = int(winner[block_id])
        if reader_id < 0:
            continue
        enter = int(read_enter_ns[block_id])
        exit_ns = int(winner_exit_ns[block_id])
        length = min(read_bytes, file_size - block_id * read_bytes)
        if diagnostics:
            logical.append({
                "worker": reader_id, "block_id": block_id, "offset": block_id * read_bytes,
                "length": length, "accepted": "primary", "bytes_returned": length,
                "logical_enter_ns": enter, "logical_exit_ns": exit_ns,
                "logical_ms": (exit_ns - enter) / 1e6,
            })
    first_enter = min((int(value) for value in read_enter_ns if int(value) > 0), default=0)
    last_exit = max((int(value) for value in winner_exit_ns if int(value) > 0), default=0)
    source_wall_ms = (last_exit - first_enter) / 1e6 if last_exit >= first_enter else 0.0
    completed_blocks = sum(1 for block_id in range(total_blocks) if int(winner[block_id]) >= 0)
    covered_bytes = sum(
        min(read_bytes, file_size - block_id * read_bytes)
        for block_id in range(total_blocks)
        if int(winner[block_id]) >= 0
    )
    contiguous = completed_blocks == total_blocks
    coverage = {
        "expected_bytes": expected_bytes, "completed_bytes": covered_bytes,
        "file_size": file_size, "bytes_match": covered_bytes == expected_bytes == file_size,
        "blocks_expected": total_blocks, "blocks_completed": completed_blocks,
        "all_blocks_published_once": all(int(attempts[index]) >= 1 and int(winner[index]) >= 0 for index in range(total_blocks)),
        "no_overlap": contiguous, "contiguous_cover": contiguous,
        "all_reads_returned_full_length": completed_blocks == total_blocks,
        "covers_entire_file_exactly_once": completed_blocks == total_blocks and contiguous and covered_bytes == file_size,
    }
    result: dict[str, Any] = {
        "schema_version": 1, "kind": "mmap_source_probe",
        "config": {
            "file_path": file_path, "read_bytes": read_bytes, "read_mib": read_bytes / 1024 / 1024,
            "qd": qd, "worker_model": "mmap_source", "mmap_mode": mmap_mode,
            "consume_mode": consume_mode, "touch_ahead": 0, "zero_copy": consume_mode != "memcpy",
            "min_launch_gap_ns": min_launch_gap_ns, "min_launch_gap_ms": min_launch_gap_ns / 1e6,
            "total_blocks": total_blocks,
        },
        "env": {"platform": platform.system(), "syscall_impl": f"mmap:{mmap_mode}+{consume_mode}", "multiprocessing_start_method": ctx.get_start_method()},
        "identity": {"requested_gpu": requested_gpu, "observed_gpu": observed_gpu},
        "file_identity": {"path": file_path, "size": file_size, "st_dev": getattr(stat_result, "st_dev", None), "st_ino": getattr(stat_result, "st_ino", None), "st_mtime_ns": getattr(stat_result, "st_mtime_ns", None)},
        "worker_model": "mmap_source", "mmap_mode": mmap_mode,
        "payload_copy_bytes": sum(int(payload.get("payload_copy_bytes") or 0) for payload in payloads),
        "payload_copy_bytes_per_block": 0.0 if consume_mode != "memcpy" else read_bytes,
        "dest_allocated": any(bool(payload.get("dest_allocated")) for payload in payloads),
        "staging": {
            "enabled": staging is not None, "slots": int(staging["slots"]) if staging is not None else 0,
            "bytes": int(staging["bytes"]) if staging is not None else 0,
            "wait_ms_total": sum(float(payload.get("staging_wait_ms") or 0) for payload in payloads),
            "wait_events_total": sum(int(payload.get("staging_wait_events") or 0) for payload in payloads),
            "published_total": sum(int(payload.get("staging_published") or 0) for payload in payloads),
            "reader_wait_ms": [float(payload.get("staging_wait_ms") or 0) for payload in payloads],
            "reader_published": [int(payload.get("staging_published") or 0) for payload in payloads],
            "wait_ms_total_shared": sum(int(value) for value in staging_wait_ns) / 1e6,
            "wait_events_total_shared": sum(int(value) for value in staging_wait_events),
            "reader_wait_ms_shared": [int(value) / 1e6 for value in staging_wait_ns],
            "reader_wait_events_shared": [int(value) for value in staging_wait_events],
        },
        "timing": {
            "pre_fork_ms": (started - started) * 1000.0, "fork_ms": (fork_done - started) * 1000.0,
            "ready_ms": (ready_done - fork_done) * 1000.0,
            "on_ready_ms": (source_release_done - ready_done) * 1000.0,
            "join_ms": (join_done - source_release_done) * 1000.0,
            "collect_ms": 0.0,
        },
        "parent_pid": os.getpid(), "worker_pids": [int(process.pid or 0) for process in processes],
        "reader_pids": [payload.get("pid") for payload in payloads], "barrier_release_ns": release_ns,
        "barrier_error": barrier_error,
        "worker_errors": [{"reader": index, "error": "reader_failed"} for index, status in enumerate(worker_status) if int(status) != 0],
        "physical_reads": completed_blocks, "physical_attempts": len(records) if diagnostics else completed_blocks,
        "physical_amplification": (len(records) / total_blocks) if diagnostics and total_blocks else 1.0,
        "stale_duplicates": sum(int(payload.get("stale") or 0) for payload in payloads),
        "useful_bytes": covered_bytes, "covered_bytes": covered_bytes,
        "full_file_wall_ms": source_wall_ms,
        "source_first_enter_ns": first_enter,
        "source_last_exit_ns": last_exit,
        "reader_timing": [
            {
                "reader": reader_id,
                "first_enter_ns": min(
                    (int(read_enter_ns[index]) for index in range(total_blocks)
                     if int(winner[index]) == reader_id and int(read_enter_ns[index]) > 0),
                    default=0,
                ),
                "last_exit_ns": max(
                    (int(winner_exit_ns[index]) for index in range(total_blocks)
                     if int(winner[index]) == reader_id),
                    default=0,
                ),
                "busy_ms": sum(
                    (int(read_exit_ns[index]) - int(read_enter_ns[index])) / 1e6
                    for index in range(total_blocks) if int(winner[index]) == reader_id
                ),
                "blocks": sum(1 for index in range(total_blocks) if int(winner[index]) == reader_id),
            }
            for reader_id in range(qd)
        ],
        "full_file_decimal_gbps": (covered_bytes / (source_wall_ms / 1000.0) / 1e9) if source_wall_ms else None,
        "coverage": coverage, "scheduler": {"selfservice": True, "max_physical_qd_observed": qd, "max_physical_qd_structural": qd, "sticky_lanes": bool(sticky_lanes), "lane_sizes": [len(lane) for lane in lanes], "affinity_breaks": 0},
        "pacer": {"configured_min_gap_ms": min_launch_gap_ns / 1e6, "observed_min_global_claim_gap_ms": None},
        "launch_spacing": {"configured_min_gap_ms": min_launch_gap_ns / 1e6, "mean_effective_concurrency": None, "max_simultaneous_in_flight": qd},
        "logical_reads": logical if diagnostics else [], "reads": logical if diagnostics else [],
        "physical_attempts_log": records if diagnostics else [], "allocator_dispatches": [], "touch_events": [], "touch_relationship": [],
    }
    return result


__all__ = ["run_mmap_source_probe"]
