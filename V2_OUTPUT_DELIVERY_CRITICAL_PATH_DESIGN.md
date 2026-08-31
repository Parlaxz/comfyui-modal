# V2 Output Delivery Critical-Path Study — Earliest Safe Result Delivery

> **SUPERSESSION NOTICE (2026-08-30):** This is a historical design study,
> preserved for its evidence and rejected/endorsed alternatives. Its proposed
> generated-output deferral, background drain, deduplication, and universal
> commit-before/after semantics are not current policy. Use
> `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md`: output durability is off by
> default and strict commit/reopen/hash proof is opt-in. S4 source publication
> durability remains mandatory.

Status: DESIGN ONLY (read-only study; no code modified, no paid generations run)
Date: 2026-08-11 (data from runs through 2026-08-12)
Scope: post-VAE output delivery only. Active-profile logic, CLIP/UNET overlap, conditioning cache, sampling, and snapshot/loader architecture are explicitly out of scope and untouched.

---

# Executive conclusion

**Result delivery CAN safely precede the persistence commit. The existing semantics support it, with one required local-side change and one bounded retry addition.**

The current V2 chain puts a blocking Modal `Volume.commit` RPC (~0.9–1.3 s) between "output collected" and "result streamed to caller". The caller does not need the commit — the delivered payload is descriptor-only (~2.2 KB, no bytes), and all byte reads happen lazily afterwards through the asset route. The commit exists solely to guarantee that later Volume reads (from possibly fresh, single-use containers) find the files.

**Recommended design (Variant A, endorsed):**

```
VAE decode → image encode (~570 ms) → collect+hash+descriptors (~10 ms)
→ result becomes returnable
    ├─ yield result event ────────────────→ caller receives result immediately
    └─ await Volume commit (~0.9–1.3 s)  ──→ runs in generator tail (off caller path)
→ generator ends → stream done → exit hook → Modal exit-time commit (backstop)
```

- **Client-visible saving: 0.9–1.3 s per run** (typical ~0.97 s ≈ 55% of the post-VAE-decode tail of 1.74–2.30 s). Encode and handoff stay on-path and are not claimed.
- Explicit commit must be **kept** (deferred, not deleted): Modal SDK 1.4.3 has **no periodic background commit** — the "every few seconds" docs claim is false for this SDK version; only the explicit `commit()` and the container-exit commit exist. Variant B (drop the explicit commit, rely on the exit-time commit) is rejected: under the default `single_use_containers=False` container-reuse deployment, assets would stay invisible to other containers for the container's whole lifetime.
- Two safe structural facts make this work: (1) the local transport's `aclose()` on the remote generator sends **no cancel RPC** — Modal's container entrypoint drives the user generator to exhaustion independently, so code after the final yield runs to completion even today; (2) Modal's exit sequence runs the exit hook and a final volume commit before teardown, and generator functions keep the container alive until the generator ends.
- Two compensating changes are required: a **background drain** on the local side (keep consuming the stream to natural end so commit status is observed and the container completes cleanly) and a **bounded retry** in the asset route / auto-save fetch (the only consumers that read Volume bytes; they will see a short 404 window while the deferred commit is in flight).

---

# Current output lifecycle

## Remote (Modal container) side — exact chain after VAE decode

Measured markers (`FULL_RUN_LOGS.md` runs 4–6, 2026-08-12, RTX PRO 6000, 1 image, ~2.95 MB PNG; durations in ms):

| # | Step | Code anchor | Cost (min / typical / max) |
|---|---|---|---|
| 1 | VAE decode (GPU, context) | `vae_decode_start/end` in `model_preload.py:~9965-9980`; authoritative `modal_app.py:~11800-11817` | 350 / ~400 / 841 |
| 2 | **Image encode (CPU PIL)** — in-graph node `ComfyModalProductionOutput.encode()` → `encode_image_tensor_batch` (`comfyapp.py:570, 460-512`) → `_store_production_output` into in-memory registry (`comfyapp.py:410`) | `output_encode_start/end`, `modal_app.py:~11822-11842` | 570 / 575 / 583 |
| 3 | **Output collect** — `pop_outputs(prompt_id)`; `run_strategy_chain` → `DirectOutputSink.collect` (`output_delivery.py:538`); SHA-256 per item in `OutputItem.__post_init__` (`output_delivery.py:99-107`) | `output_collect_start` (t7b), `modal_app.py:~12492-12522` | ~10 ms total with step 4-5 |
| 4 | Optional re-encode if `output_format != "original"` | `convert_output_items`, `result_delivery.py:323-421`, `modal_app.py:~12542-12604` | only when format differs |
| 5 | **Persist (write + hash + descriptors + serialize)** — atomic-ish write to `RUNTIME_STATE_PATH/output_assets/<sha256><ext>`; SHA-dedup skips write+commit if file exists; spawn commit task | `_persist_output_assets`, `modal_app.py:~13151-13242` (spawn at ~13241); `output_persist_start/end` `modal_app.py:~12618-12640` | 10 / 10 / 13 |
| 6 | Descriptor result build (overlaps commit task; ~2.2 KB payload, no base64) | `attempt_to_descriptor_result(..., legacy_data=False)`, `output_delivery.py:259-349`; `base64_counting_scope` `modal_app.py:~12629-12634` | few ms |
| 7 | **Volume commit (awaited)** — `volume.commit.aio()` | **`await _asset_commit_task`, `modal_app.py:~12642-12644`** | **895 / ~970 / 1287** |
| 8 | Payload size measure; `output_collect_end` (t8b) | `_measure_json_bytes` `output_delivery.py:395-401`; `modal_app.py:~12683, ~12705-12714` | ~1 ms |
| 9 | Validation-cert write + **second awaited commit** (only when cert scheduled) | `_write_v2_validation_certificate`, `modal_app.py:~1438-1448`, called ~12751 | up to another ~1 s when enabled |
| 10 | `return result` → streamed as terminal `{"type":"result"}` event | `RuntimeExecutor.stream`, `runtime_executor.py:2909`; generator `run_plan_stream`/`_run_plan_stream_impl`, `modal_app.py:~14065/14173` | — |
| 11 | **Pre-yield cleanup** — `_run_terminal_cleanup_sync` (production cleanup + GPU release) | `modal_app.py:~13988-14023`, invoked ~14117 | off-path (result not yet handed off) |
| 12 | Post-stream wrapper cleanup | `_release_after_stream_complete`, `modal_app.py:~14025-14063` at ~15189 | off-path |
| 13 | Container exit hook (~30 ms) + Modal exit-time volume commit (9 retries, failures logged only) | `exit()` hook `modal_app.py:~4845-4921`; SDK `container_io_manager.py:1070-1097` | ~0.03 s + backstop commit |

**Tail total (VAE decode end → local `final_result_received`): 1744 / 1757 / 2299 ms.** Breakdown (Run 6, 1756.7 ms): encode 570 (32%), persist+serialize 10 (0.6%), commit 970 (55%), remote→local handoff 207 (12%). Remote teardown after collect (~0.9–1.0 s) is already off the user-visible path.

## Local (host) side — handoff contract

1. Transport `async for` over the stream; on `{"type":"result"}` it emits `final_result_received` (local) and yields the event (`modal_transport.py:~866-875`).
2. Callers **break immediately** on the result event (`canonical_execution.py:1665-1667` and `2719-2721`) — the response path never waits for the stream to end.
3. Transport `finally` does best-effort `await _aclose_iterator(_iterator)` (`modal_transport.py:~890-895`). **Verified in Modal SDK 1.4.3: client-side aclose sends no cancel RPC** (`_functions.py:_call_generator` → `run_generator`; only stream-polling and status-polling are cancelled). The container entrypoint drives the user generator to exhaustion independently (`_container_entrypoint.py:142-149`) and only then sends `output_items_generator_done`. **Post-yield remote code therefore already runs to completion today**; aclose only produces a logged `async_generator_athrow` warning (documented in `modal_transport.py:~44-50`) and loses commit-status observability.
4. Then locally (sequential, all fast, none touching the Volume): materialize (descriptor mode writes **no local files**; `result_delivery.py:553-559`), timings build, history write (non-fatal on failure; `studio_run_adapter.py:~3641-3654`, `playground_service.py:~867-877`), response return.
5. Image bytes are fetched **lazily** by the frontend via `/comfymodal/assets/{asset_id}` (`__init__.py:6649-6703`) → remote `read_output_asset` (`modal_app.py:~13244-13266`: `volume.reload()` then `candidate.is_file()`), or by auto-save `_remote_fetch_fn` (`__init__.py:2637-2653`, `result_delivery.py:715-724`) when `auto_save_local` is enabled.

---

# Earliest safe result point

**The result is returnable the moment descriptors exist — i.e., after step 5 (collect+hash+descriptor build), before the commit.**

What the caller actually needs before `final_result_received` (all metadata, verified against consumption sites):
- `outputs` / `images` / `videos` — counts + materialization input (`canonical_execution.py:~2730-2737`, `result_delivery.py:606-635`)
- `asset_descriptors` — `asset_id`, `backend_path`, `byte_count`, `mime_type`, `node_id`, `output_key`, `width`, `height` (`__init__.py:608-637`, `playground_service.py:543-571`)
- `use_descriptors`, `primary_asset_id` (gates "output produced" with zero local files; `playground_service.py:779-780`)
- `trace`/stages/waterfall (timing and history fields)

None of these require committed Volume state. The payload is ~2.2 KB (`serialized_result_bytes` measured, `FULL_RUN_LOGS.md:915/2626/4335`).

**What is NOT returnable early:** the encoded image itself. The ~570 ms in-graph PNG encode (step 2) is the first thing the payload depends on; it cannot overlap VAE decode (it consumes its output) and there is nothing else pending to overlap with in single-image runs. It stays on the critical path (see Safe overlap opportunities for the multi-image/format cases).

---

# Persistence contract

## Required before returning: nothing beyond descriptors.
The local caller never reads Volume bytes on the happy path. Local history writes are independent of Volume state (they record local basenames + `asset_id`; Volume paths live only in the lease registry as `modal://<workspace>|<gpu>|<backend_path>`, `__init__.py:622-637`).

## Required for history/download durability (must complete before bytes are served):
1. **Volume commit** — makes the files visible to other containers. Explicitly documented contract: *"If successful, the changes made are now persisted in durable storage and available to other containers"* (Modal `Volume.commit`). Reader must `reload()` to see them.
2. **Backstop:** Modal's container-exit commit (`container_io_manager.py:1070-1097`, 9 retries, failures only logged) runs after `@modal.exit` hooks on every graceful teardown. Not a primary mechanism — see Executive conclusion for why Variant B is rejected.

## Consumers that currently assume commit-before-response:
| Consumer | Assumption | Consequence if commit is deferred |
|---|---|---|
| Remote `await _asset_commit_task` (`modal_app.py:~12642-12644`) | commit completes before result | **being moved** (the design) |
| `/comfymodal/assets/{asset_id}` (`__init__.py:6649-6703`) | file exists when frontend asks | transient 404 → needs retry |
| `_remote_fetch_fn` auto-save (`__init__.py:2637-2653`) | bytes available right after receipt | transient failure → needs retry |
| `read_output_asset` (`modal_app.py:~13244-13266`) | reload sees committed state | 404 `FileNotFoundError` in window |
| Save-from-history (`studio_run_adapter.py:2173-2177`) | — | already rejects `modal://` paths regardless of commit state; unaffected |

**No history/download consumer assumes commit-before-response in a way that breaks:** history stores descriptors/hashes and is written locally; the only byte-serving path is the asset route, which is being given retry.

---

# Single-use teardown constraints

Current teardown shape (already optimized in the earlier single-use work; `docs/v2-single-use-container-teardown.md`):
- GPU release runs **before** the terminal event (`_run_terminal_cleanup_sync`, `modal_app.py:~13988-14023`) — GPU cost is not extended by any post-yield work.
- The Modal wrapper `finally` re-runs cleanup after stream consumption (`_release_after_stream_complete`, ~15189).
- `exit()` hook (`modal_app.py:~4845-4921`, ~30 ms) joins: request samplers (0.5 s budget), preload workers (5 s budget — "5 s is far below Modal's 30 s shutdown grace"), trace services (0.5 s), legacy workers, production cleanup, GPU release.
- Modal then runs its exit-time volume commit and interpreter shutdown. Container is torn down by Modal (`single_use_containers` per `COMFYMODAL_V2_SINGLE_USE_CONTAINERS`, default False; `min_containers=0`, `scaledown_window=4`).

**What must be joined before safe container exit (post-deferral):**
1. **The deferred commit** — awaited in the generator tail *before the generator ends*. The container cannot finish the input until the generator is exhausted (`_container_entrypoint.py:142-149`), so this join is structurally guaranteed on graceful paths.
2. Exit-hook worker joins (unchanged).
3. Modal exit-time commit as final backstop (unchanged).

**Constraints on new persistence machinery:** no fire-and-forget asyncio tasks (cancelled at container exit, `user_code_event_loop.py:27-35`) and no daemon threads (die at interpreter exit); non-daemon threads block exit up to ~30 s. The commit is an awaited coroutine in the generator — this is the supported shape.

---

# Failure/race analysis

1. **Commit fails after result delivered** (today: commit failure raises → `{"type":"error"}` event, run fails despite image being ready — `modal_app.py:~13235-13239` documents "Propagate commit failures so no result yield", which must be inverted *deliberately*). Post-deferral semantics: result is already delivered; failure is (a) retried internally by Modal's commit RPC (90 retries, exponential backoff), (b) retried by the exit-time commit (9 retries), (c) logged to `_teardown_diagnostics` and marked in the payload (`commit_status`), and (d) surfaced as a 404/503 on the asset route with a clear message. History already holds descriptors + hashes, so re-running the generation is cheap (SHA-dedup skips the commit entirely on cache hits). Strictly better than today: today the user gets *nothing*; after, the user gets the result, and the asset either appears (retry success) or fails loudly.
2. **404 window for asset reads**: bounded ≈ commit RTT + fresh-container spin-up (~3 s budget). Mitigation: retry in the asset route (e.g., 5 attempts, 250 ms → 1.5 s backoff, re-invoking `read_output_asset` per attempt; tolerate both the 404 and 502 paths at `__init__.py:6679-6682`). Same retry for auto-save fetch. Cache-hit runs (no write, no commit) have no window (proven 10.9 ms collection on cache hit, `V2_SINGLE_INVOCATION_PLAN_EXECUTION_REPORT.md:26`).
3. **Local aclose vs post-yield remote code**: safe — no cancel RPC exists in the client SDK; the container drains the generator itself. The background drain is for *status fidelity* (observing commit success and clean completion), not durability. If the drain is cancelled, durability is unaffected; only observability is lost. The drain must be `asyncio.shield`-ed and the transport `finally` must hand off `_iterator` ownership so it doesn't aclose it out from under the drain.
4. **Teardown mid-commit**: generator-drain is sufficient on graceful paths; force-kill (SIGKILL/OOM) exposure is *unchanged from today* — the exit-time commit is equally lost on a hard kill either way. Variant A only widens the interval in which a hard kill leaves "result delivered but asset invisible" (recoverable by re-run; history intact).
5. **Concurrent commits**: Modal serializes commits per volume via its internal lock (`volume.py:764`); under `max_inputs > 1` this is latency, not correctness. Keep a single writer (the generation container); do not add a spawned second writer on the same paths (v1 last-write-wins caveat, ≤5 concurrent commits guidance).
6. **Two commits on the same volume (asset + cert)**: Modal commits snapshot the volume's *entire* dirty state; the cert write (`modal_app.py:~1438-1448`) targets the same `runtime_state_volume`. Merge both writes into one post-yield commit — removes a second RTT in cert-scheduled runs.
7. **Result-payload diagnostics regression**: `output_volume_commit_ms` / `output_commit_overlap_ms` will report 0/pending once the commit is deferred (they are populated from the commit await). Downstream consumers (`tools/benchmark_v2_direct.py:1511-1518`, `tools/variance_report.py:461/885`, Playground, history) must tolerate this; emit a `deferred_commit_end` marker into `_teardown_diagnostics` to preserve observability.

---

# Safe overlap opportunities

| Opportunity | Status | Value |
|---|---|---|
| **Commit ∥ result handoff + local processing** | New (Variant A) | **~0.9–1.3 s off caller path** — the headline win; container wall time unchanged, GPU already released |
| Commit ∥ descriptor build (existing) | Already implemented | ~10 ms overlap — negligible (descriptor build is tiny) |
| Asset commit + cert commit merged | New | Saves a second ~1 s RTT in cert-scheduled runs (container-side, not client-visible) |
| SHA-dedup commit skip on cache hits | Already implemented (`modal_app.py:~13175, ~13202`) | Proven: 10.9 ms vs ~1.3 s. Deterministic-cache-hit runs already pay nothing |
| Image encode overlap | **No overlap within a single-image run** — encode is the first consumer of VAE output and everything else depends on it | — |
| Multi-image encode parallelism | Possible: thread the per-image PIL encodes (encode is C-backed; partial GIL release) | Modest; typical runs are 1 image |
| Double-encode avoidance | When `output_format != "original"`, the node encodes to PNG **and** `convert_output_items` re-encodes (`result_delivery.py:323-421`) — two encodes on the path | ~one encode's worth (0.5 s) when triggered; fix = encode once in final format |

---

# Proposed minimal implementation

## Variant A — defer the commit until after the result event (endorsed)

**Remote (modal_app.py):**
1. In the post-collect sequence, replace `await _asset_commit_task` (currently `modal_app.py:~12642-12644`, inside `_run_in_process`) with a stash: attach the commit task to `self` (per-request; key by `request_id` for `max_inputs > 1`) instead of awaiting it. Keep the write + dedup + task-spawn exactly as-is.
2. Do the same for the cert write: write the cert bytes into the volume before the result return, but drop its own awaited commit (`~1444-1445`) so both dirty sets land in the single deferred commit.
3. In `_run_plan_stream_impl`, after the `async for event in _execution_stream:` loop completes (i.e., after the result event has been yielded; ~`modal_app.py:15058`), `await` the stashed commit task (with a bounded timeout + try/except that logs and records `commit_status` into `_teardown_diagnostics`). The generator then ends naturally.
4. Emit `deferred_commit_start/end` markers into `_teardown_diagnostics` (do not reuse `output_persist_end` semantics — it no longer spans the commit). Optionally add `"commit_status": "pending"` to the result payload so the local side can distinguish.
5. Invert the "propagate commit failures so no result yield" intent (`output_delivery.py:~13276-13280` comment) deliberately; failure handling per Failure/race #1.

**Local (modal_transport.py + callers):**
6. On the result event: keep emitting `final_result_received` and yielding the event to the caller. Instead of closing `_iterator` in the transport `finally`, hand off ownership to a **shielded background drain task** that consumes the remaining stream to natural end (the SDK's `run_generator` already terminates on `items_received >= items_total`; no new "done" event needed — protocol-native), then closes the iterator. Cancel-safe: if the drain is cancelled, durability is unaffected.
7. Callers' early `break` on the result event stays as-is (that is the point — response proceeds immediately).

**Asset serving (`__init__.py` + `result_delivery.py`):**
8. Add bounded retry/backoff to `/comfymodal/assets/{asset_id}` (~`__init__.py:6669-6689`): on 404/502, retry ~5 times with 250 ms → 1.5 s backoff (≈3 s budget covers commit + container spin-up), then return the current error.
9. Same retry for `_remote_fetch_fn` auto-save (`__init__.py:2637-2653` / `result_delivery.py:715-724`).

**Deliberately NOT changed:** encode pipeline, history/local persistence, descriptor payload, teardown ordering, GPU release timing, container lifecycle config.

## Rejected: Variant B (drop explicit commit, rely on Modal's exit-time commit)
Unsafe for the default deployment: SDK 1.4.3 has **no periodic background commit** (verified: `VolumeCommit(` appears only in `volume.py:768` explicit and `container_io_manager.py:1080` container-exit). Under container reuse (`single_use_containers=False` default), a shutdown-commit-only design leaves assets invisible to other containers for the container's entire lifetime, and exit-commit failures are only logged. Viable only if every deployment were single-use — not worth betting the default.

## Rejected: base64 fallback on commit failure
Defeats the 2.2 KB descriptor design; the residual double-failure case is covered by a loud 404/503 + re-run (history holds hashes). Not worth the payload cost.

---

# Expected critical-path savings

| Segment | Current (ms) | After Variant A (ms) |
|---|---:|---:|
| Image encode | 570 / 575 / 583 | 570 / 575 / 583 (unchanged — on-path) |
| Collect + persist + serialize | ~10 | ~10 (unchanged) |
| **Volume commit (awaited)** | **895 / ~970 / 1287** | **0 on caller path** (runs in generator tail, ~same container wall time) |
| Remote → local handoff | 207 / 252 / 428 | 207 / 252 / 428 (unchanged) |
| **vae_decode_end → final_result_received** | **1744 / 1757 / 2299** | **787 / ~787 / 1008** |

**Maximum realistic foreground saving: 0.9–1.3 s (typical ~0.97 s, ~50–57% of the post-VAE tail).** This is the commit RTT moved fully off the caller's critical path; the container-side cost is unchanged (commit still runs, GPU already released, exit hook still waits for it). Not claimed: encode (570 ms, irreducible for single-image runs) or handoff (network). Secondary, container-side only: merging the cert commit removes a second ~1 s RTT in cert-scheduled runs.

---

# Files/functions an implementation would touch

| File | Anchor | Change |
|---|---|---|
| `comfymodal_runtime/modal_app.py` | `_run_in_process` commit await ~12642-12644; `_persist_output_assets` ~13151-13242 (dedup ~13175/13202, spawn ~13241, failure raise ~13235-13239); `_write_v2_validation_certificate` ~1438-1448, call ~12751; `_run_plan_stream_impl` ~14173+ (post-loop await ~15058) | Stash commit task; defer await into generator tail; merge cert commit; emit `deferred_commit_*` diagnostics; `commit_status` in payload |
| `comfymodal_runtime/modal_transport.py` | result-event handling ~866-895; `_aclose_iterator` ~41-64 | Shielded background drain; ownership handoff in `finally`; no early aclose |
| `canonical_execution.py` | break on result 1665-1667, 2719-2721 | No change (response proceeds on result event; drain is transport-level) |
| `__init__.py` | asset route ~6649-6703; auto-save `_remote_fetch_fn` ~2637-2653 | Bounded retry/backoff on 404/502 |
| `comfymodal_runtime/result_delivery.py` | auto-save fetch 715-724 | Retry + `commit_status` passthrough |
| `comfymodal_runtime/output_delivery.py` | comment ~13276-13280 (intent inversion, in `modal_app.py` copy); diagnostics fields already exist (134-135) | Documentation only |
| `studio_run_adapter.py` / `playground_service.py` | history status ~3641-3654 / ~867-877 | Optionally record `commit_status` (non-fatal) |
| Tests | `tests/test_v2_teardown_diagnostics.py` (cleanup-before-handoff order, ~466-497), `tests/test_v2_waterfall.py`, `tests/test_studio_timing_integration.py` (~2020-2150), `tests/test_studio_direct_run.py` (~1320-1370) | New: result-before-commit ordering; drain keeps stream open; asset-route retry; deferred-commit diagnostics; regression: `output_commit_ms` consumers tolerate 0/pending |
| `tools/benchmark_v2_direct.py` (~1511-1518), `tools/variance_report.py` (~461/885) | commit-field consumers | Tolerate deferred values |

---

# Verification plan

1. **Unit tests (no GPU):** transport drain semantics (result event delivered while stream stays open; drain consumes to natural end; cancel of drain does not error); `_run_plan_stream_impl` awaits stash before generator end; deferred-commit failure path logs + sets `commit_status` and does **not** emit an error event; asset-route retry logic (fake 404 → retry → 200); teardown ordering test updated for the new handoff point.
2. **Instrumented deploy run (the implementer's next step, not part of this design task):** one `COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS=1` run with the FULL_RUN_LOGS-style trace; assert: `final_result_received` precedes `deferred_commit_end`; `output_collect_end`→`final_result_received` unchanged; asset fetch immediately post-result succeeds within the retry budget; `[v2.output]` line shows `commit_ms` now post-yield; exit hook still ~30 ms; no `async_generator_athrow` warning.
3. **Consumer regression sweep:** grep all readers of `output_volume_commit_ms`/`output_commit_overlap_ms` (benchmark, variance, Playground, history) and confirm 0/pending is tolerated; confirm `resolve_run_output_path` behavior unchanged.
4. **Benchmark comparison:** run `tools/benchmark_v2_direct.py` before/after; expect `output_collection_ms`-equivalent tail drop of ~0.9–1.3 s; cache-hit runs stay at ~10 ms.
5. **Manual UX check:** studio run → image appears; during the post-result window the asset route retries transparently; on injected commit failure (test hook), the asset route returns a clear 503 and history records the descriptor + failed status.

---

# Recommended next action

Implement **Variant A** in three sequenced steps, each independently mergeable and observable:

1. **Remote deferral** (modal_app.py: stash commit task, await in generator tail, merge cert write, `deferred_commit_*` diagnostics, `commit_status`) + local shielded drain (modal_transport.py). This alone delivers the 0.9–1.3 s saving; asset-route retry can land in the same change.
2. **Asset/auto-save retry** (__init__.py, result_delivery.py) — needed before the deferral ships to any deployment that renders via the asset route.
3. **Test + benchmark pass** (verification plan above) with the FULL_RUN_LOGS-style instrumented run, then consumer-regression sweep.

Do **not** ship the deferral without step 2. Do **not** pursue Variant B unless the deployment is fully `single_use_containers=True` — and even then the silent-failure semantics make it inferior to Variant A.

## Constraints honored
- Read-only design study: no code modified, no paid generations run, no git operations (no stash/reset/revert/branch).
- Out-of-scope areas untouched: active-profile logic, CLIP/UNET overlap, conditioning cache, sampling, snapshot/loader architecture.
- Concurrent agent work in those areas is preserved; all anchors above are file:line references into the current checkout.
- Note: earlier reports predating the commit instrumentation (e.g., `V2_RTX6000_12CPU_32G_6_COLD_RUN_REPORT.md`, 2026-07-19) state "no output commit in the V2 request path"; the current checkout (2026-08-12 runs) does commit on-path (`modal_app.py:~12642-12644`). This document reflects the current checkout.

---

# Implementation (Variant A) — status

Implementation complete per the approved Variant A spec. All changes are in the current checkout; no competing report, no git operations, no paid runs yet.

## What landed (file → change)

**`comfymodal_runtime/modal_app.py` (remote)**
- `_run_in_process`: the `await _asset_commit_task` is replaced by a per-request stash: `self._deferred_commit_task` / `self._deferred_commit_diag` / `self._deferred_commit_pending = True` (both write and cache-hit branches). `await asyncio.sleep(0)`, the descriptor build, and `output_persist_start/end` trace emits are unchanged. Asset write/hash/dedup behavior in `_persist_output_assets` is untouched.
- `result["output_diagnostics"]["commit_status"]` = `"pending"` (commit stashed) or `"skipped"` (no commit needed). `[v2.output]` print line now reports `commit_status=...`.
- New method `_finalize_deferred_commit(self, *, request_id="") -> dict | None` (idempotent, never raises, catches `Exception` and `asyncio.CancelledError`): awaits the stashed commit, emits `deferred_commit_start` / `deferred_commit_end` teardown-diagnostics markers, and returns the definitive `{"type": "persistence", "status": "ok"|"failed", "commit_ms", "detail", "skipped"}` event (or `None` when nothing was pending).
- `_run_plan_stream_impl` generator tail: after the execution-stream loop, awaits `_finalize_deferred_commit` and yields the persistence event. Runs even when the client closed the stream (Modal's container entrypoint drives the generator to exhaustion).
- `run_plan_stream` outer `finally`: guarded `await self._finalize_deferred_commit(...)` as a safety net for closed/cancelled streams.
- Request-start reset of the stash under `release_lock`, plus instance-defaults in `__init__`, the post-unpickle getattr-guard helper, and `_v2_init_instance`.
- **Cert write/commit left untouched** (`_write_v2_validation_certificate` and its call site) per the approved constraint — the graph/certificate lane owns it.
- `run_prompt_stream` (v2 class) is a thin wrapper that delegates to `run_plan_stream`, so it inherits the tail + safety net; no separate change needed.

**`comfymodal_runtime/modal_transport.py` (local)**
- Module-level registry `_PERSISTENCE_STATUS_BY_PROMPT: dict[str, dict]`; `get_persistence_status(prompt_id)` (returns a copy); `record_persistence_status(request_id, event)` (shared normalized recorder).
- `_spawn_persistence_drain(iterator, *, request_id, runtime_trace)` — shielded background task (`create_task(_shielded_drain())` where `_shielded_drain` awaits `asyncio.shield(...)`; the wrapper is required because `asyncio.shield()` returns a Future on Python 3.11 and `create_task` rejects it directly).
- `_drain_persistence_iterator(...)` — consumes the iterator to natural completion, records the `persistence` event into the registry, emits local trace `deferred_commit_end` (phase="local"), then best-effort acloses. Never raises.
- `run_plan_stream`: local `_stream_exhausted` flag set after natural exhaustion; the `finally` hands the iterator to the drain when `_iterator is not None and not _stream_exhausted` (stored on `self._drain_task`), else acloses. The `final_result_received` emit is unchanged.

**`__init__.py` (local serving)**
- Asset route `/comfymodal/assets/{asset_id}` (`modal://` branch): bounded retry — 5 attempts, backoff `[0.25, 0.5, 1.0, 1.5, 1.5]`, retrying only `FileNotFoundError` (the deferred-commit visibility window). Consults `get_persistence_status(record["cell_key"])`: definitive `"failed"` → 503 "asset persistence failed" (no retry); exhaustion → existing 404; other errors → 502. Local-path branch unchanged.
- `_remote_fetch_fn` (auto-save): 3-attempt bounded retry on `FileNotFoundError` (`time.sleep` 0.25/0.5); preserves the 120 s timeout and the caller's non-fatal `save_warning` downgrade.

**`modal_client.py` (legacy client)**
- `run_prompt_stream` records remote `persistence` events via `record_persistence_status` (keyed by trace `prompt_id`/`request_id`). This path already consumes the stream to natural completion (no early break), so no drain was needed — only registry recording. `read_output_asset` untouched.

**`tools/benchmark_v2_direct.py` (consumers)**
- `output_commit_ms` extraction guards `None` and honors `commit_status == "pending"` (sets `commit_pending=True`, never fabricates a commit time). Acceptance validation relaxed: absence of `output_commit_ms` fails only when the commit was not deferred; `0.0` remains valid. `tools/variance_report.py` verified tolerant (`_num(None) → None`; stats skip `None`) — no edit needed.

**Tests — new `tests/test_v2_deferred_commit.py` (21 tests, offline)**
- Drain end-to-end (break-on-result → registry `ok`, `commit_ms` recorded, iterator aclosed exactly once); drain records failure; natural exhaustion skips drain; `record_persistence_status` normalization + overwrite + copy semantics; `get_persistence_status` unknown → None; `_finalize_deferred_commit` success/idempotence/failure/cache-hit/not-pending with teardown-marker assertions; asset-route retry/503/404/502 via aiohttp-style handler invocation (pattern from `test_routes_registered.py`).
- Existing-test fixups (minimal, contract-driven): `tests/test_v2_local_submission_timing.py` — three `aclose` assertions now join `transport._drain_task` first (inner aclose moved into the background drain).

## Local gate results (all offline; no paid runs)

| Suite | Result |
|---|---|
| `tests/test_v2_deferred_commit.py` (new) | 21 passed |
| `tests/test_v2_local_submission_timing.py` | 111 passed |
| `tests/test_v2_teardown_diagnostics.py` + `test_v2_publish_transport_spawn.py` + `test_v2_waterfall.py` | 80 passed |
| `tests.test_v2_executor_seeding` (isolated) | 15 passed |
| `tests.test_routes_registered` (isolated) | 61 passed |
| `tests.test_modal_asset_integration` (isolated) | 25 tests, 1 pre-existing failure (`test_caller_result_preserved_after_processing` — waterfall in-place mutation in `_on_remote_event`, untouched area) |
| Combined adjacent sweep | 199 tests; failures = 3 pre-existing + 1 order-dependent (sqlite WAL), all pass in isolation |
| `TestBenchmarkPrefixInstrumentation` (9) | Pre-existing — require a deployed Modal runtime (offline `deployed_*` shape metadata); present before these changes |

No Variant A regression. The remaining gate failures are pre-existing or order-dependent and unrelated to this work.

# Results (paid correctness run) — PENDING

The single approved paid correctness run has **not** executed. Deployment attempts (`deploy_and_run_v2_single.bat`) were aborted by Modal's build-integrity check because concurrent agents repeatedly modified repo files during the ~77 s image build (observed: `tests/test_exact_cache_telemetry.py`, `__init__.py`, `modal_transport.py`, `.baked_custom_node_deps/custom_node_deps_baked.json`); no paid generation has been billed. This section will record, once the run completes:

- `final_result_received` precedes `deferred_commit_end` by ~commit RTT (teardown-diagnostics markers, `COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS=1`)
- immediate asset fetch succeeds through bounded retry
- generator drains to completion (no `async_generator_athrow` warning)
- exit/teardown remains clean (exit hook ~30 ms)
- caller-visible improvement vs the 0.9–1.3 s commit baseline
