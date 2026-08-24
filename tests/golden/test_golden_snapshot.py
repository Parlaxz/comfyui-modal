"""Golden snapshot composition tests: static-only, quiescent, deterministic."""

from __future__ import annotations

import pytest

from comfymodal_runtime.golden.contracts import (
    DestinationKind,
    GoldenError,
    ImmutableStateAbsentError,
    ModelRole,
    QuiescenceViolationError,
)
from comfymodal_runtime.golden.snapshot import (
    FORBIDDEN_SNAPSHOT_ENTRIES,
    REQUIRED_STATIC_ENTRIES,
    SnapshotAccounting,
    assert_quiescent,
    build_snapshot_manifest,
    immutable_metadata_present,
    validate_exclusions,
)

from conftest import build_manifest


def test_manifest_deterministic_sha(small_clip_file, vae_file):
    manifests = {
        ModelRole.CLIP: build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER),
        ModelRole.VAE: build_manifest(vae_file, ModelRole.VAE, 1048576, DestinationKind.CONTIGUOUS_GPU_BUFFER),
    }
    extra = {"workflow_topology_reachability": {"nodes": 7}, "model_identities": {"clip": "abc", "vae": "def"}}
    a = build_snapshot_manifest(manifests, extra_static=extra)
    b = build_snapshot_manifest(manifests, extra_static=dict(extra))
    assert a == b
    assert a["manifest_sha256"] == b["manifest_sha256"]
    c = build_snapshot_manifest(manifests, extra_static={"workflow_topology_reachability": {"nodes": 8}})
    assert c["manifest_sha256"] != a["manifest_sha256"]


def test_required_entries_present_and_forbidden_absent(small_clip_file):
    manifests = {ModelRole.CLIP: build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)}
    doc = build_snapshot_manifest(manifests)
    for entry in REQUIRED_STATIC_ENTRIES:
        assert entry in doc
    assert doc["forbidden_absent"] == {name: True for name in FORBIDDEN_SNAPSHOT_ENTRIES}
    assert set(doc["model_manifests"]) == {"clip", "unet", "vae"}


def test_quiescence_clean_report():
    report = assert_quiescent()
    assert report.quiescent and report.violations == ()


def test_quiescence_violations_listed_together():
    with pytest.raises(QuiescenceViolationError) as excinfo:
        assert_quiescent(
            loaders_active=True,
            unresolved_cuda_events=3,
            request_state_present=True,
            persistence_queue_present=True,
            speculative_future_present=True,
            temporary_owner_present=True,
            live_pinned_buffer_count=4,
        )
    msg = str(excinfo.value)
    for fragment in ["active_source_readers", "unresolved_cuda_events=3", "request_state",
                     "persistence_queue", "speculative_future", "temporary_owner", "live_pinned_transfer_buffers=4"]:
        assert fragment in msg


def test_weight_value_exclusion_enforced():
    accounting = SnapshotAccounting()
    validate_exclusions(accounting)
    accounting.value_bytes_by_role[ModelRole.VAE] = 12345
    with pytest.raises(GoldenError, match="vae"):
        validate_exclusions(accounting)


def test_immutable_metadata_absent_raises_with_names():
    immutable_metadata_present({"safetensors_headers": True, "tensor_maps": True})
    with pytest.raises(ImmutableStateAbsentError) as excinfo:
        immutable_metadata_present({"safetensors_headers": False, "tensor_maps": True, "qd_range_plans": False})
    msg = str(excinfo.value)
    assert "safetensors_headers" in msg and "qd_range_plans" in msg
