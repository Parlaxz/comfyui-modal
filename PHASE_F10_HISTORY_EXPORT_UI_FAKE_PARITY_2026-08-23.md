# Phase F10 — History Export UI, Fake Backend Parity & End-to-End Product Semantics (2026-08-23)

**Lane:** Batch F10 — IMPLEMENTATION (History V2 configured-folder Export frontend UX, repository adapter, fake/server F9 parity, F5 favorite-filter fake parity, browser/frontend tests).
**Base:** F3A Browser Download COMPLETE; F6 Resume/Retry COMPLETE; F7 Export core service COMPLETE; F2/F2A annotations COMPLETE; F5 backend favorite filter COMPLETE.
**Constraints honored:** NO production Python edits (`history_v2_routes.py` / `history_v2_repository.py` / `history_v2_export.py` / `history_v2_store.py` / `__init__.py` untouched), NO edit to `tests/run_studio_tests.py` (F9 owns registration), no Browser Download redesign, no GPU behavior change, no Resume/replay backend change, no History schema change. Deploy / Modal / GPU / live generation / commit / push / branch / reset: **NONE**. Shared dirty worktree preserved.

---

## 1. Verdict

**F10 verdict: PASS on this lane's scope.** Configured-folder Export is now a first-class, clearly distinct action family in mounted History V2 for Single Generation Preview and Original, every logical output's ⋮ menu, and Experiment cell panes — driven end-to-end by the frozen bodyless F9 contract (`POST /history-v2/assets/{asset_id}/export`) with truthful per-variant states (not_exported / exported / missing / failed), duplicate suppression, missing→re-export, failed→retry, partial-failure truth, already_exported idempotency, correct multi-output Asset identity, rerender-successor semantics, and zero conflation with Browser Download. The fake backend/server implement the F9 contract structurally (per-session per-Asset records, simulated destination files with lazy `missing` classification, one-shot failure arming, captured POST log), and the intentionally-deferred F5 §F5.3 fake favoriteOnly gap is closed. All F1B/F2A/F3A/F4C/F6 regression suites stay green.

## 2. Files modified by THIS lane ONLY

| File | Change |
|---|---|
| `web/history-v2-repository.js` | `exportAsset(assetId)` → `_v2ExportAsset`: exactly ONE bodyless POST to `/history-v2/assets/{id}/export`; no legacy Save route; structured ok/error envelopes normalize without discarding `saved / already_exported / export_state / reason / message / partial / destination_path / metadata_path / byte_count / file_ext / mime_type / exported_at`; already_exported resolves a SUCCESS; network/HTTP failures RESOLVE `{ok:false,…}` (no unhandled rejections); absent Asset ID never fetches. `normalizeHistoryOutput` threads `previewAssetId / previewExportState / originalAssetId / originalExportState` (snake_case authoritative; null when absent/unknown via exported `normalizeExportState`; Asset IDs NEVER parsed from URL text). Bridge repo exposes `exportAsset` as unavailable. |
| `web/history-v2-export.js` | NEW small helper module: `deriveExportAction(state, variant)` truth table (not_exported→"Export X"; exported→disabled "X exported"; missing→"Export X again"; failed→"Retry export X"), `exportResultNote` bounded truthful text (partial → distinct "Export partially failed — …" wording; failure prefers backend message; already_exported → "Already exported — <path>"), `buildConfiguredExportButton` native-button builder (per-button in-flight guard collapsing rapid duplicate clicks into one POST without blocking other outputs/variants; recovers after success AND failure; focus restored on failure; zero blob/anchor/download side effects; no transport of its own). |
| `web/studio-history-v2-detail.js` | Featured Preview slot gains `Export Preview` beside Download Preview; Original slot gains `Export Original` beside View Original / Download Original (independent third action; availability decided solely by the projected winner Asset ID — a failed producer Attempt without a retained winner projects none, so no dead control and Retry Original stays); per-output ⋮ menus gain `history-v2-output-export-{preview,original}-{index}` items addressing each output's OWN Assets (never a featured redirect, no client output index); dedicated `_runExport` runner (per-Asset in-flight Set, exactly one POST, immediate truthful note while refetching, then durable `reload()` whose server projection is the sole authority) + separate `history-v2-export-note` status line (never conflated with the Download note). |
| `web/studio-history-v2-experiment.js` | Cell detail pane gains `history-v2-cell-export-{preview,original}-<key>` buttons over the CELL'S OWN projected Asset IDs (Generation-backed parity; no Experiment-specific route, no batch/fanout); `_runCellExport` runner (per-Asset guard, one POST, durable Experiment refetch via `_rerenderPage`, feed `onChanged`); separate `history-v2-cell-export-note` line. |
| `tests/browser/fake/fake-backend.mjs` | Frozen F9 contract mirror: session `exportRecords/exportFiles/exportFailOnce/exportRequests` (+reset); per-output AND per-cell wire projection of `preview_asset_id / original_asset_id / preview_export_state / original_export_state` (null when absent OR when the asset is not servable — a failed/unregistered producer Attempt projects no identity); `exportHistoryV2Asset` (bodyless enforcement 400, unknown asset 404 `asset_not_found`, armed one-shot failures 500 with machine reason/message/partial, idempotent `already_exported:true saved:false` reuse, re-export after missing/failed, deterministic destination/MIME/ext/byte_count); lazy persisted `missing` classification when the simulated destination file was externally deleted; `_expMatchesV2` + `expFilters` gain the favorite constraint (F5 §F5.3 closure — true/false/absent semantics, applied pre-pagination inside the stream match); `dumpState` exposes export diagnostics. |
| `tests/browser/fake/fake-server.mjs` | Route `POST /comfymodal/history-v2/assets/:id/export` (200 ok/already · 404 · 400 non-bodyless · 500 armed failures); test controls `/__comfymodal_test/export-fail` (armed reasons incl. `partial:true`) and `/__comfymodal_test/export-delete` (external destination deletion). |
| `tests/browser/fake/studio-fake-history-v2-export.spec.mjs` | NEW — 21 deterministic browser tests (matrix below). |
| `tests/studio_phase_f6_history_actions_unit.mjs` | Sections 7–9 added (registered file): exact frozen route/bodyless pins, tolerant normalization incl. already_exported/partial/network envelopes, per-variant projection normalization (authoritative IDs, null-absent, no URL parsing), UI wiring pins (distinct Download/Export testids, single call sites, durable refresh, Export helper contains no blob-download machinery, Download helper performs GETs only). |
| `tests/studio_history_v2_download_unit.mjs` | Distinction pins: download labels never use Export wording; the configured-Export helper exists separately and never blob-downloads. |

Not touched: `scenarios.mjs` (default + existing seeds sufficed), all F9-owned production Python files, `tests/run_studio_tests.py`.

## 3. Semantics implemented

- **Export ≠ Browser Download.** Every Export control copies server-side into the configured Studio output folder via the bodyless F9 route; Browser Download controls keep their exact F3A labels/behavior and still fire zero export requests (pinned both directions). No control says just "Save". View Original untouched.
- **Per-variant independence.** Preview and Original carry independent projected states; exporting one never flips or suppresses the other; no generation-level collapse (browser-proven: after Original export, Preview button stays enabled `Export Preview`, and vice versa).
- **State truth table.** not_exported→enabled action; exported→disabled `<Variant> exported` (redundant active export suppressed); missing→`Export <Variant> again` (never rendered as "never exported"); failed→`Retry export <Variant>`. Absent variant (no servable Asset ID projected) renders NO control — older payloads without the projection simply show nothing.
- **Explicit refresh.** After every response the runner refetches the durable Generation/Experiment detail; local `exportState` is never optimistically mutated. The immediate response paints only a transient note.
- **Failure UX.** Backend `message` preferred, bounded ≤180 chars, machine `reason` preserved in the normalized envelope; partial:true surfaces the distinct "Export partially failed" wording and never shows Exported; failures never mutate Generation/Attempt status, favorite, note, or Download state.
- **Rerender semantics.** Generate Again creates a new winner Asset starting not_exported (UI offers Export Original for O2; old record remains historical provenance); a scripted failed rerender keeps the retained winner and its exported state with no false new Export action.
- **Auto-save is not Export.** Legacy save/auto-save materialization writes zero export records; only the explicit route mutates state (browser-proven).

## 4. Test evidence (exact counts)

Focused (this lane):

| Suite | Result |
|---|---|
| NEW `studio-fake-history-v2-export.spec.mjs` | **21/21 PASS** |
| Focused regressions: download(11) + resume-retry(7) + cancel-menu + annotations + history-v2 base + phase-e-original + grid-columns | **61/61 PASS** (7 spec files) |
| Node units (f6-actions incl. new §7–9, download incl. new pins, experiment, persisted-status, e4c, grid-columns, phase-e-contract) | **7/7 files PASS** |

Full wrapper `python tests/run_studio_tests.py --fake`:

```
python             run=1741  fail=0    error=0    skip=0
node-unit          run=21    fail=0    error=0    skip=0
fake-playwright    175 passed / 1 failed   (single timing-flaky playground-lifecycle
                    progress test, unrelated to this lane; passes 14/14 in isolation,
                    and the identical full suite passed 176/176 in a direct run
                    minutes earlier against a clean fake server)
FAILED LANES: fake-playwright (flake only)
```

Wrapper exit status: nonzero solely due to that one flaky Playwright test; python and node-unit lanes fully green. A first wrapper attempt also showed mass `ECONNREFUSED` createSession failures caused by a stale leftover fake-server process on port 8377 dying mid-run (environmental, not code); with a clean port the suite is green.

### Browser matrix coverage (new spec)

1–2 Preview not_exported→export + suppression; Original independent; both exported independently · 3 already_exported idempotent success (stale UI) · 4 missing→"Export again"→exported with managed asset servable throughout · 5 failed→truthful message→Retry export→exported · 6 partial:true distinct failure, never "Exported", durable failed · 7a–7c absent variants hide actions; failed Original w/o winner keeps Retry, loses Export · 8 retained winner addressed by its Asset ID · 9 two outputs address different Assets; featured change never redirects · 10 rerender successor starts not_exported, old record historical · 11 failed rerender retains exported winner · 12 Experiment cell pane parity, own Assets, one POST each · 13 rapid duplicate click ⇒ one POST · 14 Download sends ZERO export POSTs, state untouched · 15 Export causes NO browser download, exactly one POST (wire postData null) · 16 zero eager Export POSTs (render/menus/View Original inert) · 17 auto-save/save never marks exported · 18 favoriteOnly mixed feed = exactly favorited Generation + favorited Experiment, refresh retains, whole-Experiment favorite keeps working · 19 F2A cell favorite stays Generation-backed and independent under the filter.

## 5. Remaining integration (F9-owned)

When the parallel Production agent lands `history_v2_routes.py` route + per-output projection, the frontend consumes them unchanged (snake_case authoritative, tolerant of absent fields); rerunning the full gate then lets fake/frontend contract and production structural tests coexist. Thumbnail Export remains deliberately unexposed per scope.

Deploy / live / GPU / commit / push / branch / reset: **NONE**.
