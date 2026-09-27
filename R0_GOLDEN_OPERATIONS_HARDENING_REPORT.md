# R0 Golden Operations Hardening Report

> **SUPERSESSION NOTICE (2026-08-30):** Historical R0 evidence is preserved as
> recorded. Use `.opencode/skills/comfymodal-golden-ops/SKILL.md` and
> `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for current operations:
> generated-output durability is off by default and strict is opt-in. S4
> source publication durability remains mandatory.

**Verdict:** PASS — isolated remote Golden closure completed. The final
deployment was source-verified, health-verified, and followed by a valid gate
and five valid single-run confirmations on the same deployment identity.

## Scope and invariants

The accepted target was `batch-r0-golden-ops` /
`ModalRuntimeEntrypointV2.run_golden_serial_stream` under `golden_p1`.
The protected production app `stable-modal-comfy-v2-golden-p1` was not touched.
Civitai was excluded from R0 deployment, runtime, identity, inference, and
validation reasoning.

The operation retained one request per invocation, `gap_seconds=35.0`,
`strict_serial=true`, `min_containers=0`, and single-use containers. The expected
output was SHA-256
`454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`.

## Implementation change

`comfymodal_runtime/modal_app.py` now performs a remote-safe fallback lookup of
the already-mounted `comfymodal-runtime-config` Volume when the serialized
module resource map has no live runtime-state handle. The existing
fail-closed `golden_runtime_state_volume_unavailable` error remains in force if
the fallback also fails.

Focused validation after the change:

- `tests/test_modal_app_identity.py -k GoldenSerialStreamWiring`: 7 passed
- `tests/test_v2_observability_instrumentation.py -k TestPublishRestorePlanVolumeFallback`: 4 passed
- `tests/test_p2_golden_snapshot_adapter.py -k test_adapter_passes_mount_restore_metadata_and_terminal_timestamps`: 1 passed
- `git diff --check`: passed

## Deployment and source proof

Deployment used:

```text
python tools/v2ctl.py golden deploy --app batch-r0-golden-ops
```

Deployment manifest:
`.v2ctl/deployments/deploy_20260828-215821_0924070a.json`

| Field | Value |
|---|---|
| Git HEAD | `b578f77cfdabff73b3c1d66cb9d5c7fcc155ca22` |
| Profile | `golden_p1` |
| Profile config fingerprint | `6c47efdc01d7a8f1ec46ac2925e480efd6ec9c7706de7e7c511e6ac6d5d3ecaf` |
| Deployment fingerprint | `0924070a685e2de4ffe6e7d2b95c1aceffd29e0907cbfb9a04c5dad4468d5cc5` |
| Deployment combined hash | `d25161544d2d2d7461d32a1b2f99ea381c6cf7a108d3c9b2481037192fbeac96` |
| Target | `batch-r0-golden-ops` |
| Class / method | `ModalRuntimeEntrypointV2 / run_golden_serial_stream` |
| CPU / memory | `12 / 32768 MB` |
| Runtime overrides | none; policy `forbid` |
| Source probe | `PASS`, `source_identity=MATCH` |
| Final health | `verified`; `ready=True` |

The deployed source probe used the public top-level command and matched the
remote `comfymodal_runtime/modal_app.py` bytes. The runtime-state Volume
`comfymodal-runtime-config` was present and the repaired adapter successfully
published durable output assets under `/mnt/comfymodal_runtime_state`.

## Attempt history

The first post-deployment request is retained as an invalid platform/runtime
attempt. It reached the correct app and proved true-cold identity, but emitted
`RuntimeError: golden_runtime_state_volume_unavailable`; it had no terminal
result and was not counted.

| Role | Cohort | Request ID | Result | Deployment fingerprint |
|---|---|---|---|---|
| initial failure | `cohort_2026-08-29_02-44-29_55b7d4` | `golden-p1-0-8f4fa6804e26` | invalid; runtime-state volume unavailable | `96a1c0a1...` |
| valid run 1 | `cohort_2026-08-29_03-00-25_d3d715` | `golden-p1-0-8ee6a15bbdd9` | valid, true-cold | `0924070a...` |
| valid run 2 | `cohort_2026-08-29_03-01-43_cdd54b` | `golden-p1-0-06ff32eb6883` | valid, true-cold | `0924070a...` |
| valid run 3 | `cohort_2026-08-29_03-02-46_77d9c7` | `golden-p1-0-1e0c0be1e91d` | valid, true-cold | `0924070a...` |
| valid run 4 | `cohort_2026-08-29_03-03-39_fb0c6c` | `golden-p1-0-fdcebfc49886` | valid, true-cold | `0924070a...` |
| valid run 5 | `cohort_2026-08-29_03-04-40_1c07e0` | `golden-p1-0-3851980302e5` | valid, true-cold | `0924070a...` |

All five valid runs had `valid_count=1`, `invalid_count=0`, `dnf_count=0`,
`strict_serial=true`, and the expected output SHA. Each observed
`COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=true` and
`core_model_patcher_is_dynamic=true`.

## Gate and inherited confirmation

The structural gate passed:

```text
.v2ctl/gates/gate_20260829-030549_5d3926df.json
gate_valid=true
```

The first confirmation invocation used the wrong default profile and was
rejected before backend work; it issued no request. The corrected command was:

```text
python tools/v2ctl.py --profile golden_p1 --app batch-r0-golden-ops confirm \
  --from .v2ctl/gates/gate_20260829-030549_5d3926df.json --runs 5
```

Confirmation manifest:
`.v2ctl/confirmations/confirm_20260829-030820_5d3926df.json`

The confirmation runner executed five separate single-run backend invocations;
all five summaries were valid with no reasons. Their cohorts were:

- `cohort_2026-08-29_03-06-10_1281ea`
- `cohort_2026-08-29_03-06-32_1c6fe2`
- `cohort_2026-08-29_03-06-57_258032`
- `cohort_2026-08-29_03-07-27_4ae57e`
- `cohort_2026-08-29_03-07-54_ec9bbd`

The gate run itself was retained at
`cohort_2026-08-29_03-05-29_46621a` and was valid.

## Runtime proof

Every accepted attempt reported:

- restore count `1`, request count `1`, and true-cold identity tokens;
- stable deployment combined hash above;
- valid passive snapshot content proof and snapshot quiescence proof;
- `true_durable_marked=true` and `reopen_verified=true`;
- commit evidence before reopen evidence;
- zero seriality violations;
- expected output SHA and durable output asset path;
- completed Golden teardown telemetry.

The final status and doctor logs report matching deployment fingerprints and
targets, verified source/runtime health, no overrides, no active lock, and
`ready=True`.

## Raw evidence

Raw control-plane logs are retained under `artifacts/`, including:

- `r0_remote_redeploy_20260828.log`
- `r0_remote_redeploy_source_probe_20260828.log`
- `r0_remote_redeploy_status_20260828.log`
- `r0_remote_redeploy_doctor_20260828.log`
- `r0_remote_attempt_001_20260828.log`
- `r0_remote_attempt_002_20260828.log` through `r0_remote_attempt_006_20260828.log`
- `r0_remote_gate_20260828.log`
- `r0_remote_confirm_5_20260828.log`
- `r0_remote_confirm_5_20260828_retry.log`
- post-attempt and post-confirm status/doctor logs

Every cohort directory retains its `manifest.json`, `summary.json`,
`attempt_0.json`, and `attempt_0_events.json`. Invalid evidence was retained;
no artifact was selected only by modification time.

## Remaining qualification

The implementation fix is intentionally uncommitted in the working tree so it
remains auditable alongside the existing user/runtime changes. The deployed
manifest records the corresponding dirty source hash. Do not claim the stable
production app was validated by this R0 experiment.
