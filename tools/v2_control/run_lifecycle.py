"""Early run manifests + run-scoped cancellation plumbing (durable evidence).

Local-only, stdlib-only.  This module owns two narrow pieces of the
durable-evidence story:

* **Early local manifest.**  Written to ``.v2ctl/runs/`` as soon as a run
  starts (``status="running"``), carrying the invocation id, the deployment
  identity, the profile, the workflow identity, the start time, and the
  bound supervisor.  The request id is filled in as soon as it is known and
  the status is updated on completion / timeout / cancellation, so a timed
  out run always leaves a discoverable manifest containing the request id.
  Writes are atomic (temp file + ``os.replace`` in the same directory),
  mirroring the runtime-state volume's atomic-write ownership.  The full
  post-run manifest written by ``write_run_manifest`` is unchanged; the
  early manifest points at it once it exists.

* **Run-scoped cancellation.**  :func:`request_run_cancel` cancels the
  specific request/attempt addressed by ``request_id`` — never the app.
  Resolution order: (1) a live in-process transport's
  ``transport.cancel_attempt(request_id, reason)`` (the verified
  narrowest path, owned by ``ModalTransport``/the modern scheduler
  binding); (2) a cooperative cancel message on the run's named Modal
  control Queue at ``partition=request_id`` (same primitive shape the
  transport delivers, same deterministic queue name); (3) a truthful
  ``unavailable`` verdict.  There is deliberately NO ``modal app stop``
  or ``modal app delete`` path anywhere in this module (grep-provable);
  the app-wide stop exists only as a last-resort fallback in the external
  bounded supervisor, which must never need it.

The Modal SDK is imported lazily inside :func:`modal_control_queue_put`
so manifest discovery, dry-run planning, and unit tests never need it.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


RUN_LIFECYCLE_SCHEMA_VERSION = 1

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_TIMEOUT = "timeout"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"

TERMINAL_STATUSES = frozenset(
    {STATUS_COMPLETED, STATUS_TIMEOUT, STATUS_CANCELLED, STATUS_FAILED}
)
# A locally-timed-out run may still be executing remotely, so cancellation
# remains meaningful; only these statuses mean "nothing left to cancel".
NOTHING_TO_CANCEL = frozenset({STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED})

SUPERVISOR_ENV_VAR = "COMFYMODAL_V2CTL_SUPERVISOR"

# Deterministic cooperative-cancel control Queue name.  Mirrors the rule in
# comfymodal_runtime/modal_transport.py (env override, same default) so a
# cross-process canceller addresses the exact Queue the run's transport
# polls.  Duplicated (not imported) because this package is stdlib-only by
# contract and never imports project runtime modules.
CONTROL_QUEUE_ENV_VAR = "COMFYMODAL_V2_CONTROL_QUEUE"
DEFAULT_CONTROL_QUEUE = "comfymodal-v2-control"

# Same request-id pattern the backend artifact discovery uses on captured
# stdout, so partial-timeout output and supervisor log tails resolve the
# identical id spelling.
_REQUEST_ID_RE = re.compile(
    r"['\"]?(?:request_id|REQUEST_ID)['\"]?\s*[=:]\s*['\"]?([^\s,'\"}]+)",
    flags=re.MULTILINE,
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def control_queue_name(env: Mapping[str, str] | None = None) -> str:
    """Return the deterministic cooperative-cancel control Queue name."""
    source = env if env is not None else os.environ
    try:
        raw = str(source.get(CONTROL_QUEUE_ENV_VAR, "") or "").strip()
    except Exception:
        raw = ""
    return raw or DEFAULT_CONTROL_QUEUE


def extract_request_id(text: Any) -> str:
    """Return the first request id found in *text*, else ``""``.

    Pure/stdout-shape only: never raises, never touches the network.
    """
    if not text:
        return ""
    try:
        match = _REQUEST_ID_RE.search(str(text))
    except Exception:
        return ""
    if match is None:
        return ""
    return str(match.group(1) or "").strip()


def build_cancel_message(partition: str, reason: str = "") -> dict[str, str]:
    """Build the primitive JSON-safe cancel message for *partition*.

    Mirrors ``build_cancel_message`` in
    comfymodal_runtime/local_handle_client.py: the remote generator consumes
    only messages whose ``partition`` matches its ``control_partition``.
    """
    return {
        "type": "cancel",
        "partition": str(partition or ""),
        "reason": str(reason or ""),
    }


def run_manifest_dir(repo_root: str | os.PathLike) -> Path:
    return Path(repo_root) / ".v2ctl" / "runs"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically write *payload* as JSON (temp file + rename, same dir)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp.{os.getpid()}"
    tmp.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8"
    )
    os.replace(tmp, path)


def write_early_run_manifest(
    repo_root: str | os.PathLike,
    *,
    profile: str,
    invocation_id: str,
    target: Mapping[str, Any] | None = None,
    deploy_fingerprint: str = "",
    workspace_id: str = "",
    environment: str = "",
    workflow_selection: Mapping[str, Any] | None = None,
    supervisor: Mapping[str, Any] | None = None,
    backend_command: str = "",
) -> Path:
    """Write the ``status="running"`` early manifest and return its path.

    Call as soon as the run starts (the remote request id is filled in
    later via :func:`update_run_manifest` as soon as it is known).
    """
    target_map = dict(target or {})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short_inv = str(invocation_id or "unknown")[:12] or "unknown"
    path = run_manifest_dir(repo_root) / f"run_{stamp}_{short_inv}_early.json"
    manifest = {
        "schema_version": RUN_LIFECYCLE_SCHEMA_VERSION,
        "kind": "run_lifecycle",
        "created_at": _utcnow_iso(),
        "updated_at": _utcnow_iso(),
        "status": STATUS_RUNNING,
        "profile": str(profile or ""),
        "invocation_id": str(invocation_id or ""),
        "request_id": "",
        "deployment": {
            "app": str(target_map.get("app", "") or ""),
            "class": str(target_map.get("class", "") or ""),
            "method": str(target_map.get("method", "") or ""),
            "deploy_fingerprint": str(deploy_fingerprint or ""),
            "workspace_id": str(workspace_id or ""),
            "environment": str(environment or ""),
        },
        "workflow_selection": (
            dict(workflow_selection)
            if isinstance(workflow_selection, Mapping)
            else {"active": False}
        ),
        "supervisor": dict(supervisor) if isinstance(supervisor, Mapping) else {},
        "backend_command": str(backend_command or ""),
        "final_manifest": "",
        "error": "",
    }
    _atomic_write_json(path, manifest)
    return path


def read_run_manifest(path: str | os.PathLike) -> dict[str, Any] | None:
    """Return the parsed manifest at *path*, else ``None`` (never raises)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def update_run_manifest(
    path: str | os.PathLike,
    *,
    status: str,
    request_id: str = "",
    error: str = "",
    final_manifest: str = "",
) -> dict[str, Any] | None:
    """Atomically update status/request bookkeeping; return the new doc.

    A terminal status is never downgraded back to ``running``.  A
    non-empty *request_id* is always recorded (a timeout MUST leave the
    request id discoverable).  Returns ``None`` when the file is missing
    or malformed.
    """
    manifest = read_run_manifest(path)
    if manifest is None:
        return None
    current = str(manifest.get("status", "") or "")
    if current in TERMINAL_STATUSES and status == STATUS_RUNNING:
        return manifest
    manifest["status"] = str(status or current)
    if str(request_id or "").strip():
        manifest["request_id"] = str(request_id).strip()
    if error:
        manifest["error"] = str(error)[:1024]
    if final_manifest:
        manifest["final_manifest"] = str(final_manifest)
    manifest["updated_at"] = _utcnow_iso()
    try:
        _atomic_write_json(Path(path), manifest)
    except OSError:
        return None
    return manifest


def iter_run_manifests(repo_root: str | os.PathLike) -> list[tuple[Path, dict]]:
    """Return ``(path, doc)`` for every parseable manifest, newest first."""
    directory = run_manifest_dir(repo_root)
    try:
        entries = sorted(
            directory.iterdir(), key=lambda p: p.name, reverse=True
        )
    except OSError:
        return []
    found: list[tuple[Path, dict]] = []
    for entry in entries:
        if not entry.is_file() or entry.suffix != ".json":
            continue
        if entry.name.startswith("."):
            continue
        doc = read_run_manifest(entry)
        if doc is not None:
            found.append((entry, doc))
    return found


def find_manifest_for_request(
    repo_root: str | os.PathLike, request_id: str
) -> tuple[Path, dict] | None:
    """Return the newest manifest carrying *request_id*, else ``None``."""
    wanted = str(request_id or "").strip()
    if not wanted:
        return None
    for path, doc in iter_run_manifests(repo_root):
        if str(doc.get("request_id", "") or "").strip() == wanted:
            return (path, doc)
    return None


def find_running_manifests(
    repo_root: str | os.PathLike,
    *,
    profile: str | None = None,
    invocation_id: str | None = None,
) -> list[tuple[Path, dict]]:
    """Return running-status manifests, optionally filtered, newest first."""
    found: list[tuple[Path, dict]] = []
    for path, doc in iter_run_manifests(repo_root):
        if str(doc.get("status", "")) != STATUS_RUNNING:
            continue
        if profile is not None and str(doc.get("profile", "")) != profile:
            continue
        if invocation_id is not None and str(
            doc.get("invocation_id", "")
        ) != invocation_id:
            continue
        found.append((path, doc))
    return found


def current_supervisor_record(
    *, script: str = "", env: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Return the supervisor binding record for an early manifest."""
    source = env if env is not None else os.environ
    try:
        declared = str(source.get(SUPERVISOR_ENV_VAR, "") or "").strip()
    except Exception:
        declared = ""
    try:
        pid = os.getppid()
    except Exception:
        pid = 0
    return {
        "script": declared or str(script or ""),
        "pid": int(pid) if isinstance(pid, int) else 0,
    }


# ── Run-scoped cancellation ──────────────────────────────────────────────


def _verdict(
    outcome: str, via: str, detail: str = ""
) -> dict[str, str]:
    return {
        "outcome": outcome,
        "via": via,
        "detail": str(detail or "")[:1024],
    }


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _drive_to_completion(awaitable: Any) -> Any:
    """Run *awaitable* to completion on a fresh event loop (CLI context)."""
    if asyncio.iscoroutine(awaitable):
        return asyncio.run(awaitable)

    async def _wrap() -> Any:
        return await awaitable

    return asyncio.run(_wrap())


def request_run_cancel(
    request_id: str,
    *,
    reason: str = "",
    transport: Any = None,
    queue_put: Any = None,
    manifest_status: str = "",
) -> dict[str, str]:
    """Cancel the specific request/attempt addressed by *request_id*.

    Never touches the app: there is no app-stop/app-delete path here by
    construction.  Resolution order:

    1. ``transport.cancel_attempt(request_id, reason)`` when a live
       transport is supplied (the verified narrowest path);
    2. *queue_put* (a ``(message, partition) -> bool`` callable delivering
       the cooperative cancel primitive to the run's control Queue);
    3. truthful ``unavailable``.

    A put success means *delivered*, never *confirmed*: only the remote's
    explicit ``cancelled`` event confirms.  Synchronous (runs an awaitable
    transport result to completion when no event loop is already running).
    Never raises.
    """
    rid = str(request_id or "").strip()
    if not rid:
        return _verdict("unavailable", "none", "empty request_id")
    if str(manifest_status or "") in NOTHING_TO_CANCEL:
        return _verdict(
            "completed_before_cancel",
            "none",
            f"manifest status {manifest_status} is already terminal",
        )
    if transport is not None:
        cancel_attempt = getattr(transport, "cancel_attempt", None)
        if callable(cancel_attempt):
            try:
                result = cancel_attempt(rid, reason=str(reason or ""))
                if inspect.isawaitable(result):
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    result = (
                        _drive_to_completion(result)
                        if loop is None
                        else _pending_in_running_loop()
                    )
                state = getattr(result, "state", None)
                if state is None and isinstance(result, Mapping):
                    state = result.get("state", "")
                return _verdict(
                    str(state or "pending"),
                    "transport",
                    getattr(result, "detail", "")
                    if not isinstance(result, Mapping)
                    else str(result.get("detail", "")),
                )
            except Exception as exc:
                return _verdict(
                    "unavailable", "none", f"transport cancel failed: {exc}"
                )
    if queue_put is not None:
        try:
            message = build_cancel_message(rid, str(reason or ""))
            delivered = queue_put(message, rid)
            if inspect.isawaitable(delivered):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                delivered = (
                    _drive_to_completion(delivered) if loop is None else False
                )
            if delivered:
                return _verdict(
                    "pending",
                    "control_queue",
                    "cancel message delivered; confirmation requires "
                    "the remote cancelled event",
                )
            return _verdict(
                "unavailable", "none", "control-queue put reported no delivery"
            )
        except Exception as exc:
            return _verdict(
                "unavailable", "none", f"control-queue put failed: {exc}"
            )
    return _verdict(
        "unavailable",
        "none",
        "no live transport binding and no control-queue channel supplied",
    )


def _pending_in_running_loop() -> dict[str, str]:
    """Fallback verdict when an awaitable cannot be driven (running loop)."""
    return {"state": "pending", "detail": "awaitable returned to caller loop"}


def modal_control_queue_put(
    queue_name: str,
    message: Mapping[str, Any],
    partition: str,
    *,
    timeout_s: float = 30.0,
) -> bool:
    """Put *message* on the named Modal control Queue at *partition*.

    Uses ambient Modal credentials (``MODAL_TOKEN_ID``/``MODAL_TOKEN_SECRET``,
    plus ``MODAL_ENVIRONMENT`` when set).  The Queue is opened with
    ``create_if_missing=False``: cancellation never creates infrastructure.
    Returns ``True`` on put success (delivered, NOT confirmed); raises on
    any failure (missing SDK, missing Queue, put error, timeout) so the
    caller reports a truthful ``unavailable`` verdict.
    """
    try:
        import modal  # noqa: E402  (lazy: stdlib-only module surface)
    except Exception as exc:
        raise RuntimeError(f"modal SDK unavailable: {exc}") from exc
    name = str(queue_name or "").strip() or DEFAULT_CONTROL_QUEUE
    part = str(partition or "").strip()
    if not part:
        raise ValueError("control partition must be non-empty")
    if len(part.encode("utf-8")) > 64:
        raise ValueError("control partition exceeds Modal's 64-byte limit")
    payload = dict(message)
    try:
        queue = modal.Queue.from_name(name, create_if_missing=False)
    except Exception as exc:
        raise RuntimeError(f"control queue {name!r} unavailable: {exc}") from exc

    def _put() -> bool:
        queue.put(payload, partition=part)
        return True

    import concurrent.futures

    budget = float(timeout_s or 30.0)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_put)
        try:
            return bool(future.result(timeout=max(1.0, budget)))
        except Exception as exc:
            raise RuntimeError(f"control-queue put failed: {exc}") from exc


def describe_cancel_plan(
    request_id: str,
    *,
    reason: str = "",
    manifest_status: str = "",
    queue_name: str = "",
) -> dict[str, str]:
    """Pure dry-run plan for a run-scoped cancel (no I/O, no SDK)."""
    return {
        "request_id": str(request_id or ""),
        "reason": str(reason or ""),
        "manifest_status": str(manifest_status or ""),
        "queue": str(queue_name or DEFAULT_CONTROL_QUEUE),
        "partition": str(request_id or ""),
        "message": json.dumps(
            build_cancel_message(str(request_id or ""), str(reason or "")),
            sort_keys=True,
        ),
        "never": "modal app stop / modal app delete (run-scoped only)",
    }


__all__ = [
    "RUN_LIFECYCLE_SCHEMA_VERSION",
    "STATUS_RUNNING",
    "STATUS_COMPLETED",
    "STATUS_TIMEOUT",
    "STATUS_CANCELLED",
    "STATUS_FAILED",
    "TERMINAL_STATUSES",
    "NOTHING_TO_CANCEL",
    "SUPERVISOR_ENV_VAR",
    "CONTROL_QUEUE_ENV_VAR",
    "DEFAULT_CONTROL_QUEUE",
    "control_queue_name",
    "extract_request_id",
    "build_cancel_message",
    "run_manifest_dir",
    "write_early_run_manifest",
    "read_run_manifest",
    "update_run_manifest",
    "iter_run_manifests",
    "find_manifest_for_request",
    "find_running_manifests",
    "current_supervisor_record",
    "request_run_cancel",
    "modal_control_queue_put",
    "describe_cancel_plan",
]
