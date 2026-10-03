from __future__ import annotations

import hashlib
import json

import pytest

from comfymodal_runtime.triton_cache import (
    cache_compatible,
    cache_identity,
    hydrate_cache,
    manifest_path,
    read_manifest,
    write_manifest,
)


pytestmark = pytest.mark.fast_unit


SPECIALIZATION = {
    "B": 1,
    "M": 64,
    "N": 281,
    "dtype": "float32",
    "BLOCK_M": 64,
    "BLOCK_N": 64,
}


def _identity(**overrides):
    values = {
        "triton_version": "3.8.0",
        "torch_version": "2.14.0+cu130",
        "cuda_version": "13.0",
        "target_arch": "sm90",
        "specialization": SPECIALIZATION,
    }
    values.update(overrides)
    return cache_identity(**values)


def test_cache_identity_invalidates_version_cuda_arch_and_specialization():
    identity = _identity()
    assert cache_compatible({"identity": identity}, identity)
    for field, value in (
        ("triton_version", "3.9.0"),
        ("torch_version", "2.14.0+cu131"),
        ("cuda_version", "13.1"),
        ("target_arch", "sm80"),
    ):
        changed = dict(identity)
        changed[field] = value
        assert not cache_compatible({"identity": identity}, changed)
    changed = dict(identity)
    changed["specialization"] = {**SPECIALIZATION, "N": 280}
    assert not cache_compatible({"identity": identity}, changed)


def test_stale_triton_version_fails_closed_and_hydration_does_not_copy(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "kernel.cubin").write_bytes(b"genuine artifact")
    identity = _identity()
    write_manifest(source, {"identity": identity, "files": []})
    stale = {**identity, "triton_version": "3.7.0"}
    result = hydrate_cache(source=source, target=target, expected_identity=stale)
    assert result["status"] == "stale_or_missing"
    assert not target.exists()


def test_wrong_cuda_or_arch_cannot_silently_reuse_artifact(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    identity = _identity()
    write_manifest(source, {"identity": identity})
    assert not cache_compatible(
        read_manifest(source),
        {**identity, "cuda_version": "12.8"},
    )
    assert not cache_compatible(
        read_manifest(source),
        {**identity, "target_arch": "sm90a"},
    )


def test_missing_cache_falls_back_without_mutating_target(tmp_path):
    result = hydrate_cache(
        source=tmp_path / "missing",
        target=tmp_path / "target",
        expected_identity=_identity(),
    )
    assert result["status"] == "stale_or_missing"
    assert not (tmp_path / "target").exists()


def test_manifest_round_trip_preserves_artifact_bytes_and_semantics(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    payload = b"kernel bytes are opaque to this layer"
    (source / "kernel.bin").write_bytes(payload)
    identity = _identity()
    write_manifest(source, {"identity": identity, "files": [{"path": "kernel.bin"}]})
    result = hydrate_cache(source=source, target=target, expected_identity=identity)
    assert result["status"] == "hydrated"
    assert (target / "kernel.bin").read_bytes() == payload
    assert hashlib.sha256((target / "kernel.bin").read_bytes()).hexdigest() == hashlib.sha256(payload).hexdigest()
    assert manifest_path(source).is_file()
