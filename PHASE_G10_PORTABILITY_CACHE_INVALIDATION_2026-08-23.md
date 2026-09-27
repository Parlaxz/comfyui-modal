# PHASE G10 — Derived Portability Report Cache & Invalidation (2026-08-23)

**Batch:** G10 · **Type:** pure implementation (derived-cache lane) · **Mode:** stdlib-only module + tests + this document. No route wiring, no G9 route/service changes, no Workflow import/export behavior change, no frontend, no History/Settings/Modal/runtime/GPU/performance changes, no runner registration, no deploy/live/generation, no commit/push/branch/worktree/reset.

**Files created by THIS lane (nothing else touched):**

| File | Status |
|---|---|
| `portability_cache.py` | NEW — derived report cache with frozen G5 invalidation |
| `tests/test_portability_cache.py` | NEW — 40 deterministic tests, standalone + pytest-discoverable |
| `PHASE_G10_PORTABILITY_CACHE_INVALIDATION_2026-08-23.md` | NEW — this document |

Untouched per ownership boundary: `studio_workflow_routes.py`, `studio_domain/services.py`, `portability_contract.py`, `portability_risk.py`, `portability_targets.py`, `studio_store.py`, `tests/run_studio_tests.py`, all `.studio_*.json` stores, G8 fixtures, History, Settings, Modal/runtime.

---

## 1. Verdict

**G10 PASS.** A small derived-only cache module now persists one validated portability report per immutable `workflow_version_id` in a dedicated sidecar, reuses the frozen G5 invalidation comparator verbatim (`portability_contract.invalidation_mismatches`), stales conservatively on every concrete field change AND on any null on either side (including null-vs-null), fails open on every corruption shape, writes atomically through the existing `StudioJsonStore` locking/tmp+replace machinery without modifying it, and exposes explicit `hit / miss / stale / invalid` states plus a list-card summary helper. The cache never gates execution or import and performs no recomputation. Regression: cache 40/40, contract 32/32, fixtures 35/35, risk engine 28/28, target rules 33/33.

## 2. Sidecar format

Canonical file: `.studio_portability_reports.json` (constant `DEFAULT_SIDECAR_FILENAME`), stored next to the other Studio stores by the caller. Layout:

```json
[
  {
    "cache_format_version": 1,
    "reports": {
      "<workflow_version_id>": {
        "report": { "...full contract-valid portability report..." },
        "stamp":  { "...exact frozen 8-field G5 invalidation stamp..." }
      }
    }
  }
]
```

- **Array-rooted with exactly one envelope object** — this adapts around the existing list-rooted `StudioJsonStore` reader WITHOUT changing it, inheriting its RLock thread safety, atomic tmp+`os.replace`+fsync writes, UTF-8 BOM tolerance, and missing-file→empty convention.
- `CACHE_FORMAT_VERSION = 1` is an INTERNAL sidecar-layout version. It is deliberately distinct from `manifest_version` and `rule_version`; unknown future values fail open to `invalid`.
- No fields were added to `.studio_workflows.json`, `.studio_workflow_versions.json`, `.studio_workflow_mappings.json`, or `.studio_workflow_presets.json`. History SQLite is not used.
- Cached rows hold only JSON-safe contract data (validated report + stamp copy). No random runtime objects are persisted.

## 3. Cache API

```python
PortabilityReportCache(path_or_store)   # path OR existing StudioJsonStore
get(version_id, current_stamp) -> CacheLookup    # state/report/mismatched_fields/reason; .hit/.stale properties
put(report) -> CachePutResult                    # ok/version_id/reasons (ALL rejection reasons)
remove(version_id) -> bool                       # drops one row; others untouched
clear()                                          # reset to empty v1 envelope (tests/maintenance)
inspect(version_id) -> dict                      # diagnostics without needing a current stamp
summaries(version_ids, current_stamps=None)      # list-card helper
```

Callers never infer state from `None`: every lookup carries an explicit `state` plus a human-readable `reason`. `last_diagnostics` records the most recent load/write diagnostics for logs/tests.

## 4. Hit / miss / stale / invalid semantics

- **hit** — row present, internally consistent (report validates; stamp has exactly the 8 frozen fields; row key == `report.version_id` == `stamp.workflow_version_id`; `report.graph_hash` == `stamp.graph_hash`) and `invalidation_mismatches(current_stamp, cached_stamp)` is empty. Returned view is a copy marked `stale=false`.
- **miss** — unknown version id, missing file, empty sidecar, or empty reports map. Reads NEVER create the sidecar file.
- **stale** — usable cached report but at least one stamp field differs or is unknowable. Returns a COPY of the old report explicitly marked `stale=true` plus `mismatched_fields` naming exactly which G5 fields fired — suitable for a future list chip that renders stale/unknown while recomputation happens.
- **invalid** — corrupt/incompatible content (see §7). The poisoned payload is never returned; diagnostics explain why.

## 5. Frozen invalidation & null rule

The stamp uses EXACTLY the G5 fields (`portability_contract.INVALIDATION_FIELDS`): `workflow_version_id, graph_hash, dependency_metadata_hash, model_library_generation, custom_node_registry_generation, rule_version, manifest_version, comfyui_version`. Comparison is delegated verbatim to `portability_contract.invalidation_mismatches` — no locally reimplemented comparator exists. Consequences enforced and tested:

- Every concrete single-field change stales (graph hash, dependency metadata hash, model library generation, custom-node registry generation, rule version, manifest version, ComfyUI version).
- Any null on EITHER side stales — including null compared with null. Null is never "probably unchanged".
- A completely unknowable current stamp (non-dict/None) stales on all eight fields.
- `analyzed_at` is NOT an invalidation criterion and there is NO TTL: a 2020-dated report with identical stamps hits; staleness is evidence/version based only.
- Rule-version and manifest-version bumps stale old reports; nothing auto-rewrites them to the new version.
- Generation values and `dependency_metadata_hash` are OPAQUE caller-supplied comparables; this module never inspects Model Library, custom-node registry, or WorkflowVersion stores to manufacture them. If a later backend cannot supply a value, null → stale by contract — invalidation is never weakened for hit rate.

## 6. PUT contract

`put(report)` writes NOTHING unless: the report is a dict passing `portability_contract.report_validation_issues`; `report.invalidation` is a complete 8-field stamp passing `invalidation_stamp_issues`; `stamp.workflow_version_id == report.version_id`; and `stamp.graph_hash == report.graph_hash`. Rejections return `CachePutResult(ok=False, reasons=(...))` carrying ALL violations and leave the sidecar uncreated/unchanged. Null stamp FIELD VALUES are accepted at put time (they simply can never produce a hit). Same-version puts atomically replace the previous complete row; different versions coexist.

## 7. Corruption behavior — FAIL OPEN

Derived-cache corruption never crashes the Workflows product and never yields an authoritative bad report:

| Shape | Result |
|---|---|
| malformed JSON | `invalid` + diagnostic (store error surfaced into reason, not raised) |
| wrong root type (object/string/etc.) | `invalid` |
| zero envelopes / empty array / missing file | `miss` |
| multiple envelopes | `invalid` (ambiguous) |
| unknown `cache_format_version` | `invalid` ("incompatible") |
| envelope without valid reports map | `invalid` |
| one malformed row | that row → `invalid`; other rows unaffected (never authoritative) |
| tampered/contract-invalid cached report | `invalid`; never returned as hit |
| row-key vs internal id/graph-hash disagreement | `invalid` |

Reads never repair or rewrite anything. Because the file is derived-only, WRITES may regenerate it from scratch when pre-existing content is unreadable/alien (diagnostic recorded); no source-of-truth store is ever touched or "partially repaired". Full regeneration is always acceptable.

## 8. Atomicity & thread safety

All mutations go through `StudioJsonStore.update()`/`write_atomic()`: write temp sibling → fsync → `os.replace`. Verified by test: with `os.replace` patched to raise, the put surfaces the error, the temp file is cleaned up, and the previous complete sidecar content remains intact and hittable. Single-process thread safety is the store's RLock; tested with 8 barrier-synchronized threads doing 48 distinct-version puts plus contended same-version puts and reads concurrently — final file parses, contains exactly the expected rows, and every row passes full validation. Cross-process guarantee (truthful): NO multiprocess transactional semantics are claimed; last COMPLETE atomic writer wins, and readers can never observe partial JSON because of tmp+replace. That is acceptable precisely because the cache is derived and regenerable. No global Studio-domain lock is taken.

## 9. Report immutability & stale views

Persisted reports are stored verbatim as computed. Lookup views are deep copies: a stale read flips `stale=true` ONLY on the returned copy — the persisted `risk_level`, `issues`, `analyzed_at`, `targets`, `environment`, and original `stale` flag are never mutated to pretend freshness (tested by tampering with the returned view and re-reading disk). Hit views are copies marked `stale=false`; stale views are copies marked `stale=true`, so stale results can never be presented as current.

## 10. Summary helper (list-card seam)

`summaries(version_ids, current_stamps=None)` returns one entry per requested id that has a USABLE cached row — `{version_id, risk_level, issue_count, analyzed_at, stale, freshness, mismatched_fields}` — omitting misses/unusable rows rather than fabricating entries. Freshness is explicit tri-state so a future UI can never silently render possibly-stale data as current: `verified`+`stale=false` (true hit against a supplied stamp), `verified`+`stale=true` (+ mismatched fields), or `unchecked`+`stale=None` when no current stamp was supplied. The cache does not scan Workflow stores; callers supply the ids they want.

## 11. Derived-only / no-gating invariant

The module's responsibility is storage/reuse only. There is deliberately NO `runnable`/`authorize`/`can_execute`/`can_import`-style API, no recomputation logic, and no import of G6/G7/G9 or domain run-state modules (imports pinned by test to exactly `portability_contract`, `studio_store`, `copy`, `dataclasses`). Route integration (later seam) decides when to recompute; the cache answers hit/miss/stale only. This avoids circular dependencies and keeps testing deterministic.

## 12. G8 invalidation fixture results

Consumed READ-ONLY via `tests/portability_fixtures.load_invalidation_stamps()` / `load_invalidation_semantics()` (fixtures unmodified):

- All 9 stamps carry exactly the 8 frozen fields and pass `invalidation_stamp_issues`.
- `stamp_a` vs `stamp_a2` → **hit** through the real cache round-trip.
- All six single-field variants (`graph_hash`, `model_library_generation`, `custom_node_registry_generation`, `rule_version`, `manifest_version`, `comfyui_version`) → **stale**, each mismatching EXACTLY its flipped field set from `semantics.expected.json`.
- `stamp_null_field` (null `dependency_metadata_hash`) → **stale both against itself (null-vs-null) and against concrete `stamp_a`**.
- Note: the G8 corpus defines no `dependency_metadata_hash_changed` variant; that case is covered by a locally derived stamp (fixture files untouched).

## 13. Test evidence (this batch)

- `python tests/test_portability_cache.py` → **40/40 passed** (pytest-discoverable; temp dirs only — no real `.studio_portability_reports.json` is ever written into the project, verified).
- Regression neighbors green: `test_portability_contract.py` 32/32 · `test_portability_fixtures.py` 35/35 · `test_portability_risk_engine.py` 28/28 · `test_portability_target_rules.py` 33/33.
- Coverage maps to all 33 mandated checks plus extras: empty-sidecar miss, unknown-future-format fail-open, row-key impersonation → invalid, stamp-less put rejection, inspect diagnostics, clear, and an all-fields-unknowable current-stamp case.

## 14. Explicit non-goals (this batch)

No route wiring (cache is NOT yet called by `studio_workflow_routes.py`/services); no automatic recompute; no TTL; no frontend code; no Model Library/Registry inspection; no History/Settings changes; no Modal/runtime/GPU/live generation; no deploy; no commit/push/branch/worktree/reset; no runner registration (belongs to the later reconciliation/integration step alongside G9).

## 15. Exact later integration seam

1. **G9 route/service shell** constructs the current 8-field stamp per request (supplying opaque `model_library_generation`, `custom_node_registry_generation`, `dependency_metadata_hash`, `comfyui_version`, `graph_hash`, `manifest_version`; nulls allowed but will conservative-stale), instantiates `PortabilityReportCache(<studio-dir>/.studio_portability_reports.json)`, calls `get(version_id, stamp)`:
   - `hit` → serve cached report view;
   - `stale` → optionally render the stale-marked view while recomputing via live G6/G7 analysis, then `put(fresh_report)`;
   - `miss`/`invalid` → recompute live (corruption must never block live analysis) and `put`.
2. **Workflows list endpoint** calls `summaries(ids, stamps_by_id)` for cheap chips; render `unchecked`/`stale` states distinctly — never as verified-current.
3. **Reconciliation batch** registers `tests/test_portability_cache.py` in `tests/run_studio_tests.py`.

*G10 complete. Deploy/live/GPU/generation/commit/push: NONE.*
