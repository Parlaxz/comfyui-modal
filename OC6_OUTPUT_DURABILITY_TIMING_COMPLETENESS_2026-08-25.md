# OC6 — Batch Output: Output Durability, Timing-Completeness Forensic Audit (2026-08-25)

Mode: READ-ONLY forensic audit. No deploy, no paid run, no source/instrumentation changes.
Deliverables: this file + `OC6_OUTPUT_TIMING_CLAIMS_2026-08-25.csv`.
All event/field names below are copied verbatim from code or artifacts. Nothing is renamed; nothing is invented. Where a named boundary does not exist, the report says so.

Fact taxonomy used: **CURRENT SOURCE FACT** (read from working tree today, file:line), **HISTORICAL SOURCE STATE** (git commit), **REMOTE RAW ARTIFACT** (verbatim artifact excerpt), **HISTORICAL REPORT QUOTE**, **MEASURED (historical)**, **UNKNOWN / NOT FOUND**.

---

## 1. Referenced batch documents — existence check

Requested reading list vs filesystem reality:

| Requested | Exists in repo? | Search performed |
|---|---|---|
| Phase-O SoT + v2.1 | **NOT FOUND** | `glob **/*PHASE_O*`, filename scan `^(O\d|OB\d|OC\d|PHASE_O|PHASE-O)`, git grep `Phase-O|PHASE-O`, sibling dirs (`comfyui-modal-r42`, `comfyui-modal-r41.disabled`), `AI HUB` tree for `OC*.md` |
| O5 / O6 / O7 / O8 | **NOT FOUND as documents** | git grep `\bO[5-8]\b` in `*.md` → only unrelated hits (`OPENCODE_RTK_CBM_ADOPTION_REPAIR_2026-08-20.md` "Batch O4" = opencode tooling; `V2_GRAPH_CERT_SETUP_DECOMPOSITION.md` O1'–O4' = certificate setup) |
| OB5 output evidence / OB6 deferred-persistence evidence / OB7 output interfaces / OB8 challenges | **NOT FOUND** | git grep `OB[5-8]` across all tracked files → zero document hits |
| OC-series prior reports | **NOT FOUND** | same searches |

Substitute evidence actually used (all present): `E38B_CANONICAL_TIMING_AND_VALIDATION_CONTRACT_AUDIT.md` (canonical timing/validation contract), `E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md` + `config/v2/profiles/e37-clean-lane-qd4.toml`, `E36_FULL_CRITICAL_PATH_REPORT.md`, `E39_COMFYAPP_GOLDEN_PATH_PRUNING_REPORT.md` + `E39_REMOTE_GATE_RAW_LOG.txt`, `E40_CANONICAL_RUNTIME_TRUTH_AND_CLEANUP_REPORT.md`, `K1_GOLDEN_RESTORE_QUIESCENCE_SEAM_RECOVERY_REPORT.md`, `C8_BENCHMARK_COMPLETE_RUN_LOG.md`, `_last_trace_result.json`, current working-tree source, and git history (`dc8c4bc` 2026-07-26, `0ba7000` 2026-08-18).

If the O-series/OB-series material lives outside this repository, it was not reachable from here; every conclusion in this report is derived from the sources above instead. Per the audit mandate ("Derive semantics from code"), no conclusion depends on the missing docs.

---

## 2. GoldenOutput's contract — derived from the implementation

### 2.1 The gate definition (CURRENT SOURCE FACT)

The project's serialized gate `PYTHON_RESUME_TO_FIRST_DURABLE_MS` is implemented as the canonical ledger's authoritative serial window:

- `comfymodal_runtime/critical_path_ledger.py:32-35` — "Zero-gap contract: at request end ``build_serial_ledger`` constructs the serial ledger ``remote_python_resume_mono_ns -> first_durable_result_mono_ns``".
- `critical_path_ledger.py:83-98` — `_AUTHORITATIVE_ENDPOINTS`; `set_authoritative_endpoints(...)` requires both endpoints; a missing endpoint surfaces as `endpoint_status="missing"`.
- The END endpoint is stamped at exactly one site: `comfymodal_runtime/modal_app.py:19817` — `_ledger_event("first_durable_result", mono_ns=_emit_mono or time.monotonic_ns())` where `_emit_mono = int(data.get("remote_result_emit_mono_ns") or 0)` (`modal_app.py:19805`).
- `remote_result_emit_mono_ns` is captured by `_stamp_remote_result_emit()` (`modal_app.py:5412-5430`), called at `modal_app.py:19780`, immediately before `yield event` (`modal_app.py:19952`).

Therefore, **by implementation definition**:

```
first_durable_result_mono_ns  ≡  remote_result_emit_mono_ns
PYTHON_RESUME_TO_FIRST_DURABLE_MS ≡ remote_python_resume_mono_ns → first_durable_result_mono_ns
```

Raw confirmation (REMOTE RAW ARTIFACT, E39_REMOTE_GATE_RAW_LOG.txt ledger chain): `output_persist_done @ 264498220558` and `first_durable_result @ 264498220558` — identical stamps because both are emitted with the same `_emit_mono`. E38B §4 additionally measured Δ7.7 µs between container-wall emit and durable mono for E37.

### 2.2 What has physically completed when `first_durable_result` fires

Ordered, all awaited synchronously inside the remote request path before the stamp (CURRENT SOURCE FACT):

1. **Image encode** — output node (`ComfyModalProductionOutput`) encodes via PIL; PNG path: `pil_img.save(out_buf, format="PNG", compress_level=_png_level)` (`comfyapp.py:638`). `_png_level = _v2_png_compress_level()` (`comfyapp.py:577`); allowed values `{1, 6}`, default **1** (`v2_experiments.py:211-225`). So "current PNG level-1 path" = level 1 unless env override selects 6. Encode milestones: `output_encode_start` / `output_encode_end` emitted by the executor around that node (`modal_app.py:14453-14474`), with fallback `output_encode_end` at the persist boundary (`modal_app.py:15430-15440`).
2. **Output conversion accounting** — `output_conversion_end` (`modal_app.py:15417-15429`).
3. **Persist stage opens** — `output_persist_start` (`modal_app.py:15444-15449`); ledger span `result:assembly` opened (`modal_app.py:15469-15474`); ledger event `result_assembly_start` (`modal_app.py:15479-15488`).
4. **Asset write** — `_persist_output_assets()` (`modal_app.py:16082-16213`): each encoded item's bytes are written atomically (temp file + `os.replace`) to `/mnt/comfymodal_runtime_state/output_assets/<sha256><ext>` (`RUNTIME_STATE_PATH = "/mnt/comfymodal_runtime_state"` at `modal_app.py:284`; mount is the Modal Volume `runtime_state_volume`, fetched via `_MODAL_RESOURCES["runtime_state_volume"]` at `modal_app.py:16175`). Content identity = SHA-256 over final bytes (computed upstream per item; recomputed if absent, `modal_app.py:16097-16103`). Thumbnails likewise (graceful, non-fatal). Write window diag: `write_ms`, `write_end_mono_ns`.
5. **Volume commit STARTED but NOT awaited** — if anything was written, `commit_start_mono_ns` is stamped (`modal_app.py:16180-16181`) and `commit_volume()` is launched as an asyncio task (`asyncio.create_task(commit_volume())`, `modal_app.py:16212`). Commit failure inside the task raises, but only into the task.
6. **Descriptor/result construction** — `attempt_to_descriptor_result(...)` builds the descriptor-only payload (`use_descriptors: True`, `include_base64: False` — no image bytes travel in the result; `output_delivery.py:433-556`, descriptor fields incl. `identity="sha256:..."`, backend path, dimensions at `output_delivery.py:285-366`).
7. **`output_persist_end`** — duration = write + hash + descriptor window (`_descriptor_start_mono_ns` at `modal_app.py:15491` → `_descriptor_end_mono_ns` at `15506`; emitted `15507-15512`).
8. **Commit explicitly NOT awaited** — CURRENT SOURCE FACT, comment verbatim (`modal_app.py:15513-15516`): "Variant A: do NOT await the commit here — the result event must be yielded first." Stash: `self._deferred_commit_task/_deferred_commit_diag/_deferred_commit_pending` (`15517-15524`).
9. **Readiness mark** — `_v2_startup_stage("first_durable_result", "ready", phase="request", metadata={"output_persisted": 1})` (`modal_app.py:15525-15530`). This is a startup-stage readiness mark, NOT the ledger endpoint.
10. **Result emission stamps** — `_stamp_remote_result_emit()` sets `data["remote_result_emit_wall_unix_ns"]` / `data["remote_result_emit_mono_ns"]`, emits trace event `remote_result_emit`, records `handoff_payload_bytes` (`modal_app.py:5412-5474+`, called at `19780`).
11. **Ledger finalization at the same timestamp** — `output_persist_done` (ledger event, `modal_app.py:19809-19814`), `first_durable_result` (`19817`), close of span `result:assembly` (`19822-19828`), `set_authoritative_endpoints(first_durable_result_mono_ns=_emit_mono)` (`19835-19839`), ledger report captured into `data["canonical_ledger"]` with `canonical_ledger_status` ok/error (`19853-19873`).
12. **Yield** — `yield event` at `modal_app.py:19952`.

### 2.3 Candidate-owned work AFTER the stamp (deferred)

The generator tail runs after the result was already delivered (CURRENT SOURCE FACT):

- `await self._finalize_deferred_commit(request_id=request_id)` at `modal_app.py:19959` (and the finally-block fallback at `17995`).
- `_finalize_deferred_commit` (`modal_app.py:16215-16351`): awaits the stashed commit task; emits trace events **`deferred_commit_start`** and **`deferred_commit_end`** (with `status`, `commit_ms`, `detail`); on failure prints `[output_delivery] deferred commit failed: ...` and reports `status="failed"` — it MUST NEVER raise and cannot retract or invalidate the already-yielded result. Cache-hit/no-write case yields a skipped definitive persistence event with `commit_ms=0.0`.
- It then returns a `{"type": "persistence", ...}` event which is yielded (`modal_app.py:19977`) and attaches the `deferred_commit_*` events post-hoc into `result["trace"]["events"]` so the waterfall row `output_deferred_commit` ("Deferred persistence after yield", `v2_waterfall.py:2044-2045`) can render.
- The comment at `modal_app.py:19954-19958` states the container entrypoint drives the generator to exhaustion even when the client closes the stream, so the tail WILL run — but nothing protects durability against hard container death between yield and commit completion.

### 2.4 Answering the mandated question directly

> "What exact persistence condition does THIS implementation require before its result survives the intended container lifecycle and is available through its documented result path?"

Three distinct conditions, all proven from code:

| # | Condition | Required for | Where proven |
|---|---|---|---|
| C1 | Encoded bytes exist atomically under `/mnt/comfymodal_runtime_state/output_assets/<sha256><ext>` and descriptors carry matching SHA-256/path | Same-container retrieval; client fetch while THIS container lives | `modal_app.py:16105-16121`; `read_output_asset()` reloads volume, resolves path under root, verifies SHA (`16353-16375`); local fetch retries FileNotFoundError ×3 (`__init__.py:2651-2679` per recon) |
| C2 | `runtime_state_volume.commit()` completes successfully | Survival of the asset beyond this container's lifecycle (cross-container / post-teardown retrieval) | Volume semantics implied by explicit `volume.commit.aio` requirement (`16175-16179`); `reload_volume()` needed before cross-container read (`16354-16357`) |
| C3 | Result payload (descriptors) delivered to caller | Client-visible documented result path (descriptor mode) | `yield event` `19952`; descriptor contract `output_delivery.py:285-556` |

The declared gate `first_durable_result` fires when **C1 + C3** hold. **C2 is started before the stamp and completes strictly after it.** If the container dies between yield and commit completion, C1's file exists only in the dying container's staged volume state — cross-container durability fails even though `first_durable_result` fired and cannot be retracted.

Verdict on the gate itself: `first_durable_result` is **TOTAL by declaration** for the serialized GoldenOutput window (it IS the endpoint the ledger defines), and **PARTIAL with respect to full cross-container durability** (C2 outstanding, owned by the request-lifecycle tail, not teardown). The implementation intentionally ends GoldenOutput before C2; whether that intent is *correct* is an architecture question and is out of scope (no architecture selection in this batch).

---

## 3. Event relationship map (actual names only)

Remote monotonic axis, current code. Events that do not exist are stated as absent.

```
vae_decode_end
  └─ output_encode_start            (trace event, modal_app.py:14457)
  └─ output_encode_end              (trace event, modal_app.py:14471 or 15437)
  └─ output_conversion_end          (trace event, modal_app.py:15418)
  └─ output_persist_start           (trace event, modal_app.py:15445)
  └─ result:assembly [span open]    (ledger span, modal_app.py:15470)
  └─ result_assembly_start          (ledger event, modal_app.py:15481)
  └─ <atomic asset writes>          (NO named ASSET_WRITE_DONE event exists;
  │                                  local var _stage13_asset_write_end_mono_ns
  │                                  modal_app.py:15493; diag field
  │                                  write_end_mono_ns modal_app.py:16164)
  └─ commit START                   (NO named COMMIT_START event exists;
  │                                  diag field commit_start_mono_ns
  │                                  modal_app.py:16181; asyncio task created 16212)
  └─ output_persist_end             (trace event, modal_app.py:15507)
  └─ remote_result_emit             (trace event + data fields,
  │                                  modal_app.py:5467/5429-5430, called 19780)
  └─ output_persist_done            (ledger event @ emit mono, 19811)
  └─ first_durable_result           (ledger event @ emit mono, 19817)
  │                                   ≡ set_authoritative_endpoints end (19837)
  └─ yield event                    (RESULT_YIELD, modal_app.py:19952)
      └─ deferred_commit_start      (trace event, 16287/16288/16335 — post-yield)
      └─ <await commit task>        (COMMIT_DONE has NO pre-yield event; completion
      │                              lands only in diag update 16314-16315 +
      │                              deferred_commit_end 16339)
      └─ deferred_commit_end        (trace event, modal_app.py:16339)
      └─ yield {"type":"persistence"} (modal_app.py:19977)
```

Local-side sequence after receipt (separate host process/clock): `t9_modal_return` / `t9b_local_result_received` → `t9e_local_materialize_start` → `client_result_decode_start/done` → `client_file_write_start/done` → `client_comfy_notify_done` → `_finish_job` → ComfyUI queue history + local run-history store (+ local `history_v2.db` SQLite writer; `history_v2_writer.py:1-19` — explicitly LOCAL, not part of the remote durability contract).

Named-boundary existence statement:
- `IMAGE_ENCODE_DONE`, `ASSET_WRITE_DONE`, `COMMIT_START`, `COMMIT_DONE`, `RESULT_BUILT`, `FIRST_DURABLE_RESULT` (as a distinct event separate from emit), `EXIT`: **do not exist under those names.** Nearest actual equivalents are listed in §3 above. `persistence` exists ONLY as a post-yield event type string (`{"type": "persistence"}`), not as a telemetry event name.

---

## 4. Historical classes — what each number actually reached

### 4.1 Current waterfall parent `output_persistence` (application chain)

Producer (CURRENT SOURCE FACT, `v2_waterfall.py:1109-1119`):

```
start = output_encode_start (remote) | output_persist_start
end   = remote_result_emit boundary
        | output_persist_end | output_collect_end | output_encode_end
```

So today the parent stage ends AT the durable/emit boundary. Children (`v2_waterfall.py:2003-2045`): `output_vae_end_to_encode`, `output_png_encode` (else `output_encode_ms`), `output_descriptor` (encode_end→persist_end, else `output_commit_ms`), plus markers `output_remote_emitted` and `output_deferred_commit`.

Measured (REMOTE RAW ARTIFACT, E39_REMOTE_GATE_RAW_LOG.txt): parent `output_persistence` = **306.369902 ms**, `start_ns=264191850656`, `end_ns=264498220558` (= `first_durable_result`). Children: `output_png_encode` **184.494491 ms**, `output_descriptor` **7.860588 ms**, `output_vae_end_to_encode` ~0.58 ms, `output_deferred_commit` duration **null** (UNAVAILABLE in that artifact view).

### 4.2 C8-era class (~146–262 ms) — HISTORICAL REPORT QUOTE + HISTORICAL SOURCE STATE

`C8_BENCHMARK_COMPLETE_RUN_LOG.md` lists `output_persistence` values **140.971547 – 262.183896 ms** across its recorded runs (typical ≈ 200–250 ms). Producer of that era ended the stage at persist/collect boundaries (the `remote_result_emit` field did not exist until e28/e39 era — introduced by `0ba7000` 2026-08-18 / refined `0c59c46` 2026-08-22; C8 committed `25b8562` 2026-08-05).

Structural fact recovered from git (`dc8c4bc` 2026-07-26, the C8-era runtime): the executor flow was

```
await _persist_output_assets(...)     # writes + creates commit task
await asyncio.sleep(0)
build descriptors
emit output_persist_end               # commit STILL pending here
_asset_commit_diag = await _asset_commit_task   # commit awaited HERE
... method return → remote result packaging
```

Consequences, exactly bounded:
- C8 `output_persistence` (146–262 ms) = encode-start → persist_end: **PNG encode + asset write + descriptor build. Does NOT include commit wait.**
- BUT in that era the commit was awaited **before the method returned**, so any C8-era "returned result" implied commit-complete (C2 satisfied pre-return). Today (Variant A, since `0ba7000` 2026-08-18) the commit completes strictly after yield. This is a real semantic change in what "result returned" guarantees across eras — not merely cosmetic.
- Note on the "~166–247 ms" recollection in the batch prompt: literals 166/247 match `prompt_executor_cache_setup` values in C8 blobs (e.g., 166.258, 167.687, 245.189…) which are NOT output timings; the actual historical output class range is 140.97–262.18 ms. Both facts recorded to prevent mis-attribution.

Contamination warning for ALL waterfall-derived numbers: E38B §5 proves the waterfall SUMS mixed clock domains (V1–V4 violations; e.g., −7741.042 ms residual decomposition). Stage durations quoted above carry that contamination risk; the canonical-ledger numbers do not.

### 4.3 Canonical durable-window measurements

| Value | Source | Completion condition reached |
|---|---|---|
| 10,562.860481 ms | E38B §4 (E37 run `v2-benchmark-0-c9ac6e750942`, profile `e37-clean-lane-qd4`) | resume→first_durable, zero-gap ledger, `canonical_ledger_status="ok"`; `first_durable_result = output_persistence.end`; `remote_result_emit` Δ≈7.7 µs; `output_deferred_commit` UNAVAILABLE |
| 306.369902 ms parent + children (above) | E39 raw log | encode-start → emit/durable |
| 17,926.783 / 24,716.236 ms | E36 table | durable-endpoint values, decision endpoint separate from wall and post-durable tail |
| 14,313.273 – 28,619.637 ms (`first_remote_event_to_final_result_ms`) | K1:144; producer `tools/benchmark_v2_direct.py:2390-2416` = wall interval event `modal_first_event`→`final_result_received` (host clock, harness-side) | host-observed first-remote-event → final result receipt; includes handoff; placement-noise sensitive per K1 |

### 4.4 Legacy V1 trace classes (raw artifact `_last_trace_result.json`, MEASURED)

`t7_vae_decode_end=1781032757.066758` → `t8_image_written=1781032757.326011` (~259 ms, covered by delta `image_io=1629.51 ms` which spans a wider window in that schema) → `t7b_collect_start` (+1033 ms gap) → `t8b_outputs_collected=1781032758.9555166` → `t9_modal_return=1781032758.955526` (**Δ0.01 ms** — collect-end and return stamped together) → `t10_local_materialized=…759.681554` (+726.03 ms, local host side). Derived: `output_collection_total_ms=595.81`, `sampler_end_to_outputs_collected_ms=3158.25`. These stages measure the legacy V1 inline-image pipeline (images embedded in result, written locally) — a different delivery contract than the V2 descriptor path.

### 4.5 Codec timings (HISTORICAL REPORT QUOTE)

WebP encode 93.491 ms; original-PNG encode 179.011 ms (`PHASE_E_FINAL_CLOSURE_2026-08-22.md:67,268`; `PHASE_E7_LIVE_PREVIEW_ORIGINAL_GATE_2026-08-22.md:102,211-214`) — encode-only; excludes write, descriptor, commit, emit.

---

## 5. Classification (mandated fields)

Legend — MOC: MEASURED_OPERATION_COMPLETENESS (what the measurement physically covers); GPC: GOLDEN_PART_COMPLETENESS (which slice of resume→durable it represents); CONTAM: clock-domain/sum contamination; BEFORE/AFTER: candidate-owned work relative to the stamp; DRW: DEFERRED_REQUIRED_WORK; TIER: RAW_EVIDENCE_TIER (A1 remote raw artifact · A2 direct current-source verification · B1 committed historical report · B2 repo-root raw artifact · C git-historical source state).

1. **resume→first_durable (canonical)** — MOC: full serialized remote window per ledger endpoints; GPC: TOTAL (by declaration); CONTAM: none (single remote mono axis, endpoint-bounded); BEFORE: n/a (is the window); AFTER: C2 commit completion outstanding; DRW: yes — deferred commit, owner = runtime instance stash, finalized in generator tail; TIER: A1+A2. Verdict **TOTAL (declared) / PARTIAL (full cross-container durability)**.
2. **remote_result_emit** — MOC: instant of pre-yield stamping (payload serialization-ready; descriptors complete; assets written; commit pending); GPC: endpoint-equivalent to durable (Δ≤µs observed); CONTAM: none; AFTER: commit outstanding + actual transport not yet begun; TIER A2+A1. Verdict **PARTIAL for durability-C2, TOTAL for C1+C3**.
3. **output_persist_done** — despite the name it is stamped AT emit (`_emit_mono`), i.e. it means "descriptor assembly done at emission", NOT "volume commit done". Proven by identical stamps in E39 log and code `19812`. Verdict **PARTIAL**; name is misleading and must not be read as commit-completion.
4. **output_encode_start/end** — MOC: PIL encode loop inside output node; GPC: PARTIAL (encode only); TIER A2; verdict PARTIAL.
5. **output_conversion_end** — conversion accounting boundary; PARTIAL; TIER A2.
6. **output_persist_start / result_assembly_start / result:assembly span** — window open markers; span closes at emit (`19825-19827`); PARTIAL framing; TIER A2.
7. **output_persist_end.duration_ms** — MOC: asset write + hashing + descriptor build (NOT commit wait — commit only `sleep(0)`'d); GPC: PARTIAL; TIER A2; verdict PARTIAL.
8. **output_asset_write_ms (diag)** — write loop wall; PARTIAL; TIER A2.
9. **output_volume_commit_ms (diag)** — commit interval, but value materializes only after finalize updates the holder; in post-yield era it is NOT part of the request-path measurement; TIER A2; verdict PARTIAL/UNKNOWN-at-stamp-time.
10. **output_commit_overlap_ms** — computed pre-yield from partial diag (commit_end=0 until finalize ⇒ overlap effectively unmeasurable at that point); treat as diagnostic-only; TIER A2; UNKNOWN as a completeness claim.
11. **deferred_commit_start / deferred_commit_end** — the ONLY named events bounding commit completion; post-yield by construction; TIER A2 (+B1 E38B noting UNAVAILABLE in E37); verdict: this is the true COMMIT_DONE-class evidence, when present.
12. **output_deferred_commit (waterfall detail row)** — renders those events; frequently UNAVAILABLE in artifacts (E39 view null; E37 unavailable) — absence is expected when drain artifacts don't capture the tail, and must not be read as "commit didn't happen"; TIER A1+B1; UNKNOWN when null.
13. **C8 `output_persistence` 140.97–262.18 ms** — MOC: encode+write+descriptor (era without emit boundary); commit awaited later in-method ⇒ returned results of that era were commit-complete even though this stage doesn't include commit wait; CONTAM: waterfall sum risks (E38B V1–V4); TIER B1+C; verdict PARTIAL for GoldenOutput (ends one boundary short of emit), historically backed by stronger return-time guarantee.
14. **Legacy t8_image_written** — local write moment in V1 inline pipeline; different contract (inline base64); PARTIAL, legacy-only; TIER B2.
15. **t8b_outputs_collected / t9_modal_return** — stamped Δ0.01 ms apart; measures collection==return bookkeeping, not durability; PARTIAL; TIER B2.
16. **t10_local_materialized** — host-side materialization complete (decode+local write); AFTER remote durability entirely; local-contract TOTAL, remote PARTIAL; TIER B2.
17. **image_io / output_collection_total_ms / sampler_end_to_outputs_collected_ms (legacy)** — broad derived windows, mixed scopes; PARTIAL/contaminated; TIER B2.
18. **output_codec_ms / conversion_time_ms** — codec-only; PARTIAL; TIER B1.
19. **K1 `first_remote_event_to_final_result_ms`** — host wall, includes transport; reaches C3 (receipt) not C2; PARTIAL; placement-sensitive; TIER B1+A2(producer).
20. **`prompt_executor_cache_setup` (166–247 ms hits)** — NOT an output timing; recorded solely to kill the mis-attribution; N/A.
21. **read_output_asset() success** — the documented retrieval condition (reload + path-under-root + SHA verify): this is the strongest operational proof of C1; C2 only via a DIFFERENT container's successful fetch post-teardown (no such negative-path test found in artifacts reviewed — UNKNOWN for C2 survival proof).

---

## 6. Boundary-truth result table

| Historical/current telemetry name | Exact emitter | Exact semantic condition | Satisfies GoldenOutput completion? | TOTAL/PARTIAL/UNKNOWN | Candidate-owned work still outstanding |
|---|---|---|---|---|---|
| `remote_python_resume_mono_ns` | ledger restore bridge (endpoint) | Python resume point | start endpoint | (boundary) | — |
| `first_durable_result` (ledger) | `modal_app.py:19817` @ `_emit_mono` | emit-stamp instant: C1+C3 done, C2 pending | YES — IS the declared end endpoint | TOTAL (declared); PARTIAL vs full durability | C2 commit completion |
| `remote_result_emit` (+`*_wall_unix_ns`/`*_mono_ns`) | `_stamp_remote_result_emit` `5412-5474` via `19780` | immediate pre-yield stamp | endpoint-equivalent | PARTIAL (durability) / TOTAL (C1+C3) | C2; transport not yet started |
| `output_persist_done` (ledger) | `modal_app.py:19810-19814` @ `_emit_mono` | descriptor assembly done AT emission — NOT commit done | co-stamped with durable | PARTIAL (name misleading) | C2 |
| `output_persist_end` (trace) | `modal_app.py:15507-15512` | write+hash+descriptor window closed | no (pre-emit, pre-commit-await) | PARTIAL | emit pending; C2 pending |
| `output_encode_end` (trace) | `14471`/`15437` | PIL encode finished | no | PARTIAL | write+descriptor+emit; C2 |
| `output_asset_write_ms` (diag) | `_persist_output_assets` `16163` | atomic writes completed | contributes to C1 only | PARTIAL | descriptor+emit; C2 |
| `commit_start_mono_ns` (diag only — no event) | `16180-16181` | commit task about to be created | no | (boundary, unnamed) | C2 completion |
| `deferred_commit_start`/`deferred_commit_end` (trace) | `_finalize_deferred_commit` `16287-16343` | commit await begin/end POST-YIELD; status ok/failed | NO — strictly after GoldenOutput | post-gate (this is the real COMMIT_DONE-class pair) | none (it IS C2's measurement) |
| `output_deferred_commit` (waterfall row) | `v2_waterfall.py:2044-2045` | renders deferred pair; often UNAVAILABLE/null | no | UNKNOWN when null | — |
| `{"type":"persistence"}` event | yielded `19977` | definitive post-yield persistence verdict | no (post-gate) | post-gate | — |
| `output_persistence` (waterfall parent, current) | `v2_waterfall.py:1109-1119` | encode_start→emit/persist_end | reaches emit boundary | PARTIAL (excludes C2) | C2 |
| C8 `output_persistence` 146–262 ms class | same producer, pre-emit era | encode_start→persist_end | no | PARTIAL (era had pre-return commit await — see §4.2) | C2 (was awaited pre-return in that era) |
| Legacy `t8_image_written` | V1 local trace | local write moment (inline-bytes era) | no (different contract) | PARTIAL (legacy) | n/a legacy |
| `t8b_outputs_collected`≡`t9_modal_return` | V1 trace | collection/return bookkeeping | no | PARTIAL (legacy) | n/a legacy |
| `t10_local_materialized` | V1/host trace | host decode+write done | no — after remote gate | local TOTAL / remote PARTIAL | n/a |
| `first_remote_event_to_final_result_ms` (K1) | `benchmark_v2_direct.py:2390-2416` | host wall first-remote-event→final receipt | reaches C3 only | PARTIAL | C2 unknown from this metric |
| E37/E36/K1 durable-window numbers | ledger endpoints / harness | resume→first_durable | YES (declared) | TOTAL (declared) | C2 outstanding |

---

## 7. Deferred-work ownership summary

- Owner: runtime instance (`self._deferred_commit_task`, `self._deferred_commit_diag`, `self._deferred_commit_pending`; init sites `modal_app.py:5667-5669`, `6527-6532`; cleared `17872-17874`, `20086-20088`).
- Start: task created `16212` with `commit_start_mono_ns` stamped `16180` (BEFORE the durable stamp — start is pre-durable).
- Completion: awaited only in `_finalize_deferred_commit` (`19959` tail / `17995` finally); completion time lands in `deferred_commit_end` + diag update (`16314-16315`).
- Attribution rule honored: this work belongs to the REQUEST LIFECYCLE TAIL (candidate-owned), not to teardown — the stash/finalize machinery is request-scoped and runs while the stream generator is still driving, before `_release_gpu_after_request`/teardown paths in the finally block ordering (`17958-17999`). Attributing it to "teardown" would be wrong; attributing it to GoldenOutput would also be wrong under the declared endpoints.

## 8. Explicit UNKNOWNs

1. Whether C2 (post-yield commit) has ever been negatively proven (kill container between yield and commit → verify asset loss). No such test/artifact found in reviewed evidence. Until then, "asset survives intended container lifecycle" remains SUPPORTED INFERENCE from Volume semantics + code structure, not REMOTE PROOF.
2. `output_deferred_commit` numeric values: UNAVAILABLE/null in E37 (per E38B) and null in the E39 artifact view reviewed; no verified numeric commit_ms sample located in reviewed artifacts.
3. The requested Phase-O/O-series/OB-series documents: NOT FOUND (§1). Any claims attributed to them elsewhere could not be checked against this repo.
4. Exact split of the ≥1103 ms inter-machine clock skew vs network transit for emit→receipt (inherited UNKNOWN from E38B §6; unchanged here).

---

## 9. Raw evidence appendix

### A. E39_REMOTE_GATE_RAW_LOG.txt — ledger chain tail (verbatim)
```
  - sampling_end @ 263184840714
  - sampler_finally_done @ 263184997673
  - post_vae_decode @ 264191056018
  - graph_next_node_after_sampler @ 264372126859
  - result_assembly_start @ 264376475550
  - output_persist_done @ 264498220558
  - first_durable_result @ 264498220558
```

### B. E39_REMOTE_GATE_RAW_LOG.txt — waterfall parent + key children (verbatim excerpts)
```json
{
 "accounting_role": "top_level",
 "clock_scope": "monotonic:remote",
 "duration_ms": 306.369902,
 "end_ns": 264498220558,
 "key": "output_persistence",
 "label": "Output encode / descriptor",
 "provenance": "remote_trace",
 "source": "event",
 "start_ns": 264191850656,
 "status": "measured"
}
```
```json
{ "key": "output_png_encode", "duration_ms": 184.494491,
  "start_ns": 264191850656, "end_ns": 264376345147,
  "parent_key": "output_persistence", "clock_scope": "monotonic:remote", "status": "measured" }
{ "key": "output_descriptor", "duration_ms": 7.860588,
  "start_ns": 264376345147, "end_ns": 264384205735,
  "parent_key": "output_persistence", "clock_scope": "monotonic:remote", "status": "measured" }
{ "key": "output_remote_emitted", "label": "Remote result emitted",
  "end_ns": 1787364440212137253, "parent_key": "remote_return_handoff",
  "source_fields": ["remote_result_emit"], "status": "derived" }
{ "key": "output_deferred_commit", "label": "Deferred persistence after yield",
  "duration_ms": null, ... }
```

### C. C8_BENCHMARK_COMPLETE_RUN_LOG.md — sample stage blob (verbatim, one of many)
```json
{"application_restore":1017.210863,"clip_to_sampler_node":3393.938,"first_node_to_clip":289.895,"local_preparation":478.5712,"modal_handle_submission":397.5822,"modal_scheduling":6619.1986,"output_persistence":247.896758,"post_sampling_transition":608.40523,"prompt_executor_cache_setup":275.058,"remote_local_return":13.478648,"remote_method_setup":174.655516,"remote_return_handoff":null,"restore_to_method_entry":27.132634,"sampler_node_to_sampling":2233.246233,"sampling":4946.287275,"vae":513.577546}
```
Observed `output_persistence` range across the file: 140.971547 – 262.183896 ms.

### D. _last_trace_result.json — legacy stages/deltas (verbatim excerpts)
```json
"t7_vae_decode_end": 1781032757.066758,
"t8_image_written": 1781032757.326011,
"t7b_collect_start": 1781032758.3597088,
"t8b_outputs_collected": 1781032758.9555166,
"t9_modal_return": 1781032758.955526,
"t10_local_materialized": 1781032759.681554
...
"image_io": 1629.51,
"t8b_to_t9": 0.01,
"t9_to_t10": 726.03
...
"output_collection_total_ms": 595.81,
"sampler_end_to_outputs_collected_ms": 3158.25
```

### E. Current source — deferred-commit decision (verbatim, modal_app.py:15513-15529)
```python
            # Variant A: do NOT await the commit here — the result event must
            # be yielded first.  Stash the commit task + diag per-request; the
            # generator tail (_finalize_deferred_commit) awaits it and yields
            # a definitive persistence event.
            if _asset_commit_task is not None:
                self._deferred_commit_task = _asset_commit_task
                self._deferred_commit_diag = _asset_diag
                self._deferred_commit_pending = True
            else:
                self._deferred_commit_task = None
                self._deferred_commit_diag = _asset_diag
                self._deferred_commit_pending = True
            if not getattr(self, "_v2_first_durable_result_seen", False):
                self._v2_first_durable_result_seen = True
                _v2_startup_stage(
                    "first_durable_result", "ready", phase="request",
                    metadata={"output_persisted": 1},
                )
```

### F. Current source — durable stamps at emit mono (verbatim, modal_app.py:19805-19817)
```python
                    _emit_mono = int(data.get("remote_result_emit_mono_ns") or 0)
                    try:
                        _ledger_event(
                            "output_persist_done",
                            mono_ns=_emit_mono or time.monotonic_ns(),
                            metadata={"request_id": _t4_request_id or request_id},
                        )
                    except Exception:
                        pass
                    _ledger_event("first_durable_result", mono_ns=_emit_mono or time.monotonic_ns())
```

### G. Current source — commit task creation, never awaited in-path (verbatim, modal_app.py:16175-16213, abridged)
```python
        volume = globals().get("_MODAL_RESOURCES", {}).get("runtime_state_volume")
        commit = getattr(volume, "commit", None)
        commit_aio = getattr(commit, "aio", None) if commit is not None else None
        if not callable(commit_aio):
            raise RuntimeError("output volume commit.aio is unavailable")
        commit_start_ns = time.monotonic_ns()
        diag["commit_start_mono_ns"] = commit_start_ns
        async def commit_volume() -> dict[str, Any]:
            ...
                raise RuntimeError(
                    f"output volume commit failed: {str(exc)[:120]}"
                ) from exc
        commit_task = asyncio.create_task(commit_volume())
        return dataclasses.replace(attempt, items=tuple(persisted)), commit_task, diag
```

### H. Current source — post-yield order (verbatim, modal_app.py:19952-19959)
```python
            yield event

        # Variant A: the asset commit completes after the result event was
        # already delivered. ...
        _deferred_commit_event = await self._finalize_deferred_commit(request_id=request_id)
```

### I. HISTORICAL SOURCE STATE — dc8c4bc (2026-07-26), C8-era ordering (verbatim excerpt via git show)
```python
            _descriptor_start_mono_ns = time.monotonic_ns()
            selected, _asset_commit_task, _asset_diag = await self._persist_output_assets(selected)
            ...
            if _asset_commit_task is not None:
                await asyncio.sleep(0)
            with base64_counting_scope(selected):
                result = attempt_to_descriptor_result(...)
            _descriptor_end_mono_ns = time.monotonic_ns()
            trace.emit("output_persist_end", ...)
            if _asset_commit_task is not None:
                _asset_commit_diag = await _asset_commit_task
                _asset_diag.update(_asset_commit_diag)
```
(Commit awaited AFTER `output_persist_end`, BEFORE method return.)

### J. Git provenance
```
25b8562 2026-08-05 logs and manifests                      (C8 log committed)
dc8c4bc 2026-07-26 handoff                                 (_persist_output_assets + commit_aio; in-method commit await)
0ba7000 2026-08-18 e28: critical-path implementation ...   (Variant A deferral + remote_result_emit scaffolding)
0c59f46 2026-08-22 e39: prune superseded comfyapp paths .. (remote_result_emit refinement era)
```

### K. Waterfall producer — parent stage end selection (verbatim, v2_waterfall.py:1109-1119)
```python
    if key == "output_persistence":
        # Output encode/descriptor ENDS at direct completion: the remote result
        # emit boundary when present, else the persist/collect completion.
        start = event("output_encode_start", process="remote") or event("output_persist_start", process="remote")
        end = (
            _remote_emit_boundary(result)
            or event("output_persist_end", process="remote")
            or event("output_collect_end", process="remote")
            or event("output_encode_end", process="remote")
        )
        return _candidate(result, start, end, duration_keys=("output_collection_ms", "output_persist_ms", "output_commit_ms"))
```

### L. Ledger endpoint contract (verbatim, critical_path_ledger.py:32-35)
```
Zero-gap contract: at request end ``build_serial_ledger`` constructs the serial
ledger ``remote_python_resume_mono_ns -> first_durable_result_mono_ns``; every
nanosecond on that serial axis is represented.
```

---

End of report. No production telemetry renamed; no instrumentation modified; no deploy/run performed. Companion machine-readable table: `OC6_OUTPUT_TIMING_CLAIMS_2026-08-25.csv`.
