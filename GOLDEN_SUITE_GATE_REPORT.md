# Golden Suite Gate Report

**Evidence date:** 2026-08-27 (UTC)  
**Evidence set:** `golden-p3-ComfyUI` / `phase_p1_serial_golden_v1`  
**Report ownership:** this report only; no other repository file is changed by this report.

## 1. Objective and scope

This report records the final Golden P1 structural gate and its five-run confirmation, together with every cohort manifest in the relevant 19:00 UTC hour. The scope is the deployed serial workflow `run_golden_serial_stream`, its exact output and durability contract, loader/snapshot identity evidence, telemetry, and the diagnostics from earlier failed gates.

The evidence is persisted outside this Git checkout under:

```text
C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal
```

The three contextual root reports inspected were `E40_CANONICAL_RUNTIME_TRUTH_AND_CLEANUP_REPORT.md`, `R41_DETERMINISTIC_GOLDEN_QD4_PIPELINE_REPORT.md`, and `R41_E40_RECONCILIATION_MANIFEST.md`.

## 2. Final verdict

**PASS — final structural gate valid, followed by five successful confirmation runs.**

The final gate has `gate_valid=true`, `reasons=[]`, `backend_ok=true`, exit code `0`, and `provenance_validation_status=validated`. All nine 19:00-hour cohorts have one valid attempt, no DNF, no failure reasons, and the same output SHA. The five cohorts after the final gate are the confirmation set.

This is a structural/durability pass, not a true-cold pass: every attempt explicitly reports `true_cold=false` because remote/container identity tokens were not present.

## 3. Exact commit and identity

| Identity | Exact value | Evidence / qualification |
|---|---|---|
| Repository checkout commit at report creation | `8b385860824b52cf84b74f2c22bf65bbe07dcce6` | Local checkout `git log -1`; message `Aug 26 complete Golden Suite First Working space` |
| Gate-embedded `git_head` | `unknown` | Exact gate/config value; therefore the gate does not independently attest the Git commit |
| Deployed ComfyUI commit | `f49bdb655707b97952dcef40e12e5af1f08d2007` | Temp `.deployed_state.json`; `comfyui_core_match=1`, version `0.24.0` |
| Custom-node deployment generation | `e5b3c03280a09da4998c08b02225e2d2` | Temp `.deployed_state.json` |
| Deployment combined hash | `dacc5d6c022a85e4127507928653a0a74219e3383e03674a8708d3322f544178` | `.deployed_state.json` and every cohort manifest |
| Deployment fingerprint | `3e487cc21090879c1efa4c4c0979388249c29211162928cd73ca50396ce774a2` | Final gate and deployment records |
| Runtime-shape fingerprint | `f504e296c398bdcb2c4c07e2` | `.deployed_state.json` |
| Overall dependency hash | `e2e2af478360fadb6ac35d5dc87d3f2b1668363e9c17109875f55ba9aa9917cc` | `.deployed_state.json` |

## 4. Environment and workflow identity

### 4.1 Runtime and control-plane scalars

| Field | Value |
|---|---|
| Profile | `golden_p1` |
| Profile config fingerprint | `99b974a3b0a256ae2c9cd46158a74cd1a58bcfbe31f5d0364a0b7ec95adcea53` |
| Run fingerprint | `b2f49680a5f7ed058908019e9d552f32ce3aacf27038ba252efe7a5b678e7598` |
| Target app | `stable-modal-comfy-v2-golden-p1` |
| Target class | `ModalRuntimeEntrypointV2` |
| Target method | `run_golden_serial_stream` |
| GPU | `rtx-pro-6000` / `NVIDIA RTX PRO 6000 Blackwell Server Edition` |
| CPU request | `12` |
| Memory request | `32768 MB` |
| Scaledown window | `4` |
| Minimum containers | `0` |
| Runtime override policy | `forbid` |
| Single-use containers | `1` |
| Thread policy | `TBASE` |
| Snapshot model order | `O0` |
| VAE policy | `v1` |
| UNET activation | `late` |
| VAE activation | `late` |
| CLIP QD | `4` |
| CLIP QD block | `32 MiB` |
| CLIP launch policy | `restore_earliest` |
| Golden dynamic VRAM observed | `true` |
| Core patcher dynamic observed | `true` |
| Conditioning cache flag | `1` |
| Workflow-hash check | disabled and bypassed (`enabled=false`, `bypassed=true`) |
| Fresh required | `true` |
| Dirty hashes | `{}` |
| Git dirty | `false` |
| Gate provenance | `validated` |

### 4.2 Final `deploy_inputs.deploy_flags` scalar inventory

| Flag | Value | Flag | Value |
|---|---:|---|---:|
| `COMFYMODAL_MINIMAL_RESTORE` | `1` | `COMFYMODAL_V2_ATOMIC_PROFILE` | `0` |
| `COMFYMODAL_V2_BASELINE_CPU_REQUEST` | `12` | `COMFYMODAL_V2_BASELINE_MEMORY_REQUEST` | `32768` |
| `COMFYMODAL_V2_C9QD_EXTRAS` | `0` | `COMFYMODAL_V2_CHECKPOINT_PREWARM` | `0` |
| `COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB` | `64` | `COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS` | `4` |
| `COMFYMODAL_V2_CLEAN_LANE` | `0` | `COMFYMODAL_V2_CLIP_COLD_FORENSICS` | `0` |
| `COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST` | `0` | `COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA` | `0` |
| `COMFYMODAL_V2_CLIP_CONDITIONING_CACHE` | `1` | `COMFYMODAL_V2_CLIP_FAST_HYDRATION` | `0` |
| `COMFYMODAL_V2_CLIP_FP32_CAST_ONCE` | `0` | `COMFYMODAL_V2_CLIP_QD_ARTIFACT` | `""` |
| `COMFYMODAL_V2_CLIP_QD_BLOCK_MIB` | `32` | `COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY` | `restore_earliest` |
| `COMFYMODAL_V2_CLIP_QD_QD` | `4` | `COMFYMODAL_V2_CLIP_QD_READER` | `0` |
| `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS` | `1` | `COMFYMODAL_V2_CLIP_STAGED_HYDRATION` | `0` |
| `COMFYMODAL_V2_CLOUD` | `""` | `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT` | `0` |
| `COMFYMODAL_V2_CPU_REQUEST` | `12` | `COMFYMODAL_V2_CRITICAL_GPU_COORDINATION` | `0` |
| `COMFYMODAL_V2_CRITICAL_PATH_LEDGER` | `1` | `COMFYMODAL_V2_DEEP_MODEL_DIAG` | `0` |
| `COMFYMODAL_V2_E27_FORENSICS` | `0` | `COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT` | `1024` |
| `COMFYMODAL_V2_E31_FORENSICS` | `0` | `COMFYMODAL_V2_E31_FORWARD_PROFILE` | `0` |
| `COMFYMODAL_V2_E37_CLEAN_LANE` | `0` | `COMFYMODAL_V2_ENV_PROFILE` | `inherit` |
| `COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT` | `0` | `COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS` | `0` |
| `COMFYMODAL_V2_EVICT_RETAIN_ROLE` | `none` | `COMFYMODAL_V2_FAST_COLD_ORCHESTRATION` | `0` |
| `COMFYMODAL_V2_FULL_TRACE` | `0` | `COMFYMODAL_V2_GANTT_TELEMETRY` | `0` |
| `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM` | `1` | `COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK` | `0` |
| `COMFYMODAL_V2_GPU_FAST_RETURN` | `1` | `COMFYMODAL_V2_INPUT_TYPES_WARM` | `1` |
| `COMFYMODAL_V2_MEMORY_MB` | `32768` | `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET` | `1` |
| `COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS` | `0` | `COMFYMODAL_V2_PAGEFAULT_TRACKING` | `0` |
| `COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE` | `1` | `COMFYMODAL_V2_PREFILL_LANES` | `critical` |
| `COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET` | `0` | `COMFYMODAL_V2_REGION` | `""` |
| `COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST` | `1` | `COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS` | `0` |
| `COMFYMODAL_V2_SCOPED_CUDA_READINESS` | `0` | `COMFYMODAL_V2_SINGLE_USE_CONTAINERS` | `1` |
| `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION` | `0` | `COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET` | `0` |
| `COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER` | `O0` | `COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION` | `0` |
| `COMFYMODAL_V2_STAGED_SAFETENSORS` | `0` | `COMFYMODAL_V2_STAGED_SOURCE_ORDER` | `0` |
| `COMFYMODAL_V2_THREAD_POLICY` | `TBASE` | `COMFYMODAL_V2_UNET_ACTIVATION_MODE` | `late` |
| `COMFYMODAL_V2_UNET_FASTSAFETENSORS` | `0` | `COMFYMODAL_V2_UNET_FORENSICS` | `0` |
| `COMFYMODAL_V2_VAE_ACTIVATION_MODE` | `late` | `COMFYMODAL_V2_VAE_POLICY` | `v1` |
| `COMFYMODAL_V2_VAE_SNAPSHOT` | `0` | `V2_D10_INTEGRATION_VALIDATION` | `0` |
| `V2_D6_FASTPATH_VALIDATION` | `0` | `V2_E10_BUCKET_FIRST_VALIDATION` | `0` |
| `V2_E19_FINAL_COLD_LOADER` | `0` | `V2_E25_VALIDATION` | `0` |
| `V2_E26_VALIDATION` | `0` | `V2_E28_VALIDATION` | `0` |

### 4.3 Workflow scalars

| Field | Value |
|---|---|
| Workflow source path | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\latest_benchmark_workflow.json` |
| Workflow hash | `14f815f1916e075ae79de7325681f6b0ec2216b8ad86c45e9bfa18f6388f5ea9` |
| Prompt SHA-256 | `14f815f1916e075ae79de7325681f6b0ec2216b8ad86c45e9bfa18f6388f5ea9` |
| Workflow captured-at scalar | `1787806519.2959576` |
| Expected output SHA | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| Node count | `60` |
| CLIP node | `62` |
| Sampler node | `1242` |
| CLIP model | `qwen_3_4b.safetensors` |
| CLIP type | `lumina2` |
| CLIP folder | `text_encoders` |

## 5. Successful gate details

| Gate field | Value |
|---|---|
| Gate artifact | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\.v2ctl\gates\gate_20260827-193031_b2f49680.json` |
| Created | `2026-08-27T19:30:31.224187+00:00` |
| `gate_valid` | `true` |
| Reasons | `[]` |
| Request ID | `golden-p1-0-950b25c5dcb6` |
| Backend exit code | `0` |
| Backend OK | `true` |
| Fresh required | `true` |
| Output SHA | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| Expected SHA | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| Provenance validation | `validated` |
| v2ctl invocation ID | `b01173e4a08a4b75b1b546c69b6bb3e0` |
| Selected run path | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-30-10_22e884\attempt_0.json` |
| Selected summary path | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-30-10_22e884\summary.json` |

The final gate run completed the ordered Golden stages: restore, request setup, CLIP load, CLIP forward, UNET load, sampler preparation, VAE load, sampling, sampler tail, VAE decode, output, durable commit, and teardown. The outer result event count is `1`; internal event/telemetry records are persisted in the attempt event file.

## 6. All cohorts in the relevant 19:00 UTC hour

All nine matching manifests are listed. The first four are pre-confirmation observations (the 19:30:10 cohort is the successful gate-selected run); the last five are the confirmation set after that gate.

| Cohort | Role | Started UTC | Completed UTC | Attempts | Valid | Invalid | DNF | Gap s | Strict serial | Request ID | Duration ms | Output SHA |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---:|---|
| `cohort_2026-08-27_19-23-57_0bf24f` | pre-gate | 19:23:57.625270 | 19:24:26.044862 | 1 | 1 | 0 | 0 | 35.0 | true | `golden-p1-0-ec699e817ca5` | 28112.707 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| `cohort_2026-08-27_19-26-34_169482` | pre-gate | 19:26:34.214732 | 19:26:55.486406 | 1 | 1 | 0 | 0 | 35.0 | true | `golden-p1-0-9f827b7f51b6` | 20919.117 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| `cohort_2026-08-27_19-28-12_893726` | pre-gate | 19:28:12.582558 | 19:28:33.269405 | 1 | 1 | 0 | 0 | 35.0 | true | `golden-p1-0-e65c62f8c6fe` | 20365.684 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| `cohort_2026-08-27_19-30-10_22e884` | final gate | 19:30:10.144667 | 19:30:30.673187 | 1 | 1 | 0 | 0 | 35.0 | true | `golden-p1-0-950b25c5dcb6` | 20187.404 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| `cohort_2026-08-27_19-30-40_86aa19` | confirmation 1/5 | 19:30:40.142112 | 19:31:02.896266 | 1 | 1 | 0 | 0 | 35.0 | true | `golden-p1-0-99fc4efadce1` | 22434.198 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| `cohort_2026-08-27_19-31-04_3fad42` | confirmation 2/5 | 19:31:04.417016 | 19:31:25.283376 | 1 | 1 | 0 | 0 | 35.0 | true | `golden-p1-0-6ea1e901124a` | 20523.616 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| `cohort_2026-08-27_19-31-26_6a312c` | confirmation 3/5 | 19:31:26.752381 | 19:31:49.464248 | 1 | 1 | 0 | 0 | 35.0 | true | `golden-p1-0-4352a45d612c` | 22395.609 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| `cohort_2026-08-27_19-31-50_199ec6` | confirmation 4/5 | 19:31:50.959526 | 19:32:15.572310 | 1 | 1 | 0 | 0 | 35.0 | true | `golden-p1-0-20c7cfa52216` | 24295.989 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| `cohort_2026-08-27_19-32-16_466e99` | confirmation 5/5 | 19:32:16.967293 | 19:33:04.703053 | 1 | 1 | 0 | 0 | 35.0 | true | `golden-p1-0-666616f2db14` | 47400.589 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |

Every cohort has the same manifest-level scalars: `mode=golden_p1_serial`, `method=run_golden_serial_stream`, target app/class/GPU as above, the same deployment identity, workflow identity, expected output SHA, `run_count_requested=1`, `attempt_count=1`, `valid_count=1`, `invalid_count=0`, `dnf_count=0`, `gap_seconds=35.0`, and `strict_serial=true`.

| Manifest scalar field | Value in all nine 19:00-hour manifests |
|---|---|
| `mode` | `golden_p1_serial` |
| `method` | `run_golden_serial_stream` |
| `target.app_name` | `stable-modal-comfy-v2-golden-p1` |
| `target.class_name` | `ModalRuntimeEntrypointV2` |
| `target.gpu` | `rtx-pro-6000` |
| `deployment_identity.app_name` | `stable-modal-comfy-v2-golden-p1` |
| `deployment_identity.class_name` | `ModalRuntimeEntrypointV2` |
| `deployment_identity.deployment_combined_hash` | `dacc5d6c022a85e4127507928653a0a74219e3383e03674a8708d3322f544178` |
| `deployment_identity.deployed_at` | `2026-08-27T18:41:51.806469+00:00` |
| `workflow.source_path` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\latest_benchmark_workflow.json` |
| `workflow.workflow_hash` | `14f815f1916e075ae79de7325681f6b0ec2216b8ad86c45e9bfa18f6388f5ea9` |
| `workflow.prompt_sha256` | `14f815f1916e075ae79de7325681f6b0ec2216b8ad86c45e9bfa18f6388f5ea9` |
| `workflow.captured_at` | `1787806519.2959576` |
| `expected_output_sha` | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| `expected_flags` | `{}` |
| `run_count_requested` | `1` |
| `attempt_count` | `1` |
| `valid_count` | `1` |
| `invalid_count` | `0` |
| `dnf_count` | `0` |
| `gap_seconds` | `35.0` |
| `strict_serial` | `true` |

## 7. Per-attempt table

| # | Cohort | Request ID | Status | Duration ms | DNF | True cold | Output SHA | Failures / validation reasons | Attempt artifact | Events artifact | Summary artifact |
|---:|---|---|---|---:|---|---|---|---|---|---|---|
| 1 | 19-23-57 | `golden-p1-0-ec699e817ca5` | VALID | 28112.707 | false | false | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | `[]` / `[]` | `...\cohort_2026-08-27_19-23-57_0bf24f\attempt_0.json` | `...\cohort_2026-08-27_19-23-57_0bf24f\attempt_0_events.json` | `...\cohort_2026-08-27_19-23-57_0bf24f\summary.json` |
| 2 | 19-26-34 | `golden-p1-0-9f827b7f51b6` | VALID | 20919.117 | false | false | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | `[]` / `[]` | `...\cohort_2026-08-27_19-26-34_169482\attempt_0.json` | `...\cohort_2026-08-27_19-26-34_169482\attempt_0_events.json` | `...\cohort_2026-08-27_19-26-34_169482\summary.json` |
| 3 | 19-28-12 | `golden-p1-0-e65c62f8c6fe` | VALID | 20365.684 | false | false | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | `[]` / `[]` | `...\cohort_2026-08-27_19-28-12_893726\attempt_0.json` | `...\cohort_2026-08-27_19-28-12_893726\attempt_0_events.json` | `...\cohort_2026-08-27_19-28-12_893726\summary.json` |
| 4 | 19-30-10 | `golden-p1-0-950b25c5dcb6` | VALID / gate | 20187.404 | false | false | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | `[]` / `[]` | `...\cohort_2026-08-27_19-30-10_22e884\attempt_0.json` | `...\cohort_2026-08-27_19-30-10_22e884\attempt_0_events.json` | `...\cohort_2026-08-27_19-30-10_22e884\summary.json` |
| 5 | 19-30-40 | `golden-p1-0-99fc4efadce1` | VALID / confirm 1 | 22434.198 | false | false | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | `[]` / `[]` | `...\cohort_2026-08-27_19-30-40_86aa19\attempt_0.json` | `...\cohort_2026-08-27_19-30-40_86aa19\attempt_0_events.json` | `...\cohort_2026-08-27_19-30-40_86aa19\summary.json` |
| 6 | 19-31-04 | `golden-p1-0-6ea1e901124a` | VALID / confirm 2 | 20523.616 | false | false | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | `[]` / `[]` | `...\cohort_2026-08-27_19-31-04_3fad42\attempt_0.json` | `...\cohort_2026-08-27_19-31-04_3fad42\attempt_0_events.json` | `...\cohort_2026-08-27_19-31-04_3fad42\summary.json` |
| 7 | 19-31-26 | `golden-p1-0-4352a45d612c` | VALID / confirm 3 | 22395.609 | false | false | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | `[]` / `[]` | `...\cohort_2026-08-27_19-31-26_6a312c\attempt_0.json` | `...\cohort_2026-08-27_19-31-26_6a312c\attempt_0_events.json` | `...\cohort_2026-08-27_19-31-26_6a312c\summary.json` |
| 8 | 19-31-50 | `golden-p1-0-20c7cfa52216` | VALID / confirm 4 | 24295.989 | false | false | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | `[]` / `[]` | `...\cohort_2026-08-27_19-31-50_199ec6\attempt_0.json` | `...\cohort_2026-08-27_19-31-50_199ec6\attempt_0_events.json` | `...\cohort_2026-08-27_19-31-50_199ec6\summary.json` |
| 9 | 19-32-16 | `golden-p1-0-666616f2db14` | VALID / confirm 5 | 47400.589 | false | false | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | `[]` / `[]` | `...\cohort_2026-08-27_19-32-16_466e99\attempt_0.json` | `...\cohort_2026-08-27_19-32-16_466e99\attempt_0_events.json` | `...\cohort_2026-08-27_19-32-16_466e99\summary.json` |

The `...` in the compact artifact columns is only a display abbreviation. The exact full paths for all nine attempts, event files, and summaries are enumerated in [Source evidence](#source-evidence).

### 7.1 Attempt scalar inventory

The following preserves the remaining scalar fields from each `attempt_0.json`; nested event scalars are retained in the exact event artifacts listed later.

| Cohort | `dispatch_unix_ms` | `dispatch_iso` | `start_ts` | `end_ts` | `event_count` | `events_file` | `error` | Commit evidence / ts | Reopen evidence / ts | Ordering OK | Observed flags |
|---|---:|---|---|---|---:|---|---|---|---|---|---|
| 19-23-57 | 1787858637931 | `2026-08-27T19:23:57.931000+00:00` | `2026-08-27T19:23:57.931121+00:00` | `2026-08-27T19:24:26.043863+00:00` | 1 | `attempt_0_events.json` | `null` | `data.golden_telemetry.events[22]` / 1787858656.7256055 | `data.golden_telemetry.events[24]` / 1787858665.2997556 | true | `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=true`; `core_model_patcher_is_dynamic=true` |
| 19-26-34 | 1787858794565 | `2026-08-27T19:26:34.565000+00:00` | `2026-08-27T19:26:34.565057+00:00` | `2026-08-27T19:26:55.484406+00:00` | 1 | `attempt_0_events.json` | `null` | `data.golden_telemetry.events[22]` / 1787858814.0689218 | `data.golden_telemetry.events[24]` / 1787858814.9223514 | true | `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=true`; `core_model_patcher_is_dynamic=true` |
| 19-28-12 | 1787858892902 | `2026-08-27T19:28:12.902000+00:00` | `2026-08-27T19:28:12.902414+00:00` | `2026-08-27T19:28:33.268406+00:00` | 1 | `attempt_0_events.json` | `null` | `data.golden_telemetry.events[22]` / 1787858911.699588 | `data.golden_telemetry.events[24]` / 1787858912.6861527 | true | `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=true`; `core_model_patcher_is_dynamic=true` |
| 19-30-10 | 1787859010483 | `2026-08-27T19:30:10.483000+00:00` | `2026-08-27T19:30:10.483623+00:00` | `2026-08-27T19:30:30.671186+00:00` | 1 | `attempt_0_events.json` | `null` | `data.golden_telemetry.events[22]` / 1787859029.1866913 | `data.golden_telemetry.events[24]` / 1787859030.1432276 | true | `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=true`; `core_model_patcher_is_dynamic=true` |
| 19-30-40 | 1787859040460 | `2026-08-27T19:30:40.460000+00:00` | `2026-08-27T19:30:40.460884+00:00` | `2026-08-27T19:31:02.895266+00:00` | 1 | `attempt_0_events.json` | `null` | `data.golden_telemetry.events[22]` / 1787859061.3159509 | `data.golden_telemetry.events[24]` / 1787859062.2148368 | true | `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=true`; `core_model_patcher_is_dynamic=true` |
| 19-31-04 | 1787859064758 | `2026-08-27T19:31:04.758000+00:00` | `2026-08-27T19:31:04.758490+00:00` | `2026-08-27T19:31:25.281377+00:00` | 1 | `attempt_0_events.json` | `null` | `data.golden_telemetry.events[22]` / 1787859083.6848845 | `data.golden_telemetry.events[24]` / 1787859084.731005 | true | `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=true`; `core_model_patcher_is_dynamic=true` |
| 19-31-26 | 1787859087067 | `2026-08-27T19:31:27.067000+00:00` | `2026-08-27T19:31:27.067397+00:00` | `2026-08-27T19:31:49.462246+00:00` | 1 | `attempt_0_events.json` | `null` | `data.golden_telemetry.events[22]` / 1787859107.6491601 | `data.golden_telemetry.events[24]` / 1787859108.9033241 | true | `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=true`; `core_model_patcher_is_dynamic=true` |
| 19-31-50 | 1787859111275 | `2026-08-27T19:31:51.275000+00:00` | `2026-08-27T19:31:51.275126+00:00` | `2026-08-27T19:32:15.571310+00:00` | 1 | `attempt_0_events.json` | `null` | `data.golden_telemetry.events[22]` / 1787859134.2924898 | `data.golden_telemetry.events[24]` / 1787859135.0541415 | true | `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=true`; `core_model_patcher_is_dynamic=true` |
| 19-32-16 | 1787859137300 | `2026-08-27T19:32:17.300000+00:00` | `2026-08-27T19:32:17.300770+00:00` | `2026-08-27T19:33:04.701053+00:00` | 1 | `attempt_0_events.json` | `null` | `data.golden_telemetry.events[22]` / 1787859181.8396475 | `data.golden_telemetry.events[24]` / 1787859184.0825293 | true | `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=true`; `core_model_patcher_is_dynamic=true` |

## 8. Five-run confirmation

The confirmation artifact records `confirm_runs=5`, `gate_valid=true`, `reasons=[]`, and `provenance_validation_status=validated`.

| Confirmation field | Value |
|---|---|
| Confirmation artifact | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\.v2ctl\confirmations\confirm_20260827-193305_b2f49680.json` |
| Created | `2026-08-27T19:33:05.284585+00:00` |
| `confirm_runs` | `5` |
| Gate manifest | `...\.v2ctl\gates\gate_20260827-193031_b2f49680.json` |
| Confirmation request ID (selected fifth run) | `golden-p1-0-666616f2db14` |
| Confirmation invocation ID | `398d281d18cb4b0a8ca96fc932cb5b44` |
| Gate-valid | `true` |
| Reasons | `[]` |
| Profile | `golden_p1` |
| Profile config fingerprint | `99b974a3b0a256ae2c9cd46158a74cd1a58bcfbe31f5d0364a0b7ec95adcea53` |
| Output SHA | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |

| Confirmation run | Cohort | Request ID | Status | Duration ms | Output SHA | Durable | Reopen verified | Seriality |
|---:|---|---|---|---:|---|---|---|---|
| 1/5 | `19-30-40_86aa19` | `golden-p1-0-99fc4efadce1` | VALID | 22434.198 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | true | true | `ok`, 0 violations |
| 2/5 | `19-31-04_3fad42` | `golden-p1-0-6ea1e901124a` | VALID | 20523.616 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | true | true | `ok`, 0 violations |
| 3/5 | `19-31-26_6a312c` | `golden-p1-0-4352a45d612c` | VALID | 22395.609 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | true | true | `ok`, 0 violations |
| 4/5 | `19-31-50_199ec6` | `golden-p1-0-20c7cfa52216` | VALID | 24295.989 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | true | true | `ok`, 0 violations |
| 5/5 | `19-32-16_466e99` | `golden-p1-0-666616f2db14` | VALID | 47400.589 | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` | true | true | `ok`, 0 violations |

## 9. Validation-contract results

| Contract | Result | Evidence / exact scalar values |
|---|---|---|
| Gate validity | PASS | Final `gate_valid=true`; `reasons=[]` |
| Backend execution | PASS | `backend_exit_code=0`; `backend_ok=true` for every listed successful cohort |
| Provenance | PASS | `provenance_validation_status=validated` in gate, confirmation, and manifests |
| Exact output | PASS | Expected and observed SHA are identical: `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| Attempt validity | PASS | Each cohort `valid=true`, `failures=[]`, `dnf=false` |
| Durable result | PASS | `true_durable_marked=true`; final event data has `true_durable=true` |
| Durable reopen | PASS | `reopen_verified=true`; `durable_reopen_verified` event; `reopened_verified=true` |
| Commit/reopen ordering | PASS | `commit_reopen_ordering_ok=true`; final attempt paths `data.golden_telemetry.events[22]` and `[24]` |
| Seriality | PASS | `seriality.ok=true`, `count=0`, `violations=[]`; terminal `seriality_violation_count=0` |
| Snapshot quiescence | PASS | `snapshot_quiescence.proven=true`, `passive=true`; executor pending work `0`; conditioning joined workers `0` |
| Snapshot value exclusion | PASS | `tensor_count=0`, `parameter_bytes=0`, `qd_owner_count=0`, `open_payload_reader_count=0`, `preload_worker_count=0`, `future_count=0`; `nonzero={}` and `nonzero_roles={}` |
| Snapshot bounds | PASS | `snapshot_size_bytes=4518584320` <= `snapshot_size_limit_bytes=5368709120`; source is RSS proxy, not serialized size |
| Telemetry persistence | PASS | `telemetry_persisted=true` |
| Runtime activation | PASS | `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=true`; `core_model_patcher_is_dynamic=true`; `ModelPatcherDynamic` |
| Loader identity | PASS in available manifest evidence | CLIP 398 tensors, UNET 453 same-storage assignments, VAE 244 same-storage assignments; no copied storage or unexpected device/shape/dtype counts |
| Workflow check | PASS by configured contract | Check disabled and explicitly bypassed; actual and expected workflow scalar hashes are retained in each attempt |
| True-cold contract | NOT PROVEN | `true_cold=false`; identity tokens are empty and reason is `insufficient remote/container identity evidence; never inferred` |

The repeated snapshot check scalar values are identical across the nine manifests: surface count `4`, snapshot size `4518584320`, size limit `5368709120`, tensor count `0`, parameter bytes `0`, model patcher count `0`, QD owner count `0`, open payload reader count `0`, preload worker count `0`, future count `0`, and all three role counters zero.

## 10. Telemetry and timing

The following table preserves the scalar restore/timing fields present in the cohort manifests. Stage timings are calculated directly from each manifest's `end_monotonic_ns - entry_monotonic_ns`; full timestamp scalars remain in the exact attempt and event artifacts.

| Cohort | Attempt ms | Restore total ms | Snapshot restore ms | Backend startup ms | Folder warm ms | CLIP load ms | CLIP forward ms | UNET load ms | VAE load ms | Sampling ms | VAE decode ms | Output ms | Durable commit ms | Teardown ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 19-23-57 | 28112.707 | 972.410 | 941.870 | 19316.870 | 356.221 | 1763.709 | 2184.926 | 2108.552 | 246.207 | 5856.440 | 578.226 | 201.708 | 8576.001 | 0.203 |
| 19-26-34 | 20919.117 | 601.744 | 573.060 | 19316.870 | 324.750 | 1861.259 | 2079.697 | 2125.348 | 257.843 | 5771.011 | 556.476 | 202.809 | 856.101 | 0.429 |
| 19-28-12 | 20365.684 | 740.662 | 686.040 | 19316.870 | 395.690 | 1993.011 | 2164.088 | 2370.125 | 268.652 | 6336.140 | 588.517 | 203.562 | 989.223 | 0.221 |
| 19-30-10 | 20187.404 | 523.614 | 493.090 | 19316.870 | 365.367 | 1765.111 | 2095.397 | 2163.454 | 233.904 | 5793.780 | 614.673 | 199.968 | 963.074 | 0.241 |
| 19-30-40 | 22434.198 | 2671.969 | 2638.430 | 19316.870 | 367.470 | 1914.809 | 2252.304 | 2098.577 | 263.655 | 6245.505 | 704.746 | 236.868 | 899.580 | 0.264 |
| 19-31-04 | 20523.616 | 808.806 | 776.600 | 19316.870 | 409.104 | 1733.206 | 2190.383 | 2201.274 | 226.074 | 5787.908 | 570.392 | 204.579 | 1047.382 | 0.192 |
| 19-31-26 | 22395.609 | 641.568 | 609.500 | 19316.870 | 363.732 | 1706.885 | 2099.702 | 2444.840 | 252.832 | 6096.944 | 587.723 | 214.323 | 1255.753 | 0.249 |
| 19-31-50 | 24295.989 | 514.300 | 487.040 | 19316.870 | 333.088 | 1799.471 | 2018.732 | 1984.950 | 237.528 | 5783.415 | 551.428 | 204.813 | 762.643 | 0.214 |
| 19-32-16 | 47400.589 | 887.141 | 853.670 | 19316.870 | 347.990 | 1812.789 | 2130.433 | 1923.449 | 267.889 | 5741.989 | 596.114 | 214.728 | 2243.931 | 1.092 |

Common scalar telemetry across the manifests includes `lifecycle_status=ok`, `lifecycle_method=restore`, `restore_count=1`, `models_symlink_ms=5.18`, `manager_offline_ms=1.22`, `sync_custom_nodes_ms=583.71`, `install_requirements_ms=0.01`, `comfyui_path_setup_ms=0.13`, `observe_generations_ms=2.54`, `folder_warm_folders=29`, `restore_method_status=success`, `initialize_cuda_invoked=true`, `initialize_cuda_reason=ok`, `reload_models_invoked=true`, `reload_models_reason=ok`, `reload_runtime_state_invoked=true`, `reload_runtime_state_reason=ok`, `restore_gpu_state_invoked=true`, `restore_gpu_state_reason=ok`, and `snapshot_identity_checks_invoked=false` with reason `not_invoked`.

### Stage scalar details from the final confirmation attempt

| Stage | `ok` | Scalar details |
|---|---|---|
| `golden_restore` | true | `observation_only=true`; device `NVIDIA RTX PRO 6000 Blackwell Server Edition` |
| `golden_request_setup` | true | request `golden-p1-0-666616f2db14`; node count `60`; actual workflow `e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5`; expected workflow `f2de4c6a8f032b4adcd21be0e490ecb97aa87261c8403af79d52e6a2eb29734c`; check `false`, bypassed `true` |
| `golden_clip_load` | true | usable `true`; published `398`; device `cpu`; owner retained `true`; state dict count `1`; source reads `240`; H2D bytes `8044936192` |
| `golden_clip_forward` | true | encoded `true` |
| `golden_unet_load` | true | assigned `453`; same storage `453`; assign mode `assign_true`; source reads `367`; H2D bytes `12309817472`; post-QD allocation delta `0`; skeleton peak delta `0`; adoption peak delta `0`; peak measurement supported `true` |
| `golden_sampler_prepare` | true | CUDA allocation delta bounded check `0`; patcher identity `47526349631568` |
| `golden_vae_load` | true | parameter count `244`; device `cuda:0`; dtype `torch.float32`; source reads `10`; H2D bytes `335278732` |
| `golden_sampling` | true | sampling nodes `1` |
| `golden_sampler_tail` | true | executed node count `30`; UI output node `935:931`; evidence gap `J1/O4 tail source bodies unrecovered; bounded bookkeeping only` |
| `golden_vae_decode` | true | image shape `(1, 1920, 1088, 3)` |
| `golden_output` | true | SHA `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`; byte count `3118312`; committed `false` |
| `golden_durable_commit` | true | SHA same as above; volume relative path `output_assets/454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da.png`; reopened verified `true` |
| `golden_teardown` | true | seriality violations `0`; owner staging release `0.1261 ms`; worker assert `0.932 ms`; reconcile `0.0117 ms` |

## 11. Fingerprint and identity table

| Cohort | Restore session ID | Container session ID | Restored instance ID | Identity object | Identity tokens present | Runtime state generation baseline |
|---|---|---|---|---|---|---|
| 19-23-57 | `a7c5b9c5ce4442279aff15f9b830748a` | `e3b41740b2214c0f` | `5ed120f158244c4cb6612668623c3567` | `{}` | false | `7e13941f111f4dc3b4ed438757445433` |
| 19-26-34 | `a3f779d8dbc74e6993f8bbfa4dec5bb7` | `e3b41740b2214c0f` | `f0d177c0c539421bb8d00b3720c5c8ef` | `{}` | false | `7e13941f111f4dc3b4ed438757445433` |
| 19-28-12 | `ef6796a86d864b9fa718ff50a34c7f0f` | `e3b41740b2214c0f` | `339614e52808436792d7cb09e3353f5e` | `{}` | false | `7e13941f111f4dc3b4ed438757445433` |
| 19-30-10 | `471da414b07847b8a35116be67ddcb62` | `e3b41740b2214c0f` | `559123f5a66844f291cb773bf9d18e3e` | `{}` | false | `7e13941f111f4dc3b4ed438757445433` |
| 19-30-40 | `ef200d0ce5f5413bad7f70ca0378f135` | `e3b41740b2214c0f` | `171f477d5c104cb4802254ea85c9bb7b` | `{}` | false | `7e13941f111f4dc3b4ed438757445433` |
| 19-31-04 | `3cf810bf1da14ea4ab7bc02fe931e71d` | `e3b41740b2214c0f` | `39f69092f5564fc686ac06b5ed7804d7` | `{}` | false | `7e13941f111f4dc3b4ed438757445433` |
| 19-31-26 | `5118665fece0431aaa2a2b9445903d57` | `e3b41740b2214c0f` | `7e651b8a81a24bd09540e49ee484bf8b` | `{}` | false | `7e13941f111f4dc3b4ed438757445433` |
| 19-31-50 | `b2c7b2d917f0446e99655ce41a2a6b73` | `e3b41740b2214c0f` | `26c78e6fede741a786f3c35ffce133d1` | `{}` | false | `7e13941f111f4dc3b4ed438757445433` |
| 19-32-16 | `31b33a74fe064be1987b26165729911a` | `e3b41740b2214c0f` | `e5943b52cb734c729103b736e6e47599` | `{}` | false | `7e13941f111f4dc3b4ed438757445433` |

All attempts also report empty `cold_evidence.identity_tokens` (`container_task_id`, `modal_container_id`, `container_session_id`, and `restored_instance_id` are empty in that object), `restore_count=null`, `request_count=null`, `basis=""`, and the explicit non-cold reason quoted above. The populated restore observation is separate from the cold-evidence identity contract.

## 12. Earlier failed-gate diagnostics

| Gate artifact | Created | Deploy fingerprint | Request ID | Gate valid | Exact reasons |
|---|---|---|---|---|---|
| `gate_20260827-153925_68a1fb54.json` | 2026-08-27T15:39:25.208750+00:00 | `26d4558c1b39238ae896f601da56fa3129e0b0169b1e4edf5816101be05cf243` | `v2-benchmark-0-cbe7fa4324f9` | false | `[structural] runtime_status_not_nominal:DEGRADED`; `[structural] loader_unobserved_clip`; `[structural] loader_unobserved_vae`; `[structural] loader_observed_mismatch_clip`; `[structural] loader_observed_mismatch_vae` |
| `gate_20260827-185931_b2f49680.json` | 2026-08-27T18:59:31.111183+00:00 | `3e487cc21090879c1efa4c4c0979388249c29211162928cd73ca50396ce774a2` | `v2-benchmark-0-6193d99b5f50` | false | Structural output mismatch (expected `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`, observed `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`); `runtime_status_not_nominal:DEGRADED`; `loader_unobserved_clip`; `loader_unobserved_vae`; `loader_observed_mismatch_clip`; `loader_observed_mismatch_vae`; duplicate `[output_sha]` mismatch reason |
| `gate_20260827-192833_b2f49680.json` | 2026-08-27T19:28:33.897936+00:00 | `3e487cc21090879c1efa4c4c0979388249c29211162928cd73ca50396ce774a2` | `golden-p1-0-e65c62f8c6fe` | false | `[canonical_ledger] canonical ledger missing from the run artifact (canonical_ledger_status absent): an E29 tracer run must attach canonical_ledger + canonical_ledger_status` |

The first failed gate's attempt additionally recorded terminal result count `0` instead of `1`, one error event, missing true-durable evidence, missing seriality telemetry, missing teardown telemetry, missing/unproven snapshot proof, missing commit and reopen timestamps, missing `TRUE_FIRST_DURABLE_RESULT`, missing terminal output SHA, and missing runtime flag evidence. Its transport/backend exit was nevertheless `0`; the failure was structural. The later 18:59 failure retained a valid backend transport but observed the wrong output and degraded loader evidence. The 19:28 failure isolated the canonical-ledger attachment defect. The final gate's `reasons=[]` demonstrates those gate-level defects were absent in the accepted run.

## 13. Source evidence

### Required control-plane evidence

| Evidence | Exact path |
|---|---|
| Final gate | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\.v2ctl\gates\gate_20260827-193031_b2f49680.json` |
| Five-run confirmation | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\.v2ctl\confirmations\confirm_20260827-193305_b2f49680.json` |
| Earlier failed gate 1 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\.v2ctl\gates\gate_20260827-153925_68a1fb54.json` |
| Earlier failed gate 2 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\.v2ctl\gates\gate_20260827-185931_b2f49680.json` |
| Earlier failed gate 3 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\.v2ctl\gates\gate_20260827-192833_b2f49680.json` |
| Deployment state | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\.deployed_state.json` |
| E40 context report | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\E40_CANONICAL_RUNTIME_TRUTH_AND_CLEANUP_REPORT.md` |
| R41 context report | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\R41_DETERMINISTIC_GOLDEN_QD4_PIPELINE_REPORT.md` |
| Reconciliation manifest | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\R41_E40_RECONCILIATION_MANIFEST.md` |

### Cohort manifest and nested artifact paths

The following are the exact full paths for each manifest and every nested attempt/event/summary artifact. The manifest's `artifact_file_hashes` scalars are retained below.

| Cohort | Manifest | Attempt | Nested events / telemetry | Summary |
|---|---|---|---|---|
| 19-23-57 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-23-57_0bf24f\manifest.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-23-57_0bf24f\attempt_0.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-23-57_0bf24f\attempt_0_events.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-23-57_0bf24f\summary.json` |
| 19-26-34 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-26-34_169482\manifest.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-26-34_169482\attempt_0.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-26-34_169482\attempt_0_events.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-26-34_169482\summary.json` |
| 19-28-12 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-28-12_893726\manifest.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-28-12_893726\attempt_0.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-28-12_893726\attempt_0_events.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-28-12_893726\summary.json` |
| 19-30-10 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-30-10_22e884\manifest.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-30-10_22e884\attempt_0.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-30-10_22e884\attempt_0_events.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-30-10_22e884\summary.json` |
| 19-30-40 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-30-40_86aa19\manifest.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-30-40_86aa19\attempt_0.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-30-40_86aa19\attempt_0_events.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-30-40_86aa19\summary.json` |
| 19-31-04 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-04_3fad42\manifest.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-04_3fad42\attempt_0.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-04_3fad42\attempt_0_events.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-04_3fad42\summary.json` |
| 19-31-26 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-26_6a312c\manifest.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-26_6a312c\attempt_0.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-26_6a312c\attempt_0_events.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-26_6a312c\summary.json` |
| 19-31-50 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-50_199ec6\manifest.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-50_199ec6\attempt_0.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-50_199ec6\attempt_0_events.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-31-50_199ec6\summary.json` |
| 19-32-16 | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-32-16_466e99\manifest.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-32-16_466e99\attempt_0.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-32-16_466e99\attempt_0_events.json` | `C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-32-16_466e99\summary.json` |

For unambiguous resolution of the compact cells in the previous table, each `...` is the directory prefix of that row's exact manifest path. For example, the final confirmation's full nested paths are:

```text
C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-32-16_466e99\attempt_0.json
C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-32-16_466e99\attempt_0_events.json
C:\Users\parla\AppData\Local\Temp\opencode\golden-p3-ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-08-27_19-32-16_466e99\summary.json
```

### Manifest artifact-file hashes

| Cohort | `attempt_0.json` SHA-256 | `attempt_0_events.json` SHA-256 | `summary.json` SHA-256 |
|---|---|---|---|
| 19-23-57 | `a7338a0c8c7007e564013c5ef03d299a79e7435f422ce1ce0cfde85c4bb03a23` | `c586fb2dc4bd602509ab440fd8be53a2b3363d43966236ae735f1ad7e0372dde` | `c10622f67672446af2754de86be8cb45e9850b99c854840e675af69fff7e278a` |
| 19-26-34 | `690ac5d906529875409d972d4ee37be64f9f655ed989e26d52f91947ee4b59c3` | `205b69298af5fb7743b93c39d8603afbb11b11050d5840abf0e48f30ff8a0888` | `8dd862d165b35e186c85a802e0817b5278168f7a7a0cfbc7c03a298856390cb6` |
| 19-28-12 | `8215223520e96672c08d1008533b12fb1fe9ba71528621777b1027827be5caca` | `6012b7f1ad254715fbb4b7aba1fe70a9d359e6a3db5385d28c0b4cd8cbc7d544` | `3821b0f5428878b81291b0df3c3af429ad6951c620ec19531f35b0b9df43e08b` |
| 19-30-10 | `20f1bf00b0cc5a101724efea7ad597d0c8ab2f44af5d9a21b9f374e2c36d1be2` | `c554b4945369c0814d9ef70bd36e0ae37483523c7007953a7df59de15122280d` | `5378e5d930396ae2afb994e49f5f9d23958e93c6823931f7ff6f9e90d81d9713` |
| 19-30-40 | `c0caadaf21ac9283d4ce809210030c7ca2b1ebeb3b6e547ee66faa4d77127d33` | `e49de199edbcbe427e678890a333b23702d5953827cf6d595dd4811a7cc171c2` | `7839c2d285ab371ea1dd0a4a91bf5ba8755059d3fe66d25208e75843ac195075` |
| 19-31-04 | `b4507378ccd3b96d7833edfab707db4fa7f018782aa106f034d33b938fa7b37b` | `60f14fb694fa67193e5e45b11cdad475dc3f955f1ad2d4c6ab7727da002a596b` | `06c3def34b9927c1d1d61aa23815dc112ad98d89fa16aa4a689af12ed49e91a1` |
| 19-31-26 | `94f0919bf1f1dd87ee781b889864ef0dadfd9bd2d3f376e769c869a0064bbc50` | `f9eca11ec0363489fdec7f01b6a8be1ebb9f59fee2672fe5fe1e1c0837e5f283` | `ac5cb4911155f169648281505bd85254ae027d5f5e5f279937ecf2ec809cc635` |
| 19-31-50 | `0236602e5f3e9989da86d3f1a9923349e02fe021bf5a7676a7c489b696e9c197` | `ef88de77369916d1575f841ca7f83f767811dadee2c9c17867887134276b81e6` | `3591c45b4d3c97be614c97715717ba09b1d2b4584b687bf38ed3e855d6678e04` |
| 19-32-16 | `6a37f5d29b8b60aedc15c7cc908f1260032a318ef18881b435cab0f86c12036e` | `e8adf904508b99d1aaaec5c21b8fd80183c640978f144706b4f2db6651140156` | `34a9bc11d732405b258ba085e800434a04d5dfa081f9c9b217e740cd6f25ca0f` |

## 14. Limitations

1. The gate and cohort evidence is in the temp workspace outside Git; it is not itself versioned by this repository.
2. The gate and confirmation JSON embed `git_head="unknown"`; the exact local checkout commit is reported separately and is not independently asserted by the remote gate.
3. True-cold status is not proven. The evidence explicitly refuses to infer it without remote/container identity tokens.
4. `snapshot_size_bytes` is sourced from `process_rss_pre_capture_resident_memory_proxy`; it is explicitly not serialized snapshot size.
5. Workflow-hash checking was disabled/bypassed, so actual and expected workflow hash scalars are recorded but not used as an acceptance predicate.
6. The sampler-tail evidence gap is explicitly recorded as `J1/O4 tail source bodies unrecovered; bounded bookkeeping only`.
7. The compact artifact columns above use `...` for display only; the exact per-cohort manifest prefixes and final full nested paths are provided in [Source evidence](#source-evidence).

## 15. Reproducibility checklist

- [ ] Use the stated checkout commit and verify the deployed ComfyUI commit separately.
- [ ] Verify deployment combined hash, deploy fingerprint, profile config fingerprint, run fingerprint, and runtime-shape fingerprint.
- [ ] Use profile `golden_p1`, target `stable-modal-comfy-v2-golden-p1`, class `ModalRuntimeEntrypointV2`, method `run_golden_serial_stream`.
- [ ] Use the recorded workflow/prompt SHA and expected output SHA.
- [ ] Confirm `gate_valid=true`, `reasons=[]`, backend exit `0`, and provenance `validated`.
- [ ] Confirm one valid, non-DNF attempt per cohort and identical output SHA across the gate plus five confirmations.
- [ ] Confirm durable commit, reopen verification, seriality zero, snapshot quiescence, zero snapshot value bytes, and persisted telemetry.
- [ ] Treat true-cold as unproven unless container identity evidence is added; do not infer it from timing.
- [ ] Preserve the temp evidence directory or copy its JSON artifacts into a versioned evidence store before relying on this report elsewhere.
