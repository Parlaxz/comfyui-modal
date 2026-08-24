"""Shared fixtures for Golden pipeline deterministic tests."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import torch  # noqa: E402

from comfymodal_runtime.golden.contracts import (  # noqa: E402
    DestinationKind,
    DestinationPlan,
    ModelRole,
    QDRangePlan,
    RoleManifest,
)
from comfymodal_runtime.golden.qd_engine import parse_safetensors_header  # noqa: E402


def write_safetensors(path: Path, tensors_spec, fill_mod: int = 251):
    """Write a real safetensors-format file. tensors_spec: list[(name, dtype, shape)]."""
    elem_sizes = {"F32": 4, "F16": 2, "BF16": 2, "I64": 8, "U8": 1}
    header = {}
    offset = 0
    payloads = []
    for name, dtype, shape in tensors_spec:
        nbytes = elem_sizes[dtype]
        for dim in shape:
            nbytes *= dim
        header[name] = {"dtype": dtype, "shape": list(shape), "data_offsets": [offset, offset + nbytes]}
        payloads.append(bytes((i % fill_mod) for i in range(nbytes)))
        offset += nbytes
    header_bytes = json.dumps(header).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(struct.pack("<Q", len(header_bytes)))
        fh.write(header_bytes)
        for payload in payloads:
            fh.write(payload)
    return path


def expected_data_bytes(path: Path) -> bytes:
    with open(path, "rb") as fh:
        header_len = struct.unpack("<Q", fh.read(8))[0]
        fh.seek(8 + header_len)
        return fh.read()


def build_manifest(path: Path, role: ModelRole, block_bytes: int, kind: DestinationKind) -> RoleManifest:
    layout = parse_safetensors_header(str(path))
    mode = "per_tensor" if kind == DestinationKind.PARAMETER_COPY_TARGET else "contiguous"
    plan = QDRangePlan.build(layout, block_bytes, buffer_mode=mode)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return RoleManifest(
        role=role,
        model_path=str(path),
        file_sha256=digest,
        layout=layout,
        identity_hash=digest[:32],
        destination_kind=kind,
        qd_range_plan=plan,
    )


def contiguous_destination(manifest: RoleManifest) -> DestinationPlan:
    total = manifest.qd_range_plan.total_bytes
    return DestinationPlan(
        kind=DestinationKind.CONTIGUOUS_GPU_BUFFER,
        buffers=[torch.empty(total, dtype=torch.uint8)],
        buffer_bytes=[total],
    )


def parameter_destination(manifest: RoleManifest) -> DestinationPlan:
    buffers = []
    sizes = []
    for entry in sorted(manifest.layout.tensor_map, key=lambda t: t.abs_start):
        nbytes = entry.abs_end - entry.abs_start
        buffers.append(torch.empty(nbytes, dtype=torch.uint8))
        sizes.append(nbytes)
    return DestinationPlan(kind=DestinationKind.PARAMETER_COPY_TARGET, buffers=buffers, buffer_bytes=sizes)


@pytest.fixture()
def small_clip_file(tmp_path: Path) -> Path:
    return write_safetensors(tmp_path / "clip_like.safetensors", [("w0", "F32", (64, 64)), ("w1", "F32", (32, 128))])


@pytest.fixture()
def unet_file(tmp_path: Path) -> Path:
    return write_safetensors(
        tmp_path / "unet_like.safetensors",
        [("blk0.w", "F32", (16, 512)), ("blk0.b", "F32", (512,)), ("blk1.w", "F32", (512, 256)), ("norm.g", "F32", (256,))],
    )


@pytest.fixture()
def vae_file(tmp_path: Path) -> Path:
    return write_safetensors(tmp_path / "vae_like.safetensors", [("dec.conv.w", "F32", (8, 8))])
