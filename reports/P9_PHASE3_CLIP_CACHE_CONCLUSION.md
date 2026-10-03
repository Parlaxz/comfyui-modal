# Production 009 — Phase 3 Conclusion: persistent CLIP layout/meta cache

**Verdict: NOT SUCCESSFUL.** The cache is correctly built, correctly fail-soft,
and completely inert on the measured path. It is **not committed**, because a
treatment that never activates has not passed its gate.

Starting SHA `95e90b26`. Lane `.slim/worktrees/p8fix`. Output SHA
`3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` verified on
every run.

## What Phase 3 asked

Healthy CLIP layout resolve is ~30.6 ms and metadata extraction ~46.4 ms, but
the same deterministic Python work balloons to ~1609 ms / ~1632 ms on sick
hosts. The prize is tail stability, not the median.

## What was built

Uncommitted in the lane (a failed treatment is not committed):

| file | role |
|---|---|
| `comfymodal_runtime/golden_model_metadata_cache.py` | new — blob format, identity, publish, hydrate |
| `comfyapp.py` | publication seam in `download_model_to_volume` / `download_model_stream` |
| `comfymodal_runtime/golden_model_transport.py` | `_parse_layout` consults the cache |
| `comfymodal_runtime/golden_serial.py` | `_clip_meta_state_dict_from_header` consults the cache |
| `tests/test_golden_model_metadata_cache.py` | new — 9 tests |

Design choices that are sound and worth keeping:

- **Identity** is `(canonical model-relative path, st_size, st_mtime_ns,
  SHA-256 of the raw SafeTensors JSON header)`. Not `st_dev`/`st_ino` (not
  stable across containers) and not `models_generation` (never advanced on
  download, so it would serve stale entries).
- **One normalized tensor table** — `(name, dtype, shape, offset, length)` —
  serves both `_parse_layout` and `_clip_meta_state_dict_from_header`. Tensor
  objects are never serialized.
- **Publication is owned by the downloader**, never by inference. This is the
  invariant the previous attempt violated, and it is respected.
- **Atomic publish**: temp file → `fsync` → `os.replace` → Volume commit.
- **Fail-soft** on absent / corrupt / wrong schema / truncated / stale / unknown,
  with corruption still visible in telemetry.
- Synthetic 3-model blob: 84,660 bytes, **12.5 ms** hydration (budget was 75 ms).

Local suite: **623 passed** (up from 614 by the 9 new tests), only the two
pre-existing `test_rx9p_h_identity_chain` failures.

## Why it does not activate — measured, not inferred

One true-cold cohort run on deployment `059bfab9`:

```
metadata_cache_loaded        = False
metadata_cache_schema        = 'absent'
metadata_cache_file_bytes    = 0
metadata_cache_hydration_ms  = 0.038
metadata_cache_entry_hit     = False
metadata_cache_identity_match= False
layout_cache_source          = 'runtime_parse'   (all 3 layout sites)
clip_meta_cache_hit          = False
residual_meta_build_ms       = 2.357
valid=True  true_cold=True  sha_match=True
```

The blob does not exist at request time, so every site correctly falls back to
the canonical parse. There are **two independent reasons**, either of which is
sufficient:

1. **The downloader is not on the cohort path.** `download_model_to_volume` /
   `download_model_stream` are reachable only from the user-facing APIs
   (`modal_client.py:727`, `__init__.py:4606`). No Golden runtime code calls
   them — the only `download` references under `comfymodal_runtime/` are the
   new cache module's own docstrings, and every `download` hit under `tools/` is
   a *trace artifact* download, not a model download. The cohort's models were
   provisioned onto the persistent Volume outside the measured path.

2. **The downloader early-exits before publishing.** `comfyapp.py:9529` and
   `:9582` both do `if dest.exists(): return ... skipped`. On a volume that
   already holds the weights — which is the normal case for a persistent Volume
   and certainly the case for every run in a cohort — control returns before the
   publication call, so nothing is written even when the downloader *is*
   invoked.

Cause (2) was found by review and fixed: publication now also runs on the
already-present path in both functions, and is idempotent because it is keyed by
model identity and merged into the blob. Cause (1) is **not** fixed, because
fixing it means choosing a new publication point, which is a design decision
rather than a patch.

## The trap worth recording

The design rule "publish at the downloader, never in inference" is right about
*which container owns the write* — it is exactly what the previous attempt got
wrong by writing from a daemon thread inside a dying single-use inference
container. But the rule as applied here silently assumes the downloader runs
during the measurement. It does not. A cache whose only writer is off the
measured path is indistinguishable from no cache at all, and it fails *quietly*:
the run stays valid, the SHA still matches, and the only symptom is
`layout_cache_source=runtime_parse`.

The generalisable lesson: **a persistent cache needs a verified writer on the
measured path before its hit rate means anything.** Checking that the reader
falls back safely is not evidence that the writer ever runs.

## What unblocks Phase 3

Publication must happen in a container that (a) is not the inference request
path and (b) outlives the write. Candidates:

1. **A sanctioned pre-cohort provisioning step** that invokes the downloader (or
   a dedicated one-shot metadata-prebuild function) once before the cohort, then
   commits the Volume. Aligned with the existing design; adds a small, explicit
   step to the run pipeline. This is the preferred option.
2. **Synchronous publication during `restore()`** (`snap=False`), which we have
   already established is snapshot-safe for Triton work. It would be durable and
   correctly ordered, but it is inference-container publication, which the
   design forbids, and it writes on every container start.

Option 1 preserves every invariant that Phase 2 and Phase 3 established. It
should be built and gated before any Phase 3 commit.

## Gate status

- Local tests: **PASS** (623 passed).
- Production effectiveness: **FAIL / not demonstrated** — the cache is never
  populated, so there is no cohort result to compare.
- Committed: **no**. Only this report is committed.