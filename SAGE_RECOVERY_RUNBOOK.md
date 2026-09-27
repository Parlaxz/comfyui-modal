# SageAttention Recovery Runbook

This runbook records the SageAttention regression investigation and the safe
Golden validation procedure. It is intentionally fail-closed: an override
counter is not proof that the native SageAttention CUDA leaf executed, and a
process exit code is not proof that the Golden output is canonical.

## 1. Scope and safety

- Work in the repository root only.
- Preserve the shared, already-dirty worktree. Do not reset, clean, stash,
  revert, overwrite, or delete unrelated changes.
- Use the experimental app selected for the current run. The protected app
  `stable-modal-comfy-v2-golden-p1` must not be used for ordinary Golden
  operations.
- Use `python tools/v2ctl.py ...` for every deploy, source probe, run, gate,
  and confirmation. Do not invoke BAT files, the raw Modal CLI, ad-hoc SDK
  deploys, or experiment-specific launchers.
- Acquire and respect `.v2ctl/deploy.lock`. Check it first:

  ```powershell
  python tools/v2ctl.py lock status
  ```

  Deploy commands acquire the lock automatically. A conflicting owner must
  stop. Treat a lock as stale only with evidence; force release is explicit,
  logged, and should use:

  ```powershell
  python tools/v2ctl.py --owner <operator> lock force-release
  ```

  The lock was `deploy.lock=none` during the final local validation.

## 2. Symptom and hash history

The original R0 Golden contract expected:

```text
454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da
```

The current `golden_p1` profile and the S1 cohort expected:

```text
8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
```

These are not interchangeable baselines. Never label a run canonical until
the expected SHA is taken from the active profile and the observed SHA matches
it. The final S1 artifact below had a structurally valid attempt and exit code
zero, but recorded an observed SHA of
`bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` against
the configured `8a924...` SHA. That is a hash warning, not a successful
canonical-output proof.

## 3. What failed and why

The regression was a lifecycle/restore problem, not a sampler-routing change.
The relevant sequence was:

1. Snapshot creation used a CPU-safe path and could preserve a fallback state.
2. Restore reattached CUDA and restored the API instance.
3. The restored instance could retain the snapshot-carried
   `_sage_runtime_mode` value, including `triton_fallback`, as a sticky value.
4. KJNodes held a closure alias through `get_sage_func`; inspecting or wrapping
   only the visible `attention_sage` symbol missed the callable that actually
   mattered.
5. The earlier probe instrumentation also used `__wrapped__` in a way that
   bypassed the effective callable and produced misleading backend evidence.
6. A late-bound `transformer_options` mapping meant that a one-time lookup was
   not sufficient for request-local observation.

The observed consequence was that a Sage request could be converted by the
KJNodes wrapper from a non-`baked_cuda` mode to `attention_fallback`, then to
PyTorch/SDPA. The coarse override label could therefore look Sage-like while
the native leaf was not proven.

## 4. Fix that is now deployed

The fix is in `comfymodal_runtime/modal_app.py` and preserves ordinary V2
behavior:

- Ordinary restores retain the normal wide Sage policy and existing cache/
  override behavior.
- Golden restore installs a Golden-only selector after CUDA restore.
- That selector clears only the stale API fields
  `api._sage_runtime_mode` and `api._sage_runtime_reason` at the callback
  boundary.
- Golden then selects `baked_cuda` through the configured environment path;
  it does not enter the native smoke probe during restore.
- KJNodes' Sage policy is reapplied after CUDA restore.
- Request-local strict/native validation remains in `golden_serial.py`.
- Sampler `attention_backend` routing and ordinary profiles are unchanged.

The key source locations are:

- `comfymodal_runtime/modal_app.py:9285-9394`
- `comfyapp.py:15161-15240`
- `comfyapp.py:6670-6750` (KJNodes policy)
- `comfymodal_runtime/runtime_bootstrap.py:2165-2240`
- `comfymodal_runtime/sampling_deep_profile.py:450-500, 930-990`

## 5. Evidence from the final deployment/run

Authoritative deployment manifest:

```text
.v2ctl/deployments/deploy_20260830-090243_6c5893f8.json
```

Recorded deployment facts:

- app: `batch-s1-cache-e1`
- class: `ModalRuntimeEntrypointV2`
- profile: `golden_p1`
- GPU: `rtx-pro-6000`
- deployment fingerprint/combined hash:
  `6c5893f803822c74419debcf74f5c87bf0f339006fd969502366953e327177ba`
- deploy started: `2026-08-30T14:01:48+00:00`
- deploy ended: `2026-08-30T14:02:43+00:00`
- deploy exit code: `0`

Final cohort artifact:

```text
artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_11-15-03_dc131f/summary.json
```

Recorded run facts:

- run started: `2026-08-30T11:15:03.118644+00:00`
- run completed: `2026-08-30T11:15:55.732280+00:00`
- requested runs: `1`
- structurally valid attempts: `1`
- invalid attempts: `0`
- DNF count: `0`
- strict seriality: `true`
- backend observation: `sageattention_override_no_sdpa_observed`
- KJNodes/Sage override dispatches: `300`
- PyTorch SDPA calls: `0`
- observed Sage-SDPA evaluations: `0`
- observed chain:
  `attention_override_sage -> attention_sage -> sage_func`
- observed input: bf16 CUDA tensor, `[1, 8448, 3840]`

The telemetry proves dispatch through the KJNodes Sage override with no
observed SDPA calls. It does **not** prove a native SageAttention leaf kernel:
the direct leaf counters were zero/unobserved. Keep that limitation attached
to every future report.

## 6. Focused validation already run

Offline regression tests:

```powershell
pytest -q tests/test_sageattention_restore_policy.py tests/test_sampling_deep_profile_attention_observation.py tests/test_ra5_attention_backend.py
```

Result:

```text
56 passed
```

The tests cover runtime identity changes, strict negative-cache rejection,
compiled-extension selection, KJNodes fallback rejection, request-local
backend normalization, clone-versus-seeded patcher targeting, omitted-backend
preservation, closure aliases, lazy override mappings, bounded callable
metadata, counting, and restoration.

Before accepting a remote result, also run the public control-plane checks:

```powershell
python tools/v2ctl.py golden status --app <experimental-app>
python tools/v2ctl.py doctor --profile golden_p1 --app <experimental-app>
python tools/v2ctl.py golden deploy --app <experimental-app>
python tools/v2ctl.py --profile golden_p1 --app <experimental-app> source-probe
python tools/v2ctl.py golden run --app <experimental-app>
python tools/v2ctl.py gate --profile golden_p1 --app <experimental-app>
python tools/v2ctl.py --profile golden_p1 --app <experimental-app> confirm --from <gate-manifest> --runs 5
```

Deploy before a request. Run exactly one cold gate first. If the gate is
structurally invalid or the SHA is wrong, stop, diagnose, and redeploy after
any deploy-relevant source/config change. Do not spend confirmation runs on an
invalid gate.

## 7. Reading backend evidence correctly

Use the complete raw artifact, not only the summary label. Check all of:

1. `attention_backend.actual_backend`.
2. `dispatch_counts` for Sage, PyTorch, SDPA, and unknown calls.
3. The full callable chain and its module/source identity.
4. Input shape, dtype, device, and layout.
5. Direct native-leaf counters, if present.
6. Request identity, restore identity, deployment fingerprint, and workflow
   hash.
7. Canonical output SHA and the profile's expected SHA.

An override count of `300` plus `pytorch_sdpa_calls=0` is strong evidence of the
observed KJNodes dispatch path. It remains a candidate Sage result unless the
native leaf is independently observed. A missing native counter is
`unobserved`, not zero native execution.

## 8. Modified files and worktree accounting

The Sage-recovery workstream touched or requires review of:

```text
comfyapp.py
comfymodal_runtime/modal_app.py
comfymodal_runtime/runtime_bootstrap.py
comfymodal_runtime/sampling_deep_profile.py
comfymodal_runtime/golden_serial.py
comfymodal_runtime/deployment_spec.py
config/v2/profiles/golden_p1.toml
tests/test_sageattention_restore_policy.py
tests/test_v2_sampling_deep_profile.py
tests/test_v2_sampling_deep_profile_wrapper.py
tests/test_sampling_deep_profile_attention_observation.py
tests/test_ra5_attention_backend.py
```

The repository also contains broad unrelated tracked and untracked changes
(runtime, v2ctl, publication, web, reports, and many artifacts). Before any
commit, inspect and stage only the intended files:

```powershell
rtk git status --short
rtk git diff --name-only
rtk git diff -- SAGE_RECOVERY_RUNBOOK.md
```

Do not infer ownership from file timestamps. Retain every run manifest,
cohort summary, attempt, event file, and raw command log, including invalid
attempts.

## 9. Next diagnostic if the SHA still differs

Stop changing runtime policy. First establish whether the mismatch is a
baseline/configuration mismatch or an actual runtime regression:

1. Read `expected_output_sha` from the active `golden_p1` profile and cohort.
2. Verify deployment fingerprint and `source-probe` identity match the local
   source.
3. Compare workflow hash and prompt hash.
4. Compare the complete output artifact, not just the filename or summary.
5. Compare backend chain, tensor metadata, restore/request identity, and
   native-leaf evidence.
6. Only then determine whether to investigate image/dependency drift, restore
   state, KJNodes policy, or sampler behavior.

Never silently rewrite the expected SHA to make a run pass.
