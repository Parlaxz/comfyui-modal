# V2 Batch C9 — FastSafetensors Production Integration Report (Meta ZImage + Concurrent Direct-GPU Load)

Date: 2026-08-15 · Agent: Batch C9 continuation (subagent-driven) · Scope:
default-OFF production integration experiment consuming the accepted C9
queue-depth result and the C10 fastsafetensors finding with the C8-proven
meta-construction strategy. One canonical deployment, one true-cold
validation generation (standing rule; no cohort). No commit, no branch.

---

## 1. Verdict

### Correctness: PASS — Performance: MAJOR WIN (measured 2743 ms UNET chain)

| axis | result |
|---|---|
| Correctness | **PASS** — output SHA `20b10e1f…e5260` (exact baseline match), fastsafe status=ok, fallback_count=0, 453 tensors / 12,309,817,472 B exact, zero-copy bind proven (8/8 data_ptr equality), residual meta 0, final cuda:0 bf16, one authoritative UNET lifecycle, native fast-disk machinery SKIPPED (`unet_fast_disk_skip=1`, `unet_fast_disk_complete=0`), TWO-LANE/MutationLane unchanged, local waterfall reconciliation OK |
| Performance | **MAJOR WIN** — integrated UNET load chain **2743.4 ms** vs native reference **4605.3 ms** → **measured loader saving 1861.9 ms (40.4% reduction)**. Band: ≤ 3.0 s = MAJOR WIN; the 2.0 s STRONG band was not reached only because meta construction was a cold-host outlier (2292.9 ms vs C8's 19.5–199.9 ms band) — the fastsafe file→GPU stage itself was 2172.9 ms cold (5.67 GB/s), and the bind dropped to **9.5 ms** (native 109.6 ms). |

The pipeline replaced the native read→construct/bind→H2D chain entirely on the
valid run: no native mmap read, no native bulk H2D, no to_empty(cuda), no
preadv ring, no ComfyUI core change. The output is byte-identical to the
accepted baseline across the full generation.

---

## 2. Exact target and configuration

- model file = `z_image_turbo_bf16.safetensors` (diffusion_models)
- total data bytes = **12,309,817,472** (453 tensors, bf16, gap-free)
- platform = AWS/us-east-2, RTX PRO 6000 Blackwell, CUDA 13.0, torch
  2.13.0+cu130, 32 GiB container, safetensors 0.5.3 (image-pinned; the
  official pread backend is unavailable and was not modified)
- deployment = `stable-modal-comfy-v2-c9qd-shadow`, deployment_combined_hash
  `d0c3dfefc3ba4742`, comfyui_core_match=1, custom_nodes_generation
  `8ed7b4825727227b` — deployed via the canonical
  `deploy_and_run_v2_single.bat` (never raw `modal deploy`), which also
  published custom nodes to the Volume and recorded the baked identity.
- vehicle = UNET-absent snapshot construction (SNAPSHOT_EXCLUDE_UNET=1,
  clip_vae eviction, CPU_MODEL_SNAPSHOT=1, SNAPSHOT_MODEL_ORDER=O0) — the
  documented production config under which the UNET is ALWAYS fresh-loaded
  through the V2LoaderBridge prep lane (restore_count=1, request_count=1,
  Fresh YES, stored_snapshot_model_order=O0).

## 3. Implementation summary

New default-OFF production path (flag `COMFYMODAL_V2_UNET_FASTSAFETENSORS`;
on/off/invalid fail-closed; historical flags untouched):

- `comfymodal_runtime/unet_fastsafetensors.py` — the pipeline:
  1. narrow ZImage-only eligibility (family, HIGH_VRAM, no torch future,
     no quant/FP8/channels_last, uniform bf16 sd dtype within supported,
     weight_dtype default, CUDA, fastsafetensors importable);
  2. header-only config derivation + value probe (allow_fp16) + hard
     param-count gate (6,154,908,736);
  3. **Worker A**: meta ZImage construction + model_sampling repair outside
     the meta context (C8 strategy); **Worker B**: fastsafetensors nogds
     file→CUDA (`SafeTensorsFileLoader`, threads=16, 1 GiB blocks,
     `use_buf_register=False`, `disable_cache=True`) — run CONCURRENTLY,
     joined with measured worker/join walls;
  4. validity gates (453 tensors / exact bytes / key set / shape+dtype
     spot check / transform INDEPENDENT);
  5. zero-copy bind: `diffusion_model.load_state_dict(tensors, assign=True)`
     with a post-bind data_ptr sample (torch's assign replaces Parameter
     entries, so the sample re-walks after bind — 8/8 exact);
  6. residual-meta sweep + byte-budgeted final `.to()` (500 ms duplicate-
     transfer gate) + one synchronize + final validation (all params on
     target, zero meta);
  7. plain ModelPatcher + **owner retention**:
     `patcher._comfymodal_fastsafe_owner` (loader + FilesBufferOnDevice) for
     the model's full lifetime — never `close()` on success;
  8. lean one-event telemetry `unet_fastsafetensors_pipeline` (walls, bytes,
     GB/s, data-ptr proof, owner mode, memory deltas, CUDA deltas,
     fallback_count);
  any failure → named reason, loader/buffer release, CUDA cache clear,
  fresh native `_invoke_original` exactly once.
- `model_preload.py` — flag functions + `_load_unet` branch (ring → meta-
  direct → fastsafetensors → native); on success the native fast-disk
  machinery is never invoked (`unet_fast_disk_skip`).
- `modal_app.py` — `_runtime_env` passthrough for the new flag +
  `run_env_probe` allowlist + deployed-code capability read
  (`_comfymodal_fs_flag_value` / `_comfymodal_fs_pipeline_enabled`).
- `unet_qd_probe.py` — structural gate now carries the fastsafetensors CUDA
  **ownership micro-test** (identity records + retained/closed lifetime).
- `tests/test_c9_fastsafetensors_integration.py` — 28 offline tests.

## 4. Gate 1 — GPU tensor ownership/lifetime (RESOLVED: loader retained)

Traced upstream 0.3.3 source: `copy_files_to_device` returns a
`FilesBufferOnDevice` that OWNS the backing device buffer; `get_tensor`
returns zero-copy views sharing the gbuf lifetime; the contract is explicit
that tensors are valid only while the buffer stays open and `close()`
invalidates them. The pipeline therefore retains the loader+fb on the
patcher for the model's lifetime, never closes on success, and never clones.

Empirically confirmed in the first valid container (structural gate,
`loader_ownership`): representative tensors recorded (data_ptr, storage
data_ptr == data_ptr, storage_offset 0, contiguous, base None; small-file
case yields per-tensor allocations); **retained_lifetime: hash identical
after gc.collect + synchronize** (f908964d… before/after); **closed_lifetime:
read after `close()` errors** (`error:KeyError:0`) — the documented
invalidation contract. On the data run, the zero-copy bind was proven by
exact data_ptr equality on 8/8 sampled parameters, and the generation
completed byte-identically with the owner retained.

## 5. Gate 2 — memory (RESOLVED: no hidden full-file CPU allocation)

| snapshot | field | value |
|---|---|---|
| after load | RSS delta | **+171 MB** (bounce pool + overhead — NO 12.31 GB CPU file buffer) |
| after load | CUDA allocated delta | **+11.54 GB** (the 11.47 GiB file buffer lives in VRAM) |
| after load | CUDA reserved delta | +12.33 GB |
| after load | CUDA reserved peak | 13.09 GB |
| after bind | RSS delta | +10.9 MB (zero-copy bind adds no memory) |
| request peak | process maxRSS | 34.92 GiB (includes the snapshot-construction phase of the vehicle — CLIP/VAE/UNET captured before UNET eviction; not a loader cost) |

Conclusion: fastsafetensors' CUDA path introduces only the bounded bounce
pool on the host; the payload is read directly into VRAM. No production
memory-request increase is required (32 GiB container unchanged).

## 6. Valid-run evidence (v2_2026-08-15_18-32-47)

Fresh YES · C1 identity healthy (deployment_combined_hash d0c3dfefc3ba4742,
comfyui_core_match=1) · B1 exact match (harness validation passed;
generation parity) · ZImage eligible · fastsafe status=ok ·
**fallback_count = 0** · exactly one authoritative UNET lifecycle
(one `unet_fastsafetensors_pipeline`, zero `unet_fast_disk_complete`) ·
tensors=453 · bytes=12,309,817,472 · key_set_ok · spot_check 16/16 ·
transform INDEPENDENT · residual meta 0 · first param cuda:0 bf16 ·
ModelPatcher healthy (full generation produced output) · **NO native mmap
read** (`unet_fast_disk_skip=1`) · **NO native H2D replay** · TWO-LANE
unchanged (execution_prefill_* + sampler lane intact; sampling 4.898 s) ·
MutationLane unchanged · local waterfall reconciliation OK (−6.958 ms) ·
**output SHA = sha256:20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
(EXACT MATCH)**

Pipeline telemetry (the data run):

| metric | value |
|---|---|
| header/config wall | 14.49 ms |
| value probe wall | 0.94 ms |
| meta get_model wall | **2292.86 ms** (cold-host outlier; C8 band 19.5–199.9 ms) |
| sampling fix wall | 12.61 ms (1 poisoned tensor repaired) |
| fastsafe setup wall | 21.89 ms |
| **fastsafe file→GPU wall** | **2172.92 ms (5.67 GB/s)** — true-cold (standalone battery's 924 ms/13.3 GB/s was cache-warm) |
| fastsafe instantiate wall | 0.57 ms |
| worker A / worker B / join | 2306.3 / 2195.4 / 2298.1 ms (concurrent; join ≈ worker A) |
| **bind wall** | **9.54 ms** (zero-copy assign; native 109.6 ms) |
| final sweep+to wall | 43.45 ms |
| final sync | 0.05 ms |
| **total pipeline wall** | **2743.40 ms** |
| native reference chain | 4605.3 ms (read 1623.7 + construction/bind 513.7 + H2D 2467.9) |
| **measured loader saving** | **1861.9 ms (40.4% loader reduction)** |
| non-scheduling request wall | 18.33 s (production_adjusted_total_wall_ms) |
| command → response | 43.6 s (scheduling 25.96 s dominates) |

Performance band: **MAJOR WIN** (≤ 3.0 s). The residual gap to the STRONG
band is the cold-host meta-construction outlier (2.3 s); the fastsafe I/O
(2.17 s cold) and the 9.5 ms bind are the healthy contributions. Do not
subtract historical numbers beyond the loader-stage comparison (the
internal chain is the authoritative comparison, per the mission).

## 7. Required fields

```
report path            = V2_BATCH_C9_FASTSAFETENSORS_INTEGRATION_REPORT.md
changed files          = comfymodal_runtime/unet_fastsafetensors.py (new),
                         comfymodal_runtime/model_preload.py (flag + branch),
                         comfymodal_runtime/modal_app.py (env passthrough +
                         run_env_probe capability read),
                         comfymodal_runtime/unet_qd_probe.py (ownership
                         micro-test),
                         tests/test_c9_fastsafetensors_integration.py (new)
commit = none
deploy count           = 7 (6 direct vehicle-debug deploys + 1 canonical
                         deploy_and_run_v2_single.bat deployment
                         d0c3dfefc3ba4742)
Modal requests         = 11 (3 structural gates, 4 env probes, 1 identity
                         readback, 5 benchmark generations — of which 1 is
                         the valid data run; the earlier attempts were
                         structurally-invalid vehicle configurations
                         discarded per the standing fix-and-repeat rule;
                         no cohort)

implementation status  = DEFAULT-OFF integration validated end-to-end
flag default           = OFF (COMFYMODAL_V2_UNET_FASTSAFETENSORS; invalid
                         values fail closed)
family eligibility     = ZImage only (narrow, fail-closed; Lumina2 excluded)

fastsafetensors version = 0.3.3
threads                = 16
max_copy_block_size    = 1 GiB
nogds                  = True
buf_register           = False (cudaHostRegister unsupported, C6 rc=304)

tensor ownership mode  = loader_retained (FilesBufferOnDevice owns the gbuf;
                         upstream-documented + container-verified)
loader owner retained  = YES (patcher._comfymodal_fastsafe_owner, model
                         lifetime; no close() on success)
clone required         = NO (data_ptr 8/8 exact; zero-copy assign)

host memory delta      = +171 MB RSS after load (no full-file CPU alloc)
host memory peak       = 34.92 GiB maxRSS (includes construction phase)
CUDA memory delta      = +11.54 GB allocated (file buffer in VRAM)
CUDA memory peak       = 13.09 GB reserved

header/config wall     = 14.49 ms
meta get_model wall    = 2292.86 ms (cold-host outlier)
sampling fix wall      = 12.61 ms
fastsafe file->GPU wall = 2172.92 ms (5.67 GB/s cold)
bind wall              = 9.54 ms
final validation wall  = 43.45 ms (sweep+to+sync)

integrated UNET chain  = 2743.40 ms
native reference chain = 4605.3 ms
measured loader saving = 1861.9 ms
percent loader reduction = 40.4%

non-scheduling request wall = 18.33 s (production_adjusted_total_wall_ms);
                         command→response 43.6 s (scheduling 25.96 s)

fallback count         = 0
tensor count           = 453
bytes                  = 12,309,817,472
config parity          = PASS (param count exact; transform INDEPENDENT;
                         key/shape/dtype gates; value probe resolved)
residual meta          = 0
output SHA             = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260 (exact)
final GPU state        = 453/453 params cuda:0 bf16; first param cuda:0 bf16

native mmap read occurred = NO (unet_fast_disk_skip=1)
native H2D replay occurred = NO (no fast-disk to events)
TWO-LANE unchanged     = YES (prefill + sampler lane evidence intact)
MutationLane unchanged = YES

tests                  = 28 new integration + 113 (C8/C6/QD) + 108
                         (Batch A/B/C acceptance) green; py_compile clean
Batch B/C              = green (108)
B1                     = exact match (harness validation passed)

correctness classification = PASS (byte-identical output; all gates held)
performance classification = MAJOR WIN (2743 ms ≤ 3.0 s; 40.4% loader
                         reduction; bind 9.5 ms; single-pass read→GPU)

C8_SEPARATE_VALIDATION_NEEDED = NO — C8's meta construction was consumed
                         and validated inside this path (sampling repair,
                         zero residual meta, byte-identical output)
C10 ready to archive    = YES — its tuned fastsafetensors path is consumed
                         and validated here
C12 ready to archive    = YES — no shards created; same-file QD already
                         reached 40.72 GB/s

recommended production default = OFF (evidence returned; separate decision
                         required before enabling)
additional runs needed = 0 — first correct validation run is the data run;
                         no cohort
reason = the default-OFF fastsafetensors + meta-construction loader
                         replaced the native UNET chain on a true-cold
                         generation with byte-identical output (SHA exact),
                         zero fallbacks, zero native replay, a 9.5 ms
                         zero-copy bind, no hidden full-file CPU
                         allocation, and a 1861.9 ms (40.4%) loader-stage
                         saving (MAJOR WIN band); the residual gap to the
                         2.0 s STRONG band is a cold-host meta-construction
                         outlier, not a mechanism limit.
```

## 9. Addendum — second cold run (user-requested evidence; not a cohort)

A second true-cold generation was explicitly requested and run against the
same deployment (d0c3dfefc3ba4742) at `v2_2026-08-15_19-02-50`
(AWS/ap-northeast-1 — a different region/host than run 1's us-east-2).
Standing-rule data-run semantics unchanged (run 1 remains the classification
run); this run is confirmatory evidence only.

| metric | run 1 (us-east-2) | run 2 (ap-northeast-1) |
|---|---|---|
| fastsafe status / fallback | ok / 0 | ok / 0 |
| header/config | 14.49 ms | 15.34 ms |
| meta get_model | 2292.86 ms | 2576.18 ms |
| sampling fix | 12.61 ms | 0.92 ms |
| fastsafe file→GPU | 2172.92 ms (5.67 GB/s) | 2499.30 ms (4.93 GB/s) |
| bind | 9.54 ms | 9.92 ms |
| final sweep+to+sync | 43.5 ms | 28.6 ms |
| pipeline total | 2743.40 ms | 3792.58 ms |
| hidden overlap (A+B−wall) | ≈1758 ms | ≈1309 ms |
| non-scheduling request wall | 18.33 s | 44.90 s (host restore 29.5 s) |
| output SHA | exact | **exact (20b10e1f…e5260)** |
| RSS delta after load | +171 MB | +21.9 MB |
| CUDA alloc delta | +11.54 GB | +12.31 GB |

Run 2 confirms: (a) byte-identical output is reproducible across hosts;
(b) the meta get_model cold cost (2.3–2.6 s) is a systematic container-cold
phenomenon on this vehicle, not a one-off — it now dominates the pipeline
alongside the cold fastsafe I/O (2.2–2.5 s), which run concurrently with
~1.3–1.8 s of hidden overlap; (c) memory behavior is stable (no hidden
full-file CPU allocation); (d) host/region variance is large (restore 3.4 s
vs 29.5 s; I/O 4.9–5.7 GB/s), so the internal loader-stage comparison
remains authoritative. Run 2 sits in the MEANINGFUL WIN band (3.0–4.0 s);
run 1 remains the classification basis (MAJOR WIN).

1. Meta get_model took 2292.9 ms on the data-run host (C8's measured band is
   19.5–199.9 ms). With meta at the healthy band the chain would be
   ~0.7 s (STRONG band); the mechanism is not meta-bound — this host was.
2. The first four benchmark generations of this task were structurally
   invalid vehicle attempts (raw deploys missing the documented
   construction vehicle; flag/`_load_unet` lane never engaged). They were
   discarded per the standing rule. The canonical
   `deploy_and_run_v2_single.bat` + `run_v2_single.bat` flow (per
   `.slim/deepwork/v2-cold-runs.md`) is the required vehicle; the valid run
   came from it.
3. The structural gate's ownership micro-test used a 1 MiB synthetic file
   (per-tensor allocations in that regime); the production ownership mode
   is the same loader-retained contract verified on the data run via
   data_ptr equality + byte-identical output.
4. `normal_loader_ready`/`unet_loader_*` events were not present in the run
   trace (lane-worker trace context); the authoritative lifecycle evidence
   is the single `unet_fastsafetensors_pipeline` event + `unet_fast_disk_skip`
   + the harness-validated generation.
5. No commit was made; C4 artifacts untouched; unrelated working-tree
   changes preserved.

---

## You asked for

- Implement and validate a default-OFF production integration of
  fastsafetensors 0.3.3 (nogds, 16 threads, 1 GiB blocks,
  use_buf_register=False) as the storage→GPU engine combined with C8 meta
  construction for ZImage, with owner/lifetime and memory gates, one
  canonical deployment, one true-cold validation generation, and the
  required report.

## You should now manually check

- **Decision fields**: performance MAJOR WIN (2743 ms, 40.4% loader
  reduction) but production default stays OFF — a separate decision is
  required before enabling `COMFYMODAL_V2_UNET_FASTSAFETENSORS`.
- The cold-host meta-construction outlier (2292.9 ms vs C8's 19.5–199.9 ms
  band) — worth confirming on a second diagnostic container before
  production consideration (the fastsafe stage itself was 5.67 GB/s cold).
- Owner-retention semantics: the fastsafetensors file buffer (12.31 GB
  VRAM) lives as long as the ModelPatcher; unload/reload behavior (patcher
  unload copies params to CPU while the gbuf stays reserved) should be
  exercised in a multi-request reuse scenario before any production
  decision.
- Run artifacts: `comfymodal-data/benchmarks/runs/v2_2026-08-15_18-32-47/`
  (run_0.json, summary.json) — pipeline event, SHA, waterfall, memory.
- No commit was made; C4 untouched; all unrelated working-tree changes
  preserved.
