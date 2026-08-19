# V2 Batch E15 External Loader Feasibility

Date: 2026-08-16
Status: complete as a source and local-capability spike
Scope: external loader feasibility only; no production loader wiring

## Final Decision

InstantTensor is the strongest conditional external candidate for a future
shadow experiment. It has a generic multi-file SafeTensors API, CUDA output,
bounded internal staging, and no model-family code. Its important risks are
Linux-only installation, CUDA-only output, strict SafeTensors layout checks,
and direct-I/O behavior on mounted filesystems. The target mount behavior was
not tested because E15 forbids Modal runs.

Run:ai Model Streamer is the safest reusable library seam. It is standalone,
accepts local paths, streams ordinary CPU PyTorch tensors, and has an explicit
CPU staging limit. It leaves the GPU copy and tensor lifetime to the caller,
so it is less likely than InstantTensor to be a direct replacement for the
current CUDA loader but is a good bounded-source-reader candidate.

ModelExpress and NVIDIA Dynamo are not suitable as independent loaders for
ComfyUI. ModelExpress exposes its useful load strategies through vLLM,
SGLang, TensorRT-LLM, or Dynamo loader hooks. Dynamo is the serving runtime,
not a SafeTensors path-to-tensor library.

## Required Result

```text
E15_COMPLETE=YES

INSTANTTENSOR_INSTALLABLE=NO on the current Windows host; target Linux image is YES by PyPI metadata, not locally install-tested
INSTANTTENSOR_POSIX_WITHOUT_GDS=YES, with O_DIRECT/filesystem caveat
INSTANTTENSOR_GENERIC_COMFY_COMPATIBLE=YES at source level, target integration unverified
INSTANTTENSOR_PROTOTYPE_CREATED=NO

MODELSTREAMER_REUSABLE_AS_LIBRARY=YES
MODELSTREAMER_RUNTIME_MIGRATION_REQUIRED=NO

SAFETENSORS_PREAD_AVAILABLE=NO
SAFETENSORS_PREAD_API=NONE in the installed 0.5.3 public Python API

FASTSAFETENSORS_LOW_LEVEL_REUSE_AVAILABLE=YES

BEST_EXTERNAL_CANDIDATE=InstantTensor, conditional on target mount/layout validation
SECOND_BEST=Run:ai Model Streamer

RECOMMEND_EXTERNAL_BACKEND_NOW=NO

LOCAL_TESTS=PASS: E15 suite and installed fastsafetensors CPU smoke; no remote test
PYCOMPILE=PASS: E15 test module

MODAL_RUNS=0
COMMIT=none

READY_FOR_INTEGRATION=NO: candidate evidence is ready; production integration remains gated on E11 outcome and target-image/mount validation
```

`INSTANTTENSOR_INSTALLABLE` is intentionally host-qualified. The current
checkout runs on Windows, while the package publishes Linux wheels and its
source uses Linux I/O facilities. The target Modal image is Linux x86_64 with
Python 3.11, so package metadata makes installation plausible there, but no
remote installation was performed.

## Environment Compatibility

### Repository target

The repository target is defined in `comfyapp.py`:

| Item | Repository configuration | Compatibility implication |
|---|---|---|
| OS/architecture | Modal image from `nvidia/cuda:13.0.0-devel-ubuntu24.04` | Linux x86_64 is suitable for InstantTensor and Run:ai Model Streamer wheels |
| Python | `add_python="3.11"` | Satisfies InstantTensor `>=3.9`, ModelExpress `>=3.10`, and Dynamo `>=3.10` |
| PyTorch | `torch torchvision torchaudio` force-installed from the CUDA 13.0 index without a version pin | Must be checked against InstantTensor's `torch>=2.8.0`; the exact deployed Torch version is not reproducible from this source alone |
| CUDA | CUDA 13.0 image and CUDA 13.0 PyTorch index | Runtime is suitable in principle; exact Torch/driver combination was not tested |
| GPU | `COMFYMODAL_V2_GPU` defaults to `rtx-pro-6000` | Intended target is RTX PRO 6000 Blackwell; InstantTensor has no explicit Blackwell claim |
| GPU arch build | SageAttention is built with `TORCH_CUDA_ARCH_LIST=12.0+PTX` | This is evidence for the repository's Blackwell assumption, not evidence that every dependency supports it |
| Memory profile | Standard/high-memory profiles use 32768 MiB | InstantTensor staging defaults need explicit tuning; upstream reports large default `io_depth` allocations |

Relevant paths: `comfyapp.py:7862-7902`,
`comfymodal_runtime/modal_app.py:7928`, and
`comfymodal_runtime/modal_app.py:3474-3484`.

### Current local validation host

The local, non-Modal environment used for this spike reported:

| Item | Observed value |
|---|---|
| Python | 3.11.9 |
| OS | Windows 10 x86_64 |
| PyTorch | 2.8.0+cu128 |
| Torch CUDA build | 12.8 |
| GPU | NVIDIA GeForce RTX 3070 |
| Local capability | compute capability 8.6 |
| safetensors | 0.5.3 |
| fastsafetensors | 0.3.3 |
| InstantTensor | not installed; no Windows binary matched `pip download` |
| Run:ai Model Streamer | not installed; no Windows binary matched `pip download` |
| ModelExpress | not installed |
| NVIDIA Dynamo | not installed |

No repository lockfile or production dependency was changed. The existing
repository pins safetensors in `cachedit_dependency_lock.txt`; fastsafetensors
is already pinned in `comfymodal_runtime/modal_app.py:3478`. Run:ai Model
Streamer is already an optional C9 queue-depth image extra at
`comfymodal_runtime/modal_app.py:3481-3484` and is not enabled by default.

## InstantTensor

### Primary sources

- Repository: https://github.com/scitix/InstantTensor
- Package metadata: https://pypi.org/project/instanttensor/
- Official vLLM extension documentation:
  https://docs.vllm.ai/en/latest/models/extensions/instanttensor/
- Source examined: `instanttensor/_impl.py`, `csrc/main.cpp`,
  `csrc/loader_common.cpp`, `csrc/loader_io_aio.cpp`,
  `csrc/loader_io_uring.cpp`, `csrc/loader_io_cufile.cpp`, and the wheel CI

Latest observed release was 0.1.9. PyPI metadata declares Python `>=3.9`
and `torch>=2.8.0`. Published wheels are Linux x86_64 for CPython 3.10-3.14;
there is no Windows wheel. Source builds require Linux and compile C++17
I/O support, including vendored libaio/liburing.

### Compatibility findings

| Question | Result | Evidence and limits |
|---|---|---|
| Install mechanism | `pip install instanttensor` | Official README and PyPI; source build is Linux-specific |
| Python/PyTorch | Python `>=3.9`, Torch `>=2.8.0` | Target Python 3.11 fits; repository's unpinned target Torch must be recorded at build time |
| CUDA | CUDA device required by the Python API | Runtime CUDA functions are resolved from the already loaded Torch process; no nvcc or library CUDA kernels are compiled |
| RTX PRO 6000 / Blackwell | UNKNOWN as an explicit upstream support claim | No Blackwell or RTX PRO 6000 is named upstream. The absence of compiled CUDA arch code makes support plausible when Torch and driver support the GPU, but not proven |
| Ordinary POSIX path | YES | Backends open ordinary path strings with `open`; no object-store or special fd API is required |
| GDS mandatory | NO | CUFILE is one optional backend. AIO, buffered AIO, io_uring, buffered io_uring, and mmap paths exist |
| Normal POSIX mount without GDS | YES, conditionally | Direct AIO/io_uring/CUFILE paths use `O_DIRECT`; `INSTANTTENSOR_BACKEND=BUFFERED` selects buffered I/O for mounts that reject it |
| FUSE/network/Modal mount | UNKNOWN | Upstream does not prove that the target mount accepts `O_DIRECT`; direct backends fail rather than automatically switching. Buffered mode is the required follow-up |
| mmap | YES as an internal backend | mmap is selected for in-memory filesystems; it is not a public Python mmap toggle |
| pread | YES internally, not as a standalone API | AIO uses `io_prep_pread`; there is no separate user-facing pread backend |
| AIO/io_uring | YES | Backend selection supports AIO, buffered AIO, URING, and buffered URING |
| Multi-file SafeTensors | YES | `safe_open` accepts a list of paths, plans reads across files, and exposes keys/metadata/tensor iteration |
| Generic PyTorch output | YES, with caveats | `tensors()` yields `(name, torch.Tensor)` CUDA pairs suitable for a plain mapping and `load_state_dict(assign=True)` |
| Model-family knowledge | YES | No model-family logic was found; layout constraints still apply |
| Target device | CUDA only in the Python API | It cannot serve as a CPU-first loader in the same way as Run:ai Model Streamer |
| CPU staging | Bounded internally | `io_depth`, chunk size, buffer size, concurrency, and `max_free_mem_usage` control staging; defaults can be aggressive |

### API and lifetime

The straightforward API is:

```python
from instanttensor import safe_open

with safe_open(paths, framework="pt", device=0) as loader:
    state = {name: tensor.clone() for name, tensor in loader.tensors()}
```

In release 0.1.9, `copy=True` is the default and yielded tensors own their
storage. `copy=False` exposes views into a reusable internal ring buffer and
requires consumption before the next yield and before context exit. The
iterator is single-use. The loader is CUDA-only and raises after context exit.

Important source-level constraints:

- Data offsets must be contiguous.
- Tensors in each file must be ordered by non-increasing element size.
- `tensors()` is the implemented iteration surface. Some upstream docstrings
  refer to `get_tensor`, but that method is not implemented in 0.1.9.
- Default staging uses host and device buffers derived from `io_depth` and
  chunk size. Upstream issue evidence reports multi-gigabyte defaults at
  larger world sizes; E15 would need an explicit low `io_depth` policy.

### Key flags

```text
CAN_USE_WITH_GENERIC_COMFY_STATE_DICT=YES, subject to layout and CUDA-only caveats
CAN_USE_ON_NORMAL_POSIX_MOUNT_WITHOUT_GDS=YES, using AIO/URING or BUFFERED; mount-specific O_DIRECT behavior remains a risk
```

### Prototype decision

No InstantTensor adapter was created. The current host is Windows and cannot
install the Linux package, so a local prototype would falsely test neither
the target ABI nor the target mounted filesystem. The target-image API is
simple enough for a later isolated `probe(paths, device)` adapter, but it
should follow a Linux shadow installation and SafeTensors layout probe.

## Run:ai Model Streamer

### Primary sources

- Repository: https://github.com/run-ai/runai-model-streamer
- Package metadata: https://pypi.org/project/runai-model-streamer/
- Official repository docs: `docs/README.md`, `docs/src/usage.md`,
  `docs/src/env-vars.md`, and `docs/src/installation.md`
- Python source: `runai_model_streamer/safetensors_streamer/safetensors_streamer.py`

The observed release was 0.16.1. It is a standalone Python SDK rather than a
Dynamo or vLLM runtime. The public shape is:

```python
from runai_model_streamer import SafetensorsStreamer

with SafetensorsStreamer() as streamer:
    streamer.stream_file(path)
    for name, tensor in streamer.get_tensors():
        gpu_tensor = tensor.to("cuda:0")
```

### Reuse evaluation

| Dimension | Result |
|---|---|
| Local SafeTensors path | YES; `stream_file` and `stream_files` accept local paths |
| Path-to-tensor shape | YES; yields `(name, torch.Tensor)` on CPU by default |
| Generic Comfy binding | MEDIUM/HIGH; the mapping shape is ordinary PyTorch, but tensors must be cloned or consumed before ring-buffer reuse and GPU movement is caller-owned |
| Bounded staging | YES; `RUNAI_STREAMER_MEMORY_LIMIT` supports minimal, byte-limited, or unlimited modes; the limit cannot be below the largest tensor |
| Source scheduling | YES for concurrent reads, chunk size, and distributed read division; it does not provide ModelExpress's multi-source priority chain |
| GDS | NO requirement; default path is CPU staging and caller-owned H2D |
| CUDA ownership | NONE; the caller selects and owns CUDA tensors/transfers |
| Runtime migration | NO |
| Dependency footprint | MEDIUM; Torch, NumPy, humanize, a native streamer library, and documented Linux system libraries |
| API stability | MEDIUM risk; release 0.x and active evolution, although the standalone API is small |
| Mounted filesystem | MEDIUM/HIGH; ordinary file reads avoid InstantTensor's explicit O_DIRECT requirement, but target mount throughput and native library behavior remain unmeasured |

### Verdict

```text
REUSABLE_AS_LIBRARY=YES
REQUIRES_RUNTIME_MIGRATION=NO
```

It is the best conservative source-reader candidate if E11 needs bounded CPU
staging and the Comfy binding can consume a stream or perform a controlled
per-tensor transfer. Retaining a full cloned mapping would remove much of the
memory benefit, so the binding contract must be designed before adoption.

## ModelExpress and NVIDIA Dynamo

### ModelExpress

Primary sources:

- Repository: https://github.com/ai-dynamo/modelexpress
- Package metadata: https://pypi.org/project/modelexpress/
- Repository architecture: `docs/ARCHITECTURE.md`

Observed package version: 0.5.0, Python `>=3.10`. The Python strategies include
local SafeTensors and Model Streamer paths, but they run inside engine loader
hooks. The documented integrations are vLLM, SGLang, TensorRT-LLM, and NVIDIA
Dynamo. The useful path is a priority chain involving peer transfer,
ModelStreamer, GDS, and the engine fallback.

| Dimension | Result |
|---|---|
| Local SafeTensors | YES, inside engine strategy hooks |
| Path-to-tensor library for ComfyUI | NO documented standalone API |
| Bounded staging | YES inside the ModelStreamer strategy |
| Python API | MEDIUM/LOW stability risk; pre-1.0 and engine-coupled |
| Dependency footprint | LOW suitability; gRPC, protobuf, pydantic, Torch, Model Streamer, and full system components |
| CUDA ownership | Operates in the serving engine's CUDA context |
| Runtime migration | YES; practical value requires adopting a supported serving engine and usually its ModelExpress server/metadata topology |

```text
MODELSTREAMER_REUSABLE_AS_LIBRARY=YES     # Run:ai component, not ModelExpress itself
MODELEXPRESS_REUSABLE_AS_LIBRARY=NO
MODELEXPRESS_REQUIRES_RUNTIME_MIGRATION=YES
```

### NVIDIA Dynamo

Primary sources:

- Repository: https://github.com/ai-dynamo/dynamo
- Documentation: https://docs.nvidia.com/dynamo/
- Package metadata: https://pypi.org/project/ai-dynamo/

Observed package version: 1.4.0, Python `>=3.10`. Dynamo is a datacenter
serving/orchestration runtime over vLLM, SGLang, and TensorRT-LLM. Its source
and docs expose no independent local SafeTensors path-to-tensor API. Model
weights remain the backend engine's responsibility; Dynamo's scheduling and
staging features target serving traffic and KV cache as well as runtime
coordination, not a ComfyUI state-dict loader.

```text
DYNAMO_REUSABLE_AS_LIBRARY=NO
DYNAMO_REQUIRES_RUNTIME_MIGRATION=YES
```

Adopting Dynamo would replace the runtime topology rather than simplify the
current source-side loader. It is out of scope for E15.

## Stock safetensors mmap/pread

### Primary sources and local evidence

- Repository: https://github.com/huggingface/safetensors
- Official docs: https://huggingface.co/docs/safetensors/
- Installed package: safetensors 0.5.3
- Local generated stub: `safetensors/__init__.pyi`
- Local implementation wrapper: `safetensors/torch.py`

The installed package is a thin Python wrapper over `_safetensors_rust`. Its
public `safe_open` API supports filename, framework, and device, with methods
including `keys`, `metadata`, `get_tensor`, and `get_slice`. It does not expose
a `pread` method, a destination-buffer method, or a public mmap toggle.

The local probe confirmed:

```text
safe_open_has_pread=False
safe_open_has_mmap=False
safe_open(..., mmap=False) -> TypeError: unexpected keyword argument 'mmap'
```

`get_slice` is a logical view over the mapped file data. It is not a user-facing
range-read or direct-destination API. A CUDA load still involves internal host
staging and DMA; changing a flag on stock safetensors cannot turn it into the
E11 source feeder.

| Requested capability | Stock safetensors 0.5.3 |
|---|---|
| Full tensor | YES through `safe_open(...).get_tensor(name)`, backed by the internal map |
| Tensor slice | YES as a logical `get_slice` view; not a pread byte-range operation |
| Arbitrary file byte range | NO public API |
| Direct destination buffer | NO public API |
| mmap selection | NO public toggle; mapping is an internal implementation detail |
| pread backend selection | NO public API |

```text
SAFETENSORS_PREAD_AVAILABLE=NO
SAFETENSORS_PREAD_API=NONE
```

Backend swapping can still improve E11, but it means replacing the loader
with fastsafetensors, Run:ai Model Streamer, or the existing staged path. It
does not mean selecting pread through stock safetensors.

## fastsafetensors Reuse

### Primary sources and current repository usage

- Repository: https://github.com/foundation-model-stack/fastsafetensors
- Package metadata: https://pypi.org/project/fastsafetensors/
- Installed package: fastsafetensors 0.3.3
- Current direct-GPU path: `comfymodal_runtime/unet_fastsafetensors.py:813-844`
  and `comfymodal_runtime/clip_fast_hydration.py:604-660`
- Existing staged source path: `comfymodal_runtime/staged_safetensors.py`

The package does expose a lower-level copier layer:

```text
fastsafetensors.copier.CopierInterface
fastsafetensors.copier.NoGdsFileCopier
fastsafetensors.copier.GdsFileCopier
fastsafetensors.copier.UnifiedMemCopier
fastsafetensors.copier.DStorageFileCopier
fastsafetensors.copier.ThreeFSFileCopier
fastsafetensors.copier.create_copier_constructor
```

The relevant interface is:

```text
set_byte_ranges(runs)
submit_io(use_buf_register, max_copy_block_size)
wait_io(gbuf, dtype, noalign)
```

The lower-level path can provide:

- `pread`-based `NoGdsFileCopier` reads into a bounded pinned bounce pool;
- `set_byte_ranges` for selected absolute file ranges;
- chunked ordered copying by source offset;
- CPU or CUDA destination devices through the framework operation layer;
- zero-copy tensor views whose lifetime is owned by the returned device buffer.

The package's loader layer, rather than one copier instance, aggregates files:
`add_filenames` registers multiple files and `copy_files_to_device` walks them
in sorted filename order. A copier itself is one-file-at-a-time. The current
repository's `staged_safetensors.py` remains the stronger implementation for a
bounded pooled host-to-GPU commit because fastsafetensors allocates a full
destination buffer per file/range and its internal bounce pool is not the same
as the repository's configurable total host pool.

The local CPU smoke succeeded with a temporary SafeTensors file:

```text
fastsafetensors 0.3.3
device=cpu
shape=(4,)
values=[0.0, 1.0, 2.0, 3.0]
```

Therefore:

```text
FASTSAFETENSORS_LOW_LEVEL_REUSE_AVAILABLE=YES
```

This is a reusable seam for a later E11 investigation, not a reason to change
C9/default behavior now. Its API is lower-level and more maintenance-sensitive
than the current `SafeTensorsFileLoader` path, and device-buffer ownership must
remain explicit.

## Candidate Scorecard

Ratings are feasibility ratings for this ComfyUI source-loader problem, not
generic product quality. `HIGH` means the candidate satisfies the dimension
with little additional architecture; `MEDIUM` means a bounded integration
condition remains; `LOW` means it conflicts with the current runtime; `UNKNOWN`
means E15 evidence cannot establish it without target execution.

| Candidate | Generic Comfy compatibility | SafeTensors support | Mounted distributed FS | Bounded memory | CUDA support | Dependency weight | Maintenance risk | Fallback simplicity | Likely to beat E10 source feeder |
|---|---|---|---|---|---|---|---|---|---|
| InstantTensor | HIGH, with layout/CUDA caveats | HIGH | MEDIUM; buffered mode helps, O_DIRECT unknown | HIGH, but defaults aggressive | HIGH | MEDIUM | MEDIUM | HIGH | HIGH, conditional |
| Run:ai Model Streamer | MEDIUM/HIGH; CPU tensors and clone/transfer contract | HIGH | MEDIUM/HIGH | HIGH, explicit CPU limit | MEDIUM; caller owns H2D | MEDIUM | MEDIUM | HIGH | MEDIUM/HIGH |
| fastsafetensors copier layer | MEDIUM; lower-level owner integration required | HIGH | MEDIUM; existing native behavior applies | MEDIUM; bounce pool bounded, destination buffer large | HIGH | LOW incremental because already present | MEDIUM/HIGH due lower-level API | HIGH | MEDIUM/HIGH |
| stock safetensors | MEDIUM for ordinary loading | HIGH | MEDIUM | LOW for source scheduling | HIGH | LOW | LOW | HIGH | LOW/MEDIUM |
| ModelExpress | LOW outside serving engine | HIGH inside strategies | MEDIUM | HIGH inside strategy | HIGH inside engine | LOW suitability | LOW | LOW | UNKNOWN |
| NVIDIA Dynamo | LOW | Delegated only | LOW for this use | N/A for Comfy model load | HIGH as serving runtime | LOW suitability | LOW | LOW | UNKNOWN |

### Score interpretation

- InstantTensor wins on direct CUDA output, multi-file planning, and bounded
  asynchronous I/O, but only if the target filesystem accepts the selected
  backend or is forced to buffered mode and the checkpoint layout passes its
  validation.
- Run:ai Model Streamer wins on standalone reuse and explicit CPU memory
  limiting, but a generic Comfy state dict must not retain mutable ring-buffer
  views and must account for the separate H2D phase.
- fastsafetensors is the lowest dependency-risk experiment because version
  0.3.3 is already in the image, but its lower-level copier surface does not
  automatically replace the repository's packed bounded staging design.
- ModelExpress and Dynamo score poorly because their main value is runtime
  integration, not a generic loader function.

## Production Boundary and Follow-up

No changes were made to:

- `comfymodal_runtime/staged_safetensors.py`;
- current CLIP or UNET production loader wiring;
- C9/default behavior;
- dependency lockfiles;
- Modal applications, images, volumes, or deployments.

The isolated E15 test file is:

```text
tests/test_v2_batch_e15_external_loader_feasibility.py
```

It checks the installed safetensors surface, the fastsafetensors copier
surface, optional-import independence of the staged loader, and a tiny local
fastsafetensors CPU copy. It deliberately makes no assumption that InstantTensor
or Run:ai Model Streamer is installed.

The minimum future validation before any external backend integration is:

1. Build a non-production Linux shadow image with a pinned InstantTensor
   version and record exact Torch/CUDA/driver versions.
2. Run a SafeTensors layout probe over the actual Comfy checkpoint shards.
3. Probe `O_DIRECT` on the actual model mount; if rejected, force
   `INSTANTTENSOR_BACKEND=BUFFERED` and repeat the loader probe.
4. Validate tensor lifetime and `load_state_dict(assign=True)` semantics with
   a tiny generic PyTorch module, retaining or cloning according to the chosen
   API.
5. Compare against E11 using identical source files, memory budget, and no
   fallback. Do not change the production default until those gates pass.

## Verification Record

Local commands/results:

```text
python -m unittest tests.test_v2_batch_e15_external_loader_feasibility
PASS: 14 tests in the current environment

python -c "... fastsafetensors CPU copy ..."
PASS: tiny tensor round-trip on CPU, fastsafetensors 0.3.3

python -m py_compile tests/test_v2_batch_e15_external_loader_feasibility.py
PASS
```

The full repository was not run because it contains unrelated pre-existing
worktree changes and the E15 request is an isolated feasibility spike. No
Modal deploy or Modal execution occurred.
