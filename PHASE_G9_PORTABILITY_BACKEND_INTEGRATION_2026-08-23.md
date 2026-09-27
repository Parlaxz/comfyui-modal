# PHASE G9 — Portability Backend Integration (2026-08-23)

**Batch:** G9 · **Type:** production backend implementation · **Mode:** service + route wiring + tests + this document. No frontend, no portability-report cache, no deploy/live/GPU/generation, no provider calls, no commit/push/branch/worktree/reset.

**Files touched by THIS lane:**

| File | Status |
|---|---|
| `portability_service.py` | NEW — composition layer: Export / Import preview+commit / live report |
| `portability_evidence.py` | NEW — narrow evidence adapter (aux_id, provenance, manifest records, env facts, target-evidence assembly, artifact credential scan) |
| `studio_domain/store.py` | MODIFIED — `commit_import_transaction()` atomic multi-collection import (+ `_compensate_import`) |
| `studio_workflow_routes.py` | MODIFIED — three frozen endpoints wired; handlers stay thin HTTP translation |
| `tests/test_portability_backend.py` | NEW — 45 deterministic tests |
| `tests/test_portability_roundtrip.py` | NEW — 4 exact-round-trip integration proofs |

Untouched per ownership boundary: `portability_contract.py`, `portability_risk.py`, `portability_targets.py`, `studio_workflow_manifest.py`, `workflow_metadata.py` (`_MODEL_REF_MAPPINGS`), `dependency_resolver.py`, `model_library.py`, `custom_node_registry.py`, `studio_domain/services.py`, History V2, Settings, all G10 cache files (`portability_cache.py`, `tests/test_portability_cache.py`), all frontend files, `tests/run_studio_tests.py` (its working-tree diff is pre-existing from earlier phases; no G9 registration added).

---

## 1. Verdict

**G9 PASS.** The existing Studio Workflow Manifest v1 is now wired end-to-end without a parallel format: read-only exact-JSON Export, dry-run-first Import with a hard atomic commit, and a LIVE WorkflowVersion portability report that genuinely consumes the G6 risk engine and the G7 six-target rules over adapted local evidence. Dry run writes nothing (byte-proven); committed imports are all-or-nothing across all four domain collections under injected failure at every stage; foreign ids never become local authority; missing dependencies import but stay gated by the unchanged `derive_version_state`; credential-shaped exportable values fail Export closed with zero mutation.

## 2. Endpoint contracts implemented

* `GET /comfymodal/studio/workflows/versions/{version_id}/export` — query `include_presets=0|1`, default **false**. Returns canonical manifest-v1 bytes (`application/json`) with `Content-Disposition: attachment; filename="<sanitized>-v<n>-<hash8>.workflow.json"` via the frozen `suggest_export_filename` sanitizer (header value re-sanitized defensively). Read-only proven by byte-level store snapshots before/after.
* `POST /comfymodal/studio/workflows/import-manifest` — body IS the manifest JSON; query `dry_run=1|0`, default **true**. Commit additionally reads the two frozen body policy fields `import_presets` / `apply_default_preset` (both default false); because manifest root sections are closed, the route strips exactly these two keys from the parsed object before manifest validation. Statuses: 200 preview (`status:"preview"`, valid manifests incl. dependency-incomplete ones), 200 commit (`status:"ok"`), 400 malformed/invalid/unsupported-version/hash-mismatch/non-finite/depth-element violations (all issues collected where available), 413 >10 MiB (content-length pre-check AND post-read check), 404 n/a, 500 true internal only.
* `GET /comfymodal/studio/workflows/versions/{version_id}/portability` — LIVE G5 report, computed from current truth; **no cache read, no cache write** (G10 inserts underneath transparently later). 404 unknown version. No second "compatibility" endpoint exists (asserted by test).

## 3. Manifest construction & exact-JSON preservation

Export builds exclusively through `studio_workflow_manifest.build_manifest`. Because the manifest codec hashes `workflow.graph`, and the domain identity rule (G1, unchanged) is the canonical hash of the **executable prompt**, the export embeds:

* `workflow.graph` = persisted executable prompt (`extract_executable_prompt(api_prompt_json)` projection — never a recapture) with `graph_hash` = the Version's stored hash, so manifest integrity *verifies the domain identity rule*;
* `version.graph_json` and `version.api_prompt_json` verbatim as section-level payload (unknown keys inside sections are preserved data per the frozen format) — this is what makes the round trip byte-exact;
* `mapping` role-keyed entries from the stored immutable Mapping; optional `presets[]` (raw records + derived `is_default` from the Workflow pointer); `models[]` / `custom_nodes[]` reference records; `assets[]` reference metadata; free-form `metadata` carrying `exported_at`/`exporter`/deterministic `export_warnings`.

No normalization, ID regeneration, node stripping, path rewriting, default insertion, or UI-field mutation touches embedded graph/API objects. An unmapped version or a stored-hash/recompute mismatch fails Export closed (409 `export_integrity_failure` / `graph_hash_mismatch`).

## 4. Evidence adapter & provenance confidence

`portability_evidence.py` adapts authorities into engine evidence without modifying them: DependencyResolver rows (models/custom nodes), Model Library lookups, Custom Node Registry lookups, UI-graph `properties.aux_id`. Provenance uses the frozen vocabulary conservatively: explicit row quality → resolver-state derivation (installed+commit→**declared**, installed w/o commit→**inferred**, wrong_revision→declared, missing+repo→declared, else **unresolved**) → aux_id rescue (**declared**, repo `https://github.com/<slug>`, revision unknown). A non-empty registry `repo_url` alone is never exact; host-fallback ComfyUI URLs are replaced by aux_id-derived repos when available (tested) and nothing current derives `exact` without an enforced pin.

## 5. Model extraction gap — decision

**No `_MODEL_REF_MAPPINGS` change.** The exact input contract of `ModelPatchLoader` was not provable from repository source within this lane's certainty bar ("if uncertain: do not"), so the gap is represented honestly everywhere: excluded from exported `models[]` (no fake checkpoint role/folder), surfaced as a deterministic `metadata.export_warnings` entry on Export, and emitted as `model_extraction_gap` signal + issue by G6 in every report path.

## 6. Asset references

LoadImage/Mask/Video/Audio/VHS_Load inputs export basename+role reference records only (suffix qualifiers `[input]/[output]/[temp]` stripped); bytes are never read, sha256/size/mime omitted when unknown; undecodable values fall back to the `required_input_asset` finding. Export never becomes a bundler.

## 7. Credential policy

Fail-closed Export: after the manifest is built, an artifact-wide scan (`detect_manifest_credential_shapes`: executable inputs, api_prompt sub-objects, UI-graph widget input names, Note nodes skipped) refuses the download with 409 `credential_like_value_detected` — zero mutation, values never echoed. Import reports the same finding deterministically in the preview (`issues[]` string + `security_findings[]`, key names only) and does not block, matching the frozen G5 contract (finding, not blocker). No scrub-by-mutation exists anywhere.

## 8. Live risk + target pipelines

Live report: load authoritative Version/Workflow/Mapping → resolver rows → aux_id/provenance adaptation → G6 `analyze_workflow_version` → G7 `build_target_evidence` + `evaluate_target_readiness` → composer merge (global pool = workflow issues ∪ target-only mints deduped by code with workflow objects as the single rendering authority; summary risk stays workflow-derived) → G6 environment section → invalidation stamp (`dependency_metadata_hash` computed cheaply; `comfyui_version` via guarded import; generations null) → `assemble_report` (contract-validated). Dynamic provider facts (catalogs, RunComfy native capability, Baseten storage) have no local authority and stay UNKNOWN so G7 emits `target_capability_unknown` instead of guessing.

## 9. Environment-evidence limitations

Only two dimensions are derivable cheaply and truthfully at request time (model-hash coverage and custom-node commit coverage from the version's own dependency evidence). Torch pins, plugin-worktree cleanliness, core-patch divergence, and base-image digests would require git subprocesses/heavy imports and remain UNKNOWN (never guessed) — the live environment section is intentionally less complete than the one-time G2 forensic audit and never forces workflow/target risk.

## 10. Import atomicity mechanism

`WorkflowDomainStore.commit_import_transaction(workflow, version, mapping, presets)` — option C (explicit compensation) hardened with staged pre-validation, chosen for the narrowest coherent diff over the existing per-store atomic writes:

1. one exclusive in-process import lock serializes concurrent imports;
2. uniqueness checks run up-front AND inside each per-store mutator (race-free at write time under each store's own lock);
3. appends apply versions → mappings → presets → workflows, with the Workflow row LAST as the commit point;
4. any exception triggers `_compensate_import`, removing exactly the ids this transaction added (newest-first, each removal an atomic id-keyed update), restoring byte-identical collections.

Default-preset application happens during staging (`default_preset_id` set on the staged Workflow record) so it is covered by the same transaction — no post-commit write exists. Injected failures at all eight mandated points leave all four collections byte-equal to their pre-import state (tests 22a–22h).

## 11. Round-trip results

`tests/test_portability_roundtrip.py::test_full_round_trip_is_exact`: Export → dry-run (zero writes) → atomic commit → Export again proves canonical `graph_json` equality, canonical `api_prompt_json` equality, executable-prompt equality, equal `graph_hash`, Mapping semantic equality under reminted ids, Preset semantic equality (incl. single default) under reminted ids, and full canonical equality of the normalized manifests with `manifest_hash(include_metadata=False)` stable — allowed deltas limited to reminted local ids, timestamps, and the deterministic `" (imported)"` name suffix. Double import creates two independent complete workflows with disjoint identities.

## 12. Focused regression counts (this tree)

| Suite | Result |
|---|---|
| `tests/test_portability_backend.py` (NEW) | **45/45 passed** |
| `tests/test_portability_roundtrip.py` (NEW) | **4/4 passed** |
| G5 contract (`test_portability_contract.py`) | **32/32 passed** |
| G6 risk engine (`test_portability_risk_engine.py`) | **28/28 passed** |
| G7 target rules (`test_portability_target_rules.py`) | **33/33 passed** |
| G8 fixtures (`test_portability_fixtures.py`) | **35/35 passed** |
| Manifest codec (`test_studio_workflow_manifest.py`) | **21/21 passed** |
| Workflow domain (`tests.test_workflow_domain`) | **39/39 passed** |
| Workflow routes (`tests.test_workflow_routes`) | **19/19 passed** |
| DependencyResolver (`tests.test_dependency_resolver`) | **11/11 passed** |
| Model library routes (`tests.test_model_library_routes`) | **11/11 passed** |
| Route registry (`tests.test_routes_registered`) | **61/61 passed** |

New G9 suites are direct-run only; no `run_studio_tests.py` registration while G10 is concurrent (reconcile after both lanes land). Additionally, all 17 valid G8 fixture manifests were smoke-run through `preview_import` against an empty store: none crash; readiness/risk degrade truthfully (foreign manifests embed UI graphs and unsourceable deps → honest HIGH/missing findings).

## 13. Current-corpus reconciliation

Through the PRODUCTION pipeline (persisted corpus-shaped version + prepared resolver rows mirroring the G8 fixture): workflow portability = **medium** with exactly the expected issue-code set `{custom_node_unpinned, model_hash_unpinned, model_extraction_gap, subgraph_frontend_requirement}` while the environment section independently resolves **high** (`custom_node_source_unpinned`, `model_hash_unpinned`) — coexistence preserved, no cross-contamination (G5 §2 resolution reproduced end-to-end).

## 14. Remaining work (other lanes only)

* **G10**: persistent derived report cache behind the same service seam (invalidation stamps already flow through `assemble_report`; live endpoint stays the stable product contract).
* **Frontend**: chips/import-dialog/checklist against these response shapes (no `web/` file touched here).
* Runner registration reconciliation for G6/G7/G8/G9/G10 test modules once both concurrent lanes complete.

Deploy/live/GPU/generation/commit/push: **NONE**.

*G9 complete.*
