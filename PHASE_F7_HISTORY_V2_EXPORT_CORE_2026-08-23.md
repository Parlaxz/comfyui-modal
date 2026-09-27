# Phase F7 — History V2 Configured-Folder Export CORE Service (2026-08-23)

**Lane:** Phase F batch F7 — IMPLEMENTATION (isolated History V2 Export core + focused tests).
**Baseline:** F3 export/download audit + F4 settings-consumer authority audit + Phase E closure.
**Constraints honored:** NO route wiring, NO frontend edits, NO edits to concurrent-lane owner files (`history_v2_routes.py`, `history_v2_repository.py`, `__init__.py`, `web/studio-history-v2-detail.js`, `web/studio-history-v2-experiment.js`). No deploy / Modal / GPU / live generation / commit / push. No subagents.

---

## 1. Verdict

**F7 PASS.** A standalone, route-agnostic History V2 configured-folder Export core now exists (`history_v2_export.py`), exporting any selected managed asset — local OR `modal://` — into the canonical output folder with durable per-`asset_id` `export_records` truth. Local assets and fake-resolver remote assets both export successfully; Preview/Original export state is fully independent; duplicate/missing/recovery semantics are truthful; failure ordering never persists `exported` before the destination file is durably written; there is zero legacy run-history dependence. Focused suite: **33/33 pass**; adjacent regression lanes all green (100 additional tests).

## 2. Files modified by THIS lane ONLY

| File | Change |
|---|---|
| `history_v2_export.py` | NEW — the Export core service |
| `tests/test_history_v2_export.py` | NEW — 33 focused tests |
| `PHASE_F7_HISTORY_V2_EXPORT_CORE_2026-08-23.md` | NEW — this report |
| `PHASE_F3_HISTORY_EXPORT_DOWNLOAD_AUDIT_2026-08-22.md` | Appended F7 closure note (§16) |

Nothing else was touched. The full Studio wrapper was NOT run (module deliberately not registered into `tests/run_studio_tests.py` while concurrent F5/F6 lanes are active; registration belongs to the integration batch).

## 3. Service API

```python
service = HistoryV2ExportService(
    repository,                      # get_asset / get_export_record / upsert_export_record
    byte_resolver=None,              # async-or-sync (Asset) -> bytes for modal:// assets
    converter=None,                  # default: output_converter.convert_image_bytes (lazy)
    clock=utc_now_iso,
)

await service.export_asset(asset_id, options, naming) -> ExportResult
service.get_export_state(asset_id, persist_missing=True) -> ExportStateView
```

- `ExportOptions` (frozen): `save_folder`, `output_format`, `quality`, `webp_lossless_compression`, `save_metadata_sidecar` — exactly the F4-canonical Output settings domain; **no new settings invented**, settings authority stays entirely outside the service (no `.modal_settings.json`, localStorage, or window-global reads).
- `ExportNamingContext` (frozen): real `output_index` (validated non-negative int; fixes the legacy hardcode-index-0 weakness), plus optional `workflow_name/workflow_hash/preset_id/preset_name/seed/comfyui_root`.
- `ExportResult`: `status ok|error`, `reason` (`asset_not_found | remote_resolver_unavailable | source_unreadable | hash_mismatch | conversion_failed | write_failed | record_persist_failed`), `saved`, `already_exported`, `state`, `destination_path`, `metadata_path`, `byte_count`, `file_ext`, `mime_type`, `quality`, `exported_at`, `partial`, `orphan_path`.
- All mutable collaborators are injected; no module-global mutable state.

## 4. Source resolution & remote support

- Local managed path → read directly by the service.
- `modal://workspace||gpu||path` → delegated to the injected byte resolver (the established URI-aware serving seam; the future route wraps `modal_client.read_output_asset`). Remote availability is NEVER classified with `os.path.isfile(modal_uri)`.
- Resolver may be sync or async (`inspect.isawaitable`), so the same core serves sync tests and the async aiohttp route without editing route code.
- Missing resolver + `modal://` asset → truthful error `remote_resolver_unavailable` with **no record write** (no real attempt occurred).
- Resolver raising (remote retrieval failure) → real attempt → record becomes `failed`; no destination file; no false `exported`.

## 5. Hash / identity

Single hashing model: the immutable `assets.sha256`. Whenever the asset carries a SHA-256, resolved bytes are verified before any write; mismatch → `failed` record + error result, no corrupted output ever written, managed source untouched (proven for local corruption AND fake-remote mismatch). This is a strict superset of the serving path's remote-only verification and reuses the same digest model — no second hashing scheme.

## 6. Conversion / options semantics

- `output_format == "original"` → byte-preserving fast path; converter is provably never invoked (spy test).
- Otherwise the canonical `output_converter.convert_image_bytes` runs with the resolved quality/WebP-effort options. A converter exception, invalid result, or silent PNG-fallback-with-error is rejected as `conversion_failed` (no "asked WebP, got PNG" lie); record becomes `failed`, nothing written.
- Input variant identity stays Preview/Original; exported file format follows resolved options; bookkeeping stays attached to the source `asset_id`.

## 7. Save folder / filename / path safety

- Folder resolution reuses `output_saver._resolve_save_folder` verbatim (absolute paths honored; legacy `output/modal` migrates to the external data root; relative paths anchor at ComfyUI root). Layout parity: `<resolved>/images` + `<resolved>/metadata`.
- Deterministic filename from ASSET identity, not wall clock: `{asset.created_at stamp}_{workflow_name|hash12|generation}_seed-{seed}_{real_output_index}{ext}` — required so idempotent reuse maps to the same path; `_unique_filename` anti-collision prevents silent overwrite of a different export; name component capped at 80 chars (MAX_PATH guard).
- Containment invariant asserted in-code: sanitization strips every separator, and the final destination must sit exactly inside the resolved images dir. Tests cover traversal-like names, Windows-invalid chars, Unicode/emoji, control chars, and 5000-char names — all contained, all < 260 chars.

## 8. Duplicate / missing semantics

- Idempotency gate: record `exported` + destination file exists + recorded destination matches currently resolved folder (+ target extension when converting) → `already_exported` reuse, zero new files.
- Record `exported` but file gone → classified and persisted `missing` FIRST, then explicit re-export proceeds (same deterministic path restored).
- Folder or format change → treated as an explicit export request, never a false already-exported hit (old copy left untouched; record repointed).
- Quality-only changes cannot be detected from the frozen one-row-per-asset record schema and reuse the existing copy (documented; matches legacy gate strictness which ignores format entirely).

## 9. Preview / Original independence & rerender

- Records are keyed by `asset_id` only; no Generation-level collapsed state exists in this service. Exporting Preview P leaves Original O `not_exported`; exporting O leaves P's state intact; deleting P's file classifies P `missing` while O remains `exported`.
- Rerender: new Original O2 (new `ast_*` id, even with identical bytes/sha) starts `not_exported`; O's record remains historical truth; no transfer by shared `logical_output_key`. Identical-content reuse applies only when the asset_id itself recurs (normal idempotency).

## 10. Failure atomicity

Ordering: resolve → sha256-validate → convert → atomic tmp+fsync+replace write → existence verify → persist `ExportRecord(exported)` LAST. Never persists `exported` before durable write. If record persistence fails after the write: result is `partial=True` / `record_persist_failed`, written image+sidecar are deleted (legacy `save_run_history_output` precedent) so retries cannot strand untracked duplicates; if cleanup itself fails the orphan path is reported in `orphan_path`. Managed asset is never modified/deleted by any path (asserted after success+failure mixes).

## 11. Metadata sidecar

When enabled: canonical `output_saver._build_metadata_sidecar` structure + merged History identity block (`history_v2`, `generation_id`, `run_id`/attempt, `asset_id`, `variant`, `logical_output_key`, `output_index`, `preset_id/preset_name`, `workflow_hash`, `seed`, `source_managed_path`, `exported_via`). Best-effort like legacy (failure degrades to empty `metadata_path`, never blocks the export). When disabled: no metadata dir content. No credentials anywhere (asserted).

## 12. Tests (deterministic, offline)

`tests/test_history_v2_export.py` — **33/33 OK** (~5 s):

1. local PNG export + record ✓ 2. local WebP conversion ✓ 3. remote `modal://` via fake resolver ✓ (+resolver-failure→failed, +missing-resolver→no-record) 4. hash mismatch (local corruption + remote wrong-bytes) ✓ 5. Preview/Original independent records + delete-P→missing/O-exported ✓ 6. duplicate idempotent reuse ✓ 7. deleted destination→missing(persisted)→re-export ✓ (+folder-change, +format-change explicit exports) 8. converter exception AND silent-fallback rejection ✓ 9. write failure ✓ 10. record-persist failure after write → partial + cleanup ✓ 11. real output index in filename (+bad-index validation) ✓ 12. traversal/hostile-name containment ✓ 13. sidecar on w/ identity ✓ 14. sidecar off ✓ 15. rerender successor not transferred ✓ 16. identical-content new asset not transferred ✓ 17. managed source unchanged ✓ 18. no legacy dependency (AST import allowlist + standalone import) ✓

Regression (all OK, no failures):
- `tests.test_run_history_save` + `tests.test_output_saver_paths` + `tests.test_output_contract` + `tests.test_history_v2_repository` + `tests.test_history_v2_api` → **76/76**
- Converter lanes `test_e2_preview_codec` + `test_e2d_preview_method_contract` + `test_e2_preview_effort` → **24/24**

Total this batch: **133 tests, 0 failures.**

## 13. Exact remaining integration work (later batch, after F5/F6 release their files)

1. **Route**: register e.g. `POST /comfymodal/history-v2/assets/{asset_id}/export` (or generation-scoped variant selector) in `history_v2_routes.py`; construct the service with `_open_repo()` and an async `byte_resolver` wrapping the existing `modal_client.read_output_asset(expected_sha256=…)` retry logic from the asset-serving handler; resolve `ExportOptions` from live `_load_modal_settings()`; map `ExportResult` to HTTP (200 ok/already_exported, 404 unknown asset, 502/500 failures).
2. **Frontend Export actions**: per-output/per-variant Export buttons in `web/studio-history-v2-detail.js` + experiment detail, consuming `already_exported` to suppress duplicates and surfacing `missing` for recovery.
3. **Projection**: replace the collapsed generation-level `export_state` ("exported" if any) with per-output/per-variant fields using `get_export_state()` lazy classification so `not_exported/exported/missing/failed` project truthfully.
4. **Gate registration**: add `tests.test_history_v2_export` to `STUDIO_PY_MODULES` in `tests/run_studio_tests.py` and run the authoritative wrapper once the shared tree is stable.

Deploy / live / GPU / commit / push: **NONE**.
