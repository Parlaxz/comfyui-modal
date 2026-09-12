"""Strict CPU-I/O-only persistent worker for Golden Parallel (experimental).

The child process performs storage reads only: it ``pread``s model payload into
a bounded process-shared CPU ring and publishes READY metadata.  The parent
copies shared bytes into the *existing* pinned staging slot and keeps the
canonical H2D backend and Golden model construction.

The child is deliberately CUDA-sterile: it imports only the Python standard
library (no ``torch``), never initializes CUDA, never allocates GPU memory,
never constructs models, and never performs H2D.  GPU visibility variables are
not forwarded to it.

Default OFF: ``COMFYMODAL_GOLDEN_IO_PROCESS=0``.

Lifecycle (pre-snapshot persistence, control IPC, survival accounting) mirrors
the proven loader-process worker, but ownership of CUDA/H2D/model stays in the
parent.  This module reuses no GPU ownership.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any, Optional

IO_PROCESS_ENV = "COMFYMODAL_GOLDEN_IO_PROCESS"
_TRUTHY = {"1", "true", "yes", "on"}

# Bounded ring geometry.  Initial experiment deliberately matches the existing
# Golden transport geometry (8 slots x 32 MiB) instead of a model-sized backing.
IO_SLOTS = 8
IO_SLOT_BYTES = 32 * 1024 * 1024


def io_process_enabled() -> bool:
    """Return True only when the experimental I/O-process switch is ON."""
    return str(os.environ.get(IO_PROCESS_ENV) or "").strip().lower() in _TRUTHY


# ── child (stdlib only; CUDA-sterile) ─────────────────────────────────────────


def _pread_into(fd: int, target: memoryview, offset: int, length: int) -> int:
    """Read *length* bytes at *offset* directly into *target*; return bytes read.

    Uses ``os.preadv`` (scatter read straight into the shared buffer, no extra
    copy) on Linux; falls back to ``os.pread`` + slice assignment elsewhere.
    """
    preadv = getattr(os, "preadv", None)
    if callable(preadv):
        return int(preadv(fd, [target[:length]], offset))
    pread = getattr(os, "pread", None)
    if callable(pread):
        chunk = pread(fd, length, offset)
        target[: len(chunk)] = chunk
        return len(chunk)
    # Windows local validation fallback: positional reads are unavailable, so
    # use lseek+read on this single-threaded child fd, restoring the cursor.
    saved = os.lseek(fd, 0, os.SEEK_CUR)
    os.lseek(fd, offset, os.SEEK_SET)
    data = os.read(fd, length)
    target[: len(data)] = data
    os.lseek(fd, saved, os.SEEK_SET)
    return len(data)


def _io_child_entry(conn: Any, shm_name: str, slot_count: int, slot_bytes: int) -> None:
    """Spawn child entry: serve strict storage reads and lifecycle probes.

    Imports only the standard library.  Never imports torch, never touches CUDA.
    """
    from multiprocessing import shared_memory

    shm = shared_memory.SharedMemory(name=shm_name)
    buf = shm.buf
    cuda_initialized = False
    cuda_tasks_run = 0
    gpu_alloc_bytes = 0
    try:
        while True:
            try:
                msg = conn.recv()
            except EOFError:
                break
            op = str(msg.get("op") or "")
            if op == "ping":
                conn.send({
                    "op": "pong",
                    "pid": os.getpid(),
                    "ppid": os.getppid(),
                    "uuid": msg.get("uuid"),
                    "cuda_initialized": bool(cuda_initialized),
                    "cuda_tasks_run": int(cuda_tasks_run),
                    "gpu_alloc_bytes": int(gpu_alloc_bytes),
                })
            elif op == "canary":
                marker = int(msg.get("marker") or 0)
                mv = memoryview(buf)
                mv[0: len(b"io-canary")] = b"io-canary"
                conn.send({"op": "canary_ok", "marker": marker})
            elif op == "read":
                path = str(msg["path"])
                offset = int(msg["offset"])
                length = int(msg["length"])
                slot = int(msg["slot"])
                seq = int(msg["seq"])
                if slot < 0 or slot >= slot_count or length < 0 or length > slot_bytes:
                    conn.send({"op": "error", "kind": "read", "seq": seq,
                               "error": "io_read_bounds"})
                    continue
                target = memoryview(buf)[slot * slot_bytes: slot * slot_bytes + length]
                got = 0
                try:
                    with open(path, "rb", buffering=0) as fh:
                        fd = fh.fileno()
                        while got < length:
                            n = _pread_into(fd, target, offset + got, length - got)
                            if n <= 0:
                                break
                            got += n
                except BaseException as exc:  # noqa: BLE001 - surface, then fail closed
                    conn.send({"op": "error", "kind": "read", "seq": seq,
                               "error": f"{type(exc).__name__}: {exc}"[:300]})
                    continue
                conn.send({
                    "op": "ready",
                    "slot": slot,
                    "offset": offset,
                    "length": got,
                    "seq": seq,
                })
                # Wait for the parent to release the slot before reuse.
                while True:
                    rel = conn.recv()
                    if str(rel.get("op")) == "release" and int(rel.get("slot", -1)) == slot:
                        break
            elif op == "exit":
                break
    finally:
        try:
            buf.release()
        except Exception:
            pass
        try:
            shm.close()
        except Exception:
            pass


# ── parent ────────────────────────────────────────────────────────────────────


class GoldenIoProcess:
    """Parent handle for the persistent CPU-I/O worker (no GPU ownership)."""

    def __init__(self) -> None:
        self._ctx = None
        self._proc = None
        self._conn = None
        self._shm = None
        self._pid: Optional[int] = None
        self._uuid = uuid.uuid4().hex
        self._seq = 0
        self._lock = threading.Lock()
        self._free: list[int] = list(range(IO_SLOTS))
        self._slot_cond = threading.Condition()
        # evidence
        self.spawn_count = 0
        self.shared_to_pinned_ms = 0.0
        self.shared_to_pinned_bytes = 0
        self.child_cuda_initialized = False
        self.child_cuda_tasks_run = 0
        self.child_gpu_alloc_bytes = 0

    @property
    def pid(self) -> Optional[int]:
        return self._pid

    def start(self) -> dict:
        """Spawn the child and allocate the process-shared ring (pre-snapshot)."""
        from multiprocessing import get_context, shared_memory

        started = time.perf_counter()
        ctx = get_context("spawn")
        self._ctx = ctx
        self._shm = shared_memory.SharedMemory(create=True, size=IO_SLOTS * IO_SLOT_BYTES)
        parent_conn, child_conn = ctx.Pipe(duplex=True)
        proc = ctx.Process(
            target=_io_child_entry,
            args=(child_conn, self._shm.name, IO_SLOTS, IO_SLOT_BYTES),
            daemon=True,
            name="golden-io-worker",
        )
        proc.start()
        self._proc = proc
        self._conn = parent_conn
        self._pid = proc.pid
        self.spawn_count = getattr(self, "spawn_count", 0) + 1
        # Handshake so a dead-at-spawn child fails closed immediately.
        try:
            child_conn.close()
        except Exception:
            pass
        pong = self.ping(timeout=30.0)
        return {
            "pid": self._pid,
            "uuid": self._uuid,
            "shm_name": self._shm.name,
            "slot_count": IO_SLOTS,
            "slot_bytes": IO_SLOT_BYTES,
            "ring_bytes": IO_SLOTS * IO_SLOT_BYTES,
            "startup_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "pong": pong,
        }

    def ping(self, *, timeout: float = 5.0) -> dict:
        self._conn.send({"op": "ping", "uuid": self._uuid})
        if not self._conn.poll(timeout):
            raise RuntimeError("golden_io_worker_ping_timeout")
        return dict(self._conn.recv())

    def probe(self, *, anchor_monotonic_ns: Optional[int] = None) -> dict:
        """Prove the same child + IPC + shared ring survived snapshot restore."""
        started = time.monotonic_ns()
        pong = self.ping(timeout=10.0)
        # Shared-memory round trip: write the canary again and confirm readiness.
        self._conn.send({"op": "canary", "marker": 1})
        canary_ok = bool(self._conn.poll(10.0)) and dict(self._conn.recv()).get("op") == "canary_ok"
        self.child_cuda_initialized = bool(pong.get("cuda_initialized"))
        self.child_cuda_tasks_run = int(pong.get("cuda_tasks_run") or 0)
        self.child_gpu_alloc_bytes = int(pong.get("gpu_alloc_bytes") or 0)
        return {
            "ok": bool(canary_ok),
            "pid": pong.get("pid"),
            "pid_match": int(pong.get("pid") or -1) == int(self._pid or -2),
            "uuid_match": pong.get("uuid") == self._uuid,
            "pong_ms": round((time.monotonic_ns() - started) / 1e6, 3),
            "canary_ok": canary_ok,
            "child_cuda_initialized": self.child_cuda_initialized,
            "child_cuda_tasks_run": self.child_cuda_tasks_run,
            "child_gpu_alloc_bytes": self.child_gpu_alloc_bytes,
            "spawn_count": self.spawn_count,
        }

    def _acquire_slot(self) -> int:
        with self._slot_cond:
            while not self._free:
                self._slot_cond.wait()
            return self._free.pop()

    def _release_slot(self, slot: int) -> None:
        with self._slot_cond:
            if slot not in self._free:
                self._free.append(slot)
            self._slot_cond.notify()

    def readinto(self, path: str, target: Any, offset: int, producer_id: int) -> int:
        """Child pread into a shared slot, then parent memcpy shared -> target.

        ``target`` is the existing pinned staging slot view supplied by the
        canonical Golden producer.  This is the only injected step; the pinned
        arena, the H2D backend and model construction are unchanged.
        """
        length = len(target)
        if length == 0:
            return 0
        if length > IO_SLOT_BYTES:
            raise RuntimeError(f"golden_io_read_exceeds_slot:{length}>{IO_SLOT_BYTES}")
        slot = self._acquire_slot()
        try:
            with self._lock:
                self._seq += 1
                seq = self._seq
            self._conn.send({
                "op": "read",
                "path": os.path.abspath(path),
                "offset": int(offset),
                "length": int(length),
                "slot": int(slot),
                "seq": seq,
            })
            if not self._conn.poll(600.0):
                raise RuntimeError("golden_io_read_timeout")
            reply = dict(self._conn.recv())
            if reply.get("op") == "error":
                raise RuntimeError(f"golden_io_read_error:{reply.get('error')}")
            if reply.get("op") != "ready" or int(reply.get("seq", -1)) != seq:
                raise RuntimeError("golden_io_read_protocol_error")
            got = int(reply.get("length") or 0)
            if got <= 0:
                raise RuntimeError("golden_io_short_read_zero")
            copy_started = time.perf_counter_ns()
            src = memoryview(self._shm.buf)[slot * IO_SLOT_BYTES: slot * IO_SLOT_BYTES + got]
            target[:got] = src
            self.shared_to_pinned_ms += (time.perf_counter_ns() - copy_started) / 1e6
            self.shared_to_pinned_bytes += got
            return got
        finally:
            try:
                self._conn.send({"op": "release", "slot": int(slot)})
            finally:
                self._release_slot(slot)

    def stop(self) -> dict:
        out: dict = {"pid": self._pid}
        try:
            if self._conn is not None:
                self._conn.send({"op": "exit"})
        except Exception as exc:  # noqa: BLE001
            out["stop_error"] = f"{type(exc).__name__}: {exc}"[:200]
        try:
            if self._proc is not None:
                self._proc.join(timeout=10.0)
                if self._proc.is_alive():
                    self._proc.terminate()
        except Exception:
            pass
        for closable in (self._conn, self._shm):
            if closable is self._shm:
                try:
                    self._shm.buf.release()
                except Exception:
                    pass
            try:
                if closable is not None:
                    closable.close()
            except Exception:
                pass
        try:
            if self._shm is not None:
                self._shm.unlink()
        except Exception:
            pass
        return out


# ── module-level persistent worker (pre-snapshot lifetime) ────────────────────

_PRE_SNAPSHOT_IO: Optional[GoldenIoProcess] = None
_PRE_SNAPSHOT_IO_RECORD: dict = {}


def get_io_worker() -> Optional[GoldenIoProcess]:
    return _PRE_SNAPSHOT_IO


def io_worker_record() -> dict:
    return dict(_PRE_SNAPSHOT_IO_RECORD)


def maybe_spawn_io_worker() -> dict:
    """Spawn the pre-snapshot I/O worker once (idempotent).  No-op when OFF."""
    global _PRE_SNAPSHOT_IO, _PRE_SNAPSHOT_IO_RECORD
    if not io_process_enabled():
        return {}
    if _PRE_SNAPSHOT_IO is not None and _PRE_SNAPSHOT_IO_RECORD:
        return dict(_PRE_SNAPSHOT_IO_RECORD)
    worker = GoldenIoProcess()
    record = worker.start()
    record["spawn_count"] = worker.spawn_count
    _PRE_SNAPSHOT_IO = worker
    _PRE_SNAPSHOT_IO_RECORD = dict(record)
    print(
        "[v2.golden_io_process] "
        f"event=spawn pid={record.get('pid')} slots={IO_SLOTS} slot_bytes={IO_SLOT_BYTES} "
        f"ring_bytes={record.get('ring_bytes')} startup_ms={record.get('startup_ms')}",
        flush=True,
    )
    return record


def io_process_readinto(path: str, target: Any, offset: int, producer_id: int) -> int:
    """Serve one staged source fill from the child; fail closed if unavailable."""
    worker = _PRE_SNAPSHOT_IO
    if worker is None:
        raise RuntimeError("golden_io_worker_missing")
    return worker.readinto(path, target, offset, producer_id)


def io_process_evidence() -> dict:
    worker = _PRE_SNAPSHOT_IO
    if worker is None:
        return {"active": False}
    return {
        "active": True,
        "pid": worker.pid,
        "spawn_count": worker.spawn_count,
        "child_cuda_initialized": worker.child_cuda_initialized,
        "child_cuda_tasks_run": worker.child_cuda_tasks_run,
        "child_gpu_alloc_bytes": worker.child_gpu_alloc_bytes,
        "shared_to_pinned_ms": round(worker.shared_to_pinned_ms, 3),
        "shared_to_pinned_bytes": int(worker.shared_to_pinned_bytes),
        "shared_to_pinned_GBps": round(
            (worker.shared_to_pinned_bytes / 1e9)
            / (worker.shared_to_pinned_ms / 1e3),
            3,
        )
        if worker.shared_to_pinned_ms > 0
        else None,
    }


__all__ = [
    "IO_PROCESS_ENV",
    "IO_SLOTS",
    "IO_SLOT_BYTES",
    "GoldenIoProcess",
    "get_io_worker",
    "io_process_enabled",
    "io_process_evidence",
    "io_process_readinto",
    "io_worker_record",
    "maybe_spawn_io_worker",
]
