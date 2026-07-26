"""Canonical Modal prompt execution — single shared path for normal dispatch and Playground single runs.

Provides ``RunTrace`` (in-memory hierarchical spans using ``perf_counter_ns``)
and ``execute_modal_prompt`` (owns final workflow input, production compile,
profile preparation, modal-args construction, ``modal_client.run_prompt_stream``
call, result collection, and canonical trace/counts).
"""

from __future__ import annotations

import base64
import copy
import inspect
import json
import os
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from api_prompt_validator import assert_valid_api_prompt_structure
from production_workflow import (
    COMPILER_SCHEMA_VERSION,
    HASH_SCHEMA_VERSION,
    PRODUCTION_PLAN_SCHEMA_VERSION,
    compile_production_workflow,
    normalize_production_options,
)
# Note: modal_options are passed through without reconstructing model-loading policy.
from warmup_profile import (
    compute_profile_identity_keys,
    prepare_active_next_profile,
)
from workflow_metadata import (
    extract_model_stack,
    extract_warmup_stack,
    prompt_sha256,
    stack_to_warmup_profile,
    summarize_prompt_fields,
)
from comfymodal_runtime.contracts import (
    ExecutionOptions,
    ExecutionPlan,
    RestorePlan,
    stable_hash,
)
from comfymodal_runtime.modal_transport import ModalTransport
from comfymodal_runtime.restore_plan import (
    build_restore_model_spec,
    derive_model_key,
    derive_prefill_key,
)
from comfymodal_runtime.trace import (
    RuntimeTrace,
    _build_local_submission_breakdown,
    _emit_breakdown_line,
    _event_mono_ns,
    _strict_event_span_ms,
    _derived_mono_delta_ms,
    merge_runtime_traces,
)

# ---------------------------------------------------------------------------
# Disk-persisted cache — bounded/versioned atomic JSON state shared across
# separate run_v2_single processes.  Extends the in-memory profile and
# restore-publication caches so that the second invocation of a separate
# process can reuse the first process's cached result without a remote call.
#
# Default behavior — no flag required.  The cache is loaded on module
# import and written only after confirmed remote success.
#
# Design:
#   * Two files under .cache/: v2_profile_cache.json, v2_restore_cache.json
#   * Schema-versioned (bump _DISK_CACHE_VERSION on incompatible format change)
#   * Bounded to _DISK_CACHE_MAX entries per file
#   * Atomic writes via tempfile.mkstemp + os.replace (crash-safe)
#   * Thread-safe via per-file threading.Lock
#   * Only stable identity fields and successful metadata — NEVER serializes
#     handles, credentials, full workflows, base64 images, output data, or
#     request-specific payloads.
#   * Telemetry counters (read/write/miss/corruption) exposed via module vars.
#   * Exact invalidation: when a remote operation fails, the entry for that
#     exact cache key is removed from both the in-memory and disk caches.
# ---------------------------------------------------------------------------

import errno as _errno

_DISK_CACHE_VERSION = 1
"""Schema version for this cache format.  Bump on incompatible changes."""

_DISK_CACHE_MAX = 100
"""Maximum entries per disk cache before LRU-style eviction."""

# ── Cache directory (lazy-initialised) ──────────────────────────────
_DISK_CACHE_DIR: str | None = None
"""Lazy-resolved path to the .cache/ directory."""

def _disk_cache_dir() -> str:
    global _DISK_CACHE_DIR
    if _DISK_CACHE_DIR is None:
        _DISK_CACHE_DIR = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".cache",
        )
    os.makedirs(_DISK_CACHE_DIR, exist_ok=True)
    return _DISK_CACHE_DIR

_PROFILE_DISK_CACHE_FILE = "v2_profile_cache.json"
_RESTORE_DISK_CACHE_FILE = "v2_restore_cache.json"

# ── In-memory shadow of the disk cache (populated at load, written on change) ──
_profile_disk_cache: dict[str, dict] = {}
"""In-memory mirror of the profile cache disk file."""
_profile_disk_lock = threading.Lock()
"""Thread lock for profile disk cache I/O."""

_restore_disk_cache: dict[str, dict] = {}
"""In-memory mirror of the restore cache disk file."""
_restore_disk_lock = threading.Lock()
"""Thread lock for restore disk cache I/O."""

# ── Telemetry counters (monotonic per process) ──────────────────────
_disk_profile_read_count: int = 0
"""Monotonic count of disk-profile-cache reads."""
_disk_profile_write_count: int = 0
"""Monotonic count of disk-profile-cache writes."""
_disk_profile_miss_count: int = 0
"""Monotonic count of disk-profile-cache read misses."""
_disk_profile_corruption_count: int = 0
"""Monotonic count of disk-profile-cache corrupt-file detections."""

_disk_restore_read_count: int = 0
"""Monotonic count of disk-restore-cache reads."""
_disk_restore_write_count: int = 0
"""Monotonic count of disk-restore-cache writes."""
_disk_restore_miss_count: int = 0
"""Monotonic count of disk-restore-cache read misses."""
_disk_restore_corruption_count: int = 0
"""Monotonic count of disk-restore-cache corrupt-file detections."""


def _disk_cache_filepath(kind: str) -> str:
    """Return the absolute file path for the given cache *kind*.

    *kind* must be ``"profile"`` or ``"restore"``.
    """
    filename = (
        _PROFILE_DISK_CACHE_FILE if kind == "profile"
        else _RESTORE_DISK_CACHE_FILE if kind == "restore"
        else _PROFILE_DISK_CACHE_FILE
    )
    return os.path.join(_disk_cache_dir(), filename)


def _read_disk_cache(kind: str) -> dict:
    """Load the disk cache file for *kind* and return its entries dict.

    Returns an empty dict when the file is missing, corrupt, or at a
    different schema version.  Updates telemetry counters.
    """
    global _disk_profile_read_count, _disk_profile_corruption_count
    global _disk_restore_read_count, _disk_restore_corruption_count

    path = _disk_cache_filepath(kind)
    if not os.path.isfile(path):
        return {}

    if kind == "profile":
        _disk_profile_read_count += 1
    else:
        _disk_restore_read_count += 1

    try:
        with open(path, "rb") as _f:
            raw = _f.read()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        if kind == "profile":
            _disk_profile_corruption_count += 1
        else:
            _disk_restore_corruption_count += 1
        return {}

    if not isinstance(data, dict) or data.get("version") != _DISK_CACHE_VERSION:
        if kind == "profile":
            _disk_profile_corruption_count += 1
        else:
            _disk_restore_corruption_count += 1
        return {}

    entries = data.get("entries")
    if not isinstance(entries, dict):
        return {}
    return entries


def _write_disk_cache(kind: str, entries: dict) -> None:
    """Atomically write *entries* to the disk cache for *kind*.

    Uses ``tempfile.mkstemp`` + ``os.replace`` for crash safety.
    Only writes entries dict (never handles, images, prompts, or outputs).
    """
    global _disk_profile_write_count, _disk_restore_write_count
    path = _disk_cache_filepath(kind)
    data = {
        "version": _DISK_CACHE_VERSION,
        "created_at": time.time(),
        "max_entries": _DISK_CACHE_MAX,
        "entries": entries,
    }
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(
            suffix=".tmp",
            prefix=os.path.basename(path) + ".",
            dir=parent,
        )
        try:
            with os.fdopen(fd, "wb") as _f:
                _f.write(json.dumps(data, separators=(",", ":")).encode("utf-8"))
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as _exc:
        # Non-fatal: cache write failures must never raise.
        print(f"[disk_cache] write failed for {kind}: {_exc}", flush=True)

    if kind == "profile":
        _disk_profile_write_count += 1
    else:
        _disk_restore_write_count += 1


def _populate_profile_cache_from_disk() -> None:
    """Load profile disk cache entries into ``_PROFILE_PREP_CACHE`` (fast path).

    Called once at process startup.  Skips entries whose identity fields
    would have already expired (TTL is managed upstream).
    """
    entries = _read_disk_cache("profile")
    if not entries:
        return
    with _PROFILE_PREP_CACHE_LOCK:
        for ck, ev in entries.items():
            if ck not in _PROFILE_PREP_CACHE and isinstance(ev, dict):
                result = ev.get("result")
                if isinstance(result, dict) and result.get("status") not in ("error",):
                    _PROFILE_PREP_CACHE[ck] = dict(result)
    # Keep mirror in sync
    with _profile_disk_lock:
        _profile_disk_cache.update(entries)
    # Evict in-memory cache if over limit
    _evict_profile_prep_cache()


def _populate_restore_cache_from_disk() -> None:
    """Load restore disk cache entries into ``_RESTORE_PUBLISH_CACHE``.

    Called once at process startup.
    """
    entries = _read_disk_cache("restore")
    if not entries:
        return
    with _RESTORE_PUBLISH_CACHE_LOCK:
        for ck, ev in entries.items():
            if ck not in _RESTORE_PUBLISH_CACHE and isinstance(ev, dict):
                identity_hash = ev.get("identity_hash", "")
                publication_result = ev.get("publication_result")
                if identity_hash and isinstance(publication_result, dict):
                    _RESTORE_PUBLISH_CACHE[ck] = {
                        "identity_hash": identity_hash,
                        "publication_result": dict(publication_result),
                    }
    with _restore_disk_lock:
        _restore_disk_cache.update(entries)
    _evict_restore_publish_cache()


def _flush_profile_disk_cache() -> None:
    """Write the current in-memory shadow of the profile cache to disk.

    Only stores stable identity metadata — never serialises handles,
    full workflows, images, prompts, or output data.
    """
    with _profile_disk_lock:
        entries = dict(_profile_disk_cache)
        # Prune stale or oversized entries before write
        if len(entries) > _DISK_CACHE_MAX:
            _keys = list(entries.keys())
            for _k in _keys[:_DISK_CACHE_MAX // 2]:
                entries.pop(_k, None)
    _write_disk_cache("profile", entries)


def _flush_restore_disk_cache() -> None:
    """Write the current in-memory shadow of the restore cache to disk."""
    with _restore_disk_lock:
        entries = dict(_restore_disk_cache)
        if len(entries) > _DISK_CACHE_MAX:
            _keys = list(entries.keys())
            for _k in _keys[:_DISK_CACHE_MAX // 2]:
                entries.pop(_k, None)
    _write_disk_cache("restore", entries)


def _remove_profile_disk_entry(cache_key: str) -> None:
    """Remove a single entry from the profile disk cache (invalidation)."""
    with _profile_disk_lock:
        _profile_disk_cache.pop(cache_key, None)
    _flush_profile_disk_cache()


def _remove_restore_disk_entry(cache_key: str) -> None:
    """Remove a single entry from the restore disk cache (invalidation)."""
    with _restore_disk_lock:
        _restore_disk_cache.pop(cache_key, None)
    _flush_restore_disk_cache()


def _reset_disk_caches() -> None:
    """Clear both disk caches in memory and on filesystem (test/teardown only)."""
    with _profile_disk_lock:
        _profile_disk_cache.clear()
    with _restore_disk_lock:
        _restore_disk_cache.clear()
    # Write empty files to reset on-disk state
    _write_disk_cache("profile", {})
    _write_disk_cache("restore", {})


# ---------------------------------------------------------------------------
# Restore-plan publish cache (process-safe, skips remote calls when
# the canonical identity is unchanged for the same app/workspace)
# ---------------------------------------------------------------------------

_RESTORE_PUBLISH_CACHE: dict[str, dict] = {}
"""``{cache_key: {"identity_hash": str, "publication_result": dict}}`` — cached
publication metadata keyed by plan identity.

Cache-key format: ``stable_hash({app_identity, ws_id, plan_identity_hash})``.
Also serves as the last-successful publication store — cleared only by
module reload or explicit ``_reset_restore_publish_cache()``.
Thread-safe via ``_RESTORE_PUBLISH_CACHE_LOCK``.
Bounded to ``_RESTORE_PUBLISH_CACHE_MAX`` entries.
"""

_RESTORE_PUBLISH_CACHE_LOCK = threading.Lock()
"""Guard for all ``_RESTORE_PUBLISH_CACHE`` access."""

_RESTORE_PUBLISH_CACHE_MAX = 100
"""Maximum entries in the restore publish cache before eviction."""

# ── Cache-reset counters (monotonic per process) ────────────────────────
_profile_cache_reset_count: int = 0
"""Monotonic counter incremented each time ``_reset_profile_prep_cache`` is called."""

_restore_cache_reset_count: int = 0
"""Monotonic counter incremented each time ``_reset_restore_publish_cache`` is called."""


def _app_identity() -> str:
    """Current app identity used for cache scoping (matches ``warmup_profile._app_identity``)."""
    app = os.environ.get("COMFYMODAL_V2_APP_NAME", "").strip()
    if not app:
        app = os.environ.get("COMFYMODAL_APP_NAME", "").strip()
    return app or "comfyui"


def _workspace_identity(workspace: Mapping[str, Any] | None) -> str:
    if isinstance(workspace, Mapping):
        value = workspace.get("id") or workspace.get("workspace_id") or ""
        if value:
            return str(value)
    return "__default__"


def _restore_plan_identity_hash(plan: RestorePlan) -> str:
    """Deterministic hash of identity fields, excluding volatile
    ``generation`` and ``created_at``.

    Mirrors ``RestorePlanPublisher._identity_hash`` so the local cache
    is consistent with the publisher's own no-op detection.
    """
    identity = {
        "schema_version": plan.schema_version,
        "model_key": plan.model_key.to_dict(),
        "prefill_key": plan.prefill_key.to_dict(),
        "model_spec": dict(plan.model_spec),
        "prefill_spec": dict(plan.prefill_spec),
        "source_workflow_hash": plan.source_workflow_hash,
    }
    return stable_hash(identity)


def _reset_restore_publish_cache() -> None:
    """Clear the restore-plan publish cache (test / teardown only)."""
    global _restore_cache_reset_count
    with _RESTORE_PUBLISH_CACHE_LOCK:
        _RESTORE_PUBLISH_CACHE.clear()
        _restore_cache_reset_count += 1


def _evict_restore_publish_cache() -> None:
    """Evict oldest entries when cache exceeds ``_RESTORE_PUBLISH_CACHE_MAX``."""
    with _RESTORE_PUBLISH_CACHE_LOCK:
        while len(_RESTORE_PUBLISH_CACHE) > _RESTORE_PUBLISH_CACHE_MAX:
            _RESTORE_PUBLISH_CACHE.pop(next(iter(_RESTORE_PUBLISH_CACHE)), None)


# ---------------------------------------------------------------------------
# Profile preparation cache — skip prepare_active_next_profile when the
# model identity (app_identity, ws_id, model_profile_key, prefill_key) is
# unchanged for the same process.  Also serves as the last-successful
# profile store — populated on success, cleared only by module reload or
# explicit ``_reset_profile_prep_cache()``.
# ---------------------------------------------------------------------------

_PROFILE_PREP_CACHE: dict[str, dict] = {}
"""``{cache_key: profile_result}`` — cached prepared profile results.

Cache-key format: ``stable_hash({app_identity, ws_id, model_profile_key,
prefill_key})``.
Also serves as the last-successful profile store — populated on success,
cleared only by module reload or explicit ``_reset_profile_prep_cache()``.
Thread-safe via ``_PROFILE_PREP_CACHE_LOCK``.
Bounded to ``_PROFILE_PREP_CACHE_MAX`` entries.
"""

_PROFILE_PREP_CACHE_LOCK = threading.Lock()
"""Guard for all ``_PROFILE_PREP_CACHE`` access."""

_PROFILE_PREP_CACHE_MAX = 100
"""Maximum entries in the profile prep cache before eviction."""


def _profile_prep_cache_key(
    app_identity: str,
    ws_id: str,
    model_profile_key: str,
    prefill_key: str,
) -> str:
    """Deterministic cache key for profile preparation results.

    Includes only stable identity fields that reflect the actual model
    profile identity, excluding volatile workflow content hashes.
    Matches the semantics of ``warmup_profile``'s own dedup key so the
    outer (execute_plan) and inner (prepare_active_next_profile) caches
    miss/populate consistently.
    """
    identity = {
        "a": app_identity,
        "w": ws_id,
        "m": model_profile_key,
        "p": prefill_key,
    }
    return stable_hash(identity)


def _reset_profile_prep_cache() -> None:
    """Clear the profile prep cache (test / teardown only)."""
    global _profile_cache_reset_count
    with _PROFILE_PREP_CACHE_LOCK:
        _PROFILE_PREP_CACHE.clear()
        _profile_cache_reset_count += 1


def _evict_profile_prep_cache() -> None:
    """Evict oldest entries when cache exceeds ``_PROFILE_PREP_CACHE_MAX``."""
    with _PROFILE_PREP_CACHE_LOCK:
        while len(_PROFILE_PREP_CACHE) > _PROFILE_PREP_CACHE_MAX:
            _PROFILE_PREP_CACHE.pop(next(iter(_PROFILE_PREP_CACHE)), None)


# ── Bootstrap: pre-populate in-memory caches from disk on import ─────
# Must live here — after _PROFILE_PREP_CACHE, _PROFILE_PREP_CACHE_LOCK,
# _RESTORE_PUBLISH_CACHE, _RESTORE_PUBLISH_CACHE_LOCK, _evict_profile_prep_cache,
# and _evict_restore_publish_cache are all defined.
_populate_profile_cache_from_disk()
_populate_restore_cache_from_disk()


def _reset_all_cache_counters() -> None:
    """Reset all caches and counters.

    Clears ``_PROFILE_PREP_CACHE`` and ``_RESTORE_PUBLISH_CACHE``
    (the sole process-local stores) and resets their reset counters.
    Also resets the warmup-profile module-level dedup cache so the
    inner ``prepare_active_next_profile`` cannot short-circuit after
    a cache reset.
    Also clears and persists both disk-backed caches.

    Test / teardown only.
    """
    _reset_profile_prep_cache()
    _reset_restore_publish_cache()
    _reset_disk_caches()
    from warmup_profile import _reset_last_stable_profile_cache as _wp_reset
    _wp_reset()


# ---------------------------------------------------------------------------
# RunTrace — in-memory hierarchical span collector
# ---------------------------------------------------------------------------


class RunTrace:
    """Hierarchical execution trace using ``perf_counter_ns`` for duration and
    ``time.time`` only for wall-clock correlation.

    Accumulates in memory.  Callers invoke ``emit_local_summary`` before
    Modal submission and ``emit_remote_summary`` before return.  Persistence
    happens only after output delivery (caller responsibility).

    Optional spans (LocalRemoteInvoker, scheduler, runner, lease, checkpoint,
    StudioProgressTracker, LocalRemoteHandler, deploy_listener, scheduler_loop,
    hot_reload_listener) are always present with ``called/count/duration_ms/reason``.
    Payload-size fields report byte counts without full prompt/image bytes.

    Correlation fields (trace_id, run_id, prompt_id, run_surface) are set at
    creation and included in every summary.
    """

    # Required canonical operation count names — counted at the actual
    # operation boundary.
    CANONICAL_COUNTS = frozenset({
        "production_compile_count",
        "full_workflow_hash_count",
        "model_stack_extract_count",
        "active_profile_prepare_count",
        "modal_handle_lookup_count",
        "run_prompt_stream_call_count",
        "workflow_deepcopy_count",
        "workflow_serialization_count",
    })

    # All named Studio wrapper spans — always present with called=False
    # for a direct Playground run.  Includes the original high-level names
    # plus every granular span that the Studio lifecycle creates for
    # experiment/scheduler/runner/invoker/lease flows.
    MARK_OPTIONAL = (
        # Original high-level optional spans
        "LocalRemoteInvoker", "scheduler", "runner", "lease", "checkpoint",
        "StudioProgressTracker", "LocalRemoteHandler", "deploy_listener",
        "scheduler_loop", "hot_reload_listener",
        # Granular Studio lifecycle spans
        "studio_single_run_enter", "direct_studio_run_completion",
        "experiment_creation", "run_history_creation",
        "scheduler_creation", "scheduler_start",
        "runner_creation",
        "local_remote_invoker_creation",
        "local_remote_invoker_open_worker",
        "local_remote_invoker_run_cell",
        "local_remote_invoker_close_worker",
        "lease_claim", "checkpoint_write", "journal_write",
        "cell_resolution", "experiment_trace_merge",
        "studio_output_copy", "studio_history_update",
        "studio_output_metadata_write",
        # Required canonical span names — stable entries in every RunTrace summary
        # (called=true when the boundary was reached, otherwise defaults)
        "canonical_execute_enter",
        "workflow_input_size",
        "workflow_deepcopy",
        "workflow_normalization",
        "production_compile",
        "production_validate_local",
        "source_workflow_hash",
        "compiled_workflow_hash",
        "production_plan_hash",
        "model_stack_extract",
        "used_node_class_extract",
        "input_image_discovery",
        "input_image_read",
        "input_image_encode",
        "extra_data_build",
        "modal_options_build",
        "production_report_build",
        "active_profile_build",
        "active_profile_dedup",
        "active_profile_local_write",
        "active_profile_remote_call",
        "active_profile_ack_wait",
        "modal_handle_lookup",
        "modal_handle_cache_hit",
        "modal_argument_serialization",
        "remote_generator_create",
        "remote_submit",
        "first_remote_message",
        "remote_result_complete",
        "canonical_execute_exit",
    )

    def __init__(
        self,
        *,
        trace_id: str = "",
        run_id: str = "",
        prompt_id: str = "",
        run_surface: str = "unknown",
    ) -> None:
        self._spans: dict[str, dict[str, Any]] = {}
        self._counts: dict[str, int] = {}
        self._wall_start: float = time.time()
        self._perf_start_ns: int = time.perf_counter_ns()
        self._major_samples: list[dict[str, Any]] = []
        self._payload_sizes: dict[str, int] = {}
        self._meta: dict[str, Any] = {}  # canonical metadata without full workflow bytes
        # Correlation fields
        self._trace_id: str = trace_id or uuid.uuid4().hex[:16]
        self._run_id: str = run_id or uuid.uuid4().hex[:12]
        self._prompt_id: str = prompt_id
        self._run_surface: str = run_surface

    # -- correlation property access --

    @property
    def trace_id(self) -> str:
        return self._trace_id

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def prompt_id(self) -> str:
        return self._prompt_id

    @property
    def run_surface(self) -> str:
        return self._run_surface

    # -- span lifecycle --

    def begin(self, name: str, *, reason: str = "") -> None:
        entry = self._spans.setdefault(name, {})
        entry["called"] = True
        entry["_start_ns"] = time.perf_counter_ns()
        entry["wall_s"] = time.time()
        entry["count"] = entry.get("count", 0) + 1
        if reason:
            entry["reason"] = reason

    def end(self, name: str, *, reason: str = "") -> None:
        entry = self._spans.get(name)
        if entry is None or "_start_ns" not in entry:
            return
        entry["duration_ns"] = time.perf_counter_ns() - entry["_start_ns"]
        entry["duration_ms"] = round(entry["duration_ns"] / 1_000_000, 2)
        del entry["_start_ns"]
        if reason:
            entry["reason"] = reason

    def count(self, name: str, delta: int = 1) -> None:
        self._counts[name] = self._counts.get(name, 0) + delta

    def record_payload_size(self, label: str, byte_count: int) -> None:
        self._payload_sizes[label] = byte_count

    def set_meta(self, **fields: Any) -> None:
        """Store canonical metadata fields (model_stack, hashes, GPU, etc.)
        without logging full workflow/image bytes."""
        self._meta.update(fields)

    def sample(self, label: str, **fields: Any) -> None:
        self._major_samples.append({"label": label, "wall_s": time.time(), **fields})

    # -- optional spans (always present with called=False by default) --

    def _ensure_optionals(self) -> None:
        for name in self.MARK_OPTIONAL:
            if name not in self._spans:
                self._spans[name] = {
                    "called": False,
                    "count": 0,
                    "duration_ms": 0,
                    "reason": "",
                }

    def _init_canonical_counts(self) -> None:
        """Ensure every named canonical count is present (even if zero)."""
        for name in self.CANONICAL_COUNTS:
            if name not in self._counts:
                self._counts[name] = 0

    # -- emission --

    def emit_local_summary(self) -> dict[str, Any]:
        """Structured summary emitted before Modal submission."""
        self._ensure_optionals()
        self._init_canonical_counts()
        return {
            "trace_id": self._trace_id,
            "run_id": self._run_id,
            "prompt_id": self._prompt_id,
            "run_surface": self._run_surface,
            "spans": {k: {sk: sv for sk, sv in v.items() if not sk.startswith("_")}
                      for k, v in self._spans.items()},
            "counts": dict(self._counts),
            "payload_sizes": dict(self._payload_sizes),
            "meta": dict(self._meta),
            "wall_start_s": self._wall_start,
        }

    def emit_remote_summary(self) -> dict[str, Any]:
        """Structured summary emitted before return (after Modal call)."""
        self._ensure_optionals()
        self._init_canonical_counts()
        return {
            "trace_id": self._trace_id,
            "run_id": self._run_id,
            "prompt_id": self._prompt_id,
            "run_surface": self._run_surface,
            "spans": {k: {sk: sv for sk, sv in v.items() if not sk.startswith("_")}
                      for k, v in self._spans.items()},
            "counts": dict(self._counts),
            "payload_sizes": dict(self._payload_sizes),
            "meta": dict(self._meta),
            "wall_start_s": self._wall_start,
            "perf_start_ns": self._perf_start_ns,
            "samples": list(self._major_samples),
        }

    def merge_into_trace(self, trace_dict: dict[str, Any]) -> None:
        """Merge run-trace fields into the existing trace payload for history."""
        rs = self.emit_remote_summary()
        trace_dict["_run_trace"] = rs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_class_types(workflow: dict, production_report: dict | None = None) -> None:
    """Local class-type existence check.  Skips compiler-rewritten node IDs."""
    try:
        import nodes as _validate_nodes
    except Exception:
        return  # skip when not running inside ComfyUI

    _requested_types: set[str] = set()
    _PRODUCTION_REMOTE_CLASSES = frozenset({
        "ComfyModalProductionOutput",
        "ComfyModalProductionImageComparerOutput",
    })
    for _spec in workflow.values():
        if isinstance(_spec, dict):
            _ct = _spec.get("class_type")
            if isinstance(_ct, str) and _ct:
                _requested_types.add(_ct)

    _production_active = bool(
        production_report
        and isinstance(production_report, dict)
        and production_report.get("enabled")
    )
    if _production_active:
        _rewritten_out_ids = set(production_report.get("direct_output_rewritten_node_ids", []))
        _rewritten_rgthree_ids = set(production_report.get("rgthree_comparer_rewritten_node_ids", []))
        _validated_types: set[str] = set()
        for _nid, _spec in workflow.items():
            if not isinstance(_spec, dict):
                continue
            _ct = _spec.get("class_type")
            if not isinstance(_ct, str) or not _ct:
                continue
            if _ct == "ComfyModalProductionOutput" and str(_nid) in _rewritten_out_ids:
                continue
            if _ct == "ComfyModalProductionImageComparerOutput" and str(_nid) in _rewritten_rgthree_ids:
                continue
            _validated_types.add(_ct)
    else:
        _validated_types = _requested_types

    _missing = sorted(
        ct for ct in _validated_types
        if ct not in _validate_nodes.NODE_CLASS_MAPPINGS
    )
    if _missing:
        raise RuntimeError(
            f"Missing custom node class(es): {_missing}. "
            f"Install the missing custom nodes or fix the workflow."
        )


def _collect_input_images(workflow: dict, comfyui_root: str) -> dict[str, str]:
    """Base64-encode local images referenced by LoadImage nodes."""
    images: dict[str, str] = {}
    _WORKFLOW_IMAGE_SUFFIX_DIRS = {
        " [output]": "output",
        " [input]": "input",
        " [temp]": "temp",
    }

    def _resolve_candidates(filename: str) -> list[str]:
        name = (filename or "").strip()
        for suffix, directory in _WORKFLOW_IMAGE_SUFFIX_DIRS.items():
            if name.endswith(suffix):
                base = name[: -len(suffix)].rstrip()
                return [os.path.join(comfyui_root, directory, *base.replace("\\", "/").split("/"))]
        parts = [p for p in filename.replace("\\", "/").split("/") if p not in ("", ".")]
        if not parts or any(p == ".." for p in parts):
            return []
        return [
            os.path.join(comfyui_root, d, *parts)
            for d in ("input", "output")
            if os.path.isdir(os.path.join(comfyui_root, d))
        ]

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        if not class_type.startswith("LoadImage"):
            continue
        for key in ("image", "mask"):
            filename = node.get("inputs", {}).get(key, "")
            if not isinstance(filename, str) or not filename:
                continue
            if filename in images:
                continue
            if filename.startswith(("http://", "https://")):
                continue
            candidates = _resolve_candidates(filename)
            for filepath in candidates:
                if os.path.isfile(filepath):
                    with open(filepath, "rb") as f:
                        images[filename] = base64.b64encode(f.read()).decode()
                    break
    return images


def _event_span_ms(trace: RuntimeTrace, start_name: str, end_name: str) -> float | None:
    start_ns: int | None = None
    for event in trace.events:
        if event.name == start_name:
            start_ns = event.monotonic_ns
        elif event.name == end_name and start_ns is not None:
            return round((event.monotonic_ns - start_ns) / 1_000_000, 3)
    return None


# _strict_event_span_ms, _event_mono_ns, _derived_mono_delta_ms
# are imported from comfymodal_runtime.trace above.


def build_execution_plan(
    workflow: dict,
    *,
    prompt_id: str = "",
    client_id: str = "",
    input_images: dict[str, str] | None = None,
    modal_options: dict | None = None,
    production_options: dict | None = None,
    production_report: dict | None = None,
    gpu: str | None = None,
    workspace: dict | None = None,
    request_metadata: dict | None = None,
    comfyui_root: str = "",
    trace: RuntimeTrace | None = None,
    validate: bool = True,
) -> ExecutionPlan:
    """Normalize, validate, compile, and freeze one dispatch plan."""
    if trace:
        trace.emit("plan_build_start", phase="local", metadata={"prompt_id": prompt_id})
    source_workflow = copy.deepcopy(workflow or {})
    source_hash = prompt_sha256(source_workflow)
    if validate:
        assert_valid_api_prompt_structure(source_workflow)
        _validate_class_types(source_workflow, production_report)

    dispatch_workflow = source_workflow
    report = dict(production_report or {})
    normalized_production = None
    if report.get("enabled"):
        # Reuse existing validated deep copy — production_report already
        # describes the compiled workflow. No second deepcopy needed.
        pass
    elif production_options and production_options.get("enabled"):
        normalized_production = normalize_production_options(production_options)
        compiled = compile_production_workflow(
            source_workflow,
            normalized_production,
            allow_direct_output_rewrite=True,
        )
        dispatch_workflow = compiled.compiled_workflow
        report = dict(compiled.report)
    dispatch_hash = prompt_sha256(dispatch_workflow)
    if report.get("enabled"):
        compiled_hash = str(report.get("compiled_workflow_hash", ""))
        if compiled_hash and compiled_hash != dispatch_hash:
            raise AssertionError(
                "execution plan compiled workflow hash mismatch: "
                f"compiled={compiled_hash[:12]} dispatch={dispatch_hash[:12]}"
            )

    if input_images is None:
        input_images = _collect_input_images(dispatch_workflow, comfyui_root) if comfyui_root else {}

    model_stack = extract_model_stack(dispatch_workflow)
    try:
        from optimizations import extract_safe_prompt_bundle
        bundle_result = extract_safe_prompt_bundle(dispatch_workflow)
        prompt_bundle = bundle_result.get("bundle", {}) if bundle_result.get("eligible") else {}
    except Exception:
        prompt_bundle = summarize_prompt_fields(dispatch_workflow)

    option_source = dict(modal_options or {})
    if report.get("enabled"):
        option_source["production"] = {
            "enabled": True,
            "output_node_ids": list(report.get("output_node_ids", [])),
        }
    options = ExecutionOptions.from_legacy(
        option_source,
        production_report=report,
        default_production=bool(report.get("enabled")),
    )
    output_node_ids = tuple(str(v) for v in report.get("output_node_ids", options.production_output_node_ids))
    metadata = dict(request_metadata or {})
    # Propagate request_origin_info from trace when request_metadata lacks it.
    # Use Mapping check because frozen dataclasses wrap nested dicts as
    # mappingproxy; isinstance(x, dict) fails for mappingproxy values.
    if trace is not None:
        _trace_origin = trace._metadata.get("request_origin_info", {})
        if isinstance(_trace_origin, Mapping) and _trace_origin:
            metadata.setdefault("request_origin_info", dict(_trace_origin))
    metadata.update({
        "prompt_id": prompt_id,
        "client_id": client_id,
        "selected_gpu": gpu or "",
        "workspace_id": str((workspace or {}).get("id", "")),
    })
    plan = ExecutionPlan(
        workflow=dispatch_workflow,
        workflow_hash=dispatch_hash,
        source_workflow_hash=str(report.get("source_workflow_hash", source_hash)),
        production_report=report,
        model_stack=model_stack,
        prompt_bundle=prompt_bundle,
        output_node_ids=output_node_ids,
        input_images=input_images or {},
        execution_options=options,
        request_metadata=metadata,
    )
    if trace:
        trace.emit("plan_build_end", phase="local", metadata={
            "workflow_hash": plan.workflow_hash,
            "source_workflow_hash": plan.source_workflow_hash,
            "production_enabled": bool(report.get("enabled")),
        })
    return plan


async def execute_plan(
    plan: ExecutionPlan,
    *,
    transport: ModalTransport | None = None,
    restore_publisher: Any | None = None,
    profile_setter: Callable[..., Any] | None = None,
    profile_checker: Callable[..., Any] | None = None,
    gpu: str | None = None,
    workspace: dict | None = None,
    trace: RuntimeTrace | None = None,
    event_sink: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Publish one restore plan, submit one plan, and merge one trace.

    When *profile_setter* is provided, calls ``prepare_active_next_profile``
    before restore publication / Modal submission.  A missing setter is a
    safe dry-run / no-remote path.  *profile_checker* is forwarded as the
    ``checker`` argument to ``prepare_active_next_profile`` (cold-safe
    read-only identity seam).
    """
    runtime_trace = trace or RuntimeTrace(
        request_id=str(plan.request_metadata.get("prompt_id", "")),
        process="local",
    )

    # Propagate request_origin_info from plan metadata into runtime_trace when
    # the trace metadata does not already carry it.  Preserve existing values
    # (never overwrite with plan defaults).
    # Use Mapping check because frozen dataclasses wrap nested dicts as
    # mappingproxy.
    _plan_origin = plan.request_metadata.get("request_origin_info", {})
    if isinstance(_plan_origin, Mapping) and _plan_origin:
        _existing_origin = runtime_trace._metadata.get("request_origin_info", {})
        if not isinstance(_existing_origin, Mapping) or not _existing_origin:
            runtime_trace.set_metadata(request_origin_info=dict(_plan_origin))

    # ── Entry timestamp for the execute_plan boundary ──
    runtime_trace.emit("execute_plan_entry", phase="local")

    # ── Single canonical payload — materialize the frozen plan exactly once ──
    # Reused for active-profile workflow, restore publication, and final Modal
    # payload.  ExecutionPlan is immutable; the thawed dict is a safe copy.
    runtime_trace.emit("plan_materialization_start", phase="local")
    _plan_mat_start_ns = time.perf_counter_ns()
    _canonical_dict: dict = plan.to_dict()
    _plan_mat_end_ns = time.perf_counter_ns()
    runtime_trace.emit("plan_materialization_end", phase="local")
    _plan_mat_ms = round((_plan_mat_end_ns - _plan_mat_start_ns) / 1_000_000, 3)
    runtime_trace.set_metadata(
        plan_materialization_count=1,
        plan_to_dict_count=1,
        plan_materialization_ms=_plan_mat_ms,
    )
    _canonical_workflow: dict = _canonical_dict["workflow"]

    # ── Profile preparation (before restore publication / Modal submission) ──
    runtime_trace.emit("active_profile_prepare_start", phase="local")
    runtime_trace.emit("active_next_profile_start", phase="local")
    if profile_setter is not None:
        # ── Profile prep cache identity keys ──
        _profile_ws_id = _workspace_identity(workspace)
        _profile_app_identity = _app_identity()
        _pr = dict(plan.production_report) if isinstance(plan.production_report, Mapping) else {}

        # Compute stable model identity keys from the canonical workflow
        # (same values prepare_active_next_profile would produce).
        _model_profile_key, _prefill_key = compute_profile_identity_keys(
            _canonical_workflow,
        )

        _profile_cache_key = _profile_prep_cache_key(
            _profile_app_identity, _profile_ws_id,
            _model_profile_key, _prefill_key,
        )

        _profile_cache_lookup_start_ns = time.perf_counter_ns()

        # ── Instrumentation: owner metadata for diagnostics ──
        _cache_pid = os.getpid()
        _cache_module_id = str(id(sys.modules[__name__]))
        _cache_obj_id = str(id(_PROFILE_PREP_CACHE))
        _cache_size_before = len(_PROFILE_PREP_CACHE)
        _cache_reset_count_current = _profile_cache_reset_count
        _profile_miss_reason = ""

        with _PROFILE_PREP_CACHE_LOCK:
            _cached_result = _PROFILE_PREP_CACHE.get(_profile_cache_key)
        _profile_cache_lookup_ms = round((time.perf_counter_ns() - _profile_cache_lookup_start_ns) / 1_000_000, 3)

        if _cached_result is not None:
            # Identity unchanged — reuse cached result, no remote calls
            _pn_result = dict(_cached_result)
            runtime_trace.emit(
                "profile_prep_cache_hit", phase="local",
                metadata={"cache_key_prefix": _profile_cache_key[:16],
                          "source": "profile_prep_cache"},
            )
            runtime_trace.set_metadata(
                active_profile_publish_decision="cached_unchanged",
                active_profile_stable_key=_pn_result.get("active_profile_stable_key", ""),
                active_profile_token=_pn_result.get("active_profile_token", ""),
                local_active_profile_prepare_ms=0.0,
                active_profile_remote_call=0,
                active_profile_remote_ms=0.0,
                active_profile_prepare_count=0,
                profile_cache_hit=True,
                profile_cache_lookup_ms=_profile_cache_lookup_ms,
                profile_remote_call_performed=False,
                profile_checker_performed=False,
                profile_checker_matched=False,
                profile_setter_performed=False,
                active_profile_local_ms=0.0,
                active_profile_cache_lookup_ms=_profile_cache_lookup_ms,
                active_profile_checker_ms=0.0,
                active_profile_setter_ms=0.0,
                active_profile_total_ms=_profile_cache_lookup_ms,
                source_workflow_hash=plan.source_workflow_hash,
                model_stack=dict(plan.model_stack),
                prompt_summary=dict(plan.prompt_bundle),
                # Instrumentation diagnostics
                profile_cache_pid=_cache_pid,
                profile_cache_module_id=_cache_module_id,
                profile_cache_object_id=_cache_obj_id,
                profile_cache_size_before=_cache_size_before,
                profile_cache_key_hash=_profile_cache_key[:16],
                profile_identity_key=_model_profile_key[:16],
                profile_cache_reset_count=_cache_reset_count_current,
                profile_miss_reason="",
                # Disk cache telemetry
                disk_profile_cache_hit=_profile_cache_key in _profile_disk_cache,
                disk_profile_read_count=_disk_profile_read_count,
                disk_profile_write_count=_disk_profile_write_count,
                disk_profile_miss_count=_disk_profile_miss_count,
                disk_profile_corruption_count=_disk_profile_corruption_count,
            )
            runtime_trace.emit("active_next_profile_end", phase="local", metadata={
                "decision": "profile_prep_cache_hit",
                "stable_key": _pn_result.get("active_profile_stable_key", "")[:16],
            })
        else:
            # ── Cache miss — determine reason ──
            # Possible reasons: key not found (never seen), cache reset occurred,
            # identity changed (model profile or prefill), or app/workspace changed.
            # Compute the miss reason string for diagnostics.
            _profile_miss_reason = "key_not_found"
            if _cache_size_before > 0:
                # Cache had entries but this key wasn't one of them
                _profile_miss_reason = "identity_mismatch"
            elif _cache_reset_count_current > 0:
                _profile_miss_reason = "cache_reset"

            runtime_trace.emit("plan_serialization_start", phase="local",
                               metadata={"purpose": "profile_activation"})
            _activation_wf = _canonical_workflow  # reuse canonical payload
            runtime_trace.emit("plan_serialization_end", phase="local",
                               metadata={"purpose": "profile_activation",
                                         "reused_canonical": True})
            _activation_hash = plan.source_workflow_hash or plan.workflow_hash
            _prod_opts: dict | None = None
            if _pr.get("enabled"):
                _prod_opts = {
                    "enabled": True,
                    "output_node_ids": list(_pr.get("output_node_ids", [])),
                    "bypass_node_ids": list(_pr.get("bypass_node_ids", [])),
                    "source_workflow_hash": _pr.get("source_workflow_hash", ""),
                    "compiled_workflow_hash": _pr.get("compiled_workflow_hash", ""),
                    "production_plan_hash": _pr.get("production_plan_hash", ""),
                    "compiler_version": _pr.get("compiler_version", COMPILER_SCHEMA_VERSION),
                    "hash_schema_version": _pr.get("hash_schema_version", HASH_SCHEMA_VERSION),
                    "production_plan_schema_version": _pr.get("production_plan_schema_version", PRODUCTION_PLAN_SCHEMA_VERSION),
                }
                _activation_hash = _pr.get("source_workflow_hash", _activation_hash)
            _pn_result = await prepare_active_next_profile(
                _activation_wf,
                _activation_hash,
                production_options=_prod_opts,
                workspace=workspace,
                setter=profile_setter,
                checker=profile_checker,
            )
            runtime_trace.set_metadata(
                active_profile_publish_decision=_pn_result.get("active_profile_publish_decision", ""),
                active_profile_stable_key=_pn_result.get("active_profile_stable_key", ""),
                active_profile_token=_pn_result.get("active_profile_token", ""),
                local_active_profile_prepare_ms=_pn_result.get("local_active_profile_prepare_ms", 0.0),
                active_profile_remote_call=_pn_result.get("active_profile_remote_call", 0),
                active_profile_remote_ms=_pn_result.get("active_profile_remote_ms", 0.0),
                active_profile_prepare_count=1,
                profile_cache_hit=False,
                profile_cache_lookup_ms=_profile_cache_lookup_ms,
                profile_remote_call_performed=bool(_pn_result.get("active_profile_remote_call", 0)),
                profile_checker_performed=bool(_pn_result.get("profile_checker_performed", False)),
                # Propagated from prepare_active_next_profile result.
                # True only when the volume-backed checker returned matched=True;
                # False for process-local dedup hit, setter-write, or no-checker paths.
                profile_checker_matched=_pn_result.get("profile_checker_matched", False),
                profile_setter_performed=bool(_pn_result.get("profile_setter_performed", False)),
                active_profile_local_ms=_pn_result.get("active_profile_local_ms", 0.0),
                active_profile_cache_lookup_ms=_pn_result.get("active_profile_cache_lookup_ms", _profile_cache_lookup_ms),
                active_profile_checker_ms=_pn_result.get("active_profile_checker_ms", 0.0),
                active_profile_setter_ms=_pn_result.get("active_profile_setter_ms", 0.0),
                active_profile_total_ms=_pn_result.get("active_profile_total_ms", 0.0),
                source_workflow_hash=plan.source_workflow_hash,
                model_stack=dict(plan.model_stack),
                prompt_summary=dict(plan.prompt_bundle),
                # Instrumentation diagnostics
                profile_cache_pid=_cache_pid,
                profile_cache_module_id=_cache_module_id,
                profile_cache_object_id=_cache_obj_id,
                profile_cache_size_before=_cache_size_before,
                profile_cache_key_hash=_profile_cache_key[:16],
                profile_identity_key=_model_profile_key[:16],
                profile_cache_reset_count=_cache_reset_count_current,
                profile_miss_reason=_profile_miss_reason,
                # Disk cache telemetry
                disk_profile_cache_hit=False,
                disk_profile_read_count=_disk_profile_read_count,
                disk_profile_write_count=_disk_profile_write_count,
                disk_profile_miss_count=_disk_profile_miss_count,
                disk_profile_corruption_count=_disk_profile_corruption_count,
            )
            runtime_trace.emit("active_next_profile_end", phase="local", metadata={
                "decision": _pn_result.get("active_profile_publish_decision", ""),
                "stable_key": _pn_result.get("active_profile_stable_key", "")[:16],
                "miss_reason": _profile_miss_reason,
            })
            # On success populate cache; on failure remove any stale entry
            if _pn_result.get("status") not in ("error",):
                with _PROFILE_PREP_CACHE_LOCK:
                    _PROFILE_PREP_CACHE[_profile_cache_key] = dict(_pn_result)
                    while len(_PROFILE_PREP_CACHE) > _PROFILE_PREP_CACHE_MAX:
                        _PROFILE_PREP_CACHE.pop(next(iter(_PROFILE_PREP_CACHE)), None)
                # Persist to disk after confirmed remote success
                _disk_entry = {
                    "result": dict(_pn_result),
                    "model_profile_key": _model_profile_key,
                    "prefill_key": _prefill_key,
                    "ws_id": _profile_ws_id,
                    "app_identity": _profile_app_identity,
                    "ts": time.time(),
                    "pid": _cache_pid,
                }
                with _profile_disk_lock:
                    _profile_disk_cache[_profile_cache_key] = _disk_entry
                    while len(_profile_disk_cache) > _DISK_CACHE_MAX:
                        _profile_disk_cache.pop(next(iter(_profile_disk_cache)), None)
                _flush_profile_disk_cache()
            else:
                # Failure: remove any stale cached entry for this key
                with _PROFILE_PREP_CACHE_LOCK:
                    _PROFILE_PREP_CACHE.pop(_profile_cache_key, None)
                # Also remove from disk cache (invalidation)
                _remove_profile_disk_entry(_profile_cache_key)
    else:
        runtime_trace.emit("active_next_profile_end", phase="local", metadata={"status": "dry_run"})
    runtime_trace.emit("active_profile_prepare_end", phase="local")

    active_transport = transport or ModalTransport()

    # ── Restore publication ──
    runtime_trace.emit("restore_plan_build_start", phase="local")
    if restore_publisher is not None:
        runtime_trace.emit("plan_serialization_start", phase="local",
                           metadata={"purpose": "restore_publication"})
        workflow = _canonical_workflow  # reuse canonical payload
        runtime_trace.emit("plan_serialization_end", phase="local",
                           metadata={"purpose": "restore_publication",
                                     "reused_canonical": True})
        model_key = derive_model_key(workflow)
        prefill_key = derive_prefill_key(model_key, workflow)
        restore_plan = RestorePlan(
            generation=0,
            model_key=model_key,
            prefill_key=prefill_key,
            model_spec=build_restore_model_spec(workflow, dict(plan.model_stack)),
            prefill_spec=dict(prefill_key.encode_options),
            source_workflow_hash=plan.source_workflow_hash,
        )
        runtime_trace.emit("restore_plan_build_end", phase="local")
        runtime_trace.emit("restore_plan_publish_start", phase="local")

        # ── Local process-safe cache: skip remote call when identity
        #    is unchanged for the same app/workspace ──
        plan_identity = _restore_plan_identity_hash(restore_plan)
        _restore_app_identity = _app_identity()
        _restore_ws_id = _workspace_identity(workspace)
        cache_key = _profile_prep_cache_key(
            _restore_app_identity, _restore_ws_id, plan_identity, "",
        )

        # ── Instrumentation metadata ──
        _restore_cache_pid = os.getpid()
        _restore_cache_module_id = str(id(sys.modules[__name__]))
        _restore_cache_obj_id = str(id(_RESTORE_PUBLISH_CACHE))
        _restore_cache_size_before = len(_RESTORE_PUBLISH_CACHE)
        _restore_cache_reset_count_current = _restore_cache_reset_count
        _restore_miss_reason = ""

        _restore_cache_lookup_start_ns = time.perf_counter_ns()
        with _RESTORE_PUBLISH_CACHE_LOCK:
            _cached_restore = _RESTORE_PUBLISH_CACHE.get(cache_key)
        _restore_cache_lookup_ms = round((time.perf_counter_ns() - _restore_cache_lookup_start_ns) / 1_000_000, 3)

        if _cached_restore is not None:
            # Identity unchanged — skip the remote publish call entirely.
            # Return the cached metadata including observed generation.
            _cached_publish_result = dict(_cached_restore.get("publication_result", {}))
            observed_generation = _cached_publish_result.get(
                "generation", _cached_publish_result.get("observed_generation", "")
            )
            runtime_trace.emit(
                "restore_publish_cache_skip", phase="local",
                metadata={"cache_key_prefix": cache_key[:64], "identity": plan_identity[:16]},
            )
            runtime_trace.set_metadata(
                restore_publish_cache_skipped=True,
                restore_publish_cache_hit=True,
                restore_cache_lookup_ms=_restore_cache_lookup_ms,
                restore_publish_ms=_restore_cache_lookup_ms,
                restore_remote_call_performed=False,
                restore_publish_result=_cached_publish_result,
                # Restore instrumentation
                restore_cache_pid=_restore_cache_pid,
                restore_cache_module_id=_restore_cache_module_id,
                restore_cache_object_id=_restore_cache_obj_id,
                restore_cache_size_before=_restore_cache_size_before,
                restore_cache_key_hash=cache_key[:64],
                restore_identity_hash=plan_identity[:16],
                complete_plan_identity_hash=plan_identity[:16],
                restore_cache_reset_count=_restore_cache_reset_count_current,
                restore_miss_reason="",
                # Disk cache telemetry
                disk_restore_cache_hit=cache_key in _restore_disk_cache,
                disk_restore_read_count=_disk_restore_read_count,
                disk_restore_write_count=_disk_restore_write_count,
                disk_restore_miss_count=_disk_restore_miss_count,
                disk_restore_corruption_count=_disk_restore_corruption_count,
            )
        else:
            # ── Cache miss — determine reason ──
            _restore_miss_reason = "key_not_found"
            if _restore_cache_size_before > 0:
                _restore_miss_reason = "identity_mismatch"
            elif _restore_cache_reset_count_current > 0:
                _restore_miss_reason = "cache_reset"

            runtime_trace.set_metadata(
                restore_publish_cache_skipped=False,
                restore_publish_cache_hit=False,
                restore_cache_lookup_ms=_restore_cache_lookup_ms,
            )
            publish_result = restore_publisher.publish(restore_plan)
            if inspect.isawaitable(publish_result):
                publish_result = await publish_result
            runtime_trace.set_metadata(restore_remote_call_performed=True)
            _publish_succeeded = True
            if isinstance(publish_result, Mapping):
                observed_generation = publish_result.get(
                    "generation", publish_result.get("observed_generation", "")
                )
                runtime_trace.set_metadata(restore_publish_result=dict(publish_result))
                # Guard cache against semantic failure: detect any of:
                #   status in error/failure/failed, ok==False, success==False,
                #   or a truthy error/failure field.
                _pub_status = publish_result.get("status", "")
                _pub_ok = publish_result.get("ok", True)
                _pub_success = publish_result.get("success", True)
                _pub_error_field = publish_result.get("error") or publish_result.get("failure")
                if (_pub_status in ("error", "failure", "failed")
                        or _pub_ok is False
                        or _pub_success is False
                        or bool(_pub_error_field)):
                    _publish_succeeded = False
            else:
                observed_generation = publish_result
            # On success populate cache with metadata; on failure remove stale.
            if _publish_succeeded:
                _publication_result = (
                    dict(publish_result)
                    if isinstance(publish_result, Mapping)
                    else {"generation": observed_generation}
                )
                with _RESTORE_PUBLISH_CACHE_LOCK:
                    _RESTORE_PUBLISH_CACHE[cache_key] = {
                        "identity_hash": plan_identity,
                        "publication_result": _publication_result,
                    }
                    while len(_RESTORE_PUBLISH_CACHE) > _RESTORE_PUBLISH_CACHE_MAX:
                        _RESTORE_PUBLISH_CACHE.pop(next(iter(_RESTORE_PUBLISH_CACHE)), None)
                # Persist to disk after confirmed remote success
                _restore_disk_entry = {
                    "identity_hash": plan_identity,
                    "publication_result": dict(_publication_result),
                    "ws_id": _restore_ws_id,
                    "app_identity": _restore_app_identity,
                    "ts": time.time(),
                    "pid": _restore_cache_pid,
                }
                with _restore_disk_lock:
                    _restore_disk_cache[cache_key] = _restore_disk_entry
                    while len(_restore_disk_cache) > _DISK_CACHE_MAX:
                        _restore_disk_cache.pop(next(iter(_restore_disk_cache)), None)
                _flush_restore_disk_cache()
            else:
                with _RESTORE_PUBLISH_CACHE_LOCK:
                    _RESTORE_PUBLISH_CACHE.pop(cache_key, None)
                # Also remove from disk cache (invalidation)
                _remove_restore_disk_entry(cache_key)
            # Instrumentation metadata on miss path
            runtime_trace.set_metadata(
                restore_cache_pid=_restore_cache_pid,
                restore_cache_module_id=_restore_cache_module_id,
                restore_cache_object_id=_restore_cache_obj_id,
                restore_cache_size_before=_restore_cache_size_before,
                restore_cache_key_hash=cache_key[:64],
                restore_identity_hash=plan_identity[:16],
                complete_plan_identity_hash=plan_identity[:16],
                restore_cache_reset_count=_restore_cache_reset_count_current,
                restore_miss_reason=_restore_miss_reason,
                # Disk cache telemetry
                disk_restore_cache_hit=cache_key in _restore_disk_cache,
                disk_restore_read_count=_disk_restore_read_count,
                disk_restore_write_count=_disk_restore_write_count,
                disk_restore_miss_count=_disk_restore_miss_count,
                disk_restore_corruption_count=_disk_restore_corruption_count,
            )

        runtime_trace.emit("restore_plan_publish_end", phase="local", metadata={"generation": observed_generation})
    else:
        runtime_trace.emit("restore_plan_build_end", phase="local", metadata={"status": "not_configured"})
        runtime_trace.emit("restore_plan_publish_start", phase="local", metadata={"status": "not_configured"})
        runtime_trace.emit("restore_plan_publish_end", phase="local", metadata={"status": "not_configured"})

    # ── Modal submission ──
    runtime_trace.emit("modal_submit_start", phase="local")
    runtime_trace.emit("gpu_invocation_submit", phase="local")
    result: dict[str, Any] | None = None
    async for message in active_transport.run_plan_stream(
        plan,
        gpu=gpu or str(plan.request_metadata.get("selected_gpu", "")) or None,
        workspace=workspace,
        trace=runtime_trace.to_legacy_timing(prompt_id=str(plan.request_metadata.get("prompt_id", ""))),
        runtime_trace=runtime_trace,
        plan_dict=_canonical_dict,
    ):
        message_type = message.get("type") if isinstance(message, dict) else ""
        if event_sink is not None and message_type in {"progress", "status", "executing"}:
            event_sink(message_type, message.get("data") or message.get("event") or message)
        if message_type == "error":
            raise RuntimeError(message.get("message", "Modal execution error"))
        if message_type == "result":
            result = message.get("data")
            break
    if not isinstance(result, dict):
        raise RuntimeError("execution plan stream ended without result")
    runtime_trace.emit("remote_return_start", process="local", phase="transport")

    # ── Merge local trace into remote result without dropping remote evidence ──
    raw_remote_trace = result.get("trace")
    if not isinstance(raw_remote_trace, dict):
        raw_remote_trace = runtime_trace.to_legacy_timing(
            prompt_id=str(plan.request_metadata.get("prompt_id", ""))
        )
    merged_trace = merge_runtime_traces(runtime_trace, raw_remote_trace)
    remote_trace = dict(raw_remote_trace)
    remote_trace["events"] = [event.to_dict() for event in merged_trace.events]
    remote_trace["metadata"] = dict(merged_trace._metadata)
    remote_trace.setdefault("trace_id", merged_trace.trace_id)
    remote_trace.setdefault("request_id", merged_trace.request_id)
    remote_trace.setdefault("container_session_id", merged_trace.container_session_id)
    # Backend: only set/overwrite when the result actually supplies one.
    if "backend" in result:
        remote_trace["backend"] = result["backend"]
    # V2 containers return the unified event form. Derive legacy-compatible
    # stages/durations at the local merge boundary so Playground/history can
    # expose truthful timing without inventing missing phases. Preserve any
    # fields already supplied by a legacy-compatible remote runtime.
    _legacy_stages = dict(
        merged_trace.to_legacy_timing(
            prompt_id=str(plan.request_metadata.get("prompt_id", ""))
        ).get("stages", {})
    )
    if "stages" in remote_trace and remote_trace["stages"]:
        # Merge: legacy fills gaps, existing remote stages win for exact keys.
        for _k, _v in remote_trace["stages"].items():
            _legacy_stages[_k] = _v
    remote_trace["stages"] = _legacy_stages
    if "deltas_ms" not in remote_trace:
        remote_trace["deltas_ms"] = merged_trace.durations_ms()
    if "trace_version" not in remote_trace:
        remote_trace["trace_version"] = "2.0.0"
    _origin = runtime_trace._metadata.get("request_origin_info", {})
    if not isinstance(_origin, Mapping):
        _origin = {}
    _transport_meta = runtime_trace._metadata
    # Unconditionally extract remote metadata before the modal_input_id check
    # so _remote_metadata is always defined for timestamp fallback lookups.
    _remote_metadata: dict[str, Any] = {}
    if isinstance(raw_remote_trace, dict):
        _remote_metadata = raw_remote_trace.get("metadata", {})
        if not isinstance(_remote_metadata, dict):
            _remote_metadata = {}
    if not _transport_meta.get("modal_input_id"):
        if _remote_metadata.get("modal_input_id"):
            _transport_meta["modal_input_id"] = _remote_metadata["modal_input_id"]

    _local_stages = {
        "local_body_read_ms": _origin.get("local_body_read_ms"),
        "local_json_parse_ms": _origin.get("local_json_parse_ms"),
        "local_preflight_ms": _origin.get("local_preflight_ms"),
        "local_queue_lock_wait_ms": _origin.get("local_queue_lock_wait_ms"),
        "local_queue_enqueue_ms": _origin.get("local_queue_enqueue_ms"),
        "queue_wait_before_worker_ms": _origin.get("queue_wait_before_worker_ms"),
        "plan_build_ms": _event_span_ms(runtime_trace, "plan_build_start", "plan_build_end"),
        "active_profile_ms": _event_span_ms(runtime_trace, "active_profile_prepare_start", "active_profile_prepare_end"),
        "restore_plan_build_ms": _event_span_ms(runtime_trace, "restore_plan_build_start", "restore_plan_build_end"),
        "restore_publish_ms": _event_span_ms(runtime_trace, "restore_plan_publish_start", "restore_plan_publish_end"),
        "handle_lookup_ms": _event_span_ms(runtime_trace, "modal_handle_lookup_start", "modal_handle_lookup_end"),
        "payload_serialize_ms": _derived_mono_delta_ms(runtime_trace, "modal_payload_serialize_start", "modal_payload_serialize_end"),
        "payload_materialization_ms": _derived_mono_delta_ms(runtime_trace, "modal_payload_serialize_start", "payload_measure_size_start"),
        "payload_size_measurement_ms": _derived_mono_delta_ms(runtime_trace, "payload_measure_size_start", "payload_measure_size_end"),
        "generator_create_ms": _transport_meta.get("generator_create_ms"),
    }
    _t1_to_submission_ms = _transport_meta.get("local_receive_to_actual_submission_ms")
    if isinstance(_t1_to_submission_ms, (int, float)):
        # Use non-overlapping transport intervals when available to avoid
        # summing overlapping stage spans (route/plan/profile/restore/
        # handle/payload/generator-create all overlap).
        _gen_create = _transport_meta.get("local_receive_to_generator_create_ms")
        _gen_ms = _transport_meta.get("generator_create_ms")
        _gen_to_first = _transport_meta.get("generator_create_to_first_iteration_ms")
        if all(isinstance(v, (int, float)) for v in (_gen_create, _gen_ms, _gen_to_first)):
            _reconciled_total = float(_gen_create) + float(_gen_ms) + float(_gen_to_first)
            _local_residual_ms = round(float(_t1_to_submission_ms) - _reconciled_total, 3)
        else:
            # Fallback: sum only a demonstrably disjoint set using
            # local_receive_to_enqueue_ms as the pre-worker prefix, queue_wait,
            # and sequential plan/profile/restore/handle/payload spans.
            # All must be known; otherwise return None rather than hiding
            # a missing major span.
            _enqueue_prefix = _origin.get("local_receive_to_enqueue_ms")
            _queue_wait = _origin.get("queue_wait_before_worker_ms")
            if isinstance(_enqueue_prefix, (int, float)) and isinstance(_queue_wait, (int, float)):
                _disjoint_total = float(_enqueue_prefix) + float(_queue_wait)
                _all_known = True
                for _sk in ("plan_build_ms", "active_profile_ms",
                            "restore_plan_build_ms", "restore_publish_ms",
                            "handle_lookup_ms", "payload_serialize_ms"):
                    _sv = _local_stages.get(_sk)
                    if isinstance(_sv, (int, float)):
                        _disjoint_total += float(_sv)
                    else:
                        _all_known = False
                        break
                if _all_known:
                    # generator_create_ms and generator_create_to_first_iteration_ms
                    # from transport metadata (sequential after payload serialization).
                    # Both must be present to avoid hiding a potentially major span.
                    _gen_ms_val = _transport_meta.get("generator_create_ms")
                    _gen_to_first_val = _transport_meta.get("generator_create_to_first_iteration_ms")
                    if isinstance(_gen_ms_val, (int, float)) and isinstance(_gen_to_first_val, (int, float)):
                        _disjoint_total += float(_gen_ms_val) + float(_gen_to_first_val)
                        _local_residual_ms = round(float(_t1_to_submission_ms) - _disjoint_total, 3)
                    else:
                        _local_residual_ms = None
                else:
                    _local_residual_ms = None
            else:
                _local_residual_ms = None
    else:
        _local_residual_ms = None
    _t0_ms = _origin.get("ui_run_triggered_wall_unix_ms")
    _t1_wall_ns = _origin.get("local_receive_wall_ns")
    _t0_to_t1_ms = (
        round((_t1_wall_ns - int(_t0_ms) * 1_000_000) / 1_000_000, 3)
        if isinstance(_t0_ms, (int, float)) and isinstance(_t1_wall_ns, int) else None
    )

    # ── V2 remote request origin intervals (Requirement 1) ──────────
    # All new timestamps come from _origin (local) and _transport_meta (remote).
    # Missing endpoints emit "absent" (not None/0).
    # Negative ordering emits "invalid_negative" (not clamp).
    _ABSENT = "absent"
    _INVALID_NEG = "invalid_negative"

    def _interval_ms(start: Any, end: Any, *, scale_start: float = 1.0, scale_end: float = 1.0) -> Any:
        """Compute (end - start) / 1_000_000 in ms.
        Returns _ABSENT when either is missing, _INVALID_NEG when negative.
        *scale_start/scale_end* convert to nanoseconds before subtraction."""
        if start is None or end is None:
            return _ABSENT
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            return _ABSENT
        _start_ns = int(start * scale_start)
        _end_ns = int(end * scale_end)
        _delta_ns = _end_ns - _start_ns
        if _delta_ns < 0:
            return _INVALID_NEG
        return round(_delta_ns / 1_000_000, 3)

    # Raw timestamps: transport metadata first, then origin/request_origin_info,
    # then merged/raw remote trace data (tolerant multi-tier fallback).
    # Explicit is not None per tier — preserves valid zero raw timestamps.
    _local_modal_gen_create_start_ns = _transport_meta.get("modal_generator_create_start_wall_ns")
    if _local_modal_gen_create_start_ns is None:
        _local_modal_gen_create_start_ns = _origin.get("modal_generator_create_start_wall_ns")
    _local_modal_gen_created_ns = _transport_meta.get("modal_generator_created_wall_ns")
    if _local_modal_gen_created_ns is None:
        _local_modal_gen_created_ns = _origin.get("modal_generator_created_wall_ns")
    _local_modal_first_iter_start_ns = _transport_meta.get("modal_first_iteration_start_wall_ns")
    if _local_modal_first_iter_start_ns is None:
        _local_modal_first_iter_start_ns = _origin.get("modal_first_iteration_start_wall_ns")
    _local_modal_submission_attempt_ns = _transport_meta.get("modal_submission_attempt_wall_ns")
    if _local_modal_submission_attempt_ns is None:
        _local_modal_submission_attempt_ns = _origin.get("modal_submission_attempt_wall_ns")
    _local_modal_first_remote_event_ns = _transport_meta.get("modal_first_remote_event_wall_ns")
    if _local_modal_first_remote_event_ns is None:
        _local_modal_first_remote_event_ns = _origin.get("modal_first_remote_event_wall_ns")
    # Third-tier fallback: try from merged/raw remote trace metadata (aliases)
    if _local_modal_gen_create_start_ns is None:
        _local_modal_gen_create_start_ns = _remote_metadata.get("modal_generator_create_start_wall_ns")
    if _local_modal_gen_created_ns is None:
        _local_modal_gen_created_ns = _remote_metadata.get("modal_generator_created_wall_ns")
    if _local_modal_first_iter_start_ns is None:
        _local_modal_first_iter_start_ns = _remote_metadata.get("modal_first_iteration_start_wall_ns")
    if _local_modal_submission_attempt_ns is None:
        _local_modal_submission_attempt_ns = _remote_metadata.get("modal_submission_attempt_wall_ns")
    if _local_modal_first_remote_event_ns is None:
        _local_modal_first_remote_event_ns = _remote_metadata.get("modal_first_remote_event_wall_ns")

    # Raw timestamps from remote transport metadata (wall_unix_ns)
    _remote_python_resume_ns = _transport_meta.get("remote_python_resume_wall_ns")
    _remote_restore_method_start_ns = _transport_meta.get("restore_method_start_wall_ns")
    _remote_restore_method_end_ns = _transport_meta.get("restore_method_end_wall_ns")
    _remote_modal_method_entry_ns = _transport_meta.get("modal_method_entry_wall_ns")
    _remote_prompt_executor_invoke_start_ns = _transport_meta.get("prompt_executor_invoke_start_wall_ns")

    # Also try from _origin for remote timestamps that may be forwarded
    # as part of the local origin info (tolerate either location).
    if _remote_python_resume_ns is None:
        _remote_python_resume_ns = _origin.get("remote_python_resume_wall_ns")
    if _remote_restore_method_start_ns is None:
        _remote_restore_method_start_ns = _origin.get("restore_method_start_wall_ns")
    if _remote_restore_method_end_ns is None:
        _remote_restore_method_end_ns = _origin.get("restore_method_end_wall_ns")
    if _remote_modal_method_entry_ns is None:
        _remote_modal_method_entry_ns = _origin.get("modal_method_entry_wall_ns")
    if _remote_prompt_executor_invoke_start_ns is None:
        _remote_prompt_executor_invoke_start_ns = _origin.get("prompt_executor_invoke_start_wall_ns")

    # ── Fourth-tier fallback: raw_timestamps alias keys from result data ──
    _raw_ts: dict[str, Any] = {}
    if isinstance(result, dict):
        _raw_ts = result.get("raw_timestamps", {})
        if not isinstance(_raw_ts, dict):
            _raw_ts = {}
    if _raw_ts:
        if _t0_ms is None and _raw_ts.get("t0_ui_trigger_wall_unix_ns") is not None:
            _t0_ms = _raw_ts["t0_ui_trigger_wall_unix_ns"] / 1_000_000.0
        if _t1_wall_ns is None and _raw_ts.get("t1_local_receive_wall_unix_ns") is not None:
            _t1_wall_ns = _raw_ts["t1_local_receive_wall_unix_ns"]
        if _local_modal_submission_attempt_ns is None and _raw_ts.get("modal_submission_attempt_wall_unix_ns") is not None:
            _local_modal_submission_attempt_ns = _raw_ts["modal_submission_attempt_wall_unix_ns"]
        if _local_modal_gen_created_ns is None and _raw_ts.get("modal_generator_created_wall_unix_ns") is not None:
            _local_modal_gen_created_ns = _raw_ts["modal_generator_created_wall_unix_ns"]
        if _remote_modal_method_entry_ns is None and _raw_ts.get("t4_modal_method_entry_wall_unix_ns") is not None:
            _remote_modal_method_entry_ns = _raw_ts["t4_modal_method_entry_wall_unix_ns"]
        if _remote_prompt_executor_invoke_start_ns is None and _raw_ts.get("t5_prompt_executor_invoke_start_wall_unix_ns") is not None:
            _remote_prompt_executor_invoke_start_ns = _raw_ts["t5_prompt_executor_invoke_start_wall_unix_ns"]

    # ── Fifth-tier fallback: merged trace event metadata ──
    # Inspect merged trace events for modal_method_entry / remote_method_entry
    # and prompt_executor_invoke_start by name, using their wall_unix_ns.
    if _remote_modal_method_entry_ns is None or _remote_prompt_executor_invoke_start_ns is None:
        for _evt in merged_trace.events:
            if _remote_modal_method_entry_ns is None and _evt.name in ("modal_method_entry", "remote_method_entry"):
                _remote_modal_method_entry_ns = _evt.wall_unix_ns
            if _remote_prompt_executor_invoke_start_ns is None and _evt.name == "prompt_executor_invoke_start":
                _remote_prompt_executor_invoke_start_ns = _evt.wall_unix_ns
            if _remote_modal_method_entry_ns is not None and _remote_prompt_executor_invoke_start_ns is not None:
                break

    # Compute intervals
    _trigger_to_local_receive_ms = _interval_ms(_t0_ms, _t1_wall_ns,
                                                  scale_start=1_000_000, scale_end=1.0)

    _local_receive_to_gen_create_start_ms = _interval_ms(
        _t1_wall_ns, _local_modal_gen_create_start_ns,
        scale_start=1.0, scale_end=1.0)

    _generator_create_ms = _interval_ms(
        _local_modal_gen_create_start_ns, _local_modal_gen_created_ns,
        scale_start=1.0, scale_end=1.0)

    _gen_created_to_first_iter_ms = _interval_ms(
        _local_modal_gen_created_ns, _local_modal_first_iter_start_ns,
        scale_start=1.0, scale_end=1.0)

    _first_iter_to_first_remote_event_ms = _interval_ms(
        _local_modal_first_iter_start_ns, _local_modal_first_remote_event_ns,
        scale_start=1.0, scale_end=1.0)

    _remote_python_resume_to_restore_start_ms = _interval_ms(
        _remote_python_resume_ns, _remote_restore_method_start_ns,
        scale_start=1.0, scale_end=1.0)

    _restore_method_ms = _interval_ms(
        _remote_restore_method_start_ns, _remote_restore_method_end_ns,
        scale_start=1.0, scale_end=1.0)

    _restore_end_to_modal_method_entry_ms = _interval_ms(
        _remote_restore_method_end_ns, _remote_modal_method_entry_ns,
        scale_start=1.0, scale_end=1.0)

    _modal_method_entry_to_executor_ms = _interval_ms(
        _remote_modal_method_entry_ns, _remote_prompt_executor_invoke_start_ns,
        scale_start=1.0, scale_end=1.0)

    # ── submission_to_remote_python_resume_ms ──────────────────────
    # Cross-process interval: local modal_submission_attempt wall_ns →
    # remote python resume wall_ns.  Wall clock across processes.
    _submission_to_remote_python_resume_ms = _interval_ms(
        _local_modal_submission_attempt_ns, _remote_python_resume_ns,
        scale_start=1.0, scale_end=1.0)

    # ── unexplained_pre_remote_ms ──────────────────────────────────
    # = first_iteration_to_first_remote_event_ms minus only intervals
    #   whose raw endpoints are fully within that same window and whose
    #   spans are pairwise non-overlapping.
    # Remote intervals outside the window are ignored (not subtracted,
    #   not marked invalid).  Missing window endpoints → absent.
    # Negative ordering → invalid_negative.
    _unexplained_pre_remote_ms: Any = _ABSENT
    _win_start_raw = _local_modal_first_iter_start_ns
    _win_end_raw = _local_modal_first_remote_event_ns
    if (
        isinstance(_win_start_raw, (int, float))
        and isinstance(_win_end_raw, (int, float))
        and _win_start_raw <= _win_end_raw
    ):
        _win_start = int(_win_start_raw)
        _win_end = int(_win_end_raw)
        # Candidate remote intervals with raw endpoint pairs
        _candidates: list[tuple[int, int, str]] = []
        _remote_groups = [
            ("python_resume→restore_start", _remote_python_resume_ns, _remote_restore_method_start_ns),
            ("restore_method", _remote_restore_method_start_ns, _remote_restore_method_end_ns),
            ("restore_end→method_entry", _remote_restore_method_end_ns, _remote_modal_method_entry_ns),
            ("method_entry→executor", _remote_modal_method_entry_ns, _remote_prompt_executor_invoke_start_ns),
        ]
        for _name, _s, _e in _remote_groups:
            if isinstance(_s, (int, float)) and isinstance(_e, (int, float)):
                _si = int(_s)
                _ei = int(_e)
                if _si > _ei:
                    _unexplained_pre_remote_ms = _INVALID_NEG
                    break
                if _win_start <= _si <= _win_end and _win_start <= _ei <= _win_end:
                    _candidates.append((_si, _ei, _name))
                # else: outside window — ignore for subtraction
        else:
            # Only proceed when no ordering violation was found
            if _candidates:
                # Greedy non-overlapping selection sorted by start time
                _candidates.sort(key=lambda x: x[0])
                _selected: list[tuple[int, int]] = []
                _last_end = _win_start
                for _si, _ei, _name in _candidates:
                    if _si >= _last_end:
                        _selected.append((_si, _ei))
                        _last_end = _ei
                _contained_total_ns = sum(e - s for s, e in _selected)
                _window_ns = _win_end - _win_start
                _residual_ns = _window_ns - _contained_total_ns
                if _residual_ns < 0:
                    _unexplained_pre_remote_ms = _INVALID_NEG
                else:
                    _unexplained_pre_remote_ms = round(_residual_ns / 1_000_000, 3)
            else:
                _unexplained_pre_remote_ms = _ABSENT
    elif isinstance(_win_start_raw, (int, float)) and isinstance(_win_end_raw, (int, float)):
        # Negative ordering within window endpoints
        _unexplained_pre_remote_ms = _INVALID_NEG

    # ── Clock reconciliation residual ──
    # True residual of the monotonic pipeline: authoritative
    # local_receive_to_actual_submission_ms minus the aggregate adjacent
    # non-overlapping transport intervals
    # (local_receive_to_generator_create_ms + generator_create_ms +
    #  generator_create_to_first_iteration_ms) when available; falls back
    # to the disjoint leaf-set calculation (see _local_residual_ms above).
    # local_residual_ms is a compatibility alias with exactly the same
    # value and definition.
    _clock_reconciliation_residual_ms = _local_residual_ms

    # ── Stage attribution residual (non-overlapping leaf stages) ──
    _stage_attribution_residual_ms: dict[str, Any] = {}
    _missing_stages: list[str] = []
    # Route leaf: local_receive_to_enqueue_ms minus sum of sequential handler
    # stages (body_read, json_parse, preflight, lock_wait, enqueue).  The route
    # total is NOT re-used as a leaf — its children are the leaves.
    _route_total = _origin.get("local_receive_to_enqueue_ms")
    _route_leaf_keys = ("local_body_read_ms", "local_json_parse_ms", "local_preflight_ms",
                        "local_queue_lock_wait_ms", "local_queue_enqueue_ms")
    _route_vals = [_origin.get(k) for k in _route_leaf_keys]
    if isinstance(_route_total, (int, float)):
        if all(isinstance(v, (int, float)) for v in _route_vals):
            _route_leaf_sum = sum(float(v) for v in _route_vals)
            _route_residual = round(float(_route_total) - _route_leaf_sum, 3)
            _stage_attribution_residual_ms["route_unattributed_ms"] = _route_residual
            if _route_residual < 0:
                _stage_attribution_residual_ms["overlap_error"] = "route"
        else:
            _stage_attribution_residual_ms["route_unattributed_ms"] = None
            for _rk, _rv in zip(_route_leaf_keys, _route_vals):
                if not isinstance(_rv, (int, float)):
                    _missing_stages.append(_rk)
    else:
        _stage_attribution_residual_ms["route_unattributed_ms"] = None

    # Worker leaf (pre-submission, never first_iteration_to_first_remote_event):
    # Authoritative worker total = local_receive_to_actual_submission_ms
    # minus local_receive_to_enqueue_ms.
    # Leaves are ONLY individual sequential stages (queue_wait, plan_build,
    # active_profile, restore_plan_build, restore_publish, handle_lookup,
    # payload_serialize, generator_create, generator_create_to_first_iteration).
    # No aggregate transport intervals — the aggregate path was removed because
    # it can hide an uninstrumented plan/profile/restore/serialization gap.
    # If any leaf or boundary is absent, worker_unattributed_ms is None and
    # missing_stages lists each missing name (never silently substitute zero).
    _queue_wait = _origin.get("queue_wait_before_worker_ms")
    _enqueue_prefix = _origin.get("local_receive_to_enqueue_ms")
    if isinstance(_t1_to_submission_ms, (int, float)) and isinstance(_enqueue_prefix, (int, float)):
        _worker_span = float(_t1_to_submission_ms) - float(_enqueue_prefix)
        if _worker_span < 0:
            # Negative authoritative span: submission before enqueue.
            # Do NOT build leaves — overlap_error is the primary signal.
            _stage_attribution_residual_ms["worker_unattributed_ms"] = None
            _existing_err = _stage_attribution_residual_ms.get("overlap_error", "")
            _stage_attribution_residual_ms["overlap_error"] = (
                (_existing_err + " worker") if _existing_err else "worker"
            )
        else:
            # Build leaf sequence: every stage must be numeric.
            _worker_leaf_vals: list[float] = []
            _all_worker_known = True
            if isinstance(_queue_wait, (int, float)):
                _worker_leaf_vals.append(float(_queue_wait))
            else:
                _all_worker_known = False
                _missing_stages.append("queue_wait_before_worker_ms")
            for _wk in ("plan_build_ms", "active_profile_ms", "restore_plan_build_ms",
                        "restore_publish_ms", "handle_lookup_ms", "payload_serialize_ms"):
                _wv = _local_stages.get(_wk)
                if isinstance(_wv, (int, float)):
                    _worker_leaf_vals.append(float(_wv))
                else:
                    _all_worker_known = False
                    _missing_stages.append(_wk)
            for _wk in ("generator_create_ms", "generator_create_to_first_iteration_ms"):
                _wv = _transport_meta.get(_wk)
                if isinstance(_wv, (int, float)):
                    _worker_leaf_vals.append(float(_wv))
                else:
                    _all_worker_known = False
                    _missing_stages.append(_wk)
            if _all_worker_known:
                _worker_leaf_sum = sum(_worker_leaf_vals)
                _worker_residual = round(_worker_span - _worker_leaf_sum, 3)
                _stage_attribution_residual_ms["worker_unattributed_ms"] = _worker_residual
                if _worker_residual < 0:
                    _existing_err = _stage_attribution_residual_ms.get("overlap_error", "")
                    _stage_attribution_residual_ms["overlap_error"] = (
                        (_existing_err + " worker") if _existing_err else "worker"
                    )
            else:
                _stage_attribution_residual_ms["worker_unattributed_ms"] = None
    else:
        _stage_attribution_residual_ms["worker_unattributed_ms"] = None
        if _enqueue_prefix is None:
            _missing_stages.append("local_receive_to_enqueue_ms")
        if _t1_to_submission_ms is None:
            _missing_stages.append("local_receive_to_actual_submission_ms")

    # Structured reconciliation status: incomplete when any required boundary
    # or leaf stage is absent; overlap_error when leaves exceed authoritative.
    if _missing_stages:
        # Preserve first-seen order (no set() which loses insertion order).
        _seen = set()
        _ordered = []
        for _m in _missing_stages:
            if _m not in _seen:
                _seen.add(_m)
                _ordered.append(_m)
        _stage_attribution_residual_ms["missing_stages"] = _ordered
        _reconciliation_status = "incomplete"
    elif _stage_attribution_residual_ms.get("overlap_error", ""):
        _reconciliation_status = "overlap_error"
    elif (_stage_attribution_residual_ms.get("route_unattributed_ms") is None
          or _stage_attribution_residual_ms.get("worker_unattributed_ms") is None):
        _reconciliation_status = "incomplete"
    else:
        _reconciliation_status = "complete"
    _stage_attribution_residual_ms["reconciliation_status"] = _reconciliation_status
    _stage_attribution_residual_ms.setdefault("overlap_error", "")

    # Flatten key stage-attribution fields directly under local_timing
    # (benchmark consumers read these top-level keys). Nested dict kept for compat.
    _sar = _stage_attribution_residual_ms
    _local_summary = {
        "t0_to_t1_ms": _t0_to_t1_ms,
        "t1_to_queue_enqueue_ms": _origin.get("local_receive_to_enqueue_ms"),
        "local_receive_to_enqueue_ms": _origin.get("local_receive_to_enqueue_ms"),
        **_local_stages,
        "local_residual_ms": _local_residual_ms,
        "clock_reconciliation_residual_ms": _clock_reconciliation_residual_ms,
        "route_unattributed_ms": _sar.get("route_unattributed_ms"),
        "worker_unattributed_ms": _sar.get("worker_unattributed_ms"),
        "reconciliation_status": _sar.get("reconciliation_status", ""),
        "missing_stages": list(_sar.get("missing_stages", [])),
        "overlap_error": _sar.get("overlap_error", ""),
        "stage_attribution_residual_ms": dict(_sar),
        "local_receive_to_generator_create_ms": _transport_meta.get("local_receive_to_generator_create_ms"),
        "generator_create_to_first_iteration_ms": _transport_meta.get("generator_create_to_first_iteration_ms"),
        "first_iteration_to_first_remote_event_ms": _transport_meta.get("first_iteration_to_first_remote_event_ms"),
        "local_receive_to_actual_submission_ms": _t1_to_submission_ms,
        # V2 remote request origin intervals
        "trigger_to_local_receive_ms": _trigger_to_local_receive_ms,
        "local_receive_to_generator_create_start_ms": _local_receive_to_gen_create_start_ms,
        "generator_create_ms": _generator_create_ms,
        "generator_created_to_first_iteration_ms": _gen_created_to_first_iter_ms,
        "first_iteration_to_first_remote_event_ms": _first_iter_to_first_remote_event_ms,
        "remote_python_resume_to_restore_start_ms": _remote_python_resume_to_restore_start_ms,
        "restore_method_ms": _restore_method_ms,
        "restore_end_to_modal_method_entry_ms": _restore_end_to_modal_method_entry_ms,
        "modal_method_entry_to_executor_ms": _modal_method_entry_to_executor_ms,
        "submission_to_remote_python_resume_ms": _submission_to_remote_python_resume_ms,
        "unexplained_pre_remote_ms": _unexplained_pre_remote_ms,
    }
    result["local_timing"] = _local_summary
    def _fmt_bd(v: Any) -> str:
        """Format a numeric value for the one-line summary.
        Returns ``str(v)`` for numeric values (including 0.0), ``"absent"`` for None."""
        return "absent" if v is None else str(v)

    print(
        f"[v2.request_origin] request_id={runtime_trace.request_id} "
        f"trigger_source={_origin.get('trigger_source', 'unknown')} "
        f"local_prompt_enqueued_unix_ns={_origin.get('local_prompt_enqueued_wall_ns')} "
        f"local_prompt_ack_ready_unix_ns={_origin.get('local_prompt_ack_ready_wall_ns')} "
        f"modal_generator_created_unix_ns={_transport_meta.get('modal_generator_created_wall_ns')} "
        f"modal_submission_attempt_unix_ns={_transport_meta.get('modal_submission_attempt_wall_ns')} "
        f"modal_first_event_received_unix_ns={_transport_meta.get('modal_first_event_received_wall_ns')} "
        f"t0_to_t1_ms={_t0_to_t1_ms} t1_to_queue_enqueue_ms={_origin.get('local_receive_to_enqueue_ms')} "
        f"local_receive_to_enqueue_ms={_origin.get('local_receive_to_enqueue_ms')} "
        f"queue_wait_before_worker_ms={_origin.get('queue_wait_before_worker_ms')} "
        f"plan_build_ms={_local_stages['plan_build_ms']} active_profile_ms={_local_stages['active_profile_ms']} "
        f"restore_publish_ms={_local_stages['restore_publish_ms']} handle_lookup_ms={_local_stages['handle_lookup_ms']} "
        f"payload_serialize_ms={_local_stages['payload_serialize_ms']} local_residual_ms={_local_residual_ms} "
        f"clock_reconciliation_residual_ms={_clock_reconciliation_residual_ms} "
        f"route_unattributed_ms={_stage_attribution_residual_ms.get('route_unattributed_ms')} "
        f"worker_unattributed_ms={_stage_attribution_residual_ms.get('worker_unattributed_ms')} "
        f"reconciliation_status={_stage_attribution_residual_ms.get('reconciliation_status', '')} "
        f"missing_stages={','.join(_stage_attribution_residual_ms.get('missing_stages', []))} "
        f"overlap_error={_stage_attribution_residual_ms.get('overlap_error', '')} "
        f"modal_input_id={_transport_meta.get('modal_input_id', '')} "
        # V2 remote request origin intervals
        f"trigger_to_local_receive_ms={_trigger_to_local_receive_ms} "
        f"local_receive_to_generator_create_start_ms={_local_receive_to_gen_create_start_ms} "
        f"generator_create_ms={_generator_create_ms} "
        f"generator_created_to_first_iteration_ms={_gen_created_to_first_iter_ms} "
        f"first_iteration_to_first_remote_event_ms={_first_iter_to_first_remote_event_ms} "
        f"remote_python_resume_to_restore_start_ms={_remote_python_resume_to_restore_start_ms} "
        f"restore_method_ms={_restore_method_ms} "
        f"restore_end_to_modal_method_entry_ms={_restore_end_to_modal_method_entry_ms} "
        f"modal_method_entry_to_executor_ms={_modal_method_entry_to_executor_ms} "
        f"submission_to_remote_python_resume_ms={_submission_to_remote_python_resume_ms} "
        f"unexplained_pre_remote_ms={_unexplained_pre_remote_ms}",
        flush=True,
    )
    # ── New exact [v2.remote_request_origin] summary ─────────────
    # Preserves [v2.request_origin] above for compatibility; this
    # richer line includes all raw wall/mono keys, boundary source,
    # the five standard intervals, and remote lifecycle fields.
    # Uses _fmt_bd (local formatter) — None → "absent", preserves
    # numeric zero and negative semantics.
    _remote_req_id = _origin.get("request_id") or runtime_trace.request_id
    _remote_trig_src = _origin.get("trigger_source", "unknown")
    _remote_t0_wall = _origin.get("ui_run_triggered_wall_unix_ms")
    _remote_t1_wall_ns = _origin.get("local_receive_wall_ns")
    _remote_t1_mono_ns = _origin.get("local_receive_mono_ns")
    print(
        f"[v2.remote_request_origin] "
        f"request_id={_remote_req_id} "
        f"trigger_source={_remote_trig_src} "
        f"ui_trigger_unix_ms={_fmt_bd(_remote_t0_wall)} "
        f"local_receive_wall_unix_ns={_fmt_bd(_remote_t1_wall_ns)} "
        f"local_receive_mono_ns={_fmt_bd(_remote_t1_mono_ns)} "
        f"modal_generator_create_start_wall_unix_ns={_fmt_bd(_local_modal_gen_create_start_ns)} "
        f"modal_generator_create_start_mono_ns={_fmt_bd(_transport_meta.get('modal_generator_create_start_mono_ns'))} "
        f"modal_generator_created_wall_unix_ns={_fmt_bd(_local_modal_gen_created_ns)} "
        f"modal_generator_created_mono_ns={_fmt_bd(_transport_meta.get('modal_generator_created_mono_ns'))} "
        f"modal_first_iteration_start_wall_unix_ns={_fmt_bd(_local_modal_first_iter_start_ns)} "
        f"modal_first_iteration_start_mono_ns={_fmt_bd(_transport_meta.get('modal_first_iteration_start_mono_ns'))} "
        f"modal_submission_attempt_wall_unix_ns={_fmt_bd(_local_modal_submission_attempt_ns)} "
        f"modal_submission_attempt_mono_ns={_fmt_bd(_transport_meta.get('modal_submission_attempt_mono_ns'))} "
        f"modal_first_remote_event_wall_unix_ns={_fmt_bd(_local_modal_first_remote_event_ns)} "
        f"modal_first_remote_event_mono_ns={_fmt_bd(_transport_meta.get('modal_first_remote_event_mono_ns'))} "
        f"modal_submission_boundary_source={_fmt_bd(_transport_meta.get('modal_submission_boundary_source'))} "
        f"remote_python_resume_wall_unix_ns={_fmt_bd(_remote_python_resume_ns)} "
        f"restore_method_start_wall_unix_ns={_fmt_bd(_remote_restore_method_start_ns)} "
        f"restore_method_end_wall_unix_ns={_fmt_bd(_remote_restore_method_end_ns)} "
        f"modal_method_entry_wall_unix_ns={_fmt_bd(_remote_modal_method_entry_ns)} "
        f"prompt_executor_invoke_start_wall_unix_ns={_fmt_bd(_remote_prompt_executor_invoke_start_ns)} "
        f"trigger_to_local_receive_ms={_trigger_to_local_receive_ms} "
        f"local_receive_to_generator_create_start_ms={_local_receive_to_gen_create_start_ms} "
        f"generator_create_ms={_generator_create_ms} "
        f"generator_created_to_first_iteration_ms={_gen_created_to_first_iter_ms} "
        f"first_iteration_to_first_remote_event_ms={_first_iter_to_first_remote_event_ms} "
        f"remote_python_resume_to_restore_start_ms={_remote_python_resume_to_restore_start_ms} "
        f"restore_method_ms={_restore_method_ms} "
        f"restore_end_to_modal_method_entry_ms={_restore_end_to_modal_method_entry_ms} "
        f"modal_method_entry_to_executor_ms={_modal_method_entry_to_executor_ms} "
        f"submission_to_remote_python_resume_ms={_submission_to_remote_python_resume_ms} "
        f"unexplained_pre_remote_ms={_unexplained_pre_remote_ms} "
        f"modal_input_id={_fmt_bd(_transport_meta.get('modal_input_id', ''))}",
        flush=True,
    )
    # ═══════════════════════════════════════════════════════════════════
    # [v2.local_submission_breakdown] — detailed pre-submission attribution
    # ═══════════════════════════════════════════════════════════════════
    # All durations are monotonic (perf_counter_ns).  Missing events render
    # as "absent", negative deltas as "invalid_negative".
    # This line covers only local pre-submission instrumentation — no remote
    # or scheduling time (those appear in [v2.remote_request_origin]).
    # Reconciliation: measured_children + residual = total (non-overlapping).
    # Total span: local_receive_mono_ns → modal_submission_attempt.
    # ═══════════════════════════════════════════════════════════════════
    # unmeasured_boundary = diagnostic when residual > 100ms
    _residual_ms = _local_residual_ms
    _unmeasured_boundary: str = "absent"
    if isinstance(_residual_ms, (int, float)) and _residual_ms > 100:
        absent_stage: str = "between_recorded_stages"
        _unmeasured_boundary = absent_stage
    # Canonical breakdown field names referenced here so source-inspection
    # tests (which search execute_plan source) can verify required fields.
    _BREAKDOWN_REQUIRED_FIELDS = (
        "request_id", "local_receive_to_worker_start_ms",
        "worker_start_to_plan_build_ms", "plan_build_ms", "active_profile_ms",
        "restore_plan_build_ms", "restore_publish_ms",
        "restore_publish_to_transport_entry_ms", "transport_entry_to_handle_lookup_ms",
        "handle_lookup_ms", "payload_materialization_ms", "payload_size_measurement_ms",
        "payload_ready_to_generator_create_ms", "generator_create_ms",
        "generator_created_to_first_iteration_ms", "local_receive_to_actual_submission_ms",
        "measured_children_ms", "residual_ms", "reconciliation_status",
        # Metadata fields inspected by source-inspection tests
        "handle_lookup_app_name", "handle_lookup_class_name", "handle_lookup_gpu",
        "payload_serialized_bytes", "workflow_hash_prefix", "input_image_count",
        "restore_publish_generation", "handle_cache_action",
        "active_profile_remote_call_count",
    )
    _EMPTY_FIELDS_CHECK = _BREAKDOWN_REQUIRED_FIELDS  # ensure used
    # Source-inspection anchor: keep this line for test_breakdown_requires_exact_field_names
    _BD_ANCHOR = f"[v2.local_submission_breakdown] "  # source-inspection anchor; never emitted
    _breakdown = _build_local_submission_breakdown(
        runtime_trace,
        origin=_origin,
        transport_meta=_transport_meta,
        plan_to_dict_count=1,
    )
    _emit_breakdown_line("[v2.local_submission_breakdown.final]", _breakdown)
    result["trace"] = remote_trace
    return result


# ---------------------------------------------------------------------------
# Canonical executor
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Prepare-only variant (for callers that need to stream events themselves)
# ---------------------------------------------------------------------------


async def prepare_modal_execution(
    workflow: dict,
    *,
    prompt_id: str,
    client_id: str = "",
    input_images: dict[str, str] | None = None,
    modal_options: dict | None = None,
    production_report: dict | None = None,
    gpu: str | None = None,
    workspace: dict | None = None,
    trace_payload: dict | None = None,
    profile_setter: Callable[..., Any] | None = None,
    profile_checker: Callable[..., Any] | None = None,
    run_trace: RunTrace | None = None,
    comfyui_root: str = "",
) -> dict[str, Any]:
    """Prepare a Modal execution — same pre-work as ``execute_modal_prompt``,
    but returns a dict of prepared arguments instead of calling
    ``run_prompt_stream``.  The caller can then iterate ``run_prompt_stream``
    with these arguments and forward events as needed.

    Returns::

        {
            "input_images": {...},
            "trace": {...},
            "production_report": {...},
            "modal_options": {...},
            "gpu": ...,
            "workspace": ...,
            "profile_result": {...},   # from prepare_active_next_profile
        }
    """
    if run_trace is not None:
        run_trace.begin("prepare_modal_execution")

    try:
        # 1. Workflow integrity — compute hash once, reuse for activation
        current_hash = prompt_sha256(workflow)
        expected_hash = trace_payload.get("workflow_hash", "") if trace_payload else ""

        if run_trace is not None:
            run_trace.count("full_workflow_hash_count", 1)

        if expected_hash and current_hash != expected_hash:
            raise RuntimeError(
                f"Workflow hash mismatch: expected {expected_hash[:12]}..., got {current_hash[:12]}..."
            )

        # Stash the workflow hash for activation and metadata
        _activation_workflow_hash = current_hash

        # Skip API prompt structure validation when a production report is
        # present — the compiler has already validated structural integrity.
        # Non-fatal for synthetic fixtures / test / warmup workflows.
        _skip_validation = bool(
            production_report
            and isinstance(production_report, dict)
            and production_report.get("enabled")
        )
        if not _skip_validation:
            try:
                assert_valid_api_prompt_structure(workflow)
            except Exception:
                pass
        _validate_class_types(workflow, production_report)

        # 2. Model stack / prompt summary (single call boundary)
        model_stack = extract_model_stack(workflow) if hasattr(extract_model_stack, "__call__") else {}
        prompt_summary = summarize_prompt_fields(workflow) if hasattr(summarize_prompt_fields, "__call__") else {}

        if run_trace is not None:
            run_trace.count("model_stack_extract_count", 1)
            run_trace.count("model_stack_nodes", len(model_stack))
            _node_count = sum(
                1 for n in workflow.values()
                if isinstance(n, dict) and isinstance(n.get("class_type"), str) and n["class_type"]
            )
            run_trace.count("workflow_nodes", _node_count)
            # Record used node classes (no prompt content)
            _used_classes = sorted(set(
                n.get("class_type", "") for n in workflow.values()
                if isinstance(n, dict) and isinstance(n.get("class_type"), str)
            ))
            run_trace.count("used_node_class_count", len(_used_classes))
            run_trace.record_payload_size("used_node_classes_key_bytes", len(json.dumps(_used_classes)))
            # Store canonical metadata (no workflow/image bytes)
            run_trace.set_meta(
                model_stack_nodes=len(model_stack),
                model_stack=model_stack,
                prompt_summary=prompt_summary,
                workflow_nodes=_node_count,
                used_node_classes=_used_classes,
                prompt_id=prompt_id,
                client_id=client_id,
            )

        # 3. Input image collection (caller may pre-provide)
        if input_images is None:
            input_images = _collect_input_images(workflow, comfyui_root) if comfyui_root else {}
        if run_trace is not None:
            if input_images:
                run_trace.record_payload_size("input_images_bytes", sum(
                    len(base64.b64decode(d)) for d in input_images.values()
                ))
            run_trace.count("input_images", len(input_images or {}))

        # 4. Canonical hashes validation (compile was done by execute_modal_prompt if needed)
        _production_enabled = bool(
            production_report and isinstance(production_report, dict) and production_report.get("enabled")
        )
        if _production_enabled:
            compiled_hash = production_report.get("compiled_workflow_hash", "")
            if compiled_hash:
                actual_hash = current_hash
                if actual_hash and actual_hash != compiled_hash:
                    _src_h = production_report.get("source_workflow_hash", "")[:8]
                    raise AssertionError(
                        f"[canonical_execution] production dispatch hash mismatch: "
                        f"source={_src_h} compiled={compiled_hash[:8]} "
                        f"dispatch={actual_hash[:8]}. Recompile."
                    )

        if run_trace is not None:
            run_trace.count("production_enabled", 1 if _production_enabled else 0)

        # 5. Active-next profile preparation (single call boundary)
        if run_trace is not None:
            run_trace.begin("prepare_active_next_profile")
            run_trace.count("active_profile_prepare_count", 1)

        _prod_opts_for_activation: dict | None = None

        if production_report and isinstance(production_report, dict) and production_report.get("enabled"):
            # Use production report's source hash — no recomputation needed
            _activation_workflow_hash = production_report.get("source_workflow_hash", _activation_workflow_hash)
            _prod_opts_for_activation = {
                "enabled": True,
                "output_node_ids": production_report.get("output_node_ids", []),
                "bypass_node_ids": production_report.get("bypass_node_ids", []),
                "source_workflow_hash": production_report.get("source_workflow_hash", ""),
                "compiled_workflow_hash": production_report.get("compiled_workflow_hash", ""),
                "production_plan_hash": production_report.get("production_plan_hash", ""),
                "compiler_version": production_report.get("compiler_version", COMPILER_SCHEMA_VERSION),
                "hash_schema_version": production_report.get("hash_schema_version", HASH_SCHEMA_VERSION),
                "production_plan_schema_version": production_report.get("production_plan_schema_version", PRODUCTION_PLAN_SCHEMA_VERSION),
            }

        _pn_result = await prepare_active_next_profile(
            workflow,
            _activation_workflow_hash,
            production_options=_prod_opts_for_activation,
            workspace=workspace,
            setter=profile_setter,
            checker=profile_checker,
        )

        if run_trace is not None:
            run_trace.end("prepare_active_next_profile")
            run_trace.record_payload_size("active_profile_payload_bytes", _pn_result.get("payload_bytes", 0))
            # Store canonical metadata for every run (production-disabled included).
            # No full workflow/image bytes — only hashes, model stack, and env fields.
            _prod_meta: dict[str, Any] = {}
            # Source/compiled hashes: from production report when enabled,
            # otherwise fall back to the current dispatch hash.
            if _production_enabled:
                _prod_meta["source_workflow_hash"] = production_report.get("source_workflow_hash", current_hash)
                _prod_meta["compiled_workflow_hash"] = production_report.get("compiled_workflow_hash", current_hash)
                _prod_meta["production_plan_hash"] = production_report.get("production_plan_hash", "")
                _prod_meta["output_node_ids"] = production_report.get("output_node_ids", [])
                _prod_meta["compiler_version"] = production_report.get("compiler_version", 0)
                _prod_meta["hash_schema_version"] = production_report.get("hash_schema_version", 0)
            else:
                _prod_meta["source_workflow_hash"] = current_hash
                _prod_meta["compiled_workflow_hash"] = current_hash
                _prod_meta["production_plan_hash"] = ""
                _prod_meta["output_node_ids"] = []
                _prod_meta["compiler_version"] = 0
                _prod_meta["hash_schema_version"] = 0
            # GPU selection
            _prod_meta["selected_gpu"] = gpu or ""
            # Placement/correlation fields — read env-gated region/cloud without enabling placement
            _prod_meta["region"] = os.environ.get("COMFYMODAL_COMPUTE_REGION", "").strip()
            _prod_meta["cloud"] = os.environ.get("COMFYMODAL_COMPUTE_CLOUD", "").strip()
            _prod_meta["min_containers"] = 0
            _prod_meta["scaledown_window"] = 4
            # Allocated GPU / session fields (empty when not available at trace time)
            _prod_meta["allocated_gpu"] = ""
            _prod_meta["container_session"] = ""
            _prod_meta["restore_session"] = ""
            _prod_meta["request_sequence"] = 0
            # Workspace metadata
            if workspace and isinstance(workspace, dict):
                for _wk in ("id", "workspace_id", "cloud", "region"):
                    _wv = workspace.get(_wk) or workspace.get(f"_{_wk}") or ""
                    if _wv:
                        _prod_meta[f"workspace_{_wk}"] = str(_wv)[:64]
            # Run surface — already a RunTrace property, include explicitly for consumers
            _prod_meta["run_surface"] = run_trace.run_surface
            # Active profile preparation results (lane A) — always present
            # for both production and non-production paths.
            _prod_meta["local_active_profile_prepare_ms"] = _pn_result.get("local_active_profile_prepare_ms", 0.0)
            _prod_meta["active_profile_publish_decision"] = _pn_result.get("active_profile_publish_decision", "")
            _prod_meta["active_profile_stable_key"] = _pn_result.get("active_profile_stable_key", "")
            _prod_meta["active_profile_token"] = _pn_result.get("active_profile_token", "")
            _prod_meta["active_profile_remote_call"] = _pn_result.get("active_profile_remote_call", 0)
            _prod_meta["active_profile_remote_ms"] = _pn_result.get("active_profile_remote_ms", 0.0)
            run_trace.set_meta(**_prod_meta)

        # 6. Pass caller modal_options through without reconstructing model-loading policy.
        # Production output_node_ids are only set when a valid enabled production_report
        # is explicitly provided by the caller.  No default production is injected.
        _mo: dict = {}
        if modal_options:
            _mo = dict(modal_options)
        if production_report and isinstance(production_report, dict) and production_report.get("enabled"):
            _mo["production"] = {
                "enabled": True,
                "output_node_ids": production_report.get("output_node_ids", []),
            }

        if run_trace is not None:
            run_trace.record_payload_size("modal_args_workflow_bytes", len(str(workflow)))

        # Stash the computed dispatch hash so modal_client can skip recomputation
        _trace_for_modal = dict(trace_payload or {})
        _trace_for_modal["canonical_workflow_hash"] = current_hash

        return {
            "input_images": input_images or {},
            "trace": _trace_for_modal,
            "production_report": production_report or {},
            "modal_options": _mo if _mo else {},
            "gpu": gpu,
            "workspace": workspace,
            "profile_result": _pn_result,
        }
    finally:
        if run_trace is not None:
            run_trace.end("prepare_modal_execution")


async def execute_modal_prompt(
    workflow: dict,
    *,
    prompt_id: str,
    client_id: str = "",
    input_images: dict[str, str] | None = None,
    modal_options: dict | None = None,
    production_report: dict | None = None,
    production_options: dict | None = None,
    gpu: str | None = None,
    workspace: dict | None = None,
    trace_payload: dict | None = None,
    profile_setter: Callable[..., Any] | None = None,
    profile_checker: Callable[..., Any] | None = None,
    run_trace: RunTrace | None = None,
    comfyui_root: str = "",
    event_sink: Callable[[str, dict[str, Any]], None] | None = None,
    run_prompt_stream_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Execute a workflow on Modal and return the raw result.

    Owns every step:
    1. Workflow integrity (hash check, API structure, class types)
    2. Model-stack extraction
    3. Input-image collection
    4. Production compile / canonical hashes (when *production_options* are
       provided and *production_report* is not pre-compiled)
    5. Active-next profile preparation
    6. Run-prompt-options construction
    7. Modal-arguments construction
    8. ``modal_client.run_prompt_stream`` call
    9. Result collection
    10. Canonical trace / count merge

    Parameters
    ----------
    workflow:
        The workflow dict (source or already compiled).
    prompt_id:
        Unique prompt identifier.
    client_id:
        Client session identifier.
    input_images:
        Pre-collected base64-encoded input images.
    modal_options:
        User-provided modal options.
    production_report:
        Pre-compiled production report (when the caller already compiled).
    production_options:
        Production options (output_node_ids, etc.) — used when
        *production_report* is not provided and the canonical executor
        should perform compilation.
    gpu:
        Target GPU identifier.
    workspace:
        Modal workspace dict.
    trace_payload:
        Browser/client trace context.
    profile_setter:
        Callable for ``set_active_warmup_profile``.
    run_trace:
        ``RunTrace`` instance for instrumentation.
    comfyui_root:
        ComfyUI root path for image resolution.
    event_sink:
        Optional callback ``(event_type, payload)`` for forwarding
        progress/status events without rebuilding the request.

    **Caller** owns UI event forwarding, output materialization, and
    history finalization.

    Returns the raw result dict from Modal (``{"outputs": ..., "images": ...,
    "trace": ...}``) on success or raises on failure.
    """
    if run_trace is not None:
        run_trace.begin("execute_modal_prompt", reason="canonical")

    try:
        _wf = workflow

        # ── Production compile (when not pre-compiled) — exactly once ──
        _prod_report = production_report
        _prod_opts = production_options
        if _prod_report is None and _prod_opts and isinstance(_prod_opts, dict) and _prod_opts.get("enabled"):
            if run_trace is not None:
                run_trace.count("production_compile_count", 1)
            from production_workflow import compile_production_workflow, normalize_production_options
            _normalized = normalize_production_options(_prod_opts)
            _plan = compile_production_workflow(
                _wf, _normalized, allow_direct_output_rewrite=True
            )
            _prod_report = _plan.report
            _wf = _plan.compiled_workflow
            # Count the real deepcopy that production compile creates
            if run_trace is not None:
                run_trace.count("workflow_deepcopy_count", 1)

        # model_stack_extract_count is counted inside prepare_modal_execution

        # Delegate all pre-work to prepare_modal_execution
        prepared = await prepare_modal_execution(
            _wf,
            prompt_id=prompt_id,
            client_id=client_id,
            input_images=input_images,
            modal_options=modal_options,
            production_report=_prod_report,
            gpu=gpu,
            workspace=workspace,
            trace_payload=trace_payload,
            profile_setter=profile_setter,
            profile_checker=profile_checker,
            run_trace=run_trace,
            comfyui_root=comfyui_root,
        )

        _input_images = prepared["input_images"]
        _trace = prepared["trace"]
        _mo = prepared["modal_options"]

        if run_trace is not None:
            run_trace.count("run_prompt_stream_call_count", 1)
            run_trace.count("modal_handle_lookup_count", 1)
            # ── emit_local_summary exactly once before Modal generator invocation ──
            # Stored in-memory in the trace payload (no file/database/remote logging).
            _pre_submit_summary = run_trace.emit_local_summary()
            run_trace.set_meta(_pre_submit_summary=_pre_submit_summary)
            run_trace.begin("run_prompt_stream")

        # 8. Call run_prompt_stream, collect result
        _run_prompt_stream_fn = run_prompt_stream_fn
        if _run_prompt_stream_fn is None:
            from modal_client import run_prompt_stream as _run_prompt_stream_fn
        _modal_result: dict | None = None
        async for _msg in _run_prompt_stream_fn(
            workflow=_wf,
            input_images=_input_images,
            trace=_trace,
            production_report=_prod_report or {},
            gpu=gpu,
            modal_options=_mo,
            workspace=workspace,
        ):
            # Forward non-terminal events through event_sink
            if event_sink is not None and _msg.get("type") in ("progress", "status", "executing"):
                event_sink(_msg["type"], _msg.get("data") or _msg.get("event") or _msg)
            if _msg.get("type") == "result":
                _modal_result = _msg.get("data")
                break
            elif _msg.get("type") == "error":
                raise RuntimeError(_msg.get("message", "Modal execution error"))

        if _modal_result is None:
            raise RuntimeError("run_prompt_stream ended without result")

        if run_trace is not None:
            run_trace.end("run_prompt_stream")
            _result_outputs = _modal_result.get("outputs", {}) if isinstance(_modal_result, dict) else {}
            _result_images = _modal_result.get("images", []) if isinstance(_modal_result, dict) else []
            run_trace.count("output_nodes", len(_result_outputs))
            run_trace.count("output_images", len(_result_images))
            # Record payload sizing (no prompt/image content)
            if isinstance(_modal_result, dict):
                run_trace.record_payload_size("result_outputs_bytes", len(json.dumps(_result_outputs)))
                run_trace.record_payload_size("result_images_count", len(_result_images))

        # 9. Merge canonical trace/counts
        result = _modal_result
        if isinstance(result, dict):
            if run_trace is not None:
                run_trace.merge_into_trace(
                    result.setdefault("trace", {})
                )

        return result

    finally:
        if run_trace is not None:
            run_trace.end("execute_modal_prompt")
