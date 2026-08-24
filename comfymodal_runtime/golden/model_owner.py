"""Golden model ownership protocol — one producer, many joiners, no re-reads.

Mirrors the proven ``graph_unet_join_or_adopt`` contract generically for all
three roles:

- The Golden loader is the ONLY producer per role per request generation.
  ``GoldenOwnerRegistry.register`` rejects a second live owner, which makes a
  duplicate source read structurally impossible.
- Demand sides call ``join_or_adopt``: they JOIN an in-flight producer,
  observe ALREADY_READY, ADOPT when no producer exists, or observe FAILED /
  TIMEOUT.  Demand never triggers its own read while an owner lives.
- Strong lifetime: payloads are retained until every ``take`` handle is
  released; publication requires device-readiness proof.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .contracts import (
    GoldenError,
    JoinDecision,
    ModelRole,
    OwnershipState,
)

__all__ = ["OwnerHandle", "GoldenModelOwner", "GoldenOwnerRegistry"]


@dataclass(frozen=True)
class OwnerHandle:
    role: ModelRole
    identity_hash: str
    reason: str
    taken_at_ns: int


class GoldenModelOwner:
    """Strong owner state machine for one role's Golden load."""

    def __init__(self, role: ModelRole, identity_hash: str) -> None:
        self.role = role
        self.identity_hash = identity_hash
        self._lock = threading.Lock()
        self._signal = threading.Event()
        self._state = OwnershipState.PREPARING
        self._failure: Optional[Exception] = None
        self._payload: Any = None
        self._retentions = 0
        self.take_ledger: List[Dict[str, Any]] = []

    # -- properties ---------------------------------------------------------

    @property
    def state(self) -> OwnershipState:
        with self._lock:
            return self._state

    @property
    def payload(self) -> Any:
        with self._lock:
            return self._payload

    @property
    def failure(self) -> Optional[Exception]:
        with self._lock:
            return self._failure

    def _set_state(self, new: OwnershipState, allowed_from: Tuple[OwnershipState, ...]) -> None:
        with self._lock:
            if self._state not in allowed_from:
                raise GoldenError(
                    f"illegal ownership transition {_state_name(self._state)} -> {_state_name(new)} "
                    f"(role={self.role.value})"
                )
            self._state = new

    # -- producer side -------------------------------------------------------

    def publish_device_ready(self, payload: Any = None) -> None:
        self._set_state(OwnershipState.DEVICE_READY, (OwnershipState.PREPARING,))
        with self._lock:
            self._payload = payload
        self._signal.set()

    def publish_failure(self, exc: Exception) -> None:
        if not isinstance(exc, Exception):
            raise GoldenError("publish_failure requires an exception instance")
        self._set_state(OwnershipState.FAILED, (OwnershipState.PREPARING, OwnershipState.DEVICE_READY))
        with self._lock:
            self._failure = exc
        self._signal.set()

    def mark_bind_ready(self) -> None:
        self._set_state(OwnershipState.BIND_READY, (OwnershipState.DEVICE_READY,))

    def mark_published(self) -> None:
        self._set_state(OwnershipState.PUBLISHED, (OwnershipState.BIND_READY,))

    # -- consumer side --------------------------------------------------------

    def join(self, timeout_s: float) -> JoinDecision:
        deadline = time.monotonic() + max(0.0, timeout_s)
        waited = False
        while True:
            with self._lock:
                st = self._state
            if st in (OwnershipState.DEVICE_READY, OwnershipState.BIND_READY, OwnershipState.PUBLISHED):
                return JoinDecision.JOINED if waited else JoinDecision.ALREADY_READY
            if st == OwnershipState.FAILED:
                return JoinDecision.FAILED
            remaining = deadline - time.monotonic()
            if remaining <= 0 and not self._signal.is_set():
                return JoinDecision.TIMEOUT
            if not self._signal.wait(timeout=min(remaining, 0.05) if remaining > 0 else 0):
                waited = True
                continue
            waited = True
            with self._lock:
                st = self._state
            if st in (OwnershipState.DEVICE_READY, OwnershipState.BIND_READY, OwnershipState.PUBLISHED):
                return JoinDecision.JOINED
            if st == OwnershipState.FAILED:
                return JoinDecision.FAILED
            # signal set but still PREPARING (defensive): keep bounded-waiting
            if time.monotonic() >= deadline:
                return JoinDecision.TIMEOUT

    def take(self, reason: str) -> OwnerHandle:
        with self._lock:
            if self._state in (OwnershipState.FAILED, OwnershipState.RELEASED):
                raise GoldenError(
                    f"take forbidden in state {_state_name(self._state)} (role={self.role.value})"
                )
            self._retentions += 1
            handle = OwnerHandle(
                role=self.role,
                identity_hash=self.identity_hash,
                reason=reason,
                taken_at_ns=time.perf_counter_ns(),
            )
            self.take_ledger.append(
                {"reason": reason, "retentions": self._retentions, "taken_at_ns": handle.taken_at_ns}
            )
            return handle

    def release(self) -> None:
        with self._lock:
            if self._retentions <= 0:
                raise GoldenError("release without matching take")
            self._retentions -= 1
            if self._retentions == 0:
                self._state = OwnershipState.RELEASED


def _state_name(state: OwnershipState) -> str:
    return state.value


class GoldenOwnerRegistry:
    """One live owner per role per request generation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owners: Dict[ModelRole, GoldenModelOwner] = {}

    def register(self, owner: GoldenModelOwner) -> None:
        with self._lock:
            existing = self._owners.get(owner.role)
            if existing is not None and existing.state not in (
                OwnershipState.RELEASED,
                OwnershipState.FAILED,
            ):
                raise GoldenError(
                    f"duplicate live owner for role {owner.role.value}: "
                    "one Golden read per role per request"
                )
            self._owners[owner.role] = owner

    def get(self, role: ModelRole) -> Optional[GoldenModelOwner]:
        with self._lock:
            return self._owners.get(role)

    def clear_role(self, role: ModelRole) -> None:
        with self._lock:
            self._owners.pop(role, None)

    def join_or_adopt(self, role: ModelRole, timeout_s: float) -> Tuple[JoinDecision, Optional[GoldenModelOwner]]:
        owner = self.get(role)
        if owner is None:
            return (JoinDecision.ADOPTED, None)
        return (owner.join(timeout_s), owner)
