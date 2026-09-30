"""M1-CB: physical source-copy root-cause calibration harness.

DIAGNOSTIC ONLY. Gated by COMFYMODAL_M1B_COPY_PROBE. When the gate is off this
module imports nothing at import time and changes nothing.

The harness runs INSIDE the same container/placement as the production loader so
that every comparison is same-container. It never mutates production-006, never
changes a production mechanic, and never runs on a hot path.

Design constraints honoured:
  * 64 MiB operations, matching the production physical unit exactly.
  * native libc primitives resolved once, never per call.
  * preallocated result lists; no printing inside any timed region.
  * every timed copy is preceded by a warmup and followed by a byte check.
  * all result records are appended to plain lists and serialized once, after
    the last measurement.

Evidence classes used in the emitted payload: DIRECT_MEASUREMENT for anything
this module times itself; UNAVAILABLE_GVISOR when a surface is absent.
"""
from __future__ import annotations

import ctypes
import json
import os
import struct
import time
from typing import Any

MIB = 1 << 20
SLOT_BYTES = 64 * MIB
# mmap(2) constants used by the probe.  PROT_READ is 1, so read/write is 3;
# mapping a destination PROT_READ is a guaranteed SIGSEGV on first write.
_PROT_READ = 1
_PROT_RW = 3
_MAP_PRIVATE = 2
_MAP_PRIVATE_ANON = 0x22  # MAP_PRIVATE | MAP_ANONYMOUS
# Headroom past every probe buffer so the +32 alignment variants, which copy a
# full SLOT_BYTES starting at a 32-byte offset, never read or write past the
# end of their mapping.
_SLACK = MIB
PROBE_ENV = "COMFYMODAL_M1B_COPY_PROBE"
LEVEL_ENV = "COMFYMODAL_M1B_LEVEL"

_LIBC: Any = None
_MEMMOVE: Any = None
_MEMCPY: Any = None
_MEMSET: Any = None
_MEMCMP: Any = None


def enabled() -> bool:
    return str(os.environ.get(PROBE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def level() -> int:
    try:
        return int(str(os.environ.get(LEVEL_ENV) or "1").strip() or 1)
    except ValueError:
        return 1


def _init() -> None:
    """Resolve the libc surface ONCE. ctypes.CDLL releases the GIL per call."""
    global _LIBC, _MEMMOVE, _MEMCPY, _MEMSET, _MEMCMP
    if _LIBC is not None:
        return
    _LIBC = ctypes.CDLL(None, use_errno=True)
    _LIBC.mmap.restype = ctypes.c_void_p
    _LIBC.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, ctypes.c_long]
    _LIBC.munmap.restype = ctypes.c_int
    _LIBC.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    _LIBC.memcmp.restype = ctypes.c_int
    _LIBC.memcmp.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    for name in ("memmove", "memcpy", "memset"):
        fn = getattr(_LIBC, name)
        fn.restype = ctypes.c_void_p
        if name == "memset":
            fn.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]
        else:
            fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    _MEMMOVE, _MEMCPY, _MEMSET = _LIBC.memmove, _LIBC.memcpy, _LIBC.memset
    _MEMCMP = _LIBC.memcmp


# ── small allocation helpers ────────────────────────────────────────────────
def _anon(size: int, *, align: int = 4096) -> int:
    """Anonymous memory, page-aligned, zero-filled by the kernel on first touch.

    PROT_READ|PROT_WRITE (3) is mandatory: every probe buffer is both a copy
    source and a copy destination, and mapping PROT_READ alone segfaults on the
    first write.  That was the cause of every "Server has lost track of input".
    """
    _init()
    extra = align if (size % align) else 0
    addr = _LIBC.mmap(None, ctypes.c_size_t(size + extra), _PROT_RW, _MAP_PRIVATE_ANON, -1, 0)
    if not addr or int(ctypes.cast(addr, ctypes.c_void_p).value or 0) == ctypes.c_void_p(-1).value:
        raise RuntimeError(f"anon_mmap_failed errno={ctypes.get_errno()}")
    return int(ctypes.cast(addr, ctypes.c_void_p).value or 0)


def _file_window(path: str, offset: int, length: int, page: int = 4096) -> tuple[int, int]:
    """Map only ``[offset, offset+length)`` of ``path``, page-aligned down.

    The inline sentinel must NOT whole-file map the model: the production loader
    already holds a Whole mmap of the same safetensors in this process, and a
    second whole-file mapping of an 8 GB CLIP / 12 GB UNET file inside the
    gVisor container is what killed it (InternalFailure, zero telemetry, even
    with four copies).  Windowing keeps the resident cost at one page-rounded
    window while still reading genuinely file-backed pages at the production
    file offset.

    Returns ``(window_addr, delta)`` where ``delta`` is the byte position of
    ``offset`` inside the mapping, so ``window_addr + delta`` addresses the
    exact same file offset with the exact same alignment relationship.
    """
    _init()
    page_start = offset - (offset % page)
    delta = offset - page_start
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        size = os.fstat(fd).st_size
        span = delta + length
        if page_start + span > size:
            raise RuntimeError(f"window_past_eof offset={offset} length={length} size={size}")
        # Read-only source window: PROT_READ | MAP_PRIVATE, address hint NULL
        # (page_start is the file OFFSET, not a usable address).
        addr = _LIBC.mmap(None, ctypes.c_size_t(span),
                          ctypes.c_int(_PROT_READ), ctypes.c_int(_MAP_PRIVATE),
                          ctypes.c_int(fd), ctypes.c_long(page_start))
        if not addr or int(ctypes.cast(addr, ctypes.c_void_p).value or 0) == ctypes.c_void_p(-1).value:
            raise RuntimeError(f"file_window_mmap_failed errno={ctypes.get_errno()}")
        return int(ctypes.cast(addr, ctypes.c_void_p).value or 0), delta
    finally:
        os.close(fd)


def _unmap(addr: int, size: int) -> None:
    _init()
    _LIBC.munmap(ctypes.c_void_p(addr), ctypes.c_size_t(size))


def _shm_map(name: str, size: int) -> int:
    """Shared /dev/shm mapping, same mechanism the production arena uses."""
    path = os.path.join("/dev/shm", name.lstrip("/"))
    fd = os.open(path, os.O_RDWR)
    try:
        import mmap as _mm
        m = _mm.mmap(fd, int(size), access=_mm.ACCESS_WRITE)
        addr = ctypes.addressof(ctypes.c_char.from_buffer(m))
        # keep the mmap object alive via a module-level registry
        _SHM_KEEP.append(m)  # type: ignore[name-defined]
        return int(addr)
    finally:
        os.close(fd)


def _shm_create(name: str, size: int) -> str:
    path = os.path.join("/dev/shm", name.lstrip("/"))
    try:
        os.unlink(path)
    except OSError:
        pass
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.ftruncate(fd, int(size))
    finally:
        os.close(fd)
    return path


_SHM_KEEP: list = []


# ── timing primitives ───────────────────────────────────────────────────────
def _now() -> int:
    return time.monotonic_ns()


_TCPU = hasattr(time, "thread_time_ns")


def _tcpu() -> int:
    return time.thread_time_ns() if _TCPU else 0


def _copy(prim: str, dst: int, src: int, n: int) -> tuple[int, int, int]:
    """One timed primitive call. Returns (wall_ns, thread_cpu_ns, checksum)."""
    fn = _MEMMOVE if prim == "memmove" else _MEMCPY
    c0 = _tcpu()
    t0 = _now()
    fn(ctypes.c_void_p(dst), ctypes.c_void_p(src), ctypes.c_size_t(n))
    t1 = _now()
    c1 = _tcpu()
    return t1 - t0, c1 - c0, 0


def _memset(dst: int, n: int, val: int = 0xAB) -> tuple[int, int]:
    c0 = _tcpu()
    t0 = _now()
    _MEMSET(ctypes.c_void_p(dst), ctypes.c_int(val), ctypes.c_size_t(n))
    t1 = _now()
    c1 = _tcpu()
    return t1 - t0, c1 - c0


def _checksum(addr: int, n: int, stride: int = 4096) -> int:
    """Sampled integrity check. Proves the copy actually moved bytes.

    Indexing a ``c_char`` array yields a one-byte ``bytes`` object, not an int,
    so the accumulator must be a ``c_ubyte`` array.  (This was a real
    ``int + bytes`` TypeError that aborted the copy phase.)
    """
    _init()
    buf = (ctypes.c_ubyte * n).from_address(addr)
    acc = 0
    for off in range(0, n, stride):
        acc = (acc * 31 + buf[off]) & 0xFFFFFFFF
    acc = (acc * 31 + buf[n - 1]) & 0xFFFFFFFF
    return acc


def _memmove(dst: int, src: int, n: int) -> None:
    """Untimed raw memmove, used only to set up a resident precondition."""
    _init()
    _MEMMOVE(ctypes.c_void_p(dst), ctypes.c_void_p(src), ctypes.c_size_t(n))


def _align_report(addr: int) -> dict:
    return {f"mod{m}": addr % m for m in (16, 32, 64, 128, 256, 4096, SLOT_BYTES)}


def _memcmp(a: int, b: int, n: int) -> bool:
    """Exact whole-range byte equality via libc memcmp.

    A sampled checksum cannot prove a diagnostic copy transferred the right
    bytes, and the task requires exact correctness, so compare every byte.
    """
    rc = _MEMCMP(ctypes.c_void_p(a), ctypes.c_void_p(b), ctypes.c_size_t(n))
    return int(rc) == 0


# ── the harness ─────────────────────────────────────────────────────────────
class CopyProbe:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.meta: dict[str, Any] = {}

    def add(self, **kw) -> None:
        self.rows.append(kw)

    # ---- fingerprint -------------------------------------------------------
    def fingerprint(self) -> None:
        f: dict[str, Any] = {"pid": os.getpid(), "python": __import__("platform").python_version()}
        try:
            _init()
            gv = getattr(_LIBC, "gnu_get_libc_version", None)
            f["glibc_version"] = gv().decode() if gv else "UNAVAILABLE"
        except Exception as exc:
            f["glibc_version"] = f"UNAVAILABLE: {type(exc).__name__}"
        for name, path in (("cpuinfo", "/proc/cpuinfo"), ("uname", "/proc/sys/kernel/osrelease"),
                           ("version", "/proc/version")):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    f[name] = fh.read(16384)
            except Exception as exc:
                f[name] = f"UNAVAILABLE: {type(exc).__name__}"
        # CPU identity fields of interest
        try:
            for line in f.get("cpuinfo", "").splitlines():
                for key in ("vendor_id", "model name", "cpu family", "model", "stepping",
                            "cache size", "cpu MHz", "flags"):
                    if line.lower().startswith(key.lower()):
                        f.setdefault("cpu_" + key.replace(" ", "_"), line.split(":", 1)[-1].strip())
        except Exception:
            pass
        _getaff = getattr(os, "sched_getaffinity", None)
        try:
            f["affinity_cpus"] = len(_getaff(0)) if _getaff else None
        except Exception as exc:
            f["affinity_cpus"] = f"UNAVAILABLE: {type(exc).__name__}"
        _getcpu = getattr(os, "sched_getcpu", None)
        f["sched_getcpu_present"] = _getcpu is not None
        for env in ("MODAL_CLOUD_PROVIDER", "MODAL_REGION", "MODAL_TASK_ID", "MODAL_ENVIRONMENT"):
            f[env] = os.environ.get(env)
        # IFUNC evidence: are memcpy/memmove/memset distinct addresses?
        try:
            addrs = {}
            for nm in ("memcpy", "memmove", "memset", "memcmp"):
                fn = getattr(_LIBC, nm)
                addrs[nm] = hex(ctypes.cast(fn, ctypes.c_void_p).value or 0)
            f["libc_symbol_addrs"] = addrs
            f["memmove_eq_memcpy"] = addrs["memmove"] == addrs["memcpy"]
        except Exception as exc:
            f["libc_symbol_addrs"] = f"UNAVAILABLE: {type(exc).__name__}"
        # dlsym/dladdr
        try:
            libdl = ctypes.CDLL("libdl.so.2", use_errno=True)
            libdl.dlsym.restype = ctypes.c_void_p
            libdl.dlsym.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            h = ctypes.c_void_p(ctypes.cast(_LIBC, ctypes.c_void_p).value or 0)
            f["dlsym_memcpy"] = hex(libdl.dlsym(h, b"memcpy") or 0)
            f["dlsym_memmove"] = hex(libdl.dlsym(h, b"memmove") or 0)
        except Exception as exc:
            f["dlsym"] = f"UNAVAILABLE: {type(exc).__name__}: {exc}"
        self.meta["fingerprint"] = f

    # ---- timing helper -----------------------------------------------------
    def _time_copy(self, tag: str, prim: str, dst: int, src: int, n: int,
                   *, reps: int = 3, verify: bool = True, **extra) -> dict:
        """Time `reps` copies; report each. First rep is separately identified."""
        walls, cpus, sums = [], [], []
        for i in range(reps):
            w, c, _ = _copy(prim, dst, src, n)
            walls.append(w)
            cpus.append(c)
            if verify:
                sums.append(_checksum(dst, n))
        rec: dict[str, Any] = dict(tag=tag, prim=prim, nbytes=n, reps=reps,
                   wall_ns=walls, cpu_ns=cpus,
                   first_wall_ns=walls[0], repeat_wall_ns=walls[1:],
                   first_gbps=n / (walls[0] / 1e9),
                   repeat_median_gbps=(n / (sorted(walls[1:])[len(walls[1:]) // 2] / 1e9)
                                       if len(walls) > 1 else None),
                   cpu_wall_ratio=(sum(cpus) / sum(walls)) if sum(walls) else None,
                   dst=_align_report(dst), src=_align_report(src),
                   rel_mod64=(src - dst) % 64, rel_mod4096=(src - dst) % 4096)
        if verify:
            rec["checksums"] = sums
            rec["checksum_stable"] = len(set(sums[1:])) <= 1 if len(sums) > 1 else None
        rec.update(extra)
        self.add(**rec)
        return rec

    def _time_memset(self, tag: str, dst: int, n: int, *, reps: int = 3, **extra) -> dict:
        walls, cpus = [], []
        for _ in range(reps):
            w, c = _memset(dst, n)
            walls.append(w)
            cpus.append(c)
        rec = dict(tag=tag, prim="memset", nbytes=n, reps=reps, wall_ns=walls, cpu_ns=cpus,
                   first_wall_ns=walls[0], first_gbps=n / (walls[0] / 1e9),
                   dst=_align_report(dst), src=None)
        rec.update(extra)
        self.add(**rec)
        return rec

    # ---- phase 7: thread scaling ------------------------------------------
    def thread_scaling(self, n: int) -> None:
        """Fan one 64 MiB block across 1..4 threads.

        Each thread owns a disjoint ``n``-byte slice, so this arm needs
        ``4 * n`` of source and of destination per destination kind.  The
        single-slot buffers used by the serial matrix are far too small here and
        would fault, so this arm allocates its own widest-case regions.
        """
        import threading
        width = 4 * n + _SLACK
        src = _anon(width)
        _memset(src, width)
        scale_shm = "m1cb_probe_shm_scaling"
        _shm_create(scale_shm, width)
        dests = {"anon_private": _anon(width),
                 "shm_unregistered": _shm_map(scale_shm, width)}
        for dptr in dests.values():
            _memset(dptr, width)
        for label, base in dests.items():
            for nthreads in (1, 2, 3, 4):
                bar = threading.Barrier(nthreads)
                out: list = [0] * nthreads
                cpu: list = [0] * nthreads

                def work(i: int) -> None:
                    bar.wait()
                    c0 = _tcpu()
                    t0 = _now()
                    _MEMMOVE(ctypes.c_void_p(base + i * n), ctypes.c_void_p(src + i * n),
                             ctypes.c_size_t(n))
                    t1 = _now()
                    out[i] = t1 - t0
                    cpu[i] = _tcpu() - c0

                ths = [threading.Thread(target=work, args=(i,), daemon=True) for i in range(nthreads)]
                for t in ths:
                    t.start()
                for t in ths:
                    t.join(120)
                slowest = max(out)
                self.add(tag="thread_scaling", prim="memmove", nbytes=n, nthreads=nthreads,
                          dest_kind=label, wall_ns=out, cpu_ns=cpu,
                          span_wall_ns=slowest,
                          per_thread_gbps=[n / (w / 1e9) if w else None for w in out],
                          aggregate_gbps=(nthreads * n) / (slowest / 1e9) if slowest else None,
                          dst=_align_report(base), src=_align_report(src))

    # ---- minimal inline sentinel (level 1) --------------------------------
    def sentinel(self, model_paths: dict, n: int, result: dict) -> None:
        """Tiny post-load correlation probe.

        Purpose is only to link this container's copy condition to the real
        CLIP/UNET load that just finished, so it copies four 64 MiB blocks and
        nothing more.  S1 and S2 target *independent* destinations so the
        repeat cannot inherit first-touch cost from an already-dirty one, and
        S3 is the anonymous control that separates "file-backed service is
        slow" from "raw memory copy is slow" (CASE 1 vs CASE 2).
        """
        dst_a = _anon(n + _SLACK)
        dst_b = _anon(n + _SLACK)
        anon_src = _anon(n + _SLACK)
        result["buffers"] = {
            "dst_a": _align_report(dst_a), "dst_b": _align_report(dst_b),
            "anon_src": _align_report(anon_src),
        }
        # Only the destinations are pre-faulted.  anon_src is left untouched so
        # S1 is a genuine first touch of source pages and S2 is the repeat.
        for d in (dst_a, dst_b):
            _memset(d, n)

        # Anonymous first-touch / repeat contrast.  This is the whole inline
        # sentinel: no file mapping, no shared memory, no registered arena.
        self._time_copy("sentinel_S1", "memmove", dst_a, anon_src, n, reps=1,
                        source_kind="anon_first_touch", dest_kind="anon_a",
                        condition="sentinel")
        self._time_copy("sentinel_S2", "memmove", dst_b, anon_src, n, reps=1,
                        source_kind="anon_resident", dest_kind="anon_b",
                        condition="sentinel")
        self._time_copy("sentinel_S3", "memmove", dst_a, anon_src, n, reps=1,
                        source_kind="anon_resident", dest_kind="anon_a",
                        condition="sentinel")
        result["exact_match"] = {"S1_dst_a": _memcmp(dst_a, anon_src, n),
                                 "S2_dst_b": _memcmp(dst_b, anon_src, n)}

        path = model_paths.get("clip")
        if level() < 2:
            result["sentinel_note"] = (
                "inline level 1 measures the anonymous path only; the file-backed "
                "arm belongs to the standalone copy lab (level>=2)"
            )
        elif not path or not os.path.exists(path):
            result["sentinel_note"] = "clip file unavailable; anonymous control only"
        else:
            fsize = os.path.getsize(path)
            with open(path, "rb") as fh:
                data_start = 8 + struct.unpack("<Q", fh.read(8))[0]
            st = os.stat(path)
            result["sentinel_source"] = {
                "path": path, "file_size": fsize, "data_start": data_start,
                "relative_mod64": data_start % 64, "dev": st.st_dev,
            }
            # Window-map only the ranges under test, never the whole file.
            waddr, delta = _file_window(path, data_start, n)
            try:
                src = waddr + delta
                # S1: first touch of a file-backed range -> its own destination
                self._time_copy("sentinel_S1", "memmove", dst_a, src, n, reps=1,
                                source_kind="file_first_touch", dest_kind="anon_a",
                                condition="sentinel", offset=data_start)
                # S2: the SAME now-resident range -> an INDEPENDENT destination
                self._time_copy("sentinel_S2", "memmove", dst_b, src, n, reps=1,
                                source_kind="file_resident", dest_kind="anon_b",
                                condition="sentinel", offset=data_start)
                # S3: anonymous control, resident source -> private destination
                self._time_copy("sentinel_S3", "memmove", dst_a, anon_src, n, reps=1,
                                source_kind="anon_resident", dest_kind="anon_a",
                                condition="sentinel")
                exact = {"S1_dst_a": _memcmp(dst_a, src, n),
                         "S2_dst_b": _memcmp(dst_b, src, n)}
                result["exact_match"] = exact
            finally:
                _unmap(waddr, delta + n)
            # a second untouched range: an independent first-touch sample,
            # in its own window so it is genuinely never-touched
            if data_start + 2 * n <= fsize:
                w2, d2 = _file_window(path, data_start + n, n)
                try:
                    self._time_copy("sentinel_S1b", "memmove", dst_b, w2 + d2, n, reps=1,
                                    source_kind="file_first_touch", dest_kind="anon_b",
                                    condition="sentinel", offset=data_start + n)
                    result["exact_match"]["S1b_dst_b"] = _memcmp(dst_b, w2 + d2, n)
                finally:
                    _unmap(w2, d2 + n)

        wall = {r["tag"]: (r.get("wall_ns") or [None])[0] for r in self.rows}
        s1, s2, s3 = wall.get("sentinel_S1"), wall.get("sentinel_S2"), wall.get("sentinel_S3")

        def gbps(ns):
            return (n / (ns / 1e9)) if ns else None

        result["sentinel"] = {
            "s1_first_copy_ns": s1, "s1_gbps": gbps(s1),
            "s2_repeat_copy_ns": s2, "s2_gbps": gbps(s2),
            "s3_anon_copy_ns": s3, "s3_gbps": gbps(s3),
            "s1_over_s2": (s1 / s2) if (s1 and s2) else None,
            "s1_over_s3": (s1 / s3) if (s1 and s3) else None,
        }

    @staticmethod
    def _med_gbps(walls, n: int):
        """Median GB/s over the repeat samples of a timed copy (excludes rep 0)."""
        if not walls:
            return None
        reps = [w for w in walls[1:]] or list(walls)
        reps.sort()
        mid = reps[len(reps) // 2]
        return ((n / (mid / 1e9)) / 1e9) if mid else None

    # ---- M1C: concurrency ceiling + registered-arena A/B/C ----------------
    def concurrency_and_arena(self, model_paths: dict, arena_addr: int | None,
                              n: int, result: dict) -> None:
        """Answer Q2 (shared source-service ceiling) and Q3 (registered arena).

        Q2: N threads each copy their own distinct 64 MiB *file-backed* window
        into private destinations, with a barrier so they overlap.  Source pages
        are pre-warmed first so this measures concurrency, not first-touch.
        If aggregate collapses from ~1 reader to ~4 readers, a shared
        file/gVisor source service is the ceiling.

        Q3: the same already-resident file range copied into three destination
        kinds -- private anonymous, unregistered shared, and the ACTUAL
        cudaHostRegister'd production arena -- so the registered-destination
        hypothesis is tested directly rather than inferred.
        """
        import threading

        role = "clip" if model_paths.get("clip") else "unet"
        path = model_paths.get(role)
        if not path or not os.path.exists(path):
            result["m1c_note"] = "no model file for concurrency/arena test"
            return
        fsize = os.path.getsize(path)
        with open(path, "rb") as fh:
            data_start = 8 + struct.unpack("<Q", fh.read(8))[0]
        result["m1c_source"] = {"role": role, "path": path, "file_size": fsize,
                                "data_start": data_start}

        nthreads_max = 4
        need = data_start + nthreads_max * n
        if need > fsize:
            result["m1c_note"] = "file too small for 4 x 64 MiB windows"
            return

        # Window-map the whole 4-window span read-only, then pre-warm every page
        # so Q2 measures concurrency rather than first-touch.
        waddr, delta = _file_window(path, data_start, nthreads_max * n)
        try:
            warm = _anon(nthreads_max * n + _SLACK)
            _memset(warm, nthreads_max * n)
            _memmove(warm, waddr + delta, nthreads_max * n)
            dsts = [_anon(n + _SLACK) for _ in range(nthreads_max)]
            for d in dsts:
                _memset(d, n)

            conc = []
            for k in (1, 2, 4):
                bar = threading.Barrier(k, timeout=120)
                walls = [0] * k
                cpus = [0] * k

                def work(i: int, _k=k) -> None:
                    try:
                        bar.wait()
                    except threading.BrokenBarrierError:
                        return
                    c0 = _tcpu()
                    t0 = _now()
                    _MEMMOVE(ctypes.c_void_p(dsts[i]), ctypes.c_void_p(waddr + delta + i * n),
                             ctypes.c_size_t(n))
                    t1 = _now()
                    walls[i] = t1 - t0
                    cpus[i] = _tcpu() - c0

                ths = [threading.Thread(target=work, args=(i,), daemon=True) for i in range(k)]
                for t in ths:
                    t.start()
                for t in ths:
                    t.join(180)
                slowest = max(walls) if any(walls) else None
                per = [(n / (w / 1e9)) / 1e9 for w in walls if w]
                conc.append({
                    "nthreads": k,
                    "per_reader_gbps": per,
                    "per_reader_median_gbps": (sorted(per)[len(per) // 2] if per else None),
                    "span_wall_ns": slowest,
                    "aggregate_gbps": ((k * n) / (slowest / 1e9)) / 1e9 if slowest else None,
                    "scaling_efficiency": None,
                    "thread_cpu_ns": cpus,
                })
            base = conc[0].get("aggregate_gbps")
            for c in conc:
                if base and c.get("aggregate_gbps"):
                    c["scaling_efficiency"] = c["aggregate_gbps"] / base
            result["m1c_concurrency"] = conc

            # ---- Q3: registered arena A/B/C on one resident file range ----
            src = waddr + delta
            abc = {}
            for dname, dptr in (("private_anon", dsts[0]),):
                _memset(dptr, n)
                rec = self._time_copy(f"arena_{dname}", "memmove", dptr, src, n, reps=5,
                                      source_kind="file_resident", dest_kind=dname,
                                      condition="arena_abc")
                abc[dname] = self._med_gbps(rec.get("wall_ns"), n)
            if arena_addr:
                for dname in ("registered_arena",):
                    _memset(arena_addr, n)
                    rec = self._time_copy(f"arena_{dname}", "memmove", arena_addr, src, n,
                                          reps=5, source_kind="file_resident",
                                          dest_kind=dname, condition="arena_abc")
                    abc[dname] = self._med_gbps(rec.get("wall_ns"), n)
            else:
                result["arena_note"] = "arena handle unavailable; Q3 incomplete"
            result["m1c_arena_abc_gbps"] = abc
            base = abc.get("private_anon")
            reg = abc.get("registered_arena")
            if base and reg:
                result["registered_arena_penalty_pct"] = (1.0 - reg / base) * 100.0
        finally:
            _unmap(waddr, delta + nthreads_max * n)

    # ---- phased driver -----------------------------------------------------
    def run_phased(self, model_paths: dict, arena_addr: int | None = None):
        """Run the probe as a generator, yielding after each phase.

        The probe is a native-memory harness, so a fault in any phase can take
        the process with it and destroy everything measured so far.  Each phase
        therefore runs independently and is yielded the moment it completes, so
        a later fault costs only that phase and the caller can persist what
        already succeeded.  The final yield is the cumulative result.
        """
        result: dict[str, Any] = {"schema": "m1cb_copy_probe_v2",
                                  "phases_completed": []}
        yield "start", result
        phases = (("libc_init", lambda: self._phase_libc(result)),
                  ("fingerprint", lambda: self._phase_fingerprint(result)),
                  ("copy_matrix", lambda: self._phase_matrix(model_paths, result,
                                                              arena_addr)))
        for name, fn in phases:
            try:
                fn()
            except Exception as exc:
                result.setdefault("phase_errors", {})[name] = (
                    f"{type(exc).__name__}: {exc}")
                yield "failed", result
                return
            result["phases_completed"].append(name)
            yield name, result
        if level() >= 3:
            # M1C phase: concurrency ceiling (Q2) and registered arena (Q3).
            # Separate from copy_matrix so a fault here cannot erase the
            # already-emitted matrix.
            try:
                self.concurrency_and_arena(model_paths, arena_addr, SLOT_BYTES,
                                           result)
            except Exception as exc:
                result.setdefault("phase_errors", {})["m1c"] = (
                    f"{type(exc).__name__}: {exc}")
                yield "failed", result
                return
            result["phases_completed"].append("m1c")
            yield "m1c", result
        yield "final", result

    def _phase_libc(self, result: dict) -> None:
        _init()
        result["libc"] = {"resolved": _LIBC is not None,
                          "memmove": bool(_MEMMOVE), "memcmp": bool(_MEMCMP)}

    def _phase_fingerprint(self, result: dict) -> None:
        self.fingerprint()
        result["fingerprint"] = dict(self.meta)

    def _phase_matrix(self, model_paths: dict, result: dict,
                      arena_addr: int | None) -> None:
        inner = self.run(model_paths, arena_addr=arena_addr)
        result["probe"] = inner
        if inner.get("error"):
            raise RuntimeError(inner["error"])

    # ---- main entry --------------------------------------------------------
    def run(self, model_paths: dict[str, str], arena_addr: int | None = None) -> dict:
        _init()
        self.fingerprint()
        n = SLOT_BYTES
        lv = level()
        result: dict[str, Any] = {"schema": "m1cb_copy_probe_v1", "level": lv,
                                  "nbytes": n, "rows": self.rows}
        try:
            if lv == 1:
                # Minimal inline sentinel only: no shared memory, no registered
                # arena, no thread scaling, no alignment sweep.  If even this
                # perturbs Golden, the file-backed arm moves to the standalone
                # lab and only the anonymous control stays inline.
                self.sentinel(model_paths, n, result)
                result["sha256_probe"] = "exact-memcmp"
                return result

            # Levels 2-4 are the wide factorial sweep.  Those belong to the
            # standalone copy lab, not to the inline Golden request: the full
            # matrix inlined is what killed the container at 497s.
            anon_src = _anon(n + _SLACK)
            anon_dst = _anon(n + _SLACK)
            result["buffers"] = {
                "anon_src": _align_report(anon_src), "anon_dst": _align_report(anon_dst),
            }
            dests = {"anon_private": anon_dst}
            if lv >= 2:
                shm_name = "m1cb_probe_shm"
                _shm_create(shm_name, n + _SLACK)
                shm_dst = _shm_map(shm_name, n + _SLACK)
                result["buffers"]["shm_dst"] = _align_report(shm_dst)
                dests["shm_unregistered"] = shm_dst
            if lv >= 3:
                if arena_addr:
                    result["buffers"]["arena_addr"] = _align_report(arena_addr)
                    dests["arena_registered"] = arena_addr
                else:
                    result["arena_note"] = "arena handle unavailable; arena rows skipped"

            # Warm every destination once so the FIRST measurement is a real
            # first-touch of SOURCE, not of an untouched destination.
            for dptr in dests.values():
                _memset(dptr, n)

            # ---- S3: resident anonymous -> each destination (raw floor) ----
            _memset(anon_src, n)  # materialize the anonymous source
            for dname, dptr in dests.items():
                self._time_copy(f"S3->{dname}", "memmove", dptr, anon_src, n, reps=2,
                                source_kind="anon_resident", dest_kind=dname, condition="S3")

            # ---- model file sources ----
            # Level 1 measures CLIP only; the wider sweep lands at level 3.
            roles = ["clip"] if lv < 3 else ["clip", "unet"]
            for role in roles:
                path = model_paths.get(role)
                if not path or not os.path.exists(path):
                    continue
                fsize = os.path.getsize(path)
                st = os.stat(path)
                # production data_start = 8 + safetensors header length
                with open(path, "rb") as fh:
                    data_start = 8 + struct.unpack("<Q", fh.read(8))[0]
                result.setdefault("models", {})[role] = {
                    "path": path, "file_size": fsize, "data_start": data_start,
                    "data_start_align": _align_report(data_start),
                    "relative_mod64": data_start % 64,
                    "relative_mod4096": data_start % 4096,
                    "dev": st.st_dev, "inode": st.st_ino,
                    "st_blocks": getattr(st, "st_blocks", None),
                }
                reps = 2 if lv < 3 else 3
                off0 = data_start
                # Window-map only the ranges under test.  A whole-file mapping
                # here would duplicate the production loader's own Whole mmap of
                # the same 8 GB / 12 GB safetensors inside one process; the
                # window keeps resident cost bounded while still reading
                # genuinely file-backed pages at the exact production offset.
                waddr, delta = _file_window(path, off0, n)
                try:
                    src = waddr + delta
                    # S1: first touch of a file-backed range (never accessed yet)
                    for dname, dptr in dests.items():
                        _memset(dptr, n)  # clean dest so S1 measures source only
                        self._time_copy(f"S1->{dname}", "memmove", dptr, src, n,
                                        reps=reps, source_kind="file_first_touch",
                                        dest_kind=dname, condition="S1", role=role,
                                        offset=off0)
                    # S2: the SAME range immediately again (now resident)
                    for dname, dptr in dests.items():
                        _memset(dptr, n)
                        self._time_copy(f"S2->{dname}", "memmove", dptr, src, n,
                                        reps=reps, source_kind="file_resident",
                                        dest_kind=dname, condition="S2", role=role,
                                        offset=off0)
                finally:
                    _unmap(waddr, delta + n)
                # a different, untouched file range for a second S1 sample
                if lv >= 3 and off0 + 2 * n <= fsize:
                    off1 = off0 + n
                    w2, d2 = _file_window(path, off1, n)
                    try:
                        for dname, dptr in dests.items():
                            _memset(dptr, n)
                            self._time_copy(f"S1b->{dname}", "memmove", dptr, w2 + d2, n,
                                            reps=reps, source_kind="file_first_touch",
                                            dest_kind=dname, condition="S1b",
                                            role=role, offset=off1)
                    finally:
                        _unmap(w2, d2 + n)

            # ---- destination write path (memset controls) ----
            for dname, dptr in dests.items():
                self._time_memset(f"memset_{dname}", dptr, n, reps=2, dest_kind=dname)

            if lv >= 3:
                # ---- memmove vs memcpy on the same resident file range ----
                p = model_paths.get("clip")
                if p and os.path.exists(p):
                    with open(p, "rb") as fh:
                        data_start = 8 + struct.unpack("<Q", fh.read(8))[0]
                    waddr, delta = _file_window(p, data_start, n)
                    try:
                        src = waddr + delta
                        _memmove(anon_dst, src, n)  # make it resident
                        for prim in ("memmove", "memcpy"):
                            for dname, dptr in dests.items():
                                _memset(dptr, n)
                                self._time_copy(f"prim_{prim}_{dname}", prim, dptr, src, n, reps=3,
                                                source_kind="file_resident", dest_kind=dname,
                                                condition="primitive_compare")
                    finally:
                        _unmap(waddr, delta + n)

                # ---- alignment variants: relative offset 0/32 on anon buffers ----
                for soff in (0, 32):
                    for doff in (0, 32):
                        _memset(anon_dst, n)
                        self._time_copy(f"align_s{soff}_d{doff}", "memmove",
                                        anon_dst + doff, anon_src + soff, n, reps=3,
                                        source_kind="anon_resident", dest_kind="anon_private",
                                        condition="alignment", forced_src_off=soff,
                                        forced_dst_off=doff)

            if lv >= 4:
                # ---- thread scaling on resident anonymous ----
                self.thread_scaling(n)

            result["sha256_probe"] = "not-computed"
        except Exception as exc:  # never let a probe failure break the request
            result["error"] = f"{type(exc).__name__}: {exc}"
            import traceback
            result["traceback"] = traceback.format_exc()[-2000:]
        finally:
            result["meta"] = self.meta
        return result
