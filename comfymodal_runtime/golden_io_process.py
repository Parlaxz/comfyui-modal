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

Control IPC preserves genuine source QD: the Golden transport submits reads from
several producer threads.  A single IPC-dispatcher thread is the sole owner of
the Pipe (thread-safe framing); producers submit request-ID-tagged requests and
wait on their own reply.  The child executes multiple source reads concurrently
(a bounded thread pool) so outstanding child source requests can exceed one.

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
IO_MAX_INFLIGHT = IO_SLOTS


def io_process_enabled() -> bool:
    """Return True only when the experimental I/O-process switch is ON."""
    return str(os.environ.get(IO_PROCESS_ENV) or "").strip().lower() in _TRUTHY


def _safe_fileno(conn: Any) -> Optional[int]:
    try:
        return int(conn.fileno())
    except Exception:
        return None


def _proc_start_ticks(pid: Optional[int]) -> Optional[int]:
    """Linux /proc start-ticks identity (survival accounting). None elsewhere."""
    if not pid:
        return None
    try:
        with open(f"/proc/{int(pid)}/stat", "r") as fh:
            return int(fh.read().split()[21])
    except Exception:
        return None


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


# ── child (stdlib only; CUDA-sterile) ─────────────────────────────────────────


def _io_child_entry(conn: Any, shm_name: str, slot_count: int, slot_bytes: int) -> None:
    """Spawn child entry: serve storage reads concurrently + lifecycle probes.

    Storage reads run on a bounded thread pool so multiple parent producers can
    have outstanding source reads at once.  A single send lock keeps reply
    framing thread-safe.  Imports only the standard library; never touches CUDA.
    """
    import concurrent.futures
    from multiprocessing import shared_memory

    shm = shared_memory.SharedMemory(name=shm_name)
    buf = shm.buf
    canary = b"io-ring-canary"
    # Pre-capture canary used only to test whether the segment survives the
    # snapshot (14 bytes; negligible dirt relative to an 8x32MiB ring).
    try:
        memoryview(buf)[0 : len(canary)] = canary
    except Exception:
        pass
    cuda_initialized = False
    cuda_tasks_run = 0
    gpu_alloc_bytes = 0
    send_lock = threading.Lock()

    def _send(msg: dict) -> None:
        with send_lock:
            conn.send(msg)

    def _do_read(msg: dict) -> None:
        path = str(msg["path"])
        offset = int(msg["offset"])
        length = int(msg["length"])
        slot = int(msg["slot"])
        req_id = msg.get("req_id")
        if slot < 0 or slot >= slot_count or length < 0 or length > slot_bytes:
            _send({"op": "error", "kind": "read", "req_id": req_id,
                   "error": "io_read_bounds"})
            return
        started_ns = time.perf_counter_ns()
        try:
            target = memoryview(buf)[slot * slot_bytes: slot * slot_bytes + length]
            got = 0
            with open(path, "rb", buffering=0) as fh:
                fd = fh.fileno()
                while got < length:
                    n = _pread_into(fd, target, offset + got, length - got)
                    if n <= 0:
                        break
                    got += n
        except BaseException as exc:  # noqa: BLE001 - surface, then fail closed
            _send({"op": "error", "kind": "read", "req_id": req_id,
                   "error": f"{type(exc).__name__}: {exc}"[:300]})
            return
        _send({
            "op": "ready",
            "req_id": req_id,
            "slot": slot,
            "offset": offset,
            "length": got,
            "pread_ms": round((time.perf_counter_ns() - started_ns) / 1e6, 3),
        })

    pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=max(4, slot_count), thread_name_prefix="io-read"
    )
    try:
        while True:
            try:
                msg = conn.recv()
            except EOFError:
                break
            op = str(msg.get("op") or "")
            if op == "ping":
                _send({
                    "op": "pong",
                    "nonce": msg.get("nonce"),
                    "req_id": msg.get("req_id"),
                    "pid": os.getpid(),
                    "ppid": os.getppid(),
                    "uuid": msg.get("uuid"),
                    "conn_fileno": _safe_fileno(conn),
                    "proc_start_ticks": _proc_start_ticks(os.getpid()),
                    "cuda_initialized": bool(cuda_initialized),
                    "cuda_tasks_run": int(cuda_tasks_run),
                    "gpu_alloc_bytes": int(gpu_alloc_bytes),
                })
            elif op == "shm_check":
                marker = int(msg.get("marker") or 0)
                ok = False
                try:
                    probe = f"io-probe-{marker}-{os.getpid()}".encode()
                    mv = memoryview(buf)
                    mv[0 : len(probe)] = probe
                    ok = bytes(mv[0 : len(probe)]) == probe
                except Exception:
                    ok = False
                _send({"op": "shm_ok", "marker": marker, "req_id": msg.get("req_id"),
                       "canary_ok": bool(ok)})
            elif op == "read":
                pool.submit(_do_read, msg)
            elif op == "exit":
                break
    except BaseException as exc:  # noqa: BLE001 - surface child failure to the parent
        try:
            conn.send({"op": "fatal", "error": f"{type(exc).__name__}: {exc}"[:400]})
        except Exception:
            pass
    finally:
        try:
            pool.shutdown(wait=False)
        except Exception:
            pass
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
        self._proc_start_ticks: Optional[int] = None
        self._conn_fileno: Optional[int] = None
        self._child_fileno: Optional[int] = None
        self._pre_capture: dict = {}
        # ── single-owner IPC dispatcher (preserves genuine source QD) ──
        self._pending: dict[int, dict] = {}
        self._pending_lock = threading.Lock()
        self._submit_q: list[dict] = []
        self._q_cond = threading.Condition()
        self._outstanding = 0
        self._dispatch_stop = threading.Event()
        self._dispatch_thread: Optional[threading.Thread] = None
        self._dispatch_error: str = ""
        # evidence
        self.spawn_count = 0
        self.shared_to_pinned_ms = 0.0
        self.shared_to_pinned_bytes = 0
        self.child_cuda_initialized = False
        self.child_cuda_tasks_run = 0
        self.child_gpu_alloc_bytes = 0
        self.effective_child_source_qd_max = 0
        self.producer_wait_ms_total = 0.0
        self.producer_wait_ms_max = 0.0
        self.child_pread_ms_total = 0.0
        self.child_pread_ms_max = 0.0
        self.child_read_count = 0
        self.child_pread_ms_by_path: dict[str, float] = {}
        self.dispatcher_send_ms = 0.0
        self.dispatcher_recv_ms = 0.0

    @property
    def pid(self) -> Optional[int]:
        return self._pid

    def start(self) -> dict:
        """Spawn the child and allocate the process-shared ring (pre-snapshot).

        Uses ``torch.multiprocessing`` spawn (the proven pre-snapshot lifecycle
        that survives Modal's CPU memory snapshot) with a standard
        ``multiprocessing`` Pipe for control IPC and a stdlib shared-memory ring
        for bulk bytes.  After the spawn handshake a single dispatcher thread
        becomes the sole owner of the Pipe.
        """
        import torch.multiprocessing as _torch_mp
        from multiprocessing import shared_memory

        started = time.perf_counter()
        ctx = _torch_mp.get_context("spawn")
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
        try:
            child_conn.close()
        except Exception:
            pass
        # Direct spawn handshake BEFORE the dispatcher thread starts.
        parent_conn.send({"op": "ping", "uuid": self._uuid})
        if not parent_conn.poll(60.0):
            raise RuntimeError("golden_io_worker_spawn_timeout")
        pong = dict(parent_conn.recv())
        self._proc_start_ticks = _proc_start_ticks(self._pid)
        self._conn_fileno = _safe_fileno(parent_conn)
        self._child_fileno = pong.get("conn_fileno")
        self._pre_capture = {
            "pid": self._pid,
            "uuid": self._uuid,
            "ppid": pong.get("ppid"),
            "conn_fileno": self._conn_fileno,
            "child_fileno": self._child_fileno,
            "proc_start_ticks": self._proc_start_ticks,
            "spawn_count": self.spawn_count,
            "shm_name": self._shm.name,
            "shm_bytes": IO_SLOTS * IO_SLOT_BYTES,
            "spawn_context": "torch.multiprocessing.spawn",
        }
        self._start_dispatcher()
        return {
            **self._pre_capture,
            "slot_count": IO_SLOTS,
            "slot_bytes": IO_SLOT_BYTES,
            "ring_bytes": IO_SLOTS * IO_SLOT_BYTES,
            "startup_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "pong": pong,
        }

    # ── dispatcher ────────────────────────────────────────────────────────
    def _start_dispatcher(self) -> None:
        self._dispatch_stop.clear()
        self._dispatch_error = ""
        self._dispatch_thread = threading.Thread(
            target=self._dispatcher_loop, daemon=True, name="golden-io-dispatcher"
        )
        self._dispatch_thread.start()

    def _fail_all(self, message: str) -> None:
        with self._pending_lock:
            waiters = list(self._pending.values())
            self._pending.clear()
        for waiter in waiters:
            waiter["error"] = message
            waiter["event"].set()

    def _dispatcher_loop(self) -> None:
        """Sole owner of the Pipe: send tagged requests, match tagged replies."""
        while not self._dispatch_stop.is_set():
            with self._q_cond:
                if not self._submit_q:
                    self._q_cond.wait(0.05)
                reqs = list(self._submit_q)
                self._submit_q.clear()
            for req in reqs:
                _t0 = time.perf_counter_ns()
                try:
                    self._conn.send(req)
                except BaseException as exc:  # noqa: BLE001
                    self._dispatch_error = f"{type(exc).__name__}: {exc}"[:200]
                    self._fail_all(self._dispatch_error)
                    return
                self.dispatcher_send_ms += (time.perf_counter_ns() - _t0) / 1e6
                with self._pending_lock:
                    self._outstanding += 1
                    if self._outstanding > self.effective_child_source_qd_max:
                        self.effective_child_source_qd_max = self._outstanding
            try:
                _t0 = time.perf_counter_ns()
                while self._conn.poll(0):
                    reply = self._conn.recv()
                    self.dispatcher_recv_ms += (time.perf_counter_ns() - _t0) / 1e6
                    _t0 = time.perf_counter_ns()
                    if not isinstance(reply, dict):
                        continue
                    if reply.get("op") == "fatal":
                        self._dispatch_error = f"child_fatal:{reply.get('error')}"[:200]
                        self._fail_all(self._dispatch_error)
                        return
                    rid = reply.get("req_id")
                    with self._pending_lock:
                        waiter = self._pending.pop(rid, None)
                        self._outstanding = max(0, self._outstanding - 1)
                    if waiter is not None:
                        if reply.get("op") == "error":
                            waiter["error"] = str(reply.get("error"))
                        else:
                            waiter["reply"] = reply
                        waiter["event"].set()
            except BaseException as exc:  # noqa: BLE001
                self._dispatch_error = f"{type(exc).__name__}: {exc}"[:200]
                self._fail_all(self._dispatch_error)
                return

    def _request(self, op: str, *, timeout_s: float = 600.0, **fields: Any) -> dict:
        """Submit one tagged request and wait for its matching reply."""
        if self._conn is None:
            raise RuntimeError("golden_io_worker_missing")
        with self._lock:
            self._seq += 1
            req_id = self._seq
        waiter = {"event": threading.Event(), "reply": None, "error": None}
        with self._pending_lock:
            self._pending[req_id] = waiter
        req = {"op": op, "req_id": req_id, **fields}
        if op == "read":
            req["path"] = os.path.abspath(req["path"])
        with self._q_cond:
            self._submit_q.append(req)
            self._q_cond.notify()
        if not waiter["event"].wait(float(timeout_s)):
            with self._pending_lock:
                self._pending.pop(req_id, None)
            raise RuntimeError("golden_io_request_timeout")
        if self._dispatch_error:
            raise RuntimeError("golden_io_dispatcher_failed:" + self._dispatch_error)
        if waiter["error"]:
            raise RuntimeError(f"golden_io_{op}_error:{waiter['error']}")
        return waiter["reply"] or {}

    # ── probes (all Pipe access via the dispatcher) ───────────────────────
    def ping(self, *, timeout: float = 5.0) -> dict:
        return self._request("ping", timeout_s=timeout, uuid=self._uuid)

    def probe(self, *, anchor_monotonic_ns: Optional[int] = None, timeout_s: float = 15.0) -> dict:
        """Diagnose A/B/C survival: child, control Pipe, shared ring.

        Never touches the payload read path and never respawns the child.
        """
        pre = dict(getattr(self, "_pre_capture", {}) or {})
        ev: dict = {
            "anchor_monotonic_ns": anchor_monotonic_ns,
            "pre_capture": pre,
            "spawn_count": self.spawn_count,
            "spawn_count_match": self.spawn_count == int(pre.get("spawn_count") or -1),
        }
        alive = bool(self._proc is not None and self._proc.is_alive())
        pid = self._pid
        exists = None
        if pid:
            try:
                os.kill(int(pid), 0)
                exists = True
            except Exception:
                exists = False
        ev.update({
            "A_child_is_alive": alive,
            "A_child_pid": pid,
            "A_child_exists_os_kill0": exists,
            "A_child_exitcode": self._proc.exitcode if self._proc is not None else None,
            "A_proc_start_ticks_now": _proc_start_ticks(pid),
        })
        if not alive or not exists:
            ev.update({"A_child_alive": False, "ok": False, "error": "child_dead"})
            return ev
        ev["A_child_alive"] = True

        nonce = uuid.uuid4().hex
        try:
            pong = self._request("ping", timeout_s=timeout_s, uuid=self._uuid, nonce=nonce)
        except Exception as exc:  # noqa: BLE001
            ev.update({"B_pipe_works": False, "ok": False,
                       "error": f"ping_failed:{type(exc).__name__}:{exc}"[:200]})
            return ev
        if not isinstance(pong, dict) or pong.get("op") != "pong" or pong.get("nonce") != nonce:
            ev.update({"B_pipe_works": False, "ok": False,
                       "error": f"pong_invalid:{str(pong)[:160]}"})
            return ev
        ev["B_pipe_works"] = True
        ev["B_pipe_fileno_now"] = _safe_fileno(self._conn)
        ev["B_pipe_fileno_pre"] = pre.get("conn_fileno")
        ev["B_pipe_fileno_match"] = ev["B_pipe_fileno_now"] == pre.get("conn_fileno")
        ev["child"] = {
            key: pong.get(key)
            for key in ("pid", "ppid", "uuid", "conn_fileno", "proc_start_ticks",
                        "cuda_initialized", "cuda_tasks_run", "gpu_alloc_bytes")
        }
        ev["pid_match"] = pong.get("pid") == pre.get("pid")
        ev["uuid_match"] = pong.get("uuid") == self._uuid
        ev["proc_start_ticks_match"] = pong.get("proc_start_ticks") == pre.get("proc_start_ticks")
        ev["child_fileno_match"] = pong.get("conn_fileno") == pre.get("child_fileno")
        ev["child_ppid_is_parent"] = pong.get("ppid") == os.getpid()

        parent_ok = False
        try:
            probe = f"io-probe-parent-{os.getpid()}".encode()
            mv = memoryview(self._shm.buf)
            mv[0 : len(probe)] = probe
            parent_ok = bytes(mv[0 : len(probe)]) == probe
        except Exception as exc:  # noqa: BLE001
            ev["C_parent_shm_error"] = f"{type(exc).__name__}:{exc}"[:160]
        ev["C_parent_shm_ok"] = bool(parent_ok)
        try:
            stat = os.stat(f"/dev/shm/{pre.get('shm_name')}")
            ev["C_dev_shm_present"] = True
            ev["C_dev_shm_size"] = int(stat.st_size)
        except Exception:
            ev["C_dev_shm_present"] = False
        child_ok = False
        try:
            reply = self._request("shm_check", timeout_s=timeout_s, marker=1)
            child_ok = bool(reply.get("op") == "shm_ok" and reply.get("canary_ok"))
        except Exception as exc:  # noqa: BLE001
            ev["C_child_shm_error"] = f"{type(exc).__name__}:{exc}"[:160]
        ev["C_child_shm_ok"] = bool(child_ok)

        self.child_cuda_initialized = bool(pong.get("cuda_initialized"))
        self.child_cuda_tasks_run = int(pong.get("cuda_tasks_run") or 0)
        self.child_gpu_alloc_bytes = int(pong.get("gpu_alloc_bytes") or 0)
        ev["ok"] = bool(
            ev["A_child_alive"]
            and ev["B_pipe_works"]
            and ev["pid_match"]
            and ev["uuid_match"]
            and ev["proc_start_ticks_match"]
            and ev["child_fileno_match"]
            and parent_ok
            and child_ok
        )
        return ev

    # ── staged source fill ────────────────────────────────────────────────
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

        Producers submit concurrently; the dispatcher owns Pipe framing and the
        child executes reads on a thread pool, so genuine source QD is preserved.
        The pinned arena, the H2D backend and model construction are unchanged.
        """
        length = len(target)
        if length == 0:
            return 0
        if length > IO_SLOT_BYTES:
            raise RuntimeError(f"golden_io_read_exceeds_slot:{length}>{IO_SLOT_BYTES}")
        slot = self._acquire_slot()
        try:
            submit_ns = time.perf_counter_ns()
            reply = self._request(
                "read", path=path, offset=int(offset), length=int(length), slot=int(slot)
            )
            wait_ms = (time.perf_counter_ns() - submit_ns) / 1e6
            self.producer_wait_ms_total += wait_ms
            if wait_ms > self.producer_wait_ms_max:
                self.producer_wait_ms_max = wait_ms
            got = int(reply.get("length") or 0)
            if got <= 0:
                raise RuntimeError("golden_io_short_read_zero")
            copy_started = time.perf_counter_ns()
            src = memoryview(self._shm.buf)[slot * IO_SLOT_BYTES: slot * IO_SLOT_BYTES + got]
            target[:got] = src
            self.shared_to_pinned_ms += (time.perf_counter_ns() - copy_started) / 1e6
            self.shared_to_pinned_bytes += got
            pread_ms = float(reply.get("pread_ms") or 0.0)
            self.child_pread_ms_total += pread_ms
            self.child_read_count += 1
            if pread_ms > self.child_pread_ms_max:
                self.child_pread_ms_max = pread_ms
            stem = os.path.basename(str(path))
            self.child_pread_ms_by_path[stem] = (
                self.child_pread_ms_by_path.get(stem, 0.0) + pread_ms
            )
            return got
        finally:
            self._release_slot(slot)

    def stop(self) -> dict:
        out: dict = {"pid": self._pid}
        self._dispatch_stop.set()
        with self._q_cond:
            self._q_cond.notify_all()
        if self._dispatch_thread is not None:
            self._dispatch_thread.join(timeout=5.0)
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


def io_process_probe(*, anchor_monotonic_ns: Optional[int] = None) -> dict:
    """Diagnose A/B/C survival of the pre-snapshot I/O worker (fail-closed)."""
    worker = _PRE_SNAPSHOT_IO
    if worker is None:
        return {"ok": False, "error": "io_worker_missing"}
    try:
        return worker.probe(anchor_monotonic_ns=anchor_monotonic_ns)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}


def io_process_evidence() -> dict:
    worker = _PRE_SNAPSHOT_IO
    if worker is None:
        return {"active": False}
    count = int(worker.child_read_count or 0)
    return {
        "active": True,
        "pid": worker.pid,
        "spawn_count": worker.spawn_count,
        "child_cuda_initialized": worker.child_cuda_initialized,
        "child_cuda_tasks_run": worker.child_cuda_tasks_run,
        "child_gpu_alloc_bytes": worker.child_gpu_alloc_bytes,
        "effective_child_source_qd_max": int(worker.effective_child_source_qd_max),
        "child_read_count": count,
        "child_pread_ms_total": round(worker.child_pread_ms_total, 3),
        "child_pread_ms_max": round(worker.child_pread_ms_max, 3),
        "child_pread_ms_mean": round(worker.child_pread_ms_total / count, 3) if count else None,
        "child_pread_ms_by_path": {
            k: round(v, 3) for k, v in sorted(worker.child_pread_ms_by_path.items())
        },
        "producer_wait_ms_total": round(worker.producer_wait_ms_total, 3),
        "producer_wait_ms_max": round(worker.producer_wait_ms_max, 3),
        "dispatcher_send_ms": round(worker.dispatcher_send_ms, 3),
        "dispatcher_recv_ms": round(worker.dispatcher_recv_ms, 3),
        "shared_to_pinned_ms": round(worker.shared_to_pinned_ms, 3),
        "shared_to_pinned_bytes": int(worker.shared_to_pinned_bytes),
        "shared_to_pinned_GBps": round(
            (worker.shared_to_pinned_bytes / 1e9) / (worker.shared_to_pinned_ms / 1e3), 3
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
    "io_process_probe",
    "io_process_readinto",
    "io_worker_record",
    "maybe_spawn_io_worker",
]
