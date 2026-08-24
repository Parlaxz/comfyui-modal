# R42B Golden Lifecycle Forensics

## 1. Scope and evidence posture

This is a read-only forensic reconstruction of request `v2-benchmark-0-803bb5dc3fd3`. It uses the current R42 source and the canonical request ledger, summary, and deployment record. Existing worktree modifications were not created or normalized by this audit.

Claim labels:

- **CONFIRMED**: directly present in source or request artifacts.
- **SUPPORTED INFERENCE**: follows from confirmed control flow and ordered telemetry.
- **HYPOTHESIS**: plausible but not uniquely established by the evidence.
- **UNKNOWN**: the instrumentation does not answer the question.
- **UNOBSERVABLE**: the required identity, byte provenance, or physical operation is not recorded.

## 2. Executive verdict

1. **VAE Golden demand missed its legal pre-first-step window.** `golden_vae_schedule_denied` records `attempts=0`, phase `phase2_clip_qd4`, and reason `vae_qd_window_timeout`. The VAE loader then takes the native fallback path after a roughly 15.4-second wait. **CONFIRMED.**
2. **Golden VAE later performs a separate successful QD load.** It reads and transfers 335,278,732 bytes to a CPU destination after `first_sampler_step_proven`. The later VAEDecode still invokes native `ModelPatcher`/`load_models_gpu` handling. Golden-to-native VAE adoption is not implemented or evidenced here, so two logical VAE load paths occur. Physical storage duplication remains cache-dependent. **CONFIRMED / SUPPORTED INFERENCE.**
3. **Golden UNET device preparation succeeds, but Golden model construction/adoption does not.** `unet_device_ready` and `unet_bind` are followed by `golden_unet_construct_fallback` with `reason=model_config_none`. Native model-management loading then occurs. **CONFIRMED.**
4. **The UNET ready-to-demand gap is not Golden QD transfer time.** The device is ready before the approximately 2.796-second interval to `unet_demand_verify`; the measured UNET GPU gate waits only `0.039 ms`. Native model construction/loading or uninstrumented orchestration is the strongest attribution, but its exact sub-phases are not recorded. **CONFIRMED / SUPPORTED INFERENCE.**
5. **The final loader-selection record is misleading.** It reports `effective=golden_qd4` and `fallback_attempted=false` for VAE and UNET despite the canonical fallback events. This is a telemetry/state-assembly defect, not proof that native fallback did not occur. **CONFIRMED.**

## 3. Request and artifact identity

- Request: `v2-benchmark-0-803bb5dc3fd3`.
- Canonical ledger: `comfymodal-data/benchmarks/runs/v2_2026-08-23_05-10-33/run_001_sample.json`.
- Summary: `comfymodal-data/benchmarks/runs/v2_2026-08-23_05-10-33/summary.json`.
- Deployment: `.v2ctl/deployments/deploy_20260823-001218_c3536363.json`.
- Profile: `r42-golden-qd4`.
- `COMFYMODAL_V2_MODEL_PRELOAD=0`. **CONFIRMED.**
- The request ledger contains 85 canonical events and preserves the same request/container identity through the relevant Golden events. **CONFIRMED.**

## 4. Observed lifecycle timeline

Monotonic timestamps are from the canonical ledger. Deltas are calculated from the listed events.

| Event | mono_ns | Evidence and delta |
|---|---:|---|
| `golden_vae_schedule_denied` | 141,286,727,055 | `attempts=0`, `phase2_clip_qd4`, `vae_qd_window_timeout`. **CONFIRMED.** |
| `unet_device_ready` | 152,528,167,784 | `wall_ms=994.658401`, `aggregate_gbps=12.3759247`. **CONFIRMED.** |
| `unet_bind` | 152,529,620,663 | 1.453 ms after device-ready; role `unet`, identity `2407613050b809ffdff18a4ac99af83e`. **CONFIRMED.** |
| `golden_unet_construct_fallback` | 152,537,550,941 | 9.383 ms after first device-ready; reason `model_config_none`. **CONFIRMED.** |
| `graph_gpu_load_start` | 155,319,475,047 | 2,791.307 ms after first device-ready. **CONFIRMED.** |
| `unet_demand_verify` | 155,324,211,056 | 2,796.043 ms after first device-ready; `checked=8`, `result=match`. **CONFIRMED.** |
| UNET GPU gate wait | 155,324,348,976 → 155,324,391,286 | Recorded wait `0.039 ms`; not the source of the multi-second gap. **CONFIRMED.** |
| `graph_gpu_load_end` | 155,368,649,593 | 49.279 ms host duration; 2,840.482 ms after device-ready. **CONFIRMED.** |
| `first_sampler_step_proven` | 156,524,643,137 | 3,996.475 ms after first UNET device-ready. **CONFIRMED.** |
| `vae_qd_submit_start` | 156,545,596,251 | Golden VAE starts after first-step proof; CPU destination, 335,304,388-byte file, 10 ranges. **CONFIRMED.** |
| `vae_qd_source_complete` | 156,623,886,547 | 10 source blocks complete. **CONFIRMED.** |
| `vae_qd_h2d_end` | 156,690,383,726 | 335,278,732 bytes completed. **CONFIRMED.** |
| `vae_device_ready` | 156,693,605,565 | Golden VAE owner publishes readiness. **CONFIRMED.** |
| `vae_decode_start` | 161,068,669,239 | 4,375.064 ms after `vae_device_ready`. **CONFIRMED.** |
| VAE native graph load | 161,069,051,809 → 161,128,445,221 | Starts 0.383 ms after decode-start; `ModelPatcher`, 59.505 ms host duration, invocation 3, `contains_registered_unet=0`. **CONFIRMED.** |
| `vae_decode_end` | 161,519,529,636 | Decode duration `450.862 ms`. **CONFIRMED.** |

The summary's `t4c_vae_load_start`/`t4c_vae_load_end` duration is approximately `15.415 s`. The canonical schedule-denial event has `attempts=0`; it is a window/deadline miss, not a failed Golden source attempt. **CONFIRMED.**

## 5. VAE lifecycle

### 5.1 Initial VAELoader request

`comfyapp.py:19022-19101` patches `VAELoader.load_vae` and retains an actual-load future when one exists. `comfymodal_runtime/model_preload.py:4102-4163` wraps `load_torch_file` for VAE/CLIP roles. The wrapper calls `vae_demand_load`; if that path returns no usable result, it invokes the original native loader. **CONFIRMED.**

The Golden VAE demand is started before the first sampler-step proof, but `resource_scheduler.py:18-21,93-157` denies VAE-QD while the protected CLIP/sampling window is active. The request event records the denial after the 15-second window with zero attempts. The native loader therefore remains the immediate VAELoader fallback. **CONFIRMED.**

### 5.2 Later Golden VAE worker

`golden_runtime_bridge.py:426-480` starts the VAE worker after first-step proof. The request then records a CPU-targeted QD read of 335,278,732 bytes, 10 source blocks, 268,435,456 pinned bytes, and a successful `vae_device_ready`. **CONFIRMED.**

`model_owner.py:105-195` provides join/adopt ownership and prevents duplicate live Golden producers. This prevents a second Golden producer; it does not attach the Golden payload to an already-created native VAE module. **CONFIRMED / SUPPORTED INFERENCE.**

### 5.3 Decode and duplicate work

`modal_app.py:14517-14547` joins the VAE owner before native decode. The join is not a native-module weight binding operation. At decode, the ledger records a separate native `ModelPatcher` graph load with `contains_registered_unet=0`, `gpu_request_invocation_count=3`, and a 9.10-GB memory requirement. **CONFIRMED.**

Therefore:

- Native VAE fallback after the initial schedule denial is **CONFIRMED** by source control flow.
- Later Golden VAE source/H2D work is **CONFIRMED** by the QD events.
- Native VAE model-management work after Golden VAE readiness is **CONFIRMED** by the decode-side graph events.
- A second physical disk read is **UNKNOWN**: the ledger does not provide cache-hit/storage-byte provenance for the native path.

## 6. UNET lifecycle

`unet_fastsafetensors.py:1285-1589` separates source preparation from the device commit gate. `unet_meta_direct.py:213-359` uses bounded `preadv` waves, reusable pinned staging slots, and copies into preallocated CUDA parameters. `golden/contracts.py:394-400` shows that `PreparedSource` carries identity/statistics rather than retaining source buffers. **CONFIRMED.**

The request reaches `unet_device_ready`, publishes a role/identity binding, and emits a second readiness marker. This proves successful Golden source preparation and device commit for the Golden owner. It does not prove that the native Comfy model object adopted those CUDA parameters. **CONFIRMED.**

Immediately afterward, the request emits `golden_unet_construct_fallback` with `model_config_none`. The current bridge/model-preload path falls through to native model construction when Golden construction cannot resolve a model config. **CONFIRMED.**

The later `unet_demand_verify` reports eight checked tensors and `result=match`. This proves an identity/shape/device verification succeeded; it is not proof of ownership adoption or of zero native source work. **CONFIRMED / SUPPORTED INFERENCE.**

Native graph model management then runs:

- `graph_gpu_load_start` has `contains_registered_unet=1`, invocation 2, and a 28.75-GB memory requirement.
- `model_patcher_load_breakdown` reports 451 patch weights and 39.184 ms wall time.
- `graph_gpu_load_end` reports 49.279 ms host duration.

Native construction/fallback and native ModelPatcher management after Golden UNET readiness are therefore **CONFIRMED**. A second full physical source read or a second full H2D is **UNKNOWN**. The request's `commit_read_storage_bytes=0` and `commit_cache_served=null` fields are not proof of no native I/O; they indicate that the relevant native provenance was not measured.

## 7. Role resolution and `matched_role=none`

The role matcher in `model_preload.py:4117-4138` contains VAE and CLIP handling but no UNET branch. UNET publication instead uses the separate `note_role_source("unet", ...)` path, and Golden binding is resolved through `golden_runtime_bridge.py:232-295,351-374` and the manifest identity.

Thus `matched_role=none` for a UNET checkpoint is an expected instrumentation blind spot, not evidence that UNET Golden ownership failed. **CONFIRMED from source.**

The exact request ledger does not provide a complete per-call `matched_role` trace for every native UNET read. Whether a particular native read saw a path mismatch is **UNOBSERVABLE**. Raw path matching also lacks a universal realpath/case/slash canonicalization layer, so mount-prefix or spelling differences remain a supported risk even though this request's `unet_bind` and `unet_demand_verify` identities match.

## 8. Attribution of the UNET gap

The interval from first `unet_device_ready` to `unet_demand_verify` is `2,796.043 ms`.

- Golden device commit is already complete at the interval's start. **CONFIRMED.**
- Golden UNET construction fallback occurs 9.383 ms after readiness. **CONFIRMED.**
- The graph load begins 2,791.307 ms after readiness. **CONFIRMED.**
- The measured GPU gate wait is only 0.039 ms. **CONFIRMED.**
- The native graph load itself is only about 49.279 ms once entered. **CONFIRMED.**

The strongest attribution is native model-config/model-construction and loader orchestration between Golden readiness and graph demand. **SUPPORTED INFERENCE.** The exact split among model-config lookup, native checkpoint parsing, ModelPatcher construction, Python scheduling, and any cache activity is **UNKNOWN** because those phases have no request-correlated spans.

## 9. Fallback and degradation semantics

Relevant fallback emissions include:

- VAE schedule/window denial and VAE demand fallback in `golden_runtime_bridge.py:695-813`.
- UNET manifest/commit/owner join fallback in `golden_runtime_bridge.py:351-395,489-546`.
- UNET construction fallback in `model_preload.py:4008-4093`.
- Native VAEDecode join/load seam in `modal_app.py:14517-14547`.

`clear_role_fallback_degradations()` at `golden_runtime_bridge.py:661-679` clears several ordinary fallback, owner-timeout, manifest-unavailable, and `golden_unet_commit_not_ready` reasons. It does not generically erase every distinct timeout/fallback reason, including the exact commit-gate timeout spelling. Success clearing must be request- and role-specific; a later Golden worker success must not erase a terminal native-construction fallback.

For this request, the loader-selection summary reports `fallback_attempted=false`, empty fallback reasons, and `effective=golden_qd4` for VAE and UNET. That summary conflicts with the canonical `golden_vae_schedule_denied` and `golden_unet_construct_fallback` events. **CONFIRMED telemetry inconsistency.** Final “nominal” selection should not be treated as proof that all native fallbacks were avoided.

## 10. Duplicate-work determination

| Work | Determination |
|---|---|
| Second Golden producer for the same role | **CONFIRMED prevented** by owner registry/join semantics. |
| Native VAE path after pre-first-step Golden denial | **CONFIRMED occurred** by wrapper fallback control flow. |
| Later Golden VAE read/H2D | **CONFIRMED occurred** from QD events. |
| Native VAE model-management load after Golden VAE readiness | **CONFIRMED occurred** at VAEDecode. |
| Golden UNET device preparation | **CONFIRMED occurred**. |
| Native UNET construction/adoption fallback | **CONFIRMED occurred** (`model_config_none`). |
| Native UNET ModelPatcher load/management | **CONFIRMED occurred**. |
| Second physical UNET source read | **UNKNOWN**. |
| Second full UNET H2D | **UNKNOWN**. |
| Storage-cache hit/miss for native paths | **UNOBSERVABLE**. |

## 11. Recommended remediation priorities

1. Make VAE demand denial explicit in loader selection and either delay native VAE construction or make the later Golden payload bindable to the native VAE object; do not report “Golden effective” while both paths run.
2. Complete UNET model-config construction/adoption from the verified Golden owner, or explicitly mark the native fallback as degraded and measure its cost.
3. Add request/role-correlated spans around native model construction, `load_torch_file`, ModelPatcher construction, and native H2D/storage provenance.
4. Make fallback state identity-aware and monotonic: provisional waits may be superseded by verified same-role success, but terminal native fallback must remain visible.
5. Add canonical path normalization for role publication/matching and retain manifest identity as the authoritative cross-mount key.
6. Reconcile `loader_selection` with actual fallback events before using it as a benchmark verdict.

## 12. Final conclusion

The request did exercise Golden QD paths successfully for UNET device preparation and the later VAE worker, but it did not provide an end-to-end native-module adoption path. VAE scheduling caused a native fallback before first-step proof, followed by separate Golden VAE work and native decode-side model management. UNET Golden commit succeeded, followed by Golden construction fallback and native ModelPatcher work. The artifacts establish duplicate logical lifecycle work and a telemetry mismatch; they do not establish the exact number of physical storage reads or full-device copies.
