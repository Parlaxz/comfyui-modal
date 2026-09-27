# PHASE G4 — Workflow Portability Product Architecture Audit (2026-08-23)

Lane: G4 (Workflow Portability product architecture). Read-only audit; no production/test edits, no deploy/live/Modal/GPU, no git actions. G1/G2/G3 run concurrently; this document records the evidence and design decisions G-lanes will need. All paths are repo-relative with line references where material.

---

## 1. Verdict (TL;DR)

1. **A portability substrate already exists and is unwired**: `studio_workflow_manifest.py` (+ `WORKFLOW_MANIFEST_FORMAT.md`) is a pure, tested, deterministic manifest builder/validator/hasher that encodes exactly the authority chain Workflow → immutable Version → Mapping → Presets. It is imported only by its test (`tests/test_studio_workflow_manifest.py:17`). Phase G should **wire this module**, not invent a new format or a new "portable workflow" object.
2. **Canonical integration point**: the **WorkflowVersion** is the unit of portability. Export = build a manifest from an existing Version (+ Mapping + optionally Presets). Import = validate manifest → diagnose dependencies → create a *new* Workflow + *immutable initial Version* through the existing `create_workflow` / `create_version_from_capture` seams (`studio_domain/services.py:203`, `studio_domain/services.py:339`) plus `set_mapping`. No new domain entity, no parallel graph authority.
3. **Raw ComfyUI JSON is not enough** (it loses Mapping, Presets, dependency references); the existing single-file Studio Workflow Manifest JSON is the right v1 artifact. A multi-file ZIP package is explicitly *not* recommended for v1 (archive-extraction attack surface, no offsetting need — see §8).
4. **Risk UX must be explainable and four-state** (`LOW | MEDIUM | HIGH | UNKNOWN`), built on the existing `DependencyResolver.reasons_for` pattern of exact human-readable reason strings (`dependency_resolver.py:305`). UNKNOWN is never collapsed into LOW.
5. **Persistence**: portability reports are **derived cache**, never source-of-truth. The four domain JSON collections remain authoritative; a report cache keyed by invalidation stamps (§13) may follow the existing `.studio_workflow_compatibility.json` annotation-store pattern (`model_library_routes.py:98`).
6. **Naming collision to avoid**: "compatibility" in the current product means *model-compatibility annotations* per version (`GET/PATCH /workflows/versions/{id}/compatibility`, `model_library_routes.py:302-364`). Target-environment portability must use distinct naming ("portability", "target readiness") to avoid two meanings of one word.

---

## 2. Current Workflow Product — Evidence Map

### 2.1 Domain model (`studio_domain/models.py`)

| Entity | Key fields | Mutability |
|---|---|---|
| `Workflow` (:148) | name, description, folder, tags, favorite, `source_url`, `source_author`, compatible_models, default_preset_id, latest_version_id | mutable via `update_workflow` |
| `WorkflowVersion` (:149) | graph_json, api_prompt_json, executable_prompt, `graph_hash`, `dependency_metadata` {model_stack, node_classes}, compatible_models | **immutable** — store has insert-only (`store.py:117-129`) |
| `Mapping` (:326) | semantic-role → node/input entries; exactly one per version, insert-once (`store.py:145-166`) | immutable after insert |
| `WorkflowPreset` (:364) | values, model_choices, lora_values, exposed_controls, recommended_values, dropped_controls, tags | mutable, version-tied |

Derived states (`VersionState`/`PresetState`, models.py:429-450) are computed at read time and carry `status/reasons/runnable` — the established "explainable state" contract of this codebase.

Note: `presets.py` (repo root) is a **different, legacy** prompt/image preset system for experiments (`.presets/` layout). It is out of scope for workflow portability; all preset talk here means `WorkflowPreset`.

### 2.2 Persistence (`studio_domain/store.py`, `studio_store.py`)

- Four JSON collections on `StudioJsonStore` (thread-safe, atomic tmp+os.replace): `.studio_workflows.json`, `.studio_workflow_versions.json`, `.studio_workflow_mappings.json`, `.studio_workflow_presets.json` (`store.py:36-51`). **Not SQLite.**
- History V2 **is** SQLite (`history_v2_repository.py`) and already links generations to `workflow_id`, `workflow_version_id`, `preset_id/preset_name`, `workflow_hash`, and stores request snapshots containing `execution_plan_json` (history_v2_repository.py:247-250, 339-350).
- Model-compat annotations persist in `.studio_workflow_compatibility.json` keyed by `version_id` (`model_library_routes.py:98-124`) — the in-repo precedent for small per-version sidecar stores.

### 2.3 Backend API (`studio_workflow_routes.py`; dependency endpoints in `model_library_routes.py`)

All under `/comfymodal/studio/workflows`: list/search/filter, create, **`POST /import`** (capture → Workflow + first Version + optional `resolver.resolve_version` → `dependency_summary`, routes:216-255), folders/tags, detail, PATCH metadata, default-preset set/clear, `GET /{id}/run-context` (Playground bundle: workflow+version+mapping+default preset+state+control schema, routes:337-374), versions list/capture, version detail/state, mapping get/create(409 if exists)/candidates/**revision-as-new-version**, presets CRUD/duplicate/copy-forward/copy-bulk.

Separate file: `GET .../versions/{id}/dependencies` (resolver-backed, model_library_routes.py:281-300) and the compatibility annotations endpoints (:302-364).

**No export route exists anywhere for workflows. No manifest import route exists.** The only import path today is raw-capture import.

### 2.4 Dependency diagnosis engine (`dependency_resolver.py`)

`DependencyResolver` reads persisted stores only (Model Library + Custom Node Registry; never filesystem scans, never installs). Outputs:
- Models: `installed | missing | wrong_version | unknown` with hash/folder/source_urls (:85-190)
- Custom nodes: `installed | wrong_revision | missing` with repo_url/required_revision (:200-272)
- Aggregate summary counts + `ready` flag (:276-303)
- `reasons_for(version)` → exact human-readable strings, wired into `derive_version_state` via `dependency_provider` (services.py:508-514) so runnability gating already explains itself.

### 2.5 Frontend (`web/`)

- **Workflows page** (`studio-workflows.js`, ~1900 lines): library grid with cards (state badge, latest version number, default preset name, favorite), folder tree + tag + search filters, **Import dialog** with two modes — "graph" (capture current ComfyUI graph as first version; surfaces the returned `dependency_summary` before closing, :793-795) and "manual" (empty workflow). Detail page: Versions section ("Capture new version"), Dependencies section (`renderDependencySection` from `studio-model-library.js`, refreshable), mapping editor with explicit immutability confirmation ("Save = new revision", :1396-1404), preset editor with copy-forward.
- **Playground** (`studio-playground.js:1353-1483` + frozen logic module `studio-workflow-run.js`): Workflow / Version / Preset selector backed by `run-context`; runnable resolution merges version state with model-compatibility gating (`modelCompatibility`, studio-workflow-run.js:678) and produces gating text like "Select a workflow / Select a version".
- **History V2** (`studio-history-v2*.js`, `history-v2-repository.js`): items carry workflow/version/preset identity; detail links back to Workflow Version/Preset; browser-download helper exists (`history-v2-browser-download.js` — filename sanitization, blob download, note painting) and configured-folder export helper (`history-v2-export.js`).
- API client surface (`studio-backend-api.js:412-660`): full workflow/version/mapping/preset functions incl. `getVersionDependencies`, `getVersionCompatibility`, `updateVersionCompatibility`.

### 2.6 ExecutionPlan & accepted-run chain

`ExecutionPlan` (`comfymodal_runtime/contracts.py:1031`) is the immutable runtime execution contract; built solely via `build_execution_plan` (`canonical_execution.py:1446`) and dispatched verbatim; History replay revalidates snapshots before `ExecutionPlan.from_dict` (`history_v2_replay.py:18-42`). The Studio chain is therefore:

```
Workflow → immutable WorkflowVersion → (immutable Mapping) → Presets
        → derived VersionState (reasons) → accepted ExecutionPlan at dispatch
```

Portability must attach to this chain, never fork it.

### 2.7 Existing manifest module (`studio_workflow_manifest.py`, documented in `WORKFLOW_MANIFEST_FORMAT.md`)

Single-JSON manifest v1 with roots `manifest_version, workflow, version, mapping, presets[], models[], custom_nodes[], assets[], metadata`:
- Embeds the graph + recomputes `graph_hash` on validation (fail-closed on mismatch); `manifest_hash(..., include_metadata=False)` gives timestamp-free identity.
- Dependencies are **reference records only** (filename/sha256/size/source_urls; repo_url/revision/classes) — no bytes, no code.
- `parse_manifest` collects **all** issues (never fails fast); `check_readiness` is a pure structural pre-check (missing hashes, missing repo/revision).
- Security model: stdlib-only, zero I/O/network/execution; URLs are data; NaN rejected; root-strict/section-lenient evolution policy.
- Route wiring is explicitly deferred ("Routes are NOT wired yet", WORKFLOW_MANIFEST_FORMAT.md §10) with suggested integration points matching what G4 independently identified.

---

## 3. Canonical Integration Point (decision)

**Decision: WorkflowVersion-centric portability around the existing domain, surfaced through `studio_workflow_routes.py`, using `studio_workflow_manifest.py` as the artifact codec.**

Rationale:
- The manifest module already cross-checks the exact authority relationships (workflow↔version↔mapping↔presets ids, graph_hash) — importing a manifest cannot silently create a second authority because the importer mints **new local ids** and re-derives everything else (§7).
- `POST /workflows/import` and `POST /workflows/{id}/versions` are proven seams for "external graph → new immutable Version"; manifest import is a strict superset of capture import (graph + api_prompt + mapping + presets + dependency refs).
- `derive_version_state` + `DependencyResolver.reasons_for` already define the explainable-state idiom the risk UI should extend, not replace.

**Rejected alternative**: a first-class "PortableWorkflow" entity or a `portability` column on Workflow. This would duplicate graph authority, go stale against immutable Versions, and contradict the store's immutability design. Evidence does not demand it.

---

## 4. Product Surface Ownership (where each future action lives)

Default rule: **Workflows owns portability**; no other surface has an ownership claim. Settings only hosts global toggles if any emerge (none required for v1).

| Future action | Surface | Placement rationale / evidence |
|---|---|---|
| Export Workflow (manifest download) | **Workflow detail header** (+ card overflow menu later) | Export is about one Workflow's latest/selected Version; detail page already hosts version-scoped actions (capture, dependencies). Browser-download pattern exists (`history-v2-browser-download.js`). |
| Include presets toggle at export | Export dialog (small confirm popover) | Presets are optional manifest section; explicit user choice prevents silently exporting mutable state. |
| Check portability / refresh risk | **Version row + Version detail "Portability" panel** (adjacent to Dependencies section) | Risk is per-Version (roadmap requirement); Dependencies section already renders resolver output per version (`studio-workflows.js:1296-1308`). |
| View portability risk (summary) | Workflows list card chip (latest version) + detail header chip | Mirrors how `latest_version_state` is enriched into summaries today (`_enrich_workflow_summary`, routes:114-140). Must be lazy/cached (§13) to avoid N×resolver cost per list render. |
| View reasons / issue list | Panel opened by clicking any risk chip | Non-negotiable: badge click always reveals reasons (§6). |
| View dependency requirements | Existing Dependencies section (unchanged) | Already implemented; portability panel links to it rather than duplicating. |
| View target-environment compatibility | Portability panel, per-target tabs/rows (Local, Modal, RunPod, RunComfy, Comfy Cloud, Baseten) | Advice layer over the same Version; see §9. Distinct naming from model-"compatibility". |
| View missing models/nodes | Dependencies section (models/custom_nodes states) + issue list cross-links | Resolver already classifies these. |
| Download portability manifest/checklist | Portability panel footer: "Download checklist (.md)" + "Download manifest (.json)" | Checklist is a deterministic rendering of the report (§11); manifest is the canonical artifact. |
| Import Workflow | **Workflows list toolbar**, extending the existing Import dialog with a third mode "From file (.json)" next to "graph"/"manual" (`studio-workflows.js:559-568, 691+`) | Import creates a new Workflow; its home is the library, not a version. Dialog gains a preview/diagnosis step before create (§7). |
| Rollback / recovery guidance | Import result notice + portability panel footnote | See §11.4 — rollback is trivial because import is purely additive. |
| Backend analysis endpoints | `studio_workflow_routes.py` (export/import/portability routes); risk engine + target rules as separate pure modules | Matches the repo's pure-core/route-shell split used by the manifest module itself. |

Not on: Playground (consumes runnability only), History (links *from* runs to versions; could deep-link to the portability panel later but hosts nothing), Settings (no global portability state in v1).

---

## 5. Preserving the Single Authority Chain

Any portability feature must keep exactly one graph authority per Workflow:

- Export reads; it never writes. Building a manifest must not touch `latest_version_id`, presets, or mappings.
- Import always lands as **new** Workflow + Version #1 (+ Mapping + optional Presets) through existing service methods; it never appends a Version to an existing Workflow in v1 (that would entangle duplicate-graph dedupe semantics with foreign input; can be revisited later as explicit "import as version" flow).
- Graph-hash discipline: local canonical hash (`graph_hash_from_capture`, services.py:345) remains the identity; the manifest's embedded-hash cross-check (WORKFLOW_MANIFEST_FORMAT.md §5) guards transport integrity; idempotent re-import follows the existing same-hash → return-existing rule (services.py:347-357).
- ExecutionPlan is untouched: plans remain runtime-derived from the accepted Version+Preset values; portability never serializes plans (they embed environment/runtime specifics and would create a second executable truth).

---

## 6. Risk Score UX Contract (explainable, four-state)

Roadmap requires per-Workflow LOW/MEDIUM/HIGH. Contract below extends the house style (`VersionState.reasons`, `reasons_for`).

### 6.1 States

- `LOW` — every finding resolved: all custom-node classes mapped to installed repos at required revision (or core), all model refs installed with matching hash (or no stricter pin declared), no structural lint findings.
- `MEDIUM` — portable with attention: unpinned-but-resolvable refs (model without sha256, custom node without revision), wrong_version/wrong_revision on resolvable deps, soft lint findings (e.g., absolute-path-looking widget values).
- `HIGH` — blocking findings: missing required custom-node class with no repo candidate, missing model with no source_urls, structurally non-portable graph (unresolvable node class anywhere), manifest readiness failures.
- `UNKNOWN` — analyzer could not produce a verdict: no executable prompt, unreadable library/registry stores, rule-engine error, or unanalyzed version. Rendered as a distinct neutral chip ("Unknown — not analyzed") with the reason. **Never rendered green/LOW.**

### 6.2 Payload shape (backend → UI)

```json
{
  "version_id": "wv_...",
  "graph_hash": "<64hex>",
  "risk_level": "MEDIUM",
  "rule_version": "portability-rules-v1",
  "issue_count": 3,
  "counts": { "high": 0, "medium": 2, "low": 1 },
  "issues": [
    {
      "code": "custom_node_unpinned",
      "severity": "medium",
      "message": "2 unpinned custom nodes: FooNode, BarNode",
      "subject": "custom_nodes",
      "fix_hint": "Pin a revision in the export dialog or install via Manager"
    }
  ],
  "targets": {
    "local":  { "risk_level": "LOW",    "issue_codes": [] },
    "modal":  { "risk_level": "MEDIUM", "issue_codes": ["native_install_disallowed"] }
  },
  "stale": false,
  "analyzed_at": "<iso>"
}
```

Rules: `severity` ∈ {high, medium, low}; `code` is a stable machine key (tests pin them); `message` is the exact human-readable sentence (deterministic ordering — sort by severity desc, then code, then subject); `targets.*.risk_level` may differ from summary; `stale=true` when invalidation keys mismatch (§13). Determinism requirement: same inputs (version bytes + store states + rule_version) ⇒ byte-identical report modulo `analyzed_at`.

### 6.3 UI behavior

- Every chip is a button; clicking opens the reason list (reuse `_reasonList` styling, studio-workflows.js:144). A colored badge with no reachable explanation is a defect.
- UNKNOWN chips are gray with tooltip "Not analyzed yet — run Check portability".
- Issue rows deep-link: missing model → Model Library entry; missing node → custom-nodes section; unpinned → export dialog pin control.
- List-card chips show summary only (level + count); detail lives one click away.

---

## 7. Export Format (decision)

**Verdict: raw ComfyUI JSON alone is insufficient; ship the existing single-file Studio Workflow Manifest (v1) as the canonical export artifact.**

- It already carries graph + api-format prompt + Mapping + optional Presets + dependency reference records + deterministic hashing — i.e., everything "reproduce one workflow run elsewhere" needs, and nothing heavy.
- **Package architecture decision: no ZIP in v1.** The audited `workflow.json + manifest.json + README` layout adds an archive container whose only unique payoff (bundled assets/models) is explicitly unwanted by default (huge files), while introducing unsafe-extraction attack surface (§10). If a bundle is ever needed (e.g., include thumbnail asset), add a *second, separate* small file download rather than an archive.
- Checklist/README: generated deterministically **from the portability report** as a sibling `.md` download (and rendered inline in the panel). It is derived advice, not authority; the manifest stays the single artifact of record.
- Secrets: exporter must scrub/flag before write — scan embedded graph/metadata for credential-shaped keys (`api_key`, `token`, `authorization`, `password`, cookie/header widgets) and either strip with a recorded issue or refuse with a HIGH finding. Test-pinned (§14).
- Preset data belongs in the manifest's optional `presets` section behind an explicit "Include presets" toggle (module already validates `is_default` uniqueness). Never silently export the *current mutable* preset state: export serializes the stored preset records as-is; the toggle governs inclusion only. Default-preset pointer is preserved as data (`is_default`), but import does not auto-apply defaults without user confirmation (§7 dialog).
- Filename convention: `<name>-v<version_number>-<short8 graph_hash>.workflow.json` reusing `sanitizeFilenamePart` semantics from `history-v2-browser-download.js:56`.

## 8. Import Semantics (design for future implementation)

Pipeline: **file → parse/validate (all issues) → dependency diagnosis preview → user confirms → create Workflow + Version#1 + Mapping (+ Presets)**. Inspect-before-execute: nothing is installed, fetched, or registered during import.

Endpoint sketch (ownership: `studio_workflow_routes.py`): `POST /comfymodal/studio/workflows/import-manifest` returning either `preview` (validate+diagnose only, `?dry_run=1`) or the created entities. Reuses `parse_manifest` → service `create_workflow` → `create_version_from_capture(graph_json/api_prompt_json from manifest)` → `set_mapping` → optional `create_preset` loop.

Policy answers:

| Question | Policy |
|---|---|
| Duplicate-name | Names are not unique today (services.py:203-231 enforces nothing beyond non-empty). Keep allowing duplicates; UI pre-fills `<name> (imported)` suggestion and shows existing-name matches. |
| Imported IDs | **Never reuse** `wf_/wv_/wm_/wpres_` ids from the package; mint fresh local ids. Original ids move to provenance (Workflow.description prefix or a `source` block; `source_url`/`source_author` fields already exist for exactly this shape of metadata). |
| Version provenance | Local `version_number` starts at 1. Manifest's original `version_number`, `created_at`, and `graph_hash` recorded in provenance metadata (e.g., `metadata.portability.origin`), clearly labeled as foreign. |
| Graph-hash behavior | Recompute locally; manifest cross-check must pass first (declared vs recomputed). Same-hash re-import into the *same* imported workflow follows the existing idempotent-return rule; across different workflows hashes may coincide legitimately (mapping revisions prove this is normal, services.py:388-405). |
| Missing nodes | Structural validity ≠ local runnability (the manifest module's stated separation). Unknown node classes import fine; resolver reports `missing`; VersionState incomplete; Playground gates the run. |
| Missing models | Same: `missing`/`unknown` findings; import proceeds; run gated. Source URLs shown as *data* with explicit "install manually / via Manager" affordances (§10). |
| Unsupported fields | Section-level unknown keys preserved as data (existing lenient policy); **unknown root sections reject** with issue list (schema-change signal). No silent stripping. |
| Malformed JSON | `parse_manifest` reports `invalid JSON: ...` plus all subsequent issues; endpoint returns 400 with the full issue list; nothing persisted. |
| Dependency mismatch | `wrong_version`/`wrong_revision` findings displayed in preview; import allowed (analysis-first product stance, consistent with capture import); runnability still governed by live `derive_version_state`. |
| Presets on import | Recreated as regular presets bound to the new Version; `is_default` honored only if the user ticks "apply default preset" in the confirm step. |
| Failure atomicity | Create order workflow → version → mapping → presets mirrors existing flows; on any error mid-sequence, abort and surface issues; because ids are fresh and additive, partial failure leaves no mutated existing entity (cleanup of a partially created workflow needs the delete-workflow gap, §11.4). |

**Never** as part of import: pip installs, git clones, Manager calls, filesystem writes outside the domain stores, fetching `source_urls`.

## 9. Target Environment UX

- One canonical Workflow/Version; targets are **advice rows computed by pure rule adapters** keyed `local | modal | runpod | runcomfy | comfy_cloud | baseten`, each emitting target-scoped issue codes (e.g., `native_install_disallowed`, `volume_model_missing_hint`, `python_version_mismatch`).
- Rules consume only: manifest/readiness facts + resolver outputs + graph lint. No provider SDKs, no execution code, no credentials in the Workflow model. Adapters live in a versioned rules module (`rule_version` stamped into every report) so findings are reproducible and testable.
- UI: within the Portability panel, a compact matrix (target × risk chip) expanding to target-specific reasons. Summary chip always reflects the *current* environment default (Local) unless a target is selected.
- Naming: use "portability"/"target readiness"; do not extend the existing model-"compatibility" endpoints (collision documented in §1.6).

## 10. Security Controls (import/export)

The pure manifest module already provides: no I/O, no network, URL-strings-as-data, fail-closed NaN, type/shape validation, duplicate-identity rejection, size-bounded structure by construction. Route layer must add:

1. **Payload caps**: enforce max body size (suggest ≤ 10 MB) and JSON nesting/element-count sanity before parse; reject giant payloads with 413.
2. **No archive extraction in v1** (single-JSON artifact) — eliminates zip-slip/bomb class entirely. If archives ever ship: size-ratio checks, entry-name normalization, no absolute paths/`..`, per-entry caps, extract-only-to-temp-under-store-dir.
3. **Path traversal**: filenames in `models/assets` are display data; never join them onto filesystem paths for read/write during import/export. Only atomic `StudioJsonStore` writes occur.
4. **Arbitrary commands / code**: node `class_type` strings and `repo_url`s are inert data; import performs zero installs. Installation stays behind the existing explicit approval flow (`/models/install-request`, `/custom-nodes/install-request` with `approved: true` + fixed note, model_library_routes.py:203-277).
5. **Malicious dependency URLs**: rendered as text with hostname display; never auto-fetched; no link-auto-open in notes; export-side scrub ensures we don't launder bad URLs into trusted-looking manifests (still data).
6. **Credential leakage**: export scrubber (§7) + import-side warning when credential-shaped keys appear in incoming graphs (issue, not refusal — user may be importing their own export).
7. **Giant/deep structures**: recursion-safe canonicalization already exists (iterative json.dumps); add depth guard on parse for defense-in-depth.
8. **Filesystem writes**: limited to the four domain collections + optional report cache, all via atomic store helpers; no temp-file sprawl.

## 11. Folder Structure, Pinning, Checklist, Rollback

Grounded in current product concepts:

- **Folder structure recommendation** (in checklist): map manifest `workflow.display.name` + existing `folder` field to a conventional layout — `workflows/<folder>/<name>/workflow.v<N>.workflow.json` + `checklist.md`; models referenced into standard ComfyUI folders via the manifest's `folder` field (checkpoints/loras/...), which the resolver already uses (`_ROLE_TO_FOLDER`, dependency_resolver.py:21-28). Advice only; the product does not enforce on-disk layout.
- **Dependency pinning**: pinning quality is a first-class risk dimension — model sha256 present? custom-node revision present? Export dialog offers "pin current installed revisions/hashes" (fills manifest refs from Model Library/Registry records) — turning MEDIUM findings LOW deterministically. Pinning is captured in the exported manifest, never retro-mutated into the stored Version.
- **Checklist content** (generated from report): summary risk + counts; per-issue fix hints; dependency table (model → folder/hash status/source; node → repo@revision/status); target matrix; import-time expectations; provenance block (origin ids, exporter, rule_version, analyzed_at).
- **Rollback plan**: import is additive — rollback = "delete the imported Workflow". Current product has **no delete-workflow endpoint** (only preset delete, routes:599-610) — a known gap. Recommendation: portability lane documents manual recovery (remove `.studio_workflows.json` entry + orphaned version/mapping/preset records via future maintenance tooling) and flags `DELETE /workflows/{id}` as a small follow-up lane item with referential care (History rows keep their own copies; they must not break). Export needs no rollback (read-only).

## 12. Persistence — Derived Cache vs Source-of-Truth

- **Source of truth (unchanged)**: the four domain collections; Model Library; Custom Node Registry; compat annotations. Nothing portability-related is authoritative.
- **Derived cache (optional, recommended)**: last portability report per `(workflow_version_id)` in a new `.studio_portability_reports.json` sidecar (StudioJsonStore, mirroring `.studio_workflow_compatibility.json` precedent) storing the §6.2 payload including its invalidation stamps. Purpose: cheap list-card chips; avoids running resolver+lint per workflow per list render.
- Cache discipline: a cached report is **never** fed into `derive_version_state`, run gating, or import decisions; those stay live-computed. On stamp mismatch → recompute (or mark `stale:true` and recompute lazily). Because Versions are immutable, per-version report bytes are stable; staleness comes almost entirely from the environment side (below).
- User-authored overrides (if ever added, e.g., "acknowledge risk") would be *annotations* (source-of-truth-ish user data), stored separately from the derived report — not in v1.

## 13. Invalidation Keys

Report considered stale when any of:

1. `workflow_version_id` + `graph_hash` (identity; immutable per version — change ⇒ different report key);
2. `dependency_metadata` content hash (defensive; normally implied by 1);
3. Model Library generation stamp (records added/installed/hash-changed since analyze);
4. Custom Node Registry/discovery generation stamp;
5. `rule_version` (risk engine or target-rule adapter bump);
6. `manifest_version` support window (format evolution);
7. ComfyUI/core version for target rules that reference it.

Stamps recorded inside the cached report; mismatch ⇒ `stale:true` + recompute. Design only; no implementation in this phase.

## 14. Testing Architecture (future, deterministic)

Map onto existing suites; all new tests pure/deterministic (no network/GPU):

| Concern | Home | Notes |
|---|---|---|
| Manifest round-trip & hash determinism | `tests/test_studio_workflow_manifest.py` (exists) | Extend for export-builder parity: build-from-domain == build-from-manifest-imported. |
| Exact JSON round trip (export→import→export identical bytes) | new `test_portability_roundtrip.py` | Byte-equal canonical_json both directions; `include_metadata=False` identity. |
| No-secret export | same file | Golden fixture graph seeded with credential-shaped keys; assert stripped/refused + issue emitted. |
| Malformed package refusal | `test_workflow_routes.py` extension | Truncated JSON, wrong roots, NaN, oversized body → 400/413 with full issue list; store unchanged. |
| Risk-score determinism | new `test_portability_risk_engine.py` | Same inputs ⇒ identical report (modulo analyzed_at); severity ordering; UNKNOWN never LOW; golden per-code fixtures. |
| Per-target findings | new `test_portability_target_rules.py` | One rule adapter case per target × representative issue code; `rule_version` pinned. |
| Workflow Version immutability | `tests/test_workflow_domain.py` (exists) | Add: import path inserts-only; no update/delete reachable from import/export routes. |
| Stale-report invalidation | new `test_portability_cache.py` | Each §13 key bump flips stale/recompute; cache never influences derive_version_state. |
| Missing-dependency handling | extend `test_dependency_resolver.py` consumers | Import with missing model/node → success + findings + gated run. |
| Backward compatibility | manifest tests | `SUPPORTED_MANIFEST_VERSIONS` window; older-but-supported manifests import; newer reject with clear message. |

## 15. Implementation Lane Plan (future ownership split; no prompts written yet)

Derived from actual file topology to maximize parallelism with minimal overlap:

| Lane | Owns | Files (new unless noted) | Depends on |
|---|---|---|---|
| L-A Manifest wiring (backend) | Export/import/portability HTTP endpoints; preview flow; provenance minting | `studio_workflow_routes.py` (extend), thin `portability_routes.py` if route file size demands | contracts from L-B (shapes only) |
| L-B Risk engine (pure core) | Findings linter (absolute paths, unpinned refs, missing hashes), severity mapping, report assembly | `portability_risk.py` | consumes DependencyResolver outputs (exists) |
| L-C Target rule adapters (pure data) | Per-target issue codes + advice, `rule_version` | `portability_targets.py` | L-B interfaces only |
| L-D Report cache + invalidation | Sidecar store, stamps, stale logic | `portability_cache.py` (+ `.studio_portability_reports.json`) | L-B payload |
| L-E Frontend UX | Portability panel, chips, import dialog mode 3 + preview step, checklist/manifest downloads | `web/studio-portability.js`, hooks in `web/studio-workflows.js`, `web/studio-backend-api.js` | L-A/L-B response shapes |
| L-F Tests & fixtures | All §14 suites + golden manifests | `tests/test_portability_*.py` | contracts freeze first |

Sequencing: freeze the §6.2 payload + endpoint contracts (small joint step) → L-B, L-C, L-F(fixture authoring) parallel → L-A, L-D parallel → L-E last against live endpoints. L-E copywriting reviewed post-hoc per house rule.

## 16. Gaps & Risks Noted (for G-lane reconciliation)

1. **No delete-workflow capability** — import rollback and failed-import cleanup depend on it (§11.4).
2. **List enrichment cost** — `_enrich_workflow_summary` already does per-workflow version scans; adding live risk computation per card would compound N×store-reads; the §12 cache (or latest-version-only lazy chips) is required, not optional.
3. **Terminology collision** — "compatibility" (model annotations) vs portability targets (§1.6); frontend already has near-duplicate `getVersionCompatibility` definitions in `studio-backend-api.js` (~:650-660) worth cleaning up in L-E.
4. **Manifest module drift risk** — until wired, `WORKFLOW_MANIFEST_FORMAT.md` is the spec of record; L-A must not fork validation logic into routes.
5. **Legacy `presets.py` naming** — docs/UI copy must say "Workflow presets" to avoid confusion with experiment prompt/image presets.

## 17. Explicit Non-Goals (this phase)

No installer/builder logic, no Manager integration, no archive format, no import-into-existing-workflow flow, no ExecutionPlan serialization, no provider APIs, no SQLite migration of the domain stores, no deletion endpoints implemented — design positions only.

---

*Audit produced by lane G4. Evidence current as of working-tree state 2026-08-23 (HEAD 0c59f46).*
