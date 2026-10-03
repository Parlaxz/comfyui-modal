# Production 009 — Phase 3 Result: persistent CLIP layout/meta cache

**Verdict: SUCCESSFUL.** The cache activates, is fail-soft, and removes the
CLIP layout resolve from the request path. Committed.

Output SHA `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`
verified on every run in the cohort.

## Result

Deployment `8d889d24`, 5 serial true-cold runs:

| run | valid | true_cold | sha | layout_cache_source | clip_meta_cache_hit |
|---|---|---|---|---|---|
| 1 | yes | yes | match | persistent | true |
| 2 | yes | yes | match | persistent | true |
| 3 | yes | yes | match | persistent | true |
| 4 | yes | yes | match | persistent | true |
| 5 | yes | yes | match | persistent | true |

Against the runtime-parse control:

| metric | control | treatment | delta |
|---|---|---|---|
| `layout_resolve_ms` | 31.16 | **1.01** | **-30.16 ms (-97%)** |
| `layout_lookup_ms` | n/a | **0.00** | free |
| `meta_sd_build_ms` | 36.31 | **33.11** | -3.20 ms |
| `metadata_cache_hydration_ms` | n/a | 5.50 - 7.83 | off the request path |

`residual_meta_build_ms` is 0.98 - 2.97 ms, so the metadata blueprint is served
from RAM and only the tensor objects are constructed. Budget was 75 ms; the
measured hydration is 5.5 - 7.8 ms and happens during `restore()`.

## Three defects that had to be found first

The first working version still reported `metadata_cache_schema='absent'` on
every run while the publisher cheerfully reported success. Each of these failed
*quietly* - the run stayed valid and the output SHA still matched.

### 1. The publisher was writing into the container, not the Volume

`CACHE_PATH` was `/root/comfymodal_runtime_state/...`. That is
`comfyapp.RUNTIME_CONFIG_PATH`, where the **legacy** `ComfyAPI` class mounts the
runtime-state Volume. The deployed class is `ModalRuntimeEntrypointV2`, which
mounts the *same* Volume at `modal_app.RUNTIME_STATE_PATH =
"/mnt/comfymodal_runtime_state"`.

So from a V2 container `os.makedirs()` created an ordinary directory, the blob
was written into it, and `runtime_config_vol.commit()` committed a Volume that
had never been written to. The bytes died with the container. The publisher
reported `status: ok` and a real `file_bytes` because from its own point of view
it had genuinely written a file - just not to the Volume.

`CACHE_PATH` now derives from `COMFYMODAL_V2_STATE_VOLUME_ROOT` (which the V2
runtime already exports) and defaults to the V2 mount. Pinned by
`test_cache_path_lives_inside_the_v2_runtime_state_mount`.

### 2. A `hydrate()` miss was memoized for the container's lifetime

`hydrate()` cached its result unconditionally, including the "not there yet"
case. Any probe that ran before the Volume became visible pinned the cached
state to `absent` for the rest of the container's life, and every later lookup
returned the stale miss. `hydrate()` now memoizes only a successful load; a miss
costs one `stat()` and is re-checked. Pinned by
`test_a_miss_is_not_memoized_so_a_late_blob_is_still_seen`, which fails against
the old code.

This was found while chasing the reload hypothesis; the reload was a red
herring. `reload_runtime_state` already reloads the Volume during restore.

### 3. Identity verification re-read the header, making the cache a net loss

With the cache finally visible, the first cohort showed it was *slower* than the
control: `layout_resolve_ms` 39.56 versus 31.16, because every lookup re-read
the SafeTensors header off the Volume to recompute `header_sha256` - about as
much work as the parse being avoided.

Identity is now `(path, size, mtime_ns)` on the fast path, with the header
digest used only as the tiebreaker when the cheap identity disagrees. `size` and
`mtime_ns` change on any modification, so the common case is a single `stat()`,
and a rewritten file is still rejected. That moved `layout_lookup_ms` to 0.00 and
`layout_resolve_ms` to ~1 ms. Pinned by
`test_lookup_hits_on_stat_identity_without_rereading_the_header`, which asserts
`_header_bytes` is never called on the fast path.

## Design

- **Identity**: `(canonical model-relative path, st_size, st_mtime_ns,
  header_sha256)`. Not `st_dev`/`st_ino` (not stable across containers) and not
  `models_generation` (never advanced on download, so it would serve stale
  entries).
- **One normalized tensor table** - `(name, dtype, shape, offset, length)` -
  serves both `_parse_layout` and `_clip_meta_state_dict_from_header`. Tensor
  objects are never serialized.
- **Publication is owned by a container off the inference path.** A first
  attempt published from the model downloader, which no Golden runtime code
  ever calls. The working seam is `ModalRuntimeEntrypoint
  .publish_model_metadata_cache`, a sibling of the read-only
  `source_identity_probe` (whose body was not modified - its docstring makes it
  contractually read-only), exposed as `v2ctl publish-model-metadata-cache` and
  inserted into the Golden sequence immediately after `source-probe`. It
  publishes the three static cohort models and commits the Volume once. It is
  idempotent (`status: noop` when nothing changed) and never raises.
- **Hydration is warmed during `restore()`**, right after
  `reload_runtime_state()`. First-touch Volume I/O costs ~464 ms when it lands
  on the request path and 5.5 - 7.8 ms when it does not, so this alone was worth
  more than the parse it replaces. It only reads; it never publishes.
- **Fail-soft**: absent / corrupt / wrong schema / truncated / stale / unknown
  all fall back to the canonical parse, with corruption visible in telemetry.

## Local suite

**631 passed** (baseline was 614; +17 across the cache and CLI tests). The only
failures are the two pre-existing `tests/test_rx9p_h_identity_chain.py` cases,
which also fail on a pristine `production-007` tree.

## The lesson worth keeping

Every one of these three defects passed the obvious check. The publisher said
`ok`. The runs were `valid`. The output SHA matched. The suite was green. Each
failure was only visible by asking a question the telemetry had not been asked
before: *is the writer writing to the thing the reader reads?*, *can a late
arriving blob ever be seen?*, and *is the cache actually faster than the thing
it replaces?*

A persistent cache has two halves and the dangerous one is not the read. It is
worth stating plainly: a treatment that is correct, tested, fail-soft, and
completely inert looks exactly like a success in every artifact except the one
that matters.