# Startup Flow

This documents the container lifecycle of `comfyapp.py`. Modal containers go
through two possible entry points depending on whether a memory snapshot exists:

- **`snap=True`** — cold start / snapshot creation (first deploy or after code change)
- **`snap=False`** — scale-from-zero restore from an existing snapshot

Both backends (`in_process`, `subprocess`) share the same lifecycle hooks but
take different code paths inside them.

---

## `@modal.enter(snap=True)` — Cold start / Snapshot creation

### Phase 1: Volume & custom-node setup (shared preamble)

| Step | What it does | Typical time |
|------|--------------|--------------|
| `_ensure_models_symlink()` | Symlink `/root/comfy/ComfyUI/models` → volume mount | 2–4 ms |
| `set_manager_network_mode_offline()` | Pin ComfyUI-Manager to offline mode | <1 ms |
| `vol.reload()` | Refresh Modal volume file listing | 100–130 ms |
| `_sync_custom_nodes_from_volume()` | Create/remove/repoint symlinks in `/custom_nodes` to match volume state | 150–250 ms |
| `_install_custom_node_requirements()` | `pip install -r requirements.txt` for changed custom nodes | 0–1200 ms |
| `_record_runtime_state()` | Snapshot model volume + custom-node directory state for stale-detection | 5–10 ms |

### Phase 2: Backend initialisation

Depending on `DEFAULT_EXECUTION_BACKEND` (overridable via
`COMFYMODAL_EXECUTION_BACKEND` env var).  The default is `"in_process"`.

#### In-process backend

| Step | What it does | Typical time |
|------|--------------|--------------|
| `os.chdir` + `sys.path` | Change CWD to `/root/comfy/ComfyUI` for module resolution | ~0 ms |
| `import folder_paths, utils.*, comfy.*` | Full ComfyUI Python import chain | **6000–6500 ms** |
| `_patch_model_cpu_cache(comfy.utils)` | Wrap `load_torch_file` to serve CPU-cached state dicts | ~0 ms |
| `_DummyServer.__init__` | Minimal PromptServer (no HTTP listener), asyncio event loop | 3–4 ms |
| `PromptExecutor.__init__` | Create executor with 24 GB model cache | 1–2 ms |
| `nodes.init_extra_nodes()` | Register all built-in + custom nodes (async) | **2000–2100 ms** |
| **Total** | | **~8500–8600 ms** |

#### Subprocess backend

| Step | What it does | Typical time |
|------|--------------|--------------|
| `_restart_comfy()` | Kill old subprocess (if any), `Popen(["comfy", "launch", …])`, wait for HTTP `/system_stats` | **~14000 ms** |

### Phase 3: Snapshot preload (in-process only)

After the backend is ready, the snapshot preload stage loads model files into CPU
RAM.  These state dicts are captured by Modal's memory snapshot and serve as a
CPU-side cache on restore (via `_patch_model_cpu_cache`).

| Step | What it does | Typical time |
|------|--------------|--------------|
| `_snapshot_preload_profile()` | Detect profile from env vars or last model stack (DB query) | ~1 ms |
| `_snapshot_preload_paths(profile)` | Resolve model bucket/file → absolute paths | ~1 ms |
| `_preload_models_to_cpu(paths)` | Load 3 model files (Flux 9 GB + Qwen 8.3 GB + VAE 0.24 GB) via `load_torch_file` to CPU RAM | **~5300 ms** |

### Total cold-start duration

| Backend | Typical total |
|---------|--------------|
| **in_process** *(default)* | **~14.5–15.5 s** |
| subprocess | **~25 s** (15.7 s setup + 9.6 s warmup GPU preload) |

---

## `@modal.enter(snap=False)` — Snapshot restore

Runs on every scale-from-zero container.  The snapshot already captured the
initialised state (imports, nodes, model cache), so this path is minimal.

### In-process backend

| Step | What it does | Typical time |
|------|--------------|--------------|
| `_ensure_models_symlink()` | Quick symlink check/recreate | ~0 ms |
| `_warmup_cuda()` | `torch.cuda.synchronize()` + 5× GEMM to re-init CUDA context and ramp GPU clocks | **50–250 ms** |
| Total | | **~50–250 ms** |

### Subprocess backend

| Step | What it does | Typical time |
|------|--------------|--------------|
| `_ensure_models_symlink()` | Quick symlink check/recreate | ~0 ms |
| `self._http_client.get("/system_stats")` | Health probe (timeout 5 s). If stale, restarts ComfyUI (+~14 s) | **~0 ms** (healthy) |
| Total | | **~0 ms** (healthy) |

---

## `@modal.exit()` — Shutdown

| Backend | What it does |
|---------|--------------|
| Both | Close HTTP client. If subprocess running, `terminate()` → `wait(10)` → `kill()`. |

---

## Execution phase (`/comfymodal/prompt` → `run_prompt`)

### In-process (`_execute_in_process`)

| Step | What it does | Typical time |
|------|--------------|--------------|
| `validate_prompt()` | Async ComfyUI workflow validation | 3–4 ms |
| `executor.execute()` | Run workflow graph: load models, encode text, sample, decode | **~14800 ms** |
| `_collect_in_process_outputs()` | Read output files from `/root/comfy/ComfyUI/output/` | **~2 ms** |
| **Total** | | **~14800 ms** |

### Subprocess (HTTP polling via `_submit_and_poll`)

| Step | What it does | Typical time |
|------|--------------|--------------|
| `POST /prompt` | Submit workflow JSON via HTTP | ~10 ms |
| Poll loop | Query `/history/{prompt_id}` every 250 ms until result appears | **~280 ms** overhead |
| `_collect_outputs()` | Read outputs via HTTP `/view` endpoint | **~10 ms** |
| **Total** | | **~7500–8000 ms** |

### Breakdown of 14800 ms in-process execution

| Phase | Time | Note |
|-------|------|------|
| VAE model load | ~0 ms | Cache hit (deepcopy_ms=0.0) |
| Qwen text encoding | **~1050 ms** | Includes Missing weight penalty (wrong CLIP loader in workflow) |
| Text→UNet handoff | **~2000 ms** | ComfyUI graph transition overhead |
| Flux model setup | **~32 ms** | CPU→GPU state dict copy (cache hit) |
| Flux sampling 20 steps / 3.1 it/s | **~9540 ms** | 6430 ms compute + 3110 ms executor overhead |
| VAE decode | **~1350 ms** | full_encoder_small_decoder.safetensors (119 MB, bf16) |
| Output collection | **~2 ms** | |

---

## Startup-time contributions (in_process)

### Fixed costs (unavoidable, once per Docker image)

| Item | Time | Why |
|------|------|-----|
| Python imports | ~6500 ms | ComfyUI + torch + all custom nodes |
| Node registration | ~2100 ms | `nodes.init_extra_nodes()` |

### Configurable costs

| Item | Time | Controlled by |
|------|------|---------------|
| Snapshot CPU preload | ~5300 ms | `ENABLE_WARMUP` env var + model stack detection |
| CUDA restore warmup | 50–250 ms | Always on (in_process `restore()`) |
| Warmup workflow (cold start only) | ~9600 ms | Always runs for subprocess on snap=True to populate GPU cache for subsequent restores |
| Warmup workflow replay (restore) | 0 ms | Gated by `ENABLE_WARMUP` env var — skipped by default |

---

## Snapshot size trade-off (why `in_process` is default, April 2026)

### The problem

`subprocess` warmup preload loads ~17 GB of model weights into GPU memory *before*
Modal's memory snapshot is taken.  With `enable_gpu_snapshot=True`, Modal's
snapshot includes this GPU memory — inflating total snapshot size from ~5 GB
(in_process) to ~22 GB (subprocess with warmup).

On a **cold restore** (snapshot evicted from local NVMe cache → fetched from
blob storage), this adds **40–52 s** of GPU memory deserialization overhead.

### The trade-off

| Backend | Restore (cold) | Execution | Total (cold restore) | Snapshot size |
|---------|---------------|-----------|---------------------|--------------|
| **in_process** *(default)* | ~1.3 s | ~14.7 s | **~16 s** | ~5 GB (CPU) |
| subprocess (warm NVMe) | ~4.7 s | ~6.9 s | **~12 s** | ~22 GB (CPU + GPU) |
| subprocess (cold blob) | ~52 s | ~6.9 s | **~59 s** | ~22 GB (CPU + GPU) |

`in_process` gives **consistently fast restores** regardless of cache temperature.
`subprocess` is faster only when the snapshot is hot on local NVMe — trade-off
wasn't worth the 4×-worse cold path.

### How to override

```bash
# Restore the subprocess default per-invocation:
COMFYMODAL_EXECUTION_BACKEND=subprocess modal run ...
# Or set the env var in your Modal secret / app config.
```
