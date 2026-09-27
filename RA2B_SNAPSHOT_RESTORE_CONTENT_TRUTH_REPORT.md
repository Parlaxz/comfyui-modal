# RA2B snapshot/restore content truth report

> **SUPERSESSION NOTICE (2026-08-30):** Historical Golden snapshot evidence;
> preserve its observations, but use
> `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for current generated-output
> semantics. Output durability is off by default; strict commit/reopen/hash
> proof is opt-in. S4 source publication durability remains mandatory.

## Executive answer

The three supplied serial Golden attempts are all structurally valid,
true-cold, provenance-validated one-restore/one-request diagnostic
observations. They show a
bounded model-free capture surface, a continued snapshot generation,
quiescent runtime state, successful restore/request execution, and durable
commit/reopen ordering. In every attempt `output_sha_match=false`, so none is
Golden acceptance-valid under the exact-output contract. That is a separate
configured output exactness result and is **not** by itself a snapshot-content
failure.

The paired manifests show capture at `snapshot_manifest.stage=before_capture`
and restore at `snapshot_manifest_restore.stage=first_restored_line`. They do
not expose Modal serialized bytes or the complete opaque serializer object
graph. The authoritative completion field is
`SERIALIZED_MODAL_SNAPSHOT_BYTES=UNAVAILABLE`. RSS, cgroup bytes, mapped bytes,
and `snapshot_size_bytes` are not serialized snapshot size.

## Evidence classification

- **Observed:** directly present in an attempt, event stream, or run manifest.
- **Derived:** arithmetic or a count difference computed only from observed
  fields.
- **Inferred:** a bounded interpretation supported by observed evidence, not a
  direct serializer or heap observation.
- **UNKNOWN/UNAVAILABLE:** not returned by the artifacts.

## Authoritative diagnostic observation set and identity boundary

| Cohort | Attempt | Run manifest | Request | Result |
|---|---|---|---|---|
| `cohort_2026-08-30_19-43-23_b37a7c` | `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-43-23_b37a7c/attempt_0.json` | `.v2ctl/runs/run_20260830-144344_1a50298d.json` | `golden-p1-0-e00bb52445b0` | structurally valid / true-cold / provenance validated / not acceptance-valid: `output_sha_match=false` |
| `cohort_2026-08-30_19-43-53_2f2c6a` | `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-43-53_2f2c6a/attempt_0.json` | `.v2ctl/runs/run_20260830-144412_1a50298d.json` | `golden-p1-0-950a1e2b42b8` | structurally valid / true-cold / provenance validated / not acceptance-valid: `output_sha_match=false` |
| `cohort_2026-08-30_19-45-14_987d28` | `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-45-14_987d28/attempt_0.json` | `.v2ctl/runs/run_20260830-144541_1a50298d.json` | `golden-p1-0-b6f36e9779ae` | structurally valid / true-cold / provenance validated / not acceptance-valid: `output_sha_match=false` |

Each cohort also has its paired `attempt_0_events.json`, `manifest.json`, and
`summary.json` beside the attempt. The prior
`cohort_2026-08-30_19-41-06_b5d37d` is rejected/superseded and is excluded.

Shared exact identity from the run manifests/attempts:

- app `batch-ra2b-content-truth`; class `ModalRuntimeEntrypointV2`; method
  `run_golden_serial_stream`; profile `golden_p1`; mode `golden_p1_serial`.
- profile-config fingerprint
  `d7ad935d796467111e2fd9ccc8e63f5725a02c8d0748f4767b69de325f48b1f5`;
  `git_head=02f1845a37c7c602bb598afb7e33cab938044e99`.
- v2ctl invocation IDs, in cohort order, are
  `9bb4610569da4ebd8ea4d2c4f14b77c1`,
  `c049cd7a511e464aaea7533b9a2b84e7`, and
  `81e5e1140457493f9463443b824a1850`; the shared v2ctl run fingerprint is
  `1a50298dd394efceb03e8124c30ab106a9de577cec885300a1d4bb2ecac8bc2b`.
- v2ctl deployment fingerprint/hash
  `52166ae5751b50f9acf5b7177e66b2f06efae2fedbdd5632526787a0871530e6`,
  namespace `comfy-modal/deployment/v2`.
- Separate attempt-reported runtime identity/deployment-identity value
  `7501bf53e9bf0a761cc15f3440ab9d3d3d7631c186f0f780180a6f4ffa90c5be`.
  This runtime identity is not substituted for the v2ctl deployment
  fingerprint.
- snapshot identity/target fingerprint
  `77c2390c4625ad631484282440bc8ff63e16b29aeac46b4a93380195bce2c9e0`;
  config identity `c7c5294b590e48310f329410818f220c6e470e7cf1279dd4b0fe45a0900579ae`.
- image `im-QtXh74jYWK6iiXudvSUigE`; provider `CLOUD_PROVIDER_GCP`; region
  `us-central1`; GPU `rtx-pro-6000`; runtime-shape fingerprint
  `f504e296c398bdcb2c4c07e2`; CPU 12; memory 32768; thread policy `TBASE`;
  snapshot model order `O0`.
- workload `conditioning_cache=forced_miss`, `fresh_required=true`, gap 35.0
  seconds, one run; expected SHA
  `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`.

True-cold is observed from the attempt gates: one restore, one request,
`min_containers=0`, single-use containers enabled, post-restore nonce,
restored instance ID, and frozen deployment/snapshot/config identities.

## Direct answers to the 17 questions

1. **Was snapshot capture observed?** Yes, as the startup/frozen snapshot
   callback's paired object: it has `stage=before_capture`; all three content
   proofs have `proven=true`. No request-time capture marker is present.
2. **Which runs are authoritative?** The three diagnostic
   cohort/attempt/run-manifest pairs listed above; all are `golden_p1`, app
   `batch-ra2b-content-truth`, and method `run_golden_serial_stream`. They are
   not Golden acceptance runs because all three failed exact output SHA
   matching.
3. **Were they true-cold?** Yes, structurally, for all three, by the recorded
   attempt gates; exact-output acceptance still failed.
4. **What logical state was present?** Bounded imported module/coordinator
   surfaces, identities, runtime configuration, and a quiescent executor;
   registry state is only inferred from module evidence.
5. **How much memory was resident at capture?** The paired capture manifest
   reports VmRSS `4,909,264 KB = 5,027,086,336 B`; cgroup current was
   `4,968,534,016 B`.
6. **What was physically mapped?** `7,989,510,144 B` virtual mappings:
   `3,795,742,720 B` anonymous and `4,193,767,424 B` file-backed.
7. **Is PSS/smaps composition available?** No. `smaps_rollup=null`; PSS and
   resident anonymous/file-backed splits are UNKNOWN.
8. **What was the largest grouped mapping?** `libcublasLt.so.13`,
   `547,655,680` virtual bytes. The largest category was file-backed mapped
   virtual ranges, not resident memory.
9. **Were model tensors retained in bounded capture surfaces?** No: tensor,
   parameter, model-patcher, QD-owner, reader, worker, and future counts were
   zero; `retained_models.present=false`. This is bounded evidence only.
10. **Was CUDA serialized?** UNKNOWN. CUDA/Torch/native mappings were loaded,
    but direct capture initialized/context/allocator fields were absent.
11. **What did restore do to GPU/CUDA?** `restore_gpu_state` was classified
    `restored`; `initialize_cuda` was invoked and classified `validated`.
    Validation is not a claim of mutation.
12. **Did custom-node synchronization run?** No. All three recorded an exact
    mounted persisted-record match and `snapshot_exact_skip`.
13. **Did runtime/model state remain unchanged?** Runtime reload was skipped on
    an exact generation match. Models were reloaded because generation was
    unknown/no snapshot baseline. Reload is not proof that models were absent
    from Modal's opaque serialized state.
14. **When were models hydrated?** After request entry: CLIP
    `8,044,936,192 B`, UNET `12,309,817,472 B`, VAE `335,278,732 B` H2D.
15. **What was request entry?** A 60-node request with workflow hash check
    enabled and passing, CLIP loader `62`, sampler `1242`, and
    `qwen_3_4b.safetensors` / `lumina2`.
16. **Did output and durability succeed?** Structural output, commit, reopen,
    durability, and seriality ordering succeeded. The configured expected SHA
    did not match the observed SHA in all three attempts.
17. **Is this RA2 acceptance or a production/optimization conclusion?** No.
    It is bounded content/provenance evidence only and does not prove the full
    serialized object graph or production behavior.

## Paired manifest evidence

All three attempts contain the same paired values except boundary timestamps
and per-request identity/timing fields. The capture generation is nonce
`22170afede134ea1a65283795f65ca07`, fingerprint
`45e473ed033f51277264e46ab9efd1524f3fbf6a00abdf098c24863b2675b48e`, with
capture continuity `origin` and restore continuity `continued`.

| Field | Capture: `snapshot_manifest` (`before_capture`) | Restore: `snapshot_manifest_restore` (`first_restored_line`) | Derived delta restore - capture |
|---|---:|---:|---:|
| VmRSS | 4,909,264 KB / 5,027,086,336 B | 1,199,784 KB / 1,228,578,816 B | -3,798,507,520 B |
| VmSize | 7,803,276 KB | 7,817,220 KB | +13,944 KB |
| VmData | 3,828,124 KB | 3,842,068 KB | +13,944 KB |
| cgroup current | 4,968,534,016 B | 1,203,523,584 B | -3,765,010,432 B |
| mapped virtual bytes | 7,989,510,144 B | 8,004,837,376 B | +15,327,232 B |
| anonymous mapped bytes | 3,795,742,720 B | 3,811,069,952 B | +15,327,232 B |
| file-backed mapped bytes | 4,193,767,424 B | 4,193,767,424 B | 0 B |
| mapping counts | 2,662 total / 405 anonymous / 2,257 file-backed | same | 0 / 0 / 0 |
| modules (`sampled=4000`) | 10,595 | 10,600 | **+5** |
| proc status threads | 36 | 36 | 0 |
| Python threads | 2 (`MainThread`, `Thread-1 (thread_inner)`) | same | 0 |
| fd count | 19 | 19 | 0 |

The module-state delta is therefore not “unchanged”: the observed module count
rose by five. The unchanged fields above are only the fields whose paired
values are equal. The selected-root census at each boundary visited 94
objects from 4 roots, was truncated, and reported zero tensor-like objects,
zero model-patcher-like objects, and zero tensor-storage bytes. The fd list
included three eventpoll handles, `/dev/urandom`, three ONNX Runtime database
files, `/tmp/mat-debug-2.log`, one unresolved target, three host handles, and
eight socket handles.

## Logical content tables

| Logical surface | Capture/restore evidence | Classification |
|---|---|---|
| Python/module state | 10,595 modules at capture; 10,600 at first restored line; 4,000 names sampled at each | Observed bounded state; derived +5 delta; full graph UNKNOWN |
| ComfyUI/custom-node registries | Module families and coordinator roots; no direct registry class/display counts or bytes | Inferred only; registry size UNKNOWN |
| Runtime configuration/identity | Frozen config, deployment, snapshot, and runtime-shape identities | Observed provenance; complete serialized retention UNKNOWN |
| Model tensors/parameters | Capture proof: tensor count 0, parameter bytes 0, model-patcher count 0, role counts 0 | Observed bounded absence, not heap/serializer-wide absence |
| Patchers/patch state | No captured patcher; request-time CLIP/UNET/VAE patchers are `ModelPatcherDynamic`, dynamic true | Observed request-time identity |
| QD/readers/workers/futures | Capture proof counts all zero; quiescence checks passive/proven, pending work 0 | Observed bounded quiescence |
| Prompt/conditioning/latent | No explicit nonempty capture evidence; request payload/workflow only | Conditioning and serialized provenance UNKNOWN |
| Workflow/sampler/output | Workflow is request-time; hash passed; sampling/output/durability occur after request | New per request, not captured content evidence |

The raw content proof also reports `snapshot_size_bytes=5041479680`,
`snapshot_size_source=process_rss_pre_capture_resident_memory_proxy`, and
`snapshot_size_is_serialized=false`. It is deliberately excluded from any
serialized-size calculation.

## Physical memory, mappings, threads, fds, and cgroup

`smaps_rollup` is null in both paired manifests. All mapping totals are virtual
ranges. The largest capture grouped paths were `libcublasLt.so.13`
547,655,680 B, `libtorch_cuda.so` 397,942,784 B, `[heap]` 371,642,368 B,
`libtorch_cpu.so` 349,196,288 B, `libcufft.so.12` 291,291,136 B,
`libcusparseLt.so.0` 233,914,368 B, `libnccl.so.2` 197,029,888 B,
`libtriton.so` 180,137,984 B, comfy-kitchen CUDA extension 176,541,696 B,
and `libcusparse.so.12` 164,659,200 B. These values do not identify
serialized ownership.

At capture and first restored line, Torch was `2.13.0+cu130` with intra-op 12
and inter-op 14. Python thread count was 2, proc status count 36, native count
was null, fd count was 19, and there were no children. An idle prefetch
executor was present. These are physical/runtime observations, not Modal
serializer observations.

## Restore stages, model provenance, and CUDA

The three attempts all recorded:

| Stage | Classification | Guard/evidence |
|---|---|---|
| GPU state | `restored` | invoked; restore method successful |
| CUDA initialization | `validated` | invoked; validated, mutation not proven |
| Sage policy | `restored` | restore telemetry |
| Runtime state | `skipped` | `skipped_generation_match`; expected/current `db26cf13b5c3459181c4267dd7c399ab` |
| Models | `reloaded` | `reloaded_generation_unknown`; reason `no_snapshot_baseline`; expected/current empty |
| Custom nodes | `skipped` | `snapshot_exact_skip`; persisted record exact match |
| Snapshot execution seed | `reconstructed` | restore telemetry |

External restore times were 694.575, 919.281, and 799.519 ms; snapshot
restore subspans were 675.8, 899.32, and 780.07 ms. These are observed
per-attempt timings, not a production performance conclusion.

Request-time model provenance was consistent across all three attempts:

- CLIP: `qwen_3_4b.safetensors`, `lumina2`, selected scope
  `qwen3_4b.transformer.model`, 398 tensors, bfloat16, source reads 240,
  398/398 same-storage adoption, and H2D 8,044,936,192 B. One outer CPU
  float32 `qwen3_4b.logit_scale` extra was 4 B.
- UNET: ZImage with prefix `model.`, raw key count 453, source reads 367,
  453 assigned and 453 same-storage, and H2D 12,309,817,472 B.
- VAE: 244 parameters/tensors/views/matches/same-storage, float32 on `cuda:0`,
  source reads 10, and H2D 335,278,732 B.
- CLIP, UNET, and VAE all used `ModelPatcherDynamic` with `is_dynamic=true`;
  the sampling wrapper was installed by `golden_sampling_runner`.

Request-time CUDA allocation checkpoints were before/after skeleton
8,078,491,136 allocated and 8,287,944,704 reserved, then after QD destination
and adoption 20,388,773,376 allocated and 20,598,226,944 reserved. The
reported post-QD, skeleton-peak, and adoption-peak deltas were 0 B. These
allocations and H2D transfers occurred after restore and are not snapshot
content. Direct capture `torch.cuda.is_initialized`, context, and allocator
fields are UNKNOWN; loaded library mappings prove mappings only.

## Output, durability, and scope

All three attempts recorded `true_durable_marked=true`, `reopen_verified=true`,
`commit_reopen_ordering_ok=true`, and zero seriality violations. The observed
output was 3,132,885 B with SHA
`bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce`, reopened
from `output_assets/bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce.png`.
The expected SHA was
`8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`; all
three report `output_sha_match=false`. This does not reclassify the snapshot
content evidence.

This report is not RA2 acceptance, does not fix or classify SHA/publisher/
identity/Sage issues, and does not claim full serialized object-graph or
production-behavior proof.

## Remaining unknowns

- Modal serialized snapshot byte count and opaque serialized object graph.
- Direct CUDA capture initialization/context/allocator state and whether it
  was serialized.
- PSS, smaps resident composition, raw per-mapping smaps, and exhaustive heap
  object graph; the bounded census was truncated.
- Direct registry class/display counts and registry bytes.
- A full manifest after restore completes; only first-restored-line is paired.
- Full serialized provenance of prompt, conditioning, latent, and other
  request-local state.
- Whether observations generalize to production behavior.

## Final completion fields

```text
RA2B_COMPLETE=YES
SNAPSHOT_CAPTURE_OBSERVED=YES
CAPTURE_PROCESS_RSS_BYTES=5027086336
CAPTURE_PROCESS_PSS_BYTES=UNKNOWN
CAPTURE_CGROUP_MEMORY_BYTES=4968534016
CAPTURE_ANONYMOUS_BYTES=3795742720 (bounded virtual mapped anonymous bytes; not resident anonymous)
CAPTURE_FILE_BACKED_BYTES=4193767424 (bounded virtual mapped file-backed bytes; not resident file-backed)
CAPTURE_THREAD_COUNT=36 (proc status; Python census 2; native count unavailable)
CAPTURE_FD_COUNT=19
CAPTURE_MODULE_COUNT=10595
CAPTURE_CUSTOM_NODE_MODULE_COUNT=951 (derived sampled-module family count; not registry size)
CAPTURE_NODE_REGISTRY_SIZE=UNKNOWN
CAPTURE_CUDA_INITIALIZED=UNKNOWN
CAPTURE_CUDA_ALLOCATED_BYTES=UNKNOWN
CAPTURE_MODEL_TENSOR_BYTES=0 (bounded proof/census only)
LARGEST_PHYSICAL_CATEGORY=file-backed mapped virtual ranges: 4193767424 bytes
LARGEST_LOGICAL_RETAINED_SUBSYSTEM=bounded imported Python/ComfyUI/custom-node module surface (10595 modules at capture; module count +5 at first restored line)
SERIALIZED_MODAL_SNAPSHOT_BYTES=UNAVAILABLE
RESTORED_UNCHANGED_SUMMARY=file-backed mapped bytes, mapping counts, proc threads, Python thread names/count, fd count, Torch settings, and quiescent executor surface; module state is not unchanged (+5)
RESTORED_VALIDATED_SUMMARY=GPU/process restore callback, CUDA initialization validation, Sage policy, custom-node exact identity, workflow hash, and durable lifecycle ordering
RESTORED_MUTATED_SUMMARY=module count changed by +5; restore guards selected runtime-state skip/model reload/seed reconstruction; CUDA mutation not proven
RECONSTRUCTED_SUMMARY=snapshot execution seed; model state reloaded after unknown generation/no snapshot baseline
NEW_PER_REQUEST_SUMMARY=workflow/prompt execution, CLIP/UNET/VAE hydration, sampler/output/durability; conditioning serialized provenance UNKNOWN
RAW_LOG=RA2B_SNAPSHOT_RESTORE_CONTENT_RAW_LOG.md
REPORT=RA2B_SNAPSHOT_RESTORE_CONTENT_TRUTH_REPORT.md
```
