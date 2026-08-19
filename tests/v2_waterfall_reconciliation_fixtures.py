"""Reconstructed real-run fixture for V2 waterfall reconciliation tests.

The original ``Pasted markdown(20260812-142808).md`` log was referenced in the
task but never actually attached to the conversation, so this fixture is
RECONSTRUCTED from the exact facts quoted in the task description:

  - command_start -> response          = 21.994 s  (21994.0 ms, exact)
  - command_start -> snapshot restore  = 3.879877 s
    (Modal app-log line "Restoring Function from memory snapshot" at
    01:12:57.388)
  - command_start -> python resume     = 11.209877 s
    (post_snapshot_restore start at 01:13:04.718)
  - python restore                     = 0.549 s
  - OLD accounting on the deficient artifact: accounted 11.264 s,
    residual 10.731 s

The internal stage timeline honors the quoted relationships (UNET read
1.047s / construction 0.271s / bind 0.158s / H2D 2.214s; VAE prep 0.8709s /
join 0.0375s; PromptExecutor execution->cached 0.999s / cached->first-node
0.227s) and is built from a pure duration chain so every scenario tiles the
wall EXACTLY (the wall is the sum of the stage durations).

Event names / dict shapes mirror what comfymodal_runtime.v2_waterfall.py
actually consumes (verified against the implementation): trace events with
``name``/``process``/``wall_unix_ns``/``monotonic_ns``/``metadata``,
``trace.metadata.request_origin_info`` origin keys
(``ui_run_triggered_wall_unix_ms`` in ms, ``local_receive_wall_ns`` /
``modal_submission_attempt_wall_unix_ns`` in ns), ``_restore_timing`` with
``remote_python_resume`` / ``restore_method_start`` / ``restore_method_end``
wall+mono keys, ``modal_restore_begin_wall_unix_ns`` (input param or result
dict key), ``pre_sampler_structured_report.active_read_records`` with
``start_wall_unix_ns``/``end_wall_unix_ns``/``wall_ms``, and
``prompt_executor_milestones`` event metadata (``invoke_to_execution_start_ms``,
``execution_start_to_cached_ms``, ``cached_to_first_node_ms``,
``first_node_to_clip_ms``, ``clip_to_sampler_node_ms``).
"""

from __future__ import annotations

import copy

from typing import Any

# Arbitrary but consistent unix-ns base (2023-11-14 16:53:20 UTC).
BASE_NS = 1_700_000_000_000_000_000
BASE_MS = BASE_NS // 1_000_000
# Monotonic offsets: remote and local processes have separate monotonic
# domains; the deltas within each domain equal the wall deltas.
REMOTE_MONO_OFFSET = 700_000_000_000
LOCAL_MONO_OFFSET = 500_000_000_000

TOTAL_MS = 21994.0
RESTORE_BEGIN_OFFSET_MS = 3879.877
PYTHON_RESUME_OFFSET_MS = 11209.877
RESTORE_MS = 549.0

# Stage durations (ms) shared by every chain.  The wall total is the sum.
LOCAL_PREP_MS = 1.0
SUBMISSION_MS = 19.0
SCHEDULING_MS = RESTORE_BEGIN_OFFSET_MS - 20.0  # 3859.877
PRE_PYTHON_MS = PYTHON_RESUME_OFFSET_MS - RESTORE_BEGIN_OFFSET_MS  # 7330.0
RESTORE_TO_METHOD_MS = 91.123
METHOD_SETUP_MS = 3970.0
INVOKE_TO_EXECUTION_MS = 1.0
EXECUTION_TO_CACHED_MS = 999.0
CACHED_TO_FIRST_NODE_MS = 227.0
FIRST_NODE_TO_CLIP_MS = 400.0
CLIP_TO_SAMPLER_MS = 300.0
JOIN_WAIT_MS = 230.0
LANE_TO_SAMPLING_MS = 40.0
VAE_TO_DECODE_MS = 916.4  # scheduled 2 + load-start offset 5 + prep 870.9 + join 37.5 + consumed->decode 1
VAE_DECODE_MS = 388.0
OUTPUT_ENCODE_MS = 280.0
OUTPUT_DESCRIPTOR_MS = 316.0
HANDOFF_MS = 140.0
LOCAL_RETURN_MS = 170.0

# UNET lane chain (ms), quoted relationships preserved.
UNET_READ_MS = 1047.0
UNET_CTOR_MS = 271.0
UNET_BIND_MS = 158.0
UNET_H2D_MS = 2214.0

# PromptExecutor metadata keys (ms) — children of prompt_executor_cache_setup.
PE_MILESTONE_KEYS = (
    ("invoke_to_execution_start_ms", INVOKE_TO_EXECUTION_MS),
    ("execution_start_to_cached_ms", EXECUTION_TO_CACHED_MS),
    ("cached_to_first_node_ms", CACHED_TO_FIRST_NODE_MS),
    ("first_node_to_clip_ms", FIRST_NODE_TO_CLIP_MS),
    ("clip_to_sampler_node_ms", CLIP_TO_SAMPLER_MS),
)

# Sampling closes the wall: total must be EXACTLY TOTAL_MS with default
# parameters (the quoted command->response wall of the real run).
_NON_SAMPLING_MS = sum(
    (
        LOCAL_PREP_MS,
        SUBMISSION_MS,
        SCHEDULING_MS,
        PRE_PYTHON_MS,
        RESTORE_MS,
        RESTORE_TO_METHOD_MS,
        METHOD_SETUP_MS,
        INVOKE_TO_EXECUTION_MS,
        EXECUTION_TO_CACHED_MS,
        CACHED_TO_FIRST_NODE_MS,
        FIRST_NODE_TO_CLIP_MS,
        CLIP_TO_SAMPLER_MS,
        JOIN_WAIT_MS,
        LANE_TO_SAMPLING_MS,
        VAE_TO_DECODE_MS,
        VAE_DECODE_MS,
        OUTPUT_ENCODE_MS,
        OUTPUT_DESCRIPTOR_MS,
        HANDOFF_MS,
        LOCAL_RETURN_MS,
    )
)
SAMPLING_MS = TOTAL_MS - _NON_SAMPLING_MS


def _wall(offset_ms: float) -> int:
    return BASE_NS + int(round(offset_ms * 1_000_000))


def _remote_mono(offset_ms: float) -> int:
    return _wall(offset_ms) - REMOTE_MONO_OFFSET


def _local_mono(offset_ms: float) -> int:
    return _wall(offset_ms) - LOCAL_MONO_OFFSET


def _event(name: str, offset_ms: float, *, process: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "name": name,
        "process": process,
        "wall_unix_ns": _wall(offset_ms),
        "monotonic_ns": _remote_mono(offset_ms) if process == "remote" else _local_mono(offset_ms),
        "metadata": metadata or {},
    }
    return event


def _chain(
    *,
    restore_ms: float = RESTORE_MS,
    scheduling_ms: float = SCHEDULING_MS,
    pre_python_ms: float = PRE_PYTHON_MS,
    sampling_ms: float = SAMPLING_MS,
    enqueue_ms: float = LOCAL_PREP_MS + SUBMISSION_MS,
    missing_children: bool = False,
) -> dict[str, float]:
    """Offsets (ms from command_start) of every boundary in the chain.

    The chain is purely additive; the wall total is the last offset.
    ``enqueue_ms`` is the command -> Modal-submission window (default
    ``LOCAL_PREP_MS + SUBMISSION_MS`` = 20.0, preserving the historical
    chain); shifting it moves the submission boundary and everything after it
    while keeping placement/restore/execution durations identical.
    """
    local_receive = LOCAL_PREP_MS
    submission = enqueue_ms
    restore_begin = submission + scheduling_ms
    python_resume = restore_begin + pre_python_ms
    restore_end = python_resume + restore_ms
    method_entry = restore_end + RESTORE_TO_METHOD_MS
    invoke_start = method_entry + METHOD_SETUP_MS
    execution_start = invoke_start + INVOKE_TO_EXECUTION_MS
    cached = execution_start + EXECUTION_TO_CACHED_MS
    first_node = cached + CACHED_TO_FIRST_NODE_MS
    join_start = first_node + FIRST_NODE_TO_CLIP_MS + CLIP_TO_SAMPLER_MS
    join_completed = join_start + JOIN_WAIT_MS
    sampling_start = join_completed + LANE_TO_SAMPLING_MS
    sampling_end = sampling_start + sampling_ms
    decode_start = sampling_end + VAE_TO_DECODE_MS
    decode_end = decode_start + VAE_DECODE_MS
    encode_end = decode_end + OUTPUT_ENCODE_MS
    persist_end = encode_end + OUTPUT_DESCRIPTOR_MS
    remote_return = persist_end + HANDOFF_MS
    response = remote_return + LOCAL_RETURN_MS
    return {
        "local_receive": local_receive,
        "submission": submission,
        "restore_begin": restore_begin,
        "python_resume": python_resume,
        "restore_end": restore_end,
        "method_entry": method_entry,
        "invoke_start": invoke_start,
        "execution_start": execution_start,
        "cached": cached,
        "first_node": first_node,
        "join_start": join_start,
        "join_completed": join_completed,
        "sampling_start": sampling_start,
        "sampling_end": sampling_end,
        "decode_start": decode_start,
        "decode_end": decode_end,
        "encode_end": encode_end,
        "persist_end": persist_end,
        "remote_return": remote_return,
        "response": response,
    }


def _remote_events(offsets: dict[str, float]) -> list[dict[str, Any]]:
    unet_start = offsets["method_entry"] + 5.0
    unet_terminal = unet_start + 8.0 + UNET_READ_MS + UNET_CTOR_MS + UNET_BIND_MS + UNET_H2D_MS + 7.0
    milestone_metadata: dict[str, Any] = dict(PE_MILESTONE_KEYS)
    return [
        _event("remote_method_entry", offsets["method_entry"], process="remote"),
        _event("unet_ownership_claim", unet_start, process="remote"),
        _event("unet_early_activation_scheduled", unet_start + 1.0, process="remote"),
        _event("unet_fast_disk_to_start", unet_start + 8.0, process="remote"),
        _event("unet_fast_disk_to_end", unet_start + 8.0 + UNET_READ_MS, process="remote"),
        _event("unet_fast_disk_bind_start", unet_start + 8.0 + UNET_READ_MS + UNET_CTOR_MS, process="remote"),
        _event("unet_fast_disk_bind_end", unet_start + 8.0 + UNET_READ_MS + UNET_CTOR_MS + UNET_BIND_MS, process="remote"),
        _event(
            "unet_fast_disk_complete",
            unet_start + 8.0 + UNET_READ_MS + UNET_CTOR_MS + UNET_BIND_MS + UNET_H2D_MS,
            process="remote",
            metadata={
                "ctor_ms": UNET_CTOR_MS,
                "get_model_ms": 0.0,
                "bind_ms": UNET_BIND_MS,
                "to_device_ms": UNET_H2D_MS,
                "decision": "complete",
            },
        ),
        _event("unet_early_activation_terminal", unet_terminal, process="remote"),
        _event(
            "unet_graph_join",
            offsets["join_completed"],
            process="remote",
            metadata={
                "join_start_mono_ns": _remote_mono(offsets["join_start"]),
                "join_completed_mono_ns": _remote_mono(offsets["join_completed"]),
                "join_wait_ms": JOIN_WAIT_MS,
            },
        ),
        _event("prompt_executor_invoke_start", offsets["invoke_start"], process="remote"),
        _event("graph_first_node", offsets["first_node"], process="remote"),
        _event(
            "prompt_executor_milestones",
            offsets["first_node"],
            process="remote",
            metadata=milestone_metadata,
        ),
        _event("sampler_lane_wait_start", offsets["join_completed"], process="remote"),
        _event("sampling_start", offsets["sampling_start"], process="remote"),
        _event("sampling_end", offsets["sampling_end"], process="remote", metadata={"duration_ms": offsets["sampling_end"] - offsets["sampling_start"]}),
        _event("vae_early_activation_scheduled", offsets["sampling_end"] + 2.0, process="remote"),
        _event("vae_early_activation_load_start", offsets["sampling_end"] + 7.0, process="remote"),
        _event("vae_early_activation_terminal", offsets["sampling_end"] + 7.0 + 870.9, process="remote"),
        _event(
            "vae_early_activation_reconciliation",
            offsets["sampling_end"] + 7.0 + 870.9,
            process="remote",
            metadata={"load_wall_ms": 870.9, "join_wait_ms": 37.5},
        ),
        _event("vae_early_activation_consumed", offsets["sampling_end"] + 7.0 + 870.9 + 37.5, process="remote"),
        _event("vae_decode_start", offsets["decode_start"], process="remote"),
        _event("vae_decode_end", offsets["decode_end"], process="remote"),
        _event("output_encode_start", offsets["decode_end"], process="remote"),
        _event("output_encode_end", offsets["encode_end"], process="remote"),
        _event("output_persist_start", offsets["encode_end"], process="remote"),
        _event("output_persist_end", offsets["persist_end"], process="remote"),
        _event("output_collect_end", offsets["persist_end"], process="remote"),
        _event("deferred_commit_start", offsets["persist_end"] + 2.0, process="remote"),
        _event("deferred_commit_end", offsets["persist_end"] + 102.0, process="remote"),
    ]


def _local_events(offsets: dict[str, float]) -> list[dict[str, Any]]:
    return [
        _event("worker_start", 0.5, process="local"),
        _event("transport_entry", offsets["local_receive"], process="local"),
        _event("modal_submission_attempt", offsets["submission"], process="local"),
        _event("modal_first_iteration_start", offsets["submission"], process="local"),
        _event("remote_return_start", offsets["remote_return"], process="local"),
        _event("final_result_received", offsets["remote_return"], process="local"),
        _event("local_result_received", offsets["remote_return"], process="local"),
    ]


def _restore_timing(offsets: dict[str, float], restore_ms: float) -> dict[str, Any]:
    return {
        "restore_method_start_wall_unix_ns": _wall(offsets["python_resume"]),
        "restore_method_start_mono_ns": _remote_mono(offsets["python_resume"]),
        "remote_python_resume_wall_unix_ns": _wall(offsets["python_resume"]),
        "remote_python_resume_mono_ns": _remote_mono(offsets["python_resume"]),
        "restore_method_end_wall_unix_ns": _wall(offsets["restore_end"]),
        "restore_method_end_mono_ns": _remote_mono(offsets["restore_end"]),
        "restore_total_ms": restore_ms,
    }


def _result_from_offsets(
    offsets: dict[str, float],
    *,
    restore_ms: float,
    boundaries: bool = True,
    restore_begin: bool = True,
    missing_children: bool = False,
    request_id: str = "req-20260812-142808",
    restored_instance_id: str = "ri-realrun-01",
    container_session_id: str = "cs-realrun-01",
    gpu: str = "RTX6000",
    cloud: str = "aws",
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Build the full result dict from a precomputed chain offset table."""
    origin: dict[str, Any] = {
        "ui_run_triggered_wall_unix_ms": BASE_MS,
        "local_receive_wall_ns": _wall(offsets["local_receive"]),
        "local_receive_mono_ns": _local_mono(offsets["local_receive"]),
    }
    events: list[dict[str, Any]] = []
    if boundaries:
        origin["modal_submission_attempt_wall_unix_ns"] = _wall(offsets["submission"])
        origin["modal_submission_attempt_mono_ns"] = _local_mono(offsets["submission"])
        events.extend(_local_events(offsets))
    events.extend(_remote_events(offsets))

    if missing_children:
        for event in events:
            if event["name"] == "prompt_executor_milestones":
                event["metadata"]["cached_to_first_node_ms"] = 226.0

    result: dict[str, Any] = {
        "request_id": request_id,
        "identity": {
            "restored_instance_id": restored_instance_id,
            "gpu": gpu,
            "cloud": cloud,
            "region": region,
            "restore_count": 1,
            "request_count": 1,
        },
        "wall_ms": offsets["response"],
        "_restore_timing": _restore_timing(offsets, restore_ms),
        "trace": {
            "request_id": request_id,
            "container_session_id": container_session_id,
            "metadata": {
                "request_origin_info": origin,
            },
            "events": events,
        },
        "pre_sampler_structured_report": {
            "active_read_records": [
                {
                    "owner": "unet",
                    "path_hash": "0f0a2b3c4d5e",
                    "request_id": request_id,
                    "container_session_id": container_session_id,
                    "wall_ms": UNET_READ_MS,
                    "start_wall_unix_ns": _wall(offsets["method_entry"] + 13.0),
                    "end_wall_unix_ns": _wall(offsets["method_entry"] + 13.0 + UNET_READ_MS),
                }
            ],
            "cpu_owner_records": [],
            "per_node_timings": [],
        },
    }
    if restore_begin:
        result["modal_restore_begin_wall_unix_ns"] = _wall(offsets["restore_begin"])
    return result


def build_real_run_result(
    *,
    boundaries: bool = True,
    restore_begin: bool = True,
    restore_ms: float = RESTORE_MS,
    scheduling_ms: float = SCHEDULING_MS,
    pre_python_ms: float = PRE_PYTHON_MS,
    sampling_ms: float = SAMPLING_MS,
    enqueue_ms: float = LOCAL_PREP_MS + SUBMISSION_MS,
    missing_children: bool = False,
) -> dict[str, Any]:
    """Full result dict for ``build_waterfall``.

    ``boundaries=False`` reproduces the DEFICIENT artifact from the real run
    (no modal submission boundary): the pre-Python window cannot be split and
    the report must flag it.  ``restore_begin=False`` drops the Modal
    app-log boundary (as the OLD tooling never ingested it).
    ``enqueue_ms`` shifts the command -> Modal-submission window (default
    ``LOCAL_PREP_MS + SUBMISSION_MS``, preserving the historical chain).
    """
    offsets = _chain(
        restore_ms=restore_ms,
        scheduling_ms=scheduling_ms,
        pre_python_ms=pre_python_ms,
        sampling_ms=sampling_ms,
        enqueue_ms=enqueue_ms,
    )
    return _result_from_offsets(
        offsets,
        restore_ms=restore_ms,
        boundaries=boundaries,
        restore_begin=restore_begin,
        missing_children=missing_children,
    )


def build_reference_run_result(
    *,
    enqueue_ms: float = 19158.0,
    placement_ms: float = 854.266,
    total_ms: float = 35168.0,
    post_restore_shift_ms: float = 0.0,
) -> dict[str, Any]:
    """Reference-run fixture for the NEW scheduling contract (test A).

    Builds a full result whose stamps yield command -> enqueue == *enqueue_ms*,
    placement == *placement_ms* and total == *total_ms*, by scaling the default
    chain's post-restore-begin durations so the final response offset lands
    EXACTLY on *total_ms*.  non_scheduling == total - enqueue - placement by
    construction.  ``post_restore_shift_ms`` moves the whole post-restore-begin
    block later by a constant (startup grows, scheduling unchanged).
    """
    base = _chain()
    default_enqueue = LOCAL_PREP_MS + SUBMISSION_MS
    default_restore_begin = default_enqueue + SCHEDULING_MS
    default_post = base["response"] - default_restore_begin
    scale = (total_ms - enqueue_ms - placement_ms) / default_post
    post_begin = enqueue_ms + placement_ms
    offsets: dict[str, float] = {}
    for key, value in base.items():
        if key == "local_receive":
            offsets[key] = value
        elif key == "submission":
            offsets[key] = enqueue_ms
        elif key == "restore_begin":
            offsets[key] = post_begin
        else:
            offsets[key] = post_begin + (value - default_restore_begin) * scale + post_restore_shift_ms
    restore_ms = offsets["restore_end"] - offsets["python_resume"]
    return _result_from_offsets(
        offsets,
        restore_ms=restore_ms,
        request_id="req-reference-run",
        restored_instance_id="ri-reference-01",
        container_session_id="cs-reference-01",
    )


def attach_host_telemetry(
    result: dict[str, Any],
    *,
    gpu_name: str = "NVIDIA RTX PRO 6000 Blackwell Server Edition",
    vram_mib: int = 97250,
    cuda: str = "13.0",
    cc: str = "12.0",
    vendor: str = "AuthenticAMD",
    family: int = 191,
    model: int = 2,
    visible: int = 28,
    requested: int = 12,
    torch_intraop: int = 12,
    torch_interop: int = 14,
    native: int = 53,
    peak_cores: float = 7.13,
    above_16_ms: int | None = 0,
    rss_restore_mib: float = 9888,
    rss_peak_mib: float = 23572,
    rss_result_mib: float = 13466,
    max_rss_mib: float = 36612,
) -> dict[str, Any]:
    """Return a deep copy of *result* with full host-hardware telemetry
    attached (``gpu_allocation``, ``runtime_shape.observed``,
    ``host_hardware_fingerprint`` / ``host_memory`` / ``host_resource_snapshot``
    trace events and ``trace.activation_diagnosis``).  Defaults produce the
    canonical 4-line compact header: GPU trimmed to ``RTX PRO 6000 Blackwell``,
    ``VRAM 97,250 MiB``, ``CUDA 13.0``, ``CC 12.0``, CPU ``AMD Family 191
    Model 2``, visible=28, requested=12, Torch=12/14, native=53,
    ``CPU peak=7.13 cores``, RSS ~9.66 -> 23.02 -> 13.15 GiB, maxRSS ~35.75 GiB.
    """
    result = copy.deepcopy(result)
    result["gpu_allocation"] = {
        "gpu_requested_order": "a10g",
        "torch_version": "2.9.0",
        "gpu_actual_name": gpu_name,
        "gpu_compute_capability": cc,
        "gpu_vram_total_mib": vram_mib,
        "cuda_version": cuda,
    }
    result["runtime_shape"] = {
        "observed": {
            "cpu_request": requested,
            "torch_intraop_threads": torch_intraop,
            "torch_interop_threads": torch_interop,
            "native_thread_count": native,
        }
    }
    trace = result.setdefault("trace", {})
    trace["activation_diagnosis"] = {
        "cpu_peak_cores": peak_cores,
        "cpu_above_16_ms": above_16_ms,
    }
    events = trace.setdefault("events", [])
    events.append({
        "name": "host_hardware_fingerprint",
        "process": "remote",
        "wall_unix_ns": BASE_NS,
        "monotonic_ns": 0,
        "metadata": {
            "cpu_vendor": vendor,
            "cpu_family": family,
            "cpu_model": model,
            "cpu_count_proc": visible,
        },
    })
    for stage, rss in (
        ("restore_complete", rss_restore_mib),
        ("peak_execution", rss_peak_mib),
        ("result_complete", rss_result_mib),
    ):
        events.append({
            "name": "host_memory",
            "process": "remote",
            "wall_unix_ns": BASE_NS,
            "monotonic_ns": 0,
            "metadata": {
                "stage": stage,
                "process_rss_mib": rss,
                "process_maxrss_mib": max_rss_mib,
            },
        })
    events.append({
        "name": "host_resource_snapshot",
        "process": "remote",
        "wall_unix_ns": BASE_NS,
        "monotonic_ns": 0,
        "metadata": {"phase": "peak", "ru_maxrss": int(max_rss_mib * 1024)},
    })
    return result


def chain_total_ms(
    *,
    restore_ms: float = RESTORE_MS,
    scheduling_ms: float = SCHEDULING_MS,
    pre_python_ms: float = PRE_PYTHON_MS,
    sampling_ms: float = SAMPLING_MS,
    enqueue_ms: float = LOCAL_PREP_MS + SUBMISSION_MS,
) -> float:
    """The wall total (ms) the chain tiles to."""
    return _chain(
        restore_ms=restore_ms,
        scheduling_ms=scheduling_ms,
        pre_python_ms=pre_python_ms,
        sampling_ms=sampling_ms,
        enqueue_ms=enqueue_ms,
    )["response"]


def command_start_ms() -> int:
    return BASE_MS


def response_ns_for(total_ms: float) -> int:
    return BASE_NS + int(round(total_ms * 1_000_000))


EXPECTED = {
    "total_ms": TOTAL_MS,
    "scheduling_ms": SCHEDULING_MS,
    "pre_python_ms": PRE_PYTHON_MS,
    "restore_ms": RESTORE_MS,
    "restore_to_method_ms": RESTORE_TO_METHOD_MS,
    "method_setup_ms": METHOD_SETUP_MS,
    "cache_setup_ms": INVOKE_TO_EXECUTION_MS + EXECUTION_TO_CACHED_MS + CACHED_TO_FIRST_NODE_MS,
    "join_wait_ms": JOIN_WAIT_MS,
    "sampling_ms": SAMPLING_MS,
    "post_sampling_ms": VAE_TO_DECODE_MS,
    "vae_ms": VAE_DECODE_MS,
    "output_ms": OUTPUT_ENCODE_MS + OUTPUT_DESCRIPTOR_MS,
    "handoff_ms": HANDOFF_MS,
    "local_return_ms": LOCAL_RETURN_MS,
    "local_prep_ms": LOCAL_PREP_MS,
    "submission_ms": SUBMISSION_MS,
    # Quoted OLD accounting on the deficient artifact (real run).
    "old_accounted_ms": 11264.0,
    "old_residual_ms": 10731.0,
}
