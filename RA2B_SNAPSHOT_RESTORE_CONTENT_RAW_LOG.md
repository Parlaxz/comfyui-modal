# RA2B snapshot/restore content raw log

## Scope and authority

This is a bounded, human-readable extraction of the authoritative paired
diagnostic artifacts. It is evidence-only and is not a replacement for the
raw JSON/event streams. The observation set is the three newly completed serial
Golden cohorts below. All three attempts are structurally `valid=true`,
`true_cold=true`, `dnf=false`, and `provenance_validation_status=validated`;
none is Golden acceptance-valid because all three have
`output_sha_match=false`. The configured output hash mismatch is recorded
separately; it is not by itself a snapshot-content failure.

The prior `cohort_2026-08-30_19-41-06_b5d37d` cohort is superseded/rejected and
is not used here because it was post-snapshot/unusable.

The three retained attempts have empty `last_snapshot_capture_request_id` and
`last_snapshot_capture_at` fields; no request-time snapshot capture was
recorded in this set.

Authoritative attempt/event/cohort paths:

- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-43-23_b37a7c/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-43-23_b37a7c/attempt_0_events.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-43-23_b37a7c/manifest.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-43-23_b37a7c/summary.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-43-53_2f2c6a/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-43-53_2f2c6a/attempt_0_events.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-43-53_2f2c6a/manifest.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-43-53_2f2c6a/summary.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-45-14_987d28/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-45-14_987d28/attempt_0_events.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-45-14_987d28/manifest.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-45-14_987d28/summary.json`

Run-manifest paths:

- `.v2ctl/runs/run_20260830-144344_1a50298d.json`
- `.v2ctl/runs/run_20260830-144412_1a50298d.json`
- `.v2ctl/runs/run_20260830-144541_1a50298d.json`

## Cohort, identity, and provenance record

| Cohort | Request ID | v2ctl invocation ID | Run fingerprint | Attempt result | Output SHA result |
|---|---|---|---|---|---|
| `cohort_2026-08-30_19-43-23_b37a7c` | `golden-p1-0-e00bb52445b0` | `9bb4610569da4ebd8ea4d2c4f14b77c1` | `1a50298dd394efceb03e8124c30ab106a9de577cec885300a1d4bb2ecac8bc2b` | structurally valid, true-cold, provenance validated; not acceptance-valid | `output_sha_match=false` |
| `cohort_2026-08-30_19-43-53_2f2c6a` | `golden-p1-0-950a1e2b42b8` | `c049cd7a511e464aaea7533b9a2b84e7` | same | structurally valid, true-cold, provenance validated; not acceptance-valid | `output_sha_match=false` |
| `cohort_2026-08-30_19-45-14_987d28` | `golden-p1-0-b6f36e9779ae` | `81e5e1140457493f9463443b824a1850` | same | structurally valid, true-cold, provenance validated; not acceptance-valid | `output_sha_match=false` |

The exact shared request/deployment/profile/runtime identity from the run
manifests and attempts is:

- app `batch-ra2b-content-truth`; class `ModalRuntimeEntrypointV2`; method
  `run_golden_serial_stream`; mode `golden_p1_serial`.
- profile `golden_p1`; profile-config fingerprint
  `d7ad935d796467111e2fd9ccc8e63f5725a02c8d0748f4767b69de325f48b1f5`;
  source `git_head=02f1845a37c7c602bb598afb7e33cab938044e99`.
- v2ctl deployment fingerprint/hash
  `52166ae5751b50f9acf5b7177e66b2f06efae2fedbdd5632526787a0871530e6`, in
  namespace `comfy-modal/deployment/v2`.
- Attempt-reported runtime identity/deployment-identity value
  `7501bf53e9bf0a761cc15f3440ab9d3d3d7631c186f0f780180a6f4ffa90c5be`.
  This is retained as a separate runtime identity and is not substituted for
  the v2ctl deployment fingerprint.
- snapshot identity/target fingerprint
  `77c2390c4625ad631484282440bc8ff63e16b29aeac46b4a93380195bce2c9e0`;
  config identity `c7c5294b590e48310f329410818f220c6e470e7cf1279dd4b0fe45a0900579ae`.
- image `im-QtXh74jYWK6iiXudvSUigE`; provider `CLOUD_PROVIDER_GCP`; region
  `us-central1`; GPU `rtx-pro-6000`; runtime-shape fingerprint
  `f504e296c398bdcb2c4c07e2`; thread policy `TBASE`; CPU request `12`; memory
  request `32768`; snapshot model order `O0`.
- Every attempt has `restore_count=1`, `request_count=1`, `min_containers=0`,
  single-use containers enabled, all frozen deployment/snapshot/config
  identities present, and a post-restore nonce. The true-cold basis is the
  exact attempt basis string, not a timing inference.
- Workload: `conditioning_cache=forced_miss`, `fresh_required=true`, gap
  `35.0` seconds, run count `1`; expected output SHA
  `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`.

Per-attempt runtime identity and timings:

| Cohort | Restore session | Restored instance | Container session/task | Post-restore nonce | Duration ms | External restore ms |
|---|---|---|---|---|---:|---:|
| `19-43-23_b37a7c` | `5da29cc85f914feda7fb316c10c7055b` | `1f382973d16b4bf997032e3294a0f273` | `f989e80a927f4db6` / `ta-01M1A35CVFG9379S1MQSB1AEQR` | `78372542002e47d89a85774826ff3655` | 19489.343 | 694.575 |
| `19-43-53_2f2c6a` | `6c2083277fb94fafa150ee01651319a0` | `250a23aa9dea443b8074291a90e33055` | `f989e80a927f4db6` / `ta-01M1A369NVHC5R8BSBFMQSNV0R` | `a2d2cbb518fd4ce6b4b80ac1e8b37fb3` | 18055.818 | 919.281 |
| `19-45-14_987d28` | `2f107584402c45439fc6be8749da5743` | `b26027becfd24daa915cf212dacabd24` | `f989e80a927f4db6` / `ta-01M1A38SZ4RJ5BV522X5JJXRHR` | `0041e64142414e2db7b58cddb2984aaf` | 26013.964 | 799.519 |

## Paired snapshot manifests

The following are the actual paired fields, not reconstructions from memory
proxies. The capture object is `snapshot_manifest` with
`stage=before_capture`; the restore object is `snapshot_manifest_restore` with
`stage=first_restored_line`. Their generation nonce and fingerprint are shared
across all three attempts:

- nonce `22170afede134ea1a65283795f65ca07`
- fingerprint `45e473ed033f51277264e46ab9efd1524f3fbf6a00abdf098c24863b2675b48e`
- capture continuity `origin`; restore continuity `continued`.

| Field | `snapshot_manifest` / `before_capture` | `snapshot_manifest_restore` / `first_restored_line` |
|---|---:|---:|
| VmSize KB | 7,803,276 | 7,817,220 |
| VmRSS KB | 4,909,264 | 1,199,784 |
| VmData KB | 3,828,124 | 3,842,068 |
| Proc status threads | 36 | 36 |
| cgroup `memory_current_bytes` | 4,968,534,016 | 1,203,523,584 |
| total mappings | 2,662 | 2,662 |
| anonymous mappings | 405 | 405 |
| file-backed mappings | 2,257 | 2,257 |
| other mappings | 0 | 0 |
| mapped bytes (virtual) | 7,989,510,144 | 8,004,837,376 |
| anonymous bytes (virtual) | 3,795,742,720 | 3,811,069,952 |
| file-backed bytes (virtual) | 4,193,767,424 | 4,193,767,424 |
| modules (`sampled=4000`) | 10,595 | 10,600 |
| Python threads | `MainThread`, `Thread-1 (thread_inner)`; count 2 | same; count 2 |
| native thread count | `null` | `null` |
| fd count | 19 | 19 |
| children | `[]` | `[]` |
| Torch | `2.13.0+cu130`, intra-op 12, inter-op 14 | same |
| retained models | `present=false` | `present=false` |
| smaps rollup | `null` | `null` |

The bounded selected-root census at both paired boundaries visited 94 objects
from 4 selected roots at depth 2 with node limit 128 and child limit 32; it
was truncated. It reported roots 83 and coordinators 11, zero tensor-like
objects, zero model-patcher-like objects, and zero tensor-storage bytes.
One idle `torch.utils._functools._prefetch_executor` was present, and the
quiescence proof reported no pending work.

The bounded top virtual mapping paths at capture were: `libcublasLt.so.13`
547,655,680 B; `libtorch_cuda.so` 397,942,784 B; `[heap]` 371,642,368 B;
`libtorch_cpu.so` 349,196,288 B; `libcufft.so.12` 291,291,136 B;
`libcusparseLt.so.0` 233,914,368 B; `libnccl.so.2` 197,029,888 B;
`libtriton.so` 180,137,984 B; the comfy-kitchen CUDA extension 176,541,696 B;
and `libcusparse.so.12` 164,659,200 B. These are virtual mapping ranges,
not RSS, PSS, or serialized snapshot bytes. `smaps_rollup=null`, so PSS and
resident anonymous/file-backed composition are unavailable.

## Content proof and serialized boundary

All three content proofs are passive and `proven=true`, with
`surface_count=4`, `tensor_count=0`, `parameter_bytes=0`,
`model_patcher_count=0`, `qd_owner_count=0`, `open_payload_reader_count=0`,
`preload_worker_count=0`, and `future_count=0`; all role records for UNET,
CLIP, and VAE are zero. `retained_models.present=false` is also observed.
This is bounded selected-surface evidence only.

The raw diagnostic field is `serialized_snapshot_bytes="UNOBSERVABLE"`.
The content proof's `snapshot_size_bytes=5041479680` is sourced from a
`process_rss_pre_capture_resident_memory_proxy` and explicitly has
`snapshot_size_is_serialized=false`; it must not be used as serialized size.
The report completion convention is therefore
`SERIALIZED_MODAL_SNAPSHOT_BYTES=UNAVAILABLE`.

## Restore decisions

The same stage classifications and guard decisions were observed in all three
attempts:

```json
{
  "restore_stage_classifications": {
    "restore_gpu_state": "restored",
    "initialize_cuda": "validated",
    "sage_policy": "restored",
    "reload_runtime_state": "skipped",
    "reload_models": "reloaded",
    "sync_custom_nodes": "skipped",
    "snapshot_execution_seed": "reconstructed"
  },
  "restore_generation_guard_decisions": {
    "reload_runtime_state": {
      "decision": "skipped_generation_match",
      "reason": "exact_match",
      "expected_generation": "db26cf13b5c3459181c4267dd7c399ab",
      "current_generation": "db26cf13b5c3459181c4267dd7c399ab"
    },
    "reload_models": {
      "decision": "reloaded_generation_unknown",
      "reason": "no_snapshot_baseline",
      "expected_generation": "",
      "current_generation": ""
    },
    "sync_custom_nodes": {
      "decision": "snapshot_exact_skip",
      "reason": "exact_match",
      "current_source": "persisted_record",
      "identity_read_reason": "mounted_volume_record"
    }
  }
}
```

The restore callback returned success. `restore_gpu_state` and CUDA
initialization were invoked; CUDA initialization is classified as validated,
not as a proven mutation. Runtime state was not reloaded because its
generation matched. Models were reloaded because the model generation was
unknown/no snapshot baseline. That reload is not proof that models were
absent from Modal's opaque serialized state. Custom-node synchronization did
not run because the mounted persisted record exactly matched.

## Request-time model, tensor, patch, registry, and CUDA evidence

The request setup in every attempt had 60 nodes, workflow hash checking
enabled and not bypassed, actual and expected workflow SHA-256
`e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5`, CLIP
loader `62`, sampler `1242`, CLIP `qwen_3_4b.safetensors`, type `lumina2`,
folder `text_encoders`.

| Request surface | Observed request-time evidence | Capture/restore content conclusion |
|---|---|---|
| CLIP tensor/model | 398 published/adopted tensors; 398 views, 398 matched, 398 same-storage, 0 copied; bfloat16; selected scope `qwen3_4b.transformer.model`; source reads 240; H2D 8,044,936,192 B | No bounded capture tensors; request-time hydration |
| UNET tensor/model | ZImage, prefix `model.`, raw key count 453; 453 assigned and 453 same-storage; 0 copied; source reads 367; H2D 12,309,817,472 B | No bounded capture tensors; request-time hydration |
| VAE tensor/model | 244 parameters/tensors/views/matches/same-storage; 0 copied; CUDA float32; source reads 10; H2D 335,278,732 B | No bounded capture tensors; request-time hydration |
| Patcher/patch state | CLIP, UNET, and VAE patcher class `ModelPatcherDynamic`, `is_dynamic=true`; sampling wrapper installed with source `golden_sampling_runner` | Request-time patcher identity; no captured model patcher |
| Registry/custom-node state | Module samples and coordinator roots observed; exact custom-node sync skip observed | Direct registry class/display counts and serialized registry bytes are UNKNOWN |

The CLIP outer extra was one CPU float32 `qwen3_4b.logit_scale`, 4 B. The
request-time CUDA allocation checkpoints were identical across attempts:
before/after skeleton allocated 8,078,491,136 B and reserved 8,287,944,704 B;
after QD destination and after adoption allocated 20,388,773,376 B and
reserved 20,598,226,944 B. Post-QD, skeleton-peak, and adoption-peak deltas
were all 0 B. These are request allocations, not snapshot content.

Direct capture CUDA initialized/context/allocator fields were not recorded.
Loaded CUDA/Torch/Triton/Sage/comfy-kitchen mappings prove loaded mappings
only; they do not prove CUDA state was serialized. Capture CUDA state is
UNKNOWN.

## Durability and output

All three attempts recorded `true_durable_marked=true`,
`reopen_verified=true`, `commit_reopen_ordering_ok=true`, and zero seriality
violations. The observed output SHA was
`bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce`, with
3,132,885 bytes, committed/reopened at
`output_assets/bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce.png`.
It differs from the configured expected SHA. This is an output exactness
result only and is not evidence of snapshot-content failure.

## Remaining unknowns and limits

- Modal serialized byte count and the opaque Modal serialized object graph.
- Whether CUDA context/allocator state was serialized; direct capture CUDA
  fields were absent.
- PSS, smaps rollup, per-mapping resident composition, and complete mappings
  beyond the bounded grouped list.
- Direct ComfyUI/custom-node registry counts, registry bytes, and full Python
  heap/object graph; the selected-root census was truncated.
- A full manifest at restore completion (only the first-restored-line
  manifest is paired with the before-capture manifest).
- Full provenance of prompt/conditioning/latent state inside the serialized
  object graph.
- These three runs do not prove the full serialized object graph or production
  behavior.
