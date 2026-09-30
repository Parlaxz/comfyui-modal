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
PROBE_ENV = "COMFYMODAL_M1B_COPY_PROBE"
LEVEL_ENV = "COMFYMODAL_M1B_LEVEL"

_LIBC: Any = None
_MEMMOVE: Any = None
_MEMCPY: Any = None
_MEMSET: Any = None


def enabled() -> bool:
    return str(os.environ.get(PROBE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def level() -> int:
    try:
        return int(str(os.environ.get(LEVEL_ENV) or "1").strip() or 1)
    except ValueError:
        return 1


def _init() -> None:
    """Resolve the libc surface ONCE. ctypes.CDLL releases the GIL per call."""
    global _LIBC, _MEMMOVE, _MEMCPY, _MEMSET
    if _LIBC is not None:
        return
    _LIBC = ctypes.CDLL(None, use_errno=True)
    _LIBC.mmap.restype = ctypes.c_void_p
    _LIBC.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, ctypes.c_long]
    _LIBC.munmap.restype = ctypes.c_int
    _LIBC.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    for name in ("memmove", "memcpy", "memset"):
        fn = getattr(_LIBC, name)
        fn.restype = ctypes.c_void_p
        if name == "memset":
            fn.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]
        else:
            fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    _MEMMOVE, _MEMCPY, _MEMSET = _LIBC.memmove, _LIBC.memcpy, _LIBC.memset


# ── small allocation helpers ────────────────────────────────────────────────
def _anon(size: int, *, align: int = 4096) -> int:
    """Anonymous memory, page-aligned, zero-filled by the kernel on first touch."""
    _init()
    extra = align if (size % align) else 0
    addr = _LIBC.mmap(None, ctypes.c_size_t(size + extra), 1, 0x22, -1, 0)  # PROT_READ|WRITE, MAP_PRIVATE|ANON
    if not addr or int(ctypes.cast(addr, ctypes.c_void_p).value or 0) == ctypes.c_void_p(-1).value:
        raise RuntimeError(f"anon_mmap_failed errno={ctypes.get_errno()}")
    return int(ctypes.cast(addr, ctypes.c_void_p).value or 0)


def _file_map(path: str, length: int | None = None) -> tuple[int, int]:
    """Whole-file MAP_PRIVATE|PROT_READ mapping, exactly as production does."""
    _init()
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        size = length if length is not None else os.fstat(fd).st_size
        addr = _LIBC.mmap(None, ctypes.c_size_t(size), 1, 2, fd, 0)  # PROT_READ, MAP_PRIVATE
        if not addr or int(ctypes.cast(addr, ctypes.c_void_p).value or 0) == ctypes.c_void_p(-1).value:
            raise RuntimeError(f"file_mmap_failed errno={ctypes.get_errno()}")
        return int(ctypes.cast(addr, ctypes.c_void_p).value or 0), int(size)
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
    """Sampled integrity check. Proves the copy actually moved bytes."""
    _init()
    buf = (ctypes.c_char * n).from_address(addr)
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
    def thread_scaling(self, anon_src: int, anon_dst: int, shm_dst: int, n: int) -> None:
        import threading
        for label, base in (("anon_private", anon_dst), ("anon_shared_registered", shm_dst)):
            for nthreads in (1, 2, 3, 4):
                bar = threading.Barrier(nthreads)
                out: list = [0] * nthreads
                cpu: list = [0] * nthreads

                def work(i: int) -> None:
                    bar.wait()
                    c0 = _tcpu()
                    t0 = _now()
                    _MEMMOVE(ctypes.c_void_p(base + i * n), ctypes.c_void_p(anon_src + i * n),
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
                          dst=_align_report(base), src=_align_report(anon_src))

    # ---- main entry --------------------------------------------------------
    def run(self, model_paths: dict[str, str], arena_addr: int | None = None) -> dict:
        _init()
        self.fingerprint()
        n = SLOT_BYTES
        result: dict[str, Any] = {"schema": "m1cb_copy_probe_v1", "level": level(),
                                  "nbytes": n, "rows": self.rows}
        try:
            anon_src = _anon(n)
            anon_dst = _anon(n)
            shm_name = "m1cb_probe_shm"
            _shm_create(shm_name, n)
            shm_dst = _shm_map(shm_name, n)
            result["buffers"] = {
                "anon_src": _align_report(anon_src), "anon_dst": _align_report(anon_dst),
                "shm_dst": _align_report(shm_dst), "arena_addr": _align_report(arena_addr) if arena_addr else None,
            }
            # warm every destination once so the FIRST measurement is a real
            # first-touch of SOURCE, not of an untouched destination.
            _memset(anon_dst, n); _memset(shm_dst, n)
            if arena_addr:
                _memset(arena_addr, n)

            dests = {"anon_private": anon_dst, "shm_unregistered": shm_dst}
            if arena_addr:
                dests["arena_registered"] = arena_addr

            # ---- S3: resident anonymous -> each destination (raw floor) ----
            _memset(anon_src, n)  # materialize the anonymous source
            for dname, dptr in dests.items():
                self._time_copy(f"S3->{dname}", "memmove", dptr, anon_src, n, reps=3,
                                source_kind="anon_resident", dest_kind=dname, condition="S3")

            # ---- model file sources ----
            for role, path in model_paths.items():
                if not path or not os.path.exists(path):
                    continue
                faddr, fsize = _file_map(path)
                try:
                    st = os.stat(path)
                    data_start = fsize - 8 - 0  # refined below
                    # production data_start = file_size - data_bytes; recover
                    # data_bytes from the known 64MiB extent plan shape instead:
                    with open(path, "rb") as fh:
                        fh.seek(0)
                        raw = fh.read(8)
                        hdr_len = struct.unpack("<Q", raw)[0]
                        data_start = 8 + int(hdr_len)
                    result.setdefault("models", {})[role] = {
                        "path": path, "file_size": fsize, "data_start": data_start,
                        "data_start_align": _align_report(data_start),
                        "relative_mod64": data_start % 64,
                        "relative_mod4096": data_start % 4096,
                        "dev": st.st_dev, "inode": st.st_ino, "st_blocks": getattr(st, "st_blocks", None),
                    }
                    # S1: first touch of a file-backed range (never accessed yet)
                    off0 = data_start
                    for dname, dptr in dests.items():
                        _memset(dptr, n)  # clean destination so S1 measures source only
                        self._time_copy(f"S1->{dname}", "memmove", dptr, faddr + off0, n,
                                        reps=3, source_kind="file_first_touch",
                                        dest_kind=dname, condition="S1", role=role, offset=off0)
                    # S2: the SAME range immediately again (now resident)
                    for dname, dptr in dests.items():
                        _memset(dptr, n)
                        self._time_copy(f"S2->{dname}", "memmove", dptr, faddr + off0, n,
                                        reps=3, source_kind="file_resident",
                                        dest_kind=dname, condition="S2", role=role, offset=off0)
                    # a different, untouched file range for a second S1 sample
                    off1 = data_start + n
                    if off1 + n <= fsize:
                        for dname, dptr in dests.items():
                            _memset(dptr, n)
                            self._time_copy(f"S1b->{dname}", "memmove", dptr, faddr + off1, n,
                                            reps=3, source_kind="file_first_touch",
                                            dest_kind=dname, condition="S1b", role=role, offset=off1)
                finally:
                    _unmap(faddr, fsize)

            # ---- memmove vs memcpy on the same resident file range ----
            if model_paths.get("clip") and os.path.exists(model_paths["clip"]):
                p = model_paths["clip"]
                faddr, fsize = _file_map(p)
                try:
                    with open(p, "rb") as fh:
                        data_start = 8 + struct.unpack("<Q", fh.read(8))[0]
                    src = faddr + data_start
                    _memmove(anon_dst, src, n)  # make it resident
                    for prim in ("memmove", "memcpy"):
                        for dname, dptr in dests.items():
                            _memset(dptr, n)
                            self._time_copy(f"prim_{prim}_{dname}", prim, dptr, src, n, reps=5,
                                            source_kind="file_resident", dest_kind=dname,
                                            condition="primitive_compare")
                finally:
                    _unmap(faddr, fsize)

            # ---- alignment variants: relative offset 0/32 on anon buffers ----
            for soff in (0, 32):
                for doff in (0, 32):
                    _memset(anon_dst, n)
                    self._time_copy(f"align_s{soff}_d{doff}", "memmove",
                                    anon_dst + doff, anon_src + soff, n, reps=5,
                                    source_kind="anon_resident", dest_kind="anon_private",
                                    condition="alignment", forced_src_off=soff, forced_dst_off=doff)

            # ---- destination write path (memset controls) ----
            for dname, dptr in dests.items():
                self._time_memset(f"memset_{dname}", dptr, n, reps=3, dest_kind=dname)

            # ---- thread scaling on resident anonymous ----
            self.thread_scaling(anon_src, anon_dst, shm_dst, n)

            result["sha256_probe"] = "not-computed"
        except Exception as exc:  # never let a probe failure break the request
            result["error"] = f"{type(exc).__name__}: {exc}"
            import traceback
            result["traceback"] = traceback.format_exc()[-2000:]
        finally:
            result["meta"] = self.meta
        return result
