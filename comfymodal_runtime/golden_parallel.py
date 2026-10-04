"""Golden parallel orchestration over the canonical stage implementations."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager, nullcontext
from typing import Any, Callable, Optional

import torch

from .golden_serial import (
    GoldenFinalResult,
    GoldenRequest,
    GoldenSession,
    _GOLDEN_QD_ARM_CONTEXT,
    _persist_final_telemetry,
    _golden_trace_span,
    golden_root_span,
    _resolve_clip_unet_schedule,
    _resolve_sampling_vae_schedule,
    golden_clip_forward_unet_window,
    golden_clip_forward,
    golden_clip_load,
    golden_durable_commit,
    golden_output,
    golden_request_setup,
    golden_restore,
    golden_sampler_prepare,
    golden_sampler_tail,
    golden_sampling,
    golden_sampling_vae_window,
    golden_teardown,
    golden_unet_load,
    golden_vae_decode,
    golden_vae_load,
)


import faulthandler
import os
import threading
import time
from typing import Any

# ── Request wall gate + progress heartbeat ────────────────────────────────
# The per-model-load gates in golden_source_threads bound the SOURCE span
# only.  Everything else in a Golden request (skeleton overlap, the CLIP/UNET
# constructors and their adoption proofs, clip forward, sampling, VAE decode,
# output) was unbounded, so a stall there hung until the outer timeout.  This
# gate bounds the whole request, and because it fires from a watchdog thread it
# also dumps every thread stack -- which is what makes the next stall
# self-diagnosing instead of a forensic reconstruction.
GOLDEN_REQUEST_WALL_GATE_S = 40.0
# The adapter's post-request return is bounded separately.  It is armed only
# after Golden completed and its telemetry is durable on the volume, so an exit
# hang can never destroy a good result -- only cap how long the container holds
# the GPU while failing to return.
POST_REQUEST_EXIT_GATE_S = 15.0
# The post-request bound has to absorb VizTracer's final serialization, which
# runs after the request is armed and scales with entry count.  Removing the
# include_files whitelist (see full_execution_trace._start_request_tracing)
# raised a Golden request from ~40k entries to ~1.2M, and serializing that
# legitimately overruns the production 15s bound -- the gate then os._exit(71)s
# a run whose telemetry, output and trace are all already durable.  Give the
# traced path a larger default and let the env var win for explicit tuning.
POST_REQUEST_EXIT_GATE_TRACED_S = 120.0


def _resolve_post_request_exit_gate_s() -> float:
    raw = str(os.environ.get("COMFYMODAL_GOLDEN_EXIT_GATE_S", "")).strip()
    if raw:
        try:
            return max(1.0, float(raw))
        except ValueError:
            pass
    if str(os.environ.get("COMFYMODAL_V2_FULL_TRACE", "")).strip().lower() in {
        "1", "true", "yes", "on",
    }:
        return POST_REQUEST_EXIT_GATE_TRACED_S
    return POST_REQUEST_EXIT_GATE_S
PROGRESS_HEARTBEAT_ENV = "COMFYMODAL_GOLDEN_PROGRESS_HEARTBEAT"

_PROGRESS_STATE: dict[str, Any] = {"t0_ns": 0, "last_stage": "none"}


def _progress_enabled() -> bool:
    """Always-on unless explicitly disabled; no dependency on stage diagnostics.

    The counted profile sets COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=0, which is
    why a previous stall printed nothing between restore and completion and
    could not be localised from the streamed log.
    """
    return str(os.environ.get(PROGRESS_HEARTBEAT_ENV, "1")).strip().lower() in {
        "1", "true", "yes", "on",
    }


def _hb(stage: str) -> None:
    _PROGRESS_STATE["last_stage"] = stage
    # Also feed the shared mark list so the recorder event emitted before
    # telemetry persist carries the inner stage decomposition, not just the
    # wrapper's entry mark.  Elapsed is measured against the request clock set
    # at execute_enter, never a literal zero.
    _now_ns = time.monotonic_ns()
    _t0_ns = int(_PROGRESS_STATE.get("t0_ns") or 0)
    _elapsed_ns = (_now_ns - _t0_ns) if _t0_ns else 0
    _OUTER_MARKS.append((stage, _now_ns, _elapsed_ns, ""))
    if not _progress_enabled():
        return
    print(
        f"[v2.golden.progress] stage={stage} "
        f"elapsed_ms={_elapsed_ns / 1e6:.3f}",
        flush=True,
    )


_GATE_WATCHDOG_SRC = """\
import os, signal, sys, time

pid = int(sys.argv[1])
gate = float(sys.argv[2])
time.sleep(gate)

# SIGKILL where available (the Linux container cannot catch or block it);
# SIGTERM is the portable equivalent and maps to TerminateProcess on Windows.
sig = getattr(signal, "SIGKILL", None) or signal.SIGTERM
msg = ("[v2.golden.request_gate] WATCHDOG fired wall_gate_s=%r; "
       "sending %s to pid %d\\n" % (gate, getattr(sig, "name", sig), pid))
try:
    sys.stdout.write(msg)
    sys.stdout.flush()
except Exception:
    pass
try:
    os.kill(pid, sig)
except Exception:
    pass
"""


def _start_request_wall_gate_watchdog(gate_s: float) -> subprocess.Popen | None:
    """Start an out-of-process watchdog for the Golden request wall gate.

    The in-process ``threading.Timer`` gate cannot be relied on to fail closed.
    Reaching ``os._exit`` from a Python thread requires the GIL, so while the
    request thread sits in a blocking native/torch call that holds the GIL, the
    timer thread never runs and the gate never fires -- observed as a Golden
    request stuck in sampling for minutes with no gate output at all, while a
    request that was merely slow (sampler in an async wait, which releases the
    GIL) did trip the gate normally.

    A separate process is immune to that: it shares no GIL with the request and
    can always deliver SIGKILL, so the container is genuinely terminated
    instead of being left holding an H100. ``subprocess`` is used rather than
    ``multiprocessing``/``os.fork`` on purpose: forking a process that has
    already initialised CUDA is unsafe, and this child never touches CUDA.

    Best effort: if the watchdog cannot be started the in-process gate remains
    the only guard, so this never makes the situation worse.
    """
    try:
        return subprocess.Popen(
            [sys.executable, "-c", _GATE_WATCHDOG_SRC, str(os.getpid()), repr(float(gate_s))],
            stdin=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001 - diagnostics/bounds are best effort
        return None


def _install_request_wall_gate(gate_s: float = GOLDEN_REQUEST_WALL_GATE_S):
    def _fire() -> None:
        print(
            f"[v2.golden.request_gate] FAILED wall_gate_s={gate_s} "
            f"last_stage={_PROGRESS_STATE.get('last_stage')}",
            flush=True,
        )
        print("[v2.golden.request_gate] BEGIN thread stacks", flush=True)
        try:
            faulthandler.dump_traceback(all_threads=True)
        except BaseException as exc:  # noqa: BLE001 - diagnostics are best effort
            print(f"[v2.golden.request_gate] stack dump failed: {exc}", flush=True)
        print("[v2.golden.request_gate] END thread stacks", flush=True)
        # Hard fail-closed: a blocking native call cannot be interrupted
        # safely, so the container is terminated rather than left holding an
        # H100 indefinitely.  The stack dump above is the evidence.
        os._exit(70)

    timer = threading.Timer(gate_s, _fire)
    timer.daemon = True
    timer.start()
    # Independent, GIL-immune backstop: guarantees termination even when the
    # thread above is starved by a GIL-holding native call.
    _PROGRESS_STATE["gate_watchdog"] = _start_request_wall_gate_watchdog(gate_s)
    _PROGRESS_STATE["gate_timer"] = timer
    return timer


def _cancel_request_wall_gate() -> None:
    """Disarm the Golden request wall gate once the request is complete."""
    watchdog = _PROGRESS_STATE.pop("gate_watchdog", None)
    if watchdog is not None:
        # The watchdog only sends SIGKILL after sleeping, so it must be reaped
        # here: leaving it armed would let a completed request be killed later.
        try:
            watchdog.kill()
        except BaseException:
            pass
        try:
            watchdog.wait(timeout=5)
        except BaseException:
            pass
    timer = _PROGRESS_STATE.pop("gate_timer", None)
    if timer is not None:
        try:
            timer.cancel()
        except BaseException:
            pass


def _install_post_request_exit_bound(gate_s: float | None = None) -> None:
    """Bound the Modal adapter's post-request return.

    Golden completed and its telemetry is already durable on the volume before
    this is armed, so an exit hang can no longer destroy a good result -- but an
    unbounded exit still holds the H100 until the platform timeout.  This fires
    only if the container has not returned, and says so explicitly.

    ``gate_s`` defaults to None and is resolved at arm time, not import time, so
    the traced run picks up its own larger budget.
    """
    gate_s = _resolve_post_request_exit_gate_s() if gate_s is None else gate_s

    def _fire() -> None:
        print(
            f"[v2.golden.exit_gate] FAILED post_request_exit_gate_s={gate_s} "
            f"last_stage={_PROGRESS_STATE.get('last_stage')} "
            f"telemetry=persisted action=force_exit",
            flush=True,
        )
        os._exit(71)

    timer = threading.Timer(gate_s, _fire)
    timer.daemon = True
    timer.start()
    _PROGRESS_STATE["exit_timer"] = timer


_OUTER_MARKS: list = []


class _OuterLifetime:
    """Passive outer-method lifetime marks for the streaming adapter.

    Modal-reported execution time is the OUTER method wall, while the Golden
    waterfall only covers the inner call.  This records the real seam: an async
    generator suspends at every ``yield``, so the interval between a result
    becoming available to the caller and Python resuming is measurable here
    rather than inferred.  Same monotonic clock the path already treats as
    authoritative; one monotonic read and one print per boundary.
    """

    __slots__ = ("t0_ns", "marks")

    def __init__(self) -> None:
        self.t0_ns = time.monotonic_ns()
        self.marks: list[tuple[str, int, int, str]] = []

    def mark(self, name: str, *, detail: str = "") -> int:
        now_ns = time.monotonic_ns()
        entry = (name, now_ns, now_ns - self.t0_ns, detail)
        self.marks.append(entry)
        _OUTER_MARKS.append(entry)
        print(
            f"[v2.golden.outer] {name} t_ns={now_ns} "
            f"elapsed_ms={(now_ns - self.t0_ns) / 1e6:.3f}"
            + (f" detail={detail}" if detail else ""),
            flush=True,
        )
        return now_ns

    def report(self) -> None:
        if not self.marks:
            return
        first, last = self.marks[0], self.marks[-1]
        wall_ms = (last[1] - first[1]) / 1e6
        print(
            f"[v2.golden.outer] OUTER_SUMMARY outer_wall_ms={wall_ms:.3f} "
            f"marks={len(self.marks)} first={first[0]} last={last[0]}",
            flush=True,
        )


async def golden_parallel_execute(
    request: GoldenRequest,
    *,
    volume: Any,
    volume_mount_root: Optional[str] = None,
    output_root: Optional[str] = None,
    telemetry_path: Optional[str] = None,
    node_classes: Optional[dict] = None,
    contract: Any = None,
    snapshot_proof: Optional[Callable[[], dict]] = None,
    restore_metadata: Optional[dict] = None,
    restore_observation: Optional[dict] = None,
    cpu_prefetch_ticket: Any = None,
    stage_observer: Optional[Callable[[dict[str, Any]], Any]] = None,
) -> GoldenFinalResult:
    """Overlap independent model stages while retaining canonical ownership."""
    session = GoldenSession(
        request,
        volume=volume,
        volume_mount_root=volume_mount_root,
        output_root=output_root,
        telemetry_path=telemetry_path,
        node_classes=node_classes,
        contract=contract,
        snapshot_proof=snapshot_proof,
        restore_metadata=restore_metadata,
        restore_observation=restore_observation,
        cpu_prefetch_ticket=cpu_prefetch_ticket,
        stage_observer=stage_observer,
    )
    primary_error: BaseException | None = None
    teardown_error: BaseException | None = None
    transport_arm_token = _GOLDEN_QD_ARM_CONTEXT.set(session.qd_transport_arm)
    result: GoldenFinalResult | None = None
    loader_worker: Any = None
    loader_process_active = False
    # Bound before the try so the finally always has a root to close, even if
    # entering the span itself is what failed.
    golden_root: Any = nullcontext()
    try:
        # Experimental loader-process modes (both disabled by default):
        # - request-time worker (COMFYMODAL_GOLDEN_LOADER_PROCESS): one
        #   persistent spawn worker performs the three full canonical loads
        #   and stays alive for the request; the parent binds the same
        #   CUDA-IPC-mapped storage through the canonical constructor+proof
        #   path (no second read, no second H2D).
        # - pre-snapshot worker (COMFYMODAL_GOLDEN_LOADER_PROCESS_PRESNAPSHOT):
        #   the CPU-only worker was spawned before snapshot capture; after
        #   restore the SAME process + IPC channel must be verified (PING/PONG,
        #   no respawn) and is then used for the same canonical loads.
        from .golden_loader_process import (
            GoldenLoaderProcess,
            cuda_visibility_probe,
            get_pre_snapshot_worker,
            loader_process_enabled,
            loader_spawn_count,
            pre_snapshot_record,
            presnapshot_loader_enabled,
        )

        loader_process_active = loader_process_enabled()
        presnapshot_active = presnapshot_loader_enabled()
        from .golden_io_process import io_process_enabled as _io_process_enabled
        _io_process_active = _io_process_enabled()
        # No task is created here on purpose.  This is the P1 parallel control
        # plane and evidence foundation; overlap belongs to a later change.
        _PROGRESS_STATE["t0_ns"] = time.monotonic_ns()
        _PROGRESS_STATE["last_stage"] = "execute_enter"
        # _OUTER_MARKS is module-global, so on a reused or concurrent container
        # it otherwise accumulates marks from earlier requests and mixes their
        # timestamps into this request's telemetry.  Reset it with the rest of
        # the per-request progress state so every mark below belongs to this
        # request's clock.
        _OUTER_MARKS.clear()
        _install_request_wall_gate()
        _hb("execute_enter")
        # THE authoritative Golden Parallel root.  It opens before any request
        # work and closes in the ``finally`` below, after teardown and after the
        # loader worker has released its child-side storage, so every canonical
        # stage and teardown are inside it.  It must be the only Golden root:
        # two competing roots make the exhaustive profiler fail closed.
        golden_root = golden_root_span("golden_parallel_execute")
        golden_root.__enter__()
        await golden_restore(session)
        _hb("restore_done")
        if _io_process_active:
            # Diagnostic probe BEFORE the first CLIP/model read: report exactly
            # which of {child, control Pipe, shared ring} survived restore.
            import json as _json
            from .golden_io_process import io_process_probe
            _io_probe = io_process_probe(
                anchor_monotonic_ns=_stage_entry_ns(session, "golden_restore"),
            )
            session.recorder.event("golden_io_process_probe", **_io_probe)
            print(
                "[v2.golden_io_process.probe] "
                + _json.dumps(_io_probe, sort_keys=True, default=str)[:1800],
                flush=True,
            )
            if not _io_probe.get("ok"):
                raise RuntimeError(
                    "golden_io_worker_probe_failed:"
                    + str(_io_probe.get("error") or "child/pipe/shm not survived")
                )
        if presnapshot_active:
            # Fail closed: never replace a missing/dead pre-snapshot worker.
            probe_evidence = _presnapshot_worker_probe(
                session,
                get_pre_snapshot_worker(),
                pre_snapshot_record(),
                loader_spawn_count,
            )
            session.recorder.event("presnapshot_worker_probe", **probe_evidence)
        with _golden_trace_span("golden_request_setup"):
            await golden_request_setup(session)
        _hb("request_setup_done")
        if presnapshot_active:
            loader_worker = get_pre_snapshot_worker()
            init_evidence = loader_worker.initialize_session(
                request=session.request,
                contract=session.contract,
                model_paths=session.model_paths,
                clip_paths=session.clip_paths,
                output_root=session.output_root,
            )
            session.recorder.event("presnapshot_worker_session_init", **init_evidence)
            session.recorder.event("presnapshot_cuda_env_probe", **cuda_visibility_probe())
            try:
                cuda_evidence = loader_worker.init_cuda()
            except BaseException as exc:  # noqa: BLE001 - evidence then fail closed
                session.recorder.event(
                    "presnapshot_worker_cuda_init_failed",
                    error=f"{type(exc).__name__}: {exc}"[:1600],
                    diagnostic=getattr(exc, "diagnostic", None),
                )
                raise
            session.recorder.event("presnapshot_worker_cuda_init", **cuda_evidence)
        elif loader_process_active:
            loader_worker = GoldenLoaderProcess()
            worker_startup_ms = loader_worker.start(
                request=session.request,
                contract=session.contract,
                model_paths=session.model_paths,
                clip_paths=session.clip_paths,
                output_root=session.output_root,
            )
            child_info = dict(loader_worker.child_info or {})
            session.recorder.event(
                "golden_loader_process_started",
                worker_startup_ms=round(float(worker_startup_ms), 3),
                worker_pid=loader_worker.pid,
                torch_version=child_info.get("torch_version"),
                cuda_version=child_info.get("cuda_version"),
                activation=child_info.get("activation") or {},
            )
        with _golden_trace_span("golden_clip_load"):
            with _loader_worker_stage(session, loader_worker, "clip", "transports") as _preloaded:
                _hb("clip_load_begin")
                await golden_clip_load(session, preloaded_transports=_preloaded)
                _hb("clip_load_done")
        clip_unet_schedule = _resolve_clip_unet_schedule()
        sampling_vae_schedule = _resolve_sampling_vae_schedule()
        _hb("clip_forward_unet_window_begin")
        await golden_clip_forward_unet_window(
            session,
            schedule=clip_unet_schedule,
            unet_load=lambda: _unet_load_with_worker_stage(session, loader_worker),
        )
        _hb("clip_forward_unet_window_done")
        with _golden_trace_span("golden_sampler_prepare"):
            await golden_sampler_prepare(session)
        _hb("sampler_prepare_done")
        _hb("sampling_vae_window_begin")
        await golden_sampling_vae_window(
            session,
            schedule=sampling_vae_schedule,
            vae_load=lambda: _vae_load_with_worker_stage(session, loader_worker),
        )
        _hb("sampling_vae_window_done")
        with _golden_trace_span("golden_sampler_tail"):
            await golden_sampler_tail(session)
        _hb("sampler_tail_done")
        with _golden_trace_span("golden_vae_decode"):
            await golden_vae_decode(session)
        _hb("vae_decode_done")
        with _golden_trace_span("golden_output"):
            await golden_output(session)
        _hb("output_done")
        if session.output_durability_mode == "strict":
            if session.pending_durability is None:
                raise RuntimeError("parallel_durable_commit_pending_missing")
            with _golden_trace_span("golden_durable_commit"):
                await golden_durable_commit(
                    session.volume_contract or session.volume,
                    session.pending_durability,
                    session.recorder,
                    expected_sha256=session.contract.expected_output_png_sha256,
                )
            session.recorder.mark_true_durable()
        result = session.build_final_result()
        session.recorder.event("RESULT_ASSEMBLED", request_id=request.request_id)
        # ── Strict CPU-I/O process evidence (experimental; default OFF) ────
        # Records child CUDA-sterility and the shared->pinned copy cost.  The
        # parent source-open count stays 0 because the child served every model
        # payload read; the one H2D/model path remains in the parent.
        try:
            from .golden_io_process import io_process_enabled, io_process_evidence
            if io_process_enabled():
                session.recorder.event("golden_io_process", **io_process_evidence())
        except Exception:
            pass
    except BaseException as exc:
        primary_error = exc
        try:
            await golden_teardown(session)
        except BaseException:
            pass
    else:
        try:
            await golden_teardown(session)
        except BaseException as exc:
            teardown_error = exc
        else:
            session.recorder.event("TEARDOWN_COMPLETE", request_id=request.request_id)
    finally:
        if loader_worker is not None:
            # Teardown has already released the parent-side owner handles;
            # stopping the worker now releases the child-side CUDA storage.
            try:
                stop_evidence = loader_worker.stop()
                session.recorder.event(
                    "golden_loader_process_stopped",
                    worker_pid=stop_evidence.get("pid"),
                    literal_probe=stop_evidence.get("literal_probe") or {},
                    stop_error=stop_evidence.get("stop_error"),
                )
            except BaseException as stop_exc:  # noqa: BLE001 - stop is best effort
                session.recorder.event(
                    "golden_loader_process_stop_failed",
                    error=f"{type(stop_exc).__name__}: {stop_exc}"[:240],
                )
            loader_worker = None
        _GOLDEN_QD_ARM_CONTEXT.reset(transport_arm_token)
        # Close the authoritative Golden root last: teardown and loader-worker
        # release are request-side work, telemetry persistence is not.
        golden_root.__exit__(None, None, None)

    try:
        _hb("telemetry_persist_begin")
        # Emit outer/progress marks through the recorder BEFORE persisting, so
        # they are part of the telemetry event stream that v2ctl collects in
        # full.  Container stdout is not captured, and attempt_0.json is a
        # curated schema that drops unknown top-level keys.
        try:
            session.recorder.event(
                "golden_outer_marks",
                marks=[
                    {"mark": name, "elapsed_ms": round(elapsed / 1e6, 3), "detail": detail}
                    for name, _t_ns, elapsed, detail in list(_OUTER_MARKS)
                ],
            )
        except BaseException:
            pass
        _persist_final_telemetry(session)
        _hb("telemetry_persist_done")
    except BaseException:
        if primary_error is not None:
            raise primary_error
        if teardown_error is not None:
            raise teardown_error
        raise
    # The Golden request has finished and its telemetry is durable on the
    # volume.  Cancel the request wall gate here: it exists to bound Golden
    # work, and leaving it armed would kill an otherwise successful request
    # whose container simply cannot return.  The post-request exit is bounded
    # separately, below, so it can never hold an H100 either way.
    _cancel_request_wall_gate()
    if primary_error is not None:
        raise primary_error
    if teardown_error is not None:
        raise teardown_error
    if result is None:
        raise RuntimeError("parallel_result_missing")
    result.telemetry_persist_ms = session.telemetry_persist_ms
    # Golden succeeded and its telemetry is durable.  From here the only thing
    # that can still go wrong is the adapter failing to return, so bound that
    # instead of letting the container sit on the GPU.
    _hb("return_armed")
    _install_post_request_exit_bound()
    return result


async def _unet_load_with_worker_stage(session: Any, worker: Any) -> Any:
    with _loader_worker_stage(session, worker, "unet", "transport") as preloaded:
        return await golden_unet_load(session, preloaded_transport=preloaded)


async def _vae_load_with_worker_stage(session: Any, worker: Any) -> Any:
    with _loader_worker_stage(session, worker, "vae", "transport") as preloaded:
        return await golden_vae_load(session, preloaded_transport=preloaded)


def _stage_entry_ns(session: Any, name: str) -> Optional[int]:
    interval = getattr(getattr(session, "recorder", None), "_intervals", {}).get(name)
    return getattr(interval, "entry_monotonic_ns", None) if interval is not None else None


def _presnapshot_worker_probe(session: Any, worker: Any, record: dict, spawn_count_fn: Callable[[], int]) -> dict:
    """Verify the pre-snapshot worker survived restore; fail closed if not."""
    if worker is None:
        raise RuntimeError("presnapshot_worker_missing")
    anchor_ns = _stage_entry_ns(session, "golden_restore")
    evidence = worker.probe(anchor_monotonic_ns=anchor_ns)
    evidence["pre_capture"] = record
    evidence["spawn_count"] = spawn_count_fn()
    evidence["request_id"] = str(getattr(session.request, "request_id", "") or "")
    print(
        "[v2.presnapshot.probe] "
        + json.dumps(
            {key: value for key, value in evidence.items() if key != "pre_capture"},
            sort_keys=True,
            default=str,
        )[:1600],
        flush=True,
    )
    if not evidence.get("ok"):
        raise RuntimeError(
            "presnapshot_worker_not_survived:"
            + str(evidence.get("error") or {
                "pid_match": evidence.get("pid_match"),
                "uuid_match": evidence.get("uuid_match"),
                "proc_start_ticks_match": evidence.get("proc_start_ticks_match"),
                "child_fileno_match": evidence.get("child_fileno_match"),
            })[:300]
        )
    if spawn_count_fn() != int(record.get("spawn_count") or -1):
        raise RuntimeError(
            "presnapshot_worker_replaced:spawn_count="
            f"{spawn_count_fn()}!={record.get('spawn_count')}"
        )
    if not record.get("worker_pid") or int(record.get("worker_pid")) != int(
        evidence.get("pid") or -1
    ):
        raise RuntimeError("presnapshot_worker_pid_precapture_mismatch")
    return evidence


@contextmanager
def _loader_worker_stage(session: Any, worker: Any, kind: str, shape: str):
    """Worker full-load + handoff events around one canonical preloaded bind.

    Yields the preloaded payload (``None`` when the loader process is OFF) so
    each stage keeps exactly one awaited canonical golden call.
    """
    if worker is None:
        yield None
        return
    reply = worker.load(kind)
    session.recorder.event(
        "golden_loader_worker_load",
        kind=kind,
        child_pid=reply.get("child_pid"),
        roundtrip_ms=round(float(reply.get("roundtrip_ms") or 0.0), 3),
        child_stage_ms=round(float(reply.get("child_stage_ms") or 0.0), 3),
        handoff_ms=round(float(reply.get("handoff_ms") or 0.0), 3),
        tensor_count=int(reply.get("tensor_count") or 0),
        h2d_completed_bytes=int(reply.get("h2d_completed_bytes") or 0),
        child_stage_interval=reply.get("child_stage_interval") or {},
    )
    transports = reply.get("transports") or []
    payload: Any = transports if shape == "transports" else (transports[0] if transports else None)
    cuda_available = torch.cuda.is_available()
    before = torch.cuda.memory_allocated() if cuda_available else None
    started_ns = time.perf_counter_ns()
    try:
        yield payload
    finally:
        after = torch.cuda.memory_allocated() if cuda_available else None
        session.recorder.event(
            "golden_loader_parent_rebind",
            kind=kind,
            parent_rebind_ms=round((time.perf_counter_ns() - started_ns) / 1e6, 3),
            parent_allocated_delta_bytes=(
                int(after - before) if before is not None and after is not None else None
            ),
        )


__all__ = ["golden_parallel_execute"]
