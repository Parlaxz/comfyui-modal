# Phase F9 — History V2 Configured-Folder Export PRODUCTION Integration (2026-08-23)

**Lane:** Phase F batch F9 — IMPLEMENTATION (production backend Export route + per-variant projection + gate registration).
**Baseline:** F7 Export core COMPLETE (`PHASE_F7_HISTORY_V2_EXPORT_CORE_2026-08-23.md`) + F3 export/download audit + F4 settings-consumer authority audit + Phase E closure.
**Constraints honored:** NO History frontend JS edits, NO fake-backend/browser fixture edits, NO GPU-authority changes, NO replay/resume semantics changes, NO Experiment scheduler changes, NO Browser Download behavior changes, NO legacy run-history Save reuse, NO deploy / Modal / GPU / live generation / commit / push / branch / worktree. No subagents. Worked in the CURRENT shared tree alongside the parallel F10 frontend/fake lane (zero F10-owned files touched).

---

## 1. Verdict

**F9 PASS.** The bodyless configured-folder Export route exists and works against local AND fake `modal://` managed sources; Output settings are read live from the canonical server authority at POST time; the logical-output index is derived server-side from current History V2 grouping (never hardcoded 0); Preview/Original export states project independently with winner-accurate asset ids; missing/re-export, duplicate idempotency, and rerender non-transfer all hold; Experiment cells carry identical semantics; a narrow per-Asset concurrency guard makes duplicate simultaneous POSTs safe; F7's suite plus the new 26-test HTTP integration module are registered in the main Studio gate and everything is green.

## 2. Files modified by THIS lane ONLY

| File | Change |
|---|---|
| `history_v2_routes.py` | NEW `POST /assets/{asset_id}/export` route; `settings_provider` injection param; shared `_read_remote_managed_bytes`/`_ManagedAssetError`/structural pre-flight factored out of asset GET; `_derive_output_index`; `_export_options_from_settings`; `_export_naming_from_detail`; per-Asset lock registry; per-variant projection in `_build_outputs`/`_generation_feed_item`/`_cell_generation_payload`; detail-route projector wiring; deprecated aggregate re-derived |
| `__init__.py` | Composition root wires `settings_provider=_load_modal_settings` into `register_history_v2_routes` (one call site) |
| `tests/test_history_v2_export_integration.py` | NEW — 26 focused HTTP integration tests (full §20 matrix) |
| `tests/test_history_v2_api.py` | Seeded export record now points at a REAL destination file (lazy checker would truthfully classify a nonexistent path as `missing`); added per-variant projection assertions |
| `tests/run_studio_tests.py` | Registered `tests.test_history_v2_export` (F7) + `tests.test_history_v2_export_integration` (F9) in `STUDIO_PY_MODULES` |
| `PHASE_F9_HISTORY_V2_EXPORT_INTEGRATION_2026-08-23.md` | NEW — this report |
| `PHASE_F3_HISTORY_EXPORT_DOWNLOAD_AUDIT_2026-08-22.md` | Appended F9 closure subsection |

Nothing else touched. F10-owned files (`web/*`, `tests/browser/fake/*`, Node unit specs) untouched.

## 3. Route contract (frozen)

`POST /comfymodal/history-v2/assets/{asset_id}/export` — BODYLESS. The selected `asset_id` uniquely identifies the managed source; the server derives and validates everything else:

1. Asset exists in durable History V2 (`404 asset_not_found` otherwise).
2. Structural availability WITHOUT fetching bytes, mirroring managed-asset GET truth: local path must be an existing file; `modal://` must parse and its workspace must resolve (`404`, no record written — no real attempt occurred).
3. Generation association derived from the asset's own durable `generation_id` (`repo.get_generation`); client generation identity is never accepted.
4. Real logical-output index via `_derive_output_index` (below); unresolvable → fail-closed `500 output_index_unresolved`.
5. Live canonical Output settings via injected provider; exactly one F7 `ExportOptions` built.
6. Naming context from immutable RequestSnapshot (+ Generation fallback); current mutable Workflow/Preset never consulted.
7. F7 `HistoryV2ExportService.export_asset(...)` under a per-Asset lock; result mapped to HTTP.

Success (200): `{status:"ok", asset_id, export_state, saved, already_exported, destination_path, metadata_path, byte_count, file_ext, mime_type, exported_at}`. New export: `saved:true, already_exported:false`. Exact repeat while the destination exists: `saved:false, already_exported:true` (the F7 core reports `saved=true` on reuse; the HTTP surface maps it to the frozen contract). Missing-then-re-export: `saved:true, already_exported:false`.

Errors (stable machine-readable payload `{status:"error", asset_id, reason, message(≤200 chars), export_state, partial}`):

| Condition | HTTP | reason | export_state |
|---|---|---|---|
| unknown asset_id | 404 | `asset_not_found` | not_exported |
| local file missing / workspace unavailable / remote missing after retries | 404 | `source_unreadable` | not_exported (pre-flight, no record) / failed (fetch attempt) |
| malformed `modal://` origin | 400 | `source_unreadable` | not_exported |
| remote retrieval failure | 502 | `source_unreadable` | failed |
| resolver not wired | 502 | `remote_resolver_unavailable` | failed |
| SHA mismatch | 502 | `hash_mismatch` | failed |
| conversion failure | 500 | `conversion_failed` | failed |
| write failure | 500 | `write_failed` | failed |
| record persistence failure | 500 | `record_persist_failed` | failed (**partial:true preserved**) |
| settings provider absent/raising | 503/500 | `settings_unavailable` | not_exported |
| index unresolvable | 500 | `output_index_unresolved` | not_exported |
| unexpected crash | 500 | `export_failed` | failed |

No credentials, access keys, stack traces, or raw internal exceptions beyond the bounded exception-text convention already used by the managed-asset GET (`str(exc)[:200]`).

## 4. Settings authority

New explicit `settings_provider` dependency on `register_history_v2_routes`; the composition root passes `__init__._load_modal_settings`. No circular import (routes never import `__init__`), no settings-file parsing duplicated. The provider is invoked ONCE per export POST — proven live by a test that changes `save_folder` between two POSTs and gets an explicit second export into the new folder (never a false duplicate). Only the five canonical keys are consumed (`save_folder`, `output_format`, `quality`, `webp_lossless_compression`, `save_metadata_sidecar`); no Export-specific settings invented; no localStorage/window globals.

## 5. Server-derived output index

`_derive_output_index` walks the SAME `_logical_output_groups` ordering that `_build_outputs` publishes as each output's canonical `index`. Consequences (all tested): a Preview and Original sharing a logical key resolve to the SAME index; multi-output generations get distinct real indices encoded in filenames (`_0.png` / `_1.png`); legacy unkeyed assets remain resolvable via run/asset provenance; Thumbnails map if they reach the route; an unmappable asset fails closed with `output_index_unresolved` instead of silently exporting as index 0.

## 6. Remote byte resolution (shared, not divergent)

The asset GET handler's exact `modal://` behavior was factored into `_read_remote_managed_bytes` (+ `_parse_modal_reference`, typed `_ManagedAssetError`, structural pre-flight helper). BOTH the GET route and the F9 Export byte resolver use it: identical URI parsing, lazy workspace resolution, 3-attempt FileNotFoundError retry ladder (0.25s/0.5s), `expected_sha256` verification inside `modal_client.read_output_asset`, identical status classification. A request-scoped classification cell lets the route map the F7 `source_unreadable` reason to its truthful status (404 remote-missing vs 502 retrieval failure) without touching F7 semantics. Projection NEVER fetches remote bytes (tested: zero `read_output_asset` calls across repeated detail GETs; ≥1 after explicit POST).

## 7. Per-variant projection & winner identity

Generation detail and every embedded Experiment cell Generation now project, per logical output:

```
preview_asset_id, preview_export_state      # null when variant absent
original_asset_id, original_export_state    # null when variant absent (NEVER "not_exported" for nonexistent)
```

States are exactly `not_exported | exported | missing | failed`, computed through the F7 lazy checker (`get_export_state(persist_missing=True)`): record exported + file gone → classified and persisted `missing`; unrelated exports never scanned; managed source untouched. Projected ids come from the SAME winner objects as the projected URLs, so URL + asset id + state always describe one selected Asset — proven for retained-winner-after-failed-retry (winner keeps `exported`) and new-rerender-winner (starts `not_exported`, predecessor's record untouched). Feed pages intentionally do NOT project export fields (no per-asset lookups on hot paths). Thumbnail projection omitted (falls out of grouping naturally but Phase-F UI does not expose it).

The old collapsed generation-level `export_state` is RETAINED as documented DEPRECATED aggregate compatibility only, now DERIVED from the lazy per-variant truth (`"exported"` iff any projected variant is exported, else `"none"`) so it can never contradict the per-variant fields. Frontends must move to the per-variant fields (F10).

## 8. Duplicate / missing / rerender semantics (F7 preserved)

First export → `saved:true`. Exact repeat → `already_exported:true`, zero duplicate files. Externally deleted destination → detail projects `missing` → next explicit POST re-creates it → `exported`. Folder/format change → explicit new export, old copy untouched, record repointed. Rerender successor begins `not_exported`; no state transfer via shared `logical_output_key`.

## 9. Concurrency

F7 audit: the core alone could interleave two same-asset POSTs between `_unique_filename` and record upsert (benign for identical bytes, but capable of producing two competing destinations under concurrent option changes). Fix: narrowest process-local per-Asset `asyncio.Lock` registry at the route layer — same-asset POSTs serialize; different assets never block; no global serialization. Regression test: two concurrent POSTs → both 200, exactly one file, one record, saved flags `{false, true}`, single destination.

## 10. Separation guarantees held

Browser Download (managed-asset GET) writes ZERO export state (tested: record stays None, projection stays `not_exported`). Execution-time auto-save materialization untouched (no ExportRecord). No legacy run-history dependency anywhere in the chain.

## 11. Tests

New `tests/test_history_v2_export_integration.py` — **26/26 OK**, covering the full §20 matrix: local Preview/Original exports (1–2), fake `modal://` Preview/Original via patched `modal_client.read_output_asset` (3–4), unknown-asset 404 + exact error shape (5), remote retrieval failure 502 (6), remote-missing 404 after retries (7), workspace-unavailable 404 no-record (8), local-missing 404 no-record (9), SHA mismatch 502 (10), conversion failure 500 (11), write failure 500 (12), already-exported response (13), missing→projection→re-export (14), Preview/Original independence + nonexistent-Original-null (15–16), distinct real indices (17), retained-winner-after-failed-retry (18), rerender-winner-not_exported (19), Experiment cell parity (20), zero eager remote fetches during projection (21), Download-writes-no-state (22), concurrent-duplicate safety (23), live-settings-at-export-time (24), snapshot-only naming incl. sidecar identity (25), bodylessness/client-identity ignored (26).

Gate registration: `tests.test_history_v2_export` (F7, 33 tests) + the new module added to `STUDIO_PY_MODULES` in `tests/run_studio_tests.py` (this lane owns the runner for F9; F10 excluded by agreement).

## 12. Verification counts

Focused regression (all deterministic, offline):

- `tests.test_history_v2_export` + `tests.test_history_v2_export_integration`: **59/59 OK**
- History V2 repository / API-routes / Phase-E logical-output integration / Phase-E History projection / F5 backend truth / F1A Resume / Generate Original / output_saver / output_contract: **226/226 OK**
- Converter lanes (e2 codec, e2d method contract, e2 effort) + migration / mixed-pagination / production-writer / modern-experiment / replay-core: **144/144 OK**

Full Studio wrapper `python tests/run_studio_tests.py --fake`: **python 1741 run / 0 fail / 0 error / 0 skip · node-unit 21/21 PASS · fake Playwright wrapper PASS exit 0 (176 tests) — ALL STUDIO LANES GREEN.**

One intermediate wrapper run showed 5 fake-lane failures (4× `studio-fake-history-v2-export.spec.mjs`, 1× `studio-fake-workflow-run.spec.mjs`) while the parallel F10 lane was mid-edit; the workflow-run case passed identically in isolation and the entire fake lane passed cleanly on rerun with ZERO F10-owned files modified — transient ownership truth, not a production regression. All F9/F10 export specs run exclusively against the FAKE backend; none exercise production routes.

## 13. Remaining work (frontend only — F10)

Consume the frozen route + per-variant projection in `web/studio-history-v2-detail.js` / `studio-history-v2-experiment.js`: per-variant Export actions, `already_exported` suppression, `missing` recovery affordance, and migration off the deprecated generation-level `export_state` aggregate.

Deploy / live / GPU / commit / push: **NONE**.
