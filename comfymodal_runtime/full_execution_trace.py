"""V2 full-execution trace engine.

Provides ``FullExecutionTraceSession``, ``ContainerResourceSampler``, and
wrapper-inventory utilities for comprehensive container-side tracing of
Model restore, prompt execution, and resource samples.

Fully inert when ``COMFYMODAL_V2_FULL_TRACE != '1'`` -- no VizTracer import,
no torch import, no session allocation, no file operations.
"""

from __future__ import annotations

import asyncio
import atexit
import copy
import contextlib
import contextvars
import functools
import gzip
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Any, Optional

log = logging.getLogger(__name__)

# ── Schema constant ──────────────────────────────────────────────────────────────────
SCHEMA_VERSION = "v2-full-trace/1"
_TRACE_BASE = "/tmp/comfymodal_full_trace"

# ── Internal test override hook ──────────────────────────────────────────────────────
_TEST_TRACE_BASE: str | None = None       # set by tests to redirect trace root
_TEST_PROC_SELF: str | None = None        # set by tests to mock /proc/self dir
_TEST_PROC_ROOT: str | None = None        # set by tests to mock /proc root
_TEST_CGROUP_V2: str | None = None        # set by tests to mock cgroup v2 dir

# ── Environment variable names (new v2 names) ────────────────────────────────────────
_ENV_ENABLE = "COMFYMODAL_V2_FULL_TRACE"
_ENV_ENTRIES = "COMFYMODAL_V2_FULL_TRACE_ENTRIES"
_ENV_RESOURCE_INTERVAL = "COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS"
_ENV_TORCH = "COMFYMODAL_V2_FULL_TRACE_TORCH"

# Legacy compat fallback names (private, checked only when new names are absent)
_LEGACY_ENV_ENTRIES = "FULL_TRACE_VIZTRACER_ENTRIES"
_LEGACY_ENV_RESOURCE_INTERVAL = "FULL_TRACE_RESOURCE_INTERVAL_MS"

_DEFAULT_VIZTRACER_ENTRIES = 8_000_000
_DEFAULT_MAX_STACK_DEPTH = 64
_DEFAULT_RESOURCE_INTERVAL_MS = 50

# A Golden request must use the tracer owned by its restore-scoped session,
# even when another VizTracer instance has subsequently replaced VizTracer's
# process-global registration.  A sentinel distinguishes an unbound caller
# (where the legacy optional global seam remains available) from an explicitly
# bound request whose missing tracer must fail closed.
_GOLDEN_TRACER_UNBOUND = object()

#: Chrome-trace category for the single authoritative Golden root span.  It must
#: match ``GOLDEN_ROOT_CATEGORY`` in ``golden_exhaustive_profile``; the offline
#: reporter reads this category to tell the authoritative root apart from the
#: executor function's own (identically categorised) Python-call record.
GOLDEN_ROOT_CATEGORY = "GOLDEN_ROOT"
_GOLDEN_TRACER: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "comfymodal_golden_tracer",
    default=_GOLDEN_TRACER_UNBOUND,
)

# Request-bound contract fields may be added to the top-level trace config by
# an adapter after construction.  Keep this seam deliberately narrow: these
# fields describe the trace contract, rather than providing a general-purpose
# mutable session state channel.
_TRACE_CONFIG_UPDATE_FIELDS: frozenset[str] = frozenset({
    "golden_profile_contract",
    "golden_profile_require_canonical_stages",
    "output_durability_mode",
    "required_canonical_stages",
    "canonical_stage_order",
})

# ── Raw file names ───────────────────────────────────────────────────────────────────
_REQUIRED_RAW_FILES: tuple[str, ...] = (
    "viztracer.json.gz",
    "torch_trace.json.gz",
    "resource_samples.jsonl.gz",
    "milestones.jsonl",
    "wrapper_snapshots.json",
    "session_events.jsonl",
    "trace_config.json",
    "runtime_result_summary.json",
)

_SUBDIRS: tuple[str, ...] = ("raw", "derived", "logs")

# ── Security redaction patterns (broadened) ──────────────────────────────────────────
_REDACT_KEYS: re.Pattern = re.compile(
    r"(MODAL[_\s]*TOKEN|MODAL[_\s]*TOKEN[_\s]*ID|MODAL[_\s]*TOKEN[_\s]*SECRET|"
    r"AUTHORIZATION|COOKIE|PASSWORD|API[_\s]*KEY|API[_\s]*SECRET|"
    r"ACCESS[_\s]*KEY|ACCESS[_\s]*TOKEN|ACCESS[_\s]*SECRET|"
    r"BEARER|SESSION[_\s]*KEY|SESSION[_\s]*TOKEN|SECRET|TOKEN|AUTH)",
    re.IGNORECASE,
)

_SANITIZE_FLAG_PATTERNS: tuple[str, ...] = (
    "--token", "-t", "--secret", "--password", "--key",
    "--api-key", "--api_key", "--access-key", "--access_key",
    "--bearer", "--auth", "--session-key", "--session_key",
    "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "COMFYMODAL_TOKEN",
)

# ── State machine ────────────────────────────────────────────────────────────────────
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "created": {"restore_tracing", "request_ready", "failed"},
    "request_ready": {"request_claimed", "failed"},
    "restore_tracing": {"restore_complete", "failed"},
    "restore_complete": {"request_claimed", "failed"},
    "request_claimed": {"request_tracing", "failed"},
    "request_tracing": {"trace_stopped", "failed"},
    "trace_stopped": set(),
    "failed": set(),
}

# ── Allowed wrapper inspection attrs ─────────────────────────────────────────────────
_ALLOWED_WRAPPER_ORIGINAL_ATTRS: frozenset[str] = frozenset({
    "__name__", "__qualname__", "__module__", "__doc__",
    "__code__", "__defaults__", "__kwdefaults__",
})
_ALLOWED_WRAPPER_PREFIXES: tuple[str, ...] = ("__wrapped__", "_wrap_", "_orig_")

# ── Known wrapper symbol names for direct discovery ──────────────────────────────────
_KNOWN_WRAPPER_SYMBOLS: tuple[str, ...] = (
    "comfy.utils.load_torch_file",
    "comfy.model_management.load_models_gpu",
    "comfy.model_management.cast_to_device",
    "comfy.model_patcher.ModelPatcher.__init__",
    "comfy.model_patcher.ModelPatcher.clone",
    "comfy.model_patcher.ModelPatcher.load",
    "comfy.model_patcher.ModelPatcher.patch_model",
    "comfy.model_patcher.ModelPatcher.patch_weight_to_device",
    "comfy.sd.load_clip",
    "comfy.sd.CLIP.encode_from_tokens",
    "nodes.CLIPTextEncode.encode",
    "nodes.VAELoader.load_vae",
    "nodes.UNETLoader.load_unet",
    "execution.PromptExecutor.execute",
    "execution.execute",
    "execution.get_input_data",
    "comfy.samplers.SAMPLER_SAMPLE",
)


# ═══════════════════════════════════════════════════════════════════════════════════
# Utility helpers
# ═══════════════════════════════════════════════════════════════════════════════════

def _redact_sensitive(value: Any, _depth: int = 0) -> Any:
    """Deep-redact sensitive keys from JSON-safe data.

    Matches keys that *contain* any of the broadened patterns (case-insensitive).
    """
    if _depth > 40:
        return "<max depth>"
    if isinstance(value, dict):
        return {
            k: "***REDACTED***" if _REDACT_KEYS.search(k) else _redact_sensitive(v, _depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive(v, _depth + 1) for v in value]
    return value


def _safe_json_serialize(value: Any, **kwargs: Any) -> str:
    """JSON-serialize with redaction and safe fallback."""
    redacted = _redact_sensitive(value)
    return json.dumps(redacted, default=_json_fallback, **kwargs)


def _json_fallback(obj: Any) -> str:
    """Fallback for types json.dumps cannot handle natively."""
    if isinstance(obj, (Path, datetime)):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if isinstance(obj, bytes):
        return f"<{len(obj)} bytes>"
    if hasattr(obj, "shape") and hasattr(obj, "dtype"):
        try:
            return f"<tensor shape={list(obj.shape)} dtype={obj.dtype}>"
        except Exception:
            return f"<{type(obj).__name__}>"
    try:
        return str(obj)
    except Exception:
        return "<unserializable>"


def _stable_hash(value: Any) -> str:
    """Deterministic SHA-256 hex digest of JSON-normalised *value*."""
    raw = json.dumps(
        _redact_sensitive(value),
        sort_keys=True,
        separators=(",", ":"),
        default=_json_fallback,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _env_int(name: str, default: int) -> int:
    """Read an int from env, falling back to *default* on missing/invalid."""
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int_chain(*names: str, default: int) -> int:
    """Try each env name in order, falling back to *default*."""
    for name in names:
        val = os.environ.get(name)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return default


@contextlib.contextmanager
def bind_golden_tracer(tracer: Any):
    """Bind one request's Golden spans to *tracer* until the scope exits.

    ``ContextVar`` state follows an async task across suspension without
    changing VizTracer's process-global registration.  Resetting the exact
    token in ``finally`` prevents the session-owned tracer from leaking into a
    later request or task.
    """
    token = _GOLDEN_TRACER.set(tracer)
    try:
        yield
    finally:
        _GOLDEN_TRACER.reset(token)


def thread_traced(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap *fn* so the thread running it installs this request's profile hook.

    ``VizTracer.enable_thread_tracing()`` only reaches threads created *after* it
    is called.  Golden's asyncio default executor already exists by the time a
    request runs, so ``asyncio.to_thread`` reuses worker threads that never
    receive the hook and produce no events at all.

    That is measurable, and it is not a code difference: on trace
    ``a4a4eaaf52fe456cbcd3583527068891`` golden_unet_load reports
    ``source_read_count = 184`` against golden_clip_load's 120, i.e. it drove
    *more* of the C0 source pool, yet recorded zero frames.  The asymmetry is
    the dispatch path -- clip loads via ``load_sync`` on the request task thread,
    while unet dispatches ``load`` -> ``asyncio.to_thread(_load_sync)`` onto the
    stale executor thread.  Everything under that call is plain Python
    (``wait_ready``, ``_read_message``, ``select.select``) and should be traced.

    ``sys.setprofile`` only ever affects the calling thread, so the hook has to be
    installed from inside the worker.  The tracer is resolved at call time, not
    captured, so the binding stays authoritative and an unbound tracer makes this
    a plain passthrough.  Tracing failures never escape into the load.
    """
    @functools.wraps(fn)
    def _run(*args: Any, **kwargs: Any) -> Any:
        try:
            tracer = _GOLDEN_TRACER.get()
            if tracer is _GOLDEN_TRACER_UNBOUND:
                _viz = sys.modules.get("viztracer")
                _get = getattr(_viz, "get_tracer", None)
                tracer = _get() if callable(_get) else None
            thread_hook = getattr(tracer, "threadtracefunc", None)
            if callable(thread_hook):
                sys.setprofile(thread_hook)
                # On Python 3.12+ VizTracer registers threads through
                # threading.settrace_all_threads instead of a bare setprofile,
                # so ask the tracer to register this thread too. On 3.11 it
                # simply re-sets the same profile function, which is harmless.
                reg = getattr(tracer, "enable_thread_tracing", None)
                if callable(reg):
                    reg()
        except BaseException:  # noqa: BLE001 - tracing must never break the load
            pass
        return fn(*args, **kwargs)

    # ``functools.wraps`` exposes __wrapped__, so ``inspect.signature`` follows
    # it to the real callable. Anything that introspects this object rather than
    # calling it -- GoldenModelTransport dispatches on the signature and rejects
    # the keyword arguments it sees -- must keep seeing the original, so the
    # wrapper's own signature is pinned rather than (*args, **kwargs).
    try:
        import inspect as _inspect
        _run.__signature__ = _inspect.signature(fn)  # type: ignore[attr-defined]
    except (TypeError, ValueError, ImportError):
        pass
    return _run


@contextlib.contextmanager
def golden_trace_span(name: str):
    """Record a Golden duration event on the request-bound VizTracer.

    When called outside a request binding, retain the compatibility seam of
    reading an already-registered global VizTracer.  Once bound, never consult
    ``viztracer.get_tracer()``: the binding is authoritative, including when it
    contains ``None`` so an unavailable session cannot accidentally capture on
    an unrelated global tracer.  This function never imports or starts
    VizTracer, and tracing failures never affect Golden execution.
    """
    event: Any = None
    try:
        tracer = _GOLDEN_TRACER.get()
        if tracer is _GOLDEN_TRACER_UNBOUND:
            tracer_module = sys.modules.get("viztracer")
            get_tracer = getattr(tracer_module, "get_tracer", None)
            tracer = get_tracer() if callable(get_tracer) else None
        log_event = getattr(tracer, "log_event", None)
        event = log_event(str(name)) if callable(log_event) else None
        enter = getattr(event, "__enter__", None)
        if not callable(enter):
            event = None
        else:
            enter()
    except BaseException:
        event = None
    try:
        yield
    finally:
        if event is not None:
            try:
                event.__exit__(None, None, None)
            except BaseException:
                pass


@contextlib.contextmanager
def golden_root_span(name: str):
    """Record THE authoritative Golden root span for one executor.

    Why this exists rather than another :func:`golden_trace_span`: in VizTracer
    1.1.1 ``VizEvent.__exit__`` hardcodes ``cat="FEE"``, so an explicit span and
    the automatic Python-call record of the same function are byte-for-byte
    indistinguishable once serialized.  An offline reader therefore cannot tell
    "the span the executor opened around its whole body" from "the call record of
    the function itself", and a build that emits both ends up with two candidate
    roots.

    Writing the same Chrome ``X`` event under a dedicated category makes the
    authoritative root unambiguous from the artifact alone.  It records no new
    measurement: the timestamps come from the tracer's own clock, so this adds no
    stopwatch and no per-function instrumentation.

    Inert when no tracer is bound, and a tracing failure never affects Golden.
    """
    tracer = _resolve_bound_tracer()
    start_us: float | None = None
    if tracer is not None:
        try:
            getts = getattr(tracer, "getts", None)
            add_raw = getattr(tracer, "add_raw", None)
            if callable(getts) and callable(add_raw):
                start_us = float(str(getts()))
            else:
                tracer = None
        except BaseException:
            tracer = None
    if tracer is None:
        yield
        return
    frame = _caller_frame()
    try:
        yield
    finally:
        try:
            duration = float(tracer.getts()) - float(start_us or 0.0)
            tracer.add_raw({
                "ph": "X",
                "name": f"{name} ({frame.f_code.co_filename}:{frame.f_lineno})",
                "ts": start_us,
                "dur": max(0.0, duration),
                "cat": GOLDEN_ROOT_CATEGORY,
            })
        except BaseException:
            pass


#: Frames that belong to the span plumbing itself, not to the Golden executor.
#: ``@contextlib.contextmanager`` inserts a ``wrapper`` frame per layer, and the
#: serial seam adds its own ``golden_root_span`` frame, so a naive
#: ``sys._getframe(1)`` would attribute the authoritative root to
#: ``contextlib.py`` or to the seam instead of to the executor that opened it.
_ROOT_SPAN_INTERNAL_FILES = ("contextlib.py", "full_execution_trace.py")
_ROOT_SPAN_INTERNAL_FUNCTIONS = frozenset({
    "golden_root_span", "wrapper", "helper",
})


def _caller_frame() -> Any:
    """Return the nearest frame outside the span plumbing itself."""
    try:
        frame: Any = sys._getframe(1)
    except Exception:  # pragma: no cover - no frame stack
        return sys._getframe(0)
    while frame is not None:
        filename = str(getattr(frame.f_code, "co_filename", "") or "")
        function = str(getattr(frame.f_code, "co_name", "") or "")
        is_internal = (
            function in _ROOT_SPAN_INTERNAL_FUNCTIONS
            or any(filename.endswith(name) for name in _ROOT_SPAN_INTERNAL_FILES)
        )
        if not is_internal:
            return frame
        frame = frame.f_back
    return sys._getframe(1)


def _resolve_bound_tracer() -> Any:
    """Return the request-bound tracer, or ``None``.

    Never consults an unrelated global tracer once a binding exists, and never
    imports VizTracer.
    """
    try:
        tracer = _GOLDEN_TRACER.get()
        if tracer is _GOLDEN_TRACER_UNBOUND:
            tracer_module = sys.modules.get("viztracer")
            get_tracer = getattr(tracer_module, "get_tracer", None)
            tracer = get_tracer() if callable(get_tracer) else None
        return tracer
    except BaseException:
        return None


def _sanitize_cmdline(cmdline: str) -> str:
    """Strip sensitive argument values from a process cmdline.

    Handles both null-separated (``/proc/pid/cmdline``) and space-separated.
    Broadened to cover more flag patterns.
    """
    separator = "\x00" if "\x00" in cmdline else " "
    parts = cmdline.split(separator)
    safe: list[str] = []
    skip_next = False
    for part in parts:
        if skip_next:
            skip_next = False
            safe.append("***")
            continue
        stripped = part.strip()
        matched = False
        for flag in _SANITIZE_FLAG_PATTERNS:
            if stripped.lower().startswith(flag.lower()):
                if "=" in stripped:
                    key, _ = stripped.split("=", 1)
                    safe.append(f"{key}=***")
                else:
                    safe.append(stripped)
                    skip_next = True
                matched = True
                break
        if matched:
            continue
        safe.append(part)
    return separator.join(safe)


def _safe_repr(value: Any) -> str:
    """Repr that never leaks tensor data, model contents, or prompt text."""
    if hasattr(value, "shape") and hasattr(value, "dtype"):
        try:
            return f"<tensor shape={list(value.shape)} dtype={value.dtype}>"
        except Exception:
            return f"<{type(value).__name__}>"
    if isinstance(value, (str, int, float, bool, type(None))):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return f"<{len(value)} items>" if len(value) > 5 else repr(value)
    if isinstance(value, dict):
        return f"<{len(value)} keys>"
    return f"<{type(value).__name__}>"


def _is_jsonable(value: Any) -> bool:
    """Check whether *value* can be natively JSON-serialized."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_jsonable(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_jsonable(v) for k, v in value.items())
    return False


def _safe_json_value(value: Any, _depth: int = 0) -> Any:
    """Convert a value to a JSON-safe form, dropping unsafe types.

    Scalars pass through.  Containers are recursed.  Non-JSONable objects
    are replaced with a safe type-name string.
    """
    if _depth > 40:
        return "<max depth>"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_json_value(v, _depth + 1) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_json_value(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (Path, datetime)):
        return str(value)
    if hasattr(value, "shape") and hasattr(value, "dtype"):
        try:
            return f"<tensor shape={list(value.shape)} dtype={value.dtype}>"
        except Exception:
            return f"<{type(value).__name__}>"
    try:
        return f"<{type(value).__name__}>"
    except Exception:
        return "<unknown>"


def _numeric_or_none(raw: str) -> int | None:
    """Parse an integer from *raw*; return None on failure."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════════
# Cgroup v2 resolution helpers
# ═══════════════════════════════════════════════════════════════════════════════════

def _get_proc_self() -> Path:
    """Return /proc/self path, respecting test override."""
    if _TEST_PROC_SELF:
        return Path(_TEST_PROC_SELF)
    return Path("/proc/self")


def _get_proc_root() -> Path:
    """Return /proc root, respecting test override."""
    if _TEST_PROC_ROOT:
        return Path(_TEST_PROC_ROOT)
    return Path("/proc")


def _resolve_cgroup_v2_path() -> Path | None:
    """Resolve the cgroup v2 directory from mountinfo + cgroup entries.

    Returns None when not in a cgroup v2 environment or on error.
    """
    # Test override
    if _TEST_CGROUP_V2:
        return Path(_TEST_CGROUP_V2)

    proc_self = _get_proc_self()
    try:
        mountinfo_path = proc_self / "mountinfo"
        if not mountinfo_path.exists():
            return None
        cgroup_mount_point: str | None = None
        for line in mountinfo_path.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 5:
                mount_point = parts[4]
                # Look for cgroup2 or cgroup v2 unified mount at /sys/fs/cgroup
                rest = " ".join(parts[5:])
                if "cgroup2" in rest or ("cgroup" in rest and mount_point == "/sys/fs/cgroup"):
                    cgroup_mount_point = mount_point
                    break
        if not cgroup_mount_point:
            return None

        cgroup_file = proc_self / "cgroup"
        if not cgroup_file.exists():
            return None
        lines = cgroup_file.read_text().strip().splitlines()
        if not lines:
            return None
        # Last line (or only line for v2): "0::/path"
        cg_line = lines[-1]
        parts = cg_line.split(":")
        if len(parts) < 3:
            return None
        cg_rel_path = parts[-1]  # e.g., "/system.slice/docker-xxx.scope"
        return Path(cgroup_mount_point + cg_rel_path)
    except (OSError, IndexError, ValueError):
        return None


def _read_cgroup_stat(cgroup_dir: Path) -> dict[str, int | None]:
    """Read cpu.stat from a cgroup v2 directory.

    Returns dict with keys: usage_usec, user_usec, system_usec,
    nr_periods, nr_throttled, throttled_usec (all nullable).
    """
    result: dict[str, int | None] = {
        "usage_usec": None, "user_usec": None, "system_usec": None,
        "nr_periods": None, "nr_throttled": None, "throttled_usec": None,
    }
    try:
        stat_path = cgroup_dir / "cpu.stat"
        if stat_path.exists():
            for line in stat_path.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0]
                    val = _numeric_or_none(parts[1])
                    if key in result:
                        result[key] = val
    except OSError:
        pass
    return result


def _read_cgroup_memory(cgroup_dir: Path) -> dict[str, int | None]:
    """Read memory.current, memory.peak, and memory.stat from cgroup v2.

    Returns dict with keys: current_bytes, peak_bytes, anon_bytes,
    file_bytes, inactive_file_bytes, active_file_bytes, pgfault, pgmajfault.
    """
    result: dict[str, int | None] = {
        "current_bytes": None, "peak_bytes": None,
        "anon_bytes": None, "file_bytes": None,
        "inactive_file_bytes": None, "active_file_bytes": None,
        "pgfault": None, "pgmajfault": None,
    }
    try:
        cur = cgroup_dir / "memory.current"
        if cur.exists():
            result["current_bytes"] = _numeric_or_none(cur.read_text().strip())

        peak = cgroup_dir / "memory.peak"
        if peak.exists():
            result["peak_bytes"] = _numeric_or_none(peak.read_text().strip())

        stat = cgroup_dir / "memory.stat"
        if stat.exists():
            for line in stat.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    k, v = parts[0], _numeric_or_none(parts[1])
                    mapping = {
                        "anon": "anon_bytes",
                        "file": "file_bytes",
                        "inactive_file": "inactive_file_bytes",
                        "active_file": "active_file_bytes",
                        "pgfault": "pgfault",
                        "pgmajfault": "pgmajfault",
                    }
                    if k in mapping:
                        result[mapping[k]] = v
    except OSError:
        pass
    return result


def _read_cgroup_io(cgroup_dir: Path) -> dict[str, int | None]:
    """Read io.stat from cgroup v2.

    Returns dict with keys: rbytes, wbytes (aggregated across devices).
    """
    result: dict[str, int | None] = {"rbytes": None, "wbytes": None}
    try:
        io_path = cgroup_dir / "io.stat"
        if io_path.exists():
            total_rbytes = 0
            total_wbytes = 0
            for line in io_path.read_text().splitlines():
                # Format: "major:minor rbytes=123 wbytes=456 rios=..."
                for token in line.split():
                    if "=" in token:
                        k, v_str = token.split("=", 1)
                        v = _numeric_or_none(v_str) or 0
                        if k == "rbytes":
                            total_rbytes += v
                        elif k == "wbytes":
                            total_wbytes += v
            result["rbytes"] = total_rbytes
            result["wbytes"] = total_wbytes
    except OSError:
        pass
    return result


# ═══════════════════════════════════════════════════════════════════════════════════
# Proc parsing helpers
# ═══════════════════════════════════════════════════════════════════════════════════

def _parse_stat_fields(stat_text: str) -> dict[str, int | None]:
    """Parse relevant fields from /proc/pid/stat.

    Handles the parenthesised comm field.  Returns:
      utime, stime, minflt, majflt, num_threads, rss
    All nullable.
    """
    result: dict[str, int | None] = {
        "utime": None, "stime": None, "minflt": None, "majflt": None,
        "num_threads": None, "rss": None,
    }
    try:
        # Find the closing paren of the comm field
        rparen = stat_text.rfind(")")
        if rparen == -1:
            return result
        rest = stat_text[rparen + 2:].split()  # skip ") "
        if len(rest) < 24:
            return result
        # After the comm field, rest is space-split. Fields (0-indexed):
        # 0:state, 1:ppid, ..., 7:minflt, 8:cminflt, 9:majflt, 10:cmajflt,
        # 11:utime, 12:stime, ..., 17:num_threads, ..., 21:rss
        result["minflt"] = _numeric_or_none(rest[7]) if len(rest) > 7 else None
        result["majflt"] = _numeric_or_none(rest[9]) if len(rest) > 9 else None
        result["utime"] = _numeric_or_none(rest[11]) if len(rest) > 11 else None
        result["stime"] = _numeric_or_none(rest[12]) if len(rest) > 12 else None
        result["num_threads"] = _numeric_or_none(rest[17]) if len(rest) > 17 else None
        result["rss"] = _numeric_or_none(rest[21]) if len(rest) > 21 else None
    except (IndexError, ValueError):
        pass
    return result


def _read_proc_io(io_path: Path) -> dict[str, int | None]:
    """Read IO stats from /proc/pid/io."""
    result: dict[str, int | None] = {
        "read_bytes": None, "write_bytes": None, "cancelled_write_bytes": None,
    }
    try:
        if io_path.exists():
            for line in io_path.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    val = _numeric_or_none(parts[1])
                    if key in result:
                        result[key] = val
    except OSError:
        pass
    return result


def _read_proc_comm(comm_path: Path) -> str | None:
    """Read a trimmed comm value."""
    try:
        if comm_path.exists():
            return comm_path.read_text().strip()
    except OSError:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════════
# ContainerResourceSampler
# ═══════════════════════════════════════════════════════════════════════════════════

class ContainerResourceSampler:
    """Periodically samples container resource metrics.

    Each sample is a flat JSON object with nullable top-level cgroup/memory/io
    fields plus process and thread inventory lists.  Written incrementally
    gzipped JSONL to ``resource_samples.jsonl.gz``.

    Parameters
    ----------
    trace_dir:
        Session base directory (raw/ subdirectory will be used).
    interval_ms:
        Sampling interval in milliseconds.
    session_phase:
        Phase label included in each sample (set by session).
    """

    def __init__(
        self,
        trace_dir: str,
        interval_ms: int | None = None,
        session_phase: str = "unknown",
    ) -> None:
        self._trace_dir = Path(trace_dir)
        self._interval_s = (interval_ms or _env_int_chain(
            _ENV_RESOURCE_INTERVAL, _LEGACY_ENV_RESOURCE_INTERVAL,
            default=_DEFAULT_RESOURCE_INTERVAL_MS,
        )) / 1000.0
        self._session_phase = session_phase
        self._pid = os.getpid()
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._sample_count = 0
        self._gz_path: Path | None = None
        self._gz_file: Any = None
        self._stopped = threading.Event()
        self._stop_timed_out = False
        # Resolve cgroup v2 path once at init
        self._cgroup_dir = _resolve_cgroup_v2_path()

    # ── Lifecycle ────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stopped.clear()
        raw_dir = self._trace_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        self._gz_path = raw_dir / "resource_samples.jsonl.gz"
        self._gz_file = gzip.open(self._gz_path, "wt", encoding="utf-8")
        self._thread = threading.Thread(target=self._run, daemon=True, name="res-sampler")
        self._thread.start()

    def stop(self, *, timeout: float = 0.5) -> dict[str, Any]:
        self._running = False
        self._stopped.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.0, float(timeout)))
        self._stop_timed_out = bool(thread is not None and thread.is_alive())
        if not self._stop_timed_out:
            self._thread = None
        with self._lock:
            self._close_gz()
        return {
            "sample_count": self._sample_count,
            "path": str(self._gz_path) if self._gz_path else "",
            "thread_alive": self._stop_timed_out,
        }

    def _close_gz(self) -> None:
        if self._gz_file is not None:
            try:
                self._gz_file.close()
            except Exception:
                pass
            self._gz_file = None

    def close(self) -> None:
        self.stop()

    # ── Sampling loop ────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            while self._running and not self._stopped.is_set():
                try:
                    sample = self._collect_sample()
                    with self._lock:
                        if self._gz_file is not None and not self._gz_file.closed:
                            self._gz_file.write(json.dumps(sample, default=_json_fallback) + "\n")
                            self._gz_file.flush()
                            self._sample_count += 1
                except Exception as exc:
                    log.warning("ResourceSampler sample error: %s", exc)
                if self._stopped.wait(self._interval_s):
                    break
        finally:
            self._stopped.set()

    def collect_sample(self) -> dict[str, Any]:
        """Collect one resource sample snapshot immediately (thread-safe)."""
        with self._lock:
            return self._collect_sample()

    # ── Core sample collection ───────────────────────────────────────────────────────

    def _collect_sample(self) -> dict[str, Any]:
        sample: dict[str, Any] = {
            "wall_unix_ns": int(time.time() * 1_000_000_000),
            "monotonic_ns": time.monotonic_ns(),
            "session_phase": self._session_phase,
        }
        self._add_cgroup_fields(sample)
        self._add_memory_fields(sample)
        self._add_io_fields(sample)
        sample["process_inventory"] = self._read_process_inventory()
        sample["thread_inventory"] = self._read_thread_inventory()
        return sample

    def _add_cgroup_fields(self, sample: dict[str, Any]) -> None:
        if self._cgroup_dir is None:
            sample.update({
                "cgroup_cpu_usage_usec": None,
                "cgroup_user_usec": None,
                "cgroup_system_usec": None,
                "cgroup_nr_periods": None,
                "cgroup_nr_throttled": None,
                "cgroup_throttled_usec": None,
            })
            return
        stat = _read_cgroup_stat(self._cgroup_dir)
        sample.update({
            "cgroup_cpu_usage_usec": stat.get("usage_usec"),
            "cgroup_user_usec": stat.get("user_usec"),
            "cgroup_system_usec": stat.get("system_usec"),
            "cgroup_nr_periods": stat.get("nr_periods"),
            "cgroup_nr_throttled": stat.get("nr_throttled"),
            "cgroup_throttled_usec": stat.get("throttled_usec"),
        })

    def _add_memory_fields(self, sample: dict[str, Any]) -> None:
        if self._cgroup_dir is None:
            sample.update({
                "memory_current_bytes": None,
                "memory_peak_bytes": None,
                "memory_stat_anon_bytes": None,
                "memory_stat_file_bytes": None,
                "memory_stat_inactive_file_bytes": None,
                "memory_stat_active_file_bytes": None,
                "memory_stat_pgfault": None,
                "memory_stat_pgmajfault": None,
            })
            return
        mem = _read_cgroup_memory(self._cgroup_dir)
        sample.update({
            "memory_current_bytes": mem.get("current_bytes"),
            "memory_peak_bytes": mem.get("peak_bytes"),
            "memory_stat_anon_bytes": mem.get("anon_bytes"),
            "memory_stat_file_bytes": mem.get("file_bytes"),
            "memory_stat_inactive_file_bytes": mem.get("inactive_file_bytes"),
            "memory_stat_active_file_bytes": mem.get("active_file_bytes"),
            "memory_stat_pgfault": mem.get("pgfault"),
            "memory_stat_pgmajfault": mem.get("pgmajfault"),
        })

    def _add_io_fields(self, sample: dict[str, Any]) -> None:
        if self._cgroup_dir is None:
            sample.update({
                "io_rbytes": None,
                "io_wbytes": None,
            })
            return
        io = _read_cgroup_io(self._cgroup_dir)
        sample.update({
            "io_rbytes": io.get("rbytes"),
            "io_wbytes": io.get("wbytes"),
        })

    # ── Process inventory ────────────────────────────────────────────────────────────

    def _read_process_inventory(self) -> list[dict[str, Any]]:
        """Enumerate /proc/<pid> directories and collect per-process stats."""
        inventory: list[dict[str, Any]] = []
        proc_root = _get_proc_root()
        try:
            for entry in proc_root.iterdir():
                if not entry.is_dir() or not entry.name.isdigit():
                    continue
                pid = int(entry.name)
                info = self._read_single_process(entry, pid)
                if info is not None:
                    inventory.append(info)
        except OSError:
            pass
        return inventory

    def _read_single_process(self, proc_dir: Path, pid: int) -> dict[str, Any] | None:
        """Read stats for a single process from its /proc/<pid> directory."""
        try:
            stat_path = proc_dir / "stat"
            if not stat_path.exists():
                return None

            stat_text = stat_path.read_text()
            fields = _parse_stat_fields(stat_text)

            status_path = proc_dir / "status"
            comm: str | None = None
            state: str | None = None
            ppid: int | None = None
            if status_path.exists():
                for line in status_path.read_text().splitlines():
                    if line.startswith("Name:"):
                        comm = line.split(":", 1)[1].strip()
                    elif line.startswith("State:"):
                        state = line.split(":", 1)[1].strip()
                    elif line.startswith("PPid:"):
                        ppid = _numeric_or_none(line.split(":", 1)[1].strip())

            if comm is None:
                comm = _read_proc_comm(proc_dir / "comm")

            cmdline_path = proc_dir / "cmdline"
            sanitized_cmdline: str | None = None
            if cmdline_path.exists():
                sanitized_cmdline = _sanitize_cmdline(cmdline_path.read_text())

            io = _read_proc_io(proc_dir / "io")

            return {
                "pid": pid,
                "ppid": ppid,
                "comm": comm,
                "sanitized_cmdline": sanitized_cmdline,
                "state": state,
                "user_ticks": fields.get("utime"),
                "system_ticks": fields.get("stime"),
                "minor_faults": fields.get("minflt"),
                "major_faults": fields.get("majflt"),
                "rss_pages": fields.get("rss"),
                "thread_count": fields.get("num_threads"),
                "read_bytes": io.get("read_bytes"),
                "write_bytes": io.get("write_bytes"),
                "cancelled_write_bytes": io.get("cancelled_write_bytes"),
            }
        except (OSError, ValueError) as exc:
            # Return a partial error record rather than None
            return {
                "pid": pid,
                "error": str(exc),
            }

    # ── Thread inventory ─────────────────────────────────────────────────────────────

    def _read_thread_inventory(self) -> list[dict[str, Any]]:
        """Enumerate /proc/self/task/<tid> directories for the calling process."""
        inventory: list[dict[str, Any]] = []
        proc_self = _get_proc_self()
        task_dir = proc_self / "task"
        try:
            if not task_dir.exists():
                return inventory
            for entry in task_dir.iterdir():
                if not entry.is_dir() or not entry.name.isdigit():
                    continue
                tid = int(entry.name)
                info = self._read_single_thread(entry, tid)
                if info is not None:
                    inventory.append(info)
        except OSError:
            pass
        return inventory

    def _read_single_thread(self, task_dir: Path, tid: int) -> dict[str, Any] | None:
        """Read stats for a single thread from a /proc/self/task/<tid> dir."""
        try:
            stat_path = task_dir / "stat"
            if not stat_path.exists():
                return None
            stat_text = stat_path.read_text()
            fields = _parse_stat_fields(stat_text)

            # For threads, comm comes from stat or /proc/<tid>/comm (same as task)
            comm = _read_proc_comm(task_dir / "comm")

            status_path = task_dir / "status"
            state: str | None = None
            if status_path.exists():
                for line in status_path.read_text().splitlines():
                    if line.startswith("State:"):
                        state = line.split(":", 1)[1].strip()
                        break

            return {
                "tid": tid,
                "comm": comm,
                "state": state,
                "user_ticks": fields.get("utime"),
                "system_ticks": fields.get("stime"),
                "minor_faults": fields.get("minflt"),
                "major_faults": fields.get("majflt"),
            }
        except (OSError, ValueError):
            return None


# ═══════════════════════════════════════════════════════════════════════════════════
# Wrapper / symbol discovery
# ═══════════════════════════════════════════════════════════════════════════════════

def _resolve_qualified_callable(qualified_name: str) -> Any:
    """Resolve a dotted qualified name to its callable, or None.

    Walks ``sys.modules`` for increasingly deeper module prefixes,
    then traverses remaining attribute segments.  Never invokes
    descriptors or monkeypatches.
    """
    parts = qualified_name.split(".")
    if len(parts) < 2:
        return None
    for i in range(1, len(parts)):
        module_name = ".".join(parts[:i])
        mod = sys.modules.get(module_name)
        if mod is None:
            continue
        obj: Any = mod
        ok = True
        for attr in parts[i:]:
            try:
                obj = getattr(obj, attr, None)
            except Exception:
                obj = None
            if obj is None:
                ok = False
                break
        if ok and callable(obj):
            return obj
    return None


def _discover_wrapper_symbols() -> dict[str, Any]:
    """Try to discover known wrapper callables by qualified name resolution.

    Returns ``{qualified_name: callable_or_None}``.  Does not monkeypatch
    or invoke descriptors.
    """
    result: dict[str, Any] = {}
    for qualified_name in _KNOWN_WRAPPER_SYMBOLS:
        result[qualified_name] = _resolve_qualified_callable(qualified_name)
    return result


def _inspect_wrapper_callable(func: Callable | None, stage: str = "") -> dict[str, Any]:
    """Inspect one wrapper callable with full metadata.

    Traverses ``__wrapped__`` chain (max 32) with cycle detection.
    Records sentinel attributes, closure callable references, known original
    attributes, chain metadata.
    """
    if func is None:
        return {
            "available": False,
            "callable_object_id": None,
            "type": None,
        }

    info: dict[str, Any] = {
        "available": True,
        "callable_object_id": id(func),
        "type": type(func).__name__,
        "module": getattr(func, "__module__", None),
        "qualname": getattr(func, "__qualname__", None),
        "source_file": None,
        "source_first_line": None,
    }

    # Source location
    try:
        code = getattr(func, "__code__", None)
        if code is not None:
            info["source_file"] = getattr(code, "co_filename", None)
            info["source_first_line"] = getattr(code, "co_firstlineno", None)
    except Exception:
        pass

    # Allowed original attrs
    for attr in _ALLOWED_WRAPPER_ORIGINAL_ATTRS:
        try:
            val = getattr(func, attr, None)
            if val is not None:
                if attr == "__code__":
                    info[attr] = _safe_repr(val)
                else:
                    info[attr] = str(val)
        except Exception:
            pass

    # Sentinel attributes (known wrapper markers like __wrapped__, _is_wrapper, etc.)
    sentinel_attrs: dict[str, str] = {}
    try:
        for k, v in vars(func).items():
            for prefix in _ALLOWED_WRAPPER_PREFIXES:
                if k.startswith(prefix):
                    sentinel_attrs[k] = str(type(v).__name__)
                    break
    except Exception:
        pass
    if sentinel_attrs:
        info["sentinel_attributes"] = sentinel_attrs

    # Traverse __wrapped__ chain
    chain: list[str] = []
    visited: set[int] = set()
    current: Any = func
    depth = 0
    chain_cycle_detected = False
    while depth < 32:
        obj_id = id(current)
        if obj_id in visited:
            chain.append(f"<cycle id={obj_id}>")
            chain_cycle_detected = True
            break
        visited.add(obj_id)
        wrapped = getattr(current, "__wrapped__", None)
        if wrapped is None or wrapped is current:
            break
        wrapped_name = getattr(wrapped, "__qualname__", None) or getattr(wrapped, "__name__", "")
        chain.append(f"{type(wrapped).__name__} {wrapped_name}")
        current = wrapped
        depth += 1
    info["wrapped_chain"] = chain
    info["chain_cycle_detected"] = chain_cycle_detected
    info["chain_depth"] = depth

    # known_original_attribute
    try:
        orig = getattr(func, "__wrapped__", None)
        if orig is not None:
            info["known_original_attribute"] = (
                getattr(orig, "__qualname__", None) or getattr(orig, "__name__", "")
            )
    except Exception:
        pass

    # Closure callable references (just identities, no content)
    closure = getattr(func, "__closure__", None)
    if closure is not None:
        callable_refs: list[int] = []
        for cell in closure:
            try:
                contents = cell.cell_contents
                if callable(contents):
                    callable_refs.append(id(contents))
            except ValueError:
                pass
        info["closure_callable_references"] = callable_refs
        info["closure_count"] = len(closure)
    else:
        info["closure_callable_references"] = []
        info["closure_count"] = 0

    return info


def capture_wrapper_inventory(
    stage: str,
    session: Any = None,
    extra_symbols: dict[str, Callable | None] | None = None,
    asyncio_loop: Any = None,
) -> dict[str, Any]:
    """Capture JSON-safe snapshot of discovered wrapper callables.

    Directly discovers symbols by scanning sys.modules — no monkeypatch app.
    """
    inventory: dict[str, Any] = {
        "stage": stage,
        "timestamp": time.time(),
        "timestamp_iso": datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(),
        "monotonic_ns": time.monotonic_ns(),
        "wrappers": {},
    }

    symbols = _discover_wrapper_symbols()
    if extra_symbols:
        symbols.update(extra_symbols)

    for name, func in symbols.items():
        inventory["wrappers"][name] = _inspect_wrapper_callable(func, stage=stage)

    # Active functions from session
    if session is not None and hasattr(session, "_active_functions"):
        active = getattr(session, "_active_functions", {})
        if isinstance(active, dict):
            for name, func in active.items():
                if name not in inventory["wrappers"]:
                    inventory["wrappers"][name] = _inspect_wrapper_callable(func, stage=stage)

    # Asyncio tasks
    if asyncio_loop is not None:
        tasks: list[dict[str, Any]] = []
        try:
            all_tasks_fn = getattr(asyncio_loop, "all_tasks", None)
            if all_tasks_fn is None:
                all_tasks_fn = lambda: asyncio.all_tasks(asyncio_loop)
            for task in all_tasks_fn():
                try:
                    tasks.append(_inspect_asyncio_task(task))
                except Exception:
                    pass
        except Exception:
            pass
        inventory["asyncio_tasks"] = tasks

    return inventory


def _inspect_asyncio_task(task: asyncio.Task) -> dict[str, Any]:
    """Inspect an asyncio Task for milestone inventory."""
    info: dict[str, Any] = {
        "task_id": id(task),
        "task_name": task.get_name() if hasattr(task, "get_name") else "",
        "done": task.done(),
        "cancelled": task.cancelled(),
        "coroutine_qualname": None,
        "top_stack_file": None,
        "top_stack_line": None,
        "top_stack_function": None,
    }
    # Get coroutine qualname
    try:
        coro = task.get_coro()
        if coro is not None:
            info["coroutine_qualname"] = getattr(coro, "__qualname__", None) or getattr(coro, "__name__", None)
    except Exception:
        pass
    # Get top of stack
    try:
        stack = task.get_stack(limit=1)
        if stack:
            frame = stack[-1]
            info["top_stack_file"] = frame.f_code.co_filename
            info["top_stack_line"] = frame.f_lineno
            info["top_stack_function"] = frame.f_code.co_name
    except Exception:
        pass
    return info


# ═══════════════════════════════════════════════════════════════════════════════════
# Include-path resolution for trace_config.json
# ═══════════════════════════════════════════════════════════════════════════════════

def _comfyui_root_candidates(here: Path | None) -> list[Path]:
    """Return plausible ComfyUI checkout roots, most specific first.

    Covers both layouts this runtime ships in: a source checkout where the
    package sits at ``<ComfyUI>/custom_nodes/comfyui-modal/comfymodal_runtime``,
    and the deployed layout where the package is mounted at
    ``/root/comfymodal_runtime``. Derivation from the module path alone misses
    the second case entirely.
    """
    out: list[Path] = []
    if here is not None:
        try:
            node = here
            for _ in range(4):
                node = node.parent
                if node.name == "comfyui-modal" and node.parent.name == "custom_nodes":
                    out.append(node.parent.parent)
                if node.name == "ComfyUI":
                    out.append(node)
        except Exception:
            pass
    out.extend([
        Path("/root/ComfyUI"),
        Path("/ComfyUI"),
        Path("/opt/ComfyUI"),
        Path("/workspace/ComfyUI"),
        Path("/app/ComfyUI"),
    ])
    # Anything that imports cleanly is authoritative.
    try:
        import folder_paths  # type: ignore
        base = getattr(folder_paths, "base_path", None)
        if base:
            out.append(Path(str(base)))
        main = getattr(folder_paths, "get_folder_paths", None)
        if callable(main):
            for name in ("custom_nodes", "comfy"):
                try:
                    p = main(name)
                except Exception:
                    continue
                if p:
                    base_p = Path(str(p))
                    out.append(base_p if base_p.name != "comfy" else base_p.parent)
    except Exception:
        pass
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        try:
            k = str(p)
        except Exception:
            continue
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


#: VizTracer ``min_duration`` floor, in milliseconds.  Tracing every Python call
#: in a Golden request produced ~1.25M events, which is a ~400 MB JSON trace and
#: dominates the analysis loop.  A 10us floor drops the sub-frame bookkeeping
#: noise while preserving every call a human would read in a call tree.
#: Override with COMFYMODAL_V2_TRACE_MIN_DURATION_MS (0 disables the filter).
TRACE_MIN_DURATION_MS_DEFAULT = 0.01


def _trace_min_duration_ms() -> float:
    raw = str(os.environ.get("COMFYMODAL_V2_TRACE_MIN_DURATION_MS", "")).strip()
    if not raw:
        return TRACE_MIN_DURATION_MS_DEFAULT
    try:
        value = float(raw)
    except ValueError:
        return TRACE_MIN_DURATION_MS_DEFAULT
    return value if value >= 0 else TRACE_MIN_DURATION_MS_DEFAULT


def _resolve_trace_include_paths() -> dict[str, Any]:
    """Resolve VizTracer include file paths from known project layout.

    Returns dict with: requested, resolved, missing, excluded.
    """
    requested: list[str] = [
        # V2-owned
        "comfymodal_runtime/",
        "comfyapp.py",
        "canonical_execution.py",
        "production_workflow.py",
        "profiler_trace_v4.py",
        "timing_trace.py",
        "wall_clock_trace_v3.py",
        "warmup_profile.py",
        "run_prompt_options.py",
        "optimizations.py",
        # ComfyUI core
        "execution.py",
        "nodes.py",
        "comfy/model_management.py",
        "comfy/model_patcher.py",
        "comfy/sd.py",
        "comfy/samplers.py",
        "comfy/sample.py",
        "comfy/utils.py",
        # Loaded custom-node modules (symbolic)
        "CacheDiT",
        "RES4LYF",
        "ClownsharKSampler",
        "rgthree",
        "KJNodes",
        "ComfyUI-Easy-Use",
        "FeatureInjLatent",
    ]

    excluded: list[str] = [
        "torch",
        "transformers",
        "diffusers",
        "numpy",
        "site-packages",
        "comfy/ldm",
    ]

    resolved: list[str] = []
    missing: list[str] = []

    # Build search roots from module location
    search_roots: list[Path] = []
    try:
        here = Path(__file__).resolve().parent
        search_roots.append(here)                    # comfymodal_runtime/
        custom_node_root = here.parent               # comfyui-modal/
        search_roots.append(custom_node_root)
    except Exception:
        here = None

    # Locate the ComfyUI checkout. The obvious two-levels-up guess only holds
    # for a source checkout; the deployed layout puts this package at
    # /root/comfymodal_runtime, so `comfyui_root.name == "ComfyUI"` was never
    # true and ComfyUI was never searched at all. Every `comfy/*.py` and
    # custom-node pattern below silently landed in `missing`, which is why the
    # compute stages -- whose bodies are ComfyUI and RES4LYF code -- recorded no
    # frames however well they were traced.
    comfyui_root: Path | None = None
    for candidate in _comfyui_root_candidates(here):
        try:
            if (candidate / "comfy").is_dir():
                comfyui_root = candidate
                break
        except Exception:
            continue
    if comfyui_root is not None:
        search_roots.append(comfyui_root)
        search_roots.append(comfyui_root / "comfy")
        # Custom nodes hold the sampler, CFG and CacheDiT implementations that
        # golden_sampling executes; without them that stage is a bare leaf.
        custom_nodes_dir = comfyui_root / "custom_nodes"
        if custom_nodes_dir.is_dir():
            search_roots.append(custom_nodes_dir)
            try:
                for entry in sorted(custom_nodes_dir.iterdir()):
                    if entry.is_dir() and not entry.name.startswith("."):
                        search_roots.append(entry)
            except Exception:
                pass

    # Custom node search roots (from known installed paths)
    try:
        import site
        for sp in site.getsitepackages():
            search_roots.append(Path(sp))
    except Exception:
        pass

    # Locate the ComfyUI checkout by content, not by path shape.
    #
    # The layout assumption above (``<custom_node_root>/../../ComfyUI``) only
    # holds when this package is installed under ComfyUI/custom_nodes/. In the
    # container it lives at /root/comfymodal_runtime, so custom_node_root is
    # /root, the guessed parent is "/", its name is not "ComfyUI", and the real
    # checkout is never searched. Every requested ComfyUI path then resolved to
    # `missing`, and since a non-empty include list is used, those frames were
    # silently filtered out of the trace.
    #
    # That is precisely why golden_clip_load was deep (its body is
    # comfymodal_runtime, always included) while every stage that hands off to
    # ComfyUI or a custom node -- clip_forward, unet_load, vae_load, sampling --
    # collapsed to a leaf despite the tracer recording the calls. Probe for a
    # directory that actually contains the ComfyUI package instead of assuming.
    def _looks_like_comfyui(root: Path) -> bool:
        try:
            return (root / "comfy" / "sd.py").exists() and (
                root / "folder_paths.py"
            ).exists()
        except OSError:
            return False

    probe_roots: list[Path] = []
    for base in list(search_roots):
        for suffix in ("", "ComfyUI", "custom_nodes/ComfyUI", ".."):
            try:
                probe_roots.append((base / suffix).resolve())
            except OSError:
                continue
    for candidate in probe_roots:
        try:
            if candidate.name == "ComfyUI" or _looks_like_comfyui(candidate):
                if candidate not in search_roots:
                    search_roots.append(candidate)
                comfy_pkg = candidate / "comfy"
                if comfy_pkg.is_dir() and comfy_pkg not in search_roots:
                    search_roots.append(comfy_pkg)
                custom_nodes = candidate / "custom_nodes"
                if custom_nodes.is_dir() and custom_nodes not in search_roots:
                    # Sampler/model packs live here (RES4LYF, ComfyUI-CacheDiT).
                    search_roots.append(custom_nodes)
        except OSError:
            continue

    searched_dirs = set()
    for root in search_roots:
        try:
            searched_dirs.add(str(root.resolve()))
        except Exception:
            pass

    for pattern in requested:
        found = False
        for root in search_roots:
            candidate = root / pattern
            if candidate.exists():
                resolved.append(str(candidate.resolve()))
                found = True
                break
            # Try glob for partial matches
            if "*" not in pattern:
                for ext in (".py", ""):
                    candidate_ext = root / (pattern + ext) if ext else root / pattern
                    if candidate_ext.exists():
                        resolved.append(str(candidate_ext.resolve()))
                        found = True
                        break
                if found:
                    break
        if not found:
            missing.append(pattern)

    return {
        "requested": requested,
        "resolved": resolved,
        "missing": missing,
        "excluded": excluded,
        "search_roots": sorted(searched_dirs),
    }


# ═══════════════════════════════════════════════════════════════════════════════════
# FullExecutionTraceSession
# ═══════════════════════════════════════════════════════════════════════════════════

class FullExecutionTraceSession:
    """Container-side full-execution trace session.

    Lifecycle states (exact):
        created → restore_tracing → restore_complete → request_claimed
             ↓                                      ↓              ↓
        request_ready → request_claimed            failed         failed
                              ↓
                       request_tracing → trace_stopped
                              ↓               ↓
                            failed          failed

    Thread-safe state transitions.  Invalid/repeated transitions are recorded
    in ``session_events.jsonl`` but never raised.

    Module is fully inert when ``COMFYMODAL_V2_FULL_TRACE != '1'``.  Golden
    request-only sessions use ``start_request_only``; restore does not create
    them.
    """

    _instance: Optional[FullExecutionTraceSession] = None
    _instance_lock = threading.Lock()

    def __init__(
        self,
        *,
        container_session_id: str,
        restored_instance_id: str = "",
        restore_session_id: str = "",
        _trace_id_override: str | None = None,     # internal test hook
    ) -> None:
        """Private constructor.  Use ``create_if_enabled`` factory."""
        # Identity fields stored at construction
        self._container_session_id = container_session_id
        self._restored_instance_id = restored_instance_id
        self._restore_session_id = restore_session_id
        self._modal_task_id: str = ""
        self._image_id: str = ""
        self._cloud: str = ""
        self._region: str = ""

        self.trace_id = _trace_id_override or uuid.uuid4().hex
        self.schema_version = SCHEMA_VERSION
        self._base_dir = self._resolve_base_dir()
        self._state: str = "created"
        self._state_lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._events_path: Path | None = None
        self._claimed = False
        self._claimed_request_id: str | None = None
        self._resource_sampler: ContainerResourceSampler | None = None
        self._viztracer: Any = None
        self._viztracer_version: str | None = None
        self._torch_profiler: Any = None
        self._torch_profiler_active = False
        self._torch_profiler_lock = threading.Lock()
        self._torch_profiler_thread_id: int | None = None
        self._active_functions: dict[str, Callable] = {}
        self._stopped = threading.Event()
        self._start_time = time.time()
        self._start_mono_ns = time.monotonic_ns()
        self._result_summary: dict[str, Any] = {}
        self._trace_stopped_result: dict[str, Any] | None = None
        self._trace_config_lock = threading.Lock()

        # Operation tracking (nested stacks, thread/task-safe)
        self._op_lock = threading.Lock()
        self._op_stacks: dict[tuple[int, int | None], list[str]] = {}  # (thread_id, asyncio_task_id) -> [operation_id]
        self._op_cache: dict[str, dict[str, Any]] = {}  # operation_id -> cached start metadata

        self._setup_directories()
        self._write_event("created", {"state": self._state})

    def _resolve_base_dir(self) -> Path:
        """Determine the trace root directory.

        Respects ``_TEST_TRACE_BASE`` for test isolation —
        does not expose this via public factory parameters.
        """
        base = _TEST_TRACE_BASE if _TEST_TRACE_BASE else _TRACE_BASE
        return Path(base) / self.trace_id

    # ── Factory ──────────────────────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> Optional["FullExecutionTraceSession"]:
        """Return the live traced session, or ``None`` when tracing is off.

        A read-only accessor for process-boundary integrations that must ask
        "is this request being traced?" without being able to create a session.
        """
        return cls._instance

    @classmethod
    def create_if_enabled(
        cls,
        *,
        container_session_id: str,
        restored_instance_id: str = "",
        restore_session_id: str = "",
        _trace_id_override: str | None = None,
    ) -> Optional[FullExecutionTraceSession]:
        """Create and return a singleton session when the env flag is ``'1'``.

        Returns ``None`` when tracing is disabled — no files, no imports.

        Parameters
        ----------
        container_session_id:
            The Modal container session identifier.
        restored_instance_id:
            Initial restored instance ID (optional, may be updated later).
        restore_session_id:
            Initial restore session ID (optional, may be updated later).
        _trace_id_override:
            Internal test hook to set a deterministic trace ID.
        """
        if os.environ.get(_ENV_ENABLE) != "1":
            return None
        with cls._instance_lock:
            if cls._instance is not None:
                return cls._instance
            instance = cls(
                container_session_id=container_session_id,
                restored_instance_id=restored_instance_id,
                restore_session_id=restore_session_id,
                _trace_id_override=_trace_id_override,
            )
            cls._instance = instance
            return instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (used by tests)."""
        with cls._instance_lock:
            cls._instance = None

    # ── Directory scaffolding ────────────────────────────────────────────────────────

    def _setup_directories(self) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        for subdir in _SUBDIRS:
            (self._base_dir / subdir).mkdir(exist_ok=True)

        self._events_path = self._base_dir / "raw" / "session_events.jsonl"

        # Build and write trace_config.json
        config = self._build_config()
        self._write_json("trace_config.json", config)

        # Empty placeholders
        self._write_json("runtime_result_summary.json", {})
        self._write_json("wrapper_snapshots.json", [])
        for name in _REQUIRED_RAW_FILES:
            path = self._base_dir / "raw" / name
            if not path.exists():
                if name.endswith(".gz"):
                    import gzip as _gz
                    with _gz.open(path, "wb") as f:
                        f.write(b"")
                elif name.endswith(".json"):
                    path.write_text("{}")
                elif name.endswith(".jsonl"):
                    path.write_text("")

    def _build_config(self) -> dict[str, Any]:
        """Build the trace_config.json content."""
        inc = _resolve_trace_include_paths()
        entries = _env_int_chain(
            _ENV_ENTRIES, _LEGACY_ENV_ENTRIES,
            default=_DEFAULT_VIZTRACER_ENTRIES,
        )
        stack_depth = _env_int(
            "COMFYMODAL_V2_FULL_TRACE_MAX_STACK_DEPTH",
            _DEFAULT_MAX_STACK_DEPTH,
        )
        torch_enabled = os.environ.get(_ENV_TORCH, "0").strip().lower() in {
            "1", "true", "yes", "on",
        }

        # VizTracer version detection is deferred to start_restore (lazy import)
        viz_version: str | None = None

        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "container_session_id": self._container_session_id,
            "identity": {
                "restored_instance_id": self._restored_instance_id,
                "restore_session_id": self._restore_session_id,
                "modal_task_id": self._modal_task_id,
                "image_id": self._image_id,
                "cloud": self._cloud,
                "region": self._region,
            },
            "include_paths": {
                "requested": inc["requested"],
                "resolved": inc["resolved"],
                "missing": inc["missing"],
            },
            "exclusions": inc["excluded"],
            "search_roots": inc["search_roots"],
            "viztracer_version": viz_version,
            "entry_capacity": entries,
            "torch_enabled": torch_enabled,
            "config": {
                "viztracer_entries": entries,
                "viztracer_max_stack_depth": stack_depth,
                "resource_interval_ms": _env_int_chain(
                    _ENV_RESOURCE_INTERVAL, _LEGACY_ENV_RESOURCE_INTERVAL,
                    default=_DEFAULT_RESOURCE_INTERVAL_MS,
                ),
                "env_entries_var": _ENV_ENTRIES,
                "env_resource_interval_var": _ENV_RESOURCE_INTERVAL,
            },
            "created_at": self._start_time,
            "created_at_iso": datetime.fromtimestamp(
                self._start_time, tz=timezone.utc,
            ).isoformat(),
        }

    def _update_trace_config_viz_version(self) -> None:
        """Re-read ``trace_config.json``, update ``viztracer_version``, rewrite."""
        config_path = self._base_dir / "raw" / "trace_config.json"
        try:
            if config_path.exists():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                config["viztracer_version"] = self._viztracer_version
                config_path.write_text(
                    _safe_json_serialize(config, indent=2), encoding="utf-8",
                )
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Cannot update trace_config viztracer_version: %s", exc)

    def update_trace_config(
        self,
        updates: Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> None:
        """Persist a bounded set of request-level trace contract fields.

        This is intentionally not a general session-state mutator.  Adapters
        use it when a contract is known only after session construction (for
        example, the direct Golden output durability mode).  Unknown fields
        and unsafe values are ignored; tracing metadata must never change the
        execution request or make an optional trace path fail.
        """
        if updates is None:
            updates = fields
        elif fields:
            updates = {**dict(updates), **fields}
        if not isinstance(updates, Mapping):
            return
        safe_updates: dict[str, Any] = {}
        for key, value in updates.items():
            name = str(key)
            if name not in _TRACE_CONFIG_UPDATE_FIELDS:
                continue
            safe_value = _safe_json_value(value)
            if name in {"required_canonical_stages", "canonical_stage_order"}:
                if not isinstance(safe_value, list) or not all(
                    isinstance(item, str) for item in safe_value
                ):
                    continue
            elif not isinstance(safe_value, (str, int, float, bool, type(None))):
                continue
            safe_updates[name] = safe_value
        if not safe_updates:
            return

        config_path = self._base_dir / "raw" / "trace_config.json"
        try:
            with self._trace_config_lock:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                if not isinstance(config, dict):
                    return
                config.update(safe_updates)
                config_path.write_text(
                    _safe_json_serialize(config, indent=2), encoding="utf-8",
                )
            self._write_event("trace_config_updated", {
                "fields": sorted(safe_updates),
            })
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Cannot update trace config: %s", exc)

    def _write_json(self, name: str, data: Any) -> Path:
        path = self._base_dir / "raw" / name
        path.write_text(_safe_json_serialize(data, indent=2))
        return path

    # ── State management ─────────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        with self._state_lock:
            return self._state

    def _transition(self, target: str) -> bool:
        """Attempt a state transition.

        Returns ``True`` on success.  Invalid/repeated transitions are
        recorded in the session events log but **never raised**.
        """
        with self._state_lock:
            current = self._state
            allowed = _VALID_TRANSITIONS.get(current, set())
            if target in allowed:
                self._state = target
                self._write_event("state_transition", {
                    "from": current,
                    "to": target,
                    "valid": True,
                })
                return True

            self._write_event("state_transition", {
                "from": current,
                "to": target,
                "valid": False,
                "reason": f"Invalid transition from {current!r} to {target!r}",
            })
            return False

    def _write_event(self, event_type: str, data: dict[str, Any]) -> None:
        event: dict[str, Any] = {
            "timestamp": time.time(),
            "timestamp_iso": datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(),
            "monotonic_ns": time.monotonic_ns(),
            "event": event_type,
            "data": data,
        }
        self._events.append(event)
        if self._events_path is not None:
            try:
                with open(self._events_path, "a", encoding="utf-8") as f:
                    f.write(_safe_json_serialize(event) + "\n")
            except OSError as exc:
                log.warning("Cannot write session event: %s", exc)

    # ── Lifecycle API ────────────────────────────────────────────────────────────────

    def start_restore(self) -> None:
        """Start restore-time tracing.

        Transitions to ``restore_tracing``, starts the resource sampler,
        and lazily initialises VizTracer.
        """
        if not self._transition("restore_tracing"):
            print(
                f"[v2.full_trace] stage=start_restore "
                f"status=skipped reason=invalid_state({self._state}) "
                f"trace_id={self.trace_id}",
                flush=True,
            )
            return

        entries = _env_int_chain(
            _ENV_ENTRIES, _LEGACY_ENV_ENTRIES,
            default=_DEFAULT_VIZTRACER_ENTRIES,
        )
        stack = _env_int(
            "COMFYMODAL_V2_FULL_TRACE_MAX_STACK_DEPTH",
            _DEFAULT_MAX_STACK_DEPTH,
        )

        # Start resource sampler
        try:
            self._resource_sampler = ContainerResourceSampler(
                str(self._base_dir),
                interval_ms=_env_int_chain(
                    _ENV_RESOURCE_INTERVAL, _LEGACY_ENV_RESOURCE_INTERVAL,
                    default=_DEFAULT_RESOURCE_INTERVAL_MS,
                ),
                session_phase="restore_tracing",
            )
            self._resource_sampler.start()
        except Exception as exc:
            log.warning("Resource sampler start failed")
            print(
                f"[v2.full_trace] stage=start_restore "
                f"status=error error_type=ResourceSampler "
                f"trace_id={self.trace_id}",
                flush=True,
            )
            self._resource_sampler = None

        # Lazy VizTracer start — import only here, never at module/construction time
        try:
            inc = _resolve_trace_include_paths()
            from viztracer import VizTracer as _VT

            # Detect version
            try:
                self._viztracer_version = (
                    getattr(_VT, "__version__", None)
                    or getattr(_VT, "VERSION", None)
                    or "unknown"
                )
            except Exception:
                self._viztracer_version = "unknown"

            # Build intended configuration
            viz_kwargs: dict[str, Any] = dict(
                tracer_entries=entries,
                verbose=0,
                max_stack_depth=stack,
                ignore_c_function=True,
                ignore_frozen=True,
                log_func_args=False,
                log_func_retval=False,
                log_print=False,
                log_gc=True,
                log_async=True,
                log_torch=False,
                pid_suffix=False,
                file_info=True,
                register_global=True,
                trace_self=False,
                min_duration=_trace_min_duration_ms(),
                minimize_memory=True,
                output_file=str(self._base_dir / "raw" / "viztracer.json"),
            )
            # Blacklist, never the include_files whitelist -- same reasoning as the
            # request tracer below. A rejected call increments VizTracer's
            # thread-local ignore_stack_depth and suppresses every descendant
            # without re-testing its own filename, so a whitelist that omits
            # asyncio/threading/concurrent.futures hides whole subtrees.
            viz_kwargs["exclude_files"] = inc["excluded"]

            # Attempt creation with full kwargs; fall back on keyword rejection
            try:
                self._viztracer = _VT(**viz_kwargs)
            except TypeError as te:
                log.warning("VizTracer keyword rejection; retrying with minimal kwargs")
                minimal_kwargs: dict[str, Any] = dict(
                    tracer_entries=entries,
                    max_stack_depth=stack,
                    # Keep the blacklist on the fallback path too. Falling back
                    # to the include_files whitelist here would silently
                    # reinstate the subtree-poisoning this replaced.
                    exclude_files=inc["excluded"],
                )
                self._viztracer = _VT(**minimal_kwargs)

            self._viztracer.start()

            # Update trace_config with detected version
            self._update_trace_config_viz_version()

        except ImportError:
            log.info("VizTracer not available; continuing without function tracing")
            print(
                f"[v2.full_trace] stage=start_restore "
                f"status=skipped reason=viztracer_not_available "
                f"trace_id={self.trace_id}",
                flush=True,
            )
        except Exception as exc:
            log.warning("VizTracer start failed")
            print(
                f"[v2.full_trace] stage=start_restore "
                f"status=error error_type={type(exc).__name__} "
                f"trace_id={self.trace_id}",
                flush=True,
            )

        self._write_event("restore_started", {
            "tracer_entries": entries,
            "max_stack_depth": stack,
        })

    def start_request_only(self, request_id: str) -> bool:
        """Start deep tracing lazily for one request, never during restore.

        Golden deep tracing is a run selector.  The session directory and all
        samplers/tracers are created only after the request has been validated;
        restore therefore remains lightweight and cannot claim restore capture.
        """
        if not self._transition("request_ready"):
            return False
        if not self._transition("request_claimed"):
            return False
        self._claimed = True
        self._claimed_request_id = str(request_id)
        self._write_event("request_claimed", {
            "request_id": str(request_id),
            "request_id_hash": _stable_hash(str(request_id)),
            "request_only": True,
        })
        if not self._transition("request_tracing"):
            return False
        # Start the resource/VizTracer machinery at the request boundary, not
        # in restore.  start_restore's setup is intentionally reused only for
        # these request-owned components.
        self._start_request_tracing_components()
        self._handoff_request_thread_tracing()
        self._write_event("request_trace_started", {"request_id": str(request_id)})
        return True

    def _start_request_tracing_components(self) -> None:
        """Initialize request tracing components without restore state claims."""
        entries = _env_int_chain(_ENV_ENTRIES, _LEGACY_ENV_ENTRIES, default=_DEFAULT_VIZTRACER_ENTRIES)
        stack = _env_int("COMFYMODAL_V2_FULL_TRACE_MAX_STACK_DEPTH", _DEFAULT_MAX_STACK_DEPTH)
        try:
            self._resource_sampler = ContainerResourceSampler(
                str(self._base_dir),
                interval_ms=_env_int_chain(
                    _ENV_RESOURCE_INTERVAL, _LEGACY_ENV_RESOURCE_INTERVAL,
                    default=_DEFAULT_RESOURCE_INTERVAL_MS,
                ),
                session_phase="request_tracing",
            )
            self._resource_sampler.start()
        except Exception as exc:
            self._resource_sampler = None
            self._write_event("request_resource_sampler_error", {"error_type": type(exc).__name__})
        try:
            inc = _resolve_trace_include_paths()
            from viztracer import VizTracer as _VT
            self._viztracer_version = (
                getattr(_VT, "__version__", None)
                or getattr(_VT, "VERSION", None)
                or "unknown"
            )
            kwargs: dict[str, Any] = {
                "tracer_entries": entries,
                "max_stack_depth": stack,
                "output_file": str(self._base_dir / "raw" / "viztracer.json"),
                "register_global": True,
                "log_async": True,
                "pid_suffix": False,
                "ignore_c_function": True,
                "ignore_frozen": True,
                "min_duration": _trace_min_duration_ms(),
            }
            # Use a BLACKLIST, never the include_files whitelist.
            #
            # VizTracer applies these at capture time, and a rejected call
            # increments a thread-local ignore_stack_depth that suppresses every
            # descendant WITHOUT re-checking its own filename (snaptrace.c skips
            # on `ignore_stack_depth > 0` before the prefix test). A whitelist
            # that omits asyncio/threading/concurrent.futures therefore hides
            # every project function reached beneath them -- which is why only
            # the work before the first await was ever deep.
            #
            # Excluding torch and the site-packages bulk instead keeps the
            # scheduler frames traceable, so no ancestry is poisoned and call
            # trees survive coroutine resumes and executor workers. Dropping
            # include_files entirely was tried and is not viable: it traces torch
            # internals too, the event volume explodes, and the request stops
            # completing inside golden_sampling.
            kwargs["exclude_files"] = inc["excluded"]
            try:
                self._viztracer = _VT(**kwargs)
            except TypeError:
                self._viztracer = _VT(tracer_entries=entries, max_stack_depth=stack)
            self._viztracer.start()
            self._update_trace_config_viz_version()
        except ImportError:
            self._write_event("request_viztracer_unavailable", {})
        except Exception as exc:
            self._write_event("request_viztracer_error", {"error_type": type(exc).__name__})

    def set_restore_complete(self) -> None:
        """Mark the restore phase as complete.

        Transitions to ``restore_complete``.  Required before claiming
        a request.
        """
        self._transition("restore_complete")
        # Update resource sampler phase
        if self._resource_sampler is not None:
            self._resource_sampler._session_phase = "restore_complete"

    def update_identity(
        self,
        *,
        restored_instance_id: str,
        restore_session_id: str,
        modal_task_id: str = "",
        image_id: str = "",
        cloud: str = "",
        region: str = "",
    ) -> None:
        """Update container identity metadata.

        All parameters are keyword-only.  Updates are persisted to the
        session events log.
        """
        self._restored_instance_id = restored_instance_id
        self._restore_session_id = restore_session_id
        self._modal_task_id = modal_task_id
        self._image_id = image_id
        self._cloud = cloud
        self._region = region
        self._write_event("identity_updated", {
            "restored_instance_id": restored_instance_id,
            "restore_session_id": restore_session_id,
            "modal_task_id": modal_task_id,
            "image_id": image_id,
            "cloud": cloud,
            "region": region,
        })

    def claim_first_request(self, request_id: str) -> bool:
        """Claim the first inference request *exactly once*.

        Returns ``True`` if this call successfully claimed the request.
        Subsequent calls return ``False`` and are logged.

        On success the session transitions through
        ``restore_complete → request_claimed`` and automatically
        begins request tracing.
        """
        if self._claimed:
            self._write_event("claim_skipped", {
                "request_id": request_id,
                "reason": "already_claimed",
                "existing_request_id": self._claimed_request_id,
            })
            print(
                f"[v2.full_trace] stage=claim_first_request "
                f"status=skipped reason=already_claimed "
                f"trace_id={self.trace_id}",
                flush=True,
            )
            return False

        if not self._transition("request_claimed"):
            print(
                f"[v2.full_trace] stage=claim_first_request "
                f"status=skipped reason=invalid_state({self._state}) "
                f"trace_id={self.trace_id}",
                flush=True,
            )
            return False

        self._claimed = True
        self._claimed_request_id = request_id
        self._write_event("request_claimed", {
            "request_id": request_id,
            "request_id_hash": _stable_hash(request_id),
        })

        # Begin request tracing phase (silent internal transition)
        if self._resource_sampler is not None:
            self._resource_sampler._session_phase = "request_tracing"

        # Transition to request_tracing so mark/operations can proceed
        if self._transition("request_tracing"):
            self._handoff_request_thread_tracing()

        return True

    def _handoff_request_thread_tracing(self) -> None:
        """Enable VizTracer tracing on the thread that owns the request.

        VizTracer is started during restore, but request execution may be
        handed to a different thread.  This compatibility hook is optional:
        missing or failing VizTracer support is recorded and never escapes
        into request execution.
        """
        event_data: dict[str, Any] = {
            "hook": "enable_thread_tracing",
            "called": False,
            "succeeded": False,
            "skipped": False,
        }

        try:
            hook = (
                getattr(self._viztracer, "enable_thread_tracing", None)
                if self._viztracer is not None
                else None
            )
        except BaseException:
            hook = None
            event_data["skipped"] = True
            event_data["reason"] = "hook_unavailable"

        if not callable(hook):
            event_data["skipped"] = True
            event_data.setdefault(
                "reason",
                "viztracer_unavailable" if self._viztracer is None else "unsupported",
            )
        else:
            event_data["called"] = True
            try:
                hook()
            except BaseException as exc:
                event_data["reason"] = "hook_failed"
                event_data["error_type"] = type(exc).__name__
                try:
                    print(
                        f"[v2.full_trace] stage=request_thread_tracing "
                        f"status=error error_type={type(exc).__name__} "
                        f"trace_id={self.trace_id}",
                        flush=True,
                    )
                except BaseException:
                    pass
            else:
                event_data["succeeded"] = True

        self._write_event("request_thread_tracing_handoff", event_data)

    def mark(self, name: str, **metadata: Any) -> None:
        """Record a trace mark event with safe metadata.

        Allowed in ``request_claimed`` and ``request_tracing`` states.
        Metadata is redacted for sensitive keys.
        """
        # Allow in both request_claimed and request_tracing
        with self._state_lock:
            if self._state not in ("request_claimed", "request_tracing"):
                self._write_event("mark_skipped", {
                    "name": name,
                    "reason": f"invalid_state:{self._state}",
                })
                return

        safe_metadata = {k: _safe_json_value(v) for k, v in metadata.items()}
        self._write_event("mark", {
            "name": name,
            "metadata": safe_metadata,
            "monotonic_ns": time.monotonic_ns(),
        })

    def operation_start(
        self,
        operation_type: str,
        semantic_key: str,
        **metadata: Any,
    ) -> str:
        """Record the start of a semantic operation.

        Returns a new opaque ``operation_id`` that must be passed to
        ``operation_end``.

        Allowed in ``request_claimed`` and ``request_tracing`` states.
        Thread/task-safe nested stacks.  Never stores raw semantic key.
        """
        with self._state_lock:
            if self._state not in ("request_claimed", "request_tracing"):
                self._write_event("operation_start_skipped", {
                    "operation_type": operation_type,
                    "reason": f"invalid_state:{self._state}",
                })
                return ""

        operation_id = uuid.uuid4().hex
        semantic_key_hash = _stable_hash(semantic_key)

        # Thread and asyncio task identity
        thread_id = threading.get_ident()
        native_thread_id: int | None = None
        try:
            native_thread_id = threading.current_thread().native_id
        except AttributeError:
            pass
        asyncio_task_id: int | None = None
        try:
            loop = asyncio.get_running_loop()
            task = asyncio.current_task(loop)
            if task is not None:
                asyncio_task_id = id(task)
        except RuntimeError:
            pass

        stack_key = (thread_id, asyncio_task_id)

        # Determine parent operation from stack
        parent_op_id: str | None = None
        with self._op_lock:
            stack = self._op_stacks.get(stack_key, [])
            if stack:
                parent_op_id = stack[-1]
            stack.append(operation_id)
            self._op_stacks[stack_key] = stack

        safe_metadata = {k: _safe_json_value(v) for k, v in metadata.items()}
        start_mono = time.monotonic_ns()

        # Cache start metadata for later operation_end (full schema)
        start_record: dict[str, Any] = {
            "operation_id": operation_id,
            "operation_type": operation_type,
            "semantic_key_hash": semantic_key_hash,
            "parent_operation_id": parent_op_id,
            "request_id": self._claimed_request_id,
            "restore_session_id": self._restore_session_id,
            "restored_instance_id": self._restored_instance_id,
            "pid": os.getpid(),
            "native_thread_id": native_thread_id,
            "asyncio_task_id": asyncio_task_id,
            "start_monotonic_ns": start_mono,
            "end_monotonic_ns": None,
            "wall_ms": None,
            "status": "started",
            "metadata": safe_metadata,
        }
        with self._op_lock:
            self._op_cache[operation_id] = start_record

        self._write_event("operation_start", start_record)

        return operation_id

    def operation_end(
        self,
        operation_id: str,
        *,
        status: str = "ok",
        **metadata: Any,
    ) -> None:
        """Record the end of a semantic operation.

        Matches the ``operation_id`` from a prior ``operation_start``.
        Safe against mismatched ends (logs warning, does not raise).
        """
        with self._state_lock:
            if self._state not in ("request_claimed", "request_tracing"):
                self._write_event("operation_end_skipped", {
                    "operation_id": operation_id,
                    "reason": f"invalid_state:{self._state}",
                })
                return

        if not operation_id:
            return

        # Look up cached start metadata
        with self._op_lock:
            cached = self._op_cache.get(operation_id)

        if cached is None:
            self._write_event("operation_end_mismatch", {
                "operation_id": operation_id,
                "reason": "not_found_in_cache",
            })
            return

        # Pop from stack (task-aware key)
        thread_id = threading.get_ident()
        asyncio_task_id: int | None = None
        try:
            loop = asyncio.get_running_loop()
            task = asyncio.current_task(loop)
            if task is not None:
                asyncio_task_id = id(task)
        except RuntimeError:
            pass
        stack_key = (thread_id, asyncio_task_id)

        with self._op_lock:
            stack = self._op_stacks.get(stack_key, [])
            if stack and stack[-1] == operation_id:
                stack.pop()
                self._op_stacks[stack_key] = stack
            elif operation_id in stack:
                try:
                    stack.remove(operation_id)
                    self._op_stacks[stack_key] = stack
                except ValueError:
                    pass

        end_mono = time.monotonic_ns()
        wall_ms = (end_mono - cached["start_monotonic_ns"]) / 1_000_000

        safe_metadata = {k: _safe_json_value(v) for k, v in metadata.items()}
        # Preserve safe metadata from start, merge with end metadata
        combined_metadata = dict(cached.get("metadata", {}))
        combined_metadata.update(safe_metadata)

        # Clean up cache entry
        with self._op_lock:
            self._op_cache.pop(operation_id, None)

        self._write_event("operation_end", {
            "operation_id": operation_id,
            "operation_type": cached["operation_type"],
            "semantic_key_hash": cached["semantic_key_hash"],
            "parent_operation_id": cached["parent_operation_id"],
            "request_id": cached["request_id"],
            "restore_session_id": cached["restore_session_id"],
            "restored_instance_id": cached["restored_instance_id"],
            "pid": cached["pid"],
            "native_thread_id": cached["native_thread_id"],
            "asyncio_task_id": cached["asyncio_task_id"],
            "start_monotonic_ns": cached["start_monotonic_ns"],
            "end_monotonic_ns": end_mono,
            "wall_ms": wall_ms,
            "status": status,
            "metadata": combined_metadata,
        })

    # ── Milestones ───────────────────────────────────────────────────────────────────

    def capture_milestone(
        self,
        stage: str,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        bridge_snapshot: Mapping[str, Any] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Record a milestone with thread inventory, asyncio tasks, bridge state,
        wrapper inventory, and extra metadata.

        Parameters
        ----------
        stage:
            Label for this milestone (e.g. ``"restore_start"``).
        loop:
            Optional event loop for asyncio task enumeration.
        bridge_snapshot:
            JSON-safe bridge state (validated and redacted).
        extra:
            Extra metadata (validated and redacted).
        """
        # No-op after trace is stopped (post-stop milestone guard)
        if self._state == "trace_stopped":
            print(
                f"[v2.full_trace] stage=capture_milestone "
                f"status=skipped reason=already_stopped "
                f"stage={stage} trace_id={self.trace_id}",
                flush=True,
            )
            return
        milestone: dict[str, Any] = {
            "milestone_type": stage,
            "timestamp": time.time(),
            "timestamp_iso": datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(),
            "monotonic_ns": time.monotonic_ns(),
            "state": self._state,
            "trace_id": self.trace_id,
        }

        # Thread inventory
        milestone["thread_inventory"] = self._capture_thread_inventory()

        # Asyncio tasks
        if loop is not None:
            milestone["asyncio_tasks"] = self._capture_milestone_asyncio_tasks(loop)
        else:
            milestone["asyncio_tasks"] = []

        # Bridge snapshot — validate JSON safety, drop unsafe
        if bridge_snapshot is not None:
            validated = self._validate_bridge_snapshot(dict(bridge_snapshot))
            milestone["bridge_snapshot"] = _redact_sensitive(validated)
        else:
            milestone["bridge_snapshot"] = None

        # Extra — redacted
        milestone["extra"] = _redact_sensitive(dict(extra) if extra else {})

        # Wrapper inventory
        try:
            wrapper_inv = capture_wrapper_inventory(
                stage=stage,
                session=self,
                asyncio_loop=loop,
            )
            milestone["wrapper_inventory"] = wrapper_inv
        except Exception as exc:
            milestone["wrapper_inventory"] = {
                "error_type": type(exc).__name__,
            }

        # Persist milestone
        milestones_path = self._base_dir / "raw" / "milestones.jsonl"
        try:
            with open(milestones_path, "a", encoding="utf-8") as f:
                f.write(_safe_json_serialize(milestone) + "\n")
        except OSError as exc:
            log.warning("Cannot write milestone: %s", exc)

        self._write_event("milestone", {"stage": stage})

        # Also persist wrapper snapshot to dedicated file
        if "wrapper_inventory" in milestone and isinstance(milestone["wrapper_inventory"], dict):
            self._append_wrapper_snapshot(milestone["wrapper_inventory"])

    def _validate_bridge_snapshot(self, snapshot: dict[str, Any], _depth: int = 0) -> dict[str, Any]:
        """Validate a bridge snapshot, dropping or replacing unsafe values.

        Returns a JSON-safe copy.  Non-JSONable leaf values are replaced
        with their type name.  Recursion depth is limited to 20 to prevent
        stack overflow from malicious or deeply nested metadata.
        """
        if _depth > 20:
            return {"<max_depth>": True}
        result: dict[str, Any] = {}
        for k, v in snapshot.items():
            if isinstance(v, (str, int, float, bool, type(None))):
                result[k] = v
            elif isinstance(v, (list, tuple)):
                result[k] = [_safe_json_value(item) for item in v]
            elif isinstance(v, dict):
                result[k] = self._validate_bridge_snapshot(v, _depth + 1)
            else:
                result[k] = _safe_json_value(v)
        return result

    def _append_wrapper_snapshot(self, wrapper_data: dict[str, Any]) -> None:
        """Append a wrapper inventory snapshot to wrapper_snapshots.json."""
        wrapper_path = self._base_dir / "raw" / "wrapper_snapshots.json"
        try:
            existing: list[dict[str, Any]] = []
            if wrapper_path.exists():
                try:
                    raw = wrapper_path.read_text(encoding="utf-8")
                    if raw.strip():
                        existing = json.loads(raw)
                        if not isinstance(existing, list):
                            existing = []
                except (json.JSONDecodeError, OSError):
                    existing = []
            existing.append(wrapper_data)
            wrapper_path.write_text(
                _safe_json_serialize(existing, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning("Cannot write wrapper snapshot: %s", exc)

    def _capture_thread_inventory(self) -> list[dict[str, Any]]:
        """Capture safe Python thread inventory."""
        threads: list[dict[str, Any]] = []
        for thread in threading.enumerate():
            try:
                threads.append({
                    "name": thread.name or "",
                    "ident": thread.ident,
                    "native_id": getattr(thread, "native_id", None),
                    "daemon": thread.daemon,
                    "alive": thread.is_alive(),
                })
            except Exception:
                pass
        return threads

    def _capture_milestone_asyncio_tasks(self, loop: asyncio.AbstractEventLoop) -> list[dict[str, Any]]:
        """Capture asyncio task inventory with detailed fields."""
        tasks: list[dict[str, Any]] = []
        try:
            all_tasks_fn = getattr(loop, "all_tasks", None)
            if all_tasks_fn is None:
                all_tasks_fn = lambda: asyncio.all_tasks(loop)
            for task in all_tasks_fn():
                try:
                    tasks.append(_inspect_asyncio_task(task))
                except Exception:
                    pass
        except Exception:
            pass
        return tasks

    # ── Torch Profiler ───────────────────────────────────────────────────────────────

    def start_torch_profiler(self) -> None:
        """Lazily start the ``torch.profiler.profile`` context manager.

        Uses exact args: ``record_shapes=False``, ``profile_memory=True``,
        ``with_stack=True``.  No automatic start/schedule/sync.

        Gracefully handles missing CUDA and global Kineto state conflicts.
        Reports sanitized diagnostics on failure.
        """
        if self._torch_profiler_active or self._torch_profiler is not None:
            return
        _start_thread_id = threading.get_ident()
        # Torch/Kineto shutdown can block request terminalization on some
        # CUDA/runtime combinations, so it is explicitly opt-in.  The rest
        # of the full trace remains enabled when this optional lane is off.
        if os.environ.get(_ENV_TORCH, "0").strip().lower() not in {
            "1", "true", "yes", "on",
        }:
            print(
                f"[v2.full_trace] stage=start_torch_profiler "
                f"status=skipped reason=torch_disabled "
                f"trace_id={self.trace_id}",
                flush=True,
            )
            return
        try:
            import torch.profiler

            # Check for global Kineto conflicts
            try:
                from torch._C._profiler import _kineto_profiler_running
                if _kineto_profiler_running():
                    log.warning("Kineto profiler already running; skipping torch profiler")
                    print(
                        f"[v2.full_trace] stage=start_torch_profiler "
                        f"status=skipped reason=kineto_conflict "
                        f"trace_id={self.trace_id}",
                        flush=True,
                    )
                    return
            except (ImportError, AttributeError):
                pass

            activities = [torch.profiler.ProfilerActivity.CPU]
            if torch.cuda.is_available():
                activities.append(torch.profiler.ProfilerActivity.CUDA)

            self._torch_profiler = torch.profiler.profile(
                activities=activities,
                record_shapes=False,
                profile_memory=True,
                with_stack=True,
                with_modules=False,
            )
            self._torch_profiler.__enter__()
            self._torch_profiler_active = True
            self._torch_profiler_thread_id = _start_thread_id
            print(
                f"[v2.full_trace] stage=start_torch_profiler "
                f"status=started thread_id={_start_thread_id} "
                f"trace_id={self.trace_id}",
                flush=True,
            )
            self._write_event("torch_profiler_started", {
                "activities": [str(a) for a in activities],
                "record_shapes": False,
                "profile_memory": True,
                "with_stack": True,
                "thread_id": _start_thread_id,
            })
        except ImportError:
            log.info("torch.profiler not available; skipping")
            print(
                f"[v2.full_trace] stage=start_torch_profiler "
                f"status=skipped reason=not_available "
                f"trace_id={self.trace_id}",
                flush=True,
            )
        except Exception as exc:
            log.warning("torch profiler start failed")
            print(
                f"[v2.full_trace] stage=start_torch_profiler "
                f"status=error error_type={type(exc).__name__} "
                f"trace_id={self.trace_id}",
                flush=True,
            )

    def stop_torch_profiler(self) -> None:
        """Stop and export the torch profiler.  Exactly-once under lock.

        Detaches the profiler under the session lock, calls ``__exit__()``
        once, and repeated stops are no-ops.  Exports Chrome trace, gzips it.
        """
        _profiler = None
        with self._torch_profiler_lock:
            if self._torch_profiler is None:
                return
            _profiler = self._torch_profiler
            self._torch_profiler = None
            _was_active = self._torch_profiler_active
            self._torch_profiler_active = False

        _stop_thread_id = threading.get_ident()
        _start_thread_id = getattr(self, "_torch_profiler_thread_id", None)
        _same_thread = (
            _start_thread_id is not None and _start_thread_id == _stop_thread_id
        )

        print(
            f"[v2.full_trace] stage=stop_torch_profiler "
            f"start_thread_id={_start_thread_id} "
            f"stop_thread_id={_stop_thread_id} "
            f"same_thread={_same_thread} "
            f"trace_id={self.trace_id}",
            flush=True,
        )

        if _was_active and _profiler is not None:
            _torch_stop_started = time.perf_counter()
            _torch_exit_ms = 0.0
            _torch_save_ms = 0.0
            _torch_gzip_ms = 0.0
            try:
                _phase_started = time.perf_counter()
                _profiler.__exit__(None, None, None)
                _torch_exit_ms = round((time.perf_counter() - _phase_started) * 1000, 3)
                trace_path = self._base_dir / "raw" / "torch_trace.json"
                _phase_started = time.perf_counter()
                _profiler.export_chrome_trace(str(trace_path))
                _torch_save_ms = round((time.perf_counter() - _phase_started) * 1000, 3)
                _phase_started = time.perf_counter()
                self._gzip_file(trace_path)
                _torch_gzip_ms = round((time.perf_counter() - _phase_started) * 1000, 3)
                trace_path.unlink(missing_ok=True)
                self._write_event("torch_profiler_stopped", {
                    "exported": True,
                    "path": str(trace_path.with_name("torch_trace.json.gz")),
                    "start_thread_id": _start_thread_id,
                    "stop_thread_id": _stop_thread_id,
                    "same_thread": _same_thread,
                    "stop_ms": _torch_exit_ms,
                    "save_ms": _torch_save_ms,
                    "gzip_ms": _torch_gzip_ms,
                    "total_ms": round((time.perf_counter() - _torch_stop_started) * 1000, 3),
                })
            except Exception as exc:
                log.warning("Torch profiler export error")
                print(
                    f"[v2.full_trace] stage=stop_torch_profiler "
                    f"status=error error_type={type(exc).__name__} "
                    f"trace_id={self.trace_id}",
                    flush=True,
                )
                self._write_event(
                    "torch_profiler_error",
                    {"error_type": type(exc).__name__},
                )

        if not _same_thread and _start_thread_id is not None:
            log.warning(
                "Torch profiler started on thread %s but stopped on thread %s",
                _start_thread_id,
                _stop_thread_id,
            )

    # ── Stop Tracing ─────────────────────────────────────────────────────────────────

    def stop_tracing(self) -> dict[str, Any]:
        """Stop all tracing in order: resource sampler → VizTracer → metadata.

        Idempotent and safe.  Torch profiler must be explicitly stopped
        on the PromptExecutor thread before ``stop_tracing()`` is called
        from the async artifact worker.

        Reports sanitized diagnostics on failure.
        Once stopped, no further milestones may be captured.
        """
        if self._trace_stopped_result is not None:
            return dict(self._trace_stopped_result)

        result: dict[str, Any] = {
            "trace_id": self.trace_id,
            "state_before": self._state,
        }

        # ── 1. Torch profiler (stopped explicitly before stop_tracing) ──
        torch_result: dict[str, Any] = {}
        result["torch_profiler"] = torch_result

        # ── 2. Stop resource sampler ────────────────────────────────────────────────
        sampler_result: dict[str, Any] = {}
        if self._resource_sampler is not None:
            try:
                sampler_result = self._resource_sampler.stop()
            except Exception as exc:
                sampler_result = {"error_type": type(exc).__name__}
                log.warning("Resource sampler stop error")
                print(
                    f"[v2.full_trace] stage=stop_resource_sampler "
                    f"status=error error_type={type(exc).__name__} "
                    f"trace_id={self.trace_id}",
                    flush=True,
                )
        result["resource_sampler"] = sampler_result

        # ── 3. Stop & save VizTracer ───────────────────────────────────────────────
        viz_result: dict[str, Any] = {}
        if self._viztracer is not None:
            _viz_stop_started = time.perf_counter()
            _viz_stop_ms = 0.0
            _viz_save_ms = 0.0
            _viz_gzip_ms = 0.0
            try:
                _entry_capacity = getattr(self._viztracer, "tracer_entries", 0) or 0
                _phase_started = time.perf_counter()
                self._viztracer.stop()
                _viz_stop_ms = round((time.perf_counter() - _phase_started) * 1000, 3)
                _entry_count = getattr(self._viztracer, "data", None)
                if _entry_count is None:
                    # Parsing the saved trace here makes finalization scale with
                    # the full profiler output.  The cheap live data length is
                    # sufficient when available; otherwise leave the count
                    # unknown rather than turning a diagnostic into a request
                    # critical read/parse.
                    _entry_count = None
                else:
                    _entry_count = len(_entry_count) if hasattr(_entry_count, "__len__") else 0
                viz_path = self._base_dir / "raw" / "viztracer.json"
                _phase_started = time.perf_counter()
                self._viztracer.save(str(viz_path))
                _viz_save_ms = round((time.perf_counter() - _phase_started) * 1000, 3)
                _phase_started = time.perf_counter()
                self._gzip_file(viz_path)
                _viz_gzip_ms = round((time.perf_counter() - _phase_started) * 1000, 3)
                viz_path.unlink(missing_ok=True)
                viz_result = {
                    "saved": True,
                    "path": str(viz_path.with_name("viztracer.json.gz")),
                    "entry_count": _entry_count,
                    "entry_capacity": _entry_capacity,
                    "stop_ms": _viz_stop_ms,
                    "save_ms": _viz_save_ms,
                    "gzip_ms": _viz_gzip_ms,
                    "total_ms": round((time.perf_counter() - _viz_stop_started) * 1000, 3),
                }
            except Exception as exc:
                viz_result = {
                    "saved": False,
                    "error_type": type(exc).__name__,
                    "stop_ms": _viz_stop_ms,
                    "save_ms": _viz_save_ms,
                    "gzip_ms": _viz_gzip_ms,
                    "total_ms": round((time.perf_counter() - _viz_stop_started) * 1000, 3),
                }
                log.warning("VizTracer save error")
                print(
                    f"[v2.full_trace] stage=stop_viztracer "
                    f"status=error error_type={type(exc).__name__} "
                    f"trace_id={self.trace_id}",
                    flush=True,
                )
            finally:
                try:
                    self._viztracer = None
                except Exception:
                    pass
        result["viztracer"] = viz_result

        # ── 4. Transition to trace_stopped ──────────────────────────────────────────
        self._transition("trace_stopped")
        self._stopped.set()

        # ── 5. Write runtime_result_summary.json ────────────────────────────────────
        summary = dict(self._result_summary)
        end_time = time.time()
        summary.update({
            "trace_id": self.trace_id,
            "schema_version": self.schema_version,
            "trace_stopped_at": end_time,
            "trace_stopped_at_iso": datetime.fromtimestamp(
                end_time, tz=timezone.utc,
            ).isoformat(),
            "elapsed_seconds": end_time - self._start_time,
            "final_state": self._state,
        })
        self._write_json("runtime_result_summary.json", summary)
        result["summary"] = {
            "path": str(self._base_dir / "raw" / "runtime_result_summary.json"),
        }

        result["final_state"] = self._state
        self._trace_stopped_result = result
        return dict(result)

    def _gzip_file(self, path: Path) -> None:
        """Gzip *path* in-place; removes original and leaves ``.gz``."""
        gz_path = path.with_suffix(path.suffix + ".gz")
        try:
            with open(path, "rb") as src, gzip.open(gz_path, "wb") as dst:
                dst.write(src.read())
        except OSError as exc:
            log.warning("Gzip failed for %s: %s", path.name, exc)

    # ── Result summary ───────────────────────────────────────────────────────────────

    def set_result_summary(self, data: dict[str, Any]) -> None:
        """Update the result summary that will be written at stop time."""
        self._result_summary.update(data)

    def register_active_function(self, name: str, func: Callable) -> None:
        """Register an active wrapper function for snapshot inclusion."""
        self._active_functions[name] = func

    # ── Properties ───────────────────────────────────────────────────────────────────

    def raw_session_dir(self) -> Path:
        """Return the ``raw/`` subdirectory path."""
        return self._base_dir / "raw"

    def status_dict(self) -> dict[str, Any]:
        """Return a JSON-safe status summary of the current session state."""
        return {
            "trace_id": self.trace_id,
            "schema_version": self.schema_version,
            "state": self._state,
            "container_session_id": self._container_session_id,
            "identity": {
                "restored_instance_id": self._restored_instance_id,
                "restore_session_id": self._restore_session_id,
                "modal_task_id": self._modal_task_id,
                "image_id": self._image_id,
                "cloud": self._cloud,
                "region": self._region,
            },
            "claimed": self._claimed,
            "claimed_request_id": self._claimed_request_id,
            "has_viztracer": self._viztracer is not None,
            "has_torch_profiler": self._torch_profiler is not None,
            "has_resource_sampler": self._resource_sampler is not None,
            "start_time": self._start_time,
            "start_monotonic_ns": self._start_mono_ns,
            "elapsed_seconds": time.time() - self._start_time,
            "base_dir": str(self._base_dir),
            "raw_dir": str(self._base_dir / "raw"),
        }

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def events_path(self) -> Path | None:
        return self._events_path

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    @property
    def resource_sampler(self) -> ContainerResourceSampler | None:
        return self._resource_sampler

    @contextlib.contextmanager
    def golden_trace_scope(self):
        """Bind Golden spans to this session's exact VizTracer instance.

        The tracer is read when the request scope is entered, before any
        suspension in Golden execution.  Binding ``None`` is intentional: an
        unavailable owner must not fall through to a different global tracer.
        """
        with bind_golden_tracer(self._viztracer):
            yield

    def close_for_exit(self, *, timeout: float = 0.5) -> dict[str, Any]:
        """Stop runtime tracing services without packaging or volume writes."""
        result: dict[str, Any] = {"state": self._state}
        sampler = self._resource_sampler
        if sampler is not None:
            result["resource_sampler"] = sampler.stop(timeout=timeout)
            self._resource_sampler = None
        with self._torch_profiler_lock:
            profiler = self._torch_profiler
            self._torch_profiler = None
            self._torch_profiler_active = False
        if profiler is not None:
            try:
                profiler.__exit__(None, None, None)
                result["torch_profiler"] = "stopped_without_export"
            except Exception as exc:
                result["torch_profiler"] = {"error_type": type(exc).__name__}
        viztracer = self._viztracer
        self._viztracer = None
        if viztracer is not None:
            try:
                viztracer.stop()
                result["viztracer"] = "stopped_without_export"
            except Exception as exc:
                result["viztracer"] = {"error_type": type(exc).__name__}
        return result


# ═══════════════════════════════════════════════════════════════════════════════════
# Module-level re-exports for backward compat
# ═══════════════════════════════════════════════════════════════════════════════════

# Private compat aliases (not in public API spec, but harmless)
# complete_restore = set_restore_complete  # not exported
# start_request_tracing handled internally
