# Production 009 — Phase 3 Addendum: pre-cohort writer works, one blocker left

Follows `P9_PHASE3_CLIP_CACHE_CONCLUSION.md`. **Gate still not passed; the
treatment is still not committed.**

## What changed

Option A was implemented: a pre-cohort publication step, so the cache is no
longer dependent on a downloader that the measured path never calls.

- `comfymodal_runtime/modal_app.py` — new `ModalRuntimeEntrypoint.publish_model_metadata_cache`.
  Sibling method to `source_identity_probe`, which was **not** modified (its
  docstring makes it contractually read-only). Never raises; returns structured
  per-model evidence. Not on the inference request path, not in `restore()`.
- `tools/v2_control/cli.py` — new top-level `v2ctl publish-model-metadata-cache`,
  inserted into the Golden sequence immediately after `source-probe`.
- `tools/v2_control/source_probe.py`, `comfymodal_runtime/golden_serial.py`
  (canonical folder constants), plus tests.
- Local suite: **627 passed** (was 623; +4), only the two pre-existing
  `test_rx9p_h_identity_chain` failures.

## The writer is proven to work

Deployment `ab12f0ed`, real containers, real volume:

```
cache_path              /root/comfymodal_runtime_state/caching_data/golden_model_metadata.bin
file_bytes              11817
runtime_config_volume   available
status                  ok
  clip  text_encoders/qwen_3_4b.safetensors              ok
  unet  diffusion_models/z_image_turbo_bf16.safetensors  ok
  vae   vae/ae.safetensors                                ok
```

So the earlier diagnosis was right and is now fixed: the cache **is** populated
from a container that outlives the write, off the inference path, idempotently,
at effectively no marginal cost — it reuses the class the cohort already starts.

## The remaining blocker: cross-container volume visibility

The very next true-cold run still reported the cache absent:

```
metadata_cache_schema  'absent'
metadata_cache_file_bytes  0
layout_cache_source    'runtime_parse'
valid=True  true_cold=True  sha_match=True
```

So the write lands and the read does not see it. Two candidate causes, in
likelihood order:

1. **No `reload()` before hydration.** `golden_model_metadata_cache.hydrate()`
   contains no `reload` call anywhere in the module. Modal Volumes only make one
   container's committed writes visible to another after an explicit
   `volume.reload()`; a container that materialised its view before the commit
   keeps reading the pre-commit state. The publish and the benchmark are
   different containers, which is exactly the case `reload()` exists for. Note
   the codebase already has this idiom — `reload_runtime_state()` in
   `modal_app.py` does `getattr(module, "runtime_config_vol", None)` then
   `volume.reload()`.
2. **Different physical volume.** `RUNTIME_CONFIG_PATH` is
   `/root/comfymodal_runtime_state` and the publisher resolves
   `comfyapp.runtime_config_vol`, while the deployed class mounts
   `RUNTIME_STATE_VOLUME_NAME = "comfymodal-runtime-config"`. Name and path
   agree, so this is less likely — but it is not excluded, and the publisher
   resolving a handle from `comfyapp` rather than from the class's own mounts is
   the kind of indirection that makes this possible.

Cause (1) is a small, local, testable fix. It could not be validated here
because the Modal workspace ran out of credit.

## Gate status

| check | result |
|---|---|
| local suite | **PASS** — 627 passed |
| writer populates the blob | **PASS** — 11,817 bytes, 3/3 models, volume available |
| reader sees the blob | **FAIL** — `schema='absent'`, `layout_cache_source='runtime_parse'` |
| tail improvement | **NOT DEMONSTRATED** |
| committed | **no** |

## Next step

Call `runtime_config_vol.reload()` once, early, in the inference container
before the first `hydrate()` — reusing the existing `reload_runtime_state()`
idiom rather than inventing a new mechanism — then redeploy, re-publish, and run
the 5-request serial true-cold cohort. Only commit if `layout_cache_source`
flips to `persistent` and `clip_meta_cache_hit` is true.

## Note on the workspace

The lane's destination is `Testing 9` (`ws_ee7221847f7d`), which is now out of
credit. `Testing 1` (`ws_e677ab553606`) is a stale deployment from 2026-08-06 on
comfyapp 2.16.30. Modal Volumes are workspace-scoped, so its models Volume is not
known to hold this cohort's three models, and completing the gate there may
require re-provisioning the weights. That is a provisioning decision, not a
patch, so it was not made unilaterally.
## Addendum 2: Testing 1 verified, and one hypothesis eliminated

Destination switched to Testing 1 (ws_e677ab553606) after Testing 9 ran out of
credit. Testing 1 is fully viable - no model reprovisioning needed.

| check | Testing 9 (ab12f0ed) | Testing 1 (dc69bfd6) |
|---|---|---|
| deploy | exit=0 | exit=0 |
| models present | 3/3 ok | 3/3 ok |
| blob written | 11817 B | 11811 B |
| volume handle | available | available |
| reader sees blob | absent | not yet run |

**Eliminated: wrong-volume.** Both sides resolve to the same volume.
`comfyapp.py` binds `runtime_config_vol = modal.Volume.from_name(
RUNTIME_CONFIG_VOLUME_NAME)` with `RUNTIME_CONFIG_VOLUME_NAME =
"comfymodal-runtime-config"`, and the deployed class mounts
`RUNTIME_STATE_VOLUME_NAME = os.environ.get(
"COMFYMODAL_RUNTIME_STATE_VOLUME", "comfymodal-runtime-config")`. Identical
name, identical mount path `RUNTIME_CONFIG_PATH =
"/root/comfymodal_runtime_state"`, identical blob path. The publish and the read
address the same physical volume.

**Also eliminated: missing reload.** `reload_runtime_state` is already a
wrapped restore stage and appears in the restore stage list, and the class
already calls `runtime_config_vol.reload()` on several paths. A reload does
happen; adding another is therefore not obviously the fix and was not applied.

**Remaining open question.** The read happens in a process that may not have the
runtime-config volume mounted. The Golden request path spawns separate
processes (`golden_io_process_v2`, `source_copy_probe`), and hydration is
reached through `golden_model_transport.py` / `golden_serial.py`. If the
hydrating process is a spawned subprocess rather than the container process that
mounts the volume, the blob is genuinely not visible to it and no amount of
`reload()` in the parent would help. This was not confirmed before the session
ended and is the single next thing to check.

Gate remains NOT passed. Treatment remains uncommitted.
