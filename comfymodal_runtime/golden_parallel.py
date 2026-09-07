"""Golden parallel foundation.

This is a distinct orchestration boundary for the future overlapped Golden
path.  It intentionally has no overlap yet: the canonical stage functions
remain owned by :mod:`golden_serial`, and this module only composes those
functions in the same order with a distinct runtime identity.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

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
    try:
        # No task is created here on purpose.  This is the P1 parallel control
        # plane and evidence foundation; overlap belongs to a later change.
        with _golden_trace_span("golden_parallel_execute"):
            await golden_restore(session)
        with _golden_trace_span("golden_request_setup"):
            await golden_request_setup(session)
        with _golden_trace_span("golden_clip_load"):
            await golden_clip_load(session)
        with _golden_trace_span("golden_clip_forward"):
            await golden_clip_forward(session)
        with _golden_trace_span("golden_unet_load"):
            await golden_unet_load(session)
        with _golden_trace_span("golden_sampler_prepare"):
            await golden_sampler_prepare(session)
        with _golden_trace_span("golden_vae_load"):
            await golden_vae_load(session)
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


__all__ = ["golden_parallel_execute"]
