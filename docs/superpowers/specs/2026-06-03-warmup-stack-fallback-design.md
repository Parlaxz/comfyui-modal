# Warmup stack fallback design

## Summary

Remove the Flux2-specific warmup profile defaults from the runtime so cloned repos and non-Flux workflows do not inherit an invalid model preload configuration. Keep warmup behavior, but derive the fallback warmup profile from the detected last-workflow model stack instead of hardcoded environment variables.

## Problem

The current restore path seeds `COMFYMODAL_WARMUP_UNET`, `COMFYMODAL_WARMUP_CLIP1`, `COMFYMODAL_WARMUP_CLIP2`, `COMFYMODAL_WARMUP_VAE`, and `COMFYMODAL_WARMUP_CLIP_TYPE` with Flux2 values when they are unset. The Modal image env map also bakes in the same defaults. This makes unrelated workflows fail or warm up the wrong assets after cloning the repo, because the application silently behaves as if every deployment were a Flux2 setup.

## Goals

- Remove Flux2-specific hardcoded warmup profile defaults.
- Preserve warmup support for users who explicitly configure warmup env vars.
- Use the detected last-workflow model stack as the fallback source for warmup preload decisions.
- Keep no-stack behavior safe: no fake profile should be injected when nothing is known.

## Non-goals

- Redesign warmup execution.
- Remove explicit env-var-based warmup configuration.
- Change snapshot-key semantics beyond what naturally follows from removing the hardcoded defaults.

## Approach options considered

### Option 1 — workflow-stack fallback only

Remove the restore-time env injection and the image-level Flux2 defaults. Continue using existing stack-derived profile logic for preload and direct warmup. Explicit env vars still win when intentionally set.

This is the recommended option because it fixes the portability problem without deleting the warmup feature.

### Option 2 — partial fix

Remove only the restore-time injection but keep image-level defaults. This reduces one source of surprise but still leaves Flux2 assumptions in deployed environments.

### Option 3 — explicit-config-only

Require all users to define warmup env vars manually. This is simpler but worsens usability and discards the existing last-stack fallback path.

## Approved approach

Implement Option 1.

## Detailed design

### Runtime behavior

1. If explicit `COMFYMODAL_WARMUP_*` env vars are set, warmup continues to use them.
2. Otherwise, warmup fallback is derived from the detected last-workflow model stack.
3. If there is no explicit profile and no detected stack, warmup does not invent a profile.

### Code changes

1. Remove the restore-time block in `comfyapp.py` that injects Flux2 warmup env vars.
2. Remove the Flux2 `COMFYMODAL_WARMUP_*` entries from the Modal image env map in `comfyapp.py`.
3. Keep `load_warmup_profile()` and the stack-based fallback path intact.
4. Do not change unrelated warmup flags such as `COMFYMODAL_WARMUP_PROFILE`, `COMFYMODAL_WARMUP_PROFILE_VERSION`, or `COMFYMODAL_WARMUP_CLIP_ENCODE` unless tests show a direct dependency on the removed defaults.

### Test strategy

Add or update tests to verify:

- `restore()` no longer seeds Flux2 warmup profile env vars.
- The existing restore flow still uses stack-derived warmup behavior when a last stack exists.
- The no-profile, no-stack case behaves cleanly without fabricating Flux2 assets.
- Snapshot-key and runtime-config tests continue to pass with explicit env-var behavior unchanged.

### Error handling

If stack-derived assets are missing, existing validation remains responsible for surfacing the problem. This change should not add new fallback defaults that hide those errors.

## Risks and mitigations

- Risk: some existing tests may implicitly rely on Flux2 defaults. Mitigation: replace that assumption with explicit fixtures or stack-derived setup.
- Risk: some deployments may have depended on accidental image defaults. Mitigation: explicit env vars remain supported, and stack-derived behavior becomes the default fallback.

## Success criteria

- A fresh clone using a non-Flux workflow no longer inherits Flux2 warmup assets by default.
- Warmup still works for workflows with a detected last model stack.
- Explicit warmup env var overrides still function.
