"""R41 Golden deterministic QD4 model pipeline.

ONE generic Golden QD4 loader engine for CLIP/UNET/VAE with decoupled
source/H2D planes, bounded pinned staging, occupancy-first telemetry, an
event-driven resource scheduler with an explicit overlap matrix, strong
ownership with join/adopt demand semantics, static-metadata-only snapshot
composition, and fail-closed fallback classification.

Public surface (interface freeze v1 — see contracts.py docstring for E40
reconciliation notes).
"""

from .contracts import (  # noqa: F401
    DEFAULT_BLOCK_BYTES,
    DEFAULT_CONDITIONING_CONTRACT,
    EXACT_OUTPUT_SHA,
    GOLDEN_QUEUE_DEPTH,
    BindError,
    BlockPlan,
    ConditioningContract,
    CopySegment,
    CoverageReconciliationError,
    DegradationRecord,
    DegradedReason,
    DestinationKind,
    DestinationPlan,
    ForbiddenOverlapError,
    GoldenError,
    GoldenEvent,
    GoldenQDFailure,
    GoldenQDTelemetry,
    ImmutableStateAbsentError,
    InMemoryLedgerSink,
    JoinDecision,
    LifecyclePhase,
    LoadResult,
    ModelRole,
    NULL_LEDGER_SINK,
    OwnershipState,
    QDDropReason,
    QDRangePlan,
    QuiescenceViolationError,
    ResourceDomain,
    RoleManifest,
    RuntimeStatus,
    SafetensorsLayout,
    ShortReadError,
    SourceReadError,
    TensorMapEntry,
    WorkerCrashedError,
)
from .model_owner import (  # noqa: F401
    GoldenModelOwner,
    GoldenOwnerRegistry,
    OwnerHandle,
)
from .qd_engine import (  # noqa: F401
    CpuCopyBackend,
    CudaTransferBackend,
    GoldenQD4Loader,
    QD4EngineConfig,
    parse_safetensors_header,
)
from .resource_scheduler import (  # noqa: F401
    ACT_CLIP_FORWARD,
    ACT_CLIP_GPU_CRITICAL,
    ACT_CLIP_QD_H2D,
    ACT_CLIP_QD_SOURCE,
    ACT_SAMPLING,
    ACT_UNET_BULK_SOURCE,
    ACT_UNET_GPU_COMMIT,
    ACT_UNET_H2D,
    ACT_UNET_METADATA_PREP,
    ACT_VAE_GPU_MUTATION,
    ACT_VAE_QD,
    GoldenResourceScheduler,
    OverlapMatrix,
)
from .snapshot import (  # noqa: F401
    FORBIDDEN_SNAPSHOT_ENTRIES,
    REQUIRED_STATIC_ENTRIES,
    SnapshotAccounting,
    assert_quiescent,
    build_snapshot_manifest,
    immutable_metadata_present,
    validate_exclusions,
)
from .pipeline import (  # noqa: F401
    GOLDEN_ROLE_LOADER_POLICY,
    GoldenPipeline,
    RoleBinding,
    assert_fallback_never_nominal,
    classify_hard_failure,
    final_status,
)

__all__ = [
    "EXACT_OUTPUT_SHA",
    "DEFAULT_BLOCK_BYTES",
    "GOLDEN_QUEUE_DEPTH",
    "GoldenQD4Loader",
    "QD4EngineConfig",
    "CpuCopyBackend",
    "CudaTransferBackend",
    "parse_safetensors_header",
    "GoldenModelOwner",
    "GoldenOwnerRegistry",
    "OwnerHandle",
    "GoldenResourceScheduler",
    "OverlapMatrix",
    "GoldenPipeline",
    "RoleBinding",
    "GOLDEN_ROLE_LOADER_POLICY",
    "classify_hard_failure",
    "final_status",
    "assert_fallback_never_nominal",
    "assert_quiescent",
    "build_snapshot_manifest",
    "validate_exclusions",
    "immutable_metadata_present",
    "SnapshotAccounting",
    "REQUIRED_STATIC_ENTRIES",
    "FORBIDDEN_SNAPSHOT_ENTRIES",
]
