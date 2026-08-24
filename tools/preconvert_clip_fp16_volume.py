"""R44I3 ARM B: ONE-TIME BF16->FP16 preconversion of a CLIP checkpoint on the
Modal models volume.

Run OFF the request critical path:

    modal run tools/preconvert_clip_fp16_volume.py --name qwen_3_4b.safetensors

Writes ``<text_encoders>/<stem>.fp16.safetensors`` ATOMICALLY (tmp + os.replace)
next to the source, preserving every key/shape/metadata and converting only
dtype (BF16 -> FP16).  A ``.fp16.manifest.json`` beside it records tensor
count / bytes / source size for provenance.  Re-running skips when the twin
already exists and matches the manifest (idempotent).
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile

import modal

MODELS_VOLUME_NAME = os.environ.get("COMFYMODAL_MODELS_VOLUME", "comfyui-models")
MODELS_PATH = "/root/models"

app = modal.App("comfymodal-clip-fp16-preconvert")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("safetensors", "numpy", "torch==2.8.0")
)

volume = modal.Volume.from_name(MODELS_VOLUME_NAME, create_if_missing=True)


@app.function(image=image, volumes={MODELS_PATH: volume}, timeout=3600)
def preconvert(name: str, force: bool = False) -> dict:
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    src = os.path.join(MODELS_PATH, "text_encoders", name)
    stem, ext = os.path.splitext(src)
    dst = f"{stem}.fp16{ext}"
    manifest_path = f"{dst}.manifest.json"

    if os.path.isfile(dst) and os.path.isfile(manifest_path) and not force:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            prior = json.load(handle)
        if int(prior.get("tensor_count", -1)) > 0 and os.path.getsize(dst) == int(
            prior.get("dst_bytes", -1)
        ):
            return {"status": "already_present", "dst": dst, **prior}

    tensors: dict[str, "torch.Tensor"] = {}
    src_bytes = 0
    with safe_open(src, framework="pt", device="cpu") as handle:
        metadata = handle.metadata() or {}
        for key in handle.keys():
            tensor = handle.get_tensor(key)
            src_bytes += tensor.numel() * tensor.element_size()
            if tensor.dtype in (torch.bfloat16, torch.float32):
                tensors[key] = tensor.to(torch.float16)
            else:
                tensors[key] = tensor.clone()

    # Validate BEFORE publishing: every converted weight must be FP16.
    for key, tensor in tensors.items():
        if tensor.is_floating_point() and tensor.dtype != torch.float16:
            raise RuntimeError(f"non-fp16 weight survived: {key}:{tensor.dtype}")

    dir_name = os.path.dirname(dst)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp.safetensors")
    os.close(fd)
    try:
        save_file(tensors, tmp_path, metadata=metadata)
        os.replace(tmp_path, dst)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    dst_bytes = os.path.getsize(dst)
    info = {
        "source": os.path.basename(src),
        "source_bytes": src_bytes,
        "dst": os.path.basename(dst),
        "dst_bytes": dst_bytes,
        "tensor_count": len(tensors),
        "conversion": "BF16->FP16",
        "metadata_preserved": bool(metadata),
    }
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(info, handle, indent=1, sort_keys=True)
    volume.commit()
    return {"status": "written", **info}


@app.local_entrypoint()
def main(name: str = "qwen_3_4b.safetensors", force: bool = False):
    result = preconvert.remote(name=name, force=force)
    print(json.dumps(result, indent=1))
