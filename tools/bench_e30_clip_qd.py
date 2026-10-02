"""E30 local synthetic benchmark: QD scaling + GPU pipeline on this host.

Mechanics validation ONLY — a local NVMe/Windows result is NOT a Modal
Volume throughput conclusion (the remote gate will measure that).  Bounded:
synthetic file ~256 MiB, QD {1,2,4,8} x 32 MiB blocks, plus one GPU pass.

Usage: python tools/bench_e30_clip_qd.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["COMFYMODAL_V2_CLIP_QD_READER"] = "1"

import torch  # noqa: E402
import safetensors.torch  # noqa: E402

from comfymodal_runtime import clip_qd_reader as qr  # noqa: E402


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="e30_bench_")
    path = str(Path(tmp) / "synth_256m.safetensors")
    print(f"[e30] building synthetic file at {path} ...", flush=True)
    tensors = {}
    dim = 4096
    for i in range(16):
        tensors[f"blk{i}.weight"] = torch.randn(dim, dim, dtype=torch.bfloat16)
        tensors[f"blk{i}.bias"] = torch.randn(dim, dtype=torch.bfloat16)
    safetensors.torch.save_file(tensors, path)
    size = os.path.getsize(path)
    print(f"[e30] file bytes = {size} ({size / (1024**3):.3f} GiB)", flush=True)
    rows = []
    for qd in (1, 2, 4, 8):
        os.environ["COMFYMODAL_V2_CLIP_QD_QD"] = str(qd)
        os.environ["COMFYMODAL_V2_CLIP_QD_BLOCK_MIB"] = "32"
        r = qr.read_file_qd(path)
        st = r["stats"]
        rows.append((qd, st["total_source_wall_ms"], st["aggregate_gbps"],
                     st["observed_max_outstanding"], st["submit_count"],
                     st["completion_count"], st["per_read_errors"]))
        print(f"[e30] QD{qd}: wall={st['total_source_wall_ms']:.1f} ms "
              f"gbps={st['aggregate_gbps']:.2f} obs_max={st['observed_max_outstanding']} "
              f"submit={st['submit_count']} done={st['completion_count']} "
              f"errors={st['per_read_errors']}", flush=True)
    print("\n[e30] QD scaling table (local mechanics only):", flush=True)
    print("  QD | wall_ms | GB/s | obs_max | submit | done | errors", flush=True)
    for row in rows:
        print("  %2d | %7.1f | %5.2f | %7d | %6d | %4d | %d" % row, flush=True)
    if torch.cuda.is_available():
        os.environ["COMFYMODAL_V2_CLIP_QD_QD"] = "4"
        os.environ["COMFYMODAL_V2_CLIP_QD_BLOCK_MIB"] = "32"
        r = qr.read_file_qd_gpu(path)
        st = r["stats"]
        print(f"\n[e30] GPU pipeline (QD4/32MiB): wall={st['total_source_wall_ms']:.1f} ms "
              f"h2d_dev={st['h2d']['h2d_device_ms']} ms "
              f"obs_max={st['observed_max_outstanding']} "
              f"cuda_delta={st['memory']['cuda_alloc_delta_bytes']} bytes "
              f"tensors={len(r['sd'])}", flush=True)
        r["owner"].close()
    print("\n[e30] done.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
