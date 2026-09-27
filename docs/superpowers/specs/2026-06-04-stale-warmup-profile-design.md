# Stale warmup profile prevention design

## Summary

Prevent cold restore from preloading the previous workflow's model stack when the next submitted workflow has changed. The restore path should prefer an explicitly activated next-profile derived from the current workflow, fall back only to an explicit env default, and otherwise disable warmup rather than silently using stale history.

## Problem

The current restore flow resolves the warmup/preload profile from persisted history in `comfyapp.py`, especially `_load_last_model_stack()` through `_snapshot_preload_profile()`. That means a cold restore can preload workflow A even when the prompt being submitted is workflow B, because the current workflow is known on the local side before dispatch but not yet reflected in persisted restore-time state.

This is especially costly when switching between very different stacks, such as a large Flux2/Mistral workflow and a smaller Klein/Qwen workflow. A wrong warmup profile is worse than no warmup because it adds restore cost, loads the wrong assets, and obscures root-cause debugging.

## Goals

- Ensure restore-time warmup selection reflects the workflow currently being dispatched whenever that workflow can be identified confidently.
- Remove `last_stack` as an implicit restore-time authority.
- Prefer explicit activation over inferred history.
- Fall back safely to no warmup when the current workflow profile is uncertain.
- Add clear logging that makes stale-profile behavior obvious.
- Preserve existing architecture patterns where possible, especially the existing runtime-config setter mechanism.

## Non-goals

- Editing workflow JSON.
- Changing sampler settings.
- Changing scaledown behavior.
- Starting CUDA graph, `torch.compile`, or broader performance work.
- Re-enabling ModelPatcher cache.
- Changing image return mode.
- Introducing workflow-specific hardcoded model names.
- Building a multi-tenant stack scheduler.

## Approach options considered

### Option 1 — remove `last_stack` restore fallback only

Change restore-time selection so `_snapshot_preload_profile()` no longer uses `_load_last_model_stack()` as an implicit selector. Restore would use an explicit env warmup profile if present, otherwise no warmup.

This is the safest behavioral fix, but it loses the ability to warm the current workflow immediately after a workflow switch unless some explicit activation mechanism is added.

### Option 2 — explicit active-next profile before dispatch

Add a lightweight CPU-only runtime-config setter that stores the next requested warmup profile immediately before prompt dispatch. Restore consumes that explicit activation first, then falls back to env default, then to no warmup.

This is the recommended option because it fixes the stale-profile bug while keeping warmup available for the workflow that is actually about to run.

### Option 3 — stack registry plus active-next profile

Store reusable profiles keyed by normalized stack identity, then activate one before dispatch.

This is viable later, but it is not required for the first fix. A registry alone does not solve the timing problem because restore still needs an explicit signal telling it which profile to use for the next cold invocation.

## Approved approach

Implement Option 2 for phase 1, with these rules:

1. Restore selection order is `active_next_profile -> env_default -> no warmup`.
2. `last_stack` remains history/diagnostic data only, not restore-time authority.
3. The active-next setter must be CPU-only and must not initialize ComfyUI, GPU state, or the main runner class.
4. If the current workflow profile cannot be derived confidently, warmup is disabled for that request instead of using stale state.
5. Registry work is deferred to a later phase.

## Detailed design

### Runtime behavior

#### Restore-time profile selection

`_snapshot_preload_profile()` in `comfyapp.py` should be changed to prefer:

1. an explicitly stored `active_next_profile` record, if valid and unexpired
2. an explicit env-configured warmup profile
3. no warmup profile

It should no longer treat `_load_last_model_stack()` as a restore selector.

#### Pre-dispatch activation

The local bridge already computes `workflow_hash` and `model_stack` before remote execution in `__init__.py`. Right before `run_prompt_stream()` starts in `_execute_job()`, the code should:

1. derive a warmup-profile-compatible profile from the current workflow/model stack
2. determine whether the profile is confident enough to use
3. call a new lightweight Modal setter that writes a volume-backed `active_next_profile` record

If derivation is not confident, the local side should explicitly arm a disable/no-warmup record for the next restore rather than allowing stale restore state to win.

#### Post-execution persistence

`_save_last_model_stack()` and `_save_last_warmup_workflow()` should remain in place for history, diagnostics, and possible future optimizations. They must not control restore-time profile selection.

### Active-next profile record

The volume-backed record should contain these fields:

- `profile_token`
- `workflow_hash`
- `created_at`
- `expires_at`
- `mode`
- `model_stack`
- `warmup_profile`
- `disable_warmup`
- `selected_at`

The token is important because this is global shared state. Logs should be able to distinguish which activated record restore selected and which prompt later ran.

### Setter requirements

The new setter should follow the existing runtime-config pattern used by `set_preload_mode`, `set_warmup_clip_encode`, and `set_return_mode`, but with stricter safety expectations:

- it must run as a lightweight CPU-only function
- it must not initialize ComfyUI
- it must not initialize GPU state
- it must not instantiate or restore the main runner class
- it must write to the shared volume and commit synchronously so restore can see the update

This avoids accidentally paying the expensive startup/restore cost in the very mechanism intended to prevent stale restore behavior.

### Confidence rules

The system should activate warmup only when the current workflow can be mapped confidently to one of these:

- checkpoint mode with a concrete checkpoint name
- split mode with concrete UNET, CLIP, and VAE identity

If extraction is partial, empty, malformed, or otherwise uncertain, the system should prefer `disable_warmup=true` for that request.

### TTL and staleness

The active-next profile TTL is 60 seconds.

If restore sees an expired record, it should:

- log that the activation expired
- ignore the record
- use env default if explicitly configured
- otherwise perform no warmup

An expired activation must never silently degrade into `last_stack` usage.

### Consume/select semantics

Phase 1 will not hard-delete the record on selection. Instead:

- restore records `selected_at` and the selected `profile_token`
- the next dispatch overwrites the record
- expired records are ignored

This keeps phase 1 simple while avoiding premature consumption if a run fails after restore begins.

### Logging

#### Restore-time logs

Restore should log:

- `current_workflow_stack` when available from activation metadata
- `selected_warmup_profile`
- `profile_source=active_next_profile|env_default|none`
- `workflow_hash`
- `profile_token`
- `profile_match=true|false|unknown`
- `warmup_disabled_due_to_mismatch=true|false`
- activation age / expiry result

If an activation is rejected, log the reason clearly, such as expired, malformed, empty, or uncertain.

#### Prompt-execution logs

During prompt execution, compare the restore-selected profile against the actual workflow model stack and log:

- `WARMUP_PROFILE_MATCH=true|false`
- selected profile token
- prompt workflow hash

If false, print both stacks/profile payloads so the mismatch is obvious.

#### Env fallback logs

If restore falls back to env configuration, log that explicitly as `profile_source=env_default`. It should never appear as if the env profile came from the current workflow.

### Concurrency model

This design is acceptable for the current single-queue, infrequent-customer setup.

Important limitation: `active_next_profile` is global state. That means it is not a complete solution for multi-tenant or highly concurrent mixed-stack workloads. Phase 1 intentionally does not solve per-stack routing, multi-pool warming, or concurrent activation races across multiple workers.

To minimize risk even in the current setup:

- write activation in `_execute_job()` right before dispatch, not at initial HTTP ingress
- include a profile token and workflow hash
- use a short TTL
- never fall back from invalid activation to stale history

## Code changes

1. Add a new lightweight runtime-config setter in `comfyapp.py` for `active_next_profile`.
2. Add any needed client wrapper in `modal_client.py` for calling that setter.
3. In `__init__.py:_execute_job()`, activate the next warmup profile immediately before `run_prompt_stream()`.
4. Update `comfyapp.py:_snapshot_preload_profile()` to prefer explicit activation and stop using `_load_last_model_stack()` as a restore selector.
5. Update restore-time logging around early warmup profile selection.
6. Update prompt-time diagnostics so the selected restore profile is compared against the actual workflow stack using token/hash-aware logs.
7. Keep `_save_last_model_stack()` and `_save_last_warmup_workflow()` for history/diagnostics only.

## Error handling

- If activation write fails, log loudly and fall back to env/none.
- If the activated record is malformed, expired, or incomplete, ignore it and fall back to env/none.
- If current workflow identity is unknown, disable warmup rather than using stale history.
- If restore-selected and actual prompt stacks mismatch, log the mismatch loudly; do not silently claim success.

## Test strategy

Add or update tests to cover:

### Test 1 — same workflow repeated

- same workflow activated twice
- selected warmup profile matches workflow
- no mismatch warning

### Test 2 — huge workflow to small workflow

- run a large workflow, then activate and run a smaller workflow
- second request must not preload the previous large stack
- selected profile must match the smaller workflow

### Test 3 — small workflow to huge workflow

- run a small workflow, then activate and run a larger workflow
- selected profile must intentionally switch to the larger stack
- no stale small-profile warmup

### Test 4 — unknown profile

- force a case where current stack derivation is incomplete or uncertain
- restore must not use stale history
- warmup must be disabled or safely omitted
- logs must explain why

### Additional behavior tests

- restore ignores expired activation records
- env fallback is labeled `env_default`
- `last_stack` is not referenced as the selector path in restore logic
- the active-next setter remains lightweight and does not initialize the main runtime
- token/hash logging is present in restore and prompt diagnostics

## Risks and mitigations

- Risk: the setter accidentally triggers expensive restore/runtime initialization. Mitigation: keep it as a separate CPU-only function with explicit tests.
- Risk: the activation write is not visible in time for restore. Mitigation: synchronous volume commit, short path, safe fallback to env/none.
- Risk: global activation can race under future concurrency. Mitigation: tokenized logging, dispatch-time write, TTL, and no stale-history fallback. Full concurrency isolation is deferred.
- Risk: prompt execution failure after activation could leave a record behind. Mitigation: TTL plus selection/consumption metadata and overwrite-on-next-dispatch behavior.

## Future phase

Phase 2 may add a registry of known stack combos keyed by normalized stack identity. That registry would support reuse, metrics, and faster activation lookup when bouncing between workflows.

Phase 2 should remain advisory only. Even with a registry, restore must still require explicit activation for the current next request.

## Success criteria

- Switching workflows no longer causes restore to preload the previous workflow's stack.
- Restore selects the current workflow's profile whenever the current workflow can be identified confidently before dispatch.
- If current workflow identity is uncertain, stale warmup is not used.
- Logs clearly show which profile restore selected, where it came from, and whether it matched the actual prompt.
- Phase 1 does not depend on a stack registry.
