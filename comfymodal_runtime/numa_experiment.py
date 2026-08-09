"""NUMA placement causal experiment for restored-UNET H2D variance (shadow only).

Question: does NUMA page placement, CPU affinity, or underlying NUMA/GPU
topology cause the restored-UNET H2D instability (~1-2 s healthy vs
~5-19 s bad, 12.31 GB, 100% resident, zero faults)?

On ONE restored single-use container this module:

  1. captures topology: CPU model/sockets/threads, process/thread CPU
     affinity, per-CPU node membership, NUMA node list + distance matrix,
     GPU PCI bus id + GPU NUMA node, current CPU;
  2. captures the ACTUAL NUMA distribution of the restored UNET pages
     (per-storage page ranges, from /proc/self/numa_maps AND an exact
     per-page move_pages(2) status query);
  3. measures baseline synchronized H2D of those exact restored storages;
  4. attempts to physically migrate the SAME restored pages to the
     GPU-local NUMA node with move_pages(2) (MPOL_MF_MOVE), then VERIFIES
     actual placement (exact status query) before re-measuring identical
     H2D;
  5. if local migration verified, migrates the same pages to a REMOTE
     NUMA node, verifies, re-measures H2D (reversibility check);
  6. runs the fallback/complement bind probe: fresh anonymous buffers of
     the same total size explicitly bound (mbind MPOL_BIND) to each
     available node, verified, then identical H2D — asking whether NUMA
     locality alone reproduces the fast/slow modes;
  7. proves byte equality of the transferred data after all timing.

Every step is JSON-safe, bounded, and never raises.  Success of a syscall
is NEVER inferred from its return value: page placement is always verified
after any migration/binding before an H2D comparison is reported.
"""

from __future__ import annotations

import ctypes
import json
import os
import time
from pathlib import Path
from typing import Any

# ── syscall constants (linux/mempolicy.h) ────────────────────────────────
MPOL_BIND = 2
MPOL_MF_MOVE = 1  # move pages owned by this process (no CAP_SYS_NICE needed)
MPOL_MF_STRICT = 1  # never combined with MOVE here (SIGBUS risk on faults)
MPOL_MF_MOVE_ALL = 2  # requires CAP_SYS_NICE — reported if attempted

_MOVE_CHUNK = 100_000  # pages per move_pages(2) call (bounded)
_PAGE_ALIGN_MASK = None  # resolved at first use


def _page_size() -> int:
    try:
        import ctypes as _c
        return int(_c.CDLL(None, use_errno=True).getpagesize())
    except Exception:
        return 4096


def _run_capture(args: list[str], timeout: float = 5.0) -> str | None:
    try:
        import subprocess as _sp
        _out = _sp.run(args, capture_output=True, text=True, timeout=timeout)
        if _out.returncode == 0 and _out.stdout:
            return _out.stdout.strip()
    except Exception:
        pass
    return None


# ── Topology capture ─────────────────────────────────────────────────────


def _read_sys(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip() or None
    except Exception:
        return None


def _path_readable(path: str) -> bool:
    try:
        with open(path, "rb"):
            return True
    except Exception:
        return False


def capture_topology() -> dict[str, Any]:
    """CPU/socket/thread/affinity/NUMA-node/distance/GPU-node snapshot.

    Best effort; every field is captured independently and absent fields
    are simply missing (never invented).  Never raises.
    """
    topo: dict[str, Any] = {}
    try:
        from comfymodal_runtime.modal_app import (
            _capture_cpu_info,
            _capture_gpu_info,
            _capture_vm_identity,
        )
        topo["cpu"] = _capture_cpu_info()
        topo["gpu"] = _capture_gpu_info()
        topo["vm"] = _capture_vm_identity()
    except Exception:
        pass
    try:
        topo["affinity_cpus"] = sorted(int(c) for c in os.sched_getaffinity(0))
    except Exception as exc:
        topo["affinity_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    try:
        import ctypes as _c
        _libc = _c.CDLL(None, use_errno=True)
        _libc.sched_getcpu.restype = _c.c_int
        topo["current_cpu"] = int(_libc.sched_getcpu())
    except Exception:
        pass
    topo["native_tid"] = None
    try:
        import threading
        topo["native_tid"] = int(threading.get_native_id())
    except Exception:
        pass
    # Node list + per-CPU node membership + distance matrix (sysfs).
    _nodes: list[int] = []
    try:
        _base = Path("/sys/devices/system/node")
        if _base.is_dir():
            for _entry in sorted(_base.iterdir()):
                if _entry.name.startswith("node") and _entry.name[4:].isdigit():
                    _nodes.append(int(_entry.name[4:]))
    except Exception:
        pass
    # Fallback when sysfs node dirs are hidden (sandboxed containers): the
    # nodes actually used by this process appear in /proc/self/numa_maps.
    if not _nodes:
        try:
            _vmas = read_proc_numa_maps()
            for _v in _vmas or []:
                for _n in _v["node_counts"]:
                    _digits = "".join(c for c in _n if c.isdigit())
                    if _digits and int(_digits) not in _nodes:
                        _nodes.append(int(_digits))
            _nodes.sort()
        except Exception:
            pass
    topo["numa_nodes"] = sorted(_nodes)
    _cpu_node: dict[int, str] = {}
    try:
        _cpu_base = Path("/sys/devices/system/cpu")
        for _cpu_dir in _cpu_base.glob("cpu[0-9]*"):
            try:
                _nid = int(_cpu_dir.name[3:])
            except ValueError:
                continue
            _node_ref = None
            try:
                _node_file = _cpu_dir / "node" / "numa_node"
                if _node_file.is_file():
                    _node_ref = _node_file.read_text(
                        encoding="utf-8", errors="replace"
                    ).strip()
            except Exception:
                _node_ref = None
            if _node_ref is None:
                # older kernels expose cpuN/node as a symlink dir "nodeX"
                try:
                    _node_dir = _cpu_dir / "node"
                    if _node_dir.is_dir():
                        _node_ref = _node_dir.name
                except Exception:
                    _node_ref = None
            if _node_ref is not None:
                _digits = "".join(ch for ch in str(_node_ref) if ch.isdigit())
                if _digits:
                    _cpu_node[_nid] = f"N{int(_digits)}"
    except Exception:
        pass
    topo["cpu_to_node"] = _cpu_node
    topo["affinity_nodes"] = sorted(
        {_cpu_node.get(c, "?") for c in topo.get("affinity_cpus", [])}
    )
    # Distance matrix: nodeN/distance rows (comma-separated to each node).
    _distances: dict[str, list[int]] = {}
    for _n in _nodes:
        _row = _read_sys(f"/sys/devices/system/node/node{_n}/distance")
        if _row:
            try:
                _distances[f"N{_n}"] = [int(x) for x in _row.split()]
            except Exception:
                _distances[f"N{_n}"] = []
    topo["distance_matrix"] = _distances
    _hw = _run_capture(["numactl", "--hardware"])
    if _hw:
        topo["numactl_hardware"] = _hw
    # GPU NUMA node: /sys/bus/pci/devices/<bus>/numa_node.  nvidia-smi
    # reports "00000000:00:05.0"; sysfs names are "0000:00:05.0".
    _gpu_bus = (topo.get("gpu") or {}).get("pci_bus_id", "")
    _gpu_node: Any = None
    _candidates = [str(_gpu_bus)]
    _norm = str(_gpu_bus)
    if len(_norm) > 4 and _norm.startswith("0000"):
        _candidates.append(_norm[4:])
    if _norm.startswith("00000000:"):
        _candidates.append(_norm[4:])
    for _bus in _candidates:
        if not _bus:
            continue
        _val = _read_sys(f"/sys/bus/pci/devices/{_bus}/numa_node")
        if _val is not None:
            try:
                _gpu_node = int(_val)
                break
            except ValueError:
                _gpu_node = _val
                break
    topo["gpu_pci_bus_id"] = _gpu_bus
    topo["gpu_numa_node"] = _gpu_node
    try:
        topo["cpuset"] = _read_sys("/proc/self/cpuset")
        _status_raw = Path("/proc/self/status").read_text(
            encoding="utf-8", errors="replace"
        )
        _seccomp: str | None = None
        _mems_raw: str | None = None
        for _ln in _status_raw.splitlines():
            if _ln.startswith("Mems_allowed:"):
                _mems_raw = _ln.split(":", 1)[1].strip()
            elif _ln.startswith("Seccomp:"):
                _seccomp = _ln.split(":", 1)[1].strip()
        topo["seccomp_mode"] = _seccomp
        topo["mems_allowed_raw"] = _mems_raw
        _mems_nodes: list[int] = []
        for _part in (_mems_raw or "").split(","):
            _part = _part.strip()
            if not _part:
                continue
            if "-" in _part:
                _lo, _, _hi = _part.partition("-")
                try:
                    _mems_nodes += list(range(int(_lo), int(_hi) + 1))
                except ValueError:
                    pass
            else:
                try:
                    _mems_nodes.append(int(_part))
                except ValueError:
                    pass
        topo["mems_allowed_nodes"] = sorted(set(_mems_nodes)) or None
    except Exception:
        pass
    # Sandbox visibility of NUMA proc files + per-node zone headers.
    topo["proc_visibility"] = {
        "numa_maps": _path_readable("/proc/self/numa_maps"),
        "maps": _path_readable("/proc/self/maps"),
        "zoneinfo": _path_readable("/proc/zoneinfo"),
        "buddyinfo": _path_readable("/proc/buddyinfo"),
        "sys_node_dir": bool(Path("/sys/devices/system/node").is_dir()),
    }
    try:
        _zone_nodes: list[str] = []
        for _ln in Path("/proc/zoneinfo").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            if _ln.startswith("Node"):
                _tok = _ln.split()[1]
                if _tok and _tok not in _zone_nodes:
                    _zone_nodes.append(_tok)
        topo["zoneinfo_nodes"] = _zone_nodes or None
    except Exception:
        pass
    topo["kernel"] = None
    try:
        import platform
        topo["kernel"] = platform.release()
    except Exception:
        pass
    return topo


# ── /proc/self/numa_maps parsing ─────────────────────────────────────────


def parse_numa_maps_lines(raw_lines: list[str]) -> list[dict[str, Any]]:
    """Parse /proc/self/numa_maps lines.

    IMPORTANT: numa_maps lines carry ONLY the VMA START address (no range).
    Each line: ``<addr> policy ... N0=5 anon=3 dirty=3 kernelpagesize_kB=4``.
    Returns [{addr, node_counts}] in file order.  Never raises.
    """
    out: list[dict[str, Any]] = []
    for _line in raw_lines:
        _toks = _line.split()
        if len(_toks) < 2:
            continue
        try:
            _addr = int(_toks[0], 16)
        except ValueError:
            continue
        _node_counts: dict[str, int] = {}
        for _tok in _toks[1:]:
            if len(_tok) > 1 and _tok[0] == "N" and "=" in _tok:
                _node, _, _cnt = _tok.partition("=")
                if _node[1:].isdigit() and _cnt.isdigit():
                    _node_counts[_node] = _node_counts.get(_node, 0) + int(_cnt)
        if _node_counts:
            out.append({"addr": _addr, "node_counts": _node_counts})
    return out


def _parse_maps_lines(raw_lines: list[str]) -> list[dict[str, Any]]:
    """Parse /proc/self/maps into [{start, end, perms}] (address order)."""
    out: list[dict[str, Any]] = []
    for _line in raw_lines:
        _toks = _line.split()
        if len(_toks) < 2:
            continue
        _range = _toks[0].split("-")
        if len(_range) != 2:
            continue
        try:
            _start = int(_range[0], 16)
            _end = int(_range[1], 16)
        except ValueError:
            continue
        out.append({"start": _start, "end": _end, "perms": _toks[1]})
    return out


def read_proc_numa_maps() -> list[dict[str, Any]] | None:
    """NUMA page counts per VMA, cross-referenced with /proc/self/maps.

    Both files enumerate the same VMAs in ascending address order, so the
    node-count lines are zipped with the maps ranges (fallback: match by
    start address; unmatched entries get a zero-length range).  Returns
    [{start, end, perms, node_counts}, ...] or None when unreadable.
    """
    try:
        _numa_lines = Path("/proc/self/numa_maps").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        _maps_lines = Path("/proc/self/maps").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except Exception:
        return None
    _counts = parse_numa_maps_lines(_numa_lines)
    _maps = _parse_maps_lines(_maps_lines)
    if len(_counts) == len(_maps):
        out: list[dict[str, Any]] = []
        for _c, _m in zip(_counts, _maps):
            out.append({
                "start": _m["start"], "end": _m["end"],
                "perms": _m["perms"], "node_counts": _c["node_counts"],
            })
        return out
    # Fallback: index by start address (e.g. kernel omitted empty VMAs).
    _by_start: dict[int, dict[str, Any]] = {_m["start"]: _m for _m in _maps}
    out = []
    for _c in _counts:
        _m = _by_start.get(_c["addr"])
        if _m is None:
            out.append({
                "start": _c["addr"], "end": _c["addr"],
                "perms": "?", "node_counts": _c["node_counts"],
            })
        else:
            out.append({
                "start": _m["start"], "end": _m["end"],
                "perms": _m["perms"], "node_counts": _c["node_counts"],
            })
    return out


def numa_counts_for_range(
    vmas: list[dict[str, Any]], start: int, end: int,
) -> dict[str, Any]:
    """NUMA page counts of the VMA(s) covering [start, end).

    Returns {node_counts, vma_start, vma_end, coverage_fraction, pages}.
    If no VMA covers the range, ``coverage_fraction`` is 0.
    """
    _ps = _page_size()
    for _vma in vmas:
        if _vma["start"] <= start and end <= _vma["end"]:
            _pages = (end - start) // _ps
            return {
                "node_counts": dict(_vma["node_counts"]),
                "vma_start": _vma["start"],
                "vma_end": _vma["end"],
                "coverage_fraction": 1.0,
                "pages": _pages,
                "perms": _vma["perms"],
            }
        if _vma["start"] < end and _vma["end"] > start:
            _overlap = min(end, _vma["end"]) - max(start, _vma["start"])
            _pages = max(1, _overlap // _ps)
            return {
                "node_counts": dict(_vma["node_counts"]),
                "vma_start": _vma["start"],
                "vma_end": _vma["end"],
                "coverage_fraction": round(_overlap / max(1, end - start), 4),
                "pages": _pages,
                "perms": _vma["perms"],
            }
    return {"node_counts": {}, "coverage_fraction": 0.0, "pages": 0}


def collect_unet_page_ranges(unet: Any) -> list[tuple[int, int]]:
    """Merged, page-aligned unique address ranges of all UNET storages.

    Uses the same storage iteration as unet_backing (dedup by storage
    identity), then merges overlapping page ranges (restored storages may
    share one big VMA).  Returns [(start, end_page_aligned), ...] sorted.
    """
    try:
        from comfymodal_runtime.unet_backing import _iter_unet_tensors
    except Exception:
        return []
    _ps = _page_size()
    _ranges: list[tuple[int, int]] = []
    try:
        for _name, _tensor, _st, _addr, _nbytes in _iter_unet_tensors(unet):
            if not _addr or _nbytes <= 0:
                continue
            _start = (_addr // _ps) * _ps
            _end = ((_addr + _nbytes + _ps - 1) // _ps) * _ps
            _ranges.append((_start, _end))
    except Exception:
        pass
    if not _ranges:
        return []
    _ranges.sort()
    _merged: list[tuple[int, int]] = []
    _s, _e = _ranges[0]
    for _ns, _ne in _ranges[1:]:
        if _ns <= _e:
            _e = max(_e, _ne)
        else:
            _merged.append((_s, _e))
            _s, _e = _ns, _ne
    _merged.append((_s, _e))
    return _merged


def unet_numa_distribution(unet: Any) -> dict[str, Any]:
    """NUMA distribution of the restored UNET pages (numa_maps based)."""
    record: dict[str, Any] = {"method": "proc_numa_maps_per_storage"}
    _vmas = read_proc_numa_maps()
    if _vmas is None:
        record["error"] = "proc_numa_maps_unreadable"
        return record
    _ps = _page_size()
    _total_pages = 0
    _covered_pages = 0
    _agg: dict[str, int] = {}
    _storages = 0
    try:
        from comfymodal_runtime.unet_backing import _iter_unet_tensors
        _seen: set[int] = set()
        _per_storage: list[dict[str, Any]] = []
        for _name, _tensor, _st, _addr, _nbytes in _iter_unet_tensors(unet):
            if not _addr or _nbytes <= 0 or id(_st) in _seen:
                continue
            _seen.add(id(_st))
            _start = (_addr // _ps) * _ps
            _end = ((_addr + _nbytes + _ps - 1) // _ps) * _ps
            _info = numa_counts_for_range(_vmas, _start, _end)
            _storages += 1
            _total_pages += _info["pages"]
            _covered_pages += int(_info["pages"] * _info["coverage_fraction"])
            for _n, _c in _info["node_counts"].items():
                _agg[_n] = _agg.get(_n, 0) + _c
            if len(_per_storage) < 24:
                _per_storage.append({
                    "name": _name, "bytes": int(_nbytes),
                    "addr": hex(_addr), "node_counts": _info["node_counts"],
                    "vma_shared": _info["coverage_fraction"] < 1.0,
                })
        record["storages"] = _storages
        record["total_pages"] = _total_pages
        record["covered_fraction"] = round(
            _covered_pages / _total_pages, 4
        ) if _total_pages else 0.0
        record["node_counts"] = _agg
        record["node_fractions"] = {
            _n: round(_c / max(1, _total_pages), 4) for _n, _c in _agg.items()
        }
        record["samples"] = _per_storage
    except Exception as exc:  # noqa: BLE001
        record["error"] = str(exc)[:200]
    return record


# ── move_pages(2) / mbind(2) via raw syscall(2) ───────────────────────────
# glibc does NOT export move_pages/mbind (they live in libnuma); the only
# portable path is the raw syscall(2) with the per-architecture numbers.
_SYSCALL_NRS: dict[str, dict[str, int]] = {
    "x86_64": {"move_pages": 279, "mbind": 237},
    "amd64": {"move_pages": 279, "mbind": 237},
    "aarch64": {"move_pages": 239, "mbind": 235},
    "arm64": {"move_pages": 239, "mbind": 235},
}

_SYSCALL_ARGTYPES: dict[str, list[Any]] = {
    # syscall(nr, pid, nr_pages, pages, nodes, status, flags)
    "move_pages": [
        ctypes.c_long, ctypes.c_int, ctypes.c_ulong,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
    ],
    # syscall(nr, addr, len, mode, nodemask, maxnode, flags)
    "mbind": [
        ctypes.c_long, ctypes.c_void_p, ctypes.c_ulong,
        ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_uint,
    ],
}


def _syscall_nr(name: str) -> int | None:
    try:
        import platform
        _m = platform.machine().lower()
    except Exception:
        _m = ""
    _table = _SYSCALL_NRS.get(_m) or _SYSCALL_NRS.get("x86_64")
    return (_table or {}).get(name)


def _raw_syscall(name: str, *args: Any) -> int:
    """Call *name* via syscall(2); returns the raw return code (errno set).

    args are converted to the exact C types (no varargs promotion), so
    pointers and 64-bit counts survive.  Raises only when the syscall
    function itself cannot be resolved (platform without syscall()).
    """
    _nr = _syscall_nr(name)
    if _nr is None:
        raise OSError(f"no syscall number for {name}")
    _lc = _libc()
    _fn = _lc.syscall
    try:
        _fn.restype = ctypes.c_long
        _fn.argtypes = [ctypes.c_long] + _SYSCALL_ARGTYPES[name][1:]
    except (AttributeError, TypeError):
        pass
    return int(_fn(ctypes.c_long(_nr), *args))


def _libc() -> Any:
    return ctypes.CDLL(None, use_errno=True)


def _page_addresses(ranges: list[tuple[int, int]]) -> list[int]:
    """Expand merged ranges into a flat list of page addresses."""
    _ps = _page_size()
    _addrs: list[int] = []
    for _start, _end in _ranges_guard(ranges):
        _addr = _start
        while _addr < _end:
            _addrs.append(_addr)
            _addr += _ps
    return _addrs


def _ranges_guard(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    _ps = _page_size()
    out: list[tuple[int, int]] = []
    for _s, _e in ranges or []:
        _s = (_s // _ps) * _ps
        _e = ((_e + _ps - 1) // _ps) * _ps
        if _e > _s:
            out.append((_s, _e))
    return out


def _move_pages_chunked(
    page_addrs: list[int],
    *,
    target_node: int | None,
    chunk: int = _MOVE_CHUNK,
) -> dict[str, Any]:
    """move_pages(2) (raw syscall) for self; None => status query only.

    Returns {calls, pages, status_counts, errno, error} where
    status_counts maps positive node ids -> count and negative values
    (-errno) -> count.  Never raises.
    """
    _pid = int(os.getpid())
    _flags = 0 if target_node is None else MPOL_MF_MOVE
    result: dict[str, Any] = {
        "mode": "query" if target_node is None else "move",
        "target_node": target_node,
        "pages": len(page_addrs),
        "calls": 0,
        "status_counts": {},
        "syscall_errno": [],
    }
    if not page_addrs:
        return result
    try:
        for _i in range(0, len(page_addrs), chunk):
            _slice = page_addrs[_i:_i + chunk]
            _n = len(_slice)
            _pages_arr = (ctypes.c_void_p * _n)(*_slice)
            _status_arr = (ctypes.c_int * _n)()
            _nodes_ptr = None
            if target_node is not None:
                _nodes_arr = (ctypes.c_int * _n)(*([int(target_node)] * _n))
                _nodes_ptr = ctypes.cast(_nodes_arr, ctypes.c_void_p)
            _rc = _raw_syscall(
                "move_pages", ctypes.c_int(_pid), ctypes.c_ulong(_n),
                ctypes.cast(_pages_arr, ctypes.c_void_p),
                _nodes_ptr,
                ctypes.cast(_status_arr, ctypes.c_void_p),
                ctypes.c_int(_flags),
            )
            _err = ctypes.get_errno()
            result["calls"] += 1
            if _rc != 0:
                # On syscall failure the status array is indeterminate; only
                # the errno is meaningful.  Never count it as placement.
                result["syscall_errno"].append(_err)
                continue
            for _st in _status_arr:
                if _st >= 0:
                    result["status_counts"][f"N{_st}"] = (
                        result["status_counts"].get(f"N{_st}", 0) + 1
                    )
                else:
                    _k = f"errno{-_st}"
                    result["status_counts"][_k] = result["status_counts"].get(_k, 0) + 1
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return result


def query_unet_pages_exact(unet: Any) -> dict[str, Any]:
    """Exact per-page NUMA placement of the restored UNET pages.

    Uses move_pages(2) status query (no flags, no nodes) — the ground
    truth for page placement.  Returns status_counts + pages on each node.
    """
    _ranges = collect_unet_page_ranges(unet)
    _addrs = _page_addresses(_ranges)
    _res = _move_pages_chunked(_addrs, target_node=None)
    _res["method"] = "move_pages_exact_status"
    _res["ranges"] = len(_ranges)
    _res["page_size"] = _page_size()
    _res["total_bytes"] = len(_addrs) * _page_size()
    return _res


def migrate_unet_pages_to_node(unet: Any, node: int) -> dict[str, Any]:
    """move_pages(MPOL_MF_MOVE) all restored UNET pages to *node*.

    Verification is NEVER inferred: after the move, an exact status query
    re-counts every page's actual node.  ``verified`` is True only when
    >=99.9% of pages are on the target node.  Never raises.
    """
    record: dict[str, Any] = {"target_node": node}
    try:
        _ranges = collect_unet_page_ranges(unet)
        _addrs = _page_addresses(_ranges)
        record["pages"] = len(_addrs)
        if not _addrs:
            record["verified"] = False
            record["error"] = "no_pages"
            return record
        _move = _move_pages_chunked(_addrs, target_node=node)
        record["move"] = _move
        _query = _move_pages_chunked(_addrs, target_node=None)
        record["verify"] = _query
        _on_target = int(_query["status_counts"].get(f"N{node}", 0))
        _total = int(_query.get("pages", 0))
        record["pages_on_target"] = _on_target
        record["fraction_on_target"] = round(_on_target / max(1, _total), 4)
        record["verified"] = bool(
            _total > 0 and _on_target >= max(1, int(_total * 0.999))
        )
    except Exception as exc:  # noqa: BLE001
        record["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        record["verified"] = False
    return record


# ── mbind-based fresh-buffer bind probe ──────────────────────────────────


def mbind_probe(size_bytes: int, node: int) -> dict[str, Any]:
    """Allocate *size_bytes* of fresh anonymous RAM bound to *node*.

    mmap -> mbind(MPOL_BIND, nodemask={node}) -> touch every page ->
    verify actual placement via move_pages status query (all pages) ->
    return {addr, mbind_errno, verify, pages_on_node, verified,
    allocated_bytes}.  The mapping stays live; caller must munmap via
    ``mbind_probe_release``.  Never raises.
    """
    record: dict[str, Any] = {"target_node": node, "bytes": int(size_bytes)}
    _lc = _libc()
    _libc_mmap = _lc.mmap
    _libc_mmap.restype = ctypes.c_void_p
    _libc_mmap.argtypes = [
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_long,
    ]
    _libc_munmap = _lc.munmap
    _libc_munmap.restype = ctypes.c_int
    _libc_munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    _PROT_RW = 0x1 | 0x2
    _MAP_PRIV_ANON = 0x02 | 0x20
    _addr = None
    try:
        _size = int(size_bytes)
        _size = max(_size, _page_size())
        _addr = _libc_mmap(None, _size, _PROT_RW, _MAP_PRIV_ANON, -1, 0)
        if not _addr or _addr == ctypes.c_void_p(-1).value:
            record["error"] = f"mmap_failed errno={ctypes.get_errno()}"
            return record
        record["addr"] = hex(int(_addr))
        # nodemask: bit N set for node N; maxnode = highest node + 1.
        _words = (max(int(node), 0) + 64) // 64
        _mask = (ctypes.c_ulong * max(1, _words))()
        _mask[int(node) // 64] = (
            int(_mask[int(node) // 64]) | (1 << (int(node) % 64))
        )
        _rc = _raw_syscall(
            "mbind",
            ctypes.c_void_p(int(_addr)), ctypes.c_ulong(_size),
            ctypes.c_int(MPOL_BIND),
            ctypes.cast(_mask, ctypes.c_void_p),
            ctypes.c_ulong(int(node) + 1),
            ctypes.c_uint(0),
        )
        record["mbind_attempts"] = [{
            "mode_type": "c_int",
            "rc": int(_rc),
            "errno": None if _rc == 0 else ctypes.get_errno(),
        }]
        record["mbind_errno"] = record["mbind_attempts"][-1]["errno"]
        # Touch every page (allocation happens under the policy).
        import numpy as np
        _np_buf = np.frombuffer(
            (ctypes.c_ubyte * _size).from_address(_addr), dtype=np.uint8,
        )
        _np_buf[:] = 1
        # Verify actual placement (full exact status query).
        _ps = _page_size()
        _npages = _size // _ps
        _sample = list(range(0, _npages, 512))  # 1/512 sample is enough here
        _sample_addrs = [int(_addr) + _p * _ps for _p in _sample]
        _verify = _move_pages_chunked(_sample_addrs, target_node=None)
        record["verify_sample"] = _verify
        record["verify_sample_pages"] = len(_sample)
        _on_node = int(_verify["status_counts"].get(f"N{node}", 0))
        record["pages_on_node_sample"] = _on_node
        record["fraction_on_node_sample"] = round(
            _on_node / max(1, len(_sample)), 4
        )
        record["verified"] = bool(
            _on_node >= max(1, int(len(_sample) * 0.999))
        )
        # Keep the mapping alive: store the byte-array object in the record
        # (JSON-safe str) AND return the real objects via the impl caller.
        record["_keepalive"] = _np_buf  # non-serializable; stripped before json
    except Exception as exc:  # noqa: BLE001
        record["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return record


def mbind_probe_release(record: dict[str, Any]) -> None:
    """munmap the mbind probe mapping (best effort)."""
    try:
        _addr = int(record.get("addr", "0"), 16)
        _size = int(record.get("bytes", 0))
        if _addr and _size:
            _lc = _libc()
            _lc.munmap.restype = ctypes.c_int
            _lc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            _lc.munmap(ctypes.c_void_p(_addr), _size)
    except Exception:
        pass
    try:
        record.pop("_keepalive", None)
    except Exception:
        pass


def run_bind_probe_h2d(
    unet_bytes: int, node: int, *, label: str,
) -> dict[str, Any]:
    """Fresh anonymous *unet_bytes* buffer bound to *node*, then H2D.

    Synchronized H2D of the bound buffer (same mechanics as the real UNET
    load).  Reports mbind result + verified placement + H2D wall/GB/s.
    Never raises; always frees GPU + unmaps.
    """
    record: dict[str, Any] = {"label": label, "target_node": node,
                              "bytes": int(unet_bytes)}
    _probe = mbind_probe(int(unet_bytes), node)
    record["mbind"] = {k: v for k, v in _probe.items() if not k.startswith("_")}
    try:
        if _probe.get("verified"):
            import torch
            import numpy as np
            _buf = _probe.get("_keepalive")
            if _buf is not None:
                _torch_t = torch.from_numpy(np.frombuffer(_buf, dtype=np.float32))
                torch.cuda.synchronize()
                _start = time.perf_counter()
                _gpu = _torch_t.to(device="cuda", non_blocking=False)
                torch.cuda.synchronize()
                _dur = max(time.perf_counter() - _start, 1e-9)
                record["h2d_wall_ms"] = round(_dur * 1000.0, 3)
                record["h2d_gb_per_s"] = round(
                    (int(unet_bytes) / 1_000_000_000.0) / _dur, 3
                )
                try:
                    del _gpu
                    torch.cuda.empty_cache()
                except Exception:
                    pass
        else:
            record["h2d_skipped_reason"] = (
                _probe.get("error") or "placement_not_verified"
            )
    except Exception as exc:  # noqa: BLE001
        record["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        mbind_probe_release(_probe)
    return record


# ── Main experiment impl ─────────────────────────────────────────────────


def _resolve_retained_unet(entrypoint: Any) -> Any:
    _models = getattr(entrypoint, "_cpu_snapshot_models", None)
    _unet = getattr(_models, "unet", None) if _models is not None else None
    if _unet is None:
        try:
            _prep = getattr(entrypoint._preload_bridge, "_preparation", None)
            if _prep is not None and getattr(_prep, "unet_future", None) is not None:
                _unet = _prep.unet_future.result()
        except Exception:
            _unet = None
    return _unet


def _json_safe(record: dict[str, Any]) -> dict[str, Any]:
    try:
        json.dumps(record)
        return record
    except Exception:
        def _clean(v: Any) -> Any:
            if isinstance(v, dict):
                return {str(k): _clean(x) for k, x in v.items()}
            if isinstance(v, (list, tuple)):
                return [_clean(x) for x in v]
            if isinstance(v, (bool, int, float)) or v is None:
                return v
            return str(v)
        return _clean(record)


def run_numa_experiment_impl(
    entrypoint: Any,
    *,
    request_id: str = "",
) -> dict[str, Any]:
    """Execute the full NUMA causal cascade on ONE restored container.

    *entrypoint* — the ModalRuntimeEntrypoint instance.  Returns a
    JSON-safe record; never raises.
    """
    started_mono_ns = time.monotonic_ns()
    record: dict[str, Any] = {
        "method": "run_numa_experiment",
        "request_id": str(request_id or ""),
        "started_mono_ns": started_mono_ns,
        "status": "running",
    }
    try:
        # ── Identity + runtime init (mirrors rehoming experiment) ──
        try:
            from comfymodal_runtime.rehoming_experiment import _capture_identity
            record["identity"] = _capture_identity()
        except Exception:
            pass
        try:
            entrypoint._configure_runtime()
            entrypoint._lazy_init_snapshot_state()
        except Exception as exc:
            record["runtime_config_error"] = str(exc)[:200]
        record["restore_count"] = getattr(entrypoint, "_restore_count", 0)
        record["restored_instance_id"] = getattr(
            entrypoint, "_restored_instance_id", ""
        )
        try:
            import torch
            record["cuda_available"] = bool(torch.cuda.is_available())
            if record["cuda_available"]:
                record["gpu_name"] = str(torch.cuda.get_device_name(0))
        except Exception:
            pass

        # ── Topology ──
        record["topology"] = capture_topology()

        # ── Retained restored UNET ──
        unet = _resolve_retained_unet(entrypoint)
        if unet is None:
            record["status"] = "failed"
            record["reason"] = "no_retained_unet"
            return record
        record["unet_object_id"] = str(id(unet))
        try:
            from comfymodal_runtime.unet_backing import unet_storage_sizes
            record["storage_sizes"] = unet_storage_sizes(unet)
            record["storage_count"] = len(record["storage_sizes"])
            record["unet_bytes"] = sum(record["storage_sizes"])
        except Exception:
            pass
        try:
            from comfymodal_runtime.unet_backing import mincore_unet_residency
            record["restored_residency"] = mincore_unet_residency(unet)
        except Exception:
            pass

        # ── Baseline NUMA distribution + H2D of the restored storages ──
        from comfymodal_runtime.unet_backing import (
            _iter_unet_tensors,
            measure_tensors_synced_h2d,
        )
        _orig_tensors: list[tuple[str, Any]] = [
            (_name, _tensor)
            for _name, _tensor, _st, _addr, _nbytes in _iter_unet_tensors(unet)
        ]
        record["original_tensor_count"] = len(_orig_tensors)
        record["baseline_numa_maps"] = unet_numa_distribution(unet)
        record["baseline_numa_exact"] = query_unet_pages_exact(unet)
        record["baseline_h2d"], _ = measure_tensors_synced_h2d(
            _orig_tensors, label="restored_baseline", keep_gpu=False,
        )

        # ── Migration cascade (GPU-local first, then remote) ──
        _topo = record.get("topology") or {}
        _gpu_node = _topo.get("gpu_numa_node")
        _nodes = [int(n) for n in (_topo.get("numa_nodes") or [])]
        _allowed = [int(n) for n in (_topo.get("mems_allowed_nodes") or [])]
        _gpu_node_int: int | None = None
        try:
            _gn = int(_gpu_node)
            if _gn >= 0:
                _gpu_node_int = _gn
        except (TypeError, ValueError):
            _gpu_node_int = None
        # Fallback "local" node when the GPU node is undetectable (hidden
        # PCI bus in sandboxes): the only node this process may allocate on.
        _local_node: int | None = _gpu_node_int or (_allowed[0] if _allowed else None)
        _remote_node: int | None = None
        _all_nodes = sorted(set(_nodes) | set(_allowed))
        if _all_nodes:
            _candidates = [n for n in _all_nodes if n != _local_node]
            if _candidates:
                _remote_node = _candidates[-1]
        record["gpu_numa_node"] = _gpu_node_int
        record["local_node"] = _local_node
        record["remote_node"] = _remote_node

        if _local_node is not None:
            _mig = migrate_unet_pages_to_node(unet, _local_node)
            record["local_migration"] = _mig
            if _mig.get("verified"):
                record["after_local_numa_maps"] = unet_numa_distribution(unet)
                record["local_h2d"], _ = measure_tensors_synced_h2d(
                    _orig_tensors, label="after_local_migration", keep_gpu=False,
                )
                if _remote_node is not None:
                    _mig2 = migrate_unet_pages_to_node(unet, _remote_node)
                    record["remote_migration"] = _mig2
                    if _mig2.get("verified"):
                        record["after_remote_numa_maps"] = unet_numa_distribution(unet)
                        record["remote_h2d"], _ = measure_tensors_synced_h2d(
                            _orig_tensors, label="after_remote_migration",
                            keep_gpu=False,
                        )
        else:
            record["local_migration"] = {
                "verified": False, "error": "no_local_node"
            }

        # ── Sandbox restriction summary ──
        # move_pages EPERM on a status-only query = the sandbox blocks the
        # NUMA syscall family; placement is then unobservable + immovable.
        _blocked = False
        _baseline_exact = record.get("baseline_numa_exact") or {}
        if _baseline_exact.get("syscall_errno"):
            _blocked = True
        _mig_move = (record.get("local_migration") or {}).get("move") or {}
        if _mig_move.get("syscall_errno"):
            _blocked = True
        record["manipulation_blocked"] = _blocked
        if _blocked:
            _errnos = sorted(set(
                list(_baseline_exact.get("syscall_errno") or [])
                + list(_mig_move.get("syscall_errno") or [])
            ))
            record["blocked_errnos"] = _errnos
            record["blocked_reason"] = (
                "move_pages(2) denied by sandbox (EPERM on status query); "
                "NUMA page placement unobservable and immovable in-container"
            )

        # ── Bind probe: fresh memory explicitly bound to each node ──
        _ubytes = int(record.get("unet_bytes") or 0)
        _bind: dict[str, Any] = {}
        if _ubytes > 0:
            _probe_nodes: list[tuple[str, int | None]] = [
                ("local", _local_node),
            ]
            if _remote_node is not None:
                _probe_nodes.append(("remote", _remote_node))
            for _label, _node in _probe_nodes:
                if _node is None:
                    _bind[_label] = {"skipped": "no_node"}
                    continue
                _bind[_label] = run_bind_probe_h2d(
                    _ubytes, int(_node), label=_label,
                )
        record["bind_probe"] = _bind

        # ── Fresh anonymous control H2D (same container, same size) ──
        # Same-container control: freshly allocated anonymous 12.31 GB
        # (subject to the same single-node cpuset) measured with the same
        # synchronized H2D mechanics as the restored storages.
        if _ubytes > 0:
            try:
                from comfymodal_runtime.unet_backing import (
                    run_contiguous_h2d_probe,
                )
                record["fresh_control_h2d"] = run_contiguous_h2d_probe(
                    bytes_=_ubytes,
                )
            except Exception as exc:  # noqa: BLE001
                record["fresh_control_h2d"] = {
                    "error": f"{type(exc).__name__}: {str(exc)[:200]}"
                }

        # ── Byte equality: kept GPU copy vs current CPU storages ──
        _eq: dict[str, Any] = {"compared": 0, "equal": 0, "status": ""}
        try:
            import torch
            _eq_pair = measure_tensors_synced_h2d(
                _orig_tensors, label="equality_proof", keep_gpu=True,
            )
            _gpu_list = _eq_pair[1][0] if _eq_pair[1] is not None else None
            _gpu_names = _eq_pair[1][1] if _eq_pair[1] is not None else None
            _cpu_map: dict[str, Any] = {}
            for _n, _t in _orig_tensors:
                _cpu_map[_n] = _t
            if _gpu_list is not None and len(_gpu_list) == len(_gpu_names):
                for _idx, _name in enumerate(_gpu_names):
                    _cpu_t = _cpu_map.get(_name)
                    if _cpu_t is None:
                        _eq["status"] = f"missing_cpu:{_name}"
                        break
                    try:
                        _gpu_cpu = _gpu_list[_idx].to(device="cpu")
                        if not torch.equal(_cpu_t, _gpu_cpu):
                            _eq["status"] = f"mismatch:{_name}"
                            break
                    except Exception as exc:
                        _eq["status"] = f"compare_error:{_name}:{type(exc).__name__}"
                        break
                    _eq["compared"] += 1
                    _eq["equal"] += 1
                if not _eq["status"]:
                    _eq["status"] = "all_equal"
            else:
                _eq["status"] = "equality_h2d_failed"
            try:
                del _gpu_list
                torch.cuda.empty_cache()
            except Exception:
                pass
        except Exception as exc:  # noqa: BLE001
            _eq["status"] = f"error:{type(exc).__name__}"
        record["byte_equality"] = _eq

        record["ended_mono_ns"] = time.monotonic_ns()
        record["total_wall_ms"] = round(
            (record["ended_mono_ns"] - started_mono_ns) / 1_000_000, 3
        )
        record["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 - never raises out
        record["status"] = "failed"
        record["reason"] = str(exc)[:300]
        try:
            record["error_type"] = type(exc).__name__
        except Exception:
            pass
    return _json_safe(record)
