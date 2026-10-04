# Production 009 Phase 3 — design, grounded in code recon

Read-only reconnaissance against `.slim/worktrees/p8fix` @ `d4613e19`. Every
`file:line` below was verified in code, not inferred. Phase 3 is **not
implemented**; this records the design so the work is not lost and the
ordering rule (no Phase 3 implementation before a written Phase 2 conclusion)
is respected.

## 1. The seam: publication must happen outside inference

The whole point is that the previous attempt failed because the publisher lived
inside a dying single-use container. The correct owner already exists.

**Chosen seam — `comfyapp.py:9496-9538` `download_model_to_volume`:**

```
HTTP stream -> write .part -> size validation
  -> os.replace(.part, dest)      line 9536   <- "the file now exists and is complete"
  -> vol.commit()                line 9537   <- durable in the models Volume
```

This is a **dedicated download Modal function** with
`volumes={MODELS_PATH: vol}` — not the inference request container. That is
exactly the lifecycle property the previous attempt lacked.

`download_model_stream` (`comfyapp.py:9548-9597`, rename 9595, commit 9596) has
the same shape. `batch_download_models` (`9607-9615`) delegates via
`.starmap`, so the per-file seam stays line 9536.

Rejected as seams:
- `sync_custom_nodes_to_volume` (`comfyapp.py:9677-9828`) writes the
  **custom-nodes** Volume, not models.
- Anything on the inference/restore path — that is the failure mode being fixed.

## 2. Identity: `st_dev`/`st_ino` must NOT be authoritative

Current identity is `(st_dev, st_ino, st_size, st_mtime_ns)` at
`golden_model_transport.py:313-320`.

Verified: `cross_source_runs/DELIVERABLE.md:71-78` observed two files on the
same Volume sharing a device number (`st_dev=31`, differing `st_ino` 4 and 6),
with `/tmp` on a different device (`st_dev=18`).

**Not verified anywhere in the repo: that `st_dev`/`st_ino` are stable across
separate Modal containers, Volume reloads, snapshot restores or remounts.**

So they may remain a *local* fast-path discriminator but must not be the
cross-container proof of freshness.

### A second finding that changes the identity choice

`models_generation` lives at
`/root/custom_nodes_vol/.comfymodal_control/models_generation.json`
(`comfyapp.py:1922-1926`), written by `_write_models_generation_record`
(`1971-1992`). The **only** call found is at `comfyapp.py:18990-18997`, which
initialises the baseline **if the record is absent**. No download path advances
it.

That means today `models_generation` is **not** a reliable freshness signal
after a model download or replacement. The task lists it as a candidate
identity component, but keying on it without also fixing the writer would serve
stale metadata — a correctness bug, not a missed optimisation.

### Chosen identity

Per model entry, at the ingest seam where the file is known complete:

| component | why |
|---|---|
| canonical model-relative path | stable across containers; the model's identity in this architecture |
| `st_size` | cheap, changes on any real content change |
| `st_mtime_ns` | cheap, changes on rewrite |
| safetensors **header SHA-256** | the authoritative content proof, computed once at ingest |

Deliberately **not** `st_dev`/`st_ino` (unproven across containers) and **not**
`models_generation` (not advanced on download today). If generation-based
identity is wanted later, advancing the generation on download must land first
as its own change — it is not this phase's job to silently alter that
counter's semantics.

No full-file hash: the models are 8–12 GiB. The header digest is a few KiB and
is the only content actually consumed.

## 3. What must be cached (both consumers, one representation)

Two independent consumers parse the same header today:

1. `_parse_layout` — `golden_model_transport.py:343-389`. Reads the file
   directly: `st_size` (344), 8-byte header length (345-349), header bytes
   (352), JSON decode (353), then per-tensor dtype/shape/`data_offsets`
   (360-386). Needs path, identity, size, header tensor entries, dtype, shape,
   offsets.

2. `_clip_meta_state_dict_from_header` — `golden_serial.py:2217-2237`, called
   from `2341-2349`. Calls
   `clip_qd_reader.parse_safetensors_header(path)` at `2220`, then applies
   `_clip_te_normalize_sd_keys`. Needs tensor names, dtype strings, shapes.
   **The header's `__metadata__` is ignored by this function**, so the cache
   need not carry it.

So **one** normalized tensor table — `(name, dtype, shape, offset, length)` —
serves both. The layout resolver needs the offsets; the meta builder needs
name/dtype/shape. Storing two representations would recreate the drift the
previous attempt risked.

Store the compact blueprint; construct any unavoidable lightweight meta
tensors from it at hydration. No giant tensor objects are serialized.

## 4. Storage and Volume mechanics

- Models Volume -> `MODELS_PATH`; custom nodes -> `CUSTOM_NODES_PATH`;
  runtime config -> `RUNTIME_CONFIG_PATH` (`comfyapp.py:9470-9482`).
- The reverted implementation's established path was
  `/root/comfymodal_runtime_state/caching_data/golden_model_metadata.bin` on
  `runtime_config_vol`. Reuse it: one file, kept separate from weight files.
- Established rule from the reverted code, reconfirmed here: a Volume write is
  **not durable/visible to later containers until `commit()`**, and a later
  container needs `reload()` to see a prior committed state.

Publication: temp file -> fsync -> `os.replace` -> `vol.commit()`. One writer.

## 5. What not to repeat

The previous failure (`79a2414e`, `83ae83cd`, reverted in `b2c0f82c`):

- `_schedule_metadata_cache_publish` started a **daemon thread inside the
  inference container**; the single-use container exited before durable
  publication was useful.
- The follow-up correctly added `volume_reload()` before hydration and
  `volume_commit()` after publication, but that did not fix the lifecycle bug:
  publication still depended on a dying inference container staying alive.

**Hard rule:** no cache publication, commit, or durability work in an
inference-container daemon thread. The downloader owns it.

Also excluded by the task: background inference publisher, daemon writer,
multi-file cache, SQLite/database, journal, sharding, distributed lock
framework.

## 6. Inference read path

```
restore
  -> volume_reload()            (see prior committed metadata)
  -> read ONE blob              (file open/read)
  -> deserialize + validate schema
  -> install RAM index
  -> CLIP layout lookup  +  meta blueprint lookup   (RAM only)
```

Fail-soft is mandatory: **absent, corrupt, wrong schema, stale, unknown model**
must never make an otherwise-valid model fail. Fallback to the existing
canonical `_parse_layout` / `parse_safetensors_header` path must stay correct
and unchanged. Corruption must be visible in telemetry even though it is not
fatal.

Hydration target `<75 ms` consistently; prior evidence was ~86 KB / ~0.3 ms
local deserialize, so anything far larger needs an explanation.

## 7. Required telemetry

Per CLIP load:
`metadata_cache_loaded`, `metadata_cache_schema`, `metadata_cache_file_bytes`,
`metadata_cache_hydration_ms`, `metadata_cache_entry_hit`,
`metadata_cache_identity_match`, `layout_cache_source`
(`persistent|runtime_parse`), `clip_meta_cache_hit`, `residual_meta_build_ms`.

Separately measure: cache hydration, layout lookup, meta blueprint lookup, and
the unavoidable meta-object construction, so any residual cost is attributable.

## 8. Open item to resolve during implementation

Whether the CLIP model actually arrives through `download_model_to_volume` on
this deployment, or is baked into the image / synced by another route. The
recon verified the downloader is a correct seam **if** it is the arrival path.
If the production CLIP arrives another way, publication needs an equivalent
non-inference ingest seam, and the cache must fail soft when no entry exists.
This must be checked before the cache can be claimed effective rather than
merely correct.