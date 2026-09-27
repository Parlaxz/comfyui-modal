# PHASE G5 — Portability Contract Freeze (2026-08-23)

**Batch:** G5 · **Type:** small contract implementation/freeze · **Mode:** pure contract module + tests + this document. No risk engine, no target rules, no routes, no cache, no frontend, no dependency installs, no Modal/runtime/performance changes, no deploy/live/GPU, no commit/push/branch/reset.

**Deliverables by THIS lane:**

| File | Status |
|---|---|
| `portability_contract.py` | NEW — single machine-readable contract module (pure, stdlib-only) |
| `tests/test_portability_contract.py` | NEW — 32 deterministic contract tests |
| `PHASE_G5_PORTABILITY_CONTRACT_FREEZE_2026-08-23.md` | NEW — this document (authoritative for all later G lanes) |
| `tests/run_studio_tests.py` | MODIFIED — one allowlist registration line only |

---

## 1. Verdict

**G5 PASS.** One pure contract module now freezes: three distinct risk dimensions, four-state risk vocabulary, six target ids, issue/report/target-result/environment/invalidation/checklist schemas, export/import endpoint contracts with explicit defaults, security limits, and reconciled policies. The existing manifest v1 remains the sole export artifact authority. Later lanes (risk engine, target rules, backend wiring, report cache, frontend) can be implemented independently against `portability_contract.py` + this document.

## 2. Reconciliation of G1/G2/G3/G4 — and the MEDIUM-vs-HIGH resolution

G1 classified the real WorkflowVersion approximately **MEDIUM** portability risk (many custom nodes across ≥10 repos, partially unreliable registry revision evidence, model hashes absent, ModelPatchLoader extraction gap, subgraph definitions). G2 classified the **current source execution environment HIGH** reproducibility debt (floating torch trio, working-tree plugin deployment, uncommitted local ComfyUI patch, missing model hashes, floating node provenance).

**Frozen resolution: both are simultaneously true because they are different dimensions.**

1. **WORKFLOW PORTABILITY RISK** — "How risky is this immutable WorkflowVersion to move/reproduce elsewhere?" Derived from graph structure, node identities, model references/hashes, assets, paths/endpoints, dependency-resolution evidence, and target rules. This is where G1's MEDIUM lives.
2. **TARGET READINESS** — per-target LOW/MEDIUM/HIGH/UNKNOWN for exactly six targets, each with its own issues/advice.
3. **ENVIRONMENT REPRODUCIBILITY** — "How exactly reproducible is the CURRENT source execution environment itself?" This is where G2's HIGH lives, in a separate report section (`environment`), sourced from `current_studio_environment`.

A core-only workflow may be LOW portability risk while the Studio deployment environment carries HIGH reproducibility debt. The environment section NEVER forces the workflow's or any target's risk level (`POLICY_ENVIRONMENT_ISOLATION = "environment_reproducibility_never_forces_workflow_or_target_risk"`). G2 findings are representable verbatim via frozen environment codes: `torch_stack_unpinned`, `custom_node_source_unpinned`, `plugin_worktree_dirty`, `local_core_patch_divergence`, `model_hash_unpinned`, `base_image_digest_unpinned`. (Positive facts such as "ComfyUI core pinned" are absence-of-issue, not codes.)

Other reconciliations:

- **G4 wire example used uppercase `"MEDIUM"`; frozen wire values are lowercase** (`"medium"`), matching house style (`DependencyResolver` states, `VersionState.status`). UI may render uppercase labels later.
- **G4 §11.4 suggested manual JSON cleanup after failed imports; superseded.** Import atomicity is now a hard backend requirement (§9).
- **G1 S1–S12 numeric labels remain audit shorthand only**; the public wire uses de-numbered signal names (`has_absolute_path`, …, plus count form `unresolved_node_count`).
- **G3's UNKNOWN provider facts stay UNKNOWN**: rules must never pretend unknowns are supported (`target_capability_unknown`).
- The audits themselves are historical evidence and were NOT edited.

## 3. Manifest authority (unchanged)

The canonical v1 artifact is the EXISTING `studio_workflow_manifest.py` single-JSON manifest documented in `WORKFLOW_MANIFEST_FORMAT.md`. No second format, no ZIP, no `manifest_version` change (still `(1,)`). The manifest represents workflow metadata, version graph/API capture, mapping, optional presets, model/custom-node/asset reference records, and metadata/provenance. Dependencies are references only — no model bytes, no custom-node code, no credentials. Export is read-only; import creates NEW Workflow + Version #1 + Mapping + optional presets; ExecutionPlan is never exported as portability authority; no PortableWorkflow entity, no second graph store, no portability column as graph authority.

`check_readiness()` remains structural manifest readiness. Frozen distinction (all five separately named in code as `PORTABILITY_CONCEPTS`):

```
manifest_readiness ≠ dependency_availability ≠ workflow_portability_risk
                   ≠ target_readiness ≠ environment_reproducibility
```

## 4. Risk vocabularies

### 4.1 Levels (`PortabilityRiskLevel`, wire = lowercase)

`low | medium | high | unknown` — used by summary risk AND every target result AND the environment section.

Severity philosophy (frozen principles; exact emission belongs to the risk-engine lane):

- **LOW** — no blocking/unresolved findings; structurally portable; dependencies resolved with sufficient identity evidence; no required environment-bound inputs.
- **MEDIUM** — portable with explicit setup/attention: known-but-unpinned dependencies, model refs without byte hashes, separately transported assets, resolvable mismatches, soft structural concerns.
- **HIGH** — likely/non-negotiable portability blocker: unresolved required node identity, host-bound path required by the graph, unavailable dependency/source, manifest readiness failure, or a target explicitly cannot satisfy a requirement.
- **UNKNOWN** — analyzer cannot make a defensible determination: unreadable evidence store, essential analysis unavailable, or target capability itself unknown and decision-relevant.

### 4.2 Issue severity

`high | medium | low` ONLY. There is NO unknown severity; report-level inability to judge is expressed as an UNKNOWN verdict plus an explanatory issue/reason.

### 4.3 Summary-risk policy notes (reconciled)

- **Subgraphs** (`definitions.subgraphs`, frontend ≥1.44): presence is a finding/signal (`uses_subgraphs`, code `subgraph_frontend_requirement`) but NOT a universal HIGH. Policy `POLICY_SUBGRAPHS = "target_sensitive_not_global_blocker"`. With frontend 1.44.19 guaranteed (current pin), Local/Modal may remain low-impact; targets that cannot support subgraphs raise severity in their own rules.
- **Absolute paths**: always produce a workflow-level finding (`local_path_reference`); Local may deem a self-consistent host path operationally usable while other targets become HIGH via severity override. Policy `POLICY_ABSOLUTE_PATHS = "global_finding_with_target_severity_override"`. The summary algorithm is explicitly source-environment-oriented; it must not force summary HIGH solely due to absolute paths when Local remains usable — the per-target results carry the cross-target severity.

## 5. Target ids (sole vocabulary)

```
local · modal · runpod · runcomfy · comfy_cloud · baseten
```

Banned in wire payloads (audit shorthand only): `comfy-cloud`, `comfycloud`, `run_comfy`. Frozen broad semantics from G3 (rules implement later):

| Target | Broad meaning |
|---|---|
| `local` | native/reference environment |
| `modal` | native product target; broad dependency control |
| `runpod` | same JSON broadly usable; custom Docker/image setup often required; model mount/path profile required |
| `runcomfy` | strong managed import/auto-setup story; exact commit/native dependency controls partly UNKNOWN |
| `comfy_cloud` | import broadly compatible; execution restricted to curated node/model environment; no arbitrary package/native install |
| `baseten` | capable custom environment; workflow typically embedded into a deployment rather than arbitrary graph-per-request |

Unknown provider facts remain UNKNOWN (`target_capability_unknown`), never fabricated support.

## 6. Issue contract

Canonical shape (exact keys after normalization):

```json
{
  "code": "<stable_machine_code>",
  "severity": "high|medium|low",
  "message": "<deterministic human-readable sentence>",
  "subject": "<stable subject>",
  "fix_hint": "<deterministic recommendation or empty>",
  "evidence": { "...optional bounded structured facts..." }
}
```

- `code`: non-empty snake_case (`[a-z0-9]+(_[a-z0-9]+)*`).
- `subject`: frozen vocabulary — `graph, custom_nodes, models, assets, paths, endpoints, frontend, environment, manifest, target`.
- `fix_hint`: string, defaults `""`.
- `evidence`: OPTIONAL (v1 includes it) structured dict, admitted only when it materially aids explainability/debugging; bounded at ≤2048 canonical bytes; finite JSON only. NEVER raw secrets, arbitrary file contents, huge graph fragments, or stack traces.
- Deterministic ordering: **severity descending → code → subject** (single canonical ranking high=3 > medium=2 > low=1). Duplicate codes within one report are rejected.

Foundational codes frozen (used by next lanes; renaming requires documenting aliases):

`credential_like_value_detected, local_path_reference, unresolved_node_type, custom_node_unpinned, model_hash_unpinned, model_extraction_gap, required_input_asset, external_endpoint_reference, subgraph_frontend_requirement, manifest_not_ready, dependency_missing, dependency_wrong_revision, target_capability_unknown`

**Model extraction gap**: `model_extraction_gap` + signal `model_extraction_gap` freeze the concept "workflow contains model-like loader inputs not covered by known model extraction mappings" so the risk lane can surface the ModelPatchLoader-class blind spot before any extraction fix lands. No extraction fix in G5.

**Provenance quality** (models/custom-node dependency evidence; replaces pretending repo_url/revision are always trusted): `exact | declared | inferred | unresolved`. Discovery fixes are out of scope.

## 7. Report / target / environment schemas

### 7.1 Summary report (v1)

```json
{
  "version_id": "wv_...",
  "graph_hash": "<64hex>",
  "risk_level": "medium",
  "rule_version": "portability-rules-v1",
  "issue_count": 3,
  "counts": { "high": 0, "medium": 2, "low": 1 },
  "issues": [ ...canonical issue objects... ],
  "signals": { "has_absolute_path": false, "unresolved_node_count": 3 },
  "targets": { "local": {...}, "modal": {...}, "runpod": {...},
               "runcomfy": {...}, "comfy_cloud": {...}, "baseten": {...} },
  "environment": { "risk_level": "high", "issues": [...],
                   "source": "current_studio_environment" },
  "stale": false,
  "invalidation": { ...8-field stamp... },
  "analyzed_at": "<iso>"
}
```

Validator-enforced invariants: exact field set presence; lowercase risk levels; `rule_version == "portability-rules-v1"`; counts keyed exactly `{high, medium, low}` AND equal to the actual severity tally AND `issue_count == len(issues)`; signals restricted to the frozen name/type table (booleans vs non-negative-int counts; unknown names rejected — new signals require a rule-version bump); targets keyed exactly by the six ids; every `targets.*.issue_codes` entry must exist in global `issues[]`; `stale` bool; invalidation shape valid; `analyzed_at` non-empty ISO string.

### 7.2 Target result (chosen reference-by-code model)

```json
{ "risk_level": "...", "issue_codes": ["dependency_missing"], "advice": ["..."] }
```

ONE rendering authority: ALL issue objects live in top-level `issues[]`; targets reference them by code. Target-only issues are full objects in the SAME global list, referenced from the owning target — duplication of issue objects six times is forbidden. No provider SDK data at runtime.

### 7.3 Environment reproducibility section

```json
"environment": {
  "risk_level": "high",
  "issues": [ /* canonical issues, subjects typically "environment" */ ],
  "source": "current_studio_environment"
}
```

Distinct from summary risk and target readiness by construction and validated independently. G2-style findings map to the frozen environment codes (§2).

## 8. Endpoint contracts

### 8.1 Export (read-only)

- `GET /comfymodal/studio/workflows/versions/{version_id}/export`
- Query `include_presets=0|1`; **default false** (never silently export mutable Workflow Presets).
- Response: manifest v1 JSON, appropriate content type, deterministic suggested filename metadata/header if project conventions support it.
- Filename: `<sanitized-name>-v<version_number>-<graph_hash[:8]>.workflow.json` (helper `suggest_export_filename`; sanitizer mirrors `web/history-v2-browser-download.js::sanitizeFilenamePart`; fallback part `workflow`).
- No graph/version/mapping/preset mutation; no installer action.

### 8.2 Import (distinct from raw-capture `/workflows/import`)

- `POST /comfymodal/studio/workflows/import-manifest`
- Body: the manifest JSON itself (no envelope unless absolutely necessary later).
- Query `dry_run=1|0`; **default dry_run=1**. Dry run MUST: parse; collect ALL validation issues (never fail on first); verify manifest hash/graph hash; run structural readiness; run dependency/portability analysis when available; detect duplicate names; write NOTHING.
- Commit requires explicit `dry_run=0` plus explicit preset decisions via body fields `import_presets` (default false) and `apply_default_preset` (default false). A source-marked default preset is NEVER auto-installed.
- Preview response (minimum): `{status:"preview", valid, manifest_version, issues[], readiness, portability|null, existing_name_matches[], proposed_name, will_create:{workflow,version,mapping,preset_count}}`.
- Commit response: new LOCAL ids — `workflow_id`, `workflow_version_id`, `mapping_id`, created preset ids, imported provenance summary, dependency/portability summary. Package `wf_/wv_/wm_/wpres_` ids are provenance only; local version numbering starts at 1; duplicate names allowed; suggested display name `<name> (imported)`; missing deps do not block import; malformed manifest DOES block; unsupported future manifest_version DOES block; unknown node/model imports but stays unrunnable per live VersionState.

## 9. Import atomicity requirement (backend lane, not implemented here)

G4 identified the rollback gap (no Workflow delete route). A FAILED COMMITTED import must not leave a partially-created Workflow graph in normal product state. The manifest-wiring lane must solve this via (A) transactional/staged domain-store write semantics or (B) explicit internal rollback cleanup in the import service. "Partial additive records are okay; user can edit JSON manually" is NOT acceptable. Recorded as a hard requirement for the backend lane; nothing implemented in G5.

## 10. Security contract (route layer enforces; limits frozen)

Max request body 10 MiB (`MAX_IMPORT_BODY_BYTES`, unless a stricter common app cap exists); JSON depth/element sanity limits before parse (`MAX_JSON_DEPTH=64`, `MAX_JSON_ELEMENTS=200000`); NaN/Infinity rejected; no archive extraction (single-JSON artifact); manifest filenames are data, never joined to filesystem paths during import; repo/model URLs are inert data, never auto-fetched; zero install operations; zero shell execution; credential-shaped embedded values generate a deterministic finding (`credential_like_value_detected`); exporter must not leak known secrets or local install paths (never export `.studio_model_library.json` `local_path` / `.studio_custom_nodes.json` `install_path`). Scrub logic itself is NOT implemented in G5.

## 11. Invalidation contract (cache NOT built)

Stamp fields (exact): `workflow_version_id, graph_hash, dependency_metadata_hash, model_library_generation, custom_node_registry_generation, rule_version, manifest_version, comfyui_version`. Unavailable fields may be null today.

**Stale comparison semantics (frozen):** a cached report may be reused only when EVERY field is concrete (non-null) on both sides and equal. Any concrete mismatch → stale. Any null on either side → unknowable → conservative recompute (null is NEVER "unchanged forever"). Helpers: `build_invalidation_stamp`, `invalidation_mismatches`, `invalidation_stamps_match`. The future cache stays derived-only and never gates execution.

## 12. Checklist contract (derived model, not generated yet)

Pure derived-from-report model with frozen fields: `summary_risk_level, issue_counts, issue_rows, dependency_table, target_matrix, import_expectations, provenance, rule_version, analyzed_at`. Checklist is derived advice; the manifest remains authority.

## 13. Determinism rule

Same immutable WorkflowVersion bytes + dependency evidence inputs + target-rule version + invalidation stamps ⇒ structurally identical report except `analyzed_at`. No random IDs in findings; canonical serialization follows project convention (sorted keys, compact separators, `ensure_ascii=False`, `allow_nan=False`).

## 14. Explicit non-goals (this batch)

No risk engine computation; no target rules; no HTTP route wiring; no report cache; no frontend UX; no dependency installs; no Modal/runtime/performance changes; no G2 environment fixes; no ModelPatchLoader fix; no deploy/live/GPU; no commit/push/branch/worktree/reset; no audit-document rewrites.

## 15. Exact next-lane interfaces

| Lane | Consumes from this contract |
|---|---|
| Risk engine (pure) | `RISK_LEVELS`, `SEVERITIES`, `SUBJECT_VOCABULARY`, `FOUNDATIONAL_ISSUE_CODES`, `SIGNAL_NAMES` (+type table), `sort_issues`, `build_issue`, `normalize_issue`, `PORTABILITY_RULE_VERSION`, severity philosophy (§4), emits a `validate_report()`-clean report |
| Target rules (pure data) | `TARGET_IDS`, `make_target_result`, reference-by-code model (§7.2), `target_capability_unknown`, G3 semantics (§5), shares `PORTABILITY_RULE_VERSION` |
| Backend wiring | `EXPORT_ENDPOINT`/`IMPORT_MANIFEST_ENDPOINT` + query/body constants and defaults (§8), filename helper, atomicity requirement (§9), security limits (§10) |
| Report cache | `INVALIDATION_FIELDS`, stamp helpers + stale semantics (§11), derived-only discipline |
| Frontend | lowercase wire values, report/target/environment shapes (§7), chip→reason-list behavior inherits G4 §6.3 |

## 16. Regression evidence (this batch)

- `python tests/test_portability_contract.py` → **32/32 passed** (also unittest/pytest-discoverable).
- `python tests/test_studio_workflow_manifest.py` → all pass (manifest module untouched).
- `python -m unittest tests.test_workflow_domain tests.test_dependency_resolver tests.test_workflow_routes` → all pass.
- Wrapper: module registered in `tests/run_studio_tests.py` `STUDIO_PY_MODULES` (one line); final wrapper counts reported in the batch response.

*G5 complete. Deploy/live/GPU/generation/commit/push: NONE.*
