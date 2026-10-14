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
import json
from collections import deque
from collections.abc import AsyncIterator
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

# Studio batch adapter: one Modal call executes N variants sequentially in
# the SAME container.  Deliberately uncapped: the caller splits only by
# workflow identity, and per-variant results stream out as they complete so
# no single response grows without bound.
STUDIO_BATCH_METHOD = "run_golden_studio_batch_stream"


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


def _modal_lifecycle_phase(text: str, task_state: str = "") -> str | None:
    value = str(text).lower()
    if "restoring function from memory snapshot" in value or task_state == "TASK_STATE_LOADING_CHECKPOINT_IMAGE":
        return "restoring"
    if ("[v2.startup_stage] stage=snapshot_startup_callback event=return" in value
            or "[v2.lifecycle] method=startup snap=true" in value
            or "creating memory snapshot" in value):
        return "snapshot_capturing"
    if "[v2.snapshot_pools] stage=before_snapshot_capture" in value:
        return "snapshot_preparing"
    if "[v2.snapshot_runtime]" in value or "[v2.snapshot_target]" in value:
        return "startup"
    return {
        "TASK_STATE_CREATED": "scheduling",
        "TASK_STATE_QUEUED": "scheduling",
        "TASK_STATE_WORKER_ASSIGNED": "startup",
        "TASK_STATE_LOADING_IMAGE": "startup",
        "TASK_STATE_CREATING_CONTAINER": "startup",
    }.get(task_state)


def _studio_span_events(text: str, request_id: str) -> list[dict[str, Any]]:
    events = []
    for line in str(text).splitlines():
        if not line.startswith("[v2.studio_span] "):
            continue
        try:
            event = json.loads(line[len("[v2.studio_span] "):])
        except (ValueError, TypeError):
            continue
        if (isinstance(event, dict) and event.get("request_id") == request_id
                and event.get("type") == "gantt_span"):
            events.append(event)
    return events


async def _observe_modal_lifecycle(
    profile: GoldenProfile,
    workspace: Mapping[str, Any],
    remote_method: Any,
    request_id: str,
    event_store: GoldenStageEventStore,
    submitted_at: float,
) -> None:
    try:
        from modal.client import _Client
        from modal.cli.app import resolve_app_identifier
        from modal_proto import api_pb2

        client = await _Client.from_credentials(workspace["token_id"], workspace["token_secret"])
        environment = str(workspace.get("environment") or "")
        if environment == "(default)":
            environment = ""
        app_id, _, _ = await resolve_app_identifier(profile.target["app"], environment, client)
        await remote_method.hydrate.aio()
        function_id = remote_method.object_id
        cursor = ""
        task_ids: set[str] = set()
        last_phase = ""
        async with asyncio.timeout(1800):
            while True:
                query = api_pb2.AppGetLogsRequest(
                    app_id=app_id, function_id=function_id, timeout=2, last_entry_id=cursor,
                )
                async for batch in client.stub.AppGetLogs.unary_stream(query):
                    if batch.entry_id:
                        cursor = batch.entry_id
                    if batch.app_done:
                        return
                    for item in batch.items:
                        if item.timestamp < submitted_at or not batch.task_id:
                            continue
                        for span in _studio_span_events(item.data, request_id):
                            event_store.append(request_id, span)
                        phase = _modal_lifecycle_phase(
                            item.data,
                            api_pb2.TaskState.Name(item.task_state) if item.task_state else "",
                        )
                        if not phase:
                            continue
                        task_ids.add(batch.task_id)
                        if len(task_ids) > 1 or event_store.active_count > 1:
                            phase = "lifecycle_unknown"
                        if phase == last_phase:
                            continue
                        last_phase = phase
                        event_store.append(request_id, {
                            "type": "status", "request_id": request_id,
                            "phase": phase, "source": "modal_lifecycle_log",
                            "scope": "function", "task_id": batch.task_id,
                            "observed_wall_ns": int(item.timestamp * 1_000_000_000),
                        })
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log.warning("Modal lifecycle observation unavailable for %s: %s", request_id, type(exc).__name__)
        event_store.append(request_id, {
            "type": "status", "request_id": request_id, "phase": "lifecycle_unknown",
            "source": "modal_lifecycle_log", "error_type": type(exc).__name__,
        })


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


def _sniff_image_extension(raw: bytes | None) -> str | None:
    """Image container extension from magic bytes, or None when unknown.

    The remote payload does not declare an encoding, and assuming one writes
    lying filenames (WebP bytes saved as ``.png`` break MIME serving and every
    downstream format label). Magic sniffing is exact for the containers Golden
    emits; anything unrecognized stays None so callers keep a safe default.
    """
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 12:
        return None
    head = bytes(raw[:12])
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:2] == b"\xff\xd8":
        return "jpg"
    if head[:2] == b"BM":
        return "bmp"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _materialized_image_name(out_dir: Path, now: Any = None, ext: str = "png") -> str:
    """Date-based materialized filename, e.g. ``golden_2026-10-12_153022.png``.

    Same-second collisions (parallel runs, retries) take a ``_1``/``_2``
    suffix so a write never clobbers an unrelated file. Only the name is
    date-derived — run/output identity still travels in ``output_paths`` and
    History, so nothing parses this name back.
    """
    from datetime import datetime

    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    suffix = str(ext or "png").lower().lstrip(".") or "png"
    name = "golden_%s.%s" % (stamp, suffix)
    counter = 0
    while (out_dir / name).exists():
        counter += 1
        name = "golden_%s_%d.%s" % (stamp, counter, suffix)
    return name


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
        out_dir = get_studio_outputs_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        name = _materialized_image_name(out_dir, ext=_sniff_image_extension(raw) or "png")
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
    method: str = "",
    studio_method: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    controls_map = controls if isinstance(controls, Mapping) else {}
    actual_method = method or profile.target["method"]
    meta = {
        "source": "studio_golden",
        "golden_profile": profile.name,
        "golden_request_id": request_id,
        # The ACTUAL executor method (generic runs use run_plan_stream,
        # not the profile's canonical Golden method).
        "golden_method": actual_method,
        "golden_executor": (
            "generic" if actual_method == "run_plan_stream" else "canonical"
        ),
        "golden_app": profile.target["app"],
        "prompt": str(controls_map.get("prompt") or ""),
        "negative_prompt": str(controls_map.get("negative_prompt") or ""),
        "studio_workflow_id": str(controls_map.get("_workflow_id") or ""),
    }
    # Phase 3: explicit generic-method provenance (plain JSON only).
    if isinstance(studio_method, Mapping):
        try:
            meta["studio_method"] = json.loads(json.dumps(dict(studio_method)))
        except Exception:
            pass
    return meta


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
    method: str = "",
    studio_method: Mapping[str, Any] | None = None,
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
            meta=_golden_history_meta(request_id, profile, controls, method, studio_method),
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


def _prepare_variant_prompt(
    bundle: Mapping[str, Any],
    values: Mapping[str, Any],
    effective_options: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[Any]]:
    """Apply one variant's merged controls to the resolved executable prompt.

    Shared by the single-run and batch paths so both submit byte-identical
    graphs for identical controls.  ``prepare_effective_prompt`` deep-copies
    the executable prompt, so calling this per variant on one bundle is safe.
    Returns (applied_workflow_dict, studio_meta, dropdown_repairs).
    Raises GoldenRunError when the controls cannot be applied.
    """
    from studio_workflow_run import (
        prepare_effective_prompt,
        _hydrate_missing_required_widget_defaults,
        _normalize_model_loader_names,
        _repair_empty_dropdown_links,
    )
    from workflow_metadata import prompt_sha256

    prepared = prepare_effective_prompt(
        bundle["executable_prompt"],
        bundle["control_schema"],
        dict(values),
        bundle.get("mapping"),
        modal_options=dict(effective_options),
        ui_graph=(bundle.get("version") or {}).get("graph_json"),
    )
    if "error" in prepared:
        raise GoldenRunError(str(prepared["error"]))
    applied = prepared
    _normalize_model_loader_names(applied["workflow"])
    # Same empty-dropdown repair as the generic plan seam: the fast path
    # submits applied["workflow"] directly, so an unconfigured PixaromaDropdown
    # would otherwise feed "" into ImageScaleToTotalPixels.megapixels and crash
    # remote execution AFTER model loading (TypeError: str / int).
    dropdown_repairs = _repair_empty_dropdown_links(applied["workflow"])
    if dropdown_repairs:
        _log.warning(
            "Studio repaired %d empty-dropdown link(s): %s",
            len(dropdown_repairs), dropdown_repairs,
        )
    # Same widget-default hydration as the generic plan seam: the fast path
    # submits applied["workflow"] directly, so an untouched optional widget
    # stored as null (e.g. TextGenerate mtp) would otherwise fail remote
    # validation with value_not_in_list. Host-only no-op when the node
    # registry is unavailable.
    _hydrate_missing_required_widget_defaults(applied["workflow"])
    studio_meta = copy.deepcopy(applied.get("studio_meta") or {})
    # The dedicated Golden adapter has no ExecutionPlan to compute this for
    # it; hash the exact graph that will be submitted, after bypass.
    studio_meta["workflow_hash"] = prompt_sha256(applied["workflow"])
    return applied, studio_meta, dropdown_repairs


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
    modal_options: Mapping[str, Any] | None = None,
    event_store: GoldenStageEventStore = EVENT_STORE,
    handle_factory: Callable[[GoldenProfile, Mapping[str, Any] | None], Any] | None = None,
    studio_method: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve controls, submit the selected Golden method, and retain events."""
    request_id = validate_request_id(request_id)
    profile = resolve_golden_profile(profile_name)

    # Reuse the established Studio workflow seam read-only.  In particular,
    # this preserves version/preset ownership and verbatim control mapping.
    # (Prompt application lives in _prepare_variant_prompt, shared with batch.)
    from studio_workflow_run import (
        build_workflow_execution_plan,
        merge_workflow_controls,
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
    # ── Phase 3: sanitize the explicit method BEFORE base validation (same
    #    contract as handle_workflow_run_async): an inpaint method carries
    #    its mask in params, so origin required-mask errors are tolerated;
    #    the method pre-step / override merge re-validates authoritatively.
    from studio_workflow_run import (
        _prepare_studio_method,
        _resolve_dedicated_override,
        _sanitize_studio_method,
        _tolerated_method_base_errors,
        _transfer_values_with_method_mask,
    )
    _g_method, _g_method_error = _sanitize_studio_method(studio_method)
    if _g_method_error:
        return {"status": "error", "message": _g_method_error}
    _g_base_errors = _tolerated_method_base_errors(merged["errors"], _g_method)
    if _g_base_errors:
        return {
            "status": "error",
            "error_code": "WORKFLOW_CONTROL_VALIDATION",
            "message": "; ".join(
                f"{error['field']}: {error['message']}" for error in _g_base_errors
            ),
            "errors": _g_base_errors,
        }
    if modal_options is not None and not isinstance(modal_options, Mapping):
        return {
            "status": "error",
            "error_code": "WORKFLOW_CONTROL_APPLICATION",
            "message": "modal_options must be an object",
        }
    # ── Phase 3: explicit generic methods share the studio_workflow_run
    #    helpers (sanitize/pre/dedicated-resolution). Plain runs (studio_method
    #    None) take the exact historical path below.
    #    (_g_method/_g_method_error were sanitized before base validation.)
    _g_method_ctx = None
    _g_prompt_mutator = None
    _effective_values = merged["values"]
    if _g_method is not None and _g_method["method"] != "dedicated":
        _prep = _prepare_studio_method(bundle, merged["values"], _g_method)
        if "error" in _prep:
            return {"status": "error", "message": _prep["error"]}
        _effective_values = _prep["merged_values"]
        _g_method_ctx = _prep["ctx"]
        # NOTE: _prep["ctx"] already carries kind + method NAME strings;
        # overwriting method with the full dict would break post dispatch.
        if _g_method["method"] == "conditioning":
            def _g_prompt_mutator(workflow, _ctx=_g_method_ctx):
                from studio_inpaint_expand import inject_inpaint_conditioning
                new_workflow, diag = inject_inpaint_conditioning(
                    workflow,
                    source_file=_ctx["crop_source"],
                    mask_file=_ctx["crop_mask"],
                )
                _ctx["injection"] = diag
                return new_workflow
    elif isinstance(_g_method, dict):
        _resolved = _resolve_dedicated_override(
            node_dir, workflow_id,
            _transfer_values_with_method_mask(merged["values"], _g_method),
            _g_method.get("override", ""),
        )
        if "error" in _resolved:
            return {"status": "error", "message": _resolved["error"]}
        bundle = _resolved["bundle"]
        _effective_values = _resolved["merged"].get("values") or {}
        _g_method_ctx = {
            "kind": _g_method["kind"], "method": "dedicated",
            "override": _g_method.get("override", ""),
            "origin_workflow": str(workflow_id or ""),
        }
    effective_options = dict(modal_options or {})
    try:
        applied, studio_meta, dropdown_repairs = _prepare_variant_prompt(
            bundle, _effective_values, effective_options
        )
    except GoldenRunError as exc:
        return {
            "status": "error",
            "error_code": "WORKFLOW_CONTROL_APPLICATION",
            "message": str(exc),
        }
    use_generic_executor = not _canonical_golden_fast_path(applied["workflow"])
    # Phase 3: conditioning insertion on the fast path mutates the prepared
    # per-request copy (never the stored version); unknown node classes fail
    # here loudly via ValueError, never silently.
    if _g_prompt_mutator is not None and not use_generic_executor:
        try:
            applied["workflow"] = _g_prompt_mutator(applied["workflow"])
        except ValueError as exc:
            raise GoldenRunError(str(exc)[:300])

    event_store.start(request_id)
    event_store.append(request_id, {
        "type": "status", "phase": "awaiting_remote", "request_id": request_id,
    })
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
            "studio_controls": copy.deepcopy(_effective_values),
            "repaired_empty_dropdowns": dropdown_repairs,
            "studio_meta": studio_meta,
        },
        "modal_options": copy.deepcopy(effective_options),
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
    lifecycle_task = None
    try:
        # Make the run visible on the History page. Golden bypasses the ordinary
        # save-history seam, so without this the image existed only in the
        # Playground's local store.  The record is opened BEFORE dispatch so the
        # attempt's started_at is the real run start (otherwise every Golden run
        # reported a ~1s total time), then completed below with the output and
        # timings.  Both halves are best-effort and never fail a run.
        history_run_id, history_generation_id = _begin_golden_history(
            request_id,
            profile,
            _effective_values,
            method=(
                "run_plan_stream"
                if use_generic_executor
                else profile.target["method"]
            ),
            studio_method=(
                {"kind": _g_method_ctx.get("kind"), "method": _g_method_ctx.get("method"),
                 "box": _g_method_ctx.get("box"), "origin": _g_method_ctx.get("origin"),
                 "pads": _g_method_ctx.get("pads"),
                 "orig_size": _g_method_ctx.get("orig_size"),
                 "wh_overridden": _g_method_ctx.get("wh_overridden", False),
                 "injection": _g_method_ctx.get("injection"),
                 "override": _g_method_ctx.get("override", "")}
                if isinstance(_g_method_ctx, dict) else None
            ),
        )
        handle = (
            handle_factory(profile, workspace)
            if handle_factory is not None
            else _default_handle_factory(profile, workspace)
        )
        if use_generic_executor:
            plan, plan_error = build_workflow_execution_plan(
                bundle,
                _effective_values,
                modal_options=effective_options,
                comfyui_root=str(node_dir),
                prompt_mutator=_g_prompt_mutator,
            )
            if plan_error is not None or plan is None:
                raise GoldenRunError(str(plan_error or "generic_execution_plan_failed"))
            remote_method = getattr(handle, "run_plan_stream")
            remote_gen = getattr(remote_method, "remote_gen", None)
            if remote_gen is None or not callable(getattr(remote_gen, "aio", None)):
                raise GoldenRunError("generic Studio executor is not a stream")
            plan_payload = plan.to_dict()
            plan_payload.setdefault("request_metadata", {})["studio_progress"] = True
            stream = remote_gen.aio(plan_payload, request_id=request_id)
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
        if handle_factory is None and workspace:
            lifecycle_task = asyncio.create_task(_observe_modal_lifecycle(
                profile, workspace, remote_method, request_id, event_store, time.time(),
            ))
        terminal: dict[str, Any] | None = None
        stage_events: list[dict[str, Any]] = []
        async for remote_event in stream:
            if (
                lifecycle_task is not None
                and isinstance(remote_event, Mapping)
                and remote_event.get("type") in {"result", "error", "cancelled"}
            ):
                lifecycle_task.cancel()
                await asyncio.gather(lifecycle_task, return_exceptions=True)
                lifecycle_task = None
            if (
                use_generic_executor
                and isinstance(remote_event, Mapping)
                and str(remote_event.get("type", "")).strip().lower() == "status"
                and str(remote_event.get("phase", "")).strip().lower() == "plan_received"
            ):
                # The cursor already carries the generic_execution marker for
                # this branch; the generic executor's own plan_received status
                # would overwrite it as the latest phase and refreeze the UI
                # on "Starting up". Keep it in the local timing evidence but
                # out of the polled cursor.
                stage_events.append(dict(remote_event))
                event_store.append(request_id, {
                    "type": "status", "phase": "generic_execution", "request_id": request_id,
                })
                continue
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
        # Generation success is not delivery success: a materialization
        # failure with no output paths must fail the run truthfully instead
        # of recording a completed run with no image.
        if (
            isinstance(materialized, dict)
            and materialized.get("output_materialization_error")
            and not materialized.get("output_paths")
        ):
            _fail_golden_history(
                history_run_id,
                "output materialization failed: %s (remote execution succeeded)"
                % (materialized.get("output_materialization_error") or "unknown"),
            )
            return {
                "status": "error",
                "message": "output materialization failed: %s (remote execution succeeded)"
                % (materialized.get("output_materialization_error") or "unknown"),
                "request_id": request_id,
                "runId": request_id,
                "profile": profile.name,
            }
        # ── Phase 3: generic-method post step (stitch/preserve/output swap).
        #    Runs on the materialized result before History completion, so the
        #    record carries the FINAL image, never the working crop.
        if isinstance(_g_method_ctx, dict) and str(_g_method_ctx.get("method") or "") != "dedicated":
            try:
                from studio_workflow_run import (
                    _compose_method_final,
                    _method_final_path,
                )
                from local_artifacts import get_studio_outputs_dir
                _post_paths = materialized.get("output_paths")
                _post_path = ""
                if isinstance(_post_paths, (list, tuple)):
                    for _cand in _post_paths:
                        if isinstance(_cand, str) and _cand:
                            _post_path = str(get_studio_outputs_dir() / _cand)
                            if Path(_post_path).is_file():
                                break
                            _post_path = ""
                if not _post_path:
                    raise ValueError("method run produced no readable image")
                from PIL import Image as _PILImage
                _post_img = _PILImage.open(_post_path).convert("RGB")
                _post_final, _post_diag = _compose_method_final(_g_method_ctx, _post_img)
                _post_name = Path(_method_final_path()).name
                _post_final.save(str(get_studio_outputs_dir() / _post_name))
                materialized["output_paths"] = [_post_name]
                _g_method_ctx["post"] = {
                    "final": _post_name,
                    "resized_result": bool(_post_diag.get("resized_result", False)),
                }
            except ValueError as exc:
                _fail_golden_history(history_run_id, f"studio method post failed: {exc}"[:500])
                return {
                    "status": "error",
                    "message": f"studio method post failed: {exc}"[:500],
                    "request_id": request_id,
                    "runId": request_id,
                    "profile": profile.name,
                }
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
    finally:
        if lifecycle_task is not None:
            lifecycle_task.cancel()
            await asyncio.gather(lifecycle_task, return_exceptions=True)


# Explicit name for callers that want to distinguish this from the legacy run.
execute_studio_golden_run = run_golden_workflow


def _complete_batch_variant(
    profile: GoldenProfile,
    histories: Mapping[str, tuple[str, str]],
    vid: str,
    event: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Materialize one variant terminal event into a single-shaped entry.

    History for the variant is opened before dispatch and completed/failed
    here, so each streamed entry is already durable when yielded.
    """
    run_id, generation_id = histories.get(vid, ("", ""))
    if event is None or event.get("type") != "variant_result":
        message = (
            str(event.get("message") or "variant missing from batch result")
            if event is not None
            else "variant missing from batch result"
        )
        _fail_golden_history(run_id, message)
        return {
            "status": "error",
            "message": message,
            "request_id": vid,
            "runId": vid,
            "profile": profile.name,
        }
    materialized = _materialize_image(event.get("data", event), vid)
    if (
        isinstance(materialized, dict)
        and materialized.get("output_materialization_error")
        and not materialized.get("output_paths")
    ):
        _fail_golden_history(
            run_id,
            "output materialization failed: %s (remote execution succeeded)"
            % (materialized.get("output_materialization_error") or "unknown"),
        )
        return {
            "status": "error",
            "message": "output materialization failed: %s (remote execution succeeded)"
            % (materialized.get("output_materialization_error") or "unknown"),
            "request_id": vid,
            "runId": vid,
            "profile": profile.name,
        }
    _complete_golden_history(
        run_id,
        materialized,
        timings=_golden_stage_timings([]),
    )
    response = {
        "status": "ok",
        "request_id": vid,
        "runId": vid,
        "profile": profile.name,
        "result": materialized,
        "historyGenerationId": generation_id or "",
    }
    for key, value in materialized.items():
        if key in {"outputs", "images"}:
            continue
        response.setdefault(key, value)
    return response


async def run_golden_workflow_batch_stream(
    *,
    workflow_id: str,
    version_id: str,
    variants: list[Mapping[str, Any]],
    request_id: str,
    node_dir: str | Path,
    profile_name: str,
    preset_id: str = "",
    workspace: Mapping[str, Any] | None = None,
    modal_options: Mapping[str, Any] | None = None,
    event_store: GoldenStageEventStore = EVENT_STORE,
    handle_factory: Callable[[GoldenProfile, Mapping[str, Any] | None], Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream a batch's per-variant completions as they land, in order.

    The workflow/version is resolved once; each variant's controls are merged
    and applied with the same seam as single runs (byte-identical graphs for
    identical controls).  One Modal generator call loops the variants against
    the warm container, so a queue of N pays one container start instead of N.
    Execution is sequential: one ComfyUI server runs one prompt at a time.

    Yields, in order: one {"status": "error", ...} entry per prep-failed
    variant, then {"type": "batch_start", ...}, then one single-shaped
    ok/error entry per variant AS IT COMPLETES (history already
    opened/completed server-side per entry), then a final
    {"type": "batch_result", ...} summary.  A batch-level failure yields one
    {"status": "error", ...} entry instead of variant entries.
    """
    batch_id = validate_request_id(request_id)
    profile = resolve_golden_profile(profile_name)
    if not isinstance(variants, list) or not variants:
        yield {
            "status": "error",
            "error_code": "BATCH_VARIANTS_REQUIRED",
            "message": "variants must be a non-empty list",
            "request_id": batch_id,
        }
        return
    for index, variant in enumerate(variants):
        if not isinstance(variant, Mapping):
            yield {
                "status": "error",
                "error_code": "BATCH_VARIANT_MUST_BE_OBJECT",
                "message": f"variant {index} must be an object",
                "request_id": batch_id,
            }
            return
        try:
            validate_request_id((variant or {}).get("request_id"))
        except GoldenRunError:
            yield {
                "status": "error",
                "error_code": "BATCH_VARIANT_REQUEST_ID_REQUIRED",
                "message": f"variant {index} needs a valid request_id",
                "request_id": batch_id,
            }
            return
        if not isinstance((variant or {}).get("controls"), Mapping):
            yield {
                "status": "error",
                "error_code": "BATCH_VARIANT_CONTROLS_REQUIRED",
                "message": f"variant {(variant or {}).get('request_id')} needs a controls object",
                "request_id": batch_id,
            }
            return
    variant_ids = [str(v.get("request_id")) for v in variants]
    if len(set(variant_ids)) != len(variant_ids):
        yield {
            "status": "error",
            "error_code": "BATCH_VARIANT_REQUEST_ID_DUPLICATE",
            "message": "variant request_ids must be unique within a batch",
            "request_id": batch_id,
        }
        return

    from studio_workflow_run import (
        merge_workflow_controls,
        resolve_workflow_run_bundle,
    )

    bundle = resolve_workflow_run_bundle(
        workflow_id,
        version_id,
        node_dir,
        remote_model_readiness=True,
    )
    if bundle.get("status") != "ok":
        yield bundle
        return
    if modal_options is not None and not isinstance(modal_options, Mapping):
        yield {
            "status": "error",
            "error_code": "WORKFLOW_CONTROL_APPLICATION",
            "message": "modal_options must be an object",
        }
        return
    effective_options = dict(modal_options or {})

    jobs: list[dict[str, Any]] = []
    for variant in variants:
        vid = str(variant.get("request_id"))
        merged = merge_workflow_controls(
            bundle["defaults"], dict(variant.get("controls") or {}), bundle["control_schema"],
        )
        if merged["errors"]:
            jobs.append({
                "request_id": vid,
                "error": "; ".join(
                    f"{error['field']}: {error['message']}" for error in merged["errors"]
                ),
            })
            continue
        try:
            applied, studio_meta, dropdown_repairs = _prepare_variant_prompt(
                bundle, merged["values"], effective_options
            )
        except GoldenRunError as exc:
            jobs.append({"request_id": vid, "error": str(exc)})
            continue
        if not _canonical_golden_fast_path(applied["workflow"]):
            # The generic plan executor has no batch adapter; run such
            # workflows through sequential single runs instead.
            jobs.append({
                "request_id": vid,
                "error": "BATCH_FAST_PATH_REQUIRED",
                "message": "workflow is not a canonical Golden fast-path workflow",
            })
            continue
        jobs.append({
            "request_id": vid,
            "values": merged["values"],
            "applied": applied,
            "studio_meta": studio_meta,
            "dropdown_repairs": dropdown_repairs,
        })

    try:
        from tools.v2_control.fingerprints import FingerprintEngine

        _effective_flags = FingerprintEngine(profile.config).effective_flag_values()
    except Exception:
        _effective_flags = {}
    _source_threads = str(
        _effective_flags.get("COMFYMODAL_GOLDEN_C0_SOURCE_THREADS", "") or ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    _golden_mode = (
        "parallel"
        if profile.target["method"] == "run_golden_parallel_stream"
        else "serial"
    )

    for job in jobs:
        if "error" in job:
            yield {
                "status": "error",
                "message": job.get("message") or job["error"],
                "error_code": "BATCH_VARIANT_FAILED"
                if job["error"] != "BATCH_FAST_PATH_REQUIRED"
                else "BATCH_FAST_PATH_REQUIRED",
                "request_id": job["request_id"],
                "runId": job["request_id"],
                "profile": profile.name,
            }
    runnable = [job for job in jobs if "error" not in job]
    if not runnable:
        yield {"type": "batch_result", "request_id": batch_id, "results": []}
        return
    # History opens lazily per variant_start (not upfront): skipped or
    # never-reached variants leave no half-open "running" records behind.
    histories: dict[str, tuple[str, str]] = {}
    by_job = {job["request_id"]: job for job in runnable}
    summaries: list[dict[str, Any]] = []
    yield {"type": "batch_start", "request_id": batch_id, "variant_count": len(runnable)}

    results: list[dict[str, Any]] = []
    if runnable:
        modal_variants = [
            {
                "request_id": job["request_id"],
                "prompt": job["applied"]["workflow"],
                "extra_data": {
                    "client_id": job["request_id"],
                    "workflow_id": str(workflow_id or ""),
                    "workflow_version_id": str(version_id or ""),
                    "studio_controls": copy.deepcopy(job["values"]),
                    "repaired_empty_dropdowns": job["dropdown_repairs"],
                    "studio_meta": job["studio_meta"],
                    "batch_id": batch_id,
                },
                "modal_options": copy.deepcopy(effective_options),
                "stream_golden_stage_events": True,
                "c0_source_threads": _source_threads,
                "golden_mode": _golden_mode,
                "request_origin_info": {
                    "studio": True,
                    "profile": profile.name,
                    "method": profile.target["method"],
                    "request_id": job["request_id"],
                    "batch_id": batch_id,
                },
            }
            for job in runnable
        ]
        try:
            handle = (
                handle_factory(profile, workspace)
                if handle_factory is not None
                else _default_handle_factory(profile, workspace)
            )
            remote_method = getattr(handle, STUDIO_BATCH_METHOD)
            remote_gen = getattr(remote_method, "remote_gen", None)
            if remote_gen is None or not callable(getattr(remote_gen, "aio", None)):
                raise GoldenRunError("Studio batch adapter is not a stream")
            event_store.start(batch_id)
            stream = remote_gen.aio({"request_id": batch_id, "variants": modal_variants})
            if hasattr(stream, "__await__"):
                stream = await stream
            seen_variants: set[str] = set()
            batch_terminal: dict[str, Any] | None = None
            async for remote_event in stream:
                stored = event_store.append(batch_id, remote_event)
                event_type = str(stored.get("type", "")).lower()
                if event_type == "variant_start":
                    vid = str(stored.get("variant_request_id") or "")
                    job = by_job.get(vid)
                    if job is not None and vid not in histories:
                        histories[vid] = _begin_golden_history(
                            vid, profile, job["values"], method=profile.target["method"]
                        )
                    yield stored
                elif event_type == "variant_skipped":
                    vid = str(stored.get("variant_request_id") or "")
                    if vid:
                        seen_variants.add(vid)
                    yield stored
                elif event_type in {"variant_result", "variant_error"}:
                    vid = str(stored.get("variant_request_id") or "")
                    if vid and vid not in seen_variants:
                        seen_variants.add(vid)
                        entry = _complete_batch_variant(profile, histories, vid, stored)
                        summaries.append({"request_id": vid, "status": entry["status"]})
                        yield entry
                elif event_type in {"batch_result", "error"}:
                    batch_terminal = stored
                elif event_type == "batch_cancelled":
                    batch_terminal = stored
                    yield stored
            event_store.finish(batch_id)
            if batch_terminal is None:
                raise GoldenRunError("Golden batch stream ended without a terminal event")
            if batch_terminal.get("type") == "error":
                raise GoldenRunError(
                    str(batch_terminal.get("message") or "Golden batch execution failed")
                )
        except asyncio.CancelledError:
            for vid, (run_id, _gen_id) in histories.items():
                _fail_golden_history(run_id, "Golden batch execution cancelled")
            if batch_id in event_store._runs:
                event_store.append(batch_id, {
                    "type": "error",
                    "request_id": batch_id,
                    "message": "Golden batch execution cancelled",
                })
                event_store.finish(batch_id)
            raise
        except Exception as exc:
            try:
                _clear_modal_client_cache()
            except Exception:
                pass
            for vid, (run_id, _gen_id) in histories.items():
                _fail_golden_history(run_id, f"{type(exc).__name__}: {exc}"[:500])
            if batch_id in event_store._runs:
                event_store.append(batch_id, {
                    "type": "error",
                    "request_id": batch_id,
                    "message": str(exc)[:500],
                })
                event_store.finish(batch_id)
            yield {
                "status": "error",
                "message": str(exc)[:500],
                "request_id": batch_id,
                "runId": batch_id,
                "profile": profile.name,
            }
            return
        for job in runnable:
            vid = job["request_id"]
            if vid in seen_variants:
                continue
            if batch_terminal is not None and batch_terminal.get("type") == "batch_cancelled":
                # Cancelled before starting: requeueable skip, not a failure.
                summaries.append({"request_id": vid, "status": "skipped"})
                yield {
                    "type": "variant_skipped",
                    "request_id": batch_id,
                    "variant_request_id": vid,
                }
                continue
            run_id, _gen_id = histories.get(vid, ("", ""))
            _fail_golden_history(run_id, "variant missing from batch result")
            summaries.append({"request_id": vid, "status": "error"})
            yield {
                "status": "error",
                "message": "variant missing from batch result",
                "request_id": vid,
                "runId": vid,
                "profile": profile.name,
            }
        # Preserve request order in the summary regardless of prep skipping.
        order = {vid: index for index, vid in enumerate(variant_ids)}
        summaries.sort(key=lambda item: order.get(str(item.get("request_id")), len(order)))
        if batch_terminal is not None and batch_terminal.get("type") == "batch_cancelled":
            # batch_cancelled already closed the stream: no second terminal.
            return
        yield {"type": "batch_result", "request_id": batch_id, "results": summaries}


async def run_golden_workflow_batch(
    *,
    workflow_id: str,
    version_id: str,
    variants: list[Mapping[str, Any]],
    request_id: str,
    node_dir: str | Path,
    profile_name: str,
    preset_id: str = "",
    workspace: Mapping[str, Any] | None = None,
    modal_options: Mapping[str, Any] | None = None,
    event_store: GoldenStageEventStore = EVENT_STORE,
    handle_factory: Callable[[GoldenProfile, Mapping[str, Any] | None], Any] | None = None,
) -> dict[str, Any]:
    """Buffered collection of run_golden_workflow_batch_stream.

    Returns {"status": "ok", "results": [...]} with one entry per requested
    variant in order, or a {"status": "error", ...} entry when the batch
    itself fails.  Kept for non-streaming callers and unit tests; the HTTP
    route streams the generator directly.
    """
    batch_id = validate_request_id(request_id)
    profile = resolve_golden_profile(profile_name)
    collected: list[dict[str, Any]] = []
    fallback_error: dict[str, Any] | None = None
    async for event in run_golden_workflow_batch_stream(
        workflow_id=workflow_id,
        version_id=version_id,
        variants=variants,
        request_id=request_id,
        node_dir=node_dir,
        profile_name=profile_name,
        preset_id=preset_id,
        workspace=workspace,
        modal_options=modal_options,
        event_store=event_store,
        handle_factory=handle_factory,
    ):
        if (
            isinstance(event, Mapping)
            and "runId" in event
            and str(event.get("request_id")) != batch_id
        ):
            collected.append(dict(event))
        elif isinstance(event, Mapping) and event.get("status") == "error":
            fallback_error = dict(event)
    if not collected and fallback_error is not None:
        return fallback_error
    if not collected:
        return {
            "status": "error",
            "message": "Golden batch produced no variant results",
            "request_id": batch_id,
            "runId": batch_id,
            "profile": profile.name,
        }
    variant_ids = [str(v.get("request_id")) for v in variants if isinstance(v, Mapping)]
    order = {vid: index for index, vid in enumerate(variant_ids)}
    collected.sort(key=lambda entry: order.get(str(entry.get("request_id")), len(order)))
    return {
        "status": "ok",
        "request_id": batch_id,
        "runId": batch_id,
        "profile": profile.name,
        "results": collected,
    }
