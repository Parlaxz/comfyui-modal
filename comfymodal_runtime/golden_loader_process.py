"""Golden loader-process experiment (disabled by default).

Two related experimental modes, both default OFF:

* ``COMFYMODAL_GOLDEN_LOADER_PROCESS`` (request-time worker): one persistent
  ``spawn`` worker runs the three canonical Golden loaders; the parent
  receives the worker's CUDA view tensors through PyTorch CUDA IPC
  (``torch.multiprocessing`` reductions) and re-binds them with the same
  canonical constructors + pointer-identity proofs.  Literal wrapper transfer
  is blocked (local classes/lambdas, native AIMDO handles), so only the CUDA
  storage crosses.

* ``COMFYMODAL_GOLDEN_LOADER_PROCESS_PRESNAPSHOT`` (pre-snapshot worker): the
  CPU-only worker is spawned *before* Modal captures the CPU memory snapshot
  so its spawn/import cost leaves the request critical path.  The worker must
  stay CUDA-clean until after restore; on restore the parent verifies the same
  process + IPC channel survived (PING/PONG, PID/start-ticks/uuid identity,
  no respawn) and then uses it for the three full loads.  A missing or dead
  worker fails closed — it is never replaced by a request-time spawn.

When both switches are OFF (default) this module is never entered by the
Golden path and behavior is unchanged.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import torch
import torch.multiprocessing as torch_mp  # registers CUDA-IPC reductions

from . import golden_serial as gs

GOLDEN_LOADER_PROCESS_ENV = "COMFYMODAL_GOLDEN_LOADER_PROCESS"
GOLDEN_LOADER_PROCESS_PRESNAPSHOT_ENV = "COMFYMODAL_GOLDEN_LOADER_PROCESS_PRESNAPSHOT"

# The three existing operations under test.  Order is fixed and serial.
LOADER_KINDS = ("clip", "unet", "vae")
STAGE_NAMES = {
    "clip": "golden_clip_load",
    "unet": "golden_unet_load",
    "vae": "golden_vae_load",
}
STARTUP_TIMEOUT_S = 900.0
REPLY_TIMEOUT_S = 1800.0
STOP_TIMEOUT_S = 60.0
PROBE_TIMEOUT_S = 20.0

_TRUTHY = {"1", "true", "yes", "on"}

# Parent-side hold of the pre-snapshot worker.  Module state created before
# snapshot capture is reachable after restore because Modal resumes the same
# process image.
_PRE_SNAPSHOT_WORKER: Optional["GoldenLoaderProcess"] = None
_PRE_SNAPSHOT_RECORD: dict = {}
_SPAWN_COUNT = 0

# Child-side CUDA-work counter: proves the pre-snapshot worker never touched
# CUDA before the restore.
_CUDA_TASK_COUNT = 0


def loader_process_enabled() -> bool:
    """Return True only when the request-time loader-process switch is ON."""
    return str(os.environ.get(GOLDEN_LOADER_PROCESS_ENV) or "").strip().lower() in _TRUTHY


def presnapshot_loader_enabled() -> bool:
    """Return True only when the pre-snapshot loader-worker switch is ON."""
    return (
        str(os.environ.get(GOLDEN_LOADER_PROCESS_PRESNAPSHOT_ENV) or "").strip().lower()
        in _TRUTHY
    )


def loader_spawn_count() -> int:
    return int(_SPAWN_COUNT)


def get_pre_snapshot_worker() -> Optional["GoldenLoaderProcess"]:
    return _PRE_SNAPSHOT_WORKER


def pre_snapshot_record() -> dict:
    return dict(_PRE_SNAPSHOT_RECORD)


def _bounded_stats(value: Any, depth: int = 0) -> Any:
    """Keep transport statistics picklable and small (drop bulk arrays)."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if depth > 4:
        return None
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            bounded = _bounded_stats(item, depth + 1)
            if bounded is not None:
                out[str(key)] = bounded
        return out
    if isinstance(value, (list, tuple)):
        if len(value) > 64:
            return None
        return [_bounded_stats(item, depth + 1) for item in value]
    return None


def _stage_interval(session: Any, name: str) -> dict:
    interval = getattr(getattr(session, "recorder", None), "_intervals", {}).get(name)
    if interval is None:
        return {}
    entry = getattr(interval, "entry_monotonic_ns", None)
    end = getattr(interval, "end_monotonic_ns", None)
    return {
        "entry_monotonic_ns": entry,
        "end_monotonic_ns": end,
        "entry_wall_ns": getattr(interval, "entry_wall_ns", None),
        "end_wall_ns": getattr(interval, "end_wall_ns", None),
        "ready_monotonic_ns": getattr(interval, "ready_monotonic_ns", None),
        "wall_ms": (
            (int(end) - int(entry)) / 1e6
            if isinstance(entry, (int, float)) and isinstance(end, (int, float))
            else None
        ),
    }


def _transport_payload(transport: dict) -> dict:
    owner = transport.get("owner")
    return {
        "sd": transport["sd"],
        "stats": _bounded_stats(transport.get("stats") or {}),
        "header_metadata": transport.get("header_metadata"),
        "base_buf": owner.gpu_buf if owner is not None else None,
        "gpu_bytes": int((transport.get("stats") or {}).get("gpu_bytes", 0) or 0),
    }


def _literal_probe(session: Any) -> dict:
    """Prove/refute the literal wrapper handoff for the loaded objects."""
    from multiprocessing.reduction import ForkingPickler

    out: dict[str, str] = {}
    for name in ("clip", "patcher", "vae"):
        obj = getattr(session, name, None)
        if obj is None:
            out[name] = "absent"
            continue
        try:
            ForkingPickler.dumps(obj)
            out[name] = "pickled_ok"
        except BaseException as exc:  # noqa: BLE001 - probe records the blocker
            out[name] = f"{type(exc).__name__}: {str(exc)[:220]}"
    return out


def _proc_start_ticks(pid: Optional[int]) -> Optional[int]:
    """Linux /proc/<pid>/stat starttime (field 22): process creation marker."""
    if not pid:
        return None
    try:
        text = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8")
        after_comm = text.rsplit(")", 1)[1].split()
        return int(after_comm[19])
    except Exception:
        return None


def _safe_fileno(conn: Any) -> Optional[int]:
    try:
        value = conn.fileno()
        return int(value) if value is not None else None
    except Exception:
        return None


def _child_status(state: dict, conn: Any) -> dict:
    """Serializable child lifecycle/liveness evidence."""
    return {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "uuid": str(state.get("uuid") or ""),
        "session_generation": int(state.get("session_generation") or 0),
        "cuda_initialized": bool(torch.cuda.is_initialized()),
        "cuda_tasks_run": int(_CUDA_TASK_COUNT),
        "cuda_init_wall_ms": state.get("cuda_init_wall_ms"),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "proc_start_ticks": _proc_start_ticks(os.getpid()),
        "conn_fileno": _safe_fileno(conn),
        "mono_ns": time.monotonic_ns(),
    }


def _install_transport_capture(captured: dict) -> None:
    original_read = gs.read_file_qd_gpu

    def _capture_transport(path: Any, *, role: Optional[str] = None, **kwargs: Any) -> Any:
        result = original_read(path, role=role, **kwargs)
        if role in captured:
            captured[role].append(result)
        return result

    gs.read_file_qd_gpu = _capture_transport


def _initialize_session(state: dict, payload: dict) -> None:
    session = gs.GoldenSession(
        payload["request"],
        volume=None,
        volume_mount_root=None,
        output_root=payload.get("output_root"),
        contract=payload["contract"],
    )
    session.model_paths = dict(payload["model_paths"])
    session.clip_paths = list(payload["clip_paths"])
    state["session"] = session
    state["session_generation"] = int(state.get("session_generation") or 0) + 1


def _apply_cuda_env(env: Any) -> dict:
    """Adopt the parent's current GPU-visibility env (restored child env is stale)."""
    applied: dict = {}
    if not isinstance(env, dict):
        return applied
    for key in (
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "NVIDIA_DRIVER_CAPABILITIES",
    ):
        value = env.get(key)
        if isinstance(value, str) and value:
            if os.environ.get(key) != value:
                os.environ[key] = value
                applied[key] = value[:160]
    return applied


def _initialize_cuda(state: dict) -> None:
    global _CUDA_TASK_COUNT
    if state.get("cuda_ready"):
        return
    started_ns = time.perf_counter_ns()
    from .golden_aimdo_activation import activate_golden_dynamic_vram

    activation = activate_golden_dynamic_vram()
    torch.cuda.init()
    _CUDA_TASK_COUNT += 1
    state["activation"] = {
        key: activation.get(key)
        for key in (
            "activated",
            "already_activated",
            "aimdo_import_version_or_none",
            "patcher_class_name",
            "is_dynamic_alias",
        )
    }
    state["cuda_ready"] = True
    state["cuda_init_wall_ms"] = (time.perf_counter_ns() - started_ns) / 1e6


def _format_exc_chain(exc: BaseException, limit: int = 1200) -> str:
    """Surface the full cause chain: activation failures wrap an inner import."""
    parts: list[str] = []
    current: Optional[BaseException] = exc
    depth = 0
    while current is not None and depth < 5:
        parts.append(f"{depth}:{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
        depth += 1
    return " | ".join(parts)[:limit]


def _traceback_tail(exc: BaseException, limit: int = 1200) -> str:
    import traceback

    try:
        text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        return text[-limit:]
    except Exception:
        return ""


def cuda_visibility_probe() -> dict:
    """Environment/device visibility evidence for CUDA (parent or child)."""
    import ctypes
    import glob
    import sys as _sys

    out: dict = {}
    for name in (
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "NVIDIA_DRIVER_CAPABILITIES",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
    ):
        out[name] = (os.environ.get(name) or "")[:300]
    out["pid"] = os.getpid()
    out["ppid"] = os.getppid()
    out["cmdline_env_nvidia"] = sorted(
        key for key in os.environ if "NVIDIA" in key.upper() or "CUDA" in key.upper()
    )[:20]
    try:
        out["dev_nvidia"] = sorted(
            os.path.basename(path) for path in glob.glob("/dev/nvidia*")
        )[:20]
    except Exception:
        out["dev_nvidia"] = []
    try:
        lib = ctypes.CDLL("libcuda.so.1")
        out["libcuda_load"] = "ok"
        try:
            out["cuInit_rc"] = int(lib.cuInit(0))
        except Exception as exc:  # noqa: BLE001
            out["cuInit_rc"] = f"{type(exc).__name__}: {exc}"[:120]
        try:
            count = ctypes.c_int(-1)
            rc = int(lib.cuDeviceGetCount(ctypes.byref(count)))
            out["cuDeviceGetCount_rc"] = rc
            out["cuDeviceGetCount"] = int(count.value)
        except Exception as exc:  # noqa: BLE001
            out["cuDeviceGetCount"] = f"{type(exc).__name__}: {exc}"[:120]
    except Exception as exc:  # noqa: BLE001
        out["libcuda_load"] = f"{type(exc).__name__}: {exc}"[:200]
    try:
        out["torch_device_count"] = int(torch.cuda.device_count())
    except Exception as exc:  # noqa: BLE001
        out["torch_device_count_error"] = f"{type(exc).__name__}: {exc}"[:200]
    try:
        out["torch_is_available"] = bool(torch.cuda.is_available())
    except Exception as exc:  # noqa: BLE001
        out["torch_is_available_error"] = f"{type(exc).__name__}: {exc}"[:200]
    out["preexisting_torch_cuda_modules"] = sorted(
        name for name in _sys.modules if name.startswith(("torch.cuda", "nvidia"))
    )[:20]
    return out


def _diagnose_cuda_init_failure(exc: BaseException) -> dict:
    """Post-failure probe: which fresh imports work after restore in the child."""
    import importlib
    import sys as _sys

    results: dict[str, Any] = {}
    for name in (
        "comfy_aimdo",
        "comfy_aimdo.control",
        "comfy_aimdo.host_buffer",
        "comfy_aimdo.model_vbar",
        "comfy.model_patcher",
        "comfy.memory_management",
        "comfy.sd",
    ):
        try:
            module = importlib.import_module(name)
            results[name] = f"ok:{getattr(module, '__file__', '')}"
        except BaseException as probe_exc:  # noqa: BLE001 - diagnostic only
            results[name] = f"{type(probe_exc).__name__}: {probe_exc}"[:300]
    try:
        results["torch_cuda_is_initialized"] = bool(torch.cuda.is_initialized())
        results["torch_cuda_is_available"] = bool(torch.cuda.is_available())
    except BaseException as probe_exc:  # noqa: BLE001 - diagnostic only
        results["torch_cuda_probe"] = f"{type(probe_exc).__name__}: {probe_exc}"[:200]
    results["loaded_modules"] = sorted(
        name for name in _sys.modules if name.startswith(("comfy_aimdo", "comfy."))
    )[:40]
    results["cuda_visible_devices"] = os.environ.get("CUDA_VISIBLE_DEVICES")
    results["exception_chain"] = _format_exc_chain(exc)
    results["traceback_tail"] = _traceback_tail(exc)
    results["cuda_visibility"] = cuda_visibility_probe()
    return results


def _run_child_load(session: Any, captured: dict, kind: str) -> dict:
    if session is None:
        raise RuntimeError("loader_session_not_initialized")
    started_ns = time.perf_counter_ns()
    if kind == "clip":
        asyncio.run(gs.golden_clip_load(session))
        transports = list(captured["clip"])
        captured["clip"].clear()
    elif kind == "unet":
        asyncio.run(gs.golden_unet_load(session))
        transports = [captured["unet"].pop()]
    elif kind == "vae":
        asyncio.run(gs.golden_vae_load(session))
        transports = [captured["vae"].pop()]
    else:
        raise RuntimeError(f"loader_kind_invalid:{kind}")
    payloads = [_transport_payload(t) for t in transports]
    return {
        "op": "loaded",
        "kind": kind,
        "child_pid": os.getpid(),
        "child_total_ms": (time.perf_counter_ns() - started_ns) / 1e6,
        "child_stage_ms": (_stage_interval(session, STAGE_NAMES[kind]) or {}).get("wall_ms"),
        "child_stage_interval": _stage_interval(session, STAGE_NAMES[kind]),
        "tensor_count": sum(len(p["sd"]) for p in payloads),
        "h2d_completed_bytes": sum(
            int((p.get("stats") or {}).get("h2d_completed_bytes", 0) or 0)
            for p in payloads
        ),
        "transports": payloads,
    }


def _child_main(conn: Any, presnapshot: bool = False) -> None:
    """Spawn-child entry: serve serial load tickets and lifecycle probes."""
    state: dict = {
        "uuid": "",
        "session": None,
        "captured": {"clip": [], "unet": [], "vae": []},
        "session_generation": 0,
        "cuda_ready": False,
        "cuda_init_wall_ms": None,
        "activation": {},
    }
    try:
        _install_transport_capture(state["captured"])
        first = conn.recv()
        if presnapshot:
            # CPU-only start: no session, no CUDA.  READY may be captured into
            # the memory snapshot exactly as sent.
            state["uuid"] = str(first.get("uuid") or "")
            conn.send({"op": "presnapshot_ready", **_child_status(state, conn)})
        else:
            _initialize_session(state, first)
            _initialize_cuda(state)
            conn.send({
                "op": "ready",
                **_child_status(state, conn),
                "activation": dict(state.get("activation") or {}),
            })

        while True:
            try:
                msg = conn.recv()
            except EOFError:
                return
            if not isinstance(msg, dict):
                continue
            op = msg.get("op")
            if op == "ping":
                conn.send({
                    "op": "pong",
                    "nonce": msg.get("nonce"),
                    **_child_status(state, conn),
                })
            elif op == "init":
                try:
                    _initialize_session(state, msg)
                except BaseException as exc:  # noqa: BLE001 - reported to parent
                    conn.send({
                        "op": "error", "kind": "init",
                        "error": f"{type(exc).__name__}: {exc}"[:400],
                    })
                else:
                    conn.send({"op": "initialized", **_child_status(state, conn)})
            elif op == "init_cuda":
                env_applied: dict = {}
                try:
                    env_applied = _apply_cuda_env(msg.get("env"))
                    _initialize_cuda(state)
                except BaseException as exc:  # noqa: BLE001 - reported to parent
                    conn.send({
                        "op": "error", "kind": "init_cuda",
                        "error": _format_exc_chain(exc),
                        "diagnostic": _diagnose_cuda_init_failure(exc),
                        "env_applied": env_applied,
                    })
                else:
                    conn.send({
                        "op": "cuda_initialized",
                        **_child_status(state, conn),
                        "env_applied": env_applied,
                        "visibility_after": cuda_visibility_probe(),
                    })
            elif op == "load":
                kind = str(msg.get("kind") or "")
                try:
                    reply = _run_child_load(state.get("session"), state["captured"], kind)
                except BaseException as exc:  # noqa: BLE001 - reported to parent
                    conn.send({
                        "op": "error", "kind": kind,
                        "error": f"{type(exc).__name__}: {exc}"[:400],
                    })
                else:
                    conn.send(reply)
            elif op == "stop":
                session = state.get("session")
                conn.send({
                    "op": "stopped",
                    "pid": os.getpid(),
                    "literal_probe": _literal_probe(session) if session is not None else {},
                    **_child_status(state, conn),
                })
                return
    except BaseException as exc:  # noqa: BLE001 - report startup/loop failure
        try:
            conn.send({"op": "fatal", "error": f"{type(exc).__name__}: {exc}"[:400]})
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


@dataclass
class GoldenLoaderProcess:
    """One persistent spawn worker; serial tickets only, no overlap."""

    _ctx: Any = field(default=None, repr=False)
    _process: Any = field(default=None, repr=False)
    _conn: Any = field(default=None, repr=False)
    startup_ms: Optional[float] = None
    pid_value: Optional[int] = None
    child_info: dict = field(default_factory=dict)
    presnapshot: bool = False
    presnapshot_uuid: str = ""
    pre_snapshot_pid: Optional[int] = None
    pre_snapshot_conn_fileno: Optional[int] = None
    pre_snapshot_child_fileno: Optional[int] = None
    pre_snapshot_proc_start_ticks: Optional[int] = None
    pre_snapshot_reply: dict = field(default_factory=dict)

    @property
    def pid(self) -> Optional[int]:
        return self.pid_value

    @staticmethod
    def _await_reply(
        conn: Any, proc: Any, timeout_s: float, expect_ops: tuple[str, ...]
    ) -> dict:
        deadline = time.monotonic() + float(timeout_s)
        while True:
            if conn.poll(0.25):
                reply = conn.recv()
                if isinstance(reply, dict) and reply.get("op") in set(expect_ops):
                    return reply
                raise RuntimeError(f"loader_process_unexpected_reply:{str(reply)[:200]}")
            if proc is None or not proc.is_alive():
                raise RuntimeError("loader_process_died")
            if time.monotonic() > deadline:
                raise RuntimeError("loader_process_timeout")

    def start(
        self,
        *,
        request: Any = None,
        contract: Any = None,
        model_paths: Optional[dict] = None,
        clip_paths: Optional[list] = None,
        output_root: Optional[str] = None,
        presnapshot: bool = False,
        startup_timeout_s: float = STARTUP_TIMEOUT_S,
    ) -> float:
        """Start the worker; return its separate startup wall ms.

        ``presnapshot=True`` starts a CPU-only worker (no session, no CUDA)
        intended to be captured into the Modal memory snapshot; the session
        is initialized after restore via :meth:`initialize_session`.
        """
        global _SPAWN_COUNT
        started_ns = time.perf_counter_ns()
        ctx = torch_mp.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe(duplex=True)
        proc = ctx.Process(target=_child_main, args=(child_conn, bool(presnapshot)), daemon=True)
        proc.start()
        _SPAWN_COUNT += 1
        try:
            child_conn.close()
        except Exception:
            pass
        try:
            if presnapshot:
                presnapshot_uuid = uuid.uuid4().hex
                parent_conn.send({"op": "presnapshot_init", "uuid": presnapshot_uuid})
                reply = self._await_reply(
                    parent_conn, proc, startup_timeout_s, ("presnapshot_ready",)
                )
            else:
                parent_conn.send({
                    "op": "init",
                    "request": request,
                    "contract": contract,
                    "model_paths": dict(model_paths or {}),
                    "clip_paths": list(clip_paths or []),
                    "output_root": output_root,
                })
                reply = self._await_reply(parent_conn, proc, startup_timeout_s, ("ready",))
        except BaseException:
            try:
                parent_conn.close()
            except Exception:
                pass
            proc.terminate()
            raise
        self._ctx = ctx
        self._process = proc
        self._conn = parent_conn
        reply_pid = reply.get("pid")
        proc_pid = proc.pid
        self.pid_value = int(reply_pid) if reply_pid else (int(proc_pid) if proc_pid else None)
        self.child_info = dict(reply)
        self.presnapshot = bool(presnapshot)
        self.pre_snapshot_pid = self.pid_value
        self.pre_snapshot_conn_fileno = _safe_fileno(parent_conn)
        self.pre_snapshot_child_fileno = reply.get("conn_fileno")
        self.pre_snapshot_proc_start_ticks = reply.get("proc_start_ticks")
        if presnapshot:
            self.presnapshot_uuid = str(reply.get("uuid") or "")
        self.pre_snapshot_reply = dict(reply)
        self.startup_ms = (time.perf_counter_ns() - started_ns) / 1e6
        return self.startup_ms

    def _wait_reply(self, timeout_s: float) -> dict:
        deadline = time.monotonic() + float(timeout_s)
        conn, proc = self._conn, self._process
        while not conn.poll(1.0):
            if proc is None or not proc.is_alive():
                raise RuntimeError("loader_process_died")
            if time.monotonic() > deadline:
                raise RuntimeError("loader_process_timeout")
        reply = conn.recv()
        if not isinstance(reply, dict):
            raise RuntimeError("loader_process_bad_reply")
        return reply

    def probe(
        self, *, anchor_monotonic_ns: Optional[int] = None, timeout_s: float = PROBE_TIMEOUT_S
    ) -> dict:
        """Verify the (snapshotted) worker process + IPC channel are alive.

        Never spawns a replacement; returns evidence with ``ok`` False when
        any identity/liveness check fails.
        """
        evidence: dict = {
            "anchor_monotonic_ns": anchor_monotonic_ns,
            "pre_pid": self.pre_snapshot_pid,
            "presnapshot_uuid": self.presnapshot_uuid,
            "spawn_count": loader_spawn_count(),
        }
        if self._conn is None or self._process is None:
            evidence.update({"ok": False, "error": "worker_object_missing"})
            return evidence
        started_ns = time.perf_counter_ns()

        def _since(anchor: Optional[int], now_ns: int) -> Optional[float]:
            return round((now_ns - anchor) / 1e6, 3) if anchor else None

        alive = bool(self._process.is_alive())
        alive_ns = time.perf_counter_ns()
        evidence.update({
            "alive": alive,
            "pid": self.pid_value,
            "alive_ms": round((alive_ns - started_ns) / 1e6, 3),
            "alive_since_anchor_ms": _since(anchor_monotonic_ns, alive_ns),
            "conn_fileno": _safe_fileno(self._conn),
            "child_fileno_pre_capture": self.pre_snapshot_child_fileno,
        })
        if not alive:
            evidence.update({"ok": False, "error": "worker_process_not_alive"})
            return evidence
        nonce = uuid.uuid4().hex
        send_ns = time.perf_counter_ns()
        try:
            self._conn.send({"op": "ping", "nonce": nonce})
        except Exception as exc:  # noqa: BLE001 - report, fail closed
            evidence.update({
                "ok": False,
                "error": f"ping_send_failed:{type(exc).__name__}:{exc}"[:200],
                "ping_sent_since_anchor_ms": _since(anchor_monotonic_ns, send_ns),
            })
            return evidence
        deadline = time.monotonic() + float(timeout_s)
        pong = None
        while time.monotonic() < deadline:
            if self._conn.poll(0.25):
                pong = self._conn.recv()
                break
        pong_ns = time.perf_counter_ns()
        if not isinstance(pong, dict) or pong.get("op") != "pong" or pong.get("nonce") != nonce:
            evidence.update({
                "ok": False,
                "error": f"pong_invalid:{str(pong)[:160]}",
                "ping_sent_since_anchor_ms": _since(anchor_monotonic_ns, send_ns),
                "pong_since_anchor_ms": _since(anchor_monotonic_ns, pong_ns),
            })
            return evidence
        evidence.update({
            "child": {
                key: pong.get(key)
                for key in (
                    "pid", "ppid", "uuid", "session_generation", "cuda_initialized",
                    "cuda_tasks_run", "cuda_init_wall_ms", "proc_start_ticks",
                    "conn_fileno", "torch_version", "cuda_version", "mono_ns",
                )
            },
            "ping_sent_ms": round((send_ns - started_ns) / 1e6, 3),
            "pong_recv_ms": round((pong_ns - started_ns) / 1e6, 3),
            "ping_to_pong_ms": round((pong_ns - send_ns) / 1e6, 3),
            "ping_sent_since_anchor_ms": _since(anchor_monotonic_ns, send_ns),
            "pong_since_anchor_ms": _since(anchor_monotonic_ns, pong_ns),
        })
        child = evidence["child"]
        evidence.update({
            "pid_match": child.get("pid") == self.pre_snapshot_pid,
            "uuid_match": child.get("uuid") == self.presnapshot_uuid,
            "proc_start_ticks_match": (
                child.get("proc_start_ticks") == self.pre_snapshot_proc_start_ticks
            ),
            "child_fileno_match": (
                child.get("conn_fileno") == self.pre_snapshot_child_fileno
            ),
            "child_ppid_is_parent": child.get("ppid") == os.getpid(),
        })
        evidence["ok"] = bool(
            evidence["pid_match"]
            and evidence["uuid_match"]
            and evidence["proc_start_ticks_match"]
            and evidence["child_fileno_match"]
        )
        return evidence

    def initialize_session(
        self,
        *,
        request: Any,
        contract: Any,
        model_paths: dict,
        clip_paths: list,
        output_root: Optional[str] = None,
        timeout_s: float = 600.0,
    ) -> dict:
        """Post-restore session init for the pre-snapshot worker (CPU only)."""
        if self._conn is None or self._process is None or not self._process.is_alive():
            raise RuntimeError("loader_process_not_running")
        started_ns = time.perf_counter_ns()
        self._conn.send({
            "op": "init",
            "request": request,
            "contract": contract,
            "model_paths": dict(model_paths),
            "clip_paths": list(clip_paths),
            "output_root": output_root,
        })
        reply = self._wait_reply(timeout_s)
        if reply.get("op") != "initialized":
            raise RuntimeError(
                "presnapshot_session_init_failed:" + str(reply.get("error") or reply)[:300]
            )
        return {
            "child_pid": reply.get("pid"),
            "session_generation": reply.get("session_generation"),
            "child_cuda_initialized": reply.get("cuda_initialized"),
            "parent_roundtrip_ms": round((time.perf_counter_ns() - started_ns) / 1e6, 3),
        }

    def init_cuda(self, *, timeout_s: float = 1800.0) -> dict:
        """Post-restore first CUDA touch in the worker (activation + init).

        The restored child's environment is a copy from spawn time, so it can
        carry a stale GPU-visibility environment; the parent forwards its
        current values and the child adopts them before CUDA initialization.
        """
        if self._conn is None or self._process is None or not self._process.is_alive():
            raise RuntimeError("loader_process_not_running")
        started_ns = time.perf_counter_ns()
        env_payload = {
            key: os.environ.get(key)
            for key in (
                "CUDA_VISIBLE_DEVICES",
                "NVIDIA_VISIBLE_DEVICES",
                "NVIDIA_DRIVER_CAPABILITIES",
            )
            if os.environ.get(key)
        }
        self._conn.send({"op": "init_cuda", "env": env_payload})
        reply = self._wait_reply(timeout_s)
        if reply.get("op") != "cuda_initialized":
            diagnostic = reply.get("diagnostic")
            print(
                "[v2.presnapshot.cuda_fail] "
                + json.dumps(
                    {
                        "error": reply.get("error"),
                        "diagnostic": diagnostic,
                        "env_applied": reply.get("env_applied"),
                    },
                    sort_keys=True,
                    default=str,
                )[:3000],
                flush=True,
            )
            error = RuntimeError(
                "presnapshot_cuda_init_failed:" + str(reply.get("error") or reply)[:1200]
            )
            error.diagnostic = diagnostic  # type: ignore[attr-defined]
            raise error
        return {
            "child_pid": reply.get("pid"),
            "child_cuda_init_wall_ms": reply.get("cuda_init_wall_ms"),
            "parent_roundtrip_ms": round((time.perf_counter_ns() - started_ns) / 1e6, 3),
            "cuda_initialized": reply.get("cuda_initialized"),
            "cuda_tasks_run": reply.get("cuda_tasks_run"),
            "env_applied": reply.get("env_applied") or {},
            "visibility_after": reply.get("visibility_after") or {},
        }

    def load(self, kind: str, *, timeout_s: float = REPLY_TIMEOUT_S) -> dict:
        """Run one full canonical loader in the worker and receive its views.

        Returns the worker reply plus parent-measured ``roundtrip_ms`` and
        ``handoff_ms`` (roundtrip minus the worker's own stage wall).  Each
        transport carries a parent-side ``owner`` whose buffer is the same
        CUDA-IPC-mapped allocation, so canonical owner lifetime/registration
        code keeps working without a second allocation.
        """
        if self._conn is None or self._process is None or not self._process.is_alive():
            raise RuntimeError("loader_process_not_running")
        if kind not in LOADER_KINDS:
            raise RuntimeError(f"loader_kind_invalid:{kind}")
        started_ns = time.perf_counter_ns()
        self._conn.send({"op": "load", "kind": kind})
        reply = self._wait_reply(timeout_s)
        roundtrip_ms = (time.perf_counter_ns() - started_ns) / 1e6
        if reply.get("op") != "loaded":
            raise RuntimeError(
                "loader_process_load_failed:"
                + str(reply.get("error") or reply)[:400]
            )
        reply["roundtrip_ms"] = roundtrip_ms
        child_stage_ms = float(reply.get("child_stage_ms") or 0.0)
        reply["handoff_ms"] = roundtrip_ms - child_stage_ms
        transports = []
        for item in reply.get("transports") or []:
            base_buf = item.pop("base_buf", None)
            owner = (
                gs.GoldenQDOwner(base_buf, [], "cuda", kind)
                if base_buf is not None else None
            )
            item["owner"] = owner
            transports.append(item)
        reply["transports"] = transports
        return reply

    def stop(self, *, timeout_s: float = STOP_TIMEOUT_S) -> dict:
        """Stop the worker (releases child-side CUDA storage)."""
        conn, proc = self._conn, self._process
        self._conn = None
        self._process = None
        evidence: dict = {}
        try:
            if conn is not None:
                try:
                    conn.send({"op": "stop"})
                    deadline = time.monotonic() + float(timeout_s)
                    while not conn.poll(1.0):
                        if proc is None or not proc.is_alive() or time.monotonic() > deadline:
                            break
                    else:
                        reply = conn.recv()
                        if isinstance(reply, dict):
                            evidence = reply
                except Exception as exc:  # noqa: BLE001 - stop is best effort
                    evidence = {"stop_error": f"{type(exc).__name__}: {exc}"[:240]}
        finally:
            try:
                if proc is not None:
                    proc.join(timeout=10)
                    if proc.is_alive():
                        proc.terminate()
            finally:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass
        return evidence


def maybe_spawn_pre_snapshot_worker() -> dict:
    """Spawn the CPU-only pre-snapshot worker (idempotent, fail closed).

    Returns the pre-capture evidence record, or ``{}`` when the experimental
    switch is OFF.  Raises when the switch is ON and the worker cannot be
    started CUDA-clean; the snapshot startup then fails closed instead of
    silently degrading to request-time spawning.
    """
    global _PRE_SNAPSHOT_WORKER, _PRE_SNAPSHOT_RECORD
    if not presnapshot_loader_enabled():
        return {}
    if _PRE_SNAPSHOT_WORKER is not None and _PRE_SNAPSHOT_RECORD:
        return dict(_PRE_SNAPSHOT_RECORD)
    worker = GoldenLoaderProcess()
    startup_ms = worker.start(presnapshot=True)
    reply = dict(worker.pre_snapshot_reply or {})
    if reply.get("cuda_initialized"):
        raise RuntimeError("presnapshot_worker_cuda_not_clean")
    if int(reply.get("cuda_tasks_run") or 0) != 0:
        raise RuntimeError("presnapshot_worker_cuda_tasks_not_zero")
    if reply.get("ppid") != os.getpid():
        raise RuntimeError("presnapshot_worker_parent_mismatch")
    record = {
        "worker_pid": worker.pid_value,
        "pre_snapshot_uuid": worker.presnapshot_uuid,
        "parent_pid": os.getpid(),
        "child_ppid": reply.get("ppid"),
        "conn_fileno_parent": worker.pre_snapshot_conn_fileno,
        "conn_fileno_child": worker.pre_snapshot_child_fileno,
        "proc_start_ticks": worker.pre_snapshot_proc_start_ticks,
        "startup_ms": round(startup_ms, 3),
        "cuda_initialized": bool(reply.get("cuda_initialized")),
        "cuda_tasks_run": int(reply.get("cuda_tasks_run") or 0),
        "parent_cuda_initialized": bool(torch.cuda.is_initialized()),
        "torch_version": reply.get("torch_version"),
        "cuda_version": reply.get("cuda_version"),
        "spawn_count": loader_spawn_count(),
    }
    _PRE_SNAPSHOT_WORKER = worker
    _PRE_SNAPSHOT_RECORD = dict(record)
    print(
        "[v2.presnapshot.loader] " + json.dumps(record, sort_keys=True),
        flush=True,
    )
    return record


__all__ = [
    "GOLDEN_LOADER_PROCESS_ENV",
    "GOLDEN_LOADER_PROCESS_PRESNAPSHOT_ENV",
    "LOADER_KINDS",
    "GoldenLoaderProcess",
    "cuda_visibility_probe",
    "get_pre_snapshot_worker",
    "loader_process_enabled",
    "loader_spawn_count",
    "maybe_spawn_pre_snapshot_worker",
    "pre_snapshot_record",
    "presnapshot_loader_enabled",
]
