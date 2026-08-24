"""R41 Golden pipeline shared contracts.

This module is the ONLY cross-module coupling surface of the Golden QD4
pipeline.  Implementation modules (`qd_engine`, `model_owner`,
`resource_scheduler`, `snapshot`, `pipeline`) import types from here and
nothing else from each other.

E40 reconciliation notes (do not remove until reconciled):
- No environment reads and no deploy-baked config lookups happen here.
  Canonical configuration truth remains owned by E40; Golden role
  configuration is immutable by design (CLIP=QD4, UNET=QD4, VAE=QD4).
- RuntimeStatus/DegradedReason are R41-local enums.  E40 may later map
  them onto its canonical RuntimeStatus/ledger vocabulary; the mapping
  belongs in `pipeline`, not here.
- Provider/region/cloud/host identity is telemetry-only and must never
  influence algorithm selection.
"""

from __future__ import annotations

import enum
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence, Tuple, runtime_checkable

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Canonical expected output SHA for the exactness gate.
EXACT_OUTPUT_SHA = "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"

#: Golden block size: 32 MiB static contiguous ranges.
DEFAULT_BLOCK_BYTES = 32 * 1024 * 1024

#: Golden configured queue depth for every model role.
GOLDEN_QUEUE_DEPTH = 4


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ModelRole(str, enum.Enum):
    """Semantic ownership roles.  All three use the SAME QD4 loader engine."""

    CLIP = "clip"
    UNET = "unet"
    VAE = "vae"


class ResourceDomain(str, enum.Enum):
    """Distinct resource domains modeled by the scheduler."""

    STORAGE_HEAVY = "storage_heavy"
    H2D_HEAVY = "h2d_heavy"
    GPU_MUTATION = "gpu_mutation"
    GPU_COMPUTE = "gpu_compute"
    CPU_HEAVY = "cpu_heavy"


class LifecyclePhase(str, enum.Enum):
    """Deterministic Golden timeline phases."""

    SNAPSHOT_CAPTURE = "phase0_snapshot"
    MINIMAL_RESTORE = "phase1_minimal_restore"
    CLIP_QD_LOAD = "phase2_clip_qd4"
    CLIP_FORWARD_UNET_PREPARE = "phase3_clip_forward_unet_prepare"
    UNET_COMMIT = "phase4_unet_commit"
    SAMPLING = "phase5_sampling"
    VAE_QD_LOAD = "phase6_vae_qd4_sampling_slack"
    OUTPUT_DELIVERY = "phase7_output"
    COMPLETE = "complete"


class GoldenEvent(str, enum.Enum):
    """Proof/event names that drive phase transitions.  Never timers."""

    RESTORE_READY = "restore_ready"
    CLIP_DEVICE_READY = "clip_device_ready"
    CLIP_STORAGE_RELEASED = "clip_storage_released"
    CLIP_FORWARD_STARTED = "clip_forward_started"
    CLIP_GPU_CRITICAL_DONE = "clip_gpu_critical_done"
    UNET_PREPARE_STARTED = "unet_prepare_started"
    UNET_DEVICE_READY = "unet_device_ready"
    SAMPLING_STARTED = "sampling_started"
    FIRST_SAMPLER_STEP_PROVEN = "first_sampler_step_proven"
    VAE_QD_ALLOWED = "vae_qd_allowed"
    VAE_DEVICE_READY = "vae_device_ready"
    VAE_DECODE_DEMAND = "vae_decode_demand"
    FIRST_DURABLE_RESULT = "first_durable_result"


class RuntimeStatus(str, enum.Enum):
    """Run classification.  A fallback run can NEVER be ACCEPTED_NOMINAL."""

    ACCEPTED_NOMINAL = "accepted_nominal"
    DEGRADED = "degraded"
    FAILED = "failed"


class DegradedReason(str, enum.Enum):
    """Exact recorded cause when a run is classified DEGRADED."""

    QD_HARD_FAILURE_FALLBACK = "qd_hard_failure_fallback"
    IMMUTABLE_METADATA_ABSENT = "immutable_metadata_absent"
    OWNER_JOIN_TIMEOUT = "owner_join_timeout"
    BIND_VALIDATION_FAILED = "bind_validation_failed"


class DestinationKind(str, enum.Enum):
    """How a loaded byte range is placed on device."""

    CONTIGUOUS_GPU_BUFFER = "contiguous_gpu_buffer"  # one buffer, tensor views
    PARAMETER_COPY_TARGET = "parameter_copy_target"  # copy into live params


class OwnershipState(str, enum.Enum):
    PREPARING = "preparing"
    DEVICE_READY = "device_ready"
    BIND_READY = "bind_ready"
    PUBLISHED = "published"
    FAILED = "failed"
    RELEASED = "released"


class JoinDecision(str, enum.Enum):
    JOINED = "joined"                    # waited on an in-flight producer
    ALREADY_READY = "already_ready"      # terminal ready state observed
    ADOPTED = "adopted"                  # no producer existed; caller proceeds
    FAILED = "failed"                    # producer failed -> caller falls back
    TIMEOUT = "timeout"


class QDDropReason(str, enum.Enum):
    """Why outstanding source reads fell below the configured queue depth."""

    STARTUP_RAMP = "startup_ramp"
    TAIL_DRAIN = "tail_drain"
    H2D_BACKPRESSURE = "h2d_backpressure"
    WORKER_EXCEPTION = "worker_exception"
    SCHEDULER_BLOCKED = "scheduler_blocked"
    SOURCE_SERVICE = "source_service"
    UNEXPLAINED = "unexplained"
    OTHER = "other"  # compat: legacy catch-all; classification now uses UNEXPLAINED


# ---------------------------------------------------------------------------
# Exceptions (fail-closed taxonomy)
# ---------------------------------------------------------------------------


class GoldenError(Exception):
    """Base class for all Golden pipeline failures."""


class GoldenQDFailure(GoldenError):
    """Transactional QD load failure; callers must classify DEGRADED/FAILED."""


class SourceReadError(GoldenQDFailure):
    pass


class ShortReadError(SourceReadError):
    pass


class WorkerCrashedError(GoldenQDFailure):
    pass


class CoverageReconciliationError(GoldenQDFailure):
    """Range coverage incomplete / duplicated / unreconciled."""


class PrepareCommitIdentityError(GoldenQDFailure):
    """Prepared-source identity gate failed or lifecycle already consumed."""


class BindError(GoldenQDFailure):
    pass


class ForbiddenOverlapError(GoldenError):
    """A resource request violated the overlap allow/deny matrix."""


class QuiescenceViolationError(GoldenError):
    """Snapshot capture attempted while workers were not quiescent."""


class ImmutableStateAbsentError(GoldenError):
    """Required snapshot-resident immutable metadata was unexpectedly absent."""


# ---------------------------------------------------------------------------
# Static plan structures (snapshot-resident immutable metadata)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TensorMapEntry:
    """One safetensors tensor: absolute file offsets include the data offset."""

    name: str
    dtype: str
    shape: Tuple[int, ...]
    abs_start: int
    abs_end: int


@dataclass(frozen=True)
class SafetensorsLayout:
    header_bytes: int
    data_start: int
    file_bytes: int
    tensor_map: Tuple[TensorMapEntry, ...]


@dataclass(frozen=True)
class CopySegment:
    """One destination write for a piece of a source block."""

    buffer_index: int
    dest_offset: int
    src_offset: int
    length: int


@dataclass(frozen=True)
class BlockPlan:
    index: int
    file_start: int
    file_end: int
    segments: Tuple[CopySegment, ...]

    @property
    def length(self) -> int:
        return self.file_end - self.file_start


@dataclass(frozen=True)
class QDRangePlan:
    """Static contiguous range decomposition.  Complete, ordered, non-overlapping."""

    block_bytes: int
    data_start: int
    data_end: int
    blocks: Tuple[BlockPlan, ...]

    @property
    def n_blocks(self) -> int:
        return len(self.blocks)

    @property
    def total_bytes(self) -> int:
        return self.data_end - self.data_start

    @staticmethod
    def build(layout: SafetensorsLayout, block_bytes: int, buffer_mode: str = "contiguous") -> "QDRangePlan":
        """Decompose [data_start, file_bytes) into contiguous block ranges.

        ``buffer_mode="contiguous"`` maps every segment onto destination
        buffer 0 at its absolute position within the data region (one flat
        device buffer).  ``buffer_mode="per_tensor"`` assigns one buffer per
        tensor (exact-sized destinations such as CUDA parameters).
        Inter-tensor padding gaps are tolerated (gap bytes have no
        destination); overlaps are fatal.
        """
        if block_bytes <= 0:
            raise ValueError("block_bytes must be positive")
        if buffer_mode not in ("contiguous", "per_tensor"):
            raise ValueError(f"unknown buffer_mode {buffer_mode!r}")
        data_start = layout.data_start
        data_end = layout.file_bytes
        if data_end < data_start:
            raise ValueError("file smaller than safetensors data offset")

        # Sort tensors by file position.  Overlaps are fatal; inter-tensor
        # padding gaps are tolerated (gap bytes have no destination and are
        # never surfaced through tensor views).
        entries = sorted(layout.tensor_map, key=lambda t: t.abs_start)
        cursor = data_start
        for entry in entries:
            if entry.abs_start < cursor:
                raise CoverageReconciliationError(
                    f"tensor map overlap at {entry.name}: starts {entry.abs_start} before cursor {cursor}"
                )
            if entry.abs_end <= entry.abs_start:
                raise CoverageReconciliationError(f"empty tensor range for {entry.name}")
            cursor = entry.abs_end

        if buffer_mode == "contiguous":
            buffers: Dict[str, int] = {entry.name: 0 for entry in entries}
        else:
            buffers = {entry.name: i for i, entry in enumerate(entries)}

        blocks = []
        index = 0
        pos = data_start
        while pos < data_end:
            end = min(pos + block_bytes, data_end)
            segments = _segments_for_range(entries, buffers, pos, end, data_start, buffer_mode)
            blocks.append(BlockPlan(index=index, file_start=pos, file_end=end, segments=segments))
            index += 1
            pos = end
        return QDRangePlan(block_bytes=block_bytes, data_start=data_start, data_end=data_end, blocks=tuple(blocks))


def _segments_for_range(
    entries: Sequence[TensorMapEntry],
    buffers: Dict[str, int],
    range_start: int,
    range_end: int,
    data_start: int,
    buffer_mode: str,
) -> Tuple[CopySegment, ...]:
    segments = []
    for entry in entries:
        s = max(entry.abs_start, range_start)
        e = min(entry.abs_end, range_end)
        if s >= e:
            continue
        if buffer_mode == "contiguous":
            dest_offset = s - data_start
        else:
            dest_offset = s - entry.abs_start
        segments.append(
            CopySegment(
                buffer_index=buffers[entry.name],
                dest_offset=dest_offset,
                src_offset=s - range_start,
                length=e - s,
            )
        )
    return tuple(segments)


@dataclass(frozen=True)
class RoleManifest:
    """Immutable per-role manifest (snapshot-resident static metadata)."""

    role: ModelRole
    model_path: str
    file_sha256: str
    layout: SafetensorsLayout
    identity_hash: str
    destination_kind: DestinationKind
    qd_range_plan: QDRangePlan
    meta_params_count: int = 0
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class DestinationPlan:
    """Allocated device destinations for one load.

    ``buffers`` holds opaque backend handles (torch tensors in practice);
    ``buffer_bytes[i]`` is the exact size of buffer ``i``.
    """

    kind: DestinationKind
    buffers: list[Any]
    buffer_bytes: list[int]

    def validate(self, manifest: RoleManifest) -> None:
        expected = {seg.buffer_index for blk in manifest.qd_range_plan.blocks for seg in blk.segments}
        missing = [i for i in sorted(expected) if i >= len(self.buffers)]
        if missing:
            raise BindError(f"destination buffers missing indices {missing}")
        for blk in manifest.qd_range_plan.blocks:
            for seg in blk.segments:
                need = seg.dest_offset + seg.length
                if need > self.buffer_bytes[seg.buffer_index]:
                    raise BindError(
                        f"block {blk.index} segment overruns buffer {seg.buffer_index}: {need} > {self.buffer_bytes[seg.buffer_index]}"
                    )


# ---------------------------------------------------------------------------
# Prepared source (storage-side page-cache warming result)
# ---------------------------------------------------------------------------


_PREPARED_SOURCE_LOCK = threading.Lock()

#: Lifecycle statuses of a PreparedSource.
SOURCE_PREPARED = "SOURCE_PREPARED"
SOURCE_CONSUMED = "CONSUMED"


@dataclass(frozen=True)
class PreparedSource:
    """Bounded, state-safe result of storage-side source preparation.

    Carries ONLY identity metadata and aggregate preparation statistics —
    never buffers, never pinned memory references.  The lifecycle status
    moves SOURCE_PREPARED -> CONSUMED exactly once (atomically) when a
    commit claims it; a second commit attempt fails closed.
    """

    role: ModelRole
    manifest_identity_hash: str
    source_path: str
    range_plan_fingerprint: str
    block_count: int
    total_bytes: int
    prep_wall_ms: float
    prep_aggregate_gbps: float
    prep_source_latency_p50_ms: float
    prep_source_latency_p90_ms: float
    prep_source_latency_p99_ms: float
    residency_proof: Dict[str, Any] = field(default_factory=dict)
    prepared_at_mono_ns: int = 0
    lifecycle_status: str = SOURCE_PREPARED

    def try_consume(self) -> bool:
        """Atomically transition SOURCE_PREPARED -> CONSUMED exactly once."""
        with _PREPARED_SOURCE_LOCK:
            if self.lifecycle_status != SOURCE_PREPARED:
                return False
            object.__setattr__(self, "lifecycle_status", SOURCE_CONSUMED)
            return True


# ---------------------------------------------------------------------------
# Conditioning cache contract (the deliberate exception)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConditioningContract:
    """Golden benchmark behavior: forced miss, one encode, never persist."""

    forced_miss: bool = True
    encode_calls: int = 1
    persist: int = 0

    def validate_observed(self, observed_miss: bool, observed_encodes: int, observed_persisted: int) -> None:
        if not self.forced_miss or observed_miss is not False:
            raise GoldenError("conditioning contract violation: miss was not forced")
        if observed_encodes != self.encode_calls:
            raise GoldenError(f"conditioning contract violation: encode_calls={observed_encodes} != {self.encode_calls}")
        if observed_persisted != self.persist:
            raise GoldenError(f"conditioning contract violation: persisted={observed_persisted} != {self.persist}")


DEFAULT_CONDITIONING_CONTRACT = ConditioningContract()


# ---------------------------------------------------------------------------
# Transfer backend abstraction (CUDA production / deterministic CPU fake)
# ---------------------------------------------------------------------------


@runtime_checkable
class AsyncCompletion(Protocol):
    """Handle for an in-flight asynchronous copy."""

    def query(self) -> bool: ...

    def wait(self) -> None: ...


@runtime_checkable
class TransferBackend(Protocol):
    """Device transfer seam.

    Production uses pinned staging + non_blocking H2D + cuda events.
    Tests use a hermetic CPU backend with threading-based completions so the
    concurrency machinery is exercised deterministically without CUDA.
    """

    def allocate_staging_slot(self, nbytes: int) -> Any: ...

    def allocate_destination_buffer(self, nbytes: int) -> Any: ...

    def issue_copy(self, src: Any, dst: Any, length: int) -> AsyncCompletion: ...

    def synchronize(self) -> None: ...


# ---------------------------------------------------------------------------
# Ledger sink (bridges to critical_path_ledger at integration time)
# ---------------------------------------------------------------------------


@runtime_checkable
class LedgerEventSink(Protocol):
    def emit(self, event_name: str, **fields: Any) -> None: ...


class InMemoryLedgerSink:
    """Minimal recording sink used by tests and local tooling."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Dict[str, Any]]] = []

    def emit(self, event_name: str, **fields: Any) -> None:
        self.events.append((event_name, dict(fields)))

    def names(self) -> list[str]:
        return [name for name, _ in self.events]


NULL_LEDGER_SINK = InMemoryLedgerSink()


# ---------------------------------------------------------------------------
# Overlap matrix decision types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OverlapRequest:
    label: str
    domains: Tuple[ResourceDomain, ...]


@dataclass(frozen=True)
class OverlapDecision:
    allowed: bool
    reason: str
    request: OverlapRequest


# ---------------------------------------------------------------------------
# Degradation record
# ---------------------------------------------------------------------------


@dataclass
class DegradationRecord:
    reason: DegradedReason
    detail: Dict[str, Any] = field(default_factory=dict)
    fallback_used: bool = False


# ---------------------------------------------------------------------------
# QD telemetry (occupancy-first; peak alone is meaningless)
# ---------------------------------------------------------------------------


@dataclass
class GoldenQDTelemetry:
    # configuration / counts
    configured_qd: int = GOLDEN_QUEUE_DEPTH
    target_qd: int = GOLDEN_QUEUE_DEPTH
    submit_count: int = 0
    completion_count: int = 0
    planned_block_count: int = 0
    bytes_total: int = 0
    bytes_read: int = 0

    # occupancy (time-weighted)
    occupancy_samples: int = 0
    samples_at_target_qd: int = 0
    fraction_time_at_target_qd: float = 0.0
    time_below_qd_ms_by_reason: Dict[str, float] = field(default_factory=dict)
    free_slots_min: int = 0
    completed_waiting_h2d_max_depth: int = 0

    # backpressure
    h2d_backpressure_events: int = 0
    h2d_backpressure_ms_total: float = 0.0

    # source service latency distribution (ms)
    first_completion_ms: Optional[float] = None
    last_completion_ms: Optional[float] = None
    source_latency_p50_ms: Optional[float] = None
    source_latency_p90_ms: Optional[float] = None
    source_latency_p99_ms: Optional[float] = None
    source_latency_max_ms: Optional[float] = None

    # walls and throughput
    source_wall_ms: float = 0.0
    aggregate_gbps: float = 0.0
    steady_state_gbps: float = 0.0

    # host cost
    thread_cpu_ms: float = 0.0
    process_cpu_ms: float = 0.0

    # h2d side
    h2d_host_issue_ms_total: float = 0.0
    h2d_host_issue_ms_max: float = 0.0
    h2d_device_wall_ms: float = 0.0
    h2d_submitted_bytes: int = 0
    h2d_completed_bytes: int = 0

    # staging
    staging_slots: int = 0
    pinned_bytes: int = 0

    # prepare/commit reconciliation (R42)
    commit_read_storage_bytes: int = 0
    commit_cache_served: Optional[bool] = None

    # compat / legacy parity
    observed_max_outstanding: int = 0
    queue_backlog_max: int = 0

    # errors
    per_read_errors: int = 0
    worker_exceptions: int = 0

    status: str = "ok"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "configured_qd": self.configured_qd,
            "target_qd": self.target_qd,
            "submit_count": self.submit_count,
            "completion_count": self.completion_count,
            "planned_block_count": self.planned_block_count,
            "bytes_total": self.bytes_total,
            "bytes_read": self.bytes_read,
            "occupancy_samples": self.occupancy_samples,
            "samples_at_target_qd": self.samples_at_target_qd,
            "fraction_time_at_target_qd": self.fraction_time_at_target_qd,
            "time_below_qd_ms_by_reason": dict(self.time_below_qd_ms_by_reason),
            "free_slots_min": self.free_slots_min,
            "completed_waiting_h2d_max_depth": self.completed_waiting_h2d_max_depth,
            "h2d_backpressure_events": self.h2d_backpressure_events,
            "h2d_backpressure_ms_total": self.h2d_backpressure_ms_total,
            "first_completion_ms": self.first_completion_ms,
            "last_completion_ms": self.last_completion_ms,
            "source_latency_p50_ms": self.source_latency_p50_ms,
            "source_latency_p90_ms": self.source_latency_p90_ms,
            "source_latency_p99_ms": self.source_latency_p99_ms,
            "source_latency_max_ms": self.source_latency_max_ms,
            "source_wall_ms": self.source_wall_ms,
            "aggregate_gbps": self.aggregate_gbps,
            "steady_state_gbps": self.steady_state_gbps,
            "thread_cpu_ms": self.thread_cpu_ms,
            "process_cpu_ms": self.process_cpu_ms,
            "h2d_host_issue_ms_total": self.h2d_host_issue_ms_total,
            "h2d_host_issue_ms_max": self.h2d_host_issue_ms_max,
            "h2d_device_wall_ms": self.h2d_device_wall_ms,
            "h2d_submitted_bytes": self.h2d_submitted_bytes,
            "h2d_completed_bytes": self.h2d_completed_bytes,
            "staging_slots": self.staging_slots,
            "pinned_bytes": self.pinned_bytes,
            "commit_read_storage_bytes": self.commit_read_storage_bytes,
            "commit_cache_served": self.commit_cache_served,
            "observed_max_outstanding": self.observed_max_outstanding,
            "queue_backlog_max": self.queue_backlog_max,
            "per_read_errors": self.per_read_errors,
            "worker_exceptions": self.worker_exceptions,
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# Load result
# ---------------------------------------------------------------------------


@dataclass
class LoadResult:
    role: ModelRole
    ok: bool
    telemetry: GoldenQDTelemetry
    destination: Optional[DestinationPlan] = None
    degradation: Optional[DegradationRecord] = None
    error: Optional[str] = None


__all__ = [
    "EXACT_OUTPUT_SHA",
    "DEFAULT_BLOCK_BYTES",
    "GOLDEN_QUEUE_DEPTH",
    "ModelRole",
    "ResourceDomain",
    "LifecyclePhase",
    "GoldenEvent",
    "RuntimeStatus",
    "DegradedReason",
    "DestinationKind",
    "OwnershipState",
    "JoinDecision",
    "QDDropReason",
    "GoldenError",
    "GoldenQDFailure",
    "SourceReadError",
    "ShortReadError",
    "WorkerCrashedError",
    "CoverageReconciliationError",
    "PrepareCommitIdentityError",
    "BindError",
    "ForbiddenOverlapError",
    "QuiescenceViolationError",
    "ImmutableStateAbsentError",
    "TensorMapEntry",
    "SafetensorsLayout",
    "CopySegment",
    "BlockPlan",
    "QDRangePlan",
    "RoleManifest",
    "DestinationPlan",
    "PreparedSource",
    "ConditioningContract",
    "DEFAULT_CONDITIONING_CONTRACT",
    "AsyncCompletion",
    "TransferBackend",
    "LedgerEventSink",
    "InMemoryLedgerSink",
    "NULL_LEDGER_SINK",
    "OverlapRequest",
    "OverlapDecision",
    "DegradationRecord",
    "GoldenQDTelemetry",
    "LoadResult",
]
