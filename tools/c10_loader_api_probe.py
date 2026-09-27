"""C10 external concurrent loader probe.

Standalone benchmark adapter contract for the exact ZImage model file:
  /root/models/diffusion_models/z_image_turbo_bf16.safetensors
  (12,309,817,472 bytes, 453 tensors, BF16, single GPU)

Owned by C9 (remote benchmarking). This file is NOT wired into ComfyUI.

Adapter contract (one class per loader, all returning the same shape):

  loader_name                 str
  setup()                     optional warmup/one-time init
  load_exact_file_to_cpu_or_gpu() -> (tensors: dict[str, torch.Tensor], wall_ns: int)
  tensor_hash_check()         sha256 over tensor bytes in key order
  cleanup()                   release buffers/threads

Every adapter reports: wall_ns, bytes_read (sum of tensor nbytes), tensor_count,
tensor_hash. Validity = bytes_read equals expected data size and hash matches the
baseline adapter (mmap, mirroring comfy.utils.load_torch_file).

Usage:
  python tools/c10_loader_api_probe.py --loader all --file <path> --device cuda:0
  python tools/c10_loader_api_probe.py --loader runai --device cuda:0 --repeats 3 --out-json runai.json

Cold semantics for C9: fresh container, then --drop-caches-if-root to clear page
cache before each repeat. Warm pass = second repeat in same process.
"""

import argparse
import hashlib
import json
import os
import stat
import sys
import time

DEFAULT_FILE = "/root/models/diffusion_models/z_image_turbo_bf16.safetensors"
DEFAULT_DEVICE = "cuda:0"
PREADV_CHUNK = 32 * 1024 * 1024


class ProbeResult:
    def __init__(self, loader_name, ok, wall_ns=0, bytes_read=0, tensor_count=0,
                 tensor_hash=None, error=None, meta=None):
        self.loader_name = loader_name
        self.ok = ok
        self.wall_ns = wall_ns
        self.bytes_read = bytes_read
        self.tensor_count = tensor_count
        self.tensor_hash = tensor_hash
        self.error = error
        self.meta = meta or {}

    def to_dict(self):
        return {
            "loader": self.loader_name,
            "ok": self.ok,
            "wall_ms": round(self.wall_ns / 1e6, 3) if self.wall_ns else None,
            "decimal_GBps": round(self.bytes_read / self.wall_ns, 3) if self.wall_ns else None,
            "bytes_read": self.bytes_read,
            "tensor_count": self.tensor_count,
            "tensor_hash": self.tensor_hash,
            "error": self.error,
            "meta": self.meta,
        }


def _expected_data_bytes(path):
    with open(path, "rb") as f:
        header_len = int.from_bytes(f.read(8), "little")
        header = json.loads(f.read(header_len))
    total = 0
    for v in header.values():
        if isinstance(v, dict) and "data_offsets" in v:
            total += v["data_offsets"][1] - v["data_offsets"][0]
    return total, len([k for k in header if isinstance(header[k], dict) and "data_offsets" in header[k]])


def _hash_tensors(tensors):
    h = hashlib.sha256()
    for k in sorted(tensors):
        t = tensors[k]
        h.update(t.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes())
    return h.hexdigest()


class BaselineMmapAdapter:
    """Mirror of comfy.utils.load_torch_file (production default): safe_open +
    per-key get_tensor, mmap-backed views. Single-threaded, page-fault driven."""

    loader_name = "baseline_mmap"

    def __init__(self, path, device):
        self.path = path
        self.device = device

    def setup(self):
        import safetensors.torch as st
        self._st = st

    def load_exact_file_to_cpu_or_gpu(self):
        tensors = {}
        with self._st.safe_open(self.path, framework="pt", device="cpu") as f:
            for k in f.keys():
                tensors[k] = f.get_tensor(k)
        return tensors

    def cleanup(self):
        pass


class BaselinePreadvAdapter:
    """Existing in-tree mechanism (unet_meta_direct single-thread preadv into
    pageable buffers), reimplemented standalone as the floor reference."""

    loader_name = "baseline_preadv"

    def __init__(self, path, device):
        self.path = path
        self.device = device

    def setup(self):
        import torch

    def load_exact_file_to_cpu_or_gpu(self):
        import torch
        import safetensors.torch as st
        size = os.path.getsize(self.path)
        fd = os.open(self.path, os.O_RDONLY)
        try:
            header_len = int.from_bytes(os.pread(fd, 8, 0), "little")
            header = json.loads(os.pread(fd, header_len, 8))
            tensors = {}
            for k, v in header.items():
                if not (isinstance(v, dict) and "data_offsets" in v):
                    continue
                start, end = v["data_offsets"]
                nbytes = end - start
                buf = bytearray(nbytes)
                off = start + 8 + header_len
                got = 0
                while got < nbytes:
                    n = os.preadv(fd, [memoryview(buf)[got:got + PREADV_CHUNK]], off + got)
                    if n == 0:
                        raise IOError("short read")
                    got += n
                dt = st._get_dtype(v["dtype"]) if hasattr(st, "_get_dtype") else _dtype_map(v["dtype"])
                tensors[k] = torch.frombuffer(buf, dtype=dt).reshape(v["shape"]).clone()
            return tensors
        finally:
            os.close(fd)

    def cleanup(self):
        pass


def _dtype_map(name):
    import torch
    return {
        "BF16": torch.bfloat16, "F16": torch.float16, "F32": torch.float32,
        "F64": torch.float64, "I8": torch.int8, "I16": torch.int16,
        "I32": torch.int32, "I64": torch.int64, "U8": torch.uint8,
        "U16": torch.uint16, "U32": torch.uint32, "U64": torch.uint64,
        "BOOL": torch.bool,
    }[name]


class RunaiAdapter:
    """runai-model-streamer 0.16.1: C++ pool of RUNAI_STREAMER_CONCURRENCY (16)
    threads, each with own fd, reading byte-range slices of the SAME file (2 MiB
    buffered read chunks) into a host staging buffer; get_tensors() yields
    zero-copy views; device="cuda:0" triggers .to() H2D per tensor, overlapping
    with continued reads. No GDS anywhere in the codebase."""

    loader_name = "runai"

    def __init__(self, path, device):
        self.path = path
        self.device = device

    def setup(self):
        from runai_model_streamer import SafetensorsStreamer
        self._cls = SafetensorsStreamer

    def load_exact_file_to_cpu_or_gpu(self):
        tensors = {}
        with self._cls() as streamer:
            streamer.stream_file(self.path, device=self.device if self.device != "cpu" else "cpu")
            for name, tensor in streamer.get_tensors():
                tensors[name] = tensor.clone()
        return tensors

    def cleanup(self):
        pass


class FastSafetensorsAdapter:
    """fastsafetensors 0.3.3 (Apache-2.0): nogds copier = N concurrent pread(2)
    on ONE shared fd into a pinned bounce-buffer pool (cudaHostAlloc,
    bbuf_size_kb * max_threads), then cudaMemcpy H2D per block.
    CRITICAL TUNING: max_copy_block_size defaults to 16 GiB -> a 12.31 GB file
    gets exactly ONE reader thread. Pass --max-copy-block-size 1GiB to get
    ~12 concurrent readers (capped by max_threads)."""

    loader_name = "fastsafetensors"

    def __init__(self, path, device, max_copy_block_size=1 << 30, max_threads=16):
        self.path = path
        self.device = device
        self.max_copy_block_size = max_copy_block_size
        self.max_threads = max_threads

    def setup(self):
        from fastsafetensors import fastsafe_open
        self._open = fastsafe_open

    def load_exact_file_to_cpu_or_gpu(self):
        tensors = {}
        with self._open(filenames=[self.path], device=self.device, nogds=True,
                        max_copy_block_size=self.max_copy_block_size) as f:
            for k in f.get_keys():
                tensors[k] = f.get_tensor(k).clone().detach()
        return tensors

    def cleanup(self):
        pass


class InstantTensorAdapter:
    """instanttensor 0.1.9 (Alpha): io_uring (O_DIRECT, default, kernel>=5.15) or
    libaio fallback; io_depth (default 512) chunks of chunk_size (8 MiB) in flight
    on a private cudaStream, cudaMemcpyAsync H2D, cudaEvent pipeline; direct to
    CUDA only. Staging defaults ~4 GiB VRAM + ~4 GiB pinned host; tune via
    INSTANTTENSOR_IO_DEPTH. GDS (CUFILE backend) strictly optional."""

    loader_name = "instanttensor"

    def __init__(self, path, device):
        self.path = path
        self.device = device

    def setup(self):
        from instanttensor import safe_open
        self._open = safe_open

    def load_exact_file_to_cpu_or_gpu(self):
        tensors = {}
        dev = 0 if self.device.startswith("cuda") else self.device
        with self._open(self.path, framework="pt", device=dev, copy=True) as f:
            for name, tensor in f.tensors():
                tensors[name] = tensor
        return tensors

    def cleanup(self):
        pass


class Safetensors08PreadAdapter:
    """safetensors>=0.8.0 official backend="pread": sequential per-tensor
    pread(2) into fresh host buffers (no parallelism on Linux/CUDA; parallel
    pread is Apple-MPS-only). Included as a control, not a candidate."""

    loader_name = "safetensors08_pread"

    def __init__(self, path, device):
        self.path = path
        self.device = device

    def setup(self):
        import safetensors
        if tuple(int(x) for x in safetensors.__version__.split(".")) < (0, 8, 0):
            raise RuntimeError(f"safetensors {safetensors.__version__} < 0.8.0; backend='pread' unavailable")
        import safetensors.torch as st
        self._st = st

    def load_exact_file_to_cpu_or_gpu(self):
        tensors = {}
        with self._st.safe_open(self.path, framework="pt", device="cpu", backend="pread") as f:
            for k in f.keys():
                tensors[k] = f.get_tensor(k)
        return tensors

    def cleanup(self):
        pass


ADAPTERS = {
    "baseline_mmap": BaselineMmapAdapter,
    "baseline_preadv": BaselinePreadvAdapter,
    "runai": RunaiAdapter,
    "fastsafetensors": FastSafetensorsAdapter,
    "instanttensor": InstantTensorAdapter,
    "safetensors08_pread": Safetensors08PreadAdapter,
}


def run_loader(name, path, device, max_copy_block_size, max_threads, drop_caches):
    if drop_caches and hasattr(os, "geteuid") and os.geteuid() == 0:
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("3\n")
    cls = ADAPTERS[name]
    kw = {}
    if name == "fastsafetensors":
        kw = {"max_copy_block_size": max_copy_block_size, "max_threads": max_threads}
    try:
        adapter = cls(path, device, **kw)
    except Exception as e:
        return ProbeResult(name, False, error=f"import/init failed: {e!r}").to_dict()
    try:
        adapter.setup()
        expected, expected_n = _expected_data_bytes(path)
        t0 = time.monotonic_ns()
        tensors = adapter.load_exact_file_to_cpu_or_gpu()
        wall = time.monotonic_ns() - t0
        bytes_read = sum(t.numel() * t.element_size() for t in tensors.values())
        h = _hash_tensors(tensors)
        ok = bytes_read == expected and len(tensors) == expected_n
        adapter.cleanup()
        return ProbeResult(name, ok, wall_ns=wall, bytes_read=bytes_read,
                           tensor_count=len(tensors), tensor_hash=h,
                           meta={"expected_bytes": expected,
                                 "expected_tensors": expected_n}).to_dict()
    except Exception as e:
        try:
            adapter.cleanup()
        except Exception:
            pass
        return ProbeResult(name, False, error=f"{type(e).__name__}: {e}").to_dict()


def main():
    p = argparse.ArgumentParser(description="C10 external loader probe")
    p.add_argument("--loader", choices=sorted(ADAPTERS) + ["all"], default="all")
    p.add_argument("--file", default=DEFAULT_FILE)
    p.add_argument("--device", default=DEFAULT_DEVICE)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--max-copy-block-size", type=int, default=1 << 30,
                   help="fastsafetensors only; MUST be < file size (default 16 GiB) to parallelize a single file")
    p.add_argument("--max-threads", type=int, default=16)
    p.add_argument("--drop-caches-if-root", action="store_true")
    p.add_argument("--out-json")
    args = p.parse_args()

    names = sorted(ADAPTERS) if args.loader == "all" else [args.loader]
    results = []
    for name in names:
        for i in range(args.repeats):
            r = run_loader(name, args.file, args.device, args.max_copy_block_size,
                           args.max_threads, args.drop_caches_if_root)
            r["repeat"] = i + 1
            results.append(r)
            print(json.dumps(r))

    baseline_hash = next((r["tensor_hash"] for r in results
                          if r["loader"] == "baseline_mmap" and r["ok"]), None)
    if baseline_hash:
        for r in results:
            if r["ok"] and r["loader"] != "baseline_mmap":
                r["hash_matches_baseline"] = r["tensor_hash"] == baseline_hash
                r["ok"] = r["ok"] and r["hash_matches_baseline"]
                print(json.dumps(r))

    if args.out_json:
        with open(args.out_json, "w") as f:
            json.dump({"file": args.file, "device": args.device,
                       "results": results}, f, indent=2)


if __name__ == "__main__":
    import torch  # noqa: E402  (required by _hash_tensors; loaders import lazily)
    main()
