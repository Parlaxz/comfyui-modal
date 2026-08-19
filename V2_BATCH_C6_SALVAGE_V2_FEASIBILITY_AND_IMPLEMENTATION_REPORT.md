# V2 Batch C6 Salvage — Meta-Construction + Direct File-to-Pinned UNET Loader (Feasibility & Implementation Report)

Date: 2026-08-15 · Agent: Batch C6 salvage continuation (subagent-driven)
Scope: Candidate investigation (meta construction, preadv→pinned, cudaHostRegister, fadvise, GDS) → mechanism probe → gated V2 implementation → one true-cold validation → **measured STOP**.

---

## 1. Executive verdict

| axis | result |
|---|---|
| Correctness | **PASS** — V2 loader produced byte-identical output (SHA `20b10e1f...e5260`, 6th consecutive generation), zero fallbacks, exactly one UNET lifecycle, final GPU-ready state cuda:0/bf16, TWO-LANE & MutationLane untouched |
| Performance | **FAIL** — valid-run pipeline wall **4.84 s vs 4.60 s healthy native fast-disk reference**: measured stage saving **negative (−0.24 s)**; ring `hidden_overlap_ms = 0.0` (total wall exceeded serial-equivalent by ~0.59 s) |
| C6 final decision | **STOP** (measured). Do not promote; do not default `COMFYMODAL_V2_UNET_META_DIRECT`. |

The mechanism-probe hypothesis (meta construction removes the 2.34 s V1 regression; preadv→pinned removes the 3.43 s staging pass) was **partially confirmed and ultimately defeated by volume read bandwidth**: the full-file preadv pass is page-in/volume-bound at **4.07 GB/s (3.02 s)** — the same physical floor the native path already achieves **in a single pass** (page-fault-during-DMA, 2.47 s). A two-pass loader (read → DMA) cannot beat a one-pass loader on the same bandwidth.

---

## 2. Candidates investigated (measured, not assumed)

| # | candidate | measured result | verdict |
|---|---|---|---|
| 1 | meta construction (`torch.device("meta")` + `Module.to_empty(cuda)`) | meta get_model **19.5 ms** (probe) / **199.9 ms** (validation, container-cold); to_empty **818 ms** (probe) / **525 ms** (validation); model_sampling meta-poisoning detected & fixed (rebuild outside context, **0.18 ms**, zero meta remain) | **CONFIRMED — chosen construction strategy** |
| 2 | direct `os.preadv` → pinned buffers | **supported & byte-exact** vs safetensors (`hash_match=true`); 6.6–14.0 GB/s on first ~1.5 GB; **4.07 GB/s full-file** (validation) | **CONFIRMED mechanically, defeated by bandwidth at scale** |
| 3 | `cudaHostRegister` on existing mmap pages | **NOT supported on this environment** — rc=304 "OS call failed or operation not supported on this OS" for 256 MiB and 1.5 GiB; attrs 99/113 unavailable | **DEAD (clean negative)** |
| 4 | `os.posix_fadvise` (WILLNEED/SEQUENTIAL) | call itself ~0.02 ms, effective (post-advise first-touch 489 GB/s = cache-warm effect); advisory only | **no architecture value** |
| 5 | GPUDirect Storage | libcufile present but `/proc/driver/nvidia-fs` absent → `GDS_SUPPORTED_ON_MODAL_VOLUME = NO`, `GDS_DIRECT_PATH_AVAILABLE = NO` (Modal Volume not a GDS-ready FS) | **DEAD (cheap check, stopped immediately)** |

### get_model slowdown root cause (the 2.34 s V1 question)

Mechanically measured: fresh pre-read construction **2390 ms** → warm second construction **749 ms** → post-read **851 ms**; minflt Δ = 0, RSS Δ = 0. The mechanism is a **cold first-allocation / allocator warm-up cost**, NOT COW and NOT memory pressure (the previous "COW" label was wrong). Meta construction sidesteps the entire question: **19.5 ms**, params materialized directly on CUDA, no 12.31 GB CPU allocation ever exists.

---

## 3. V2 implementation (default OFF, flag `COMFYMODAL_V2_UNET_META_DIRECT`)

### Dataflow (as validated)
```
_load_unet → _md_try_pipeline (lazy import, zero off-path cost)
  S1 flag+eligibility (ZImage only; fast-disk guard set; uniform bf16; CUDA; preadv; pinned probe)
  S2 with torch.device("meta"): config.get_model(meta_sd)      ~200 ms
     → rebuild model.model_sampling OUTSIDE meta (same comfy helper)  ~15 ms
  S3 plain ModelPatcher(load=cuda, offload=cpu)
  S4 model.to_empty(device=cuda)                                ~525 ms
  S5 key↔param map (diffusion_model submodule, unprefixed, strict=False subset; dtype gates)
  S6 byte-contiguous waves from header (build_wave_ranges; 128 MiB target, 256 MiB cap) → 137 waves
     posix_fadvise WILLNEED (0.02 ms)
  S7 2-slot pinned ring: per wave, sub-chunked os.preadv DIRECTLY into pinned slot
     (32 MiB syscalls, chunk-exact views, short-read retry) → wave event → async
     non_blocking copy_ into ALREADY-CUDA params → reuse-wait on slot event
  S8 final model.to (buffers only; no-duplicate stop check)     ~5 ms
  S9 exactly ONE torch.cuda.synchronize()                       ~0.06 ms
  S10 lean telemetry emit → (patcher,) → unchanged _load_unet tail → future → sampler unchanged
any failure → named stage reason + discard partial state + fresh _invoke_original exactly once
```

### Corrective cycle (standing rule: diagnose → fix → redeploy → repeat once)
- Validation run 1 (05-08-09): pipeline engaged (meta 63 ms, to_empty 103 ms, 137 waves) then `stage:md_run:preadv_short_read`. Diagnosed: (a) failure metrics were init values (partial progress discarded — diagnostics blind spot); (b) wave/offset math verified EXACT via local replay of the real 453-key header (137 waves, sum 12,309,817,472, zero errors); (c) leading hypothesis = volume short/zero reads at the unproven 90–118 MB single-call regime.
- Corrective changes (implemented directly this session after two empty fixer dispatches): sub-chunked preadv (32 MiB syscalls with **chunk-exact buffer views** — the original full-slot view let `os.preadv` read beyond the chunk, which is itself a short-read trigger), 1 MiB capability self-test before the wave loop, fadvise error capture, 3-tuple failure contract `(None, reason, partial_metrics)` with `fail_wave_idx/offset/requested/got`, per-chunk byte accumulation, caller-side partial-metrics merge into the emitted event.
- Validation run 2 (05-40-58): **status=ok, fallback_count=0** — the fix worked; evidence below.

### Tests
`tests/test_c6_meta_direct.py`: 31 original + 8 corrective (chunk bounds/offsets, chunk assembly byte-exactness + param value equality, partial-return retry within chunk, short-read fail details + partial progress, self-test fail-fast before waves, self-test pass, fadvise error non-fatal, partial metrics merged into emitted fallback event) = **39 passed**. Regression batch: **429 passed / 10 failed — all 10 are the known pre-existing set** (9× TestBenchmarkPrefixInstrumentation + test_no_global_monkeypatches within-file order case); no new failures. `py_compile` clean.

---

## 4. Valid-run evidence (v2_2026-08-15_05-40-58, deploy 49d1959d76ce8cbd, comfyui_core_match=1)

### Acceptance contract
- Fresh **YES** · C1 identity healthy (deployment_combined_hash `49d1959d76ce8cbd`) · B1 **exact_match** (skipped_generation_match observed)
- ZImage eligible · **fallback_count = 0** · exactly one UNET lifecycle (1 `unet_meta_direct_pipeline`, 0 fast-disk, 0 load_torch_file events)
- Output SHA **`sha256:20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`** — identical to baseline (6th consecutive generation)
- Final GPU state: load/offload/current = cuda:0, first param bfloat16, ModelPatcher/Lumina2/NextDiT
- Waterfall: **local reconciliation OK (0.7 ms)**; host-rebuild FAILED (−1442.8 ms) — documented pre-existing vehicle property (probe-off baseline runs fail identically; local is the authoritative in-container accounting)

### Pipeline telemetry (the decisive numbers)
| metric | value |
|---|---|
| header_config / value_probe | 37.8 / 1.8 ms |
| meta get_model | **199.9 ms** (vs V1 cold 2340.9 ms) |
| sampling fix | 14.9 ms (1 poisoned tensor detected & fixed) |
| to_empty(cuda) | 525.2 ms |
| waves | 137 (target 128 MiB, max wave 118.5 MB, mean 89.9 MB) — exact match to local header replay |
| pinned | 442,966,144 B (~2 slots + self-test probe) |
| **preadv I/O** | **3021.9 ms @ 4.07 GB/s full-file** (vs 6.6–14 GB/s on first 1.5 GB) |
| DMA device | 487.7 ms (hides under I/O in wall terms) |
| H2D host issue | 286.8 ms (sub-chunk syscalls) |
| reuse wait | 13.4 ms total / 4.9 ms max |
| final model.to / final sync | 5.2 / 0.06 ms |
| **total pipeline wall** | **4839.9 ms** |
| serial-equivalent | 4254.7 ms |
| **hidden_overlap** | **0.0 ms** (wall EXCEEDS serial-equivalent by ~585 ms) |
| fallback_count | 0 |
| non-scheduling request wall | 16.27 s (host heavily contended — scheduling 60+ s; stage-level internal accounting is host-independent) |

### Performance gate evaluation
- Native healthy fast-disk chain reference: **4.605 s** (read 1.62 + construction/bind 0.51 + H2D 2.47 — C6 probe measurement, same vehicle family)
- V2 measured: **4.84 s** → stage saving **−0.24 s** (no saving; slightly slower)
- Gate required ≥ **+0.5 s** conservative stage-level saving → **FAILED by ~0.74 s**
- Root cause is physical, not fixable by tuning within this architecture: full-file Modal Volume read is ~3–4 GB/s whatever the mechanism (preadv, mmap page-in, staging memcpy all converge); native H2D already runs at that floor **in one pass** (page-fault-during-DMA). Any read-then-DMA loader pays the read pass twice.

---

## 5. Final field summary

```
report path            = V2_BATCH_C6_SALVAGE_V2_FEASIBILITY_AND_IMPLEMENTATION_REPORT.md
changed files          = comfymodal_runtime/unet_meta_direct.py (V2 loader: constants, sub-chunked
                         preadv + self-test + 3-tuple failure contract + caller merge),
                         comfymodal_runtime/unet_salvage_probe.py (mechanism probe module),
                         comfymodal_runtime/modal_app.py (_runtime_env passthrough +
                         run_unet_mechanism_probe standalone function),
                         comfymodal_runtime/model_preload.py (_md_* flag parse + _load_unet branch),
                         tests/test_c6_meta_direct.py (39), tests/test_c6_salvage_probe.py (36)
commit = none
deploy count           = 3 (mechanism probe 23dee44a; V2 attempt-1 45cdf0a2; corrected V2 49d1959d)
Modal requests         = 3 (1 mechanism probe; 2 validation runs — first fell back
                         preadv_short_read [discarded, diagnosed], second VALID 05-40-58; no cohort)

current V1 ring status = DEFAULT OFF, untouched, remains in tree
get_model slowdown root cause = cold first-allocation/allocator warm-up (2.39 s cold vs 0.75 s warm;
                         minflt=0, RSS=0 — NOT COW, NOT memory pressure)
ordinary pre-read get_model = 2390 ms (probe) / 2340.9 ms (V1 run)
meta get_model          = 19.5 ms (probe) / 199.9 ms (validation container-cold)
skip-init/other construction = not applicable (meta-device context used; skip_init unsuitable for
                         comfy's get_model signature)
chosen construction strategy = torch.device("meta") context + model_sampling rebuild outside +
                         to_empty(cuda) — solves the 2.34 s regression completely

safe_open/mmap staging GB/s = 3.6 (V1 staging) — superseded
direct preadv->pinned supported = YES (byte-exact vs safetensors, hash-verified)
preadv->pinned GB/s     = 6.6–14.0 (first ~1.5 GB) / 4.07 full-file (validation)
cudaHostRegister supported = NO (rc=304; attrs 99/113 unavailable)
cudaHostRegister total cost = n/a (unsupported)
posix_fadvise effect    = call ~0.02 ms; advisory; cache-warm effect only; no architecture value

GDS supported on Modal Volume = NO
GDS direct path available = NO (nvidia-fs absent; volume not GDS-ready FS)

chosen I/O strategy     = os.preadv -> 2 pinned slots (32 MiB sub-chunks, chunk-exact views)
chosen wave size        = 128 MiB target (137 waves; max 118.5 MB)
projected full-model I/O wall = 3.02 s (measured, volume-bandwidth-bound)
projected construction wall = ~0.74 s (measured: header+probe+meta+fix+to_empty)
projected total UNET chain = 4.84 s (measured)
conservative projected saving = NEGATIVE (−0.24 s vs 4.60 s native)

actual UNET chain       = 4839.9 ms (pipeline wall, valid run 05-40-58)
native-equivalent/reference chain = ~4605 ms (healthy fast-disk C6 reference)
measured stage saving   = −235 ms (no saving)
non-scheduling request wall = 16.27 s (host contended; internal accounting host-independent)
fallback count          = 0
output SHA              = 20b10e1f...e5260 (identical, 6th consecutive generation)
final GPU state         = cuda:0 / bf16 / ModelPatcher(Lumina2, NextDiT)

correctness classification = PASS (byte-identical output, zero fallbacks, one lifecycle, GPU-ready,
                         fail-closed contract proven across the corrective cycle)
performance classification = FAIL (pipeline ≥ native; ring overlap 0; stage saving negative)
C6 final decision       = STOP (measured)
recommended production default = OFF
additional work recommended = none within C6's two-pass loader scope. The measured floor
                         (volume read ~3–4 GB/s full-file; native single-pass page-in-during-DMA at
                         the same floor) closes read→DMA pipelining as a winning line. A future win
                         would require eliminating a pass entirely (true GDS-class storage→GPU, or
                         persistent page-cache residency across requests — a different optimization
                         axis, not a loader rewrite).
reason                  = V2 is correct but not competitive: the preadv read pass (3.02 s) is
                         page-in/volume-bandwidth-bound and simply duplicates the native H2D pass
                         (2.47 s). Total 4.84 s ≥ native 4.60 s; hidden overlap 0; the ≥500 ms gate
                         fails by ~0.74 s. Per the standing rule the first valid run is the data
                         run — no cohort, no retuning.
```

## 6. Manual checks for the reader

1. **Decision: STOP C6.** `COMFYMODAL_V2_UNET_META_DIRECT` and `COMFYMODAL_V2_UNET_PINNED_RING` both remain default OFF. Do not promote either.
2. The V2 implementation stays in the tree as a documented, fail-closed, default-off path (useful reference if Modal Volume bandwidth or a GDS-class storage option ever changes the floor).
3. Host-rebuild waterfall FAILED status is the documented pre-existing vehicle property (baseline-identical); local reconciliation (OK, 0.7 ms) is authoritative.
4. No commit was made; C4 app/reports/artifacts untouched; TWO-LANE and MutationLane semantics unchanged (ring DMA outside the mutation FIFO, exactly like the fast-disk H2D).
