"""Golden deterministic resource scheduler and overlap matrix.

One explicit state machine owns scheduling policy.  There are NO timing
sleeps, NO heuristic early-starts, and NO wall-clock decisions: every
transition is driven by a proof event (``GoldenEvent``), and every overlap
request is decided by an explicit allow/deny matrix over activity labels
plus exclusive-domain checks.

Initial conservative Golden rules (R41):

    CLIP_QD_SOURCE   + cheap request/static work : ALLOW
    CLIP_QD_SOURCE   + UNET_BULK_SOURCE          : DENY until CLIP releases storage priority
    CLIP_QD_H2D      + UNET_H2D                  : DENY
    CLIP_FORWARD     + UNET_METADATA_PREP        : ALLOW
    CLIP_FORWARD     + UNET_BULK_SOURCE          : ALLOW only after CLIP storage released
    CLIP_GPU_CRITICAL+ UNET_GPU_COMMIT           : DENY
    CLIP_GPU_CRITICAL+ SAMPLING                  : DENY
    SAMPLING         + VAE_QD                    : ALLOW only after first_sampler_step_proven
    VAE_QD (unarmed) + pre-sampling-start window: ALLOW (SAMPLING phase, no sampling grant)
    VAE_GPU_MUTATION + SAMPLING                  : DENY
    UNET_GPU_COMMIT  + SAMPLING                  : DENY

Exclusive resource domains: STORAGE_HEAVY, H2D_HEAVY, GPU_MUTATION.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .contracts import (
    ForbiddenOverlapError,
    GoldenError,
    GoldenEvent,
    LifecyclePhase,
    ModelRole,
    OverlapDecision,
    ResourceDomain,
)

__all__ = [
    "ACT_CLIP_QD_SOURCE",
    "ACT_CLIP_QD_H2D",
    "ACT_CHEAP_REQUEST_SETUP",
    "ACT_CLIP_FORWARD",
    "ACT_CLIP_GPU_CRITICAL",
    "ACT_UNET_METADATA_PREP",
    "ACT_UNET_BULK_SOURCE",
    "ACT_UNET_H2D",
    "ACT_UNET_GPU_COMMIT",
    "ACT_SAMPLING",
    "ACT_VAE_QD",
    "ACT_VAE_GPU_MUTATION",
    "ACT_OUTPUT_DELIVERY",
    "OverlapMatrix",
    "Grant",
    "GoldenResourceScheduler",
]

ACT_CLIP_QD_SOURCE = "clip_qd_source"
ACT_CLIP_QD_H2D = "clip_qd_h2d"
ACT_CHEAP_REQUEST_SETUP = "cheap_request_setup"
ACT_CLIP_FORWARD = "clip_forward"
ACT_CLIP_GPU_CRITICAL = "clip_gpu_critical"
ACT_UNET_METADATA_PREP = "unet_metadata_prep"
ACT_UNET_BULK_SOURCE = "unet_bulk_source"
ACT_UNET_H2D = "unet_h2d"
ACT_UNET_GPU_COMMIT = "unet_gpu_commit"
ACT_SAMPLING = "sampling"
ACT_VAE_QD = "vae_qd"
ACT_VAE_GPU_MUTATION = "vae_gpu_mutation"
ACT_OUTPUT_DELIVERY = "output_delivery"

#: Activities that carry no heavy resource claim.
_LIGHT_LABELS = {ACT_CHEAP_REQUEST_SETUP, ACT_OUTPUT_DELIVERY}

#: Symmetric explicit pair rules.  Missing heavy/heavy pairs default to DENY.
_PAIR_RULES: Dict[frozenset, str] = {
    frozenset({ACT_CLIP_QD_SOURCE, ACT_CLIP_QD_H2D}): "allow: same-loader source+H2D pipeline planes",
    frozenset({ACT_UNET_BULK_SOURCE, ACT_UNET_H2D}): "allow: same-loader source+H2D pipeline planes",
    frozenset({ACT_CLIP_FORWARD, ACT_CLIP_GPU_CRITICAL}): "allow: CLIP forward IS the GPU-critical holder",
    frozenset({ACT_CLIP_QD_SOURCE, ACT_CHEAP_REQUEST_SETUP}): "allow: cheap static work under CLIP source priority",
    frozenset({ACT_CLIP_QD_SOURCE, ACT_UNET_BULK_SOURCE}): "deny: UNET bulk source waits for CLIP storage release",
    frozenset({ACT_CLIP_QD_H2D, ACT_UNET_H2D}): "deny: concurrent H2D lanes forbidden",
    frozenset({ACT_CLIP_FORWARD, ACT_UNET_METADATA_PREP}): "allow: metadata prep under CLIP compute",
    frozenset({ACT_CLIP_GPU_CRITICAL, ACT_UNET_METADATA_PREP}): "allow: CPU-side metadata prep under CLIP GPU-critical work",
    frozenset({ACT_CLIP_FORWARD, ACT_UNET_BULK_SOURCE}): "allow: only reachable after CLIP storage release",
    frozenset({ACT_CLIP_GPU_CRITICAL, ACT_UNET_BULK_SOURCE}): "allow: UNET bulk source after CLIP storage release proof (flag-gated in _gate)",
    frozenset({ACT_CLIP_GPU_CRITICAL, ACT_UNET_GPU_COMMIT}): "deny: UNET commit waits for CLIP GPU-critical done",
    frozenset({ACT_CLIP_GPU_CRITICAL, ACT_SAMPLING}): "deny: sampler cannot start before CLIP critical done",
    frozenset({ACT_SAMPLING, ACT_VAE_QD}): "conditional: armed by first_sampler_step_proven only",
    frozenset({ACT_VAE_QD, ACT_CLIP_FORWARD}): "conditional_presampling: disjoint domains; unarmed VAE QD only before sampling start",
    frozenset({ACT_VAE_QD, ACT_CLIP_GPU_CRITICAL}): "conditional_presampling: disjoint domains; unarmed VAE QD only before sampling start",
    frozenset({ACT_VAE_GPU_MUTATION, ACT_SAMPLING}): "deny: unsafe sampler GPU mutation exclusion",
    frozenset({ACT_UNET_GPU_COMMIT, ACT_SAMPLING}): "deny: commit excludes sampler",
    frozenset({ACT_CLIP_FORWARD, ACT_CLIP_QD_SOURCE}): "deny: CLIP demand load cannot race its own forward",
}

_EXCLUSIVE_DOMAINS = {
    ResourceDomain.STORAGE_HEAVY,
    ResourceDomain.H2D_HEAVY,
    ResourceDomain.GPU_MUTATION,
}


@dataclass(frozen=True)
class Grant:
    label: str
    domains: Tuple[ResourceDomain, ...]
    grant_id: int


class OverlapMatrix:
    """Explicit symmetric allow/deny matrix over activity labels."""

    def __init__(
        self,
        vae_qd_armed_provider: Optional[callable] = None,  # type: ignore[type-arg]
        vae_qd_presampling_provider: Optional[callable] = None,  # type: ignore[type-arg]
    ) -> None:
        self._vae_armed = vae_qd_armed_provider or (lambda: False)
        self._vae_presampling = vae_qd_presampling_provider or (lambda: False)

    def check(self, active_labels: Set[str], request_label: str) -> OverlapDecision:
        request = (request_label,)
        for active in sorted(active_labels):
            key = frozenset({active, request_label})
            rule = _PAIR_RULES.get(key)
            if rule is None:
                if active in _LIGHT_LABELS or request_label in _LIGHT_LABELS:
                    continue
                return OverlapDecision(
                    allowed=False,
                    reason=f"unlisted heavy pair ({active} + {request_label}) defaults to deny",
                    request=_req(request_label),
                )
            if rule.startswith("allow"):
                continue
            if rule.startswith("conditional_presampling"):
                if self._vae_presampling():
                    continue
                return OverlapDecision(
                    allowed=False,
                    reason=f"{active} + {request_label}: {rule}",
                    request=_req(request_label),
                )
            if rule.startswith("conditional"):
                if self._vae_armed():
                    continue
                return OverlapDecision(
                    allowed=False,
                    reason=f"{active} + {request_label}: {rule}",
                    request=_req(request_label),
                )
            return OverlapDecision(allowed=False, reason=f"{active} + {request_label}: {rule}", request=_req(request_label))
        return OverlapDecision(allowed=True, reason="matrix allows", request=_req(request_label))

    def require(self, active_labels: Set[str], request_label: str) -> OverlapDecision:
        decision = self.check(active_labels, request_label)
        if not decision.allowed:
            raise ForbiddenOverlapError(
                f"forbidden overlap requested [{request_label}] with active "
                f"[{', '.join(sorted(active_labels))}]: {decision.reason}"
            )
        return decision


def _req(label: str):
    from .contracts import OverlapRequest

    return OverlapRequest(label=label, domains=())


class GoldenResourceScheduler:
    """Event-driven lifecycle state machine with resource-domain gating."""

    def __init__(self, ledger_sink=None) -> None:  # LedgerEventSink | None
        self._lock = threading.RLock()
        self._ledger = ledger_sink
        self._phase = LifecyclePhase.SNAPSHOT_CAPTURE
        self._history: List[Tuple[LifecyclePhase, str]] = [(LifecyclePhase.SNAPSHOT_CAPTURE, "init")]
        # R42: event-driven phase gate.  Set on EVERY phase transition so
        # waiters (e.g. the VAE demand path) block instead of spinning.
        self._phase_changed = threading.Event()
        self._grants: Dict[str, Grant] = {}
        self._grant_seq = 0
        self.unet_prepare_allowed = False
        self.clip_storage_released = False
        self.vae_qd_armed = False
        self.forced_releases: List[str] = []
        self._matrix = OverlapMatrix(
            vae_qd_armed_provider=lambda: self.vae_qd_armed,
            vae_qd_presampling_provider=lambda: self._vae_qd_presampling_window(),
        )

    # -- introspection -------------------------------------------------------

    @property
    def phase(self) -> LifecyclePhase:
        with self._lock:
            return self._phase

    @property
    def phase_history(self) -> List[Tuple[LifecyclePhase, str]]:
        with self._lock:
            return list(self._history)

    def active_labels(self) -> Set[str]:
        with self._lock:
            return set(self._grants.keys())

    def snapshot_state(self) -> dict:
        with self._lock:
            return {
                "phase": self._phase.value,
                "active": sorted(self._grants.keys()),
                "unet_prepare_allowed": self.unet_prepare_allowed,
                "clip_storage_released": self.clip_storage_released,
                "vae_qd_armed": self.vae_qd_armed,
                "forced_releases": list(self.forced_releases),
                "history_len": len(self._history),
            }

    # -- transitions -----------------------------------------------------------

    def begin_minimal_restore(self) -> LifecyclePhase:
        with self._lock:
            if self._phase != LifecyclePhase.SNAPSHOT_CAPTURE:
                raise GoldenError(f"begin_minimal_restore from phase {self._phase.value}")
            return self._enter(LifecyclePhase.MINIMAL_RESTORE, "begin_minimal_restore")

    def transition(self, event: GoldenEvent) -> LifecyclePhase:
        with self._lock:
            key = (self._phase, event)
            handler = self._TRANSITIONS.get(key)
            if handler is None:
                raise GoldenError(
                    f"illegal transition: event {event.value} not valid in phase {self._phase.value}; "
                    f"history_tail={[p.value for p, _ in self._history[-4:]]}"
                )
            return handler(self, event)

    # -- resources ---------------------------------------------------------------

    def acquire(self, label: str, domains: Sequence[ResourceDomain]) -> Grant:
        with self._lock:
            self._gate(label)
            self._matrix.require(set(self._grants.keys()), label)
            held_domains: Dict[ResourceDomain, str] = {}
            for g in self._grants.values():
                for d in g.domains:
                    held_domains.setdefault(d, g.label)
            for d in domains:
                if d in _EXCLUSIVE_DOMAINS and d in held_domains:
                    raise ForbiddenOverlapError(
                        f"exclusive domain {d.value} already held by [{held_domains[d]}]; "
                        f"request [{label}] denied"
                    )
            self._grant_seq += 1
            grant = Grant(label=label, domains=tuple(domains), grant_id=self._grant_seq)
            self._grants[label] = grant
            self._emit("resource_acquire", label=label, domains=[d.value for d in domains])
            return grant

    def release(self, grant: Grant) -> None:
        with self._lock:
            existing = self._grants.get(grant.label)
            if existing is None or existing.grant_id != grant.grant_id:
                raise GoldenError(f"release of unknown/stale grant [{grant.label}]")
            del self._grants[grant.label]
            self._emit("resource_release", label=grant.label)

    # -- internals ------------------------------------------------------------------

    def _enter(self, phase: LifecyclePhase, via: str) -> LifecyclePhase:
        self._phase = phase
        self._history.append((phase, via))
        self._phase_changed.set()
        self._emit("phase_transition", phase=phase.value, via=via)
        return phase

    def _gate(self, label: str) -> None:
        if label == ACT_UNET_BULK_SOURCE:
            if not self.unet_prepare_allowed:
                raise ForbiddenOverlapError(
                    "UNET source preparation before CLIP storage release (unet_prepare_allowed=False)"
                )
            if ACT_CLIP_QD_SOURCE in self._grants or ACT_CLIP_QD_H2D in self._grants:
                raise ForbiddenOverlapError("UNET bulk source requested while CLIP storage/H2D still held")
        if label == ACT_UNET_GPU_COMMIT and self._phase != LifecyclePhase.UNET_COMMIT:
            raise ForbiddenOverlapError(
                f"UNET GPU commit outside PHASE4 (current={self._phase.value}); requires CLIP_GPU_CRITICAL_DONE proof"
            )
        if label == ACT_VAE_QD and not self.vae_qd_armed:
            # Unarmed VAE QD is legal ONLY in the post-CLIP-load,
            # pre-sampling-start window (CLIP_FORWARD_UNET_PREPARE ..
            # SAMPLING without the ACT_SAMPLING grant).  R42 fix: the window
            # now also covers CLIP_FORWARD_UNET_PREPARE because VAELoader
            # demand commonly arrives while the graph is still inside the
            # loader/CLIP-forward-overlap phase — well before UNET_COMMIT.
            # CLIP_QD_LOAD still requires the arm proof, and heavy-domain
            # conflicts (CLIP transport, UNET bulk source) are still denied
            # by the overlap matrix / exclusive domains (demand-side callers
            # serialize via their own bounded retry).
            if (
                ACT_SAMPLING in self._grants
                or self._phase
                not in (
                    LifecyclePhase.CLIP_FORWARD_UNET_PREPARE,
                    LifecyclePhase.UNET_COMMIT,
                    LifecyclePhase.SAMPLING,
                )
            ):
                raise ForbiddenOverlapError(
                    "VAE QD before arming (requires FIRST_SAMPLER_STEP_PROVEN; "
                    "unarmed acquisition only after CLIP_DEVICE_READY "
                    "and before sampling start)"
                )
        if label == ACT_CLIP_QD_SOURCE and self._phase != LifecyclePhase.CLIP_QD_LOAD:
            raise ForbiddenOverlapError(
                f"CLIP QD source outside PHASE2 (current={self._phase.value})"
            )

    def _vae_qd_presampling_window(self) -> bool:
        """True in the post-CLIP-load, pre-sampling-start window.

        R42 fix: CLIP_FORWARD_UNET_PREPARE is included so unarmed VAE QD may
        overlap CLIP compute (disjoint resource domains; the overlap matrix
        still denies conflicts against CLIP transport and UNET bulk source).
        """
        with self._lock:
            return (
                self._phase
                in (
                    LifecyclePhase.CLIP_FORWARD_UNET_PREPARE,
                    LifecyclePhase.UNET_COMMIT,
                    LifecyclePhase.SAMPLING,
                )
                and ACT_SAMPLING not in self._grants
            )

    # -- R42 phase-gate waits (event-driven; NO busy spins) -------------------

    def _vae_qd_gate_open(self) -> bool:
        """True when an ACT_VAE_QD acquisition would pass the phase gate.

        Mirrors the unarmed branch of ``_gate`` exactly (plus the armed
        short-circuit), so a caller that waits on this predicate can never
        loop on a denial the gate itself would raise again.
        """
        with self._lock:
            if self.vae_qd_armed:
                return True
            return (
                ACT_SAMPLING not in self._grants
                and self._phase
                in (
                    LifecyclePhase.CLIP_FORWARD_UNET_PREPARE,
                    LifecyclePhase.UNET_COMMIT,
                    LifecyclePhase.SAMPLING,
                )
            )

    def wait_for_vae_qd_window(self, timeout_s: float) -> bool:
        """Block until an unarmed/armed VAE QD acquisition is phase-legal.

        Event-driven: wakes on every scheduler phase transition, with a
        defensive 0.25s re-check slice.  Returns True as soon as the gate is
        open, False on timeout.
        """
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while True:
            with self._lock:
                if self._vae_qd_gate_open():
                    return True
                self._phase_changed.clear()
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return False
            self._phase_changed.wait(timeout=min(remaining, 0.25))

    def wait_for_phase_change(self, timeout_s: float) -> bool:
        """Block until the next phase transition or timeout (event-driven)."""
        with self._lock:
            self._phase_changed.clear()
        return self._phase_changed.wait(timeout=max(0.0, float(timeout_s)))

    def _emit(self, name: str, **fields) -> None:
        if self._ledger is not None:
            try:
                self._ledger.emit(name, **fields)
            except Exception:
                pass

    # -- transition handlers ----------------------------------------------------------

    def _t_restore_ready(self, event: GoldenEvent) -> LifecyclePhase:
        return self._enter(LifecyclePhase.CLIP_QD_LOAD, event.value)

    def _t_clip_device_ready(self, event: GoldenEvent) -> LifecyclePhase:
        self.unet_prepare_allowed = True
        for stale in (ACT_CLIP_QD_SOURCE, ACT_CLIP_QD_H2D):
            if stale in self._grants:
                del self._grants[stale]
                self.forced_releases.append(stale)
        return self._enter(LifecyclePhase.CLIP_FORWARD_UNET_PREPARE, event.value)

    def _t_marker_storage_released(self, event: GoldenEvent) -> LifecyclePhase:
        self.clip_storage_released = True
        return self._enter(self._phase, event.value)

    def _t_marker_clip_forward_started(self, event: GoldenEvent) -> LifecyclePhase:
        return self._enter(self._phase, event.value)

    def _t_clip_critical_done(self, event: GoldenEvent) -> LifecyclePhase:
        return self._enter(LifecyclePhase.UNET_COMMIT, event.value)

    def _t_unet_device_ready(self, event: GoldenEvent) -> LifecyclePhase:
        return self._enter(LifecyclePhase.SAMPLING, event.value)

    def _t_sampling_started(self, event: GoldenEvent) -> LifecyclePhase:
        return self._enter(self._phase, event.value)

    def _t_first_step_proven(self, event: GoldenEvent) -> LifecyclePhase:
        self.vae_qd_armed = True
        return self._enter(self._phase, event.value)

    def _t_unet_prepare_started(self, event: GoldenEvent) -> LifecyclePhase:
        return self._enter(self._phase, event.value)

    def _t_vae_qd_allowed(self, event: GoldenEvent) -> LifecyclePhase:
        self.vae_qd_armed = True
        return self._enter(self._phase, event.value)

    def _t_vae_device_ready(self, event: GoldenEvent) -> LifecyclePhase:
        return self._enter(self._phase, event.value)

    def _t_vae_decode_demand(self, event: GoldenEvent) -> LifecyclePhase:
        return self._enter(LifecyclePhase.OUTPUT_DELIVERY, event.value)

    def _t_first_durable(self, event: GoldenEvent) -> LifecyclePhase:
        return self._enter(LifecyclePhase.COMPLETE, event.value)


GoldenResourceScheduler._TRANSITIONS = {
    (LifecyclePhase.MINIMAL_RESTORE, GoldenEvent.RESTORE_READY): GoldenResourceScheduler._t_restore_ready,
    (LifecyclePhase.CLIP_QD_LOAD, GoldenEvent.CLIP_DEVICE_READY): GoldenResourceScheduler._t_clip_device_ready,
    (
        LifecyclePhase.CLIP_FORWARD_UNET_PREPARE,
        GoldenEvent.CLIP_STORAGE_RELEASED,
    ): GoldenResourceScheduler._t_marker_storage_released,
    (
        LifecyclePhase.CLIP_FORWARD_UNET_PREPARE,
        GoldenEvent.CLIP_FORWARD_STARTED,
    ): GoldenResourceScheduler._t_marker_clip_forward_started,
    (
        LifecyclePhase.CLIP_FORWARD_UNET_PREPARE,
        GoldenEvent.CLIP_GPU_CRITICAL_DONE,
    ): GoldenResourceScheduler._t_clip_critical_done,
    (
        LifecyclePhase.CLIP_FORWARD_UNET_PREPARE,
        GoldenEvent.UNET_PREPARE_STARTED,
    ): GoldenResourceScheduler._t_unet_prepare_started,
    (LifecyclePhase.UNET_COMMIT, GoldenEvent.UNET_DEVICE_READY): GoldenResourceScheduler._t_unet_device_ready,
    # R42: VAE_DEVICE_READY is a phase-preserving marker in the widened
    # unarmed-VAE window — a demand-side VAE QD load may complete while the
    # pipeline is still inside PHASE3/PHASE4.
    (
        LifecyclePhase.CLIP_FORWARD_UNET_PREPARE,
        GoldenEvent.VAE_DEVICE_READY,
    ): GoldenResourceScheduler._t_vae_device_ready,
    (LifecyclePhase.UNET_COMMIT, GoldenEvent.VAE_DEVICE_READY): GoldenResourceScheduler._t_vae_device_ready,
    (LifecyclePhase.SAMPLING, GoldenEvent.SAMPLING_STARTED): GoldenResourceScheduler._t_sampling_started,
    (LifecyclePhase.SAMPLING, GoldenEvent.FIRST_SAMPLER_STEP_PROVEN): GoldenResourceScheduler._t_first_step_proven,
    (LifecyclePhase.SAMPLING, GoldenEvent.VAE_QD_ALLOWED): GoldenResourceScheduler._t_vae_qd_allowed,
    (LifecyclePhase.SAMPLING, GoldenEvent.VAE_DEVICE_READY): GoldenResourceScheduler._t_vae_device_ready,
    (LifecyclePhase.SAMPLING, GoldenEvent.VAE_DECODE_DEMAND): GoldenResourceScheduler._t_vae_decode_demand,
    (LifecyclePhase.OUTPUT_DELIVERY, GoldenEvent.FIRST_DURABLE_RESULT): GoldenResourceScheduler._t_first_durable,
}
