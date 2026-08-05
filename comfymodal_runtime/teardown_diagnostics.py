"""Bounded diagnostics for V2 request and container teardown."""

from __future__ import annotations

import atexit
import asyncio
import json
import multiprocessing
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping


ENV_FLAG = "COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS"
PREFIX = "[v2.teardown]"
_MAX_THREADS = 64
_MAX_PROCESSES = 64
_MAX_FDS = 128
_MAX_ITEMS = 64
_MAX_STRING = 256
_SENSITIVE = re.compile(
    r"(token|secret|password|authorization|cookie|api[_-]?key|bearer|credential)",
    re.IGNORECASE,
)
_ATExit_LOCK = threading.Lock()
_ATExit_REGISTERED = False
_INSTANCES: list["TeardownDiagnostics"] = []


def diagnostics_enabled() -> bool:
    return os.environ.get(ENV_FLAG) == "1"


def _safe_string(value: Any, limit: int = _MAX_STRING) -> str:
    try:
        text = str(value)
    except Exception:
        text = "<unavailable>"
    return text[:limit]


def _safe_value(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_MAX_STRING]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                result["<truncated>"] = True
                break
            key_text = _safe_string(key, 96)
            result[key_text] = "<redacted>" if _SENSITIVE.search(key_text) else _safe_value(item, depth + 1)
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe_value(item, depth + 1) for item in list(value)[:_MAX_ITEMS]]
    if isinstance(value, Path):
        return _safe_string(value)
    return f"<{type(value).__name__}>"


def _sanitize_cmdline(value: str) -> str:
    parts = value.replace("\x00", " ").split()
    safe: list[str] = []
    redact_next = False
    for part in parts[:_MAX_ITEMS]:
        if redact_next:
            safe.append("<redacted>")
            redact_next = False
            continue
        if _SENSITIVE.search(part):
            if "=" in part:
                safe.append(part.split("=", 1)[0] + "=<redacted>")
            else:
                safe.append(part)
                redact_next = True
            continue
        safe.append(part[:_MAX_STRING])
    return " ".join(safe)[:_MAX_STRING]


def _thread_snapshot(include_stacks: bool = True) -> list[dict[str, Any]]:
    frames = sys._current_frames() if include_stacks else {}
    result: list[dict[str, Any]] = []
    for thread in threading.enumerate()[:_MAX_THREADS]:
        try:
            item: dict[str, Any] = {
                "name": _safe_string(thread.name, 96),
                "ident": thread.ident,
                "native_id": getattr(thread, "native_id", None),
                "daemon": bool(thread.daemon),
                "alive": bool(thread.is_alive()),
            }
            if include_stacks:
                frame = frames.get(thread.ident)
                stack: list[dict[str, Any]] = []
                for _ in range(4):
                    if frame is None:
                        break
                    code = frame.f_code
                    stack.append({
                        "file": os.path.basename(_safe_string(code.co_filename, 160)),
                        "function": _safe_string(code.co_name, 96),
                        "line": int(frame.f_lineno),
                    })
                    frame = frame.f_back
                item["top_frames"] = stack
            result.append(item)
        except Exception:
            continue
    return result


def _read_proc_status(pid: int) -> dict[str, Any]:
    result: dict[str, Any] = {"pid": pid, "ppid": None, "state": None, "rss_bytes": None, "thread_count": None, "name": None}
    try:
        for line in Path(f"/proc/{pid}/status").read_text(errors="replace").splitlines():
            key, _, value = line.partition(":")
            value = value.strip()
            if key == "PPid":
                result["ppid"] = int(value)
            elif key == "State":
                result["state"] = value[:32]
            elif key == "VmRSS":
                result["rss_bytes"] = int(value.split()[0]) * 1024
            elif key == "Threads":
                result["thread_count"] = int(value)
            elif key == "Name":
                result["name"] = value[:96]
    except (OSError, ValueError):
        pass
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_text(errors="replace")
        result["command"] = _sanitize_cmdline(cmdline)
    except OSError:
        result["command"] = result.get("name")
    result["alive"] = Path(f"/proc/{pid}").exists()
    return result


def _process_snapshot() -> list[dict[str, Any]]:
    pids: set[int] = {os.getpid()}
    try:
        pids.update(child.pid for child in multiprocessing.active_children() if child.pid)
    except Exception:
        pass
    proc_root = Path("/proc")
    if proc_root.is_dir():
        parent_map: dict[int, int] = {}
        for entry in list(proc_root.iterdir())[:512]:
            if not entry.name.isdigit():
                continue
            status = _read_proc_status(int(entry.name))
            ppid = status.get("ppid")
            if isinstance(ppid, int):
                parent_map[int(entry.name)] = ppid
        changed = True
        while changed and len(pids) < _MAX_PROCESSES:
            changed = False
            for pid, ppid in parent_map.items():
                if ppid in pids and pid not in pids:
                    pids.add(pid)
                    changed = True
                    if len(pids) >= _MAX_PROCESSES:
                        break
    result = [_read_proc_status(pid) for pid in sorted(pids)[:_MAX_PROCESSES]]
    if not proc_root.is_dir():
        result = []
        try:
            psutil = sys.modules.get("psutil")
            if psutil is not None:
                root = psutil.Process(os.getpid())
                result.append({
                    "pid": root.pid,
                    "ppid": root.ppid(),
                    "state": root.status(),
                    "command": _sanitize_cmdline(" ".join(root.cmdline())),
                    "thread_count": root.num_threads(),
                    "rss_bytes": root.memory_info().rss,
                    "alive": root.is_running(),
                })
                for process in root.children(recursive=True)[:_MAX_PROCESSES - 1]:
                    result.append({
                        "pid": process.pid,
                        "ppid": process.ppid(),
                        "state": process.status(),
                        "command": _sanitize_cmdline(" ".join(process.cmdline())),
                        "thread_count": process.num_threads(),
                        "rss_bytes": process.memory_info().rss,
                        "alive": process.is_running(),
                    })
        except Exception:
            result = [{"pid": os.getpid(), "ppid": os.getppid(), "alive": True}]
    return result


class TeardownDiagnostics:
    """Emit bounded teardown events only when explicitly enabled."""

    def __init__(
        self,
        *,
        container_session_id: str = "",
        restored_instance_id: str = "",
        modal_input_id: str = "",
        modal_task_id: str = "",
    ) -> None:
        self._enabled = diagnostics_enabled()
        self._lock = threading.RLock()
        self._identity: dict[str, str] = {
            "container_session_id": _safe_string(container_session_id),
            "restored_instance_id": _safe_string(restored_instance_id),
            "modal_input_id": _safe_string(modal_input_id),
            "modal_task_id": _safe_string(modal_task_id),
            "modal_container_id": _safe_string(os.environ.get("MODAL_CONTAINER_ID", "")),
            "request_id": "",
        }
        self._paths: dict[str, str] = {}
        self._providers: dict[str, Callable[[], Any]] = {}
        self._written_files: list[dict[str, str]] = []
        self._started_ns: dict[tuple[str, str], int] = {}
        with _ATExit_LOCK:
            _INSTANCES.append(self)
        self._ensure_atexit()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _ensure_atexit(self) -> None:
        if not self._enabled:
            return
        global _ATExit_REGISTERED
        with _ATExit_LOCK:
            if _ATExit_REGISTERED:
                return
            atexit.register(_emit_python_atexit)
            _ATExit_REGISTERED = True

    def set_identity(self, **values: Any) -> None:
        if not self._enabled:
            return
        with self._lock:
            for key in self._identity:
                if key in values and values[key] is not None:
                    value = _safe_string(values[key])
                    if value:
                        self._identity[key] = value
            self._ensure_atexit()

    def configure_paths(self, **paths: Any) -> None:
        if not self._enabled:
            return
        with self._lock:
            for key, value in paths.items():
                if value:
                    self._paths[key] = os.path.abspath(_safe_string(value))

    def register_provider(self, name: str, provider: Callable[[], Any]) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._providers[_safe_string(name, 96)] = provider

    def record_file_write(self, path: Any, *, volume: str = "") -> None:
        if not self._enabled or not path:
            return
        item = {"path": os.path.abspath(_safe_string(path, 512)), "volume": _safe_string(volume, 96)}
        with self._lock:
            if item not in self._written_files:
                self._written_files.append(item)
                if len(self._written_files) > 128:
                    del self._written_files[:-128]

    def snapshot(self, *, include_stacks: bool = True) -> dict[str, Any]:
        if not self._enabled:
            return {}
        with self._lock:
            providers = dict(self._providers)
            paths = dict(self._paths)
            written = list(self._written_files)
        known: dict[str, Any] = {}
        for name, provider in providers.items():
            try:
                known[name] = _safe_value(provider())
            except Exception as exc:
                known[name] = {"error_type": type(exc).__name__}
        fds: list[dict[str, str]] = []
        fd_count: int | None = None
        proc_fd = Path("/proc/self/fd")
        if proc_fd.is_dir():
            try:
                entries = list(proc_fd.iterdir())[:_MAX_FDS]
                fd_count = len(entries)
                roots = tuple(path for path in paths.values() if path)
                for entry in entries:
                    try:
                        target = os.readlink(entry)
                    except OSError:
                        continue
                    if roots and any(os.path.abspath(target).startswith(root) for root in roots):
                        fds.append({"fd": entry.name, "target": target[:512]})
            except OSError:
                pass
        if fd_count is None:
            try:
                psutil = sys.modules.get("psutil")
                process = psutil.Process() if psutil is not None else None
                if process is not None:
                    fd_count = getattr(process, "num_fds", lambda: process.num_handles())()
            except Exception:
                pass
        cuda: dict[str, Any] = {"initialized": False}
        torch = sys.modules.get("torch")
        try:
            cuda_api = getattr(torch, "cuda", None) if torch is not None else None
            initialized = bool(cuda_api is not None and cuda_api.is_initialized())
            cuda["initialized"] = initialized
            if initialized:
                cuda["device_index"] = int(cuda_api.current_device())
                cuda["memory_allocated"] = int(cuda_api.memory_allocated())
                cuda["memory_reserved"] = int(cuda_api.memory_reserved())
                cuda["synchronization_pending"] = "unavailable"
        except Exception:
            cuda["status"] = "unavailable"
        return {
            "threads": _thread_snapshot(include_stacks=include_stacks),
            "async_tasks": _async_task_snapshot(),
            "processes": _process_snapshot(),
            "known_runtime_objects": known,
            "file_descriptors": {
                "count": fd_count,
                "mounted_volume_descriptors": fds,
                "paths": paths,
                "files_written": written,
            },
            "cuda": cuda,
        }

    def emit(self, event: str, *, elapsed_ms: float | None = None, stage: str = "", snapshot: bool = True, **fields: Any) -> None:
        if not self._enabled:
            return
        now_wall = time.time_ns()
        now_mono = time.monotonic_ns()
        key = (event, stage)
        if event.endswith("_start"):
            with self._lock:
                self._started_ns[key] = now_mono
            if elapsed_ms is None:
                elapsed_ms = 0.0
        elif elapsed_ms is None:
            start_key = (event[:-4] + "_start", stage) if event.endswith("_end") else None
            if start_key is not None:
                with self._lock:
                    start = self._started_ns.get(start_key)
                if start is not None:
                    elapsed_ms = (now_mono - start) / 1_000_000.0
        with self._lock:
            payload: dict[str, Any] = {
                "event": _safe_string(event, 96),
                "wall_unix_ns": now_wall,
                "monotonic_ns": now_mono,
                "pid": os.getpid(),
                "ppid": os.getppid(),
                **self._identity,
                "elapsed_ms": round(float(elapsed_ms), 3) if elapsed_ms is not None else None,
            }
        if stage:
            payload["stage"] = _safe_string(stage, 96)
        payload.update({
            key: "<redacted>" if _SENSITIVE.search(str(key)) else _safe_value(value)
            for key, value in fields.items()
        })
        if snapshot:
            payload["snapshot"] = self.snapshot(include_stacks=True)
        try:
            print(f"{PREFIX} {json.dumps(payload, sort_keys=True, separators=(',', ':'))}", flush=True)
        except Exception:
            pass


def _async_task_snapshot() -> list[dict[str, Any]]:
    try:
        loop = asyncio.get_running_loop()
        tasks = list(asyncio.all_tasks(loop))[:_MAX_ITEMS]
    except RuntimeError:
        return []
    result: list[dict[str, Any]] = []
    for task in tasks:
        try:
            coroutine = task.get_coro()
            result.append({
                "name": _safe_string(task.get_name(), 96),
                "done": bool(task.done()),
                "cancelled": bool(task.cancelled()),
                "coroutine": _safe_string(
                    getattr(coroutine, "__qualname__", type(coroutine).__name__), 160,
                ),
            })
        except Exception:
            continue
    return result


def _emit_python_atexit() -> None:
    if not diagnostics_enabled():
        return
    payload = {
        "event": "python_atexit",
        "wall_unix_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "container_session_id": os.environ.get("COMFYMODAL_CONTAINER_SESSION_ID", ""),
        "restored_instance_id": os.environ.get("COMFYMODAL_RESTORED_INSTANCE_ID", ""),
        "modal_input_id": os.environ.get("COMFYMODAL_INPUT_ID", ""),
        "modal_task_id": os.environ.get("MODAL_TASK_ID", ""),
        "modal_container_id": os.environ.get("MODAL_CONTAINER_ID", ""),
        "elapsed_ms": None,
        "thread_summary": _thread_snapshot(include_stacks=False),
    }
    try:
        print(f"{PREFIX} {json.dumps(payload, sort_keys=True, separators=(',', ':'))}", flush=True)
    except Exception:
        pass


def record_volume_write(path: Any, *, volume: str = "") -> None:
    for instance in list(_INSTANCES):
        instance.record_file_write(path, volume=volume)


def record_volume_commit(path: Any = "") -> None:
    return None
