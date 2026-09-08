import asyncio
import functools
import hashlib
import json
import os
import time as _time
from collections.abc import Callable

import modal

from gpu_catalog import (
    DEFAULT_GPU,
    GPU_CATALOG,
    GPU_BY_VALUE,
    get_available_gpu_options,
    get_default_gpu,
    get_supported_gpus,
    is_gpu_hidden,
    normalize_gpu_value,
)

# Delegate canonical hashing to the shared production_workflow module so
# there is one source of truth.
from production_workflow import _canonical_workflow_hash, COMPILER_SCHEMA_VERSION, HASH_SCHEMA_VERSION, PRODUCTION_PLAN_SCHEMA_VERSION
from comfymodal_runtime.env import env_flag
from comfymodal_runtime.publication_policy import (
    CUSTOM_NODES_PUBLISHER_APP_NAME,
)
from comfymodal_runtime.v2_waterfall import (
    attach_waterfall,
    graph_result_from_event,
    is_graph_result,
)


def _attach_waterfall_for_graph(result, *, run_label):
    """Attach the default waterfall to a graph-like Modal result (idempotent).

    Only graph workflow result / timing payloads are finalized; non-graph
    payloads (checkpoint summaries, asset reads, health, canary, restore-only,
    NUMA, rehoming probes) never receive fabricated graph stages.
    Host-side fallback attach: the remote container already prints the
    waterfall render, so this suppresses the duplicate host render.
    """
    if is_graph_result(result):
        attach_waterfall(result, run_label=run_label, print_render=False)


def _short_hash(h: str) -> str:
    """Return the first 8 characters of a hex hash, or '?' if empty."""
    return h[:8] if h else "?"


def validate_production_dispatch(
    workflow: dict,
    production_report: dict | None,
    *,
    label: str = "",
    workflow_hash: str = "",
) -> None:
    """Local dispatch invariant: verify the compiled workflow matches the report.

    Raised ``AssertionError`` (locally, before Modal) when:
    - The report is enabled but its compiled_workflow_hash does not match
      the actual hash of *workflow*.
    - The report's compiler_version or hash_schema_version is stale or does
      not match the current compiled version.
    - The report is missing required provenance fields.
    - The report is enabled but has no compiled_workflow_hash.

    This is a **no-op** when ``production_report`` is None, disabled
    (``enabled=False``).

    The mismatch message includes short hashes for quick diagnosis:
      source=abc12345 compiled=def67890 dispatch=ghi12345
    """
    if not production_report:
        return
    if not isinstance(production_report, dict):
        return
    if not production_report.get("enabled"):
        return

    compiled_hash = production_report.get("compiled_workflow_hash", "")
    if not compiled_hash:
        _src_h = _short_hash(production_report.get("source_workflow_hash", ""))
        _dispatch_h = _short_hash(workflow_hash or _canonical_workflow_hash(workflow))
        raise AssertionError(
            f"[{label}] production dispatch missing compiled_workflow_hash: "
            f"report has no compiled identity. "
            f"source={_src_h} compiled=n/a dispatch={_dispatch_h}. Recompile."
        )

    # Exact version guard — must match current compiled versions
    cv = production_report.get("compiler_version", 0)
    hv = production_report.get("hash_schema_version", 0)
    if cv != COMPILER_SCHEMA_VERSION:
        raise AssertionError(
            f"[{label}] stale or mismatched production compiler_version: "
            f"got {cv}, expected {COMPILER_SCHEMA_VERSION}"
        )
    if hv != HASH_SCHEMA_VERSION:
        raise AssertionError(
            f"[{label}] stale or mismatched production hash_schema_version: "
            f"got {hv}, expected {HASH_SCHEMA_VERSION}"
        )

    # Exact plan schema version guard
    pv = production_report.get("production_plan_schema_version", 0)
    if pv != PRODUCTION_PLAN_SCHEMA_VERSION:
        raise AssertionError(
            f"[{label}] stale or mismatched production_plan_schema_version: "
            f"got {pv}, expected {PRODUCTION_PLAN_SCHEMA_VERSION}"
        )

    # Use precomputed hash when provided (avoids re-serializing the workflow
    # on the hot path).  Otherwise compute it from the workflow dict.
    actual_hash = workflow_hash or _canonical_workflow_hash(workflow)
    if not actual_hash:
        raise AssertionError(
            f"[{label}] failed to hash dispatch workflow"
        )

    if actual_hash != compiled_hash:
        _src_h = _short_hash(production_report.get("source_workflow_hash", ""))
        raise AssertionError(
            f"[{label}] production dispatch hash mismatch: "
            f"source={_src_h} compiled={_short_hash(compiled_hash)} "
            f"dispatch={_short_hash(actual_hash)}. "
            "The compiled workflow no longer matches the report. Recompile."
        )

    # Success: log compact boundary identity
    source_hash = production_report.get("source_workflow_hash", "")
    plan_hash = production_report.get("production_plan_hash", "")
    print(
        f"[{label}] dispatch validated: source={_short_hash(source_hash)} "
        f"compiled={_short_hash(compiled_hash)} "
        f"plan={_short_hash(plan_hash)}"
    )

APP_NAME = os.environ.get("COMFYMODAL_APP_NAME", "comfyui").strip() or "comfyui"

# Environment-gated Modal placement: empty means global scheduling.
# Only set nonempty values to pin to a specific region or cloud provider.
# Example: COMFYMODAL_COMPUTE_REGION=us  COMFYMODAL_COMPUTE_CLOUD=aws
_COMFYMODAL_COMPUTE_REGION = os.environ.get("COMFYMODAL_COMPUTE_REGION", "").strip()
_COMFYMODAL_COMPUTE_CLOUD = os.environ.get("COMFYMODAL_COMPUTE_CLOUD", "").strip()

# Client-side backpressure: only one in-flight prompt execution at a time
_run_prompt_semaphore = asyncio.Semaphore(1)



# Per-workspace caches — populated lazily on first use per workspace.
# Key: workspace["id"] for clients, (workspace["id"], name) for function handles,
# (workspace["id"], gpu_value, region, cloud) for Cls instances.
_workspace_resolver: Callable[[], dict | None] | None = None
_workspace_clients: dict[str, object] = {}
_workspace_function_handles: dict[tuple[str, str, str | None, str], object] = {}
_workspace_cls_instances: dict[tuple[str, str, str, str], object] = {}
_current_gpu = DEFAULT_GPU
_handle_cache_hits = 0
_handle_cache_misses = 0


def _resolve_v1_environment() -> str | None:
    """Resolve Modal environment name for V1 function lookups.

    Uses ``COMFYMODAL_ENVIRONMENT`` (V1-specific variable), then
    falls back to ``MODAL_ENVIRONMENT`` for compatibility.
    Returns ``None`` when unset so the SDK uses the default
    deployed environment.
    """
    env = os.environ.get("COMFYMODAL_ENVIRONMENT", "").strip()
    if not env:
        env = os.environ.get("MODAL_ENVIRONMENT", "").strip()
    return env or None


# ── Workspace helpers ────────────────────────────────────────────────────


def set_workspace_resolver(resolver: Callable[[], dict | None] | None):
    """Install a callable that returns the currently active workspace dict.

    The resolver is invoked every time one of the public API functions is
    called *without* an explicit ``workspace=`` kwarg.  It should return a
    dict with keys ``id``, ``token_id``, ``token_secret``, or ``None`` if
    no workspace is available.
    """
    global _workspace_resolver
    _workspace_resolver = resolver


def _resolve_workspace(workspace: dict | None) -> dict:
    """Return a valid workspace dict, either from the caller or the resolver."""
    candidate = workspace or (_workspace_resolver() if _workspace_resolver else None)
    if not candidate:
        raise RuntimeError("No active Modal workspace selected")
    if not candidate.get("token_id") or not candidate.get("token_secret"):
        raise RuntimeError("Active Modal workspace is missing credentials")
    return candidate


def _workspace_client(workspace: dict):
    """Return (and cache) a ``modal.Client`` for the given workspace."""
    key = workspace["id"]
    client = _workspace_clients.get(key)
    if client is None:
        client = modal.Client.from_credentials(workspace["token_id"], workspace["token_secret"])
        _workspace_clients[key] = client
    return client


def _workspace_function(
    name: str,
    workspace: dict,
    environment_name: str | None = None,
    app_name: str | None = None,
):
    """Return (and cache) a ``modal.Function`` handle scoped to *workspace*.

    When *environment_name* is ``None`` (the default) the active environment
    is resolved via ``_resolve_v1_environment()``, which checks
    ``COMFYMODAL_ENVIRONMENT`` then ``MODAL_ENVIRONMENT``.
    The environment and app are part of the cache key so different
    environments/apps produce distinct handles.  ``app_name`` is optional so
    existing callers continue to use the module's default app.
    """
    global _handle_cache_hits, _handle_cache_misses
    if environment_name is None:
        environment_name = _resolve_v1_environment()
    selected_app = APP_NAME if app_name is None else str(app_name).strip()
    if not selected_app:
        raise ValueError("Modal app name must not be empty")
    key = (workspace["id"], name, environment_name, selected_app)
    handle = _workspace_function_handles.get(key)
    if handle is None:
        _handle_cache_misses += 1
        handle = modal.Function.from_name(
            selected_app, name,
            client=_workspace_client(workspace),
            environment_name=environment_name,
        )
        _workspace_function_handles[key] = handle
    else:
        _handle_cache_hits += 1
    return handle


def _workspace_api(workspace: dict, gpu: str | None = None):
    """Return (and cache) a GPU-class Cls instance scoped to *workspace*.

    If *gpu* is ``None`` the module-level ``_current_gpu`` is used.

    When ``COMFYMODAL_COMPUTE_REGION`` or ``COMFYMODAL_COMPUTE_CLOUD`` is
    set to a non-empty value, ``with_options(region=..., cloud=...)`` is
    applied to pin container scheduling.  Both default to empty (global
    scheduling).  Region and cloud are folded into the instance cache key.
    """
    global _handle_cache_hits, _handle_cache_misses
    selected_gpu = _current_gpu if gpu is None else normalize_gpu_value(gpu)
    entry = GPU_BY_VALUE.get(selected_gpu)
    if entry is None:
        raise ValueError(f"Unsupported GPU: {selected_gpu}")
    region = _COMFYMODAL_COMPUTE_REGION
    cloud = _COMFYMODAL_COMPUTE_CLOUD
    if selected_gpu == "rtx-pro-6000":
        region = ""
        cloud = "gcp"
    key = (workspace["id"], selected_gpu, region, cloud)
    instance = _workspace_cls_instances.get(key)
    if instance is None:
        _handle_cache_misses += 1
        cls_handle = modal.Cls.from_name(APP_NAME, entry["class_name"], client=_workspace_client(workspace))
        kwargs = {}
        if selected_gpu == "rtx-pro-6000":
            print(f"[modal-client] phase=cls_create requested_cloud=gcp requested_region=unconstrained")
        if region:
            kwargs["region"] = region
        if cloud:
            kwargs["cloud"] = cloud
        if region or cloud:
            cls_handle = cls_handle.with_options(**kwargs)
        instance = cls_handle()
        _workspace_cls_instances[key] = instance
    else:
        _handle_cache_hits += 1
    return instance


# ── V1 deployment identity capture ─────────────────────────────────────
# Records the deployment/resource identity at submission time for V1/V2
# parity comparison.  Mirrors the V2 DeploymentIdentity metadata without
# importing V2 runtime contracts.

_V1_DEPLOYMENT_METADATA: dict = {}


def _capture_v1_deployment_identity(workspace: dict, gpu: str | None = None) -> dict:
    """Capture V1 deployment identity from client-side workspace and configuration.

    Only captures values available on the local/CLIENT side (app name, gpu,
    workspace-configurable cloud/region overrides).  Authoritative Modal
    runtime identity (task_id, image_id, container_session_id, cloud
    provider, actual region) is captured by the REMOTE container and merged
    into the first stream event downstream — client-side MODAL_* env vars
    and locally generated UUIDs are NOT authoritative and are omitted here.

    Returns a dict with identity metadata matching V2's diagnosis_metadata()
    keys so comparison tooling can align V1 and V2 fields.
    """
    selected_gpu = _current_gpu if gpu is None else normalize_gpu_value(gpu)
    entry = GPU_BY_VALUE.get(selected_gpu, {})
    identity: dict = {
        "runtime_mode": "v1",
        "app_name": APP_NAME,
        "class_name": entry.get("class_name", "ComfyModalProductionAPI"),
        "method_name": "run_prompt_stream",
        "gpu": selected_gpu,
        "cloud": os.environ.get("COMFYMODAL_COMPUTE_CLOUD", "").strip() or "auto",
        "region": os.environ.get("COMFYMODAL_COMPUTE_REGION", "").strip() or "auto",
        "snapshot_enabled": True,  # V1 always has enable_memory_snapshot=True
        "gpu_snapshot_enabled": env_flag("COMFYMODAL_ENABLE_GPU_SNAPSHOT"),
    }
    global _V1_DEPLOYMENT_METADATA
    _V1_DEPLOYMENT_METADATA = dict(identity)
    return identity


def get_v1_deployment_identity() -> dict:
    """Return the cached V1 deployment identity dict from the most recent capture."""
    return dict(_V1_DEPLOYMENT_METADATA)


# ── Existing public helpers (unchanged except set_gpu validation) ─────────


def get_modal_app_name() -> str:
    return APP_NAME


def get_modal_class_name(gpu: str | None = None) -> str:
    selected_gpu = _current_gpu if gpu is None else normalize_gpu_value(gpu)
    entry = GPU_BY_VALUE.get(selected_gpu)
    if entry is None:
        raise ValueError(f"Unsupported GPU: {selected_gpu}")
    return entry["class_name"]


def get_modal_lookup_target(gpu: str | None = None, method_name: str = "run_prompt") -> str:
    return f"{APP_NAME}.{get_modal_class_name(gpu)}.{method_name}"


def get_handle_cache_stats() -> dict:
    return {"hits": _handle_cache_hits, "misses": _handle_cache_misses}


def set_gpu(gpu: str):
    global _current_gpu
    normalized = normalize_gpu_value(gpu)
    if normalized not in GPU_BY_VALUE:
        raise ValueError(f"Unsupported GPU: {normalized}")
    _current_gpu = normalized


def get_gpu() -> str:
    return _current_gpu


def get_available_gpus() -> list[dict[str, str]]:
    return get_available_gpu_options()


def clear_cache():
    """Clear all per-workspace caches so subsequent requests use fresh handles."""
    global _handle_cache_hits, _handle_cache_misses
    _workspace_clients.clear()
    _workspace_function_handles.clear()
    _workspace_cls_instances.clear()
    _handle_cache_hits = 0
    _handle_cache_misses = 0


# ── Error-handler decorator ──────────────────────────────────────────────


def _modal_error_handler(func):
    """Decorator that catches common exceptions and re-raises with user-friendly messages."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except TimeoutError as e:
            raise TimeoutError(
                "Modal request timed out. The container may be cold-starting (1-3 min)."
            ) from e
        except (ConnectionError, OSError) as e:
            raise ConnectionError(
                "Modal connection failed. Check your internet connection and Modal token."
            ) from e
        except Exception as e:
            if getattr(type(e), "__module__", "").startswith("modal"):
                raise RuntimeError(
                    f"Modal error: {e}. Try redeploying with the Deploy button."
                ) from e
            raise
    return wrapper


# ── Public async API (all accept optional workspace kwarg) ───────────────


@_modal_error_handler
async def run_prompt(
    workflow: dict,
    input_images: dict | None = None,
    trace: dict | None = None,
    production_report: dict | None = None,
    gpu: str | None = None,
    modal_options: dict | None = None,
    workspace: dict | None = None,
) -> dict:
    selected = _resolve_workspace(workspace)
    # Local dispatch invariant: verify compiled workflow matches report
    _precomputed_hash = (trace or {}).get("canonical_workflow_hash", "")
    validate_production_dispatch(
        workflow, production_report,
        label="run_prompt",
        workflow_hash=_precomputed_hash,
    )
    async with _run_prompt_semaphore:
        _result = await asyncio.to_thread(
            lambda: _workspace_api(selected, gpu).run_prompt.remote(
                workflow, input_images or {}, trace or {}, modal_options or {}, production_report,
            ),
        )
    _attach_waterfall_for_graph(_result, run_label="modal_client run_prompt")
    return _result


# NOTE: no @_modal_error_handler here — that decorator does `await func()`
# which breaks async generator functions.  Error handling is inline.
async def run_prompt_stream(
    workflow: dict,
    input_images: dict | None = None,
    trace: dict | None = None,
    production_report: dict | None = None,
    gpu: str | None = None,
    modal_options: dict | None = None,
    workspace: dict | None = None,
):
    """Execute workflow on Modal and stream progress events back to the caller.

    Yields dicts with types:
      {"type": "status", "message": "..."} — startup/restore phase.
      {"type": "progress", "event": "...", "data": {...}} — ComfyUI events.
      {"type": "result", "data": {...}} — final result (last yield).
      {"type": "error", "message": "..."} — fatal error.
    """
    selected = _resolve_workspace(workspace)
    # Local dispatch invariant: verify compiled workflow matches report
    _precomputed_hash = (trace or {}).get("canonical_workflow_hash", "")
    validate_production_dispatch(
        workflow, production_report,
        label="run_prompt_stream",
        workflow_hash=_precomputed_hash,
    )
    gen = None
    # ── V1 parity identity capture ─────────────────────────────────────
    _v1_identity = _capture_v1_deployment_identity(selected, gpu)
    _v1_identity["workspace_name"] = selected.get("name", "?")
    _v1_identity["workspace_id"] = selected.get("id", "?")[:12]
    # Enable permissive identity if not already set
    if trace is None:
        trace = {}
    _is_dict_trace = isinstance(trace, dict)

    # ── Profile publication phase markers (V1 ↦ V2 publish_restore_plan) ──
    if _is_dict_trace:
        trace["profile_publish_start"] = _time.time()
    print(f"[v1.diag] phase=profile_publish workspace={selected.get('name', '?')} "
          f"gpu={gpu or 'default'} identity_keys={list(_v1_identity.keys())}")
    # Profile publication happens implicitly via prepare_active_next_profile
    # on the local side (in __init__.py / canonical_execution.py).  The local
    # dispatch marker covers the same interval as V2's publish_restore_plan.
    if _is_dict_trace:
        trace["profile_publish_end"] = _time.time()

    # ── Local observation markers on the mutable trace dict ────────────
    # These are wall-clock observations from THIS side of the Modal
    # client — they do NOT observe internal platform restore boundaries.
    if _is_dict_trace:
        trace.setdefault("t2_local_dispatch", _time.time())
        trace["modal_handle_lookup_started"] = _time.time()
    print(f"[modal-client] phase=pre_gen workspace={selected.get('name', '?')} gpu={gpu or 'default'}")
    # Semaphore only serializes remote-generator creation, not iteration.
    # This prevents a caller that breaks early from blocking the next request.
    async with _run_prompt_semaphore:
        if _is_dict_trace:
            trace["modal_handle_lookup_completed"] = _time.time()
            trace["remote_generator_create_started"] = _time.time()
        # ── GPU submission marker (before generator creation) ──────────
        if _is_dict_trace:
            trace["gpu_submission_start"] = _time.time()
        # T2: immediately before the actual Modal remote call (legacy path)
        _t2_wall = int(_time.time() * 1_000_000_000)
        _t2_mono = _time.monotonic_ns()
        print(f"[v1.diag] comfy_modal_dispatch_start legacy_path request_id={trace.get('request_id','')[:16]}", flush=True)
        gen = _workspace_api(selected, gpu).run_prompt_stream.remote_gen.aio(
            workflow, input_images or {}, trace or {}, modal_options or {}, production_report,
        )
        # T3: after the generator object is successfully created
        _t3_wall = int(_time.time() * 1_000_000_000)
        _t3_mono = _time.monotonic_ns()
        print(f"[v1.diag] modal_call_created legacy_path request_id={trace.get('request_id','')[:16]}", flush=True)
        if _is_dict_trace:
            trace["remote_generator_create_completed"] = _time.time()
            trace["gpu_submission_end"] = _time.time()
            trace["comfy_modal_dispatch_start_wall_ns"] = _t2_wall
            trace["modal_call_created_wall_ns"] = _t3_wall
            trace["t2_wall_ns"] = _t2_wall
            trace["t3_wall_ns"] = _t3_wall
    print(f"[modal-client] phase=post_gen gen_created=True")
    if _is_dict_trace:
        _now_iter = _time.time()
        trace["remote_generator_iteration_started"] = _now_iter
        # remote_submit: same local-observation time as iteration start,
        # marking that the remote generator handoff is complete and the
        # first event is awaited.  This is an alias so both local-driven
        # (run_cell) and modal_client-driven flows produce a submit marker.
        if "remote_submit" not in trace:
            trace["remote_submit"] = _now_iter
            trace.setdefault("t2_local_dispatch", _now_iter)
        trace["v1_identity"] = dict(_v1_identity)
    _first_client_msg = True
    try:
        # V1 parity: collect the full result body
        _v1_result = None
        async for msg in gen:
            if _first_client_msg:
                first_msg = msg
                _first_client_msg = False
                if _is_dict_trace:
                    _first_msg_rcv_time = _time.time()
                    trace["first_remote_message_received"] = _first_msg_rcv_time
                    # GPU submit-to-first-event: compute interval delta from
                    # the existing gpu_submission_start marker (not an epoch
                    # timestamp stored in an interval field).
                    _gpu_sub_start = trace.get("gpu_submission_start", 0.0)
                    if _gpu_sub_start > 0:
                        _delta_s = _first_msg_rcv_time - _gpu_sub_start
                        trace["gpu_submit_to_first_event_ms"] = round(_delta_s * 1000, 2)
                        trace["gpu_submit_to_first_event_ns"] = int(round(_delta_s * 1_000_000_000))
                # V1 parity: enrich first-stream-event with identity for correlation
                if isinstance(first_msg, dict) and _is_dict_trace:
                    # Merge v1 identity into the status/progress payload (never
                    # overwrites existing identity fields from the remote side).
                    _first_identity = first_msg.setdefault("v1_identity", {})
                    for _ik, _iv in _v1_identity.items():
                        _first_identity.setdefault(_ik, _iv)
                print(f"[modal-client] phase=first_msg arrived=True")
            if isinstance(msg, dict) and msg.get("type") == "result":
                _v1_result = msg
                _rdata = msg.get("data")
                if isinstance(_rdata, dict):
                    _attach_waterfall_for_graph(
                        _rdata, run_label="modal_client run_prompt_stream",
                    )
            if isinstance(msg, dict) and msg.get("type") == "persistence":
                # Variant A: record the remote's definitive persistence
                # outcome (deferred commit) so the asset route / history can
                # distinguish pending, ok, and failed states after the caller
                # already received the result.
                try:
                    from comfymodal_runtime.modal_transport import record_persistence_status
                    _persist_key = str(
                        (trace or {}).get("prompt_id")
                        or (trace or {}).get("request_id")
                        or ""
                    )
                    if _persist_key:
                        record_persistence_status(_persist_key, msg)
                except Exception:
                    pass
            yield msg
    except TimeoutError:
        raise TimeoutError(
            "Modal request timed out. The container may be cold-starting (1-3 min)."
        )
    except (ConnectionError, OSError) as e:
        raise ConnectionError(
            "Modal connection failed. Check your internet connection and Modal token."
        ) from e
    except Exception as e:
        if getattr(type(e), "__module__", "").startswith("modal"):
            raise RuntimeError(
                f"Modal error: {e}. Try redeploying with the Deploy button."
            ) from e
        raise
    finally:
        if gen is not None:
            try:
                await gen.aclose()
            except Exception:
                pass


async def read_output_asset(
    backend_path: str,
    *,
    expected_sha256: str = "",
    gpu: str | None = None,
    workspace: dict | None = None,
) -> dict:
    selected = _resolve_workspace(workspace)
    return await _workspace_api(selected, gpu).read_output_asset.remote.aio(
        backend_path,
        expected_sha256,
    )


async def run_checkpoint_stream(
    checkpoint_id: str,
    worker_invocation_id: str,
    lease_generation: int,
    workflow: dict,
    triple: dict,
    lora_chain: dict,
    cells: list,
    experiment_id: str = "",
    revision: int = 0,
    deployment_generation: str = "",
    gpu: str | None = None,
    modal_options: dict | None = None,
    workspace: dict | None = None,
):
    """Execute a complete checkpoint block in a single Modal invocation.

    This is the real long-lived primitive the experiment suite requires:
    one Modal container stays alive for the duration of the checkpoint
    and runs every cell belonging to that checkpoint in the order
    supplied.  A caller breaks out of the generator (via stop_now) to
    cancel the checkpoint safely: the deployed side yields a
    ``cell.interrupted`` event for any cell that did not start, then a
    final ``checkpoint.completed`` summary.

    The ``experiment_id``, ``revision``, and ``deployment_generation``
    parameters are threaded through to the remote container so every
    yielded event carries the full lineage identifiers.

    Yields dicts with the same event types as ``run_prompt_stream``,
    plus a per-cell ``cell.completed`` / ``cell.failed`` /
    ``cell.interrupted`` event so the local ExperimentRunner can
    append a journal entry for each one.
    """
    selected = _resolve_workspace(workspace)
    gen = None
    async with _run_prompt_semaphore:
        gen = _workspace_api(selected, gpu).run_checkpoint_stream.remote_gen.aio(
            checkpoint_id, worker_invocation_id, lease_generation,
            workflow, triple, lora_chain, cells,
            experiment_id, revision, deployment_generation,
            modal_options or {},
        )
    try:
        async for msg in gen:
            # Only graph result / timing payloads get a waterfall.  Covers both
            # terminal ``type == "result"`` events and nested
            # ``cell.completed`` / ``cell.failed`` events carrying a graph
            # ``result`` dict.  Summaries, cells, and probes never get stages.
            _gres = graph_result_from_event(msg)
            if isinstance(_gres, dict):
                _attach_waterfall_for_graph(
                    _gres, run_label="modal_client run_checkpoint_stream",
                )
            yield msg
    except TimeoutError:
        raise TimeoutError(
            "Modal checkpoint run timed out. The container may be cold-starting."
        )
    except (ConnectionError, OSError) as e:
        raise ConnectionError(
            "Modal connection failed. Check your internet connection and Modal token."
        ) from e
    except Exception as e:
        if getattr(type(e), "__module__", "").startswith("modal"):
            raise RuntimeError(
                f"Modal error: {e}. Try redeploying with the Deploy button."
            ) from e
        raise
    finally:
        if gen is not None:
            try:
                await gen.aclose()
            except Exception:
                pass


@_modal_error_handler
async def get_object_info(workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_api(selected).object_info.remote())


@_modal_error_handler
async def health_check(workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_function("health_cpu", selected).remote())


@_modal_error_handler
async def download_model(
    url: str,
    filename: str,
    save_path: str = "checkpoints",
    hf_token: str = "",
    civitai_token: str = "",
    workspace: dict | None = None,
) -> dict:
    selected = _resolve_workspace(workspace)
    kwargs = dict(url=url, filename=filename, save_path=save_path, hf_token=hf_token)
    if civitai_token:
        kwargs["civitai_token"] = civitai_token
    return await asyncio.to_thread(
        lambda: _workspace_function("download_model_to_volume", selected).remote(**kwargs),
    )


async def download_model_stream(
    url: str,
    filename: str,
    save_path: str = "checkpoints",
    hf_token: str = "",
    civitai_token: str = "",
    workspace: dict | None = None,
):
    """Async generator yielding progress dicts from a Modal streaming download."""
    selected = _resolve_workspace(workspace)
    kwargs = dict(url=url, filename=filename, save_path=save_path, hf_token=hf_token)
    if civitai_token:
        kwargs["civitai_token"] = civitai_token
    loop = asyncio.get_running_loop()
    gen = await loop.run_in_executor(
        None,
        lambda: _workspace_function("download_model_stream", selected).remote_gen(**kwargs),
    )
    while True:
        try:
            item = await loop.run_in_executor(None, next, gen)
            yield item
        except StopIteration:
            break


@_modal_error_handler
async def batch_download_models(
    items: list,
    hf_token: str = "",
    civitai_token: str = "",
    workspace: dict | None = None,
) -> list:
    selected = _resolve_workspace(workspace)
    kwargs = dict(hf_token=hf_token)
    if civitai_token:
        kwargs["civitai_token"] = civitai_token
    return await asyncio.to_thread(
        lambda: _workspace_function("batch_download_models", selected).remote(items, **kwargs),
    )


@_modal_error_handler
async def list_models(workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_function("list_models_cpu", selected).remote())


@_modal_error_handler
async def delete_model(folder: str, filename: str, workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_function("delete_model_cpu", selected).remote(folder=folder, filename=filename),
    )


@_modal_error_handler
async def sync_custom_nodes(
    archive_data: bytes,
    workspace: dict | None = None,
    app_name: str | None = CUSTOM_NODES_PUBLISHER_APP_NAME,
    publisher_app_name: str | None = None,
) -> dict:
    """Publish custom-node content through the shared authority.

    ``app_name`` is retained for callers of the old client API.  New callers
    use the explicit publisher spelling, and the default is always the stable
    shared publisher rather than a consumer-derived app.
    """
    selected = _resolve_workspace(workspace)
    # The old ``app_name`` parameter is retained for source compatibility, but
    # it is not an ownership selector.  A consumer must not be able to route a
    # write to a different publisher app.
    _ = app_name, publisher_app_name
    app_name = CUSTOM_NODES_PUBLISHER_APP_NAME
    environment_name = str(selected.get("environment") or "(default)")
    if environment_name == "(default)":
        environment_name = None
    if app_name is None:
        operation = lambda: _workspace_function(
            "sync_custom_nodes_to_volume", selected,
            environment_name=environment_name,
        ).remote(archive_data)
    else:
        operation = lambda: _workspace_function(
            "sync_custom_nodes_to_volume", selected, app_name=app_name,
            environment_name=environment_name,
        ).remote(archive_data)
    return await asyncio.to_thread(
        operation,
    )


@_modal_error_handler
async def refresh_custom_nodes(
    expected_nodes: list | None = None,
    workspace: dict | None = None,
) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_api(selected).refresh_custom_nodes.remote(expected_nodes or []),
    )


@_modal_error_handler
async def get_sync_status(workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_function("get_volume_status", selected).remote(),
    )


@_modal_error_handler
async def upload_model_to_volume(
    file_data: bytes,
    folder: str,
    filename: str,
    workspace: dict | None = None,
) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_function("upload_model_to_volume", selected).remote(file_data, folder, filename),
    )


@_modal_error_handler
async def upload_model_chunk(
    chunk_data: bytes,
    folder: str,
    filename: str,
    offset: int,
    is_last: bool,
    workspace: dict | None = None,
) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_function("upload_model_chunk", selected).remote(
            chunk_data, folder, filename, offset, is_last,
        ),
    )


@_modal_error_handler
async def resync_runtime(scope: str = "all", workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_api(selected).resync_runtime.remote(scope))


@_modal_error_handler
async def get_runtime_state(workspace: dict | None = None) -> dict:
    """Check runtime state — CPU-only, no GPU needed."""
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_function("runtime_state_cpu", selected).remote())


async def set_active_warmup_profile(payload: dict, workspace: dict | None = None) -> dict:
    """Write an active warmup profile to the runtime-config Volume.

    CPU-only Modal function call with configurable timeout.
    Uses Modal 1.4.3+ native async ``.remote.aio()``.
    """
    selected = _resolve_workspace(workspace)
    env = _resolve_v1_environment()
    timeout = float(os.environ.get("COMFYMODAL_PROFILE_SETTER_TIMEOUT", "120"))
    handle = _workspace_function("set_active_warmup_profile", selected, environment_name=env)
    try:
        return await asyncio.wait_for(
            handle.remote.aio(payload),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise TimeoutError(
            f"[modal-client] phase=set_active_warmup_profile "
            f"app={APP_NAME} workspace={selected.get('name', '?')} "
            f"env={env or '(default)'} timed out after {timeout}s"
        )
    except (ConnectionError, OSError) as e:
        raise ConnectionError(
            f"[modal-client] phase=set_active_warmup_profile "
            f"app={APP_NAME} workspace={selected.get('name', '?')} "
            f"env={env or '(default)'} connection failed: {e}"
        ) from e
    except Exception as e:
        if getattr(type(e), "__module__", "").startswith("modal"):
            raise RuntimeError(
                f"[modal-client] phase=set_active_warmup_profile "
                f"app={APP_NAME} workspace={selected.get('name', '?')} "
                f"env={env or '(default)'} error: {e}"
            ) from e
        raise


async def check_active_warmup_profile(stable_key: str, workspace: dict | None = None) -> dict:
    """Read-only identity seam: check if a profile matching *stable_key*
    already exists on the runtime-config volume.

    CPU-only, no GPU cost, no side effects (no Volume commit).
    Returns ``{"matched": True, "profile_token": str}`` on match,
    ``{"matched": False}`` otherwise.

    Uses Modal 1.4.3+ native async ``.remote.aio()``.
    TimeoutError propagates to the caller (not swallowed by fail-open).
    """
    selected = _resolve_workspace(workspace)
    env = _resolve_v1_environment()
    timeout = float(os.environ.get("COMFYMODAL_PROFILE_CHECKER_TIMEOUT", "60"))
    handle = _workspace_function("check_active_warmup_profile", selected, environment_name=env)
    try:
        return await asyncio.wait_for(
            handle.remote.aio(stable_key),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise TimeoutError(
            f"[modal-client] phase=check_active_warmup_profile "
            f"app={APP_NAME} workspace={selected.get('name', '?')} "
            f"env={env or '(default)'} timed out after {timeout}s"
        )
    except (ConnectionError, OSError) as e:
        raise ConnectionError(
            f"[modal-client] phase=check_active_warmup_profile "
            f"app={APP_NAME} workspace={selected.get('name', '?')} "
            f"env={env or '(default)'} connection failed: {e}"
        ) from e
    except Exception as e:
        if getattr(type(e), "__module__", "").startswith("modal"):
            raise RuntimeError(
                f"[modal-client] phase=check_active_warmup_profile "
                f"app={APP_NAME} workspace={selected.get('name', '?')} "
                f"env={env or '(default)'} error: {e}"
            ) from e
        raise


def persist_clip_cache_payload(
    payload: dict,
    workspace: dict | None = None,
    *,
    timeout_s: float = 30.0,
) -> dict:
    """Synchronous post-delivery persistence of a CLIP-encoding payload.

    Calls a small CPU-only Modal function mounted to a dedicated
    prompt-encoding cache Volume.  Failures are returned as a dict
    with ``status="error"``; the caller never raises out of this path.

    The wrapper is intentionally narrow and synchronous because it is
    invoked from a background worker that has already detached from the
    user-visible request.  The local caller wraps it in
    ``PostDeliveryPersistenceDispatcher``.

    ``timeout_s`` is honored: the dispatcher bounds the
    semaphore acquisition time on the calling side, but the
    actual ``fn()`` execution is bounded indirectly by the
    Modal function's ``timeout=30``.  There is no per-task
    wall-clock timeout on ``fn()`` itself in the dispatcher;
    if the remote function hangs, the dispatcher will block
    in the worker until the Modal RPC times out at the
    function layer.  The local ``_deadline`` is used for
    diagnostics only.
    """
    import time as _t
    _deadline = _t.time() + max(1.0, float(timeout_s))
    try:
        selected = _resolve_workspace(workspace)
        fn = _workspace_function("persist_clip_cache_payload", selected)
        # Modal functions do not accept a per-call timeout kwarg for
        # ``.remote()``; the function's own ``timeout=30`` on the
        # remote side bounds the call. The dispatcher's per-task
        # timeout is the second line of defense.
        return fn.remote(payload)
    except Exception as exc:  # never raise out
        try:
            _err = f"{type(exc).__name__}: {exc}"[:200]
        except Exception:
            _err = "persist_clip_cache_payload_unreachable"
        return {"status": "error", "error": _err, "deadline_unix_s": _deadline}


def persist_validation_certificate(
    candidate: dict,
    workspace: dict | None = None,
    *,
    timeout_s: float = 60.0,
) -> dict:
    """Synchronous post-delivery persistence of a validation certificate.

    Calls a small CPU-only Modal function mounted to the runtime-config
    Volume (not the models Volume).  Failures are returned as a dict with
    ``status="error"``; the caller never raises out of this path.

    Wraps the same workspace-capture pattern as persist_clip_cache_payload.
    """
    import time as _t
    _deadline = _t.time() + max(1.0, float(timeout_s))
    try:
        selected = _resolve_workspace(workspace)
        fn = _workspace_function("persist_validation_certificate", selected)
        return fn.remote(candidate)
    except Exception as exc:
        try:
            _err = f"{type(exc).__name__}: {exc}"[:200]
        except Exception:
            _err = "persist_validation_certificate_unreachable"
        return {"status": "error", "error": _err, "deadline_unix_s": _deadline}


def lookup_clip_cache(
    bundle_hash: str,
    clip_fingerprint_key: str,
    workspace: dict | None = None,
) -> dict:
    """Synchronous lookup of a prompt-cache bundle. Returns
    ``{"status": "ok", "entry": ...}`` on hit or ``{"status": "miss", ...}``.
    Never raises out; errors become misses."""
    try:
        selected = _resolve_workspace(workspace)
        fn = _workspace_function("lookup_clip_cache", selected)
        return fn.remote(bundle_hash, clip_fingerprint_key)
    except Exception as exc:
        try:
            return {"status": "miss", "reason": f"{type(exc).__name__}: {exc}"[:120]}
        except Exception:
            return {"status": "miss", "reason": "lookup_clip_cache_unreachable"}


@_modal_error_handler
async def persist_clip_cache_payload_async(
    payload: dict, workspace: dict | None = None
) -> dict:
    """Async variant of ``persist_clip_cache_payload`` for tests."""
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_function("persist_clip_cache_payload", selected).remote(payload),
    )
