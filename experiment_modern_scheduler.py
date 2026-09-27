"""Modern experiment scheduler (Phase D, lane L2).

In-process orchestration for experiment cells:

- immutable cell plans are used verbatim (never rebuilt, never re-resolved);
- global default concurrency is 6 and payload concurrency overrides are ignored;
- bounded dispatcher: ordered deque + strong active-task map +
  ``asyncio.wait(FIRST_COMPLETED)`` with immediate refill; no task-group
  construct, no all-tasks-up-front;
- per-cell isolation: an ordinary exception makes that cell's attempt
  ``failed`` while siblings keep running;
- first-terminal-wins and attempt-identity guards are enforced by the
  injected persistence adapter (History V2 is the durable truth);
- cancel/shutdown/resume/retry semantics follow STUDIO_MODERN_EXPERIMENT_
  MIGRATION_PLAN.md sections 6, 8, 9, 10;
- user cancel of a running cell is confirmation-gated: ``remote_cancel``
  must return an explicitly confirming ``CancelResult``/dict/``True`` before
  the semantic ``canceled`` terminal is persisted.  A ``None`` return is the
  explicit compatibility mode for legacy fakes/callables (fire-and-forget);
  an unconfirmed result or a channel failure leaves the durable running
  state truthful and reports ``"cancel_unconfirmed"``.  Shutdown always
  converges to ``interrupted`` after a best-effort stop, never ``canceled``.
- the process-local production binding (``build_experiment_scheduler``)
  constructs one scheduler per accepted Experiment with a shared per-
  experiment transport: the default execution closure binds each attempt to
  the transport and calls ``canonical_execution.execute_plan(..., transport=...)``
  verbatim, and the default ``remote_cancel`` resolves the attempt binding
  and routes through the transport-owned cancellation handle.  When
  ``execute_plan`` raises because the remote stream ended after an explicit
  confirmed ``cancelled`` event, the execution closure inspects the
  transport-owned handle snapshot (before releasing it) and reports
  ``{'status': 'canceled', ...}`` so ``_run_cell`` persists the durable
  ``canceled`` terminal instead of ``failed``.  These callables are lazily
  wired so the module still imports with only the standard library.

The frozen semantic operations (load queued cells, atomically claim a queued
attempt, read the current active attempt, record running, record terminal,
create/append retry/resume attempts, list recoverable cells, aggregate status
supplied by History) are expressed as runtime-checkable Protocols.  A narrow
``PersistenceAdapter`` wrapper maps likely adapter method names onto those
operations and raises loudly instead of inventing persistence truth.

The module imports only the standard library so it can be imported even when
sibling modules (``experiment_modern_plan``, routes, History) are absent.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Deque, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Set, Tuple, Union, runtime_checkable

logger = logging.getLogger(__name__)

EXPERIMENT_CONCURRENCY = 6

TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled", "interrupted"})


# ── Adapter record shapes ────────────────────────────────────────────────


@dataclass(frozen=True)
class AttemptClaim:
    attempt_id: str
    cell_id: str
    is_new: bool = False


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    cell_id: str
    status: str


@dataclass(frozen=True)
class CellRecord:
    cell_id: str
    attempt_id: Optional[str] = None
    status: Optional[str] = None


@dataclass(frozen=True)
class CancelResult:
    """Explicit outcome of a remote-cancel primitive invocation.

    A user cancel may only persist the semantic ``canceled`` terminal when a
    remote-cancel result *explicitly* confirms cancellation (``confirmed``
    truthy).  Anything else (``confirmed`` falsy, a bare ``False``, a dict
    without a confirming key, a channel error) leaves the durable running
    state truthful and reports a cancellation-unavailable outcome.
    """

    confirmed: bool = False
    outcome: str = ""
    detail: str = ""
    attempt_id: Optional[str] = None
    cell_id: Optional[str] = None


# ── Frozen semantic-operation protocols ──────────────────────────────────


@runtime_checkable
class ExperimentPersistenceProtocol(Protocol):
    def load_queued_cells(self) -> Iterable[CellRecord]: ...
    def atomically_claim_queued_attempt(self, cell_id: str) -> Optional[AttemptClaim]: ...
    def read_active_attempt(self, cell_id: str) -> Optional[AttemptRecord]: ...
    def record_running(self, attempt_id: str, cell_id: str) -> None: ...
    def record_terminal(self, attempt_id: str, cell_id: str, status: str, error: Optional[str] = None) -> bool: ...
    def create_resume_attempt(self, cell_id: str) -> Optional[AttemptClaim]: ...
    def create_retry_attempt(self, cell_id: str) -> Optional[AttemptClaim]: ...
    def list_recoverable_cells(self) -> Iterable[CellRecord]: ...
    def aggregate_status(self) -> str: ...


@runtime_checkable
class ExecuteCallable(Protocol):
    def __call__(self, plan: Any, *, attempt_id: str, cell_id: str) -> Optional[Union[None, Awaitable[None]]]: ...


@runtime_checkable
class RemoteCancelCallable(Protocol):
    """Remote cancellation primitive.

    A return of ``None`` is treated as a *legacy compatibility mode*: the
    callable does not participate in confirmation and the scheduler preserves
    the historical fire-and-forget behavior (cancel is recorded once the
    primitive is invoked).  Any non-``None`` return must explicitly confirm:
    ``CancelResult(confirmed=True)``, a dict with a truthy ``confirmed`` /
    ``ok`` / ``acknowledged`` / ``success`` key, or ``True``.  An unconfirmed
    result or a raised channel error never marks ``canceled``.
    """

    def __call__(
        self,
        attempt_id: str,
        cell_id: str,
        *,
        intent: str,
        reason: str,
    ) -> Optional[
        Union[
            None,
            bool,
            CancelResult,
            Mapping[str, Any],
            Awaitable[Any],
        ]
    ]: ...


# ── Result coercion (shape normalization only; never fabricates truth) ───


def _coerce_claim(value: Any) -> Optional[AttemptClaim]:
    if value is None:
        return None
    if isinstance(value, AttemptClaim):
        return value
    if isinstance(value, Mapping):
        status = str(
            value.get("status")
            or value.get("reason")
            or value.get("outcome")
            or ""
        ).lower()
        if value.get("already_claimed") or value.get("claimed") is False or status in {
            "already_claimed", "already claimed", "claim_lost", "not_claimed",
            "terminal", "not_found", "claim_terminal",
        }:
            return None
        nested = value.get("attempt")
        if nested is not None:
            nested_claim = _coerce_claim(nested)
            if nested_claim is not None:
                return AttemptClaim(
                    attempt_id=nested_claim.attempt_id,
                    cell_id=(
                        str(value.get("cell_id") or value.get("cell_key"))
                        if value.get("cell_id") or value.get("cell_key")
                        else nested_claim.cell_id
                    ),
                    is_new=bool(value.get("is_new", nested_claim.is_new)),
                )
        attempt_id = value.get("attempt_id") or value.get("run_id") or value.get("id")
        if attempt_id is None:
            return None
        return AttemptClaim(
            attempt_id=str(attempt_id),
            cell_id=str(value.get("cell_id") or value.get("cell_key") or ""),
            is_new=bool(value.get("is_new", False)),
        )
    if isinstance(value, (tuple, list)):
        if not value:
            return None
        if isinstance(value[0], str) and value[0].lower() in {
            "already_claimed", "already claimed", "claim_lost", "not_claimed",
        }:
            return None
        return AttemptClaim(
            attempt_id=str(value[0]),
            cell_id=str(value[1]) if len(value) > 1 else "",
        )
    if isinstance(value, bool):
        return None
    outcome = str(getattr(value, "outcome", "") or "").lower()
    if outcome in {
        "already_claimed", "already claimed", "claim_lost", "not_claimed",
        "terminal", "not_found", "claim_terminal",
    }:
        return None
    nested = getattr(value, "attempt", None)
    if nested is not None:
        nested_claim = _coerce_claim(nested)
        if nested_claim is not None:
            return AttemptClaim(
                attempt_id=nested_claim.attempt_id,
                cell_id=str(
                    getattr(value, "cell_id", None)
                    or getattr(value, "cell_key", None)
                    or nested_claim.cell_id
                ),
                is_new=bool(getattr(value, "is_new", nested_claim.is_new)),
            )
    attempt_id = getattr(value, "attempt_id", None) or getattr(value, "run_id", None)
    if attempt_id is None:
        if isinstance(value, str) and value.lower() in {
            "already_claimed", "already claimed", "claim_lost", "not_claimed",
        }:
            return None
        return AttemptClaim(attempt_id=str(value), cell_id="")
    return AttemptClaim(
        attempt_id=str(attempt_id),
        cell_id=str(getattr(value, "cell_id", None) or getattr(value, "cell_key", "")),
        is_new=bool(getattr(value, "is_new", False)),
    )


def _coerce_attempt_record(value: Any) -> Optional[AttemptRecord]:
    if value is None:
        return None
    if isinstance(value, AttemptRecord):
        return value
    if isinstance(value, Mapping):
        attempt_id = value.get("attempt_id") or value.get("run_id") or value.get("id")
        if attempt_id is None:
            return None
        return AttemptRecord(
            attempt_id=str(attempt_id),
            cell_id=str(value.get("cell_id") or value.get("cell_key") or ""),
            status=str(value.get("status") or "queued"),
        )
    if isinstance(value, (tuple, list)):
        if not value:
            return None
        return AttemptRecord(
            attempt_id=str(value[0]),
            cell_id=str(value[1]) if len(value) > 1 else "",
            status=str(value[2]) if len(value) > 2 else "queued",
        )
    attempt_id = getattr(value, "attempt_id", None) or getattr(value, "run_id", None)
    if attempt_id is not None:
        return AttemptRecord(
            attempt_id=str(attempt_id),
            cell_id=str(getattr(value, "cell_id", None) or getattr(value, "cell_key", "")),
            status=str(getattr(value, "status", "queued") or "queued"),
        )
    return AttemptRecord(attempt_id=str(value), cell_id="", status="queued")


def _coerce_cancel_result(value: Any) -> Optional[CancelResult]:
    """Normalize a remote-cancel return into a ``CancelResult``.

    Only *explicit* confirmation counts.  ``None`` is handled by the caller
    as the legacy compatibility mode and never reaches this function; any
    shape that does not carry a truthy confirming signal is coerced to an
    unconfirmed ``CancelResult`` (safe default: never fabricate ``canceled``).
    """
    if value is None:
        return None
    if isinstance(value, CancelResult):
        return value
    if isinstance(value, bool):
        return CancelResult(confirmed=value)
    if isinstance(value, Mapping):
        confirmed = False
        for key in ("confirmed", "ok", "acknowledged", "success", "cancelled", "canceled"):
            if key in value:
                confirmed = bool(value.get(key))
                break
        return CancelResult(
            confirmed=confirmed,
            outcome=str(value.get("outcome") or ""),
            detail=str(
                value.get("detail")
                or value.get("message")
                or value.get("reason")
                or ""
            ),
            attempt_id=(
                str(value["attempt_id"]) if value.get("attempt_id") else None
            ),
            cell_id=(
                str(value["cell_id"])
                if value.get("cell_id") or value.get("cell_key")
                else None
            ),
        )
    if isinstance(value, (tuple, list)):
        # ``(bool,)`` carries an explicit confirmation; anything else is
        # unconfirmed rather than guessed.
        if value and isinstance(value[0], bool):
            return CancelResult(confirmed=value[0])
        return CancelResult(confirmed=False)
    confirmed = False
    for key in ("confirmed", "ok", "acknowledged", "success", "cancelled", "canceled"):
        if hasattr(value, key):
            confirmed = bool(getattr(value, key))
            break
    return CancelResult(
        confirmed=confirmed,
        outcome=str(getattr(value, "outcome", None) or ""),
        detail=str(
            getattr(value, "detail", None)
            or getattr(value, "message", None)
            or getattr(value, "reason", None)
            or ""
        ),
        attempt_id=(
            str(getattr(value, "attempt_id", None))
            if getattr(value, "attempt_id", None)
            else None
        ),
        cell_id=(
            str(getattr(value, "cell_id", None))
            if getattr(value, "cell_id", None) or getattr(value, "cell_key", None)
            else None
        ),
    )


def _coerce_cell_records(value: Any) -> List[CellRecord]:
    if value is None:
        return []
    records: List[CellRecord] = []
    for item in value or []:
        if isinstance(item, CellRecord):
            records.append(item)
        elif isinstance(item, Mapping):
            cell_id = item.get("cell_id") or item.get("cell_key")
            if cell_id is None:
                continue
            attempt_id = item.get("attempt_id") or item.get("run_id")
            records.append(CellRecord(
                cell_id=str(cell_id),
                attempt_id=str(attempt_id) if attempt_id else None,
                status=item.get("status"),
            ))
        elif isinstance(item, (tuple, list)) and item:
            records.append(CellRecord(
                cell_id=str(item[0]),
                attempt_id=str(item[1]) if len(item) > 1 and item[1] else None,
                status=str(item[2]) if len(item) > 2 else None,
            ))
        else:
            cell_id = getattr(item, "cell_id", None) or getattr(item, "cell_key", None)
            if cell_id is not None:
                attempt_id = getattr(item, "attempt_id", None) or getattr(item, "run_id", None)
                records.append(CellRecord(
                    cell_id=str(cell_id),
                    attempt_id=str(attempt_id) if attempt_id else None,
                    status=getattr(item, "status", None),
                ))
    return records


def _plan_cell_id(plan: Any) -> Optional[str]:
    if plan is None:
        return None
    for key in ("cell_id", "cell_key", "id"):
        if isinstance(plan, Mapping):
            val = plan.get(key)
        else:
            val = getattr(plan, key, None)
        if val is not None:
            return str(val)
    return None


def _plan_field(plan: Any, key: str, default: Any = None) -> Any:
    if isinstance(plan, Mapping):
        return plan.get(key, default)
    return getattr(plan, key, default)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _invoke(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return await _maybe_await(fn(*args, **kwargs))


def _noop(*args: Any, **kwargs: Any) -> None:
    return None


@dataclass(frozen=True)
class _CancelOutcome:
    """Classification of one remote-cancel primitive invocation.

    ``mode`` is one of:
    - ``"confirmed"``: the callable returned an explicitly confirming result;
    - ``"legacy"``: the callable returned ``None`` (explicit compatibility
      mode; historical fire-and-forget behavior, treated as confirmed);
    - ``"unconfirmed"``: the callable returned a result that did not confirm;
    - ``"error"``: the callable raised (channel failure).
    """

    confirmed: bool = False
    mode: str = "unconfirmed"
    result: Optional[CancelResult] = None


# ── Narrow persistence adapter wrapper ───────────────────────────────────


_METHOD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "load_queued_cells": ("load_queued_cells", "load_queued", "get_queued_cells", "queued_cells"),
    "atomically_claim_queued_attempt": ("atomically_claim_queued_attempt", "claim_queued_attempt", "claim_attempt", "try_claim_attempt"),
    "read_active_attempt": ("read_active_attempt", "get_active_attempt", "current_attempt", "active_attempt"),
    "record_running": ("record_running", "mark_running", "transition_running", "set_running"),
    "record_terminal": ("record_terminal", "record_attempt_terminal", "update_attempt_terminal", "mark_terminal", "write_terminal", "set_terminal"),
    "create_resume_attempt": ("create_resume_attempt", "create_attempt_for_resume", "new_resume_attempt", "resume_attempt"),
    "create_retry_attempt": ("create_retry_attempt", "create_attempt_for_retry", "new_retry_attempt", "retry_attempt"),
    "list_recoverable_cells": ("list_recoverable_cells", "recoverable_cells", "get_recoverable_cells", "list_resumable_cells"),
    "aggregate_status": ("aggregate_status", "derive_experiment_status", "get_experiment_status", "experiment_status", "current_status"),
}

_OPTIONAL_METHOD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "record_result": (
        "record_result",
        "record_execution_result",
        "attach_result_assets",
    ),
}

_REQUIRED_OPERATIONS = frozenset(_METHOD_ALIASES)


class PersistenceAdapter:
    """Narrow compatibility wrapper over a persistence implementation.

    Each frozen operation is resolved at construction time from candidate
    method names so likely D1 adapter naming can be supported.  Missing
    required operations raise a clear error; nothing is fabricated.
    """

    def __init__(self, persistence: Any):
        if persistence is None:
            raise TypeError("persistence adapter is required")
        self._inner = persistence
        self._methods: Dict[str, Callable[..., Any]] = {}
        missing: List[str] = []
        for op, aliases in _METHOD_ALIASES.items():
            fn: Optional[Callable[..., Any]] = None
            for name in aliases:
                candidate = getattr(persistence, name, None)
                if callable(candidate):
                    fn = candidate
                    break
            if fn is None:
                fn = _noop
                if op in _REQUIRED_OPERATIONS:
                    missing.append(op)
            self._methods[op] = fn
        self._optional_methods: Dict[str, Optional[Callable[..., Any]]] = {}
        for op, aliases in _OPTIONAL_METHOD_ALIASES.items():
            fn = None
            for name in aliases:
                candidate = getattr(persistence, name, None)
                if callable(candidate):
                    fn = candidate
                    break
            self._optional_methods[op] = fn
        if missing:
            raise TypeError(
                "persistence adapter is incompatible; missing required operations: "
                + ", ".join(sorted(missing))
                + f" (accepted surface: {sorted(_METHOD_ALIASES)})"
            )

    def load_queued_cells(self) -> Any:
        return self._methods["load_queued_cells"]()

    def atomically_claim_queued_attempt(self, cell_id: str) -> Any:
        return self._methods["atomically_claim_queued_attempt"](cell_id)

    def read_active_attempt(self, cell_id: str) -> Any:
        return self._methods["read_active_attempt"](cell_id)

    def record_running(self, attempt_id: str, cell_id: str) -> Any:
        return self._methods["record_running"](attempt_id, cell_id)

    def record_terminal(self, attempt_id: str, cell_id: str, status: str, error: Optional[str] = None) -> Any:
        return self._methods["record_terminal"](attempt_id, cell_id, status, error=error)

    def create_resume_attempt(self, cell_id: str) -> Any:
        return self._methods["create_resume_attempt"](cell_id)

    def create_retry_attempt(self, cell_id: str) -> Any:
        return self._methods["create_retry_attempt"](cell_id)

    def list_recoverable_cells(self) -> Any:
        return self._methods["list_recoverable_cells"]()

    def aggregate_status(self) -> Any:
        return self._methods["aggregate_status"]()

    def record_result(self, attempt_id: str, cell_id: str, result: Any) -> Any:
        """Persist result assets when the production adapter supports it.

        Older test/fake adapters intentionally have no result hook; those
        adapters retain the scheduler's status-only behavior.
        """
        fn = self._optional_methods.get("record_result")
        if fn is None:
            return True
        return fn(attempt_id, cell_id, result)


# ── Module-level scheduler registry ──────────────────────────────────────


_SCHEDULERS: Dict[str, "ExperimentModernScheduler"] = {}


def register_scheduler(scheduler: "ExperimentModernScheduler") -> None:
    _SCHEDULERS[scheduler.experiment_id] = scheduler


def unregister_scheduler(experiment_id: str) -> None:
    _SCHEDULERS.pop(experiment_id, None)


def get_scheduler(experiment_id: str) -> Optional["ExperimentModernScheduler"]:
    return _SCHEDULERS.get(experiment_id)


def _require_scheduler(experiment_id: str) -> "ExperimentModernScheduler":
    scheduler = _SCHEDULERS.get(experiment_id)
    if scheduler is None:
        raise KeyError(
            f"no registered ExperimentModernScheduler for experiment_id={experiment_id!r}"
        )
    return scheduler


# ── Process-local production binding (D3/D4) ─────────────────────────────


class _AttemptTransportBinding:
    """Per-experiment attempt -> request-id binding shared by the execution
    and remote-cancel closures.

    The execution closure registers one entry per concurrently active attempt
    and removes it in ``finally``; the remote-cancel closure resolves the
    request id so it can route through the transport-owned cancellation
    handle.  Bounded by the scheduler's concurrency — no unbounded growth
    across retries.
    """

    __slots__ = ("_bindings",)

    def __init__(self) -> None:
        self._bindings: Dict[str, str] = {}

    def bind(self, attempt_id: str, request_id: str) -> None:
        self._bindings[str(attempt_id)] = str(request_id)

    def unbind(self, attempt_id: str) -> None:
        self._bindings.pop(str(attempt_id), None)

    def lookup(self, attempt_id: str) -> Optional[str]:
        return self._bindings.get(str(attempt_id))

    def items(self) -> List[Tuple[str, str]]:
        return list(self._bindings.items())

    def __len__(self) -> int:
        return len(self._bindings)

    def clear(self) -> None:
        self._bindings.clear()


def _execution_plan_from_cell_plan(plan: Any) -> Any:
    """The frozen ``ExecutionPlan`` carried by an immutable cell plan.

    Immutable plan objects are used verbatim (``plan.execution_plan``).  A
    dict (a persisted ``CellPlan.to_dict()`` rehydrated from storage) is
    rebuilt ONLY through ``ExecutionPlan.from_dict`` — latest/default
    workflow resolution is never re-run at execution time.
    """
    if plan is None:
        return None
    if isinstance(plan, Mapping):
        raw = plan.get("execution_plan")
        if not isinstance(raw, Mapping):
            return None
        from comfymodal_runtime.contracts import ExecutionPlan

        return ExecutionPlan.from_dict(raw)
    execution_plan = getattr(plan, "execution_plan", None)
    if execution_plan is not None:
        return execution_plan
    return None


def _plan_request_id(execution_plan: Any, fallback: str) -> str:
    """The transport request/attempt id for one execution plan.

    Mirrors ``ModalTransport.run_plan_stream``'s resolution order
    (``request_origin_info.request_id`` > plan ``prompt_id``/``request_id`` >
    fallback) so the attempt binding always resolves to the handle the
    transport actually registered.
    """
    request_metadata = getattr(execution_plan, "request_metadata", None)
    if isinstance(request_metadata, Mapping):
        origin = request_metadata.get("request_origin_info")
        if isinstance(origin, Mapping) and origin.get("request_id"):
            return str(origin["request_id"])
        value = request_metadata.get("prompt_id") or request_metadata.get("request_id")
        if value:
            return str(value)
    return str(fallback)


def _transport_handle_confirms_cancel(transport: Any, request_id: str) -> bool:
    """True only when the transport-owned cancellation handle for
    *request_id* has been explicitly confirmed by the remote ``cancelled``
    event.

    Reads the handle snapshot BEFORE the execute closure's ``finally``
    releases it, so the confirmation evidence is never lost.  Only an
    explicit ``confirmed`` verdict counts; pending/unavailable/completed
    verdicts never fabricate ``canceled``.  Never raises.
    """
    get_handle = getattr(transport, "get_cancellation_handle", None)
    if not callable(get_handle):
        return False
    try:
        handle = get_handle(request_id)
    except Exception:
        return False
    if handle is None:
        return False
    snapshot = getattr(handle, "snapshot", None)
    if not callable(snapshot):
        return False
    try:
        verdict = snapshot()
    except Exception:
        return False
    if isinstance(verdict, Mapping):
        return bool(verdict.get("confirmed"))
    return bool(getattr(verdict, "confirmed", False))


def _make_binding_execute(transport: Any, binding: _AttemptTransportBinding) -> Callable[..., Any]:
    """Default execution closure for the production binding.

    Binds the attempt to the shared per-experiment transport, executes the
    cell's frozen plan through ``canonical_execution.execute_plan`` with the
    SAME transport (never a second transport), and cleans the binding plus the
    transport-owned cancellation handle in ``finally``.

    When ``execute_plan`` raises because the remote stream ended after an
    explicit confirmed ``cancelled`` event, the closure inspects the
    transport-owned handle snapshot (BEFORE releasing it) and reports a
    ``{'status': 'canceled', 'request_id': ...}`` mapping so the scheduler's
    ``_run_cell`` status branch records the durable ``canceled`` terminal —
    never a spurious ``failed``.  Ordinary exceptions are re-raised
    unchanged, and cancellation (shutdown/interrupted) semantics are
    preserved.
    """

    async def _execute(plan: Any, *, attempt_id: str, cell_id: str) -> Optional[dict[str, Any]]:
        execution_plan = _execution_plan_from_cell_plan(plan)
        if execution_plan is None:
            raise RuntimeError(f"cell {cell_id} has no execution plan")
        request_id = _plan_request_id(execution_plan, fallback=attempt_id)
        binding.bind(attempt_id, request_id)
        try:
            from canonical_execution import execute_plan
            from comfymodal_runtime.trace import RuntimeTrace

            trace = RuntimeTrace(request_id=request_id, process="local")
            result = await execute_plan(execution_plan, transport=transport, trace=trace)
            if not isinstance(result, Mapping):
                return result

            # Experiment cells use the same local materialization contract as
            # the modern Single path.  Without this step a descriptor result
            # can be terminalized successfully while History never receives a
            # local path or producer-asset identity to associate.
            result = dict(result)
            output_mode = str(
                getattr(execution_plan.execution_options, "output_mode", "original")
                or "original"
            )
            result.setdefault("output_mode", output_mode)
            result.setdefault("variant", output_mode)
            descriptors = result.get("asset_descriptors")
            if isinstance(descriptors, list):
                from comfymodal_runtime.contracts import build_logical_output_key

                result["asset_descriptors"] = [
                    {
                        **descriptor,
                        "output_mode": descriptor.get("output_mode", output_mode),
                        "variant": descriptor.get("variant", output_mode),
                        "logical_output_key": descriptor.get(
                            "logical_output_key",
                            build_logical_output_key(
                                descriptor.get("node_id", ""),
                                descriptor.get("output_key", ""),
                                descriptor.get("output_index", 0),
                            )
                            or "",
                        ),
                    }
                    for descriptor in descriptors
                    if isinstance(descriptor, Mapping)
                ]
            required_output = bool(
                getattr(execution_plan.execution_options, "production_enabled", False)
            ) or bool(execution_plan.output_node_ids)
            result["_history_output_required"] = required_output
            experiment_id = str(_plan_field(plan, "experiment_id", "") or "")
            cell_key = str(_plan_field(plan, "cell_key", "") or cell_id)
            result["_history_experiment_id"] = experiment_id
            result["_history_cell_key"] = cell_key

            has_remote_output = bool(
                result.get("outputs")
                or result.get("images")
                or result.get("videos")
                or result.get("primary_output")
            )
            if has_remote_output:
                from local_artifacts import get_experiments_dir
                from comfymodal_runtime.playground_service import _default_materialize

                output_dir = (
                    get_experiments_dir()
                    / (experiment_id or "experiment")
                    / "outputs"
                    / cell_key
                    / str(attempt_id)
                )
                output_paths = await _default_materialize(
                    result,
                    experiment_id=experiment_id or request_id,
                    cell_key=cell_key,
                    studio_output_dir=output_dir,
                    require_output=required_output,
                    expected_output_node_ids=tuple(execution_plan.output_node_ids),
                    workspace=getattr(transport, "workspace", None),
                    gpu=str(
                        execution_plan.request_metadata.get("selected_gpu", "")
                        or ""
                    ),
                )
                result["output_paths"] = list(output_paths or [])

            if required_output and not result.get("output_paths") and not result.get(
                "primary_asset_id"
            ):
                return {
                    "status": "error",
                    "message": "v2 output materialization produced no files",
                }
            return result
        except asyncio.CancelledError:
            raise
        except Exception:
            # A confirmed remote ``cancelled`` event terminates the transport
            # stream WITHOUT a result, so ``execute_plan`` raises.  Inspect the
            # transport-owned handle snapshot before ``finally`` releases it:
            # an explicit confirmed verdict means the attempt was cancelled
            # remotely, so report ``canceled`` (the ``_run_cell`` status branch
            # persists the durable terminal) instead of surfacing a spurious
            # ``failed`` that would require a user retry.
            if _transport_handle_confirms_cancel(transport, request_id):
                return {"status": "canceled", "request_id": request_id}
            raise
        finally:
            binding.unbind(attempt_id)
            release = getattr(transport, "release_cancellation_handle", None)
            if callable(release):
                try:
                    release(request_id)
                except Exception:
                    pass

    return _execute


def _make_transport_remote_cancel(transport: Any, binding: _AttemptTransportBinding) -> Callable[..., Any]:
    """Default remote-cancel primitive for the production binding.

    Looks up the active attempt binding and routes the cancel through the
    transport-owned ``cancel_attempt`` seam (the transport resolves its own
    registered handle; no Modal SDK import here).  Returns an explicitly
    unconfirmed ``CancelResult`` when no binding/channel/primitive is
    available so the scheduler leaves the durable running state truthful.
    """

    async def _remote_cancel(attempt_id: str, cell_id: str, *, intent: str, reason: str) -> Any:
        request_id = binding.lookup(attempt_id)
        if request_id is None:
            return CancelResult(
                confirmed=False,
                outcome="unavailable",
                detail="no active transport binding for attempt",
                attempt_id=str(attempt_id),
                cell_id=str(cell_id),
            )
        cancel_attempt = getattr(transport, "cancel_attempt", None)
        if callable(cancel_attempt):
            try:
                return await _invoke(cancel_attempt, request_id, reason=reason)
            except Exception as exc:
                return CancelResult(
                    confirmed=False,
                    outcome="error",
                    detail=f"cancel channel failure: {exc}",
                    attempt_id=str(attempt_id),
                    cell_id=str(cell_id),
                )
        handle = getattr(transport, "get_cancellation_handle", None)
        if callable(handle):
            registered = handle(request_id)
            cancel = getattr(registered, "cancel", None)
            if callable(cancel):
                try:
                    return await _invoke(cancel, reason=reason)
                except Exception as exc:
                    return CancelResult(
                        confirmed=False,
                        outcome="error",
                        detail=f"cancel channel failure: {exc}",
                        attempt_id=str(attempt_id),
                        cell_id=str(cell_id),
                    )
        return CancelResult(
            confirmed=False,
            outcome="unavailable",
            detail="transport exposes no cancellation primitive",
            attempt_id=str(attempt_id),
            cell_id=str(cell_id),
        )

    return _remote_cancel


def build_experiment_scheduler(
    experiment_id: str,
    cell_plans: Sequence[Any],
    persistence: Any,
    *,
    transport: Any = None,
    transport_factory: Optional[Callable[[], Any]] = None,
    execute: Optional[Callable[..., Any]] = None,
    remote_cancel: Optional[Callable[..., Any]] = None,
    concurrency: Optional[int] = None,
) -> "ExperimentModernScheduler":
    """Construct the production scheduler for one modern Experiment.

    Wires a single shared per-experiment transport into the execution and
    remote-cancel closures (see ``_make_binding_execute`` /
    ``_make_transport_remote_cancel``) and registers the scheduler in the
    module registry.  When neither *transport* nor *transport_factory* is
    supplied the factory lazily creates a ``ModalTransport()``.
    """
    if transport is None:
        if transport_factory is not None:
            transport = transport_factory()
        else:
            from comfymodal_runtime.modal_transport import ModalTransport

            transport = ModalTransport()
    binding = _AttemptTransportBinding()
    if execute is None:
        execute = _make_binding_execute(transport, binding)
    if remote_cancel is None:
        remote_cancel = _make_transport_remote_cancel(transport, binding)
    scheduler = ExperimentModernScheduler(
        experiment_id=experiment_id,
        cell_plans=cell_plans,
        persistence=persistence,
        execute=execute,
        remote_cancel=remote_cancel,
        concurrency=concurrency,
    )
    # Hang the binding + shared transport off the scheduler so lifecycle
    # teardown can release handles and clear bindings explicitly.
    scheduler._transport_binding = binding
    scheduler._shared_transport = transport
    return scheduler


# ── Scheduler ────────────────────────────────────────────────────────────


class ExperimentModernScheduler:
    def __init__(
        self,
        experiment_id: str,
        cell_plans: Sequence[Any],
        persistence: Any,
        execute: Callable[..., Any],
        remote_cancel: Callable[..., Any],
        concurrency: Optional[int] = None,
    ):
        self.experiment_id = experiment_id
        if concurrency not in (None, EXPERIMENT_CONCURRENCY):
            logger.warning(
                "ignoring per-experiment concurrency %r; using global width %s",
                concurrency, EXPERIMENT_CONCURRENCY,
            )
        self.concurrency = EXPERIMENT_CONCURRENCY
        self._execute = execute
        self._remote_cancel = remote_cancel
        self._persistence = PersistenceAdapter(persistence)
        self._plans: Dict[str, Any] = {}
        for plan in cell_plans:
            cell_id = _plan_cell_id(plan)
            if cell_id is None:
                raise ValueError("each cell plan must carry a cell_id/cell_key")
            self._plans[cell_id] = plan
        self._order: List[str] = list(self._plans.keys())
        self._queue: Deque[str] = deque()
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._active_cell: Dict[str, str] = {}
        self._attempt_for_cell: Dict[str, str] = {}
        self._preclaimed: Dict[str, AttemptClaim] = {}
        self._remote_cancelled: Set[str] = set()
        self._remote_cancel_confirmed: Set[str] = set()
        self._cancelled_cells: Set[str] = set()
        self._dispatch_task: Optional[asyncio.Task] = None
        self._stopping: bool = False
        self._shutdown_done: bool = False
        # Production binding (set by ``build_experiment_scheduler``): the
        # attempt -> request-id binding and the shared per-experiment
        # transport.  Lifecycle teardown releases handles + clears bindings.
        self._transport_binding: Optional[_AttemptTransportBinding] = None
        self._shared_transport: Any = None
        register_scheduler(self)

    # -- public lifecycle --------------------------------------------------

    async def start(self, payload: Optional[Mapping[str, Any]] = None) -> "ExperimentModernScheduler":
        if self._shutdown_done:
            raise RuntimeError("scheduler already shut down")
        if isinstance(payload, Mapping):
            override = payload.get("concurrency", payload.get("max_parallel"))
            if override is not None:
                logger.info(
                    "ignoring payload concurrency override %r; using concurrency %s",
                    override, self.concurrency,
                )
        await self._seed_queued()
        self._ensure_dispatch()
        return self

    async def start_experiment(self, payload: Optional[Mapping[str, Any]] = None) -> "ExperimentModernScheduler":
        return await self.start(payload)

    async def resume_experiment(
        self,
        experiment_id: Optional[str] = None,
        *,
        reason: str = "resume",
    ) -> Dict[str, int]:
        return await self.resume(experiment_id, reason=reason)

    async def cancel(
        self,
        experiment_id: Optional[str] = None,
        *,
        reason: str = "user_cancel",
    ) -> Dict[str, int]:
        return await self.cancel_experiment(experiment_id, reason=reason)

    async def shutdown(self, *, reason: str = "shutdown") -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self._stopping = True
        try:
            await self._shutdown_mark_interrupted(reason=reason)
        finally:
            self._cancel_local_tasks()
            try:
                await self._drain_tasks(reason)
            except asyncio.CancelledError:
                pass
            dispatch_task = self._dispatch_task
            if (
                dispatch_task is not None
                and dispatch_task is not asyncio.current_task()
                and not dispatch_task.done()
            ):
                dispatch_task.cancel()
                try:
                    await dispatch_task
                except asyncio.CancelledError:
                    pass
            self._cleanup()

    async def status(self, experiment_id: Optional[str] = None) -> str:
        raw = await _invoke(self._persistence.aggregate_status)
        return str(raw)

    async def get_status(self, experiment_id: Optional[str] = None) -> str:
        return await self.status(experiment_id)

    async def handle_terminal(
        self,
        cell_id: str,
        attempt_id: str,
        status: str,
        *,
        error: Optional[str] = None,
    ) -> bool:
        """Apply a terminal event only to the current non-terminal attempt."""
        if status not in TERMINAL_STATUSES:
            return False
        active = await self._safe_read_active_attempt(cell_id)
        if active is None or active.attempt_id != str(attempt_id):
            return False
        if active.status in TERMINAL_STATUSES:
            return False
        return await self._record_terminal(
            str(attempt_id), cell_id, status, error=error
        )

    async def handle_progress(
        self,
        cell_id: str,
        attempt_id: str,
        event: Any = None,
    ) -> bool:
        """Accept progress only for the active attempt; progress is not durable here."""
        active = await self._safe_read_active_attempt(cell_id)
        return bool(
            active is not None
            and active.attempt_id == str(attempt_id)
            and active.status not in TERMINAL_STATUSES
        )

    async def handle_event(self, event: Mapping[str, Any]) -> bool:
        cell_id = event.get("cell_id") or event.get("cell_key")
        attempt_id = event.get("attempt_id") or event.get("run_id")
        if not cell_id or not attempt_id:
            return False
        status = event.get("status")
        if status in TERMINAL_STATUSES:
            return await self.handle_terminal(
                str(cell_id), str(attempt_id), str(status), error=event.get("error")
            )
        return await self.handle_progress(str(cell_id), str(attempt_id), event)

    async def submit_cell(self, plan: Any, payload: Optional[Mapping[str, Any]] = None) -> None:
        if self._shutdown_done:
            raise RuntimeError("scheduler already shut down")
        cell_id = _plan_cell_id(plan)
        if cell_id is None:
            raise ValueError("cell plan must carry a cell_id/cell_key")
        if cell_id not in self._plans:
            self._plans[cell_id] = plan
            self._order.append(cell_id)
        if cell_id in self._cancelled_cells or cell_id in self._queue or cell_id in self._attempt_for_cell:
            return
        rec = await self._safe_read_active_attempt(cell_id)
        if rec is not None and rec.status in TERMINAL_STATUSES:
            return
        self._queue.append(cell_id)
        self._ensure_dispatch()

    async def cancel_cell(self, cell_id: str, *, reason: str = "user_cancel") -> str:
        """Cancel one cell.

        Returns ``"canceled_running"``, ``"canceled_queued"``,
        ``"cancel_unconfirmed"`` or ``"noop"``.  A queued cell is removed
        without submission (zero execute calls); a running cell gets the
        injected remote cancellation primitive invoked exactly once with an
        explicit intent/reason, and ``canceled`` is persisted only when the
        remote result *explicitly confirms* cancellation (or the legacy
        callable returned ``None``).  An unconfirmed result or a channel
        failure leaves the durable running state truthful and returns
        ``"cancel_unconfirmed"``.  ``canceled`` is only recorded as the first
        terminal write (first-wins).
        """
        if cell_id in self._queue:
            self._queue.remove(cell_id)
        self._cancelled_cells.add(cell_id)
        preclaimed = self._preclaimed.pop(cell_id, None)
        rec = await self._safe_read_active_attempt(cell_id)
        if rec is None:
            if preclaimed is not None:
                await self._record_terminal(
                    preclaimed.attempt_id, cell_id, "canceled", error=reason
                )
            else:
                try:
                    claim = _coerce_claim(
                        await _invoke(
                            self._persistence.atomically_claim_queued_attempt,
                            cell_id,
                        )
                    )
                except Exception:
                    claim = None
                if claim is not None:
                    await self._record_terminal(
                        claim.attempt_id, cell_id, "canceled", error=reason
                    )
            return "canceled_queued"
        if rec.status in TERMINAL_STATUSES:
            return "noop"
        attempt_id = rec.attempt_id
        submitted = attempt_id in self._active_tasks
        if submitted:
            if attempt_id in self._remote_cancel_confirmed:
                # Already confirmed and durably applied; retry only the write
                # (first-wins).  Never re-invoke the remote primitive.
                won = await self._record_terminal(attempt_id, cell_id, "canceled", error=reason)
                return "canceled_running" if won else "noop"
            outcome = await self._invoke_remote_cancel(
                attempt_id, cell_id, intent="cancel", reason=reason
            )
            if not outcome.confirmed:
                logger.warning(
                    "remote cancel unconfirmed for cell %s attempt %s (mode=%s); "
                    "leaving durable state running",
                    cell_id, attempt_id, outcome.mode,
                )
                return "cancel_unconfirmed"
            self._remote_cancelled.add(attempt_id)
            self._remote_cancel_confirmed.add(attempt_id)
            won = await self._record_terminal(attempt_id, cell_id, "canceled", error=reason)
            task = self._active_tasks.get(attempt_id)
            if task is not None and not task.done():
                task.cancel()
            return "canceled_running" if won else "noop"
        await self._record_terminal(attempt_id, cell_id, "canceled", error=reason)
        return "canceled_queued"

    async def cancel_experiment(
        self,
        experiment_id: Optional[str] = None,
        *,
        reason: str = "user_cancel",
    ) -> Dict[str, int]:
        self._stopping = True
        counts: Dict[str, int] = {
            "canceled_queued": 0,
            "canceled_running": 0,
            "cancel_unconfirmed": 0,
            "noop": 0,
        }
        for cell_id in list(self._order):
            result = await self.cancel_cell(cell_id, reason=reason)
            counts[result] = counts.get(result, 0) + 1
        return counts

    async def resume(
        self,
        experiment_id: Optional[str] = None,
        *,
        reason: str = "resume",
    ) -> Dict[str, int]:
        """Resume interrupted and never-started cells.

        Interrupted cells get a brand-new attempt identity via persistence
        (``create_resume_attempt``); queued/not-started cells reuse their
        existing queued attempt (``atomically_claim_queued_attempt``).
        Completed, failed, and canceled cells are skipped.  A second resume
        cannot double-submit because claims are atomic and first-wins.
        """
        if self._shutdown_done:
            return {"resumed": 0, "skipped": 0}
        counts: Dict[str, int] = {"resumed": 0, "skipped": 0}
        self._stopping = False
        recoverable = {record.cell_id: record for record in await self._list_recoverable_cells()}
        resumed_cells: Set[str] = set()
        for cell_id in self._order:
            if cell_id in self._cancelled_cells or cell_id in self._attempt_for_cell:
                continue
            record = recoverable.get(cell_id)
            if record is None:
                record = await self._safe_read_active_attempt(cell_id)
            status = record.status if record is not None else None
            if status in ("completed", "failed", "canceled", "running"):
                continue
            if status == "interrupted":
                create_attempt = self._persistence.create_resume_attempt
            else:
                create_attempt = self._persistence.atomically_claim_queued_attempt
            try:
                claim = _coerce_claim(await _invoke(create_attempt, cell_id))
            except Exception:
                claim = None
            if claim is None:
                continue
            self._preclaimed[cell_id] = claim
            if cell_id not in self._queue:
                self._queue.append(cell_id)
            resumed_cells.add(cell_id)
        counts["resumed"] = len(resumed_cells)
        counts["skipped"] = sum(1 for cid in self._order if cid not in resumed_cells)
        self._ensure_dispatch()
        return counts

    async def retry_cell(
        self,
        cell_id: str,
        *route_args: str,
        reason: str = "retry",
    ) -> bool:
        if self._shutdown_done:
            return False
        if route_args:
            cell_id = route_args[0]
        if cell_id in self._attempt_for_cell or cell_id in self._preclaimed:
            return False
        rec = await self._safe_read_active_attempt(cell_id)
        if rec is None or rec.status != "failed":
            return False
        if cell_id in self._queue:
            self._queue.remove(cell_id)
        try:
            claim = _coerce_claim(await _invoke(self._persistence.create_retry_attempt, cell_id))
        except Exception:
            claim = None
        if claim is None:
            return False
        self._stopping = False
        self._preclaimed[cell_id] = claim
        self._queue.append(cell_id)
        self._ensure_dispatch()
        return True

    # -- exposed recovery helpers ------------------------------------------

    async def _startup_recovery(self, *, reason: str = "startup_recovery") -> int:
        """Sweep attempts stuck in ``running`` (crashed/previous process) to
        ``interrupted``.  Never touches attempts this scheduler is actively
        executing; queued/not-started and terminal cells are left untouched.
        Idempotent: attempts already terminal are skipped by first-wins."""
        swept = 0
        records = await self._list_recoverable_cells()
        for rec in records:
            if rec.status != "running" or rec.attempt_id is None:
                continue
            if rec.attempt_id in self._active_tasks:
                continue
            won = await self._record_terminal(rec.attempt_id, rec.cell_id, "interrupted", error=reason)
            if won:
                swept += 1
        return swept

    async def _shutdown_mark_interrupted(self, *, reason: str = "shutdown") -> int:
        """Best-effort remote stop of active attempts, then persist
        ``interrupted`` for each (first-wins; already-terminal attempts are
        untouched).  The remote-cancel result is deliberately ignored here:
        shutdown always converges to ``interrupted`` after a best-effort
        stop, never to ``canceled``.  Returns the number of attempts marked
        interrupted."""
        marked = 0
        for attempt_id in list(self._active_tasks.keys()):
            cell_id = self._active_cell.get(attempt_id, "")
            if attempt_id not in self._remote_cancelled:
                self._remote_cancelled.add(attempt_id)
                await self._invoke_remote_cancel(
                    attempt_id, cell_id, intent="shutdown", reason=reason
                )
            won = await self._record_terminal(attempt_id, cell_id, "interrupted", error=reason)
            if won:
                marked += 1
        return marked

    # -- internals ----------------------------------------------------------

    async def _invoke_remote_cancel(
        self,
        attempt_id: str,
        cell_id: str,
        *,
        intent: str,
        reason: str,
    ) -> _CancelOutcome:
        """Invoke the injected remote-cancel primitive exactly once and
        classify its outcome.

        A ``None`` return is the explicit compatibility mode for legacy
        fakes/callables (historical fire-and-forget; treated as confirmed).
        Any non-``None`` return must explicitly confirm cancellation;
        otherwise (or on a channel exception) the outcome is unconfirmed and
        the durable running state must be left truthful.
        """
        try:
            raw = await _invoke(
                self._remote_cancel,
                attempt_id,
                cell_id,
                intent=intent,
                reason=reason,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("remote cancel failed for cell %s attempt %s", cell_id, attempt_id)
            return _CancelOutcome(confirmed=False, mode="error")
        if raw is None:
            return _CancelOutcome(confirmed=True, mode="legacy")
        result = _coerce_cancel_result(raw)
        if result is None or not result.confirmed:
            return _CancelOutcome(confirmed=False, mode="unconfirmed", result=result)
        return _CancelOutcome(confirmed=True, mode="confirmed", result=result)

    async def _seed_queued(self) -> None:
        raw = await _invoke(self._persistence.load_queued_cells)
        records = _coerce_cell_records(raw)
        queued_ids = {r.cell_id for r in records}
        for cell_id in queued_ids:
            if cell_id not in self._plans:
                logger.warning("skipping queued cell %s: no cell plan supplied", cell_id)
        self._queue = deque(
            cell_id
            for cell_id in self._order
            if cell_id in queued_ids
            and cell_id not in self._cancelled_cells
            and cell_id not in self._attempt_for_cell
        )

    def _ensure_dispatch(self) -> None:
        register_scheduler(self)
        if self._dispatch_task is None or self._dispatch_task.done():
            self._dispatch_task = asyncio.get_running_loop().create_task(self._dispatch_loop())

    async def _read_active_attempt(self, cell_id: str) -> Optional[AttemptRecord]:
        raw = await _invoke(self._persistence.read_active_attempt, cell_id)
        return _coerce_attempt_record(raw)

    async def _safe_read_active_attempt(self, cell_id: str) -> Optional[AttemptRecord]:
        try:
            return await self._read_active_attempt(cell_id)
        except Exception:
            logger.warning("read_active_attempt failed for cell %s; treating as no active attempt", cell_id)
            return None

    async def _list_recoverable_cells(self) -> List[CellRecord]:
        try:
            raw = await _invoke(self._persistence.list_recoverable_cells)
        except Exception:
            logger.warning("list_recoverable_cells failed; treating as empty")
            return []
        return _coerce_cell_records(raw)

    async def _record_terminal(self, attempt_id: str, cell_id: str, status: str, error: Optional[str] = None) -> bool:
        try:
            won = await _invoke(self._persistence.record_terminal, attempt_id, cell_id, status, error)
        except Exception:
            logger.exception("terminal write failed for cell %s attempt %s", cell_id, attempt_id)
            return False
        return bool(won)

    async def _record_result(self, attempt_id: str, cell_id: str, result: Any) -> bool:
        try:
            return bool(
                await _invoke(
                    self._persistence.record_result,
                    attempt_id,
                    cell_id,
                    result,
                )
            )
        except Exception:
            logger.exception(
                "result finalization failed for cell %s attempt %s",
                cell_id,
                attempt_id,
            )
            return False

    async def _dispatch_loop(self) -> None:
        try:
            while True:
                while (not self._stopping
                       and not self._shutdown_done
                       and len(self._active_tasks) < self.concurrency
                       and self._queue):
                    cell_id = self._queue.popleft()
                    await self._claim_and_launch(cell_id)
                if not self._active_tasks:
                    break
                done, _pending = await asyncio.wait(
                    set(self._active_tasks.values()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    await self._process_done(task)
        except asyncio.CancelledError:
            if not self._shutdown_done:
                self._shutdown_done = True
                self._stopping = True
                try:
                    await self._shutdown_mark_interrupted(reason="loop_shutdown")
                finally:
                    self._cancel_local_tasks()
                    try:
                        await self._drain_tasks("loop_shutdown")
                    except asyncio.CancelledError:
                        pass
            raise
        finally:
            if self._shutdown_done:
                self._cleanup(unregister=True)
            else:
                self._cleanup(unregister=False)

    async def _claim_and_launch(self, cell_id: str) -> None:
        if self._stopping or self._shutdown_done or cell_id in self._cancelled_cells:
            return
        claim = self._preclaimed.pop(cell_id, None)
        if claim is None:
            try:
                raw = await _invoke(self._persistence.atomically_claim_queued_attempt, cell_id)
            except Exception:
                logger.warning("claim failed for cell %s; skipping launch", cell_id)
                return
            claim = _coerce_claim(raw)
        if claim is None:
            return
        if (
            self._stopping
            or self._shutdown_done
            or cell_id in self._cancelled_cells
        ):
            terminal = "canceled" if cell_id in self._cancelled_cells else "interrupted"
            await self._record_terminal(claim.attempt_id, cell_id, terminal)
            return
        if not self._launch(claim.attempt_id, cell_id):
            await self._record_terminal(
                claim.attempt_id, cell_id, "failed", error="attempt already active"
            )

    def _launch(self, attempt_id: str, cell_id: str) -> bool:
        if attempt_id in self._active_tasks:
            return False
        if cell_id not in self._plans:
            return False
        existing = self._attempt_for_cell.get(cell_id)
        if existing is not None and existing != attempt_id:
            return False
        task = asyncio.get_running_loop().create_task(self._run_cell(cell_id, attempt_id))
        self._active_tasks[attempt_id] = task
        self._active_cell[attempt_id] = cell_id
        self._attempt_for_cell[cell_id] = attempt_id
        return True

    async def _run_cell(self, cell_id: str, attempt_id: str) -> None:
        plan = self._plans.get(cell_id)
        if plan is None:
            await self._record_terminal(attempt_id, cell_id, "failed", error="no cell plan")
            return
        try:
            await _invoke(self._persistence.record_running, attempt_id, cell_id)
            if self._shutdown_done or cell_id in self._cancelled_cells:
                return
            active = await self._safe_read_active_attempt(cell_id)
            if (
                active is None
                or active.attempt_id != attempt_id
                or active.status in TERMINAL_STATUSES
            ):
                return
            result = await _invoke(self._execute, plan, attempt_id=attempt_id, cell_id=cell_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("cell %s attempt %s failed: %r", cell_id, attempt_id, exc)
            await self._record_terminal(attempt_id, cell_id, "failed", error=repr(exc))
        else:
            failure = None
            if isinstance(result, Mapping):
                status = result.get("status")
                if status in ("failed", "error"):
                    failure = result.get("error") or result.get("message") or f"execution reported status {status!r}"
                elif status in ("canceled", "interrupted"):
                    await self._record_terminal(attempt_id, cell_id, str(status))
                    return
            if failure is not None:
                await self._record_terminal(attempt_id, cell_id, "failed", error=str(failure))
            else:
                if not await self._record_result(attempt_id, cell_id, result):
                    await self._record_terminal(
                        attempt_id,
                        cell_id,
                        "failed",
                        error="History output finalization failed",
                    )
                    return
                await self._record_terminal(attempt_id, cell_id, "completed")

    async def _process_done(self, task: asyncio.Task) -> None:
        attempt_id: Optional[str] = None
        for aid, t in list(self._active_tasks.items()):
            if t is task:
                attempt_id = aid
                del self._active_tasks[aid]
                cell_id = self._active_cell.pop(aid, None)
                if cell_id is not None and self._attempt_for_cell.get(cell_id) == aid:
                    del self._attempt_for_cell[cell_id]
                break
        if attempt_id is None:
            return
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("cell task for attempt %s raised %r", attempt_id, exc)

    def _cancel_local_tasks(self) -> None:
        for task in list(self._active_tasks.values()):
            if not task.done():
                task.cancel()

    async def _drain_tasks(self, reason: str = "shutdown") -> None:
        for attempt_id, task in list(self._active_tasks.items()):
            if not task.done():
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            cell_id = self._active_cell.get(attempt_id, "")
            if not cell_id:
                continue
            rec = await self._safe_read_active_attempt(cell_id)
            if rec is not None and rec.attempt_id == attempt_id and rec.status not in TERMINAL_STATUSES:
                await self._record_terminal(attempt_id, cell_id, "interrupted", error=reason)

    def _cleanup(self, *, unregister: bool = False) -> None:
        self._active_tasks.clear()
        self._active_cell.clear()
        self._attempt_for_cell.clear()
        self._preclaimed.clear()
        self._queue.clear()
        self._dispatch_task = None
        # Release any transport-owned cancellation handles still bound to this
        # experiment's attempts.  Attempts whose execute closure finished (or
        # was cancelled) already released theirs in ``finally``; this is the
        # shutdown/loop-end safety net so handles never accumulate across
        # retries or interrupted attempts.
        binding = self._transport_binding
        if binding is not None:
            transport = self._shared_transport
            release = (
                getattr(transport, "release_cancellation_handle", None)
                if transport is not None else None
            )
            if callable(release):
                for _attempt_id, request_id in binding.items():
                    try:
                        release(request_id)
                    except Exception:
                        pass
            binding.clear()
        if unregister:
            unregister_scheduler(self.experiment_id)


# ── Module-level convenience surface (frozen §13 names) ──────────────────


async def submit_cell(experiment_id: str, plan: Any, **kwargs: Any) -> None:
    scheduler = _require_scheduler(experiment_id)
    await scheduler.submit_cell(plan, payload=kwargs.get("payload"))


async def start_experiment(experiment_id: str, **kwargs: Any) -> ExperimentModernScheduler:
    scheduler = _require_scheduler(experiment_id)
    return await scheduler.start_experiment(payload=kwargs.get("payload"))


async def cancel_cell(experiment_id: str, cell_id: str, **kwargs: Any) -> str:
    scheduler = _require_scheduler(experiment_id)
    return await scheduler.cancel_cell(cell_id, reason=kwargs.get("reason", "user_cancel"))


async def cancel_experiment(experiment_id: str, **kwargs: Any) -> Dict[str, int]:
    scheduler = _require_scheduler(experiment_id)
    return await scheduler.cancel_experiment(reason=kwargs.get("reason", "user_cancel"))


async def resume(experiment_id: str, **kwargs: Any) -> Dict[str, int]:
    scheduler = _require_scheduler(experiment_id)
    return await scheduler.resume(reason=kwargs.get("reason", "resume"))


async def retry_cell(experiment_id: str, cell_id: str, **kwargs: Any) -> bool:
    scheduler = _require_scheduler(experiment_id)
    return await scheduler.retry_cell(cell_id, reason=kwargs.get("reason", "retry"))
