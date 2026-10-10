"""Config-bound Golden execution for the Studio Workflow route.

The ordinary Studio path remains owned by ``studio_workflow_run``.  This lane
only handles an explicit, config-selected Golden profile and intentionally
submits the resolved workflow prompt directly to the profile's registered
Golden generator instead of compiling a generic production plan.
"""

from __future__ import annotations

import copy
import asyncio
import re
import time
import uuid
import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from tools.v2_control.profile_catalog import GoldenProfile, resolve_golden_profile

_log = logging.getLogger(__name__)

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
DEFAULT_MAX_EVENTS = 256
DEFAULT_MAX_RUNS = 32
DEFAULT_TTL_SECONDS = 15 * 60

# Studio's own Golden adapter.  It exists solely to carry the live stage
# progress bridge; the ordinary v2ctl Golden methods must never contain it.
STUDIO_STREAM_METHOD = "run_golden_studio_stream"


class GoldenRunError(ValueError):
    """A Golden request was invalid or could not be submitted safely."""


def validate_request_id(request_id: Any) -> str:
    value = str(request_id or "").strip()
    if not REQUEST_ID_RE.fullmatch(value):
        raise GoldenRunError("request_id must be 1-128 path-safe characters")
    return value


@dataclass
class _RunEvents:
    created_at: float
    touched_at: float
    events: deque[dict[str, Any]] = field(default_factory=deque)
    next_cursor: int = 0
    terminal: bool = False


class GoldenStageEventStore:
    """Bounded, process-local event store for live Golden progress polling."""

    def __init__(
        self,
        *,
        max_events: int = DEFAULT_MAX_EVENTS,
        max_runs: int = DEFAULT_MAX_RUNS,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_events < 1 or max_runs < 1 or ttl_seconds <= 0:
            raise ValueError("Golden event-store bounds must be positive")
        self.max_events = int(max_events)
        self.max_runs = int(max_runs)
        self.ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._runs: dict[str, _RunEvents] = {}

    @property
    def active_count(self) -> int:
        self._prune()
        return sum(not run.terminal for run in self._runs.values())

    def start(self, request_id: str) -> None:
        request_id = validate_request_id(request_id)
        self._prune()
        existing = self._runs.get(request_id)
        if existing is not None and not existing.terminal:
            raise GoldenRunError("request_id is already running")
        if existing is not None:
            del self._runs[request_id]
        if len(self._runs) >= self.max_runs:
            completed = [
                (key, run) for key, run in self._runs.items() if run.terminal
            ]
            if completed:
                oldest = min(completed, key=lambda item: item[1].touched_at)[0]
                del self._runs[oldest]
            else:
                raise GoldenRunError("Golden run concurrency limit reached")
        now = self._clock()
        self._runs[request_id] = _RunEvents(created_at=now, touched_at=now)

    def append(self, request_id: str, remote_event: Mapping[str, Any]) -> dict[str, Any]:
        request_id = validate_request_id(request_id)
        run = self._runs.get(request_id)
        if run is None:
            raise KeyError(request_id)
        if not isinstance(remote_event, Mapping):
            remote_event = {"type": "event", "data": remote_event}
        event = copy.deepcopy(dict(remote_event))
        run.next_cursor += 1
        # ``sequence`` belongs to Golden.  The local cursor is deliberately a
        # separate field so polling never rewrites remote sequencing evidence.
        event["cursor"] = run.next_cursor
        run.events.append(event)
        while len(run.events) > self.max_events:
            run.events.popleft()
        run.touched_at = self._clock()
        if _is_terminal(event):
            run.terminal = True
        return copy.deepcopy(event)

    def finish(self, request_id: str) -> None:
        run = self._runs.get(validate_request_id(request_id))
        if run is not None:
            run.terminal = True
            run.touched_at = self._clock()

    def read(self, request_id: str, cursor: int = 0) -> dict[str, Any]:
        request_id = validate_request_id(request_id)
        if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
            raise GoldenRunError("cursor must be a non-negative integer")
        self._prune()
        run = self._runs.get(request_id)
        if run is None:
            raise KeyError(request_id)
        run.touched_at = self._clock()
        events = [
            copy.deepcopy(event)
            for event in run.events
            if int(event.get("cursor", 0)) > cursor
        ]
        next_cursor = max([cursor] + [int(event["cursor"]) for event in events])
        return {
            "status": "ok",
            "request_id": request_id,
            "cursor": next_cursor,
            "events": events,
            "terminal": bool(run.terminal),
        }

    def _prune(self) -> None:
        now = self._clock()
        expired = [
            key for key, run in self._runs.items()
            if now - run.touched_at >= self.ttl_seconds
        ]
        for key in expired:
            self._runs.pop(key, None)


def _is_terminal(event: Mapping[str, Any]) -> bool:
    if event.get("terminal") is True:
        return True
    return str(event.get("type", "")).strip().lower() in {
        "result", "error", "cancelled",
    }


EVENT_STORE = GoldenStageEventStore()


def browser_override_error(body: Mapping[str, Any]) -> str | None:
    """Reject target/resource/flag selectors from the browser boundary."""
    forbidden = {
        "app", "app_name", "class", "class_name", "method", "method_name",
        "target", "gpu", "flags", "flag", "flag_overrides", "flagoverrides",
        "runtime_overrides", "resources", "cpu", "memory_mb", "golden_mode",
        "attention_backend", "cpu_qd2_prefetch", "deep_trace",
    }
    present = sorted(key for key in body if str(key).strip().lower() in forbidden)
    modal_options = body.get("modal_options")
    if isinstance(modal_options, Mapping):
        present.extend(
            f"modal_options.{key}"
            for key in modal_options
            if str(key).strip().lower() in forbidden
        )
    if present:
        return "browser target/resource/flag overrides are not accepted: " + ", ".join(present)
    return None


# Modal clients and class handles are reused across runs. Building a fresh
# client per run is cheap to construct but defers its real cost (TLS, auth and
# connection setup) to the first remote call, where it lands as measurable
# latency before Modal has even created an input. Measured against Modal's own
# timeline: 12.08s from issuing the call to the first stage event, of which only
# 5.49s is Modal's input-created -> execution-started. v2ctl reuses its client,
# which is why it is near-instant.
_MODAL_CLIENT_CACHE: dict[tuple, Any] = {}


def _clear_modal_client_cache() -> None:
    _MODAL_CLIENT_CACHE.clear()


def _default_handle_factory(
    profile: GoldenProfile,
    workspace: Mapping[str, Any] | None,
) -> Any:
    """Resolve exactly the config-owned app/class; never read browser target data."""
    try:
        import modal
    except Exception as exc:  # pragma: no cover - exercised only in live lane
        raise GoldenRunError("Modal SDK is unavailable") from exc
    workspace = workspace or {}
    token_id = str(workspace.get("token_id") or "")
    token_secret = str(workspace.get("token_secret") or "")
    if not token_id or not token_secret:
        raise GoldenRunError("Golden execution requires an active Modal workspace")
    environment = str(workspace.get("environment") or "") or None
    cache_key = (
        token_id,
        token_secret,
        profile.target["app"],
        profile.target["class"],
        environment or "",
    )
    cached = _MODAL_CLIENT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    client = modal.Client.from_credentials(token_id, token_secret)
    cls = modal.Cls.from_name(
        profile.target["app"],
        profile.target["class"],
        client=client,
        environment_name=environment,
    )
    handle = cls()
    _MODAL_CLIENT_CACHE[cache_key] = handle
    return handle


def _materialize_image(result: Any, request_id: str) -> dict[str, Any]:
    """Write Golden's generated PNG where Studio renders it, and add output_paths.

    Golden returns the encoded image inline under ``images[].data`` because the
    default output-durability mode is ``off`` and nothing is committed to a
    Volume.  The Playground renders ``output_paths`` through
    ``/studio/outputs/<name>``, so the bytes are materialized into that same
    outputs directory here and the inline copy is dropped.

    The written file is verified against Golden's own observed ``byte_count``
    and ``image_sha256`` when both are available: a short or mis-hashed write is
    reported, never presented as a successful output.
    """
    if not isinstance(result, dict):
        return {}
    import base64
    import hashlib

    images = result.get("images")
    if not isinstance(images, list) or not images:
        return result
    first = images[0]
    if not isinstance(first, dict):
        return result
    encoded = str(first.get("data") or "")
    if not encoded:
        return result

    data = dict(result)
    try:
        from local_artifacts import get_studio_outputs_dir

        raw = base64.b64decode(encoded)
        expected_bytes = first.get("byte_count")
        if isinstance(expected_bytes, int) and len(raw) != expected_bytes:
            raise ValueError(
                "materialized_byte_count_mismatch:%d!=%d" % (len(raw), expected_bytes)
            )
        digest = str(first.get("asset_id") or result.get("image_sha256") or "")[:16]
        name = "golden_%s_%s.png" % (digest or "image", request_id)
        out_dir = get_studio_outputs_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / name).write_bytes(raw)

        expected_sha = str(result.get("image_sha256") or "")
        observed = ""
        if expected_sha:
            observed = hashlib.sha256(raw).hexdigest()
            data["materialized_sha256"] = observed
            data["materialized_sha256_match"] = observed == expected_sha
            if observed != expected_sha:
                # A mis-hashed write must never be presented as a successful
                # materialization.  Remove it and fail closed: no output_paths
                # is published, so the Studio canvas/carousel cannot paint it.
                try:
                    (out_dir / name).unlink()
                except OSError:
                    pass
                raise ValueError("materialized_sha256_mismatch")

        data["output_paths"] = [name]
        # The inline copy is large and no longer needed once it is on disk.
        trimmed = [dict(entry) for entry in images]
        trimmed[0].pop("data", None)
        data["images"] = trimmed
        return data
    except Exception as exc:  # noqa: BLE001
        data["output_materialization_error"] = str(exc)[:300]
        return data


def _primary_output_path(materialized: Any) -> str:
    """Best-effort primary output path from a materialized Golden result.

    ``output_paths`` is the key ``_materialize_image`` publishes, and it is a
    LIST.  It must be read here: it is the ONLY place the materialized
    on-disk name appears, so skipping it means no output candidate ever
    reaches the writer, no asset is attached, and the History record shows
    no image at all.
    """
    if not isinstance(materialized, Mapping):
        return ""
    paths = materialized.get("output_paths")
    if isinstance(paths, str) and paths:
        return paths
    if isinstance(paths, (list, tuple)):
        for item in paths:
            if isinstance(item, str) and item:
                return item
    for key in ("output_path", "primary_output_path"):
        value = materialized.get(key)
        if value:
            return str(value)
    for key in ("outputs", "images"):
        items = materialized.get(key)
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, str):
                return first
            if isinstance(first, Mapping):
                for sub in ("path", "output_path", "filename"):
                    if first.get(sub):
                        return str(first[sub])
    return ""


def _golden_stage_timings(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive per-stage durations from Golden's own stage-boundary events.

    Golden emits ``golden_stage`` events carrying per-stage
    ``entry_monotonic_ns`` / ``end_monotonic_ns`` (see
    ``golden_serial._observe_stage``).  Only CLOSED stages produce a row and
    the value is Golden's own monotonic measurement — never a local
    re-measurement or an estimate.  Returns ``{}`` when no stage closed, so
    History keeps showing "Diagnostics pending" rather than fabricated zeros.
    """
    stages: list[dict[str, Any]] = []
    for event in events:
        if str(event.get("type", "")).strip().lower() != "golden_stage":
            continue
        label = str(event.get("stage") or "").strip()
        if not label:
            continue
        start = event.get("entry_monotonic_ns")
        end = event.get("end_monotonic_ns")
        if not isinstance(start, int) or not isinstance(end, int) or end < start:
            continue
        stages.append({
            "label": label,
            "durationMs": round((end - start) / 1_000_000, 3),
        })
    if not stages:
        return {}
    return {"_run_type": "golden", "stages": stages}


def _canonical_golden_fast_path(workflow: Mapping[str, Any]) -> bool:
    """Return true only for the proven canonical Golden graph family."""
    try:
        from comfymodal_runtime.golden_serial import (
            derive_golden_workflow_plan,
            resolve_golden_node_map,
        )

        node_map = resolve_golden_node_map(dict(workflow), allow_replacements=False)
        plan = derive_golden_workflow_plan(dict(workflow), node_map)
        return bool(plan.canonical_fast_path)
    except Exception:
        return False


def _golden_history_meta(
    request_id: str,
    profile: GoldenProfile,
    controls: Mapping[str, Any] | None,
) -> dict[str, Any]:
    controls_map = controls if isinstance(controls, Mapping) else {}
    return {
        "source": "studio_golden",
        "golden_profile": profile.name,
        "golden_request_id": request_id,
        "golden_method": profile.target["method"],
        "golden_app": profile.target["app"],
        "prompt": str(controls_map.get("prompt") or ""),
        "negative_prompt": str(controls_map.get("negative_prompt") or ""),
        "studio_workflow_id": str(controls_map.get("_workflow_id") or ""),
    }


def _fail_golden_history(run_id: str, error: str) -> None:
    """Close an opened Golden History record as failed.

    Without this a run that errors after ``_begin_golden_history`` would stay
    ``running`` forever.  Best-effort, never raises.
    """
    if not run_id:
        return
    try:
        from experiment_service import REGISTRY
    except Exception as exc:
        _log.warning("Golden history: REGISTRY unavailable: %s", exc)
        return
    try:
        REGISTRY.history().update_run(
            run_id,
            status="failed",
            meta={"error": error},
        )
    except Exception as exc:
        _log.warning("Golden history: failed to close run %s: %s", run_id, exc)


def _begin_golden_history(
    request_id: str,
    profile: GoldenProfile,
    controls: Mapping[str, Any] | None,
) -> tuple[str, str]:
    """Open the nonterminal History record BEFORE the run is dispatched.

    Recording only after completion made ``started_at`` land at completion
    time, so every Golden run reported a ~1s total time instead of its real
    multi-second wall time.  Opening the record first makes the attempt span
    the actual run, and ``update_run`` still supplies the terminal status,
    the output association, and timings afterwards.

    Best-effort by design: History is a record, not the execution contract, so
    a recording failure must never fail a run.  Returns (legacy run id,
    History V2 generation id), with "" for either half when unavailable.
    """
    try:
        from experiment_service import REGISTRY
    except Exception as exc:
        _log.warning("Golden history: REGISTRY unavailable: %s", exc)
        return "", ""
    try:
        record = REGISTRY.history().record_run(
            kind="playground_run",
            prompt_id=request_id,
            status="running",
            meta=_golden_history_meta(request_id, profile, controls),
        )
        if not isinstance(record, dict):
            return "", ""
        return str(record.get("run_id") or ""), str(record.get("history_generation_id") or "")
    except Exception as exc:
        _log.warning("Golden history: failed to open run %s: %s", request_id, exc)
        return "", ""


def _complete_golden_history(
    run_id: str,
    materialized: Any,
    timings: Mapping[str, Any] | None = None,
) -> None:
    """Apply the terminal status, output association, and timings.

    ``output_path`` is what makes the produced image appear in History; it
    must be a real materialized name on disk.  Best-effort, never raises.
    """
    if not run_id:
        return
    try:
        from experiment_service import REGISTRY
    except Exception as exc:
        _log.warning("Golden history: REGISTRY unavailable: %s", exc)
        return
    try:
        update_kwargs: dict[str, Any] = {"status": "completed"}
        output_path = _primary_output_path(materialized)
        if output_path:
            update_kwargs["output_path"] = output_path
        if timings:
            update_kwargs["timings"] = dict(timings)
        REGISTRY.history().update_run(run_id, **update_kwargs)
    except Exception as exc:
        # Never swallow silently: an unlogged History failure is
        # indistinguishable from "the run was never recorded".
        _log.warning("Golden history: failed to record run %s: %s", run_id, exc)


async def run_golden_workflow(
    *,
    workflow_id: str,
    version_id: str,
    controls: Mapping[str, Any] | None,
    request_id: str,
    node_dir: str | Path,
    profile_name: str,
    # Retired by the Studio preset collapse (f3954638): control defaults now
    # come from the version's own executable_prompt. Kept as an optional
    # argument so pre-collapse callers still work; nothing reads it.
    preset_id: str = "",
    workspace: Mapping[str, Any] | None = None,
    event_store: GoldenStageEventStore = EVENT_STORE,
    handle_factory: Callable[[GoldenProfile, Mapping[str, Any] | None], Any] | None = None,
) -> dict[str, Any]:
    """Resolve controls, submit the selected Golden method, and retain events."""
    request_id = validate_request_id(request_id)
    profile = resolve_golden_profile(profile_name)

    # Reuse the established Studio workflow seam read-only.  In particular,
    # this preserves version/preset ownership and verbatim control mapping.
    from studio_workflow_run import (
        apply_workflow_values_to_prompt,
        build_workflow_execution_plan,
        merge_workflow_controls,
        _normalize_model_loader_names,
        resolve_workflow_run_bundle,
    )

    # The Studio preset collapse removed preset_id and
    # allow_remote_execution from this seam; control defaults now come from
    # the version's own executable_prompt via bundle["defaults"].
    bundle = resolve_workflow_run_bundle(
        workflow_id,
        version_id,
        node_dir,
        remote_model_readiness=True,
    )
    if bundle.get("status") != "ok":
        return bundle
    merged = merge_workflow_controls(
        bundle["defaults"], dict(controls or {}), bundle["control_schema"],
    )
    if merged["errors"]:
        return {
            "status": "error",
            "error_code": "WORKFLOW_CONTROL_VALIDATION",
            "message": "; ".join(
                f"{error['field']}: {error['message']}" for error in merged["errors"]
            ),
            "errors": merged["errors"],
        }
    applied = apply_workflow_values_to_prompt(
        bundle["executable_prompt"], bundle["control_schema"], merged["values"],
    )
    if "error" in applied:
        return {
            "status": "error",
            "error_code": "WORKFLOW_CONTROL_APPLICATION",
            "message": str(applied["error"]),
        }
    _normalize_model_loader_names(applied["workflow"])
    use_generic_executor = not _canonical_golden_fast_path(applied["workflow"])

    event_store.start(request_id)
    # The deployed C0 source owner is a deploy-baked arm, and Golden requires
    # the request to declare the SAME arm it was deployed with.  Read it from
    # the resolved profile so the request cannot disagree with the deployment.
    _effective_flags = {}
    try:
        from tools.v2_control.fingerprints import FingerprintEngine

        _effective_flags = FingerprintEngine(profile.config).effective_flag_values()
    except Exception:
        _effective_flags = {}
    _source_threads = str(
        _effective_flags.get("COMFYMODAL_GOLDEN_C0_SOURCE_THREADS", "") or ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    payload = {
        "request_id": request_id,
        "prompt": applied["workflow"],
        "extra_data": {
            "client_id": request_id,
            "workflow_id": str(workflow_id or ""),
            "workflow_version_id": str(version_id or ""),
            "studio_controls": copy.deepcopy(merged["values"]),
        },
        "modal_options": {},
        "stream_golden_stage_events": True,
        "c0_source_threads": _source_threads,
        "golden_mode": (
            "parallel"
            if profile.target["method"] == "run_golden_parallel_stream"
            else "serial"
        ),
        "request_origin_info": {
            "studio": True,
            "profile": profile.name,
            "method": profile.target["method"],
            "request_id": request_id,
        },
    }

    history_run_id = ""
    history_generation_id = ""
    try:
        # Make the run visible on the History page. Golden bypasses the ordinary
        # save-history seam, so without this the image existed only in the
        # Playground's local store.  The record is opened BEFORE dispatch so the
        # attempt's started_at is the real run start (otherwise every Golden run
        # reported a ~1s total time), then completed below with the output and
        # timings.  Both halves are best-effort and never fail a run.
        history_run_id, history_generation_id = _begin_golden_history(request_id, profile, merged["values"])
        handle = (
            handle_factory(profile, workspace)
            if handle_factory is not None
            else _default_handle_factory(profile, workspace)
        )
        if use_generic_executor:
            plan, plan_error = build_workflow_execution_plan(
                bundle,
                merged["values"],
                modal_options={},
                comfyui_root=str(node_dir),
            )
            if plan_error is not None or plan is None:
                raise GoldenRunError(str(plan_error or "generic_execution_plan_failed"))
            remote_method = getattr(handle, "run_plan_stream")
            remote_gen = getattr(remote_method, "remote_gen", None)
            if remote_gen is None or not callable(getattr(remote_gen, "aio", None)):
                raise GoldenRunError("generic Studio executor is not a stream")
            stream = remote_gen.aio(plan.to_dict(), request_id=request_id)
        else:
            # Canonical Studio workflows keep the dedicated Golden adapter and
            # its bounded stage-progress bridge.
            remote_method = getattr(handle, STUDIO_STREAM_METHOD)
            remote_gen = getattr(remote_method, "remote_gen", None)
            if remote_gen is None or not callable(getattr(remote_gen, "aio", None)):
                raise GoldenRunError(
                    f"Studio adapter {STUDIO_STREAM_METHOD!r} is not a stream"
                )
            stream = remote_gen.aio(payload)
        if hasattr(stream, "__await__"):
            stream = await stream
        terminal: dict[str, Any] | None = None
        stage_events: list[dict[str, Any]] = []
        async for remote_event in stream:
            stored = event_store.append(request_id, remote_event)
            stage_events.append(stored)
            if str(stored.get("type", "")).lower() in {"result", "error"}:
                terminal = stored
        event_store.finish(request_id)
        if terminal is None:
            _fail_golden_history(history_run_id, "Golden stream ended without a terminal event")
            return {
                "status": "error",
                "message": "Golden stream ended without a terminal event",
                "request_id": request_id,
                "runId": request_id,
            }
        if terminal.get("type") == "error":
            _fail_golden_history(
                history_run_id,
                str(terminal.get("message") or "Golden execution failed"),
            )
            return {
                "status": "error",
                "message": str(terminal.get("message") or "Golden execution failed"),
                "request_id": request_id,
                "runId": request_id,
                "profile": profile.name,
            }
        materialized = _materialize_image(terminal.get("data", terminal), request_id)
        _complete_golden_history(
            history_run_id,
            materialized,
            timings=_golden_stage_timings(stage_events),
        )
        # The Studio result contract is flat: the Playground reads
        # ``payload.output_paths`` directly.  Merge the materialized result to
        # the top level and keep the raw Golden payload under ``result`` for
        # provenance, so the existing frontend contract is satisfied without a
        # second renderer.
        response = {
            "status": "ok",
            "request_id": request_id,
            "runId": request_id,
            "profile": profile.name,
            "result": materialized,
            # Bridge to the History V2 generation for this run so the
            # Playground preview renders the exact record History shows.
            "historyGenerationId": history_generation_id or "",
        }
        for key, value in materialized.items():
            if key in {"outputs", "images"}:
                continue
            response.setdefault(key, value)
        return response
    except asyncio.CancelledError:
        if request_id in event_store._runs:
            event_store.append(request_id, {
                "type": "error",
                "request_id": request_id,
                "message": "Golden execution cancelled",
            })
            event_store.finish(request_id)
        _fail_golden_history(history_run_id, "Golden execution cancelled")
        raise
    except Exception as exc:
        # Drop cached Modal handles on failure so a stale/redeployed handle
        # cannot wedge every future run. Caching is an optimisation only; it
        # must never turn one transient failure into a permanent one.
        try:
            _clear_modal_client_cache()
        except Exception:
            pass
        _fail_golden_history(history_run_id, f"{type(exc).__name__}: {exc}"[:500])
        if request_id in event_store._runs:
            event_store.append(request_id, {
                "type": "error",
                "request_id": request_id,
                "message": str(exc)[:500],
            })
            event_store.finish(request_id)
        return {
            "status": "error",
            "message": str(exc)[:500],
            "request_id": request_id,
            "runId": request_id,
            "profile": profile.name,
        }


# Explicit name for callers that want to distinguish this from the legacy run.
execute_studio_golden_run = run_golden_workflow
