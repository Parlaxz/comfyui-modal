"""Generic cross-process trace control for the full-trace profiler.

This module is the *only* process-boundary integration the Golden exhaustive
profiler needs.  It deliberately contains no per-function instrumentation and no
knowledge of any particular Golden helper: it exposes a process-boundary
protocol that any worker/control surface can call.

Two independent cases are supported, because inheritance cannot solve both:

``Case A -- child spawned during an active traced request``
    The parent exports the trace identity through the child's environment
    (:func:`child_trace_env`).  A child that boots with that environment starts
    its own tracer and writes a process-local trace plus a metadata sidecar.

``Case B -- persistent child already alive before the traced request``
    Trace inheritance cannot reach it.  The parent instead drives the child's
    existing control protocol with :meth:`ChildTraceController.trace_begin` /
    :meth:`ChildTraceController.trace_end` (TRACE_BEGIN / TRACE_END).  The
    controller is inert unless a trace is explicitly begun.

Clock alignment
---------------
Every process records ``base_time_nanoseconds`` (VizTracer's machine-monotonic
origin), ``time.monotonic_ns()`` and ``time.time_ns()``.  VizTracer emits
timestamps relative to that origin, so two processes whose origins agree are
directly comparable.  The offline reporter compares origins and reports
``CLOCK_ALIGNMENT=PROVEN`` only when every observed origin agrees inside a
documented tolerance; otherwise it reports ``UNPROVEN`` and refuses to draw a
cross-process timeline as if the timestamps were exact.  Nothing here guesses.

Nothing in this module imports VizTracer at import time, and every entry point
is a no-op when full tracing is disabled.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping

__all__ = [
    "TRACE_BRIDGE_SCHEMA",
    "ENV_TRACE_ID",
    "ENV_REQUEST_ID",
    "ENV_ROLE",
    "ENV_RAW_DIR",
    "ENV_ENTRIES",
    "ENV_INCLUDE_PATHS",
    "ENV_MAX_STACK_DEPTH",
    "ENV_EXHAUSTIVE",
    "DEFAULT_TRACE_ENTRIES",
    "DEFAULT_MAX_STACK_DEPTH",
    "MAX_CLOCK_SKEW_NS",
    "env_flag",
    "exhaustive_profile_enabled",
    "clock_anchors",
    "child_trace_env",
    "apply_trace_env",
    "register_child_process",
    "process_role_for_entrypoint",
    "ProcessTraceRegistry",
    "ChildTraceController",
    "get_child_trace_controller",
    "session_trace_env",
    "register_session_process",
    "mark_session_process_traced",
    "reset_registries_for_tests",
]

TRACE_BRIDGE_SCHEMA = "comfymodal.process-trace-bridge/1"

ENV_TRACE_ID = "COMFYMODAL_TRACE_ID"
ENV_REQUEST_ID = "COMFYMODAL_TRACE_REQUEST_ID"
ENV_ROLE = "COMFYMODAL_TRACE_ROLE"
ENV_RAW_DIR = "COMFYMODAL_TRACE_RAW_DIR"
ENV_ENTRIES = "COMFYMODAL_TRACE_ENTRIES"
ENV_INCLUDE_PATHS = "COMFYMODAL_TRACE_INCLUDE_PATHS"
ENV_MAX_STACK_DEPTH = "COMFYMODAL_TRACE_MAX_STACK_DEPTH"
ENV_EXHAUSTIVE = "COMFYMODAL_GOLDEN_EXHAUSTIVE_PROFILE"

#: Default trace-entry capacity for a child tracer.  Matches the parent's
#: default so a child is not the first thing to overflow a merged request.
DEFAULT_TRACE_ENTRIES = 8_000_000

#: Default Python-call nesting depth retained per process.
DEFAULT_MAX_STACK_DEPTH = 64

#: Two process-local VizTracer clock origins further apart than this cannot be
#: attributed to one machine-monotonic origin, so a merged timeline would be
#: misleading.  The measured production-007 parent/child skew is 3 ns.
MAX_CLOCK_SKEW_NS = 1_000_000  # 1 ms

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def env_flag(name: str, env: Mapping[str, str] | None = None) -> bool:
    """Return whether *name* is set to a truthy value.  Never raises."""
    source = os.environ if env is None else env
    try:
        return str(source.get(name) or "").strip().lower() in _TRUE_VALUES
    except Exception:
        return False


def exhaustive_profile_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return whether the exhaustive Golden report should be rendered.

    This is a *report-rendering* selector only.  It never changes execution and
    never activates a profiler on its own: capture stays owned exclusively by
    the full-trace session.
    """
    return env_flag(ENV_EXHAUSTIVE, env)


def _viztracer_version(module: Any = None) -> str:
    try:
        if module is None:
            import viztracer as module  # type: ignore  # noqa: PLC0415
        return str(getattr(module, "__version__", None) or "unknown")
    except Exception:
        return "unknown"


def _safe_base_time(tracer: Any) -> int | None:
    """Return VizTracer's clock origin for *tracer*, or ``None`` if unavailable."""
    try:
        getter = getattr(tracer, "get_base_time", None)
        if callable(getter):
            return int(str(getter()))
    except Exception:
        pass
    return None


def clock_anchors(tracer: Any = None) -> dict[str, Any]:
    """Return this process's clock anchors.

    ``base_time_nanoseconds`` stays ``None`` rather than being fabricated when
    no tracer (or no tracer with a retrievable origin) is available.
    """
    anchors: dict[str, Any] = {
        "pid": os.getpid(),
        "parent_pid": os.getppid(),
        "monotonic_ns": time.monotonic_ns(),
        "time_ns": time.time_ns(),
        "base_time_nanoseconds": _safe_base_time(tracer) if tracer is not None else None,
        "viztracer_version": _viztracer_version() if tracer is not None else "unknown",
    }
    return anchors


def process_role_for_entrypoint(
    argv: Iterable[str] | None = None,
    *,
    fallback_module: str | None = None,
) -> str:
    """Derive a truthful, human-readable role for an unattributed process.

    Roles are only asserted when the evidence supports them.  Anything that
    cannot be attributed becomes ``other:<module>`` rather than a guess such as
    ``loader_worker``.
    """
    args = [str(a) for a in (argv if argv is not None else [])]
    # A script argument is stronger evidence than the interpreter that runs it:
    # every Python process starts with some python*, but only the script says
    # what the process is for.
    for arg in args:
        base = os.path.basename(arg)
        if base.endswith(".py"):
            return f"other:{base[:-3] or 'python'}"
    for arg in args:
        base = os.path.basename(arg)
        if base and base not in ("-c", "-m") and base.startswith("python"):
            return "other:python"
    if fallback_module:
        return f"other:{fallback_module}"
    if args:
        return f"other:{os.path.basename(args[0]) or 'unknown'}"
    return "other:unknown"


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


# ---------------------------------------------------------------------------
# Parent side: trace identity export and dynamic process registry
# ---------------------------------------------------------------------------


def child_trace_env(
    base_env: Mapping[str, str] | None = None,
    *,
    trace_id: str,
    request_id: str,
    role: str,
    raw_dir: str | os.PathLike[str],
    include_paths: Iterable[str] | None = None,
    entries: int = DEFAULT_TRACE_ENTRIES,
    max_stack_depth: int = DEFAULT_MAX_STACK_DEPTH,
    exhaustive: bool = True,
) -> dict[str, str]:
    """Return an environment mapping that arms a spawning child (Case A).

    A child that boots with this environment records its own trace with no
    cooperation from the parent beyond spawning it.  The mapping is additive so
    a caller can layer it onto a child environment without dropping the
    caller's own variables.
    """
    env = dict(base_env) if base_env is not None else dict(os.environ)
    env[ENV_TRACE_ID] = str(trace_id)
    env[ENV_REQUEST_ID] = str(request_id)
    env[ENV_ROLE] = str(role)
    env[ENV_RAW_DIR] = str(raw_dir)
    env[ENV_ENTRIES] = str(_positive_int(entries, DEFAULT_TRACE_ENTRIES))
    env[ENV_MAX_STACK_DEPTH] = str(_positive_int(max_stack_depth, DEFAULT_MAX_STACK_DEPTH))
    try:
        env[ENV_INCLUDE_PATHS] = json.dumps(sorted(str(p) for p in include_paths or ()))
    except Exception:
        env[ENV_INCLUDE_PATHS] = "[]"
    if exhaustive:
        env[ENV_EXHAUSTIVE] = "1"
    return env


def apply_trace_env(env: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    """Adopt an inherited trace identity in this process.

    Returns the adopted identity, or ``None`` when this process was not spawned
    under an active trace.  Reading the environment is the only side effect; no
    tracer is created here.
    """
    source = os.environ if env is None else env
    trace_id = str(source.get(ENV_TRACE_ID) or "").strip()
    if not trace_id:
        return None
    try:
        include = json.loads(str(source.get(ENV_INCLUDE_PATHS) or "[]"))
    except Exception:
        include = []
    if not isinstance(include, list):
        include = []
    return {
        "schema_version": TRACE_BRIDGE_SCHEMA,
        "trace_id": trace_id,
        "request_id": str(source.get(ENV_REQUEST_ID) or ""),
        "role": str(source.get(ENV_ROLE) or ""),
        "raw_dir": str(source.get(ENV_RAW_DIR) or ""),
        "entries": _positive_int(source.get(ENV_ENTRIES), DEFAULT_TRACE_ENTRIES),
        "max_stack_depth": _positive_int(source.get(ENV_MAX_STACK_DEPTH), DEFAULT_MAX_STACK_DEPTH),
        "include_paths": [str(p) for p in include],
        "spawned_by_parent": True,
    }


def register_child_process(
    registry: "ProcessTraceRegistry | None",
    *,
    role: str,
    pid: int | None = None,
    parent_pid: int | None = None,
    kind: str = "spawn",
    lifetime: str = "request",
) -> dict[str, Any]:
    """Record a Golden-owned child process in *registry*.

    ``kind`` is ``spawn`` (created during the request) or ``persistent`` (already
    alive).  ``role`` must be truthful; pass ``other:<x>`` when it cannot be
    established.  A ``None`` *registry* still returns the record so a caller can
    record evidence when no session is attached.
    """
    record = {
        "role": str(role or "other:unknown"),
        "pid": int(pid) if pid is not None else None,
        "parent_pid": int(parent_pid) if parent_pid is not None else os.getppid(),
        "kind": str(kind),
        "lifetime": str(lifetime),
        "registered_at_ns": time.monotonic_ns(),
    }
    if registry is not None:
        record = registry.register(record)
    return record


class ProcessTraceRegistry:
    """Dynamic expected-process accounting for one traced request.

    The expected process set is built from what actually happens, so a topology
    with no children reports ``expected_processes=1`` and a topology with three
    source workers reports three -- with no hardcoded count anywhere.
    """
    def __init__(
        self,
        *,
        trace_id: str,
        request_id: str,
        raw_dir: str | os.PathLike[str],
    ) -> None:
        self.trace_id = str(trace_id)
        self.request_id = str(request_id)
        self.raw_dir = Path(raw_dir)
        self._lock = threading.Lock()
        self._processes: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self.register({
            "role": "parent",
            "pid": os.getpid(),
            "parent_pid": os.getppid(),
            "kind": "root",
            "lifetime": "container",
        })

    @staticmethod
    def _key(role: Any, pid: Any) -> str:
        return f"{role}#{pid}"

    def register(self, record: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            key = self._key(record.get("role"), record.get("pid"))
            merged = dict(self._processes.get(key) or {})
            merged.update({k: v for k, v in record.items() if v is not None})
            merged.setdefault("registered_at_ns", time.monotonic_ns())
            if key not in self._processes:
                self._order.append(key)
            self._processes[key] = merged
            return dict(merged)

    def mark_traced(
        self,
        role: str,
        pid: int | None,
        *,
        status: str,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        """Attach the observed capture outcome for one expected process."""
        with self._lock:
            key = self._key(role, pid)
            record = self._processes.get(key)
            if record is None:
                # An observed process nobody registered is still evidence; it is
                # recorded as ``observed`` rather than silently dropped.
                record = {
                    "role": role,
                    "pid": pid,
                    "parent_pid": os.getppid(),
                    "kind": "observed",
                    "lifetime": "request",
                    "registered_at_ns": time.monotonic_ns(),
                }
                self._order.append(key)
                self._processes[key] = record
            record["trace_status"] = str(status)
            if detail:
                record["trace_detail"] = dict(detail)

    def processes(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(self._processes[key]) for key in self._order]

    def expected_count(self) -> int:
        with self._lock:
            return len(self._processes)

    def to_dict(self) -> dict[str, Any]:
        processes = self.processes()
        return {
            "schema_version": TRACE_BRIDGE_SCHEMA,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "expected_processes": len(processes),
            "processes": processes,
        }

    def write(self) -> Path | None:
        """Persist the registry beside the session's raw artifacts."""
        try:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            path = self.raw_dir / "golden_process_registry.json"
            path.write_text(
                json.dumps(self.to_dict(), indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
            return path
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Parent-side integration used at a process-creation boundary
# ---------------------------------------------------------------------------


def session_trace_env(
    session: Any,
    *,
    role: str,
    base_env: Mapping[str, str],
    raw_dir: str | os.PathLike[str] | None = None,
) -> dict[str, str]:
    """Return *base_env* armed with the active session's trace identity.

    Returns *base_env* unchanged when there is no active traced session, so a
    process boundary with full tracing off keeps byte-identical behaviour.
    """
    identity = _session_identity(session)
    if identity is None:
        return dict(base_env)
    return child_trace_env(
        base_env,
        trace_id=identity["trace_id"],
        request_id=identity["request_id"],
        role=role,
        raw_dir=str(raw_dir or identity["raw_dir"]),
        include_paths=identity["include_paths"],
        entries=identity["entries"],
    )


def register_session_process(
    session: Any,
    *,
    role: str,
    pid: int | None = None,
    kind: str = "spawn",
    lifetime: str = "request",
    status: str = "expected",
) -> dict[str, Any] | None:
    """Register a Golden-owned child process with the active traced session.

    This is how the profiler learns the *expected* process set: from what the
    runtime actually creates, never from a hardcoded topology.  Returns ``None``
    when no traced session is active.
    """
    identity = _session_identity(session)
    if identity is None:
        return None
    registry = _session_registry(session, identity)
    record = register_child_process(
        registry, role=role, pid=pid, kind=kind, lifetime=lifetime,
    )
    registry.mark_traced(role, record.get("pid"), status=status)
    registry.write()
    return record


def mark_session_process_traced(
    session: Any,
    *,
    role: str,
    pid: int | None,
    status: str,
    detail: Mapping[str, Any] | None = None,
) -> None:
    """Record the observed capture outcome for an expected process."""
    identity = _session_identity(session)
    if identity is None:
        return
    registry = _session_registry(session, identity)
    registry.mark_traced(role, pid, status=status, detail=detail)
    registry.write()


def _session_identity(session: Any) -> dict[str, Any] | None:
    """Return the active session's trace identity, or ``None`` when inactive."""
    if session is None:
        return None
    try:
        if not bool(getattr(session, "enable", False)):
            return None
        trace_id = str(getattr(session, "trace_id", "") or "")
        if not trace_id:
            return None
        raw_dir = Path(str(session.base_dir)) / "raw"
        config: dict[str, Any] = {}
        update = getattr(session, "update_trace_config", None)
        if callable(update):
            update({})
        reader = getattr(session, "_read_trace_config", None)
        if callable(reader):
            loaded = reader()
            if isinstance(loaded, dict):
                config = loaded
        includes = config.get("include_paths") or {}
        resolved = includes.get("resolved") if isinstance(includes, Mapping) else None
        return {
            "trace_id": trace_id,
            "request_id": str(getattr(session, "_claimed_request_id", "") or ""),
            "raw_dir": str(raw_dir),
            "include_paths": [str(p) for p in (resolved or [])],
            "entries": _positive_int(config.get("entry_capacity"), DEFAULT_TRACE_ENTRIES),
        }
    except Exception:
        return None


_REGISTRIES: dict[str, ProcessTraceRegistry] = {}
_REGISTRIES_LOCK = threading.Lock()


def _session_registry(session: Any, identity: Mapping[str, Any]) -> ProcessTraceRegistry:
    key = str(identity.get("trace_id") or "")
    with _REGISTRIES_LOCK:
        registry = _REGISTRIES.get(key)
        if registry is None:
            registry = ProcessTraceRegistry(
                trace_id=key,
                request_id=str(identity.get("request_id") or ""),
                raw_dir=str(identity.get("raw_dir") or "/tmp/comfymodal_process_traces"),
            )
            _REGISTRIES[key] = registry
        return registry


def reset_registries_for_tests() -> None:
    """Drop cached per-trace registries.  Test-only seam."""
    with _REGISTRIES_LOCK:
        _REGISTRIES.clear()


# ---------------------------------------------------------------------------
# Child side: TRACE_BEGIN / TRACE_END
# ---------------------------------------------------------------------------


class ChildTraceController:
    """Process-local trace control for a Golden worker.

    Serves both process cases:

    * Case A -- :meth:`adopt_spawn_identity` arms the controller from an
      inherited environment; ``TRACE_BEGIN``/``TRACE_END`` then bracket the
      child's life.
    * Case B -- a persistent worker that already exists calls
      :meth:`trace_begin` when the parent sends TRACE_BEGIN and
      :meth:`trace_end` on TRACE_END, so only the commands belonging to the
      traced request are traced.

    Every method is inert unless tracing was actually requested.  No tracer is
    imported or created before a TRACE_BEGIN arrives, so an untraced request
    pays nothing beyond a lock and a dict lookup.
    """

    def __init__(self, *, role: str | None = None) -> None:
        self.role = str(role or "")
        self._lock = threading.Lock()
        self._tracer: Any = None
        self._identity: dict[str, Any] | None = None
        self._segments: list[dict[str, Any]] = []

    # -- introspection ----------------------------------------------------

    @property
    def active(self) -> bool:
        with self._lock:
            return self._tracer is not None

    def status(self) -> dict[str, Any]:
        with self._lock:
            identity = self._identity or {}
            return {
                "active": self._tracer is not None,
                "role": self.role,
                "trace_id": identity.get("trace_id"),
                "request_id": identity.get("request_id"),
                "segments": len(self._segments),
                "last_error": identity.get("last_error"),
            }

    # -- Case A -----------------------------------------------------------

    def adopt_spawn_identity(
        self, identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Arm this process from an inherited (or supplied) trace identity.

        No tracer is started here: the caller decides the lifetime, so the same
        method serves both a spawn-armed child and a persistent worker.
        """
        resolved = dict(identity) if identity else apply_trace_env()
        if not resolved:
            return None
        with self._lock:
            if not self.role:
                self.role = (
                    str(resolved.get("role") or "")
                    or process_role_for_entrypoint()
                )
            self._identity = dict(resolved)
            return dict(self._identity)

    # -- TRACE_BEGIN / TRACE_END -----------------------------------------

    def trace_begin(
        self,
        *,
        trace_id: str,
        request_id: str = "",
        role: str | None = None,
        raw_dir: str | os.PathLike[str] | None = None,
        include_paths: Iterable[str] | None = None,
        entries: int = DEFAULT_TRACE_ENTRIES,
        max_stack_depth: int = DEFAULT_MAX_STACK_DEPTH,
        thread_tracing: bool = True,
    ) -> dict[str, Any]:
        """Begin tracing this process for one traced request.

        Idempotent for a repeated TRACE_BEGIN carrying the same ``trace_id``:
        a retried control message must never double-instrument the worker.
        """
        started_ns = time.monotonic_ns()
        with self._lock:
            prior = self._identity or {}
            resolved_role = str(role or self.role or prior.get("role") or "")
            self.role = resolved_role or process_role_for_entrypoint()
            if self._tracer is not None:
                if str(prior.get("trace_id")) == str(trace_id):
                    return {
                        "status": "already_active",
                        "trace_id": str(trace_id),
                        "role": self.role,
                    }
            resolved_raw_dir = Path(
                str(raw_dir or prior.get("raw_dir") or "/tmp/comfymodal_process_traces")
            )
            resolved_includes = list(
                include_paths if include_paths is not None
                else (prior.get("include_paths") or [])
            )
            identity: dict[str, Any] = {
                "schema_version": TRACE_BRIDGE_SCHEMA,
                "trace_id": str(trace_id),
                "request_id": str(request_id),
                "role": self.role,
                "pid": os.getpid(),
                "parent_pid": os.getppid(),
                "raw_dir": str(resolved_raw_dir),
                "raw_trace_path": str(resolved_raw_dir / f"viztracer_{os.getpid()}.json"),
                "include_paths": [str(p) for p in resolved_includes],
                "entry_capacity": _positive_int(entries, DEFAULT_TRACE_ENTRIES),
                "max_stack_depth": _positive_int(max_stack_depth, DEFAULT_MAX_STACK_DEPTH),
                "started_mono_ns": started_ns,
                "started_time_ns": time.time_ns(),
                "base_time_nanoseconds": None,
                "viztracer_version": "unknown",
                "spawned_by_parent": bool(prior.get("spawned_by_parent")),
                "trace_control": "TRACE_BEGIN",
                "status": "pending",
            }
            self._identity = identity
        try:
            tracer = _create_tracer(
                raw_dir=Path(identity["raw_dir"]),
                entry_capacity=identity["entry_capacity"],
                max_stack_depth=identity["max_stack_depth"],
                include_paths=identity["include_paths"],
                output_file=identity["raw_trace_path"],
            )
        except BaseException as exc:  # noqa: BLE001 - evidence, never fatal
            return self._fail_begin(identity, f"{type(exc).__name__}: {exc}"[:240])
        if tracer is None:
            return self._fail_begin(identity, "viztracer_import_failed")
        with self._lock:
            identity["base_time_nanoseconds"] = _safe_base_time(tracer)
            identity["viztracer_version"] = _viztracer_version()
            self._tracer = tracer
            self._segments.append({
                "trace_id": str(trace_id),
                "request_id": str(request_id),
                "begin_mono_ns": started_ns,
            })
        try:
            tracer.start()
            if thread_tracing:
                # Threads created *after* activation only get the profile hook
                # through this explicit handoff; register_global alone does not
                # do it in VizTracer 1.1.1.
                hook = getattr(tracer, "enable_thread_tracing", None)
                if callable(hook):
                    hook()
            identity["status"] = "active"
        except BaseException as exc:  # noqa: BLE001
            with self._lock:
                self._tracer = None
            return self._fail_begin(identity, f"{type(exc).__name__}: {exc}"[:240])
        return {
            "status": "started",
            "trace_id": str(trace_id),
            "request_id": str(request_id),
            "role": identity["role"],
            "pid": identity["pid"],
            "base_time_nanoseconds": identity["base_time_nanoseconds"],
            "viztracer_version": identity["viztracer_version"],
        }

    def _fail_begin(self, identity: dict[str, Any], error: str) -> dict[str, Any]:
        identity["status"] = "unavailable"
        identity["last_error"] = error
        with self._lock:
            self._identity = identity
        return {
            "status": "unavailable",
            "trace_id": identity.get("trace_id"),
            "request_id": identity.get("request_id"),
            "role": identity.get("role"),
            "pid": identity.get("pid"),
            "error": error,
        }

    def trace_end(self, *, trace_id: str | None = None) -> dict[str, Any]:
        """Stop tracing, then write this process's raw trace plus metadata."""
        ended_ns = time.monotonic_ns()
        with self._lock:
            tracer = self._tracer
            identity = dict(self._identity or {})
        if tracer is None:
            return {"status": "inactive", "trace_id": str(trace_id or "")}
        active_id = str(identity.get("trace_id") or "")
        if trace_id and active_id and str(trace_id) != active_id:
            # A late TRACE_END from a previous request must not close this one,
            # and it must not drop the live tracer either.
            return {
                "status": "mismatch",
                "trace_id": str(trace_id),
                "active_trace_id": active_id,
            }
        with self._lock:
            # Re-check under the lock: a concurrent TRACE_BEGIN may have taken
            # over between the validation and here.
            if self._tracer is not tracer:
                return {
                    "status": "mismatch",
                    "trace_id": str(trace_id or active_id),
                    "active_trace_id": str((self._identity or {}).get("trace_id") or ""),
                }
            self._tracer = None
        identity["ended_mono_ns"] = ended_ns
        identity["ended_time_ns"] = time.time_ns()
        identity["trace_control"] = "TRACE_END"
        try:
            tracer.stop()
        except BaseException as exc:  # noqa: BLE001
            identity["stop_error"] = f"{type(exc).__name__}: {exc}"[:240]
        raw_path = Path(str(identity.get("raw_trace_path") or ""))
        entry_count = 0
        capacity = _positive_int(identity.get("entry_capacity"), DEFAULT_TRACE_ENTRIES)
        truncated = False
        if raw_path.name:
            try:
                tracer.save(str(raw_path))
                entry_count = int(tracer.parse() or 0)
                capacity = _positive_int(
                    getattr(tracer, "tracer_entries", capacity), capacity,
                )
                truncated = entry_count >= capacity
            except BaseException as exc:  # noqa: BLE001
                identity["save_error"] = f"{type(exc).__name__}: {exc}"[:240]
                truncated = False
        identity["trace_entry_count"] = entry_count
        identity["trace_entry_capacity"] = capacity
        identity["truncated"] = truncated
        identity["status"] = "saved"
        meta_path = self._write_metadata(identity)
        return {
            "status": "saved",
            "trace_id": identity.get("trace_id"),
            "request_id": identity.get("request_id"),
            "role": identity.get("role"),
            "pid": identity.get("pid"),
            "parent_pid": identity.get("parent_pid"),
            "raw_trace_path": str(raw_path),
            "metadata_path": str(meta_path or ""),
            "trace_entry_count": entry_count,
            "trace_entry_capacity": capacity,
            "truncated": truncated,
            "base_time_nanoseconds": identity.get("base_time_nanoseconds"),
            "viztracer_version": identity.get("viztracer_version"),
        }

    def _write_metadata(self, identity: Mapping[str, Any]) -> Path | None:
        """Persist the per-process metadata sidecar beside the raw trace."""
        try:
            raw_path = Path(str(identity.get("raw_trace_path") or ""))
            if not raw_path.name:
                return None
            path = raw_path.with_suffix(".meta.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(dict(identity), indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
            return path
        except Exception:
            return None


def _create_tracer(
    *,
    raw_dir: Path,
    entry_capacity: int,
    max_stack_depth: int,
    include_paths: list[str],
    output_file: str,
) -> Any:
    """Create this process's VizTracer, or return ``None`` if unavailable.

    VizTracer is imported lazily and only here so a process that never receives
    a TRACE_BEGIN never imports it.  ``include_files`` is intentionally omitted:
    the whole point of the exhaustive profiler is to discover the real call tree
    dynamically, so narrowing the filter to the parent's requested list would
    hide new helpers added tomorrow.
    """
    try:
        from viztracer import VizTracer  # type: ignore  # noqa: PLC0415
    except Exception:
        return None
    raw_dir.mkdir(parents=True, exist_ok=True)
    return VizTracer(
        tracer_entries=int(entry_capacity),
        max_stack_depth=int(max_stack_depth),
        output_file=str(output_file),
        ignore_c_function=True,
        log_gc=False,
        log_async=True,
        file_info=True,
        register_global=True,
        trace_self=False,
        minimize_memory=True,
        log_func_args=False,
        log_func_retval=False,
        log_print=False,
        pid_suffix=False,
        verbose=0,
    )


_CONTROLLER_LOCK = threading.Lock()
_CONTROLLER: ChildTraceController | None = None


def get_child_trace_controller(*, role: str | None = None) -> ChildTraceController:
    """Return this process's single child-trace controller.

    One controller per process keeps TRACE_BEGIN idempotent and lets the parent
    address a worker without the worker keeping per-request state.
    """
    global _CONTROLLER
    with _CONTROLLER_LOCK:
        if _CONTROLLER is None:
            _CONTROLLER = ChildTraceController(role=role)
        elif role and not _CONTROLLER.role:
            _CONTROLLER.role = str(role)
        return _CONTROLLER


def _reset_child_trace_controller_for_tests() -> None:
    """Drop the process-wide controller.  Test-only seam."""
    global _CONTROLLER
    with _CONTROLLER_LOCK:
        _CONTROLLER = None
