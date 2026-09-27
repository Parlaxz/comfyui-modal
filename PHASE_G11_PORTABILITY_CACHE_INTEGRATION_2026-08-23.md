# PHASE G11 — Portability Cache Integration, Workflow Summary Enrichment & Gate Reconciliation (2026-08-23)

**Batch:** G11 · **Type:** backend cache integration (implementation) · **Mode:** service/route wiring + stamp authorities + list-summary contract + runner registration + tests + this document. No frontend, no fake-backend/server changes, no deploy/live/GPU/generation, no commit/push/branch/worktree/reset.

**Files touched by THIS lane:**

| File | Status |
|---|---|
| `portability_service.py` | MODIFIED — cache injection seam, current-stamp construction, generation-token authorities, cached GET flow (fail-open), list/detail summary helper, analyzer DI seam |
| `studio_workflow_routes.py` | MODIFIED — portability GET now serves through the G10 cache; workflow list/detail rows carry `portability_summary`; route composition builds the canonical sidecar + generation authorities; optional `portability_service=` injection param |
| `tests/test_portability_cache_integration.py` | NEW — 33 deterministic integration tests (endpoint hit/miss/stale/invalid, per-field recompute, G8 fixture reconciliation through the route shell, fail-open, list tri-state summaries, import/export neutrality) |
| `tests/run_studio_tests.py` | MODIFIED — registered G6/G7/G8/G9/G10/G11 suites in the main Studio gate |
| `tests/test_portability_roundtrip.py` | MODIFIED — 2-line path bootstrap so the G9 suite loads both direct-run AND as `tests.test_portability_roundtrip` (latent issue surfaced by gate registration; no test semantics changed) |

Untouched per ownership boundary: `web/**`, fake backend/server (`fake-server.mjs`, `fake-backend.mjs`), browser specs, `portability_contract.py` (G5), `portability_risk.py` (G6), `portability_targets.py` (G7), G8 fixtures, `portability_cache.py` (G10 — consumed verbatim, zero modifications), manifest format, Workflow import/export semantics, Modal/runtime/GPU/performance, History, Settings.

---

## 1. Verdict

**G11 PASS.** The G9 portability GET now truthfully uses the G10 derived cache: a validated hit serves the cached report with **zero** resolver/G6/G7 work (proven by an injected analyzer spy), while miss/stale/invalid synchronously recompute live through the unchanged G9 pipeline and refresh the entry. All eight invalidation-stamp fields are concrete wherever authoritative evidence exists; any null conservatively stales and never produces a false hit. Cache corruption and put failures **fail open** to live analysis. Workflow lists gain a frozen derived-only `portability_summary` chip served from the cache with provably zero analysis. All landed Phase-G suites are now in the main Studio gate; the Python lane runs 1991 tests green.

## 2. Cache placement

* Canonical sidecar `.studio_portability_reports.json` (`DEFAULT_SIDECAR_FILENAME`) is created by `register_workflow_routes` under the SAME Studio local data root as the Workflow domain stores (`Path(node_dir) / DEFAULT_SIDECAR_FILENAME`). No second location; nothing is written into the plugin source tree by design (the file sits beside `.studio_workflows.json` etc., exactly as G10 §2 specifies).
* Composition: `PortabilityReportCache` is injected into `PortabilityService(cache=...)`. Route handlers stay thin HTTP translation; no cache algorithm lives in handlers.
* Two NEW keyword-only authority params (`model_library_generation_source`, `custom_node_registry_generation_source`) are deliberately SEPARATE from the existing `model_library` / `custom_node_registry` import-adaptation params, so wiring the cache is **cache-neutral**: Export/Import behavior is byte-identical to G9 (proven by sidecar-snapshot tests).
* An `analyzer` param provides the deterministic recompute-injection seam for tests (no production global counters anywhere).

## 3. Current invalidation-stamp construction (`PortabilityService.current_invalidation_stamp`)

Exact G5 field names via `pc.build_invalidation_stamp`; all eight concrete when evidence exists:

| Field | Authority |
|---|---|
| `workflow_version_id` | persisted immutable Version record (never browser input) |
| `graph_hash` | persisted Version `graph_hash` |
| `dependency_metadata_hash` | canonical SHA-256 of persisted `dependency_metadata` (`pc.sha256_of_canonical`: sorted keys, compact, NaN-forbidden); None only if metadata absent → conservative stale |
| `model_library_generation` | SHA-256 token over normalized portability-relevant Model Library records: model_id, folder, filename, hash, size, sorted source_urls, provider, revision, is_placeholder, derived install/presence status (`record_is_installed` guarded single-path checks). NO local_path, NO timestamps, NO bytes read, NO directory scans |
| `custom_node_registry_generation` | SHA-256 token over persisted registry rows: name, repo_url, installed_commit, declared_version/provenance fields, sorted classes. NO tree walks, NO git, NO mtimes |
| `rule_version` | `pc.PORTABILITY_RULE_VERSION` (landed constant) |
| `manifest_version` | `studio_workflow_manifest.MANIFEST_SCHEMA_VERSION` (landed constant, read at call time) |
| `comfyui_version` | cheapest existing runtime identity chain: `comfyui_version.__version__` → `comfy.__version__` (mirrors modal_app's established pattern; guarded imports; never `git rev-parse`, never remote inspection) |

No existing numeric generation/revision counter exists on either store (inspected first per spec §6A), so option B derivation was used. Any authority failure yields None → frozen comparator stales conservatively; null-vs-null NEVER hits (tested).

## 4. GET hit / miss / stale / invalid flow (`cached_portability_report`)

route → `cached_portability_report(version_id)`:

1. read persisted Version (404 if unknown — no cache touched);
2. build current stamp;
3. `cache.get(version_id, stamp)`:
   * **HIT** → return cached validated view (`stale=false`); ZERO recomputation — the resolver is not even consulted on this path;
   * **MISS / STALE / INVALID** → `_recompute_report`: live G9 pipeline (`portability_report(current_stamp=stamp)`, unchanged G6/G7 composition) or injected analyzer; the report is stamped with the CURRENT authoritative stamp (so `put()`'s version/graph-hash consistency holds) and `cache.put()` refreshes the entry; the FRESH report is returned — a stale LOW is never served as current;
4. response shape stays `{status, portability}` plus additive `portability_cache` metadata `{state, recomputed, mismatched_fields, diagnostics}`.

No force-refresh parameter was added (spec §14): identical evidence ⇒ deterministic hit; changed evidence ⇒ automatic stale.

## 5. Fail-open behavior (spec §11/§26)

`cache.get` and `cache.put` are individually guarded: any unexpected exception is logged boundedly, recorded into `portability_cache.diagnostics`, and the live pipeline proceeds. Proven by tests: malformed JSON sidecar → 200 + valid fresh report (`state:"invalid"`) → sidecar regenerated from scratch by the next put → second GET hits; hard-crashing `put` → 200 + valid live report; put REJECTION (graph-hash disagreement) → 200 + live report, nothing written. Domain stores are byte-identical throughout. A corrupt sidecar can never turn a valid Workflow into a 500.

## 6. Analysis failure discipline (spec §12)

Recompute always runs the real G9 pipeline; contract-valid UNKNOWN reports validate and cache normally (tested end-to-end). Unexpected exceptions follow existing G9 error semantics (404/400/500 mapping). Old cache entries are never masked over current failures because every non-hit state forces synchronous recompute before responding.

## 7. List summary contract (frozen, spec §15)

Each Workflow list row (and the Workflow detail payload — same helper, same schema) carries:

```json
"portability_summary": {"version_id": "wv_...", "risk_level": "low|medium|high|unknown",
                        "issue_count": <int>, "stale": true|false|null, "analyzed_at": "<iso|null>"}
```

or `null` when no usable cached row exists for the Workflow's latest Version. Tri-state enforced: `false` = verified against a cheaply constructed current stamp; `true` = checked and outdated (marker never dropped); `null` = freshness unknowable (dangling latest pointer with a cached row → unchecked, never pretended false/current). No target matrix or issue bodies on list rows. Implementation (`workflow_portability_summaries`) reads latest versions via one store pass and calls `cache.summaries(...)` — it CANNOT analyze (no resolver call, no G6/G7, no writes; whole helper additionally fails open to all-null).

## 8. No-analysis list proof

`test_23_list_performs_zero_analysis_and_zero_cache_writes`: after list render — analyzer spy call count == 0, instrumented resolver `resolve_version` count == 0, sidecar bytes unchanged. Five-workflow independence test covers current-LOW / current-HIGH / stale-MEDIUM / never-analyzed(null) / unchecked(stale=null) with distinct version ids and no cross-reuse; same-graph-hash/different-version-id is never reused (summary null until its own explicit GET).

## 9. Import/Export neutrality (spec §21/§22)

Export and dry-run Import leave the sidecar byte-identical. Committed Import performs no eager cache fill and no forced analysis (spy count unchanged): the new Version starts summary-null, and its first explicit portability GET computes+caches (miss → fresh). New Versions naturally get new cache keys; equal graph hashes never transfer reports across versions.

## 10. Runner registration (spec §27)

`tests/run_studio_tests.py`:

* `STUDIO_PY_MODULES` += `tests.test_portability_risk_engine`, `tests.test_portability_backend`, `tests.test_portability_roundtrip`, `tests.test_portability_cache_integration` (unittest class-based suites).
* `PYTEST_STYLE_FILES` += `tests/test_portability_target_rules.py`, `tests/test_portability_fixtures.py`, `tests/test_portability_cache.py` (module-level test functions; wrapped as FunctionTestCases).
* No file is listed twice; each suite retains standalone execution (`python tests/<file>.py`).

## 11. Focused regression counts (this tree)

| Suite | Result |
|---|---|
| G5 contract (`test_portability_contract.py`) | **32/32 passed** |
| G6 risk engine (`test_portability_risk_engine.py`) | **28/28 passed** |
| G7 target rules (`test_portability_target_rules.py`) | **33/33 passed** |
| G8 fixtures (`test_portability_fixtures.py`) | **35/35 passed** |
| G9 backend (`test_portability_backend.py`) | **45/45 passed** |
| G9 roundtrip (`test_portability_roundtrip.py`) | **4/4 passed** (both invocation modes) |
| G10 cache (`test_portability_cache.py`) | **40/40 passed** |
| G11 integration (`test_portability_cache_integration.py`, NEW) | **33/33 passed** |
| Manifest codec (`test_studio_workflow_manifest.py`) | **21/21 passed** |
| Workflow domain (`tests.test_workflow_domain`) | **39/39 passed** |
| Workflow routes (`tests.test_workflow_routes`) | **19/19 passed** |
| DependencyResolver (`tests.test_dependency_resolver`) | **11/11 passed** |
| Model library routes (`tests.test_model_library_routes`) | **11/11 passed** |
| Route registry (`tests.test_routes_registered`) | **298/298 passed** |

## 12. Full Studio gate counts/status

`python tests/run_studio_tests.py` (Python + Node lanes): **python run=1991 fail=0 error=0 skip=0 · node-unit 21/21 PASS — ALL STUDIO LANES GREEN.**

`--fake` lane: **185/190 fake Playwright passed; 5 failed — ALL in `tests/browser/fake/studio-fake-workflow-portability.spec.mjs`**, which is parallel-lane G12's actively-in-flight, currently-untracked file (alongside untracked `web/studio-portability.js`, `web/studio-portability-checklist.js` and multiple modified `web/*.js`). Ownership truth: THIS lane modified zero `web/**`, zero fake-backend/server, zero browser-spec files; the fake Playwright lane runs against the JS fake server, so these failures cannot originate from Python-side changes. Rerun after the shared tree stabilizes is required for final convergence (all-Python/all-Node/all-fake GREEN).

## 13. Exact remaining frontend work (G12's lane)

* Converge the 5 red specs in `studio-fake-workflow-portability.spec.mjs` (G12-owned; backend response shapes they consume are stable: `{status, portability, portability_cache}` and the frozen five-key `portability_summary`).
* Render list/detail chips from `portability_summary`: null → "Not analyzed" (never LOW), `stale:true` → "Stale — recheck portability", `stale:null` → unchecked, `stale:false` → current risk/count.
* Portability panel consumption of the detail endpoint incl. the additive `portability_cache` metadata if desired.

Deploy/live/GPU/generation/commit/push: **NONE**.

*G11 complete.*
