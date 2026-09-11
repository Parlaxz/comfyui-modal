"""Golden loader-process experiment (disabled by default).

Full-load handoff experiment: the three canonical Golden loaders run in ONE
persistent ``spawn`` worker; the parent receives the worker's CUDA view
tensors through PyTorch CUDA IPC (``torch.multiprocessing`` reductions) and
re-binds them with the same canonical constructors + pointer-identity proofs
(no second payload read, no second H2D).

Literal wrapper transfer is blocked in practice: ``ModelPatcherDynamic`` (all
three wrappers use it) creates native AIMDO handles in ``__init__``
(``comfy/model_patcher.py`` HostBuffer/ModelVBAR -> ``aimdo.dll`` ctypes
pointers), so the loaded *objects* cannot cross processes; only their CUDA
storage can, which is the minimal Python-side state the parent needs.

The worker stays alive for the whole request so the exported CUDA storage
lifetime is valid while the parent consumes the models; it is stopped after
Golden teardown.

When the switch is OFF (default) this module is never entered by the Golden
path and behavior is unchanged.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import torch
import torch.multiprocessing as torch_mp  # registers CUDA-IPC reductions

from . import golden_serial as gs

GOLDEN_LOADER_PROCESS_ENV = "COMFYMODAL_GOLDEN_LOADER_PROCESS"

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


def loader_process_enabled() -> bool:
    """Return True only when the experimental switch is explicitly ON."""
    return str(os.environ.get(GOLDEN_LOADER_PROCESS_ENV) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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


def _run_child_load(session: Any, captured: dict, kind: str) -> dict:
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


def _child_main(conn: Any) -> None:
    """Spawn-child entry: build the session, run the real loaders serially."""
    try:
        init = conn.recv()
        request = init["request"]
        contract = init["contract"]
        session = gs.GoldenSession(
            request,
            volume=None,
            volume_mount_root=None,
            output_root=init.get("output_root"),
            contract=contract,
        )
        session.model_paths = dict(init["model_paths"])
        session.clip_paths = list(init["clip_paths"])

        from .golden_aimdo_activation import activate_golden_dynamic_vram

        activation = activate_golden_dynamic_vram()
        torch.cuda.init()

        captured: dict[str, list] = {"clip": [], "unet": [], "vae": []}
        original_read = gs.read_file_qd_gpu

        def _capture_transport(path: Any, *, role: Optional[str] = None, **kwargs: Any) -> Any:
            result = original_read(path, role=role, **kwargs)
            if role in captured:
                captured[role].append(result)
            return result

        gs.read_file_qd_gpu = _capture_transport

        conn.send({
            "op": "ready",
            "pid": os.getpid(),
            "torch_version": torch.__version__,
            "cuda_version": torch.version.cuda,
            "activation": {
                key: activation.get(key)
                for key in (
                    "activated",
                    "already_activated",
                    "aimdo_import_version_or_none",
                    "patcher_class_name",
                    "is_dynamic_alias",
                )
            },
        })

        while True:
            try:
                msg = conn.recv()
            except EOFError:
                return
            if not isinstance(msg, dict):
                continue
            op = msg.get("op")
            if op == "load":
                kind = str(msg.get("kind") or "")
                try:
                    reply = _run_child_load(session, captured, kind)
                except BaseException as exc:  # noqa: BLE001 - reported to parent
                    conn.send({
                        "op": "error",
                        "kind": kind,
                        "error": f"{type(exc).__name__}: {exc}"[:400],
                    })
                else:
                    conn.send(reply)
            elif op == "stop":
                conn.send({
                    "op": "stopped",
                    "pid": os.getpid(),
                    "literal_probe": _literal_probe(session),
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

    @property
    def pid(self) -> Optional[int]:
        return self.pid_value

    def start(
        self,
        *,
        request: Any,
        contract: Any,
        model_paths: dict,
        clip_paths: list,
        output_root: Optional[str] = None,
        startup_timeout_s: float = STARTUP_TIMEOUT_S,
    ) -> float:
        """Start the worker and return its separate startup wall ms."""
        started_ns = time.perf_counter_ns()
        ctx = torch_mp.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe(duplex=True)
        proc = ctx.Process(target=_child_main, args=(child_conn,), daemon=True)
        proc.start()
        try:
            child_conn.close()
        except Exception:
            pass
        try:
            parent_conn.send({
                "op": "init",
                "request": request,
                "contract": contract,
                "model_paths": dict(model_paths),
                "clip_paths": list(clip_paths),
                "output_root": output_root,
            })
            deadline = time.monotonic() + float(startup_timeout_s)
            while not parent_conn.poll(1.0):
                if not proc.is_alive():
                    raise RuntimeError("loader_process_startup_died")
                if time.monotonic() > deadline:
                    raise RuntimeError("loader_process_startup_timeout")
            reply = parent_conn.recv()
        except BaseException:
            try:
                parent_conn.close()
            except Exception:
                pass
            proc.terminate()
            raise
        if not isinstance(reply, dict) or reply.get("op") != "ready":
            parent_conn.close()
            proc.terminate()
            raise RuntimeError(f"loader_process_startup_invalid:{str(reply)[:200]}")
        self._ctx = ctx
        self._process = proc
        self._conn = parent_conn
        reply_pid = reply.get("pid")
        proc_pid = proc.pid
        self.pid_value = int(reply_pid) if reply_pid else (int(proc_pid) if proc_pid else None)
        self.child_info = dict(reply)
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


__all__ = [
    "GOLDEN_LOADER_PROCESS_ENV",
    "LOADER_KINDS",
    "GoldenLoaderProcess",
    "loader_process_enabled",
]
