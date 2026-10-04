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
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from tools.v2_control.profile_catalog import GoldenProfile, resolve_golden_profile

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
    client = modal.Client.from_credentials(token_id, token_secret)
    cls = modal.Cls.from_name(
        profile.target["app"],
        profile.target["class"],
        client=client,
        environment_name=str(workspace.get("environment") or "") or None,
    )
    return cls()


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


async def run_golden_workflow(
    *,
    workflow_id: str,
    version_id: str,
    preset_id: str,
    controls: Mapping[str, Any] | None,
    request_id: str,
    node_dir: str | Path,
    profile_name: str,
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
        merge_workflow_controls,
        resolve_workflow_run_bundle,
    )

    bundle = resolve_workflow_run_bundle(
            workflow_id, version_id, preset_id, node_dir,
            allow_remote_execution=True,
        )
    if bundle.get("status") != "ok":
        return bundle
    merged = merge_workflow_controls(
        bundle["preset"], dict(controls or {}), bundle["control_schema"],
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
            "preset_id": str(bundle.get("preset", {}).get("preset_id", "") or ""),
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

    try:
        handle = (
            handle_factory(profile, workspace)
            if handle_factory is not None
            else _default_handle_factory(profile, workspace)
        )
        # Studio MUST go through the dedicated Studio adapter.  Calling the
        # profile's own Golden method would put the stage-progress bridge
        # (observer, queue, extra task) inside the ordinary v2ctl path, which
        # is exactly what that path must never contain.  The profile's target
        # still decides the real Golden class/mode and is reported verbatim.
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
        async for remote_event in stream:
            stored = event_store.append(request_id, remote_event)
            if str(stored.get("type", "")).lower() in {"result", "error"}:
                terminal = stored
        event_store.finish(request_id)
        if terminal is None:
            return {
                "status": "error",
                "message": "Golden stream ended without a terminal event",
                "request_id": request_id,
                "runId": request_id,
            }
        if terminal.get("type") == "error":
            return {
                "status": "error",
                "message": str(terminal.get("message") or "Golden execution failed"),
                "request_id": request_id,
                "runId": request_id,
                "profile": profile.name,
            }
        materialized = _materialize_image(terminal.get("data", terminal), request_id)
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
        raise
    except Exception as exc:
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
