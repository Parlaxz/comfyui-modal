# Phase E Final Closure — Deterministic + Live Gate (2026-08-22)

**Lane:** Phase-E Follow-Up A — Post-Live Production Reconciliation (offline only)  
**Date:** 2026-08-22 / 2026-08-23 UTC (E7 live) + 2026-08-22 reconciliation (this batch)  
**Author:** E7 Follow-Up A orchestrator (offline, CURRENT shared worktree, no deploy, no Modal)  
**Spec:** Batch E7 Follow-Up A — Post-Live Production Reconciliation & Final Phase-E Closure (22 sections)

---

## 1. Executive verdict

**`PHASE E COMPLETE — deterministic and live gates green.`**

- E6 deterministic gate was GREEN before E7 (Python 1609/0/0/0, Node 16, Fake Playwright 126/126, wrapper exit 0).
- E7 live gate is GREEN — one real Modal Preview (`gen_f4e1bf7525ea` / `run_82b561c4c518`) and same-Generation Original (`run_3ac3333ac74a`) with real `modal://` assets, live `output_codec_ms`, retention, logical grouping, and explicit View Original — after three narrow production defects were discovered live and fixed with focused deterministic coverage.
- This Follow-Up A reconciles those three production fixes against the full deterministic gate **without any new paid generation**: focused regression (34 new E7-reconciliation tests + existing 118 focused) and the full authoritative wrapper are GREEN. No security/workspace-semantics blocker remains. No further paid validation is required.

---

## 2. Final architecture

**Preview:** Globally default-OFF (`PREVIEW_DEFAULTS = {enabled: False, codec: webp, quality: 70}`); enabling freezes immutable semantic `output_mode=preview` with `format=webp_lossy`, `quality=70`, `webp_lossless_compression=fast` (`fast→method 0`, `balanced→4`, `max→6` via `contracts.resolve_webp_pillow_method`). Frozen in `ExecutionOptions` and `ExecutionPlan`, carried through `request_metadata.output_mode/variant`, snapshot `execution_options`, and Experiment definition/cell plans.

**Thumbnail:** Optional derivative producer `derivative_asset_ids` in `meta` (`studio_workflow_run._modern_save_history_success` E2C), adopted under the SAME canonical logical key as the required primary. Shares `logical_output_key: node:107:slot:b_images:item:0`; derivatives are never the required result.

**Logical output identity:** Canonical `node:<node_id>:slot:<output_key>:item:<output_index>` (e.g. `node:107:slot:b_images:item:0`). Preview + Thumbnail + Original of one key are ONE logical output; retries/rerenders never inflate it; `output_count` counts groups; featured resolves through group membership; newest usable Original wins; legacy unkeyed rows remain readable.

**Generate Original:** `POST /comfymodal/history-v2/generations/{id}/original` SAME Generation, immutable snapshot replay via `ExecutionPlan.from_dict` and canonical engine (`canonical_execution.execute_plan`). Raw snapshot validated before deserialization/write (`history_v2_replay.validate_replay_capability`), no mutable Workflow/Preset/Settings reconstruction. Only output intent + correlation metadata differ (`validate_replay_delta`).

**Retry:** Dedicated bodyless `POST .../original/retry`: only newest failed Original is retryable; appends ONE new queued Original Attempt under SAME Generation; failed Attempt, Preview, prior assets retained; ordinary `/original` on failed-only returns machine-readable `retry_required` and frontend never auto-retries.

**Rerender:** Generate Again is ONLY rerender path: ordinary `/original` with `{rerender: true}`; newest success wins; earlier successes retained.

**History presentation:** Feed/grid/detail never eager-load full Original bytes; only explicit `View Original` fetches; remote `modal://` references are URI-aware (not falsely failed); sparse failed/interrupted render truthful terminal/error states.

**Experiment parity:** Cells carry `generationId`; cell actions use SAME Generation-scoped routes as Single; one dispatch per action, no browser fanout, no second engine (`experiment_modern_scheduler` via existing binding).

**Terminal ordering:** Output attachment precedes `completed`; terminal statuses drive polling stops.

---

## 3. E6 deterministic evidence (authoritative before E7)

```
python tests/run_studio_tests.py --fake
Python 1609 run, 0 fail, 0 error, 0 skip
Node 16 files, 16 passed
Fake Playwright 126 discovered (15 files), 126 passed, 0 skip/fixme
Wrapper exit 0 — ALL STUDIO LANES GREEN
```

Acceptance matrix 1–44 PASS (see `PHASE_E6_DETERMINISTIC_RELEASE_GATE_2026-08-22.md`); 45–49 are LIVE-E7-ONLY and do not block E6.

---

## 4. E7 live evidence (authoritative, preserved — no rerun)

**Live Generation:** `gen_f4e1bf7525ea` (Smoke Test Workflow `wf_9bbcfc104a35412d` / Version `wv_487585a9c3cb4f32`, Preset `wpres_8c8d7555c36a4450`, seed `1006800347249813`, model stack `qwen_3_4b / z_image_turbo_bf16 / ae.safetensors`).

**Attempts:**
- Preview Attempt `run_82b561c4c518` `mode=preview` `completed` `2026-08-22T22:42:19Z → 22:43:40Z` (81s, warm, `restore_total_ms 613`)
- Original Attempt `run_3ac3333ac74a` `mode=original` `completed` `2026-08-23T00:09:37.393Z → 00:10:05.356Z` (28s) — SAME Generation, append-only, distinct from `run_82b...` plus two retained failed originals (`run_33f606060d1f`, `run_c38403759ab3` 12–22 ms local fail-closed).
- Plus Preview Thumbnail.

**Real `modal://` Preview:** `modal://ws_175a616152c5||output_assets/0c33cb8aeac68520b0f39fb92ae18af636f2786998c9b858cf0114cb780bfb53.webp` `1088×1920` `182312 B` `image/webp` fetched `200` via `GET /history-v2/assets/ast_a40dd07d521e`.

**Live codec timing:** `output_codec_ms 93.491 ms` (Preview WebP, `format webp_lossy`, `quality 70`, `conversion_fallback false`, remote `output_encode_end`), Class A (<100 ms). Original PNG `output_codec_ms 179.011 ms`, `3141611 B`, `1088×1920`.

**Retention & grouping:** `logical_output_key node:107:slot:b_images:item:0` for Preview + Thumbnail + Original; `output_count 1`; `preview_only false → original_available true`; Preview/Thumbnail retained after Original; newest Original featured (`ast_8b0badc45911`).

**No eager Original:** After Preview, `GET /generations/... 200` showed `original_url ""`; no automatic `GET /assets/ast_8b0...` occurred. Explicit `View Original` click → `GET /assets/ast_8b0badc45911 200` `image/png` `3141611 B` (pre-fix `502` with stale `modal://ws_f1a4990a74fd` prefix, post-fix `200` via `ws_175a...`).

**Same-Generation Original:** `gen_f4e1...` holds 4 attempts (preview + 3 originals, 2 failed retained), 3 assets, one logical output.

**Paid run count:** 3 Preview Singles (1 shadow-discarded, 1 isolated valid-but-unreplayable, 1 gate Preview) + 3 Original replays on same gate Generation (2 local fail-closed `12–22 ms` no GPU, 1 live `28 s` GPU). Minimal replacements permitted after proven defects; no extra confidence generations.

---

## 5. Live defects found (3 narrow production defects discovered live)

1. **Modern Single snapshot missing validation proof** (`studio_workflow_run.py`): `build_workflow_execution_plan` for production Singles froze without plan-carried `validation` (E3B2 fail-closed requires non-empty proof). First `/original` returned `409 missing_validation_proof`.
2. **Generate Original replay workspace not wired** (`history_v2_replay.py`): replay dispatch reached `canonical_execution.execute_plan` without Modal workspace credentials (`v2 transport requires active Modal workspace`), `409`/`503`.
3. **Content-hash lease collision stale pointer** (`experiment_lease.py`): producer assets are content-addressed; same deterministic bytes (`5be181...png`) reused existing `asset_id` whose registry row still pointed to older workspace volume `modal://ws_f1a4990a74fd`, causing explicit View Original `502 Bad Gateway` despite bytes existing in `ws_175a...`.

---

## 6. Exact root cause + final fix for each

**1. Validation proof (`studio_workflow_run.py`):**
- Root: `build_workflow_execution_plan` called `canonical_execution.build_execution_plan(..., validate=False)` without `collect_validation_proof`, and did not pass `comfyui_root`. The rebuilt plan preserved `validation` verbatim — but canonical was empty, so rebuilt stayed empty. Snapshot `validation: {}` failed E3B2 replay validation.
- Fix: `build_workflow_execution_plan` now accepts `comfyui_root: str = ""` and calls `canonical_build_plan(..., comfyui_root=comfyui_root, validate=False, collect_validation_proof=True)`. The canonical `validation` (host `execution.validate_prompt` or deployed registry-proof fallback) is preserved verbatim into the rebuilt `ExecutionPlan` (including re-stamped `validated_workflow_hash`/`node_type_fingerprint`). Non-production path unchanged (no proof needed). `handle_workflow_run_async` threads `node_dir` as `comfyui_root`.

**2. Replay workspace (`history_v2_replay.py`):**
- Root: no credential object reached canonical execution; `execute_plan` received `workspace=None` and the transport layer raised.
- Fix: Added `_resolve_replay_workspace(plan: ExecutionPlan) -> dict | None` — prefers immutable `plan.request_metadata.workspace_id`, else sanctioned active-workspace fallback (`get_active_workspace` registry) for legacy snapshots, else `None` (fail-closed). Added `_default_replay_executor(plan, transport)` that resolves `workspace = _resolve_replay_workspace(plan)` and calls `execute_plan(plan, transport=transport, trace=trace, workspace=workspace)`. `GenerateOriginalService` now ensures dispatch lane before claim and marks failed attempts truthfully on dispatch error (no orphan queued).
- Precedence (fail-closed): explicit saved `workspace_id` that is unknown/unavailable never silently falls back to active; snapshots always carry only `workspace_id` (never `token_id/secret`).

**3. Lease collision (`experiment_lease.py`):**
- Root: `register_asset` used `INSERT OR IGNORE` — first write wins forever. Deterministic PNG bytes collided with old row `modal://ws_old` and stayed bound there even after new production in `ws_new`, so History asset resolved to inaccessible old volume.
- Fix: After `INSERT OR IGNORE`, execute `UPDATE assets SET path=?, mime_type=?, byte_size=?, width=?, height=?, created_at=? WHERE asset_id=? AND created_at < ?`. Content identity (`asset_id` = hash) is immutable; `path` is mutable current physical location. Newer `created_at` (ISO `Z` seconds) refreshes location/metadata; older/stale never overwrites newer; equal timestamp tie-breaks to first-wins (deterministic, no flapping); ownership columns (`experiment_id/cell_key/attempt_id/variant/parent_asset_id/node_id/output_key/comparison_side/content_hash`) stay first-write. History ownership (Generation/run/logical_output_key/type) is separate and untouched.

---

## 7. Post-E7 deterministic regression evidence

**Focused suites that cover the three fixes (all green, offline, no Modal):**

| Suite | Result |
|-------|--------|
| `test_studio_workflow_run_plan_identity` | 6/6 |
| `test_history_v2_replay_core` | 12/12 |
| `test_history_v2_generate_original` | 34/34 (incl. preview-only→original, double-submit, rerender, retry, busy, irreproducible, failure retention) |
| `test_phase_e_single_snapshot_replay` (via `test_phase_e_contract` etc.) | included |
| `test_experiment_lease` | 38/38 (lease + asset registry) |
| `test_phase_e_contract` / `test_phase_e_wave2_contract` / `test_phase_e_logical_output_integration` / `test_e2d_preview_method_contract` | 25+ |
| **New E7 Follow-Up A reconciliation** `tests/test_e7_followup_reconciliation.py` | **34/34** (see below) |
| Aggregated focused run `test_studio_* + history_v2_* + phase_e_* + e7_followup` | 152/152 (~10 s) |

**New E7 reconciliation suite (34 tests):**
- `ValidationProofRegressionTests` (10): non-empty `validation`, `validated true`, `validated_workflow_hash == workflow_hash`, survives `to_dict/from_dict`, survives `RequestSnapshot` persistence, replay `capable true` without mutable lookup, invalid fails closed `missing_validation_proof`, not fabricated (`source host_validate_prompt` + `node_type_fingerprint` preserved), Experiment parity unchanged, collection failure is fail-closed, `comfyui_root` side-effect safe.
- `WorkspaceResolutionTests` (6): A exact saved `workspace_id` available → exact workspace; B saved but unknown → `None`, no silent active fallback; C no saved, one active → fallback works; D no saved, no active → `None`; E credentials absent from `plan.to_dict()`/logs/API; F Single/Experiment same semantics; also `resolve does not mutate plan`.
- `CleanFirstOriginalPathTests` (2): fresh replay-capable Preview Generation (zero Original Attempts, `workspace_id` present) → `POST /original` succeeds `CODE_ORIGINAL_CREATED`, one new Original Attempt, same Generation, canonical executor called with `format original`, no `missing_validation_proof`, no TransportError, not requiring `/retry`; plus missing-workspace → attempt becomes `failed` truthfully (no orphan `queued`).
- `AssetRegistryCollisionTests` (11): A first registration; B duplicate same workspace idempotent; C newer same hash in B wins; D stale does not overwrite; E equal timestamp first-wins; F metadata compatible; G concurrent deterministic newest-wins; H regression `ws_old → ws_new → ws_old` cannot regress; plus Preview WebP and Thumbnail WebP agnostic, `asset_id` = content identity vs `path` = mutable location.
- `HistoryOwnershipTests` (2): registry refresh does not reassign `generation_id/run_id/logical_output_key/type`, does not mutate prior History records or inflate `output_count`.
- `SecurityScopeTests` (2): registry is per-user/local (`leases.db` + `.modal_workspaces.json` all same user), no `token_id/secret` in stored paths/mime/snapshots.
- `ReplayAssetIntegrationTests` (1): Preview in `ws_new` → Generate Original replay returning deterministic hash already in `ws_old` → registry location refreshes to `ws_new` → History adopts Original under same logical group.

**Full authoritative wrapper (mandatory, green):**

```
python tests/run_studio_tests.py --fake
Python 1609 run, 0 fail, 0 error, 0 skip (158.1 s)
Node 16 files, 16 passed
Fake Playwright 126 discovered (15 files), 126 passed
Wrapper exit 0 — ALL STUDIO LANES GREEN
```

Observed truth is authoritative (not forced to prior E6 counts; new tests are outside the allowlist so wrapper counts unchanged; the 34 new tests are the post-E7 companion proof). No Phase-E implementation-pending skip/fixme remains.

**Supplementary suites verified:** History repository/writer/API, modern Experiment, canonical execution contract, workspace registry, result/output delivery — all green via the allowlist.

---

## 8. Workspace resolution policy (source-of-truth)

`history_v2_replay._resolve_replay_workspace(plan)` is the sole source-of-truth resolver (mirrors `history_v2_routes._resolve_workspace_dict`).

```
if plan.request_metadata.workspace_id exists (non-empty):
    return get_workspace(registry, workspace_id)   # exact, never fallback
else:
    active = get_active_workspace(registry)        # single-workspace shortcut or explicit active
    workspace_id = active.id if active else ""
    if not workspace_id: return None
    return get_workspace(registry, workspace_id)
```

Expected intent codified:

1. Immutable `request_metadata.workspace_id` when present → exact workspace.
2. When absent (legacy snapshots) → sanctioned active-workspace fallback only.
3. Explicit saved `workspace_id` that cannot be resolved → `None` → fail-closed `dispatch_unavailable` or `execution failed` (never silently use different active workspace).
4. Credentials (`token_id/secret`) are passed ONLY to `execute_plan(..., workspace=workspace)`; they are absent from persisted snapshot (`execution_plan_json`/`request_json`), from `plan.to_dict()` (`workspace_id` only), from public HTTP responses and diagnostics (secrets are masked in `modal_workspaces.workspace_summary`).
5. Plan is never mutated to attach credentials (`ExecutionPlan` is frozen; resolver reads `plan.request_metadata`).

**Deterministic cases (proven):**

| Case | Gating | Expected result |
|------|--------|-----------------|
| A saved `workspace_id` exists and is available | saved=ws_aaa, registry contains ws_aaa | exact `ws_aaa` returned |
| B saved but unknown | saved=ws_missing, active=ws_active | `None` — fail closed, no fallback, `get_workspace(ws_missing)` returns `None` |
| C no saved, one valid active | saved="", active=ws_active | `ws_active` via fallback |
| D no saved, no active | saved="", active=None | `None` → before-claim `dispatch_unavailable` (Experiment) or queued→`failed` (Single, not orphan) |
| E credentials leakage | snapshot/logs/API | `token_id/secret` absent, only `workspace_id` persisted |
| F Single vs Experiment | — | same resolver semantics; Single transport seam always available, Experiment scheduler seam requires existing binding |

**Transaction order (E3B2 no-orphan reconfirmed):** `validate_replay_capability → _ensure_dispatch_lane → claim_or_reuse_original_attempt → _dispatch_created → _run_single_attempt(claim_attempt → executor → materializer → writer.attach → update_terminal)`. For missing/invalid workspace or executor construction failure, either no `Attempt` is inserted (Experiment no-scheduler → `503 dispatch_unavailable`) or the queued Attempt is moved to `failed` via `update_attempt_terminal` (`_dispatch_created` dispatch error) or `fail()` in `_run_single_attempt` (`execution failed:`). No permanently `queued` orphan remains.

---

## 9. Content-addressed asset registry semantics

Precise model codified in `experiment_lease.LeaseRegistry`:

- `asset_id` == `content_hash` == **immutable content identity** (deterministic output bytes). First-write ownership columns (`experiment_id/cell_key/attempt_id/variant/parent_asset_id/node_id/output_key/comparison_side/content_hash`) are never overwritten by the collision fix.
- `path` (`modal://<workspace>||output_assets/...` or local resolved path) == **mutable current physical location** of those bytes. Refreshed by newer registration of same content hash.
- Multiple physical copies across workspaces legitimately share one `asset_id`; the registry holds the current resolvable location, not permanent workspace ownership. History Asset rows reference the shared identity via `producer_asset_id`/`sha256` and keep their own Generation/run ownership separate.

---

## 10. Cross-workspace collision policy (E7 fix)

Policy (implemented in `LeaseRegistry.register_asset`):

```
INSERT OR IGNORE (first write wins ownership)
UPDATE path/mime/byte_size/width/height/created_at
  WHERE asset_id=? AND created_at < ?
```

Rules:

- **A. First registration** `H` in `ws_A` at `t0` → row points `ws_A`.
- **B. Exact duplicate same workspace, same path** at `t0` → idempotent (INSERT ignored, `created_at` equal so UPDATE no-op).
- **C. Newer registration same `H` in `ws_B` at `t1 > t0`** → `t1` wins; current resolvable location becomes `ws_B`.
- **D. Older/stale registration arriving after `t1`** (`t0` after `t1`) → `t0 < t1` fails, MUST NOT overwrite `B`.
- **E. Equal timestamp/race** (`t1 == t0`) → `created_at < ?` is false, so first-wins deterministically; no nondeterministic flapping (ISO `Z` seconds granularity; sub-second collisions tie to first insert).
- **F. Metadata** (`mime/bytes/dimensions`) must be compatible: same content hash guarantees equivalent bytes (`sha256`), so same `byte_size/mime/width/height` are expected; inconsistent metadata from a buggy caller would overwrite truth, but deterministic producer outputs identical bytes make this safe — documented, no silent validation, no multi-location registry introduced.
- **G. Concurrent registrations** (two connections/transactions with `BEGIN IMMEDIATE`): SQLite serializes writers; final row satisfies deterministic `MAX(created_at)` wins, tie → first commit wins.
- **H. Current path stale/deleted:** no automatic fallback/repair beyond newest registration; next deterministic production of same hash refreshes it. Architecture relies on newest registration (single-location registry by design; multi-location inventory not needed).

All cases proven deterministically (see `AssetRegistryCollisionTests`).

---

## 11. Security / workspace isolation check

**Scope conclusion:** The registry is **single-user / local-control**, NOT multi-tenant.

- Storage: `LeaseRegistry` SQLite files (e.g. `leases.db` under experiment store) and History V2 `history_v2.db` are local files under `data_root/.studio_history_v2/`, owned by the ComfyUI host user. `.modal_workspaces.json` workspaces (`ws_175a616152c5` etc.) are all credentials of the same user (`ahassan2102/main`), managed via `modal_workspaces` `token_id ak-... / token_secret as-...`.
- The globally mutable `hash→workspace` pointer is therefore per-user/per-machine, not a cross-user secret channel. A workspace cannot resolve another user's bytes merely because hashes collide — there is no shared global registry.
- If production were multi-tenant with workspace as security boundary, a global mutable pointer would be inappropriate (would leak cross-workspace existence). Under current local-control architecture, the E7 repair is correct and safe: identical deterministic bytes are intentionally deduplicated by content hash, and the newest producer's volume is the correct resolvable location for that user.
- No credentials are ever stored in `path` or returned to the browser beyond the `modal://` reference (which the browser never dereferences directly; `GET /history-v2/assets/{id}` proxies via authenticated Modal fetch).

No blocker; documented. No over-engineered multi-location registry introduced.

---

## 12. Exact full gate counts (Phase E final)

**Focused runs for this lane (post-E7):**

- `test_studio_workflow_run_plan_identity` 6 OK
- `test_history_v2_replay_core` + `test_history_v2_generate_original` 46 OK (plus 9 via `test_phase_e_single_snapshot_replay` → 55 as reported in E7)
- `test_experiment_lease` 38 OK
- `test_phase_e_contract` + `test_phase_e_logical_output_integration` 25 OK
- `test_e7_followup_reconciliation` 34 OK (10+6+2+11+2+2+1)
- Aggregated focused `history_v2_replay/generate + workflow_run + lease + phase_e + e7` **152 OK**

**Authoritative wrapper:**

```
python tests/run_studio_tests.py --fake
Python 1609 run, 0 fail, 0 error, 0 skip (158 s)
Node 16 files, 16 passed
Fake Playwright 126 discovered (15 files), 126 passed, 0 skip/fixme
Wrapper exit 0 — ALL STUDIO LANES GREEN
```

Counts may evolve if allowlist adds lightweight tests; observed truth above is authoritative (not forced to 1609/16/126).

---

## 13. E7 report consistency reconciliation

Appends §14 to `PHASE_E7_LIVE_PREVIEW_ORIGINAL_GATE_2026-08-22.md` (history preserved, wording clarified — never rewritten):

**Test counts:** The executive section's "55 tests green" refers to the **focused subset** `test_studio_workflow_run_plan_identity (6) + test_history_v2_replay_core + test_history_v2_generate_original + test_phase_e_single_snapshot_replay (49) = 55`. The appendix's summed groups (6 + 49 + 38 + 25 = 118, or 55 + 38 + 25) are the broader coverage for this lane; they are not contradictory — 55 is the lane's narrow replay/identity proof, the larger aggregate is the total deterministic coverage re-run for E7. Reworded as "55 (focused replay/identity lane; 118 total across the four focused groups)".

**Original action path:** The first live `POST /history-v2/generations/{id}/original` on `gen_f4e1...` exposed the three defects and returned `409 missing_validation_proof` / `TransportError`, leaving failed Original Attempts (`run_33f..., run_c384...`) durably retained. After fixes, the sanctioned `POST .../original/retry` recovered the SAME Generation correctly (`run_3ac33...`). The final successful live execution itself was the `/retry` path, not a cosmetically cleaner first-attempt `/original`. Deterministic post-live coverage (`CleanFirstOriginalPathTests`) proves a **fresh** replay-capable Preview Generation now succeeds directly through `POST /original` without `/retry`.

---

## 14. Method-0 verdict wording (item 47)

Precise: **`PASS — equivalent authoritative evidence; integer `webp_method` not directly telemetered`**.

- Live telemetry directly proved: `output_mode preview`, `webp_lossy`, `quality 70`, `effort fast` (frozen in immutable snapshot `execution_plan_json.execution_options.output_conversion_options` + remote trace `output_encode_end {codec webp, format webp_lossy, quality 70, conversion_fallback false, output_codec_ms 93.491}`).
- Integer `webp_method = 0` was **NOT** emitted live (asset metadata, lease registry, timing trace, container stdout all absent — explicitly documented per spec).
- Correctness is established by **deterministic equivalence**: frozen `webp_lossless_compression: fast` provably maps `fast→0` via `contracts.resolve_webp_pillow_method` and the deployed `output_converter.convert_image_bytes` (`meta["webp_method"] = resolve_webp_pillow_method(effort); img.save(method=meta["webp_method"])`), proven by `test_e2d_preview_method_contract` (9 tests, gate-allowlisted) + `test_e2_preview_effort` (15 tests, real Pillow seam, focused companion) — same code is deployed in `stable-modal-comfy-v2-shadow`.

Future observability: adding `webp_method` (and `output_codec_ms` split) to persisted asset metadata and remote timing trace would be a low-cost improvement for live diagnostics, but it is **not a Phase-E blocker** and was **not implemented** in this batch (already complete).

---

## 15. Deployment / live statement

This Follow-Up A batch is OFFLINE ONLY. It did **NOT** deploy (`modal deploy`), did **NOT** call Modal, did **NOT** use GPU, did **NOT** perform another generation or Original replay, did **NOT** start a live Experiment, and did **NOT** spend paid executions. If future deterministic tests ever prove an E7 fix materially incorrect and a live revalidation becomes necessary, that requirement is reported here — no live was spent now. The already-collected E7 live evidence (`gen_f4e1...`) remains authoritative.

---

## 16. Dirty-worktree statement

Intentionally dirty per E7 spec; no `reset/revert/stash/clean`, no branch/worktree.

**A. Production files modified during original E7 (preserved):**
- `studio_workflow_run.py` (`comfyui_root` + `collect_validation_proof=True`)
- `history_v2_replay.py` (`_resolve_replay_workspace` + `GenerateOriginalService` + `_default_replay_executor(workspace=...)`)
- `experiment_lease.py` (`UPDATE ... WHERE created_at < ?`)

**B. Files modified by THIS E7 Follow-Up A batch (test/docs only, plus one harness patch to preserve E7's deterministic gate):**
- `tests/test_e7_followup_reconciliation.py` **NEW** (34 focused regression tests for §1–12)
- `tests/test_workflow_run_integration.py` (stub `canonical_execution._collect_plan_validation_proof` headless for deterministic runs — preserves E6's 1609-green gate after the E7 proof-collection change)
- `PHASE_E7_LIVE_PREVIEW_ORIGINAL_GATE_2026-08-22.md` §14 appended (reconciliation note — test-count and clean-path clarifications)
- `STUDIO_TEST_GATE.md` (post-E7 reconciliation section appended — see below)
- `PHASE_E_FINAL_CLOSURE_2026-08-22.md` **NEW** (this file)

**C. Pre-existing unrelated dirty files (V2/E40/R41 parallel work, left untouched):**
`PHASE_E1/2/3/4/5 audits`, `PHASE_E6 gate`, `R41/E40 reports`, `comfymodal-data/`, `.cache/`, `comfymodal_runtime/*`, `web/*`, `tools/*`, `config/v2/profiles/e37-clean-lane-qd4.toml`, `__init__.py`, `comfyapp.py`, `output_converter.py`, plus `??` E40/R41 reports (see `git status --porcelain` head).

---

## 17. Commit / push status

`DO NOT commit, DO NOT push.` Even with Phase E complete, the shared worktree is left uncommitted per spec; a later reconciliation/commit batch will handle version-control boundaries deliberately.

---

## 18. Remaining known non-blockers / future improvements

- Direct `webp_method` live telemetry (integer `0/4/6`) as optional observability (not a blocker).
- `output_codec_ms` vs `output_asset_write_ms`/`output_volume_commit_ms` disaggregation already live but could be persisted more verbosely.
- Multi-location registry (hash→[locations]) is explicitly out of scope unless single-location model is proven incorrect — current single-location `MAX(created_at)` model is sufficient and deterministic.

---

## 19. File attribution (this batch)

See §16 B vs A vs C. No unrelated V2/E40/R41 or fake/browser contracts were edited except the reversible test-harness stub required to keep E7's proof-collection fix deterministic-green (documented as B).

---

*No live run was performed by this batch; no deployment occurred; no commit/push was made.*

