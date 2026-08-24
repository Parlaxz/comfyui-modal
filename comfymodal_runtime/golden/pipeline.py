"""Golden pipeline facade — the ONE deterministic schedule for CLIP/UNET/VAE.

Role policy is immutable: every role uses the SAME GoldenQD4Loader engine at
QD4.  There is NO adaptive loader selection: a slow QD4 is recorded as a slow
QD4; a hard failure may only recover through the DEGRADED path and can never
be classified ACCEPTED_NOMINAL.

Timeline (event-driven, never timer-driven):

    PHASE0 snapshot (static metadata only)
    PHASE1 minimal restore            --RESTORE_READY-->
    PHASE2 CLIP QD4 first priority    --CLIP_DEVICE_READY-->
    PHASE3 CLIP forward + UNET prepare--CLIP_GPU_CRITICAL_DONE-->
    PHASE4 UNET QD4 commit            --UNET_DEVICE_READY-->
    PHASE5 sampling                   --FIRST_SAMPLER_STEP_PROVEN-->
    PHASE6 VAE QD4 in sampling slack  --VAE_DECODE_DEMAND-->
    PHASE7 output                     --FIRST_DURABLE_RESULT--> COMPLETE

Conditioning cache contract is enforced here: forced miss, encode_calls=1,
persist=0 — no exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from .contracts import (
    DEFAULT_CONDITIONING_CONTRACT,
    ConditioningContract,
    DegradationRecord,
    DegradedReason,
    DestinationPlan,
    ForbiddenOverlapError,
    GoldenError,
    GoldenEvent,
    InMemoryLedgerSink,
    LedgerEventSink,
    LifecyclePhase,
    LoadResult,
    ModelRole,
    NULL_LEDGER_SINK,
    PrepareCommitIdentityError,
    PreparedSource,
    ResourceDomain,
    RoleManifest,
    RuntimeStatus,
)
from .model_owner import GoldenModelOwner, GoldenOwnerRegistry
from .qd_engine import GoldenQD4Loader
from .resource_scheduler import (
    ACT_CLIP_FORWARD,
    ACT_CLIP_GPU_CRITICAL,
    ACT_CLIP_QD_H2D,
    ACT_CLIP_QD_SOURCE,
    ACT_SAMPLING,
    ACT_UNET_BULK_SOURCE,
    ACT_UNET_H2D,
    ACT_UNET_METADATA_PREP,
    ACT_VAE_GPU_MUTATION,
    ACT_VAE_QD,
    Grant,
    GoldenResourceScheduler,
)

__all__ = [
    "GOLDEN_ROLE_LOADER_POLICY",
    "RoleBinding",
    "GoldenPipeline",
    "classify_hard_failure",
    "final_status",
    "assert_fallback_never_nominal",
]

#: Immutable Golden role configuration.  No adaptive selection exists.
GOLDEN_ROLE_LOADER_POLICY: Mapping[ModelRole, str] = MappingProxyType(
    {ModelRole.CLIP: "QD4", ModelRole.UNET: "QD4", ModelRole.VAE: "QD4"}
)

_ROLE_EVENTS = {
    ModelRole.CLIP: GoldenEvent.CLIP_DEVICE_READY,
    ModelRole.UNET: GoldenEvent.UNET_DEVICE_READY,
    ModelRole.VAE: GoldenEvent.VAE_DEVICE_READY,
}

#: Per-role grant specs: (activity_label, domains).  CLIP/UNET split source
#: and H2D into two grants; VAE is small enough that one grant holds both
#: heavy domains (same activity label, no self-pair matrix interaction).
_ROLE_GRANTS = {
    ModelRole.CLIP: (
        (ACT_CLIP_QD_SOURCE, (ResourceDomain.STORAGE_HEAVY,)),
        (ACT_CLIP_QD_H2D, (ResourceDomain.H2D_HEAVY,)),
    ),
    ModelRole.UNET: (
        (ACT_UNET_BULK_SOURCE, (ResourceDomain.STORAGE_HEAVY,)),
        (ACT_UNET_H2D, (ResourceDomain.H2D_HEAVY,)),
    ),
    ModelRole.VAE: (
        (ACT_VAE_QD, (ResourceDomain.STORAGE_HEAVY, ResourceDomain.H2D_HEAVY)),
    ),
}


@dataclass(frozen=True)
class RoleBinding:
    role: ModelRole
    manifest: RoleManifest
    destination_factory: Callable[[], DestinationPlan]


class _StripPrefixSink:
    """Ledger wrapper rewriting ``unet_qd_<name>`` engine events to canonical names.

    Used for the UNET prepare/commit path so engine events emitted with the
    ``unet_qd`` label surface under their canonical pipeline names
    (unet_prepare_start, unet_source_first_completion, unet_h2d_start,
    unet_device_ready, ...).
    """

    _REWRITES = {
        "prepare_start": "unet_prepare_start",
        "source_first_completion": "unet_source_first_completion",
        "source_last_completion": "unet_source_last_completion",
        "source_complete": "unet_source_complete",
        "source_prepared": "unet_source_prepared",
        "commit_start": "unet_commit_start",
        "submit_start": "unet_commit_load_start",
        "h2d_start": "unet_h2d_start",
        "h2d_end": "unet_h2d_end",
        "device_ready": "unet_device_ready",
    }

    def __init__(self, inner: LedgerEventSink, prefix: str = "unet_qd_") -> None:
        self._inner = inner
        self._prefix = prefix

    def emit(self, event_name: str, **fields) -> None:
        name = event_name
        if event_name.startswith(self._prefix):
            base = event_name[len(self._prefix):]
            name = self._REWRITES.get(base, f"unet_{base}")
        self._inner.emit(name, **fields)


class GoldenPipeline:
    """Orchestrates loader + ownership + scheduler through one schedule."""

    def __init__(
        self,
        scheduler: GoldenResourceScheduler,
        ledger_sink: Optional[LedgerEventSink] = None,
        conditioning: ConditioningContract = DEFAULT_CONDITIONING_CONTRACT,
        owner_registry: Optional[GoldenOwnerRegistry] = None,
        join_timeout_s: float = 120.0,
    ) -> None:
        self.scheduler = scheduler
        self.ledger = ledger_sink if ledger_sink is not None else NULL_LEDGER_SINK
        self.conditioning = conditioning
        self.registry = owner_registry if owner_registry is not None else GoldenOwnerRegistry()
        self.join_timeout_s = join_timeout_s
        self._grants: Dict[str, Grant] = {}
        self._prepared_sources: Dict[ModelRole, PreparedSource] = {}

    @property
    def prepared_sources(self) -> Dict[ModelRole, PreparedSource]:
        """Snapshot copy of stored prepared sources (tests / telemetry)."""
        return dict(self._prepared_sources)

    # -- lifecycle -----------------------------------------------------------

    def begin_restore(self) -> None:
        self.scheduler.begin_minimal_restore()

    def restore_ready(self) -> None:
        self.scheduler.transition(GoldenEvent.RESTORE_READY)
        self._emit(GoldenEvent.RESTORE_READY.value)

    # -- loads -----------------------------------------------------------------

    def run_role_load(
        self,
        role: ModelRole,
        loader: GoldenQD4Loader,
        binding: RoleBinding,
        label_prefix: str = "",
        owner: Optional[GoldenModelOwner] = None,
    ) -> Tuple[LoadResult, GoldenModelOwner]:
        if GOLDEN_ROLE_LOADER_POLICY[role] != "QD4":
            raise GoldenError(f"role policy corruption for {role.value}")
        grants = [self.scheduler.acquire(label, domains) for label, domains in _ROLE_GRANTS[role]]
        if owner is None:
            owner = GoldenModelOwner(role, binding.manifest.identity_hash)
        try:
            # Register BEFORE the I/O so demand sides can JOIN during the load.
            if self.registry.get(role) is not owner:
                self.registry.register(owner)
            destination = binding.destination_factory()
            result = loader.load(
                binding.manifest,
                destination,
                ledger_sink=self.ledger,
                label=(f"{label_prefix}_{role.value}_qd" if label_prefix else f"{role.value}_qd"),
            )
        except Exception as exc:
            try:
                owner.publish_failure(exc)
            except Exception:
                pass
            for grant in reversed(grants):
                self.scheduler.release(grant)
            raise
        owner.publish_device_ready(destination)
        for grant in reversed(grants):
            self.scheduler.release(grant)
        event = _ROLE_EVENTS[role]
        self.scheduler.transition(event)
        self._emit(event.value, role=role.value, identity=binding.manifest.identity_hash)
        return result, owner

    # -- CLIP forward ------------------------------------------------------------

    def begin_clip_forward(self) -> None:
        self._grants[ACT_CLIP_FORWARD] = self.scheduler.acquire(ACT_CLIP_FORWARD, (ResourceDomain.GPU_COMPUTE,))
        self._grants[ACT_CLIP_GPU_CRITICAL] = self.scheduler.acquire(
            ACT_CLIP_GPU_CRITICAL, (ResourceDomain.GPU_MUTATION,)
        )
        self.scheduler.transition(GoldenEvent.CLIP_FORWARD_STARTED)
        self._emit(GoldenEvent.CLIP_FORWARD_STARTED.value)

    def clip_forward_complete(self) -> None:
        grant = self._grants.pop(ACT_CLIP_FORWARD, None)
        if grant is not None:
            self.scheduler.release(grant)

    def clip_storage_release_proof(self) -> None:
        self.scheduler.transition(GoldenEvent.CLIP_STORAGE_RELEASED)
        self._emit(GoldenEvent.CLIP_STORAGE_RELEASED.value)

    def clip_gpu_critical_done(self) -> None:
        grant = self._grants.pop(ACT_CLIP_GPU_CRITICAL, None)
        if grant is not None:
            self.scheduler.release(grant)
        self.scheduler.transition(GoldenEvent.CLIP_GPU_CRITICAL_DONE)
        self._emit(GoldenEvent.CLIP_GPU_CRITICAL_DONE.value)

    # -- UNET ----------------------------------------------------------------------

    def unet_prepare(self, binding: RoleBinding, loader: "GoldenQD4Loader") -> PreparedSource:
        """Storage-side source preparation overlapping CLIP compute (PHASE3).

        Requires the CLIP_FORWARD_UNET_PREPARE phase AND the
        clip_storage_released proof flag.  Acquires the unet_bulk_source
        activity over [STORAGE_HEAVY, CPU_HEAVY] and runs the engine's
        page-cache-warming prepare pass.  Performs NO transfer and NO GPU
        mutation; the QD4 commit happens in PHASE4 after
        CLIP_GPU_CRITICAL_DONE via run_unet_commit.
        """
        if self.scheduler.phase != LifecyclePhase.CLIP_FORWARD_UNET_PREPARE:
            raise ForbiddenOverlapError(
                f"UNET prepare outside PHASE3 (current={self.scheduler.phase.value})"
            )
        if not self.scheduler.clip_storage_released:
            raise ForbiddenOverlapError("UNET prepare before CLIP storage release proof")
        grant = self.scheduler.acquire(
            ACT_UNET_BULK_SOURCE, (ResourceDomain.STORAGE_HEAVY, ResourceDomain.CPU_HEAVY)
        )
        try:
            prepared = loader.prepare_source(
                binding.manifest, ledger_sink=_StripPrefixSink(self.ledger), label="unet_qd"
            )
        except Exception:
            self.scheduler.release(grant)
            raise
        self.scheduler.release(grant)
        self._prepared_sources[ModelRole.UNET] = prepared
        self.scheduler.transition(GoldenEvent.UNET_PREPARE_STARTED)
        self._emit(
            GoldenEvent.UNET_PREPARE_STARTED.value,
            role=ModelRole.UNET.value,
            identity=binding.manifest.identity_hash,
            block_count=prepared.block_count,
        )
        return prepared

    def run_unet_commit(
        self,
        loader: GoldenQD4Loader,
        binding: RoleBinding,
        owner: Optional[GoldenModelOwner] = None,
    ) -> Tuple[LoadResult, GoldenModelOwner]:
        """PHASE4: consume the stored PreparedSource and commit to device."""
        prepared = self._prepared_sources.get(ModelRole.UNET)
        if (
            prepared is None
            or prepared.manifest_identity_hash != binding.manifest.identity_hash
            or prepared.role != binding.manifest.role
        ):
            raise PrepareCommitIdentityError(
                "no matching prepared UNET source for commit (unet_prepare must run first "
                "with an identity-equal manifest)"
            )
        if self.scheduler.phase != LifecyclePhase.UNET_COMMIT:
            raise ForbiddenOverlapError(
                f"UNET commit outside PHASE4 (current={self.scheduler.phase.value}); "
                f"requires CLIP_GPU_CRITICAL_DONE proof"
            )
        sink = _StripPrefixSink(self.ledger)
        self._emit("unet_commit_start", role=ModelRole.UNET.value, identity=binding.manifest.identity_hash)
        if owner is None:
            # Register BEFORE the commit I/O so demand sides can JOIN during it.
            owner = GoldenModelOwner(ModelRole.UNET, binding.manifest.identity_hash)
            self.registry.register(owner)
        grants: List[Grant] = []
        try:
            grants.append(self.scheduler.acquire(ACT_UNET_BULK_SOURCE, (ResourceDomain.STORAGE_HEAVY,)))
            grants.append(self.scheduler.acquire(ACT_UNET_H2D, (ResourceDomain.H2D_HEAVY,)))
            destination = binding.destination_factory()
            result = loader.commit_to_device(
                prepared, binding.manifest, destination, ledger_sink=sink, label="unet_qd"
            )
        except Exception as exc:
            try:
                owner.publish_failure(exc)
            except Exception:
                pass
            for grant in reversed(grants):
                self.scheduler.release(grant)
            raise
        owner.publish_device_ready(destination)
        self._emit("unet_bind", role=ModelRole.UNET.value, identity=binding.manifest.identity_hash)
        for grant in reversed(grants):
            self.scheduler.release(grant)
        self.scheduler.transition(GoldenEvent.UNET_DEVICE_READY)
        self._emit(
            GoldenEvent.UNET_DEVICE_READY.value,
            role=ModelRole.UNET.value,
            identity=binding.manifest.identity_hash,
        )
        return result, owner

    # -- sampling / VAE ---------------------------------------------------------------

    def sampling_started(self) -> None:
        self._grants[ACT_SAMPLING] = self.scheduler.acquire(ACT_SAMPLING, (ResourceDomain.GPU_COMPUTE,))
        self.scheduler.transition(GoldenEvent.SAMPLING_STARTED)
        self._emit(GoldenEvent.SAMPLING_STARTED.value)

    def first_sampler_step_proven(self) -> None:
        self.scheduler.transition(GoldenEvent.FIRST_SAMPLER_STEP_PROVEN)
        self._emit(GoldenEvent.FIRST_SAMPLER_STEP_PROVEN.value)

    def run_vae_qd(self, loader: GoldenQD4Loader, binding: RoleBinding) -> Tuple[LoadResult, GoldenModelOwner]:
        return self.run_role_load(ModelRole.VAE, loader, binding)

    def vae_decode_demand(self, join_timeout_s: Optional[float] = None) -> Dict[str, object]:
        from .contracts import JoinDecision

        decision, owner = self.registry.join_or_adopt(
            ModelRole.VAE, self.join_timeout_s if join_timeout_s is None else join_timeout_s
        )
        self.scheduler.transition(GoldenEvent.VAE_DECODE_DEMAND)
        self._emit(GoldenEvent.VAE_DECODE_DEMAND.value, decision=decision.value)
        if decision in (JoinDecision.JOINED, JoinDecision.ALREADY_READY):
            return {"decision": decision.value, "owner": owner, "degradation": None}
        if decision == JoinDecision.ADOPTED:
            degradation = DegradationRecord(
                reason=DegradedReason.IMMUTABLE_METADATA_ABSENT,
                detail={"cause": "no_golden_vae_owner_at_demand"},
                fallback_used=True,
            )
        elif decision == JoinDecision.TIMEOUT:
            degradation = DegradationRecord(
                reason=DegradedReason.OWNER_JOIN_TIMEOUT, detail={}, fallback_used=True
            )
        else:
            degradation = DegradationRecord(
                reason=DegradedReason.QD_HARD_FAILURE_FALLBACK,
                detail={"producer_failure": str(owner.failure) if owner else "unknown"},
                fallback_used=True,
            )
        return {"decision": decision.value, "owner": owner, "degradation": degradation}

    def vae_gpu_mutation_begin(self) -> Grant:
        return self.scheduler.acquire(ACT_VAE_GPU_MUTATION, (ResourceDomain.GPU_MUTATION,))

    def complete_output(self) -> None:
        grant = self._grants.pop(ACT_SAMPLING, None)
        if grant is not None:
            self.scheduler.release(grant)
        self.scheduler.transition(GoldenEvent.FIRST_DURABLE_RESULT)
        self._emit(GoldenEvent.FIRST_DURABLE_RESULT.value)

    # -- conditioning contract ----------------------------------------------------------

    def check_conditioning_observed(self, observed_miss: bool, observed_encodes: int, observed_persisted: int) -> None:
        self.conditioning.validate_observed(observed_miss, observed_encodes, observed_persisted)

    def _emit(self, name: str, **fields) -> None:
        try:
            self.ledger.emit(name, **fields)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Fallback semantics — a fallback can NEVER be ACCEPTED_NOMINAL
# ---------------------------------------------------------------------------


def classify_hard_failure(exc: Exception) -> DegradationRecord:
    return DegradationRecord(
        reason=DegradedReason.QD_HARD_FAILURE_FALLBACK,
        detail={"exception_type": type(exc).__name__, "message": str(exc)},
        fallback_used=True,
    )


def final_status(result_ok: bool, degradation: Optional[DegradationRecord]) -> RuntimeStatus:
    if degradation is not None:
        return RuntimeStatus.DEGRADED
    if not result_ok:
        return RuntimeStatus.FAILED
    return RuntimeStatus.ACCEPTED_NOMINAL


def assert_fallback_never_nominal(degradation: Optional[DegradationRecord]) -> None:
    if degradation is not None:
        raise GoldenError(
            f"fallback path ({degradation.reason.value}) attempted to proceed as ACCEPTED_NOMINAL"
        )
