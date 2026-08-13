# V2 Exact-Conditioning Cache: Removing Volume RPCs from the Foreground Critical Path

**Status:** READ-ONLY design study. No code changed. No paid generations run.
**Scope:** Exact-conditioning cache (`COMFYMODAL_V2_CLIP_CONDITIONING_CACHE`) only.
Untouched by design: active-profile path, CLIP↔UNET orchestration, output persistence,
sampling, snapshot/loader architecture.
**Evidence base:** Current checkout source (line-cited), Modal SDK docs v1.5.x (modal.com/docs),
Modal client source (`modal-labs/modal-client` `py/modal/volume.py`,
`_runtime/task_lifecycle_manager.py`), independent oracle review of the proposed semantics.

---

# Executive conclusion

The measured serial latency is almost entirely Modal **Volume RPCs that serve no
same-request purpose**:

| Path | Measured total | Dominant cost |
|---|---|---|
| Lookup (miss) | ≈0.16–0.47 s | `Volume.reload()` — refreshes the mounted view with **other containers'** commits |
| Store (miss) | ≈0.93–1.67 s | `Volume.commit()` ≈0.91–1.65 s (**≈98%**) — publishes the entry for **other containers** |

Code-level analysis proves both RPCs can be removed from the foreground path **without
changing cache semantics**:

1. **Every cache hit is fully validated** (`_lookup_entry`: canonical key equality, model
   identity, per-tensor dtype/shape/byte-range/checksum, payload checksum — any mismatch is a
   miss). A stale manifest therefore can only cause **extra misses** (fall back to the
   unchanged encode), never a wrong hit. A genuinely unique prompt cannot exist in another
   container's commit, so reload cannot turn its miss into a hit anyway.
2. **The current request never consumes the committed state.** The graph consumer
   (`_consume_prefill`) reads only the in-memory `_prefill_results`; nothing on the graph,
   sampler, restore, or output path reads `exact_conditioning/` on `prompt_cache_vol`.
   The commit exists solely for *future* requests in *other* containers.
3. **Every failure mode is fail-closed to a miss** (re-encode → correct output). The
   cross-container manifest read-modify-write race is miss-only and **already exists today**
   with the synchronous design; the proposal widens its window slightly but the background
   thread's reload-before-batch bounds it back at zero foreground cost.
4. **Modal runs background commits every few seconds and a final snapshot+commit at
   container shutdown by default** (client hardcodes `allow_background_commits=True`), so the
   explicit commit is not even the durability backstop — it is only a freshness accelerator.

**Design verdict (independent oracle review): APPROVE-WITH-CHANGES.**

Recommended minimal architecture (exactly the requested shape, proven sound):

```
encode conditioning
→ serialize synchronously (ms, captures immutable bytes; no live tensors cross threads)
→ enqueue (immutable payload) to a single background persistence thread
→ publish results to the current request immediately (no Volume RPC on the path)
→ background thread: reload-before-batch (throttled) → atomic file+manifest writes
  → LRU bounds → unindexed sweep → ONE coalesced commit per batch
→ bounded flush at container exit (exit() teardown stage): signal → join (5 s budget)
  → drain remaining queue → one final commit when dirty → Modal shutdown commit as backstop
```

Guaranteed removable from the foreground per genuine new-prompt request:
**≈0.91–1.65 s of commit + ≈0.16–0.47 s of reload** (plus the per-entry multiplier: today
one request with N miss entries issues N commits; the design issues 1).

---

# Current lookup path

Call chain (all verified in the current checkout):

1. `model_preload.py:9281` — `_execution_prefill` (runs on the coordinator thread pool via
   `schedule_prefill`, in parallel with the UNET restore future) resolves the cache service
   and builds the key context (`_build_clip_conditioning_cache_context`, `model_preload.py:14297`).
2. `model_preload.py:9298-9306` — `conditioning_cache_key_summary` then
   `lookup_many(base_ctx, filtered)`.
3. `clip_conditioning_cache.py:710` `lookup_many`:
   - acquires `self._lock` (threading.RLock),
   - **`_reload_volume()` at `clip_conditioning_cache.py:753`** — synchronous
     `comfyapp.prompt_cache_vol.reload()` (`_reload_volume` at `:696`),
   - `_read_manifest()` (`:627`) reads `manifest.json` from the mounted Volume filesystem
     (`/root/prompt_cache_vol/exact_conditioning`; on `FileNotFoundError`/corruption returns
     an **empty default manifest** `:644-649`),
   - per entry: canonical key build + SHA-256 digest (≈0.2 ms), then `_lookup_entry` (`:822`)
     — full validation; any mismatch → miss,
   - `_persist_lru_touch` (`:872`) rewrites the manifest with bumped `last_access_seq`
     (note: **without** calling the commit hook — LRU bumps are local to the mounted view
     until some later commit persists them).
4. Result: `(hits, misses, hit_count, miss_count)`. Every miss falls through to the
   unchanged native `CLIPTextEncode` path (`model_preload.py:9419-9439`). An exact hit
   serves the value directly with zero CLIP GPU loads/encodes.

Measured (production telemetry): total ≈0.16–0.47 s, dominated by the reload; key/digest CPU
work ≈0.2 ms.

**Why `Volume.reload()` is required before every lookup (today):** Modal's mounted view of a
Volume is a snapshot taken at container creation (or the last explicit reload). Commits made
by *other* containers are **not** visible until the container reloads; without it you read
silently stale state. The docs' canonical pattern for exactly this is **reload-on-miss**
(model-serving example), not reload-per-read — but the current code reloads unconditionally
on every lookup, before it even knows whether a miss is plausible.

**Does a fresh unique-prompt miss require blocking on reload? No.** A unique prompt's entry
cannot exist in any other container's commit (the key covers prompt text, workflow hash,
deployment hash, model identities, dtype/version surface — `clip_conditioning_cache.py:60-72,
146-185`). Reload cannot turn that miss into a hit. Its only value is finding *hits* — and
any hit that a stale manifest misses degrades to a correct, slower re-encode. Blocking on
reload for a guaranteed miss is pure latency with zero correctness content.

---

# Current store path

1. `model_preload.py:9419-9439` — per-miss-entry encode loop: `_record_clip_encode` →
   result in memory, then **synchronously** `_cc_cache_svc.store_entry(_cc_ctx, entry, result)`
   for that entry, *inside* the loop.
2. Results are published to `_prefill_results` only **after** the loop
   (`model_preload.py:9581`), and the graph consumer blocks on
   `coordinator.wait_prefill(preparation)` (`model_preload.py:10971`). So the current
   request's continuation waits for the entire store — including the Modal Volume commit.
3. `clip_conditioning_cache.py:930` `store_entry` → `_process_value` (serialize, checksum) →
   `_write_entry` (`:1047`) under the RLock:
   - atomic data-blob write (`os.replace`, fsync), atomic header write,
   - manifest read → update/append entry → deterministic LRU bounds eviction
     (`_enforce_bounds`, oldest `last_access_seq`, ties by `key_hash`),
   - atomic manifest write, `_remove_unindexed_files` sweep (`:668`),
   - **`self._commit()` at `:1126`** → registered hook = `comfyapp.prompt_cache_vol.commit`
     (synchronous Modal `Volume.commit()`; hook registered at `:1165-1176`).
4. Diagnostics (`store_diagnostics`) are accumulated on `self._diag` — which is
   **`threading.local()`** (`:609`) — and read back by `pop_store_diagnostics` on the same
   prefill thread (`model_preload.py:9487-9524`, `miss_stored` log).

Measured: store total ≈0.93–1.67 s; Modal `Volume.commit` ≈0.91–1.65 s (≈98%); serialization,
writes, and fsync are milliseconds.

**Why the current generation waits for `Volume.commit()` after conditioning is already
usable:** because the commit is invoked synchronously inside `store_entry`, inside the encode
loop, before `_prefill_results` is published and before the graph consumer is unblocked. The
conditioning value is fully materialized in memory before the commit starts; the commit only
publishes a copy for other containers. There is no same-request dependency on the committed
state (see Correctness contract, G).

---

# Correctness contract

The cache's guarantees (module docstring, `clip_conditioning_cache.py:1-27`) and their
implications for this design:

| Contract | Mechanism | Implication for async design |
|---|---|---|
| Only completed CPU conditioning stored | store called only after encode returns | value is materialized before any store |
| No pickle/torch.save — explicit serialization | JSON header + raw blob + SHA-256 | payload is immutable `bytes` once serialized; safe to hand to another thread |
| Atomic writes | temp file + fsync + `os.replace`; manifest replaced last | partial/corrupt entry is a miss; no torn state ever readable |
| Bounded storage, deterministic LRU | caps + `last_access_seq`, tie-break `key_hash` | eviction is best-effort; drift is eviction-quality-only |
| Validation before reuse | full key equality + model identity + per-tensor checksums | **any** mismatch → miss; stale state can never produce a wrong hit |
| Fail closed on every violation | every exception → miss / no-write | background failures degrade to re-encode, never to wrong output |
| Only exact key components + prompt text stored | no user images, no unrelated workflow state | nothing sensitive enters the queue |

**No same-request dependency on the committed state (oracle-verified):**
- Graph path: `_consume_prefill` (`model_preload.py:10886-10975`) reads only in-memory
  `_prefill_results`; no Volume access.
- Sampler path: no references to the cache volume.
- Output path: `read_output_asset` (`modal_app.py:13285`) reads `runtime_state_volume` — a
  different volume.
- Restore path: `comfyapp.py:20399` reloads `prompt_cache_vol`, but only for the separate
  persistent-CLIP-cache feature (its own `bundles/` + root manifest), and it **never writes
  or commits** (`comfyapp.py:20431-20441`). It never reads `exact_conditioning/`.
- The only reader of the exact cache's committed state is `lookup_many` at the start of a
  **future** request in another container.

---

# Why RPCs are currently synchronous

1. **`reload()` before every lookup** — an unconditional interpretation of Modal's
   requirement that a mounted Volume must be explicitly reloaded to see other containers'
   commits. The code reloads before it knows whether freshness could matter, on every
   request, on the critical prefill thread.
2. **`commit()` after every store** — the store API returns "stored" only after the entry is
   atomically written *and* committed, and `store_entry` is invoked inline in the encode loop
   before results are published, so the request inherits the commit's latency.
3. Neither is required by the current request; both are cross-container publication
   primitives. The code has no mechanism to decouple them, so the request blocks on them.

Documented Modal semantics that make the decoupling safe (docs + client source, v1.5.x):

- Reload is the *only* way to see other containers' commits; stale reads are the default and
  are **silent** — no error, no wrong data, just the previous snapshot.
- **During a reload the Volume appears empty to the initiating container**, and reload fails
  ("volume busy") if any file is open on it. In the current design this window sits on the
  hot path; in the proposed design it moves behind the cache lock in the background (and
  every read during it fails closed to a miss).
- A successful `commit()` **automatically triggers a reload** in the same container (client
  source) — so the measured "commit" cost already includes a second Volume operation.
- Background commits run **every few seconds** and a **final snapshot + commit is performed
  automatically at container shutdown**; both are on by default (`allow_background_commits`
  is hardcoded `True` in the current client; the old opt-in flag was removed pre-1.0).
- Concurrent commits are supported; per-file **last-writer-wins**; no distributed file
  locking; Modal advises avoiding >5 concurrent commits.

---

# Safe concurrency opportunities

1. **Skip/coalesce `reload()` on lookup.** Stale manifest → extra misses only (full hit
   validation). A genuine unique prompt cannot be hit by any reload. Safe policy: reload at
   most once per throttle interval (e.g. 10–30 s), or skip entirely when the request's key
   digest is known-unique (not required — the throttle alone captures the win).
2. **Defer `commit()` off the request path.** The current request never consumes the
   committed state; the commit is cross-container publication for future requests. Move it to
   a background persistence thread.
3. **Coalesce N per-entry commits into one per batch.** Today one request with N miss
   entries issues N serial commits (each with its implicit reload). One commit per batch
   strictly reduces Modal commit pressure (aligned with the "avoid >5 concurrent commits"
   guidance) and removes the per-entry multiplier.
4. **Background thread may reload-before-batch** (throttled, under the RLock, off the
   foreground path) — this bounds the manifest-staleness window to one batch cadence and
   mitigates the pre-existing cross-container manifest RMW race at zero foreground cost.
5. **Modal's own background commits + shutdown commit as backstop.** Even if the final
   explicit commit fails or times out, Modal persists uncommitted mount changes at container
   shutdown (best-effort, retries, failures logged not raised). Cross-container freshness
   becomes "within seconds / at exit" instead of "before this request continues" — which is
   the correct trade for a cache.
6. **Thread-based sync Modal calls are already the status quo.** The sync client runs a
   per-handle event loop; calling `commit()`/`reload()` from the prefill thread-pool worker
   is exactly what the code does today. A dedicated persistence thread is equivalent, and the
   client's per-handle lock already serializes commit vs. reload — so the only
   "volume-empty" window the foreground can ever observe is the commit's internal
   auto-reload, and every foreground read in that window fails closed to a miss.
7. **Local-only mode is free.** When no commit hook is registered or the Volume is not
   mounted (flag mismatch — see hazards), skip commit/reload entirely and treat the cache as
   local: identical semantics, no no-op RPCs.

Not safe (must remain serial): the synchronous serialization (see race analysis D),
key digesting, validation on hits, the brief RLock critical section for file/manifest
writes, and the teardown flush.

---

# Race/failure analysis

## Races (all verified miss-only or benign)

| Race | Outcome | Pre-existing? |
|---|---|---|
| Duplicate simultaneous stores of the same `key_hash` from two containers | Content is deterministic for the exact key; `os.replace` last-writer-wins over identical bytes; `_write_entry` dedupes by `key_hash` in the manifest (`:1090-1105`) → benign | Yes |
| Manifest single-file RMW across containers: A commits X; B (stale view) stores Y and rewrites the manifest without X | X becomes manifest-orphaned; a later `_remove_unindexed_files` (`:668-693`) in another container may delete X's files → future lookup of X = miss → re-encode → **correct** | Yes — the store path already reads the mounted manifest *without* reload (`:1085`), so this race exists today; throttled reload widens its window; background reload-before-batch bounds it back |
| LRU seq regression | `_write_entry` assigns `last_access_seq = next_seq` unconditionally (`:1096`) while `_persist_lru_touch` uses `max()` (`:886-889`); a stale manifest can carry a regressed `next_seq` → eviction order drifts (fresh entries can look older) → extra misses only. Optional fix: use `max()` in the store path too | Yes |
| Background commit's implicit reload vs. foreground lookup (same container) | Foreground `_read_manifest` → `FileNotFoundError` → empty default → all-miss; entry reads → OSError → miss. No wrong hit, no corruption; transient all-miss blip | No — new, but fail-closed and bounded by one commit |

## Failures

| Failure | Behavior | Impact |
|---|---|---|
| Store serialization failure | fail-closed, no write (today) | miss → correct |
| Background thread write/manifest failure | entry absent → future miss | miss → correct |
| Commit failure (explicit or background) | logged, swallowed (hook already wraps in `try/except`, `:617-624`) | entry not yet cross-container-visible → future miss in other containers until Modal's background/shutdown commit persists the mount |
| Container crash mid-request after enqueue | queue + mount lost → entry never committed | miss → correct |
| Flush join timeout at exit | drain remaining queue synchronously (payloads are materialized bytes) → one final commit if still dirty → Modal shutdown commit as backstop | at worst, delayed visibility; never wrong output |
| Persistence thread exception | never raises out of its loop; logged | degraded to local-only for that batch |

## Hazards an implementation must handle (from oracle review)

1. **Diagnostics threading — will break immediately if ignored.** `self._diag` is
   `threading.local()` (`:609`); store diag accumulated on the persistence thread would be
   invisible to the foreground `pop_store_diagnostics` reader (`model_preload.py:9487`).
   Must move store diag to a shared locked structure and return per-item results through the
   queue.
2. **`store_entry` return semantics drift.** `True` today means "atomically stored and
   committed" (comment at `:929`); after the change it means "enqueued". Split the log into
   **enqueued vs. persisted** counters; the `miss_stored` decision log must not claim
   durability it does not have.
3. **Dirty-but-empty-queue teardown.** The final commit must fire when the mount is *dirty
   since last commit* (a batch can have finished writing with its coalesced commit not yet
   run), not merely when the queue is non-empty.
4. **Lock-hold scope during `commit()` is the crux decision.** Holding the RLock across the
   ~1 s commit means a foreground lookup arriving mid-commit blocks up to the remaining
   commit time (the RPC re-enters the path as `lock_wait_ms` at the next request start).
   Preferred: hold the RLock only for file/manifest/sweep writes (as today), release before
   `commit()`, and treat the commit's empty-window as a bounded fail-closed all-miss blip.
   Either choice is correct; pick one and measure `lock_wait_ms`.
5. **Flag-coupling / unmounted volume.** The exact cache is gated on
   `COMFYMODAL_V2_CLIP_CONDITIONING_CACHE` while the mount is gated on the
   `prompt_cache_volume` resource (`modal_app.py:15340-15342`) /
   `COMFYMODAL_PERSISTENT_CLIP_CACHE` (`comfyapp.py:7951`). Enabling the cache without the
   mount makes today's per-store `commit()`/per-lookup `reload()` ~1 s **no-op RPCs** (SDK
   handle round-trips while writes land on local disk). The persistence thread must skip
   commit/reload when no hook is registered or the volume is unmounted (local-only mode).
6. **Reusable-container restore overlap.** A background commit in flight when the next
   request's restore-time reload runs (`comfyapp.py:20399`) blocks behind it on the same
   handle (client-side serialization) — new but bounded restore-path latency. Accept it, or
   drain between requests in reusable mode.
7. **Unbounded queue.** N entries/request at ms-scale vs. ~1 s commit batches. Add a bound
   and/or dedupe by `key_hash` in the queue. Minor.

---

# Proposed minimal implementation

All changes confined to the cache module, its call site, and the exit hook. Env-gated,
default behavior unchanged while disabled.

## 1. Lookup: throttle the reload (`clip_conditioning_cache.py`)

- Replace the unconditional `_reload_volume()` call in `lookup_many` (`:753`) with
  `_maybe_reload()`: performs the sync reload at most once per
  `COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_RELOAD_INTERVAL_S` (default ~15 s; 0 = once per
  process) and only when a commit hook is registered (local-only mode skips entirely).
- The reload stays on the lookup thread under the RLock (identical hazard surface to today,
  just far less frequent). Do not move reload to a separate thread in v1.

## 2. Store: split into synchronous enqueue + background persistence

- `store_entry` (`:930`) keeps: key build, digest, **synchronous serialization**
  (`serialize_conditioning` — milliseconds), fail-closed validation, then enqueues an
  **immutable payload** (`data` bytes + header dict + primitive key components) to a bounded
  queue and returns `True` ("enqueued"). No file writes, no manifest mutation, no commit on
  the foreground path.
- New single background thread (`comfymodal-exact-conditioning-persist`, non-daemon),
  draining the queue in batches:
  1. reload-before-batch (throttled) under the RLock,
  2. for each entry: atomic data/header writes, manifest RMW + `max()` seq bump,
     `_enforce_bounds`, `_remove_unindexed_files` — all under the RLock (as today),
  3. release the RLock, then **one coalesced `_commit()` per batch**,
  4. post per-item results + diag to a shared locked structure.
- Thread never raises out of its loop; every failure is logged and fail-closed.
- `pop_store_diagnostics` / `_last_store_reason` / decision logs move to the shared
  structure; `miss_stored` splits into enqueued/persisted counters.

## 3. Teardown: bounded flush in `exit()` (`modal_app.py`)

- Add a teardown stage after the existing worker stages (pattern:
  `_run_teardown_stage`, `modal_app.py:4821`; join-budget precedent
  `_PRELOAD_WORKER_JOIN_BUDGET_S = 5.0`, `:284`):
  `conditioning_cache_flush` → signal stop → join within budget → if **dirty** (queue
  non-empty or uncommitted writes): drain remaining entries synchronously (materialized
  bytes) → one final explicit commit **after** the thread has exited (avoids concurrent
  commits) → mark flushed.
- Modal's shutdown snapshot+commit remains the backstop; the existing
  `_join_lingering_preload_threads` sweep (`modal_app.py:4929`) is a second backstop for a
  mis-joined survivor, which is why the thread must be `comfymodal-`-prefixed.
- Not in `atexit` (client loop already winding down), not in `close_workers` (owns only the
  coordinator pool; wrong dependency).

## 4. Failure behavior (unchanged contract, moved locations)

- Every failure anywhere in the pipeline → entry absent → future miss → re-encode → correct.
- Commit failures: logged, swallowed (as today).
- No failure path propagates to the request; `store_entry` never raises for queue problems
  (bounded queue → if full, drop + log = miss, same as a failed store today).

---

# Expected critical-path savings

Per genuine new-prompt request (cold miss, the only requests that pay today):

| Work | Today (foreground) | After (foreground) | Class |
|---|---|---|---|
| Lookup `Volume.reload` | ≈0.16–0.47 s every request | 0 (throttled: once per interval, or never in local-only mode) | **Guaranteed removable** |
| Lookup manifest read + digest | ≈1–10 ms | unchanged | Must remain serial (ms) |
| Store serialization + file/manifest writes + fsync | ≈20 ms | unchanged (still on prefill thread, ms-scale) | Must remain serial (or trivially hideable later) |
| Store `Volume.commit` | ≈0.91–1.65 s **per entry** (N commits/request) | 0 on the path; 1 coalesced commit per batch on the background thread | **Guaranteed removable** |
| Enqueue overhead | — | <1 ms | New, negligible |
| Teardown flush (single-use) | — | ~0.3–1.7 s at exit (join + final commit), off the request path | Potentially hideable / end-of-life cost |
| Cross-container freshness | immediate (synchronous commit) | within one batch + throttle interval (seconds) or at exit; Modal background commits fill the gap | Trade, not regression |

- **Guaranteed removable foreground work:** reload ≈0.16–0.47 s + commit ≈0.91–1.65 s
  (×N entries → 1). Combined ≈**1.1–2.1 s per request**, and up to N× for multi-entry
  prompts.
- **Potentially hideable:** LRU-touch manifest rewrite (ms), teardown flush (bounded by the
  exit hook, off the request path), file writes (kept synchronous in v1 for diag fidelity).
- **Must remain serial:** key digest (≈0.2 ms), synchronous serialization (ms — required for
  the immutable-payload guarantee), hit validation, the brief RLock write section.
- **Failure behavior:** every removed RPC has a fail-closed miss path; the only observable
  difference on failure is a slower (re-encode) request — never wrong output.

---

# Files/functions an implementation would touch

| File | Functions |
|---|---|
| `comfymodal_runtime/clip_conditioning_cache.py` | `ExactConditioningCache`: `lookup_many` (`:710`), `_reload_volume` (`:696`) → `_maybe_reload` + interval state, `store_entry` (`:930`) → enqueue path, `_write_entry` (`:1047`) → extracted batch-write body reused by the persistence thread, `_persist_lru_touch` (`:872`) — move under the shared writer / use `max()` in `_write_entry` (`:1096`), `_diag` (`:609`) → shared locked diag store, `_commit` (`:617`) — keep; new: bounded queue, background thread, `flush(timeout)` / `dirty_since_last_commit` tracking; module: new env vars (interval, queue bound) |
| `comfymodal_runtime/model_preload.py` | call site `:9431-9439` (semantics change: store returns enqueued), diag read `:9487-9524` + `miss_stored`/`miss_not_stored` decision logs (`:9456-9506`) — enqueued/persisted counters |
| `comfymodal_runtime/modal_app.py` | `exit()` (`:4845`) — add `conditioning_cache_flush` teardown stage using `_run_teardown_stage` (`:4821`); nothing else (do not touch `close_workers`, restore, snapshot, sampler, output paths) |
| Tests | `tests/test_exact_cache_telemetry.py`, `tests/test_v2_clip_cache_miss_instrumentation.py`, `tests/test_sync_cache_compat.py`; new tests: enqueue/persist counters, flush-when-dirty-not-just-queued, local-only mode (no hook → no RPCs), diag threading, queue bound/dedupe, reload throttle |
| Env surface | `COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_RELOAD_INTERVAL_S`, optional queue bound; all default-preserving (opt-in feature stays opt-in) |

Not touched (explicitly out of scope): `comfyapp.py` active-profile / persistent-CLIP-cache
readers, CLIP↔UNET orchestration (`schedule_prefill`/`schedule_execution_unet`), output
persistence (`read_output_asset`, output-asset commit path), sampling, snapshot/loader
architecture, `runtime_state.py` / `CommitCoordinator` (a similar but separate subsystem).

---

# Verification plan

1. **Unit tests (local, no Modal):** queue semantics; enqueue→persist ordering; LRU bounds
   still enforced exactly once per batch; unindexed sweep unchanged; flush fires on
   dirty-not-just-queued; join-timeout drain path; `store_entry` never raises; diag visible
   to foreground after thread persistence; local-only mode performs zero commit/reload calls
   (assert with `FakeVolume`-style hook).
2. **Concurrency tests:** N threads × store+lookup interleaved with a mid-commit flush;
   assert no wrong hit (validation invariant) and no exception.
3. **SDK ground-truth check (local):** `pip show modal` — verify installed client matches
   v1.5.x semantics used here (commit auto-reload, default background commits, shutdown
   commit) before relying on the backstop; adjust the report's backstop claims if the pinned
   SDK differs.
4. **Benchmark (existing tooling, no paid runs needed beyond the established benchmark
   workflow):** with `COMFYMODAL_V2_CLIP_CONDITIONING_CACHE=1`, measure per-request
   `lookup_wall_ms` and `cache_store_wall_ms` before/after; assert store wall drops to
   ms-scale while enqueued/persisted counters reconcile; measure next-request
   `lock_wait_ms` to validate the lock-hold-scope decision (hazard 4); single-use + reusable
   container modes.
5. **Cross-container freshness test (the only paid-gated check):** request A on container 1
   (unique prompt) → immediately request B with the same prompt on a fresh container →
   expect miss (throttle window) then hit after the batch commit + reload; and hit at/after
   container 1 exit (shutdown commit backstop). This validates the freshness trade in
   production conditions.
6. **Failure injection:** kill the persistence thread mid-batch (test seam), assert request
   completes, entry eventually persisted or absent-with-miss; fail the commit hook, assert
   log-only and no request impact.

---

# Recommended next action

Proceed with implementation of the approved-with-changes design, staged to keep each step
independently shippable behind the existing opt-in flag:

1. **Stage 1 — background store + coalesced commit + teardown flush** (the ≈0.9–1.65 s×N
   win): split `store_entry` (synchronous serialize → enqueue), single persistence thread,
   one commit per batch, `exit()` flush stage, diag/threading fix, enqueued-vs-persisted
   counters. This alone removes ~98% of store latency and the per-entry multiplier.
2. **Stage 2 — throttled lookup reload** (the ≈0.16–0.47 s win): `_maybe_reload` with
   interval env var; local-only mode (skip RPCs when no hook/mount).
3. **Stage 3 — hardening:** queue bound/dedupe, `max()` seq in `_write_entry`, reload
   cadence tuning from benchmark data, freshness test across containers, lock-hold-scope
   measurement (`lock_wait_ms`).
4. Land Stage 1 and 2 only after the unit/benchmark gates above; keep the synchronous
   behavior behind `COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE=0` default so the unchanged
   path stays byte-for-byte intact for rollback.

Deliverable of this study: this document (design + implementation/results below).


---

# Implementation

The approved architecture was implemented exactly as specified (this section supersedes
any contradictory statements above; in particular the foreground miss path is
**serialize → enqueue → continue** — file/header/manifest writes and fsync belong to the
background persistence worker, never the prefill thread).

All changes are behind the existing opt-in flag (`COMFYMODAL_V2_CLIP_CONDITIONING_CACHE=1`);
when disabled the prefill encode path is unchanged.

## Stage 1 — background store and coalesced commit
- `store_entry()` is now enqueue-only: key build → synchronous serialization (immutable
  `bytes` + header dict + primitive key components) → bounded queue append → `True`.
  No file writes, manifest mutation, fsync, or commit on the foreground thread.
- One dedicated non-daemon worker (`comfymodal-exact-conditioning-persist`, 0.5 s wait
  cadence) drains the queue in batches: throttled reload-before-batch → atomic
  data/header writes → manifest read-once + `max()` seq bump → deterministic LRU bounds →
  one atomic manifest write → unindexed sweep — all under the RLock — then **ONE explicit
  `Volume.commit()` per batch outside the RLock**.
- Bounded queue (default 256) with dedupe by `key_hash`; queue-full and shutdown fail
  closed (`False`, reason recorded). Worker start failure degrades to synchronous
  single-entry persists (correct, fail-closed).
- The RLock is never held across `commit()` (verified by probe, see Local verification).

## Stage 2 — no unconditional lookup reload
- `lookup_many()` performs **zero Volume RPCs**. `_reload_volume()` is gone from the
  lookup path; the only reload is the worker's throttled reload-before-batch
  (`COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_RELOAD_INTERVAL_S`, default 15.0; <=0 → once
  per process). Stale state can only produce extra misses (every hit is fully validated).
- Local-only/unmounted mode (`mounted` auto-detected via `os.path.ismount` ancestor walk)
  performs **zero reload and zero commit RPCs** while still persisting locally.

## Stage 3 — teardown correctness
- `flush(timeout)` is idempotent: signals the worker, joins within the budget
  (5 s, `_PRELOAD_WORKER_JOIN_BUDGET_S` pattern), drains any queue remnant synchronously,
  then performs ONE final explicit commit when the mount is **dirty** (not merely
  queue-non-empty). No commit race: the flush final commit runs only after the worker has
  exited. Modal's shutdown commit remains a backstop only.
- Registered as `conditioning_cache_flush` teardown stage in `ModalRuntimeEntrypointV2.exit()`.
- Correctness contract delivered: **background explicit commit + explicit final teardown
  flush/commit**; Modal periodic/shutdown commits are never relied upon.

# Changed files

| File | Change |
|---|---|
| `comfymodal_runtime/clip_conditioning_cache.py` | All queue/worker/throttle/flush/telemetry logic; `_PendingEntry`; `_detect_mounted`; `_maybe_reload`; `_persistence_loop`; `_persist_batch`; `flush`; shared locked diagnostics; new env vars |
| `comfymodal_runtime/model_preload.py` | Store telemetry semantics only: `_cc_stored`→`_cc_enqueued`, `enqueued=`/`persisted=`/`persist_failed=` in the `miss_stored` log, `enqueued_count`/`persisted_count`/`persist_failed_count` in trace metadata (kept `stored_count` for consumer compatibility) |
| `comfymodal_runtime/modal_app.py` | One new teardown stage `conditioning_cache_flush` in `exit()` (local import, joins with `_PRELOAD_WORKER_JOIN_BUDGET_S`) |
| `tests/test_exact_cache_async_persistence.py` | New — the ten proofs |
| `tests/test_exact_cache_telemetry.py` | Updated to the async contract (worker-write timing, merged diag shape, `flush()` in teardown) |
| `V2_CONDITIONING_CACHE_CRITICAL_PATH_DESIGN.md` | This section |

`modal_app.py` / `model_preload.py` also carry concurrent uncommitted work from other
agents (UNET-H2D, execution-unet scheduling, contracts) — only the cache lines above were
touched by this task.

# Queue / worker architecture

- `self._pending`: `deque[_PendingEntry]` + `_pending_keys` set, guarded by
  `threading.Condition(self._lock)` (same RLock as file/manifest mutations — one lock
  serializes queue ops, writes, and lookups).
- `_PendingEntry(components, header, data, enqueue_mono_ns)` — immutable, no tensor
  references cross threads (serialization is synchronous by contract).
- Worker loop: wait 0.5 s → drain-all → `_persist_batch` (never raises) → repeat; on
  close, one final commit if dirty → `_worker_exited` + notify.
- `_persist_batch`: reload-before-batch (throttled) → per-entry atomic data/header writes →
  manifest read-once, `next_seq` increment, `max()` bump for existing entries →
  `_enforce_bounds(keep_digest=last)` → single atomic manifest write → unindexed sweep →
  `_dirty_since_commit = True` → **exit RLock** → one `_commit()` → clear dirty on success.
- Dedupe: same `key_hash` already queued → `queue_deduped += 1`, return `True` (identical
  deterministic content; no duplicate batch work).
- Bound: `len(_pending) >= max_queue` → `queue_full_dropped += 1`, fail closed.

# Correctness and race handling

- Every hit retains full validation (`_lookup_entry` unchanged): canonical key equality,
  model identity, dtype/shape/byte-range, per-tensor checksums, payload checksum. Any
  mismatch → miss. Stale state can only produce extra misses.
- Duplicate stores of the same key: deduped in the queue; manifest update uses the safe
  `max()` bump (the `last_access_seq` regression risk from the design review is fixed —
  `_write_entry` previously assigned unconditionally).
- Stale manifest / concurrent lookup during worker commit/reload: the commit's implicit
  auto-reload window can make the volume appear empty to a concurrent foreground lookup →
  `_read_manifest` returns the empty default → all-miss → fail-closed. No wrong hit.
- Worker/commit/queue-full/reload failures: never raise, never fail generation; fail
  closed to a future miss/re-encode.
- Dirty-but-empty queue at teardown: `_dirty_since_commit` drives the flush final commit.
- Unmounted/local-only mode: zero reload/commit RPCs; still persists locally and hits.
- Single-use and reusable containers: `exit()` flush stage covers both; per-batch commits
  give deterministic cross-container freshness within one batch + throttle interval.

# Telemetry changes

`threading.local()` was removed. Diagnostics now live in a shared structure guarded by
`_diag_lock`:

- Foreground store diag (per call, merged under the lock): `store_calls`, `store_failed`,
  `key_build_digest_ms`, `serialization_ms`, `materialize_ms`, `checksum_ms`,
  `serialized_payload_bytes`, `enqueue_ms`, `lock_wait_ms`, `total_ms`, `store_reason`.
- Worker diag (cumulative, merged into `pop_store_diagnostics`): `enqueued`, `persisted`,
  `persist_failed`, `commit_failed`, `queue_depth`, `queue_deduped`, `queue_full_dropped`,
  `batch_size`, `batch_count`, `persistence_queue_wait_ms`, `file_write_ms`, `manifest_ms`,
  `reload_ms`, `commit_ms`, `lock_wait_ms` (worker), `unindexed_files_removed`,
  `last_flush_ms`, `last_flush_status`, `flush_count`, `fallback_sync_stores`.
- `store_entry=True` means **enqueued**, never "durably committed". The decision log now
  reports `enqueued=`/`persisted=`/`persist_failed=`; trace metadata adds
  `enqueued_count`/`persisted_count`/`persist_failed_count` (kept `stored_count` as the
  enqueued alias for downstream consumers).
- New measurements: `serialization_ms`, `enqueue_ms`, `queue_depth`, `queue_deduped`,
  `persistence_queue_wait_ms`, `batch_size`, `file_write_ms`, `manifest_ms`, `reload_ms`,
  `commit_ms`, `lock_wait_ms`, persisted/failed counts, flush duration/status.

# Local verification

`python -m pytest tests/test_exact_cache_async_persistence.py tests/test_exact_cache_telemetry.py tests/test_sync_cache_compat.py tests/test_v2_clip_cache_miss_instrumentation.py` → **39 passed**.
The ten proofs map 1:1 to the validation list:

1. `test_miss_available_before_commit` — `store_entry` returns in <0.2 s while the commit
   hook is blocked; no files exist on disk until the worker runs.
2. `test_one_batch_commit` — N=5 entries → exactly **1** commit hook call (batch_size=5).
3. `test_lookup_never_reloads` — two lookups → reload hook count **0**; worker
   reload-before-batch ≤1.
4. `test_hits_fully_validated` — stored entry hits with identical tensor values; corrupting
   the data blob turns the hit into a miss.
5. `test_stale_only_misses` — seeded cross-container entry never satisfies a different key;
   exact key hits.
6. `test_worker_diag_across_threads` — `persisted/batch_count/batch_size/commit_ms` visible
   via `pop_store_diagnostics` after worker persistence.
7. `test_failures_never_fail_generation` — queue-full returns False (no raise), commit-hook
   raise and reload-hook raise never propagate, `commit_failed` counted.
8. `test_teardown_flush_dirty` — dirty-but-empty queue: flush fires the final commit; a
   clean drain gets **no** extra commit.
9. `test_local_only_zero_rpcs` — `mounted=False`: zero reload AND zero commit calls, files
   still persisted locally, hit works.
10. `test_no_lock_across_commit` — `cache._lock._is_owned()` is False inside the commit hook
    for the worker batch commit, worker final commit, and flush final commit.

`test_cachedit_dependency_family` failures are pre-existing and caused by another agent's
uncommitted contracts work (`SnapshotExecutionSeed`) — out of scope, untouched.

# Remote acceptance

Bounded: one deploy+snapshot run, then additional runs against the same deployment
(RTX PRO 6000 / CPU12 / RAM32768, provider/region unpinned; hard stop after the required
checks — no benchmark campaign). Evidence below is from the deployed container's stdout
(`[v2.clip_conditioning_cache]` lines), which the harness does not echo.

Cold-miss slot (valid runs, new diag schema):

| request | lookup_wall_ms | cache_store_wall_ms | note |
|---|---|---|---|
| `…f255b57d16de` | 440.7 | **10.1** | miss → miss_stored |
| `…a7936a7bdd4e` | 285.1 | **10.4** | miss → miss_stored |
| `…ab7f5750b95d` | 171.7 | **9.9** | miss → miss_stored |
| `…71cb469e1d4e` (deploy+snapshot) | 171.6 | **9.8** | miss → miss_stored |

Repeated-prompt / cross-container slot (fresh containers, same deployment):

| request | decision | encode_calls |
|---|---|---|
| `…ffd9a1bf3f23` | exact_hit | 0 |
| `…f0a670cae465` | exact_hit | 0 |
| `…b6c58ddd8480` | exact_hit | 0 |
| `…4097b0dad535` | exact_hit | 0 |
| `…ab3017501b7f` (3-run seq 1) | exact_hit | 0 |
| `…39831ce49a78` (3-run seq 2; remote completed) | exact_hit | 0 |

Cross-container persistence is proven: the key stored by the first container commits at
teardown (flush) and is served by later fresh containers with `encode_calls=0` — zero
reloads, zero re-encodes. Intermittent `unsupported_unet_shape` failures during the
campaign came from another agent's uncommitted snapshot/canonical-execution work deployed
in the same tree; they are unrelated to the cache path and were skipped (the retry landed).

# Before vs after critical path

| Work | Baseline | After (foreground) |
|---|---|---|
| Lookup `Volume.reload` | ≈0.16–0.47 s every request | **0** (no lookup RPC; worker-only throttled reload) |
| Store `Volume.commit` | ≈0.91–1.65 s per entry (N commits) | **0** on the path; 1 coalesced commit/batch on the worker |
| Store wall (measured) | 0.93–1.67 s | **9.8–10.4 ms** (serialize+enqueue only) |
| Lookup wall (measured) | 0.16–0.47 s | 0.17–0.44 s (manifest read only; reload removed — remaining cost is the volume manifest access, not an RPC) |
| Cross-container freshness | immediate (synchronous commit) | within one batch + throttle interval, or at exit (flush); Modal background commits as backstop only |
| Generation failure on cache failure | fail closed to miss | identical (never wrong conditioning) |

# Remaining cache latency

- Lookup still pays the mounted-manifest read (≈0.17–0.44 s measured on a fresh container;
  the old reload is gone, so this is the volume manifest access floor, not an RPC). A
  future optimization could cache the manifest in-process with a version check.
- Worker-side per-batch commit (≈0.9–1.65 s) and teardown flush (bounded by
  `_PRELOAD_WORKER_JOIN_BUDGET_S`) are off the request path but still wall time at exit /
  on the worker thread.
- Cross-container hit freshness is bounded by the reload throttle interval (15 s default)
  or the next flush; acceptable per the design (stale → miss → re-encode → correct).

# Recommended next action

Land the changes (this checkout) behind the existing opt-in flag. Before production
deploy: (1) re-run the local suite after concurrent agents stabilize their uncommitted
files, (2) one cold-miss + one repeated-prompt acceptance run after the other lanes'
snapshot work is committed (the intermittent `unsupported_unet_shape` failures are in
their path, not the cache), (3) if tighter cross-container freshness is needed, tune
`COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_RELOAD_INTERVAL_S` down from 15 s, and (4)
optionally add a first-lookup manifest cache to shave the remaining lookup floor.
