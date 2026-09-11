"""Golden parallel foundation.

This is a distinct orchestration boundary for the future overlapped Golden
path.  It intentionally has no overlap yet: the canonical stage functions
remain owned by :mod:`golden_serial`, and this module only composes those
functions in the same order with a distinct runtime identity.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

import torch

from .golden_serial import (
    GoldenFinalResult,
    GoldenRequest,
    GoldenSession,
    _GOLDEN_QD_ARM_CONTEXT,
    _persist_final_telemetry,
    _golden_trace_span,
    golden_clip_forward,
    golden_clip_load,
    golden_durable_commit,
    golden_output,
    golden_request_setup,
    golden_restore,
    golden_sampler_prepare,
    golden_sampler_tail,
    golden_sampling,
    golden_teardown,
    golden_unet_load,
    golden_vae_decode,
    golden_vae_load,
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
) -> GoldenFinalResult:
    """Execute the parallel Golden composition without overlap yet.

    Keeping the orchestration separate now makes the future scheduling change
    explicit while guaranteeing that loaders, sampler behavior, durability,
    and teardown remain the existing Golden implementations.
    """
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
    )
    primary_error: BaseException | None = None
    teardown_error: BaseException | None = None
    transport_arm_token = _GOLDEN_QD_ARM_CONTEXT.set(session.qd_transport_arm)
    result: GoldenFinalResult | None = None
    loader_worker: Any = None
    loader_process_active = False
    try:
        # Experimental Loader-Process A/B (disabled by default): one
        # persistent spawn worker performs the three full canonical loads and
        # stays alive for the request; the parent binds the same
        # CUDA-IPC-mapped storage through the canonical constructor+proof
        # path (no second read, no second H2D).
        from .golden_loader_process import (
            GoldenLoaderProcess,
            loader_process_enabled,
        )

        loader_process_active = loader_process_enabled()
        # No task is created here on purpose.  This is the P1 parallel control
        # plane and evidence foundation; overlap belongs to a later change.
        with _golden_trace_span("golden_parallel_execute"):
            await golden_restore(session)
        with _golden_trace_span("golden_request_setup"):
            await golden_request_setup(session)
        if loader_process_active:
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
                await golden_clip_load(session, preloaded_transports=_preloaded)
        with _golden_trace_span("golden_clip_forward"):
            await golden_clip_forward(session)
        with _golden_trace_span("golden_unet_load"):
            with _loader_worker_stage(session, loader_worker, "unet", "transport") as _preloaded:
                await golden_unet_load(session, preloaded_transport=_preloaded)
        with _golden_trace_span("golden_sampler_prepare"):
            await golden_sampler_prepare(session)
        with _golden_trace_span("golden_vae_load"):
            with _loader_worker_stage(session, loader_worker, "vae", "transport") as _preloaded:
                await golden_vae_load(session, preloaded_transport=_preloaded)
        with _golden_trace_span("golden_sampling"):
            await golden_sampling(session)
        with _golden_trace_span("golden_sampler_tail"):
            await golden_sampler_tail(session)
        with _golden_trace_span("golden_vae_decode"):
            await golden_vae_decode(session)
        with _golden_trace_span("golden_output"):
            await golden_output(session)
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

    try:
        _persist_final_telemetry(session)
    except BaseException:
        if primary_error is not None:
            raise primary_error
        if teardown_error is not None:
            raise teardown_error
        raise
    if primary_error is not None:
        raise primary_error
    if teardown_error is not None:
        raise teardown_error
    if result is None:
        raise RuntimeError("parallel_result_missing")
    result.telemetry_persist_ms = session.telemetry_persist_ms
    return result


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
