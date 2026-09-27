# PHASE G FINAL CLOSURE — ZERO-CONTEXT HANDOFF (2026-08-23)

**Audience:** a future agent with ZERO conversational context starting Phase H (Studio Consolidation).
**Purpose:** single authoritative reconciliation of everything Phase G (Workflow Portability) set out to do, the architecture chosen, what actually shipped in G1–G12, every frozen contract, every defect/finding and how it was resolved or classified, the rejected approaches, the exact deterministic evidence, what is COMPLETE, and what is intentionally deferred.
**This document supersedes no earlier report's history; it reconciles them.** The Phase-F handoff (`PHASE_F_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md`) remains untouched and authoritative for Phase F.
**Batch type:** G13 = documentation/reconciliation only. No production code, tests, deploy, Modal, GPU, live generation, dependency installs, provider calls, commit, push, branch, worktree, reset performed by THIS batch. Files modified by this batch: **this document only**.

---

## 1. FINAL VERDICT AND AUTHORITATIVE GATE

## `PHASE G COMPLETE`

### Final shared-tree gate state (authoritative closure numbers, re-run by this closure batch)

```
python tests/run_studio_tests.py --fake
Python lane:        1991 run / 1991 pass / 0 fail / 0 error / 0 skip
Node unit lane:     21 / 21 files PASS
Fake Playwright:    PASS (wrapper lane green)
```

Direct fake-Playwright measurement immediately after the wrapper run:

```
npm run test:fake  →  192 passed (3.5m) / 0 failed
```

### Fake-Playwright count chronology (stated, not hidden)

| Milestone | Fake Playwright | Note |
|---|---|---|
| Phase F close (baseline) | 176/176 | pre-Phase-G baseline |
| G11 wrapper run | 185/190 (5 red) | ALL 5 reds were inside `tests/browser/fake/studio-fake-workflow-portability.spec.mjs`, G12's actively-in-flight UNTRACKED spec; G11 touched zero frontend/fake files; transient concurrent-lane state |
| G12 final converged report | **192/192** full suite (16/16 portability spec) | recorded in G12 §11 |
| **G13 closure re-measurement** | **192/192** | direct `npm run test:fake`; reproduces G12's own final number exactly |

Reconciliation note: some interim coordination notes quoted "189/189" as G12's converged figure. That number matches neither G12's own written final report (192/192 full suite) nor this batch's direct re-measurement (192 passed). The arithmetic is consistent: 176 baseline + 14 in-flight spec tests at G11 time (9 pass + 5 fail = 190 total observed) + 2 more tests added while G12 finished its spec = 176 + 16 = 192. **The authoritative current count is 192/192.** The temporary five reds are historical concurrent-lane noise, NOT current failures.

### Python-lane growth across Phase G

Phase F closed at Python 1741 / Node 21 / Fake 176. Phase G added the portability suites to the gate (G11 registration): contract (32), risk engine (28), target rules (33), fixtures (35), backend (45), roundtrip (4), cache (40), cache integration (33) — plus normal drift — landing at **1991**, all green.

---

## 2. WHAT PHASE G WAS — MANDATE

Phase G = **Workflow Portability**. The original roadmap required that a Studio Workflow can move across exactly six targets — **Local ComfyUI, RunPod, RunComfy, Comfy Cloud, Modal, Baseten** — with:

1. exact Workflow JSON portability;
2. custom-node dependency understanding;
3. model-path/model dependency understanding;
4. runtime/platform restriction analysis;
5. reproducibility understanding under dependency/ComfyUI changes;
6. per-Workflow LOW/MEDIUM/HIGH portability risk;
7. explainability of every risk;
8. folder-structure guidance;
9. dependency-pinning guidance;
10. import/export checklist;
11. rollback/recovery guidance.

Every requirement is now either **A. IMPLEMENTED**, **B. DELIBERATELY ADVICE-ONLY by the Phase-G architecture**, or **C. EXPLICITLY DEFERRED by roadmap/product decision**. The complete classification table is §31 (Final Gap Classification). "We could build more automation" was never treated as a missing requirement.

### Batch map (what actually shipped)

| Batch | Lane | Outcome |
|---|---|---|
| G1 | Read-only Workflow corpus & exact-JSON audit | Capture-pair fidelity PROVEN; graph identity = executable-prompt hash; corpus env-clean; MEDIUM provisional workflow risk; S1–S12 signal proposal |
| G2 | Read-only dependency & reproducibility audit | Source environment HIGH reproducibility debt enumerated; pinning-quality classification; HIGH risk contribution |
| G3 | Read-only six-target runtime matrix | Import-vs-executes distinction per target; capability matrix with explicit UNKNOWNs; no-guessing evidence discipline |
| G4 | Read-only product architecture audit | Wire the existing manifest module; WorkflowVersion-centric design; risk UX contract; derived-cache design; rejected PortableWorkflow entity |
| G5 | Contract freeze (`portability_contract.py`, 32 tests) | Three distinct risk dimensions; four-state lowercase vocabulary; six target ids; issue/report/target/environment/invalidation/checklist schemas; endpoint contracts; security limits; MEDIUM-vs-HIGH resolution frozen |
| G6 | Pure risk engine (`portability_risk.py`, 28 tests) | All 14 static signals; deterministic issues; environment isolation proven; audited corpus resolves MEDIUM workflow + HIGH environment simultaneously |
| G7 | Target readiness rules (`portability_targets.py`, 33 tests) | Six pure adapters over tri-state evidence; UNKNOWN preserved; G3 golden matrix encoded deterministically |
| G8 | Fixture corpus (`tests/fixtures/portability/` + loader + 35 self-tests) | 18 frozen scenario ids; cross-lane stable evidence incl. current-corpus reconciliation fixture |
| G9 | Backend integration (`portability_service.py`, `portability_evidence.py`, store transaction, routes; 45+4 tests) | Export/dry-run-first Import/live report wired end-to-end; atomic import commit; credential fail-closed export; aux_id provenance rescue |
| G10 | Derived cache & invalidation (`portability_cache.py`, 40 tests) | Sidecar store; frozen 8-field stamps; null-always-stale; fail-open corruption behavior; hit/miss/stale/invalid states |
| G11 | Cache integration + list enrichment (+33 integration tests; runner registration) | GET serves through cache with zero-analysis hits; all eight stamp authorities concrete; `portability_summary` on list/detail; fail-open; Python lane reached 1991 green |
| G12 | Frontend UX (`web/studio-portability.js`, `web/studio-portability-checklist.js`, Workflows UI wiring, fake parity; 16 browser tests + unit sections) | Chips, panel, target matrix, environment separation, Export popover, mandatory dry-run Import dialog, checklist download; no browser-side risk engine |

---

## 3. CANONICAL AUTHORITY CHAIN (final)

```
Workflow
  → immutable WorkflowVersion        (write-once; ImmutableVersionError on update)
    → immutable Mapping              (exactly one per version; insert-once)
      → version-scoped WorkflowPreset(s)   (mutable values, version-tied)
        → accepted ExecutionPlan     (runtime-derived at dispatch; immutable per run)
```

**Portability attaches to the WorkflowVersion.** Analysis, reports, cache rows, and export are all keyed by `workflow_version_id`.

**Explicitly recorded: Phase G did NOT create:**

- a `PortableWorkflow` entity (no duplicate graph authority);
- a second graph store;
- a portable ExecutionPlan (plans embed environment/runtime specifics and remain runtime-derived);
- provider-specific Workflow copies;
- a ZIP package authority.

The four domain JSON collections (`.studio_workflows.json`, `.studio_workflow_versions.json`, `.studio_workflow_mappings.json`, `.studio_workflow_presets.json`) plus Model Library and Custom Node Registry remain the ONLY sources of truth. Everything portability-related outside them is derived.

---

## 4. MANIFEST — THE CANONICAL PORTABILITY ARTIFACT

- **Canonical artifact:** **Studio Workflow Manifest v1**, implemented by `studio_workflow_manifest.py` (pure, stdlib-only, zero I/O), documented in `WORKFLOW_MANIFEST_FORMAT.md`. It remains ONE JSON file.
- Roots: `manifest_version(=1), workflow, version, mapping, presets[], models[], custom_nodes[], assets[], metadata`. Unknown ROOT sections reject; unknown keys INSIDE sections are preserved data.
- **Export route:** `GET /comfymodal/studio/workflows/versions/{version_id}/export`
  - Query `include_presets=0|1`; **default false** (never silently exports mutable Workflow Presets).
  - Response: canonical manifest-v1 JSON bytes, `Content-Disposition: attachment; filename="<sanitized-name>-v<version_number>-<graph_hash[:8]>.workflow.json"` via the frozen `suggest_export_filename` sanitizer (mirrors `history-v2-browser-download.js::sanitizeFilenamePart`; fallback part `workflow`). Header value re-sanitized defensively.
- Properties (all pinned by tests):
  - **read-only** — byte-level store snapshots before/after prove zero mutation; no run request issued;
  - **graph/API capture** — `workflow.graph` = persisted executable prompt projection (`extract_executable_prompt(api_prompt_json)`; never a recapture) with `graph_hash` equal to the Version's stored hash, so manifest integrity *verifies the domain identity rule*; `version.graph_json` and `version.api_prompt_json` embedded verbatim as section payload;
  - **Mapping** — role-keyed entries from the stored immutable Mapping;
  - **optional Workflow Presets** — raw records + derived `is_default` from the Workflow pointer, only when explicitly requested;
  - **dependency references** — models[] (filename/sha256/size/folder/provider/revision/source_urls) and custom_nodes[] (repo_url/revision/classes): reference records only;
  - **asset references** — LoadImage-family basenames + role; suffix qualifiers stripped; bytes never read; sha256/size/mime omitted when unknown;
  - **NO model bytes, NO custom-node code, NO ZIP, NO local install paths** (`.studio_model_library.json` `local_path` and `.studio_custom_nodes.json` `install_path` are never exported), **NO secrets**.
- An unmapped version or a stored-hash/recompute mismatch fails Export closed (409 `export_integrity_failure` / `graph_hash_mismatch`).

---

## 5. EXACT JSON — FINAL PROOF

Persisted and proven equal across the full cycle **Export → dry-run Import → committed Import → re-Export** (`tests/test_portability_roundtrip.py::test_full_round_trip_is_exact`):

- canonical `graph_json` equality;
- canonical `api_prompt_json` equality;
- executable-prompt equality;
- equal `graph_hash`;
- Mapping semantic equality under reminted ids;
- Preset semantic equality (incl. single default) under reminted ids;
- full canonical equality of normalized manifests with `manifest_hash(include_metadata=False)` stable.

Allowed deltas are limited to reminted local ids, timestamps, and the deterministic `" (imported)"` name suffix. Double import creates two independent complete workflows with disjoint identities.

**Intentional graph identity rule (must not be reported as a bug):** graph identity is the canonical SHA-256 of the **executable API prompt** (`api_prompt_json.output`), NOT the UI graph layout. Two captures with different UI-only bytes (positions/titles/layout) but an identical executable prompt dedupe to the same version, and the newer UI-only capture is discarded. This is deliberate, codified at capture time, and pinned by domain tests since before Phase G.

---

## 6. IMPORT — FINAL SEMANTICS

**Route:** `POST /comfymodal/studio/workflows/import-manifest` (distinct from raw-capture `POST /workflows/import`).

- Body IS the manifest JSON. Query `dry_run=1|0`; **default dry_run=true**.
- Commit additionally reads two frozen body policy fields `import_presets` (default false) and `apply_default_preset` (default false); the route strips exactly these two keys before manifest validation (manifest roots are closed).
- Statuses: 200 preview (`status:"preview"`) / 200 commit (`status:"ok"`) / 400 malformed-invalid-unsupported-version-hash-mismatch-non-finite-depth-element (all issues collected where available) / 413 >10 MiB (content-length pre-check AND post-read check) / 404 n/a / 500 true internal only.

**Required user flow:** file → dry run → diagnosis → explicit confirmation → atomic commit. There is no bypass: the commit control does not exist until a valid preview renders.

Recorded behaviors:

- malformed manifests REJECTED (400, full issue list, nothing persisted);
- future unsupported `manifest_version` REJECTED;
- integrity mismatch (declared vs recomputed graph hash) REJECTED;
- missing dependencies do NOT prevent import — structural validity ≠ local runnability;
- runnability remains governed by the existing live `derive_version_state` + DependencyResolver (unchanged gating);
- foreign `wf_/wv_/wm_/wpres_` ids are PROVENANCE ONLY; new local ids minted; local version numbering starts at 1; suggested display name `<name> (imported)`; duplicate names allowed;
- presets optional (`import_presets`); an imported default preset is NEVER silently applied (`apply_default_preset` explicit, gated on imported presets AND a preview-reported default candidate);
- NO installation, NO fetch, NO shell, NO auto-run during import — ever.

Preview response carries: validity + manifest_version, ALL issues, structural readiness, dependency availability, portability risk (four separate truths), proposed name, existing-name matches, will-create counts, security findings.

---

## 7. IMPORT ATOMICITY — ACTUAL LANDED MECHANISM

Implemented as **`WorkflowDomainStore.commit_import_transaction(workflow, version, mapping, presets)`** (+ `_compensate_import`) in `studio_domain/store.py` — option C (explicit compensation) hardened with staged pre-validation:

1. one exclusive in-process import lock serializes concurrent imports;
2. uniqueness checks run up-front AND inside each per-store mutator (race-free at write time under each store's own lock);
3. appends apply versions → mappings → presets → workflows, with the **Workflow row LAST as the commit point** (a Workflow without complete children never becomes visible);
4. any exception triggers `_compensate_import`, removing exactly the ids this transaction added (newest-first, each removal an atomic id-keyed update), restoring byte-identical collections.

Default-preset application happens during staging (`default_preset_id` set on the staged Workflow record) so it is covered by the same transaction — no post-commit write exists.

Evidence: injected failures at all eight mandated stages leave all four collections byte-equal to their pre-import state (tests 22a–22h); concurrent imports complete without corruption or cross-linking.

**This closes G4's earlier delete-workflow rollback concern FOR IMPORT FAILURE.**

---

## 8. DELETE-WORKFLOW QUESTION — RECONCILED

G4 originally noted "no public Workflow delete endpoint" as a rollback gap. Final reconciliation:

- Committed-import failure is now atomic/compensated (§7), so absence of public DELETE is **NOT an import-atomicity defect**.
- Was "delete a successfully imported Workflow later" ever an actual Phase-G roadmap requirement? **No.** No roadmap artifact requires it; G4 listed it only as a noted gap with a recommendation to flag it for a follow-up lane. G12 mentioned it once more as optional UX.
- Classification: **later product lifecycle capability (Phase H or future)** — NOT a Phase-G blocker. Not implemented in G13.

---

## 9. PORTABILITY RISK MODEL — FIVE DISTINCT CONCEPTS

Frozen in `portability_contract.py` as `PORTABILITY_CONCEPTS` (all five separately named):

```
manifest_readiness ≠ dependency_availability ≠ workflow_portability_risk
                   ≠ target_readiness ≠ environment_reproducibility
```

- **manifest readiness** — pure structural `check_readiness()` on the manifest (missing hashes/repo-revision pins).
- **dependency availability** — live resolver states against Model Library / Custom Node Registry (`installed | missing | wrong_version | wrong_revision | unknown`).
- **Workflow portability risk** — summary LOW/MEDIUM/HIGH/UNKNOWN for the immutable WorkflowVersion, from graph structure, node identities, model refs/hashes, assets, paths/endpoints, dependency-resolution evidence.
- **target readiness** — per-target result for exactly six targets, each with its own issues/advice.
- **environment reproducibility** — how exactly the CURRENT source execution environment itself can be reproduced (separate report section).

Wire risk values (lowercase everywhere): `low | medium | high | unknown`.

Severity philosophy (frozen): LOW = no blocking/unresolved findings; MEDIUM = portable with explicit setup/attention (unpinned-but-resolvable, unhashed models, separate assets, soft concerns); HIGH = likely/non-negotiable blocker (unresolved required node identity, host-bound path required elsewhere, unavailable source, manifest readiness failure, target cannot satisfy a requirement); UNKNOWN = analyzer cannot make a defensible determination. Issue severity is `high|medium|low` ONLY — inability to judge is expressed as an UNKNOWN verdict plus an explanatory issue, never an "unknown severity".

**UNKNOWN never becomes LOW** — pinned by contract validation and tests.

Deterministic explainability: issues carry `{code, severity, message, subject, fix_hint, evidence}`; ordering is **severity descending → code → subject**; duplicate codes within one report rejected; evidence bounded ≤2048 canonical bytes, finite JSON, never secrets/stack traces/huge fragments. Same inputs ⇒ structurally identical report except `analyzed_at`.

Foundational issue codes frozen: `credential_like_value_detected, local_path_reference, unresolved_node_type, custom_node_unpinned, model_hash_unpinned, model_extraction_gap, required_input_asset, external_endpoint_reference, subgraph_frontend_requirement, manifest_not_ready, dependency_missing, dependency_wrong_revision, target_capability_unknown` — plus three documented G6 additions (`graph_hash_mismatch`, `env_bound_registry_leak`, `analysis_unavailable`) and G7 target-only codes (`local_dependency_missing`, `runpod_image_setup_required`, `runcomfy_native_capability_unknown`, `comfy_cloud_node_off_catalog`, `comfy_cloud_node_support_unknown`, `baseten_deployment_embedding_required`, `baseten_storage_capability_unknown`, `target_absolute_path_blocker`, `dependency_source_unresolved`, `product_internal_dependency`).

---

## 10. G1 MEDIUM / G2 HIGH — KEY ARCHITECTURAL RESULT (MUST-PRESERVE INVARIANT)

These are simultaneously true and MUST remain able to coexist:

- **current audited Workflow shape: MEDIUM portability risk** (many custom nodes across ≥10 repos, partially unreliable registry revision evidence, model hashes absent, ModelPatchLoader extraction gap, subgraph definitions);
- **current audited source execution environment: HIGH reproducibility risk** (floating torch trio, working-tree plugin deployment, uncommitted local core patch, missing model hashes, floating node provenance).

Environment HIGH does NOT contaminate Workflow portability risk or any target's level. Frozen policy constant: `POLICY_ENVIRONMENT_ISOLATION = "environment_reproducibility_never_forces_workflow_or_target_risk"`. Proven end-to-end through the production pipeline (G9 §13) and rendered as two visually distinct surfaces in the UI (G12). A core-only workflow may be LOW while the deployment environment carries HIGH debt.

---

## 11. STATIC SIGNALS — FINAL G6 COVERAGE

All 14 signals always emitted, types enforced, restricted to the frozen name/type table (unknown names rejected; new signals require a rule-version bump):

| Signal | Type | Meaning |
|---|---|---|
| `has_absolute_path` | bool | host-bound filesystem path in functional positions (URL substrings stripped first; Note/MarkdownNote text never scanned) |
| `has_unresolved_node_type` | bool | required class with no usable identity evidence |
| `unresolved_node_count` | int ≥0 | count form of the above |
| `custom_node_count` | int ≥0 | distinct custom classes |
| `custom_repo_count` | int ≥0 | distinct owning repos |
| `custom_node_revision_pinned` | bool | true iff every custom class has `exact` provenance AND a revision |
| `model_ref_basename_only` | bool | all model refs are bare filenames |
| `model_hash_pinned` | bool | 64-hex sha256 per ref (vacuous true when no refs) |
| `model_extraction_gap` | bool | model-like loader input not covered by known extraction mappings |
| `requires_input_asset` | bool | LoadImage/Mask/Video/Audio/VHS_Load family present |
| `has_external_endpoint` | bool | http(s) string in functional executable inputs only |
| `uses_subgraphs` | bool | `definitions.subgraphs` non-empty |
| `exact_roundtrip_proven` | bool | recomputed via `sha256_of_canonical(executable_prompt)` unless overridden |
| `env_bound_registry_leak` | bool | export would include local install-path fields |

G1's numeric shorthand S1–S12 remains AUDIT SHORTHAND ONLY and is NOT part of the public API; the wire uses these descriptive keys.

---

## 12. MODEL EXTRACTION GAP — DELIBERATE DECISION

G9's decision, verified in current source: **`workflow_metadata._MODEL_REF_MAPPINGS` was NOT modified** (workflow_metadata.py:213–223 still covers CheckpointLoader(Simple)/UNETLoader/CLIPLoader/DualCLIPLoader/VAELoader/LoraLoader/LoraLoaderModelOnly/ControlNetLoader — no `ModelPatchLoader` entry) because the exact `ModelPatchLoader` input contract could not be proven from repository source to the lane's certainty bar ("if uncertain: do not").

Instead the gap is represented honestly everywhere:

- unknown loader-like model dependency remains OBSERVABLE (loader-suffixed class with model-extension string input lacking a model-evidence row);
- `model_extraction_gap` signal + medium issue exist in every report path;
- Export emits a deterministic `metadata.export_warnings` entry;
- the unresolved dependency is NEVER silently exported as a guessed model role (no fake checkpoint role/folder in `models[]`).

**Does this mean Phase G is incomplete? NO.** Phase G is about TRUTHFUL portability analysis, not about semantically supporting every third-party loader. The product truthfully diagnoses the gap and refuses to invent false portability evidence — which is exactly the roadmap's explainability requirement. Adding loader mappings is future enhancement work requiring per-loader contract proof, not a closure blocker.

---

## 13. CUSTOM-NODE PROVENANCE QUALITY

Four-level frozen vocabulary: **`exact | declared | inferred | unresolved`**.

Precedence (conservative by construction):

1. explicit row quality field;
2. resolver-state derivation: installed+commit→`declared`; installed without commit→`inferred`; wrong_revision→`declared`; missing+repo→`declared`; else `unresolved`;
3. **aux_id rescue (G9)**: UI-graph `properties.aux_id` (e.g. `"kijai/ComfyUI-KJNodes"`) yields `declared` provenance with repo `https://github.com/<slug>`, revision unknown; host-fallback ComfyUI registry URLs are replaced by aux_id-derived repos when available.

**A non-empty registry `repo_url` alone is NEVER authoritative/exact**, because G1/G2 found discovery fallback noise (registry rows carrying `repo_url: https://github.com/Comfy-Org/ComfyUI` with the ComfyUI commit for unrelated nodes). Nothing current derives `exact` without an enforced pin. Unresolved provenance drives HIGH findings on provisioning targets (cannot bake unpinned).

---

## 14. SOURCE ENVIRONMENT REPRODUCIBILITY — G2 DEBT, DETECTED NOT FIXED

G2's real, current reproducibility findings (recorded separately from workflow risk):

- ComfyUI remote core commit PINNED (`f49bdb655707b97952dcef40e12e5af1f08d2007`, v0.24.0 lineage) — but the LOCAL validation checkout carries an uncommitted ~145-line patch to `comfy/model_management.py` (soft-empty-cache gate) that exists in no ref → local ≠ image soft-cache policy;
- torch/torchvision/torchaudio cu130 stack FLOATING (force-reinstalled latest wheels);
- custom-node working-tree pinning gaps: all production nodes deployed as unversioned working-tree copies; 13 of 22 lack `.git` entirely; commits recorded nowhere/enforced by nothing;
- private plugin (`Parlaxz/comfyui-modal`) deployed from a dirty working tree (124 uncommitted changes on `r42-golden-reconciliation`) — no ref reproduces deployed bytes; its internal output classes appear in compiled workflows;
- model hashes often absent (master manifest `sha256: null` in every observed entry; library hashes sparse);
- CUDA base image referenced by mutable tag, digest unpinned.

**Do NOT claim Phase G fixed those runtime/environment debts.** Actual dependency-environment hardening (pinning torch, committing the patch, recording node commits, populating hashes, pinning digests) is SEPARATE WORK unless a roadmap explicitly required Phase G to mutate the Modal build — it did not.

What Phase G now does: **DETECTS / REPORTS / EXPLAINS**. Six frozen environment codes map G2 findings verbatim into the report's `environment` section: `torch_stack_unpinned` (H), `custom_node_source_unpinned` (H), `plugin_worktree_dirty` (H), `local_core_patch_divergence` (H), `model_hash_unpinned` (M), `base_image_digest_unpinned` (M). Positive facts (e.g. "core pinned") are absence-of-issue, not codes. Unknown facts fabricate nothing; all-unknown → UNKNOWN + explanatory issue. Live-request environment evidence is intentionally cheaper than the G2 forensic audit (only model-hash coverage and node-commit coverage derivable without git subprocesses); the rest stays UNKNOWN rather than guessed.

---

## 15. TARGET READINESS — SIX FROZEN IDS

Sole vocabulary (`TARGET_IDS`, aliases `comfy-cloud`/`comfycloud`/`run_comfy` banned from wire payloads):

```
local · modal · runpod · runcomfy · comfy_cloud · baseten
```

Implemented G7 philosophy per target (pure advisory rules over prepared tri-state evidence; no provider SDKs, no network, no execution):

- **local** — reference/native environment. Core → LOW; missing local installs → HIGH; native-build burden → MEDIUM; unresolved provenance → MEDIUM (explainable, not blocking); self-consistent host paths stay operational locally; missing local models → HIGH.
- **modal** — native current product target with broad dependency control. Python/native/system needs → LOW (image layers solve them); product-internal plugin classes supported; unresolved provenance → MEDIUM (deploy bake lacks a pin); absolute paths HIGH unless product-materialized; models LOW unless explicitly unavailable on volumes.
- **runpod** — portable JSON broadly usable; everything else is image setup. Any custom node → MEDIUM `runpod_image_setup_required`; native/system/CUDA build → HIGH; unresolved source → HIGH; private/gated models → MEDIUM token plumbing; subgraphs → MEDIUM "ship a subgraph-capable frontend". No Dockerfiles generated — advice states what would be required.
- **runcomfy** — strong managed import/auto-setup story. Manager-restorable declared/exact nodes → LOW; others → MEDIUM auto-setup; native deps follow supplied capability input (`supported`→HIGH provisioning, `unsupported`→HIGH blocked, `unknown` default → `runcomfy_native_capability_unknown` + UNKNOWN); exact-pin provenance adds a LOW commit-pinning caveat; private/gated → MEDIUM token attach.
- **comfy_cloud** — largest import-vs-executes gap due to curated node/model environment; fail-honest. Node explicitly off-catalog → HIGH; catalog membership unknown → uncertainty codes + UNKNOWN (never assume support or failure); arbitrary Python install → HIGH when off-catalog known; native/system requirement → HIGH always; off-catalog model → HIGH; curated/core-only graph → LOW.
- **baseten** — capable custom deployment, but the workflow typically gets EMBEDDED INTO A DEPLOYMENT (Truss) rather than submitted as an arbitrary graph-per-request. Every result starts MEDIUM `baseten_deployment_embedding_required`; CUDA build → HIGH; other native/system → MEDIUM; unresolved source → HIGH; private/gated → MEDIUM secrets setup; persistent-storage UNKNOWN surfaced without inflating the level.

**UNKNOWN provider capability → explicit Unknown, never guessed** (`target_capability_unknown`, shared canonical object). Risk precedence within a target: high > unknown > medium > low (a known HIGH blocker wins so actionable findings are never masked; uncertainty remains visible via codes).

Target results depend on Workflow characteristics — they are NOT a universal provider ranking. The G3 golden characteristic matrix (core/popular-custom/native-build/absolute-path/private-model × six targets) is encoded deterministically and asserted literally in tests.

No six execution engines were added. Target rules are pure advisory analysis.

---

## 16. PROVIDER LIMITATIONS — IMPORTANT FACTS (G3/G7)

| Target | Key fact |
|---|---|
| Local | reference/native environment; baseline where both import and execute trivially hold |
| Modal | native current product target (origin environment); broad dependency control |
| RunPod | same JSON accepted by worker endpoints; custom Docker/image setup usually required; network volume explicitly not for nodes; timeout/volume ceilings UNKNOWN |
| RunComfy | strong managed import/auto-setup (parses graph, installs missing nodes/models); exact commit/native-dependency controls partly UNKNOWN; Cloud Save snapshotting |
| Comfy Cloud | import broadly compatible (OSS `/api/prompt`), but execution restricted to curated supported node list + platform-managed models; no arbitrary package/native install — the largest import-vs-executes gap of the six |
| Baseten | capable custom environment (Truss: build_commands/requirements/system_packages/secrets); workflow typically embedded into a deployment rather than arbitrary graph-per-request; persistent-storage options UNKNOWN |

Preserved explicit unknowns (never guessed): RunPod timeout caps/volume ceilings; RunComfy commit pinning + native/apt support + deployment timeouts; Comfy Cloud catalog breadth/wall-clock/HF-import timeline; Baseten storage/timeouts/cold-start envelope; region-dependent GPU availability. When provider facts refresh, they enter exclusively as tri-state evidence fields — no rule edits required.

---

## 17. CACHE — G10/G11 ARCHITECTURE

**Sidecar:** `.studio_portability_reports.json`, created by `register_workflow_routes` beside the other Studio stores (`Path(node_dir) / DEFAULT_SIDECAR_FILENAME`). Array-rooted with exactly one envelope `{cache_format_version: 1, reports: {<version_id>: {report, stamp}}}` — adapts around the list-rooted `StudioJsonStore` reader WITHOUT modifying it, inheriting RLock thread safety, atomic tmp+fsync+`os.replace` writes, UTF-8 BOM tolerance, missing-file→empty convention. `cache_format_version` is INTERNAL layout version, deliberately distinct from `manifest_version`/`rule_version`; unknown values fail open to invalid. **Derived only** — nothing added to the four domain collections; History SQLite unused.

**Eight invalidation fields (exact, frozen):**

```
workflow_version_id, graph_hash, dependency_metadata_hash,
model_library_generation, custom_node_registry_generation,
rule_version, manifest_version, comfyui_version
```

Comparison delegated verbatim to `portability_contract.invalidation_mismatches` — no reimplemented comparator exists.

Semantics (all tested):

- **null ALWAYS stale** — any null on EITHER side stales, including null-vs-null; null is never "probably unchanged";
- every concrete single-field change stales;
- completely unknowable current stamp stales on all eight fields;
- **no TTL** — `analyzed_at` is NOT an invalidation criterion; a 2020-dated report with identical stamps hits; staleness is evidence/version-based only;
- rule-version/manifest-version bumps stale old reports; nothing auto-rewrites them;
- generation tokens are opaque caller-supplied comparables; the cache never inspects stores to manufacture them.

**States:** `hit` (row internally consistent + stamp match → validated copy marked stale=false) / `miss` (unknown id/missing file/empty) / `stale` (copy of old report marked stale=true + `mismatched_fields`) / `invalid` (corrupt/incompatible; poisoned payload never returned).

**Corruption FAILS OPEN** (never crashes the product, never yields an authoritative bad report): malformed JSON/wrong root/multiple envelopes/unknown format/bad rows → invalid or miss with diagnostics; reads never repair; writes may regenerate from scratch because the file is derived and regenerable.

**Atomic writes & thread safety:** all mutations through `StudioJsonStore.update()`/`write_atomic()`; verified with `os.replace` patched to raise (error surfaced, temp cleaned, previous content intact) and 8-thread barrier contention tests. Cross-process semantics truthfully limited: last COMPLETE atomic writer wins; readers can never observe partial JSON. Acceptable precisely because the cache is derived.

**PUT contract:** writes nothing unless the report passes full contract validation, the stamp is a complete valid 8-field stamp, and stamp.workflow_version_id == report.version_id == row key with matching graph_hash. Rejections carry ALL reasons and leave the sidecar unchanged.

**Cache never gates execution/import** — no runnable/authorize/can_execute API exists; imports/exports/run-gating never read it (neutrality proven by sidecar-snapshot tests).

---

## 18. PORTABILITY GET — FINAL ENDPOINT BEHAVIOR

`GET /comfymodal/studio/workflows/versions/{version_id}/portability`

1. read persisted Version (404 if unknown — cache untouched);
2. build current 8-field stamp (`PortabilityService.current_invalidation_stamp`) — all eight concrete wherever authoritative evidence exists:
   - `workflow_version_id` ← persisted immutable Version record (never browser input);
   - `graph_hash` ← persisted Version hash;
   - `dependency_metadata_hash` ← canonical SHA-256 of persisted dependency_metadata (None only if absent → conservative stale);
   - `model_library_generation` ← SHA-256 token over normalized portability-relevant Model Library records (id/folder/filename/hash/size/sorted source_urls/provider/revision/is_placeholder/install status; NO local_path, timestamps, bytes, or scans);
   - `custom_node_registry_generation` ← SHA-256 token over registry rows (name/repo_url/installed_commit/declared version/provenance/sorted classes; NO tree walks/git/mtimes);
   - `rule_version` ← landed contract constant; `manifest_version` ← landed manifest schema constant; `comfyui_version` ← guarded `comfyui_version.__version__` → `comfy.__version__` chain (never git, never remote);
3. `cache.get(version_id, stamp)`:
   - **hit** → serve cached validated view (`stale=false`), ZERO analysis — the resolver is not even consulted (proven by injected analyzer spy);
   - **miss/stale/invalid** → synchronous live recompute through the unchanged G9 pipeline (G6 engine + G7 rules over adapted evidence), stamped with the CURRENT stamp, `cache.put()` refresh, **fresh truth returned** — a stale LOW is never served as current;
4. response `{status, portability}` plus additive `portability_cache` metadata `{state, recomputed, mismatched_fields, diagnostics}`.

**Cache failure fails open to live analysis**: crashing get/put or corrupt sidecar still yields 200 + valid fresh report; domain stores byte-identical throughout; a corrupt sidecar can never turn a valid Workflow into a 500. No force-refresh parameter exists (identical evidence ⇒ deterministic hit; changed evidence ⇒ automatic stale).

---

## 19. WORKFLOW LIST ENRICHMENT — FROZEN CHIP CONTRACT

Each Workflow list row AND the Workflow detail payload carry:

```json
"portability_summary": {"version_id": "wv_...", "risk_level": "low|medium|high|unknown",
                        "issue_count": <int>, "stale": true|false|null, "analyzed_at": "<iso|null>"}
```

or `null` when no usable cached row exists for the latest Version.

States:

- `null` summary → **Not analyzed** (never rendered as LOW/green);
- `stale=false` → verified/current (checked against a cheaply constructed current stamp);
- `stale=true` → checked and outdated ("Stale — recheck portability"; marker never dropped);
- `stale=null` → freshness unchecked ("Needs check") — e.g. dangling latest pointer with a cached row; never pretended current.

**The Workflow list performs ZERO live risk/resolver analysis** — proven by test: after list render, analyzer spy count == 0, instrumented resolver count == 0, sidecar bytes unchanged. This prevents N×analysis cost. Implementation (`workflow_portability_summaries`) reads latest versions in one store pass and calls `cache.summaries(...)`; it cannot analyze and cannot write; the whole helper fails open to all-null. Five-workflow independence test covers current-LOW/current-HIGH/stale-MEDIUM/never-analyzed/unchecked with no cross-reuse; same-graph-hash/different-version-id is never reused.

Import/export neutrality: Export and dry-run Import leave the sidecar byte-identical; committed Import performs no eager fill (new Version starts summary-null; first explicit GET computes+caches).

---

## 20. FRONTEND PRODUCT — G12 FINAL USER SURFACE

**Workflows owns Portability.** No other surface has an ownership claim.

- **List cards + detail header:** native `<button>` risk chips (keyboard operable) with text labels + `title`/`aria-label` — never color-only. Chip states: plain risk label + count (current); "… · Stale" (stale=true); "… · Needs check" (stale=null); neutral "Not analyzed" (null). Click opens the workflow detail / panel — a colored badge with no reachable explanation is treated as a defect.
- **Version-scoped Portability panel:** shows exact `v<N> · <version_id>` context, abbreviated graph hash, analyzed_at, stale-state sentence, counts by severity, rule_version; global issue rows with severity text + verbatim backend fix hints (bounded deep-link button "View in Model Library" only for models/custom-node subjects; otherwise fix_hint stays text); Check/Recheck button calling exactly the portability GET (in-flight guard dedupes rapid clicks; pending disables only that control with aria-busy; success refetches summary so chips update; failure shows bounded truthful message, keeps prior report labeled "PRIOR report after a failed recheck", restores focus, never raises unhandled rejections). Version switch resets the panel to Not-analyzed for the corresponding report only.
- **Target matrix:** exactly six rows in frozen order, rendered ONLY from the report (risk badge text, reasons resolved through the global issues pool by code, advice lines verbatim). Unknown targets stay Unknown with explanation "Capability unknown — no defensible determination available."
- **Source-environment reproducibility:** distinct bordered section titled "Source environment reproducibility" with the one-sentence explainer ("moving this WorkflowVersion elsewhere" vs "how exactly the CURRENT source runtime itself can be reproduced") and its own risk badge.
- **No browser-side risk engine exists** — the browser renders backend truth only; the fake backend seeds predetermined payloads (no rule logic).

---

## 21. MEDIUM + HIGH UX — PINNED RECONCILIATION

When a workflow is Medium portability risk AND the source environment is High reproducibility risk, BOTH render simultaneously:

- the main chip stays **Medium** (workflow dimension);
- Environment High appears ONLY in its distinct bordered section with its own badge — it never recolors the workflow chip or any target row (G5 `POLICY_ENVIRONMENT_ISOLATION`, enforced in UI and pinned by unit/browser tests including the checklist generator's coexistence case).

---

## 22. MANIFEST EXPORT UX

Detail-panel action **Export workflow** opens a small confirm popover:

- checkbox **Include workflow presets** default OFF;
- confirm calls `GET /versions/{id}/export?include_presets=0|1`;
- response bytes download via Blob anchor using the server's Content-Disposition filename (deterministic fallback if header missing);
- 404/409/network failures render bounded truthful messages — the 409 explains export was blocked to avoid embedding credential-like values, never echoes values, never suggests disabling security — and restore focus to the Export button;
- **no Workflow mutation and no run request issued** (asserted by write-tracker and request-pattern assertions);
- double-click dedupe holds at the app layer (server-side hit-count assertions are differential because Chromium internally re-requests attachment responses for its download manager — invisible to page events).

**Do not conflate with Phase-F History Download/Export:** History Browser Download / configured-folder Export move generated ASSETS; Workflow Manifest Export moves the workflow definition. Different routes, different artifacts, different surfaces.

---

## 23. MANIFEST IMPORT UX

Library-header entry point **Import workflow manifest** opens a dialog with a JSON file picker (no ZIP). Mandatory flow: file → exactly ONE `POST import-manifest?dry_run=1` → preview → explicit `Import workflow` → `POST ?dry_run=0` with body = manifest + `import_presets`/`apply_default_preset`.

- Preview keeps FOUR truths separate: Manifest Valid/Invalid (+version); Structural readiness; Dependency availability ("Import is allowed, but the Workflow may not run until dependencies are resolved. Nothing is installed automatically."); Portability risk. Plus proposed name, existing name matches, will-create counts, ALL returned issues readable, security findings.
- Missing dependencies are importable; no install; no fetch; no auto-run.
- Explicit preset choices: `Import workflow presets` defaults OFF (disabled when manifest has none); `Apply imported default preset` defaults OFF, disabled unless presets imported AND preview reports a default candidate; unchecking presets clears apply-default; commit transmits the exact chosen pair (fake logs prove `{false,false}` defaults and `{true,true}` explicit selections).
- Invalid previews disable commit entirely; malformed JSON is sent verbatim so the backend stays the authority; >10 MiB client precheck blocks the send locally (backend 413 remains authoritative).
- Commit failure keeps the preview, shows reason + "Nothing was created. You can retry.", refocuses the commit button; retry succeeds once the injected one-shot failure is disarmed (atomic backend commit means nothing partial exists).
- Success shows created Workflow/Version #1/Mapping/preset count plus a small provenance area (foreign ids labeled informational-only, never used for navigation), then opens the new local Workflow — never auto-running it.

---

## 24. CHECKLIST — DERIVED ADVICE, NOT AUTHORITY

`web/studio-portability-checklist.js::buildPortabilityChecklist` derives a deterministic Markdown document from the backend report. Stable section order:

header (workflow + version + "NOT the canonical workflow manifest" note) → **Summary** (risk, issue count, report state) → **Issue counts** (high/medium/low) → **Issues** (severity-tagged rows with verbatim fix hints) → **Dependency notes** (models/custom_nodes-subject issues + unresolved count; only facts present in the report) → **Target readiness** (six targets in frozen order with advice) → **Source environment reproducibility** (separate dimension + note) → **Import expectations** (creates NEW Workflow/Version #1/Mapping/optional presets; missing deps don't block; nothing installed/fetched/executed) → **Provenance** (version id, abbreviated graph hash, rule_version, analyzed_at).

Downloads as `<workflow>-v<N>-portability-checklist.md` via the reused `sanitizeFilenamePart` helper. Unit-pinned: byte-determinism, section order, six target names/order, fix hints verbatim, Medium-workflow/High-environment coexistence, no `undefined`/object dumps, dangerous filename sanitization, no invented dependency facts, no secrets.

It is **derived advice**; the manifest remains the canonical artifact of record.

---

## 25. FOLDER-STRUCTURE REQUIREMENT — RECONCILIATION

Original roadmap asked for folder-structure guidance. Final state:

- **Implemented naming convention:** deterministic export filename `<sanitized-name>-v<version_number>-<graph_hash[:8]>.workflow.json` (`suggest_export_filename`) and checklist filename builder — the file-naming half of the guidance is product-real.
- **Advisory hierarchy convention:** G4 §11 recorded `workflows/<folder>/<name>/workflow.v<N>.workflow.json` + `checklist.md` as the recommended layout, mapping manifest `workflow.display.name` + `folder` field, with models placed into standard ComfyUI buckets via the manifest's `folder` field (resolver `_ROLE_TO_FOLDER` semantics). This convention lives in the G4 audit document (historical evidence, intentionally not edited) and now in this handoff.
- **Landed checklist:** intentionally does NOT enforce or create folders and does not carry a dedicated folder-layout section. Per the closure criteria this is acceptable — Phase G required GUIDANCE, not filesystem mutation. Guidance that DID land in-product: fix hints ("Replace host-bound paths with ComfyUI folder-relative basenames", "Ship referenced assets alongside the workflow into the target input folder", "Populate sha256 … pin hashes at export"), the manifest's `models[].folder` bucket references, and the checklist's dependency/import-expectations sections.
- **Documentation-only correction applied HERE** (per reconciliation policy — historical reports not rewritten): the authoritative advisory convention is `workflows/<folder>/<name>/workflow.v<N>.workflow.json`; it is advice a user may follow when storing exported manifests client-side; the product neither enforces nor mutates any on-disk layout. No further correction needed; no filesystem organizer was added (explicitly out of scope for G13).

---

## 26. DEPENDENCY-PINNING GUIDANCE — VERIFIED

Final analysis/checklist communicates WHY risk exists and WHAT kind of pin would improve it:

- model SHA presence/absence → `model_hash_unpinned` issue, fix hint "Populate sha256 in the model library and pin hashes at export"; signal `model_hash_pinned`;
- custom-node revision quality → `custom_node_unpinned` issue, fix hint "Pin exact trusted repo revisions for each custom node"; signal `custom_node_revision_pinned`; provenance quality (exact/declared/inferred/unresolved) surfaced per class;
- environment pinning findings → the six frozen environment codes (§14) rendered in the dedicated section and checklist;
- path hygiene → `local_path_reference` fix hint "Replace host-bound paths with ComfyUI folder-relative basenames".

Phase G does NOT automatically rewrite or pin the current runtime environment — pinning is captured in exported manifests (reference records), never retro-mutated into stored Versions. This satisfies the roadmap requirement as guidance.

---

## 27. ROLLBACK / RECOVERY GUIDANCE — VERIFIED

Final user-facing/doc architecture:

- **Export:** read-only, byte-proven zero mutation — no rollback needed.
- **Import preview:** zero-write (byte-proven dry run).
- **Failed commit:** atomic + compensated — no partial graph in normal product state (§7); UI wording "Nothing was created. You can retry."
- **Successful import:** creates a NEW independent local Workflow (fresh ids, version numbering restarts at 1), leaving existing Workflows untouched; rollback of a successful import = simply ignoring/deleting that new workflow's records — no public DELETE endpoint exists or is required for Phase G (§8).
- **Cross-provider:** the manifest `.workflow.json` and checklist `.md` are retained client-side (browser downloads) as the return path to the original environment; every target's restore path starts from re-submitting retained JSON (G3 §10 matrix documents per-environment restore semantics).

No public DELETE was invented. Guidance exists in the checklist's Import expectations section and the import dialog's failure copy.

---

## 28. OPTIONAL MODEL-LIBRARY DEEP LINKS — CLASSIFIED

G12 implemented bounded deep-linking: issue rows whose subject is models/custom_nodes get a "View in Model Library" button targeting the reliable sub-view surface. Targeting SPECIFIC Model Library entries (and custom-node deep links beyond that) is:

**B. UX enhancement** — not a required Phase-G capability. No roadmap artifact requires clickable cross-panel navigation. Current issue messages/fix hints already explain missing model/node problems in text. Phase G is NOT left open for this; not implemented in G13.

---

## 29. TEST CORPUS — G8

`tests/fixtures/portability/` — measured current contents: **51 fixture files** (18 scenario descriptors + 18 manifest goldens + 8 evidence files + 3 expected files + 2 invalidation files + 1 raw + 1 README), organized as `scenarios/ manifests/ evidence/ expected/ invalidation/ raw/`. (G8's report said "50-file" at authoring time; the directory currently measures 51 including README.md — counted here so future agents trust their own `ls`.)

**18 frozen scenario ids** (`portability_fixtures.SCENARIO_IDS`):

`core_clean, custom_exact, custom_unpinned, unresolved_node, model_hash_missing, model_extraction_gap, input_asset_required, absolute_path, external_endpoint, subgraph_frontend, private_model, native_build_dependency, manifest_not_ready, credential_like_value, popular_custom, current_corpus_shape, environment_repro_high, unknown_target_capability`

Coverage map: clean core; custom provenance (exact/declared/inferred-inside-corpus-shape/unresolved); unresolved nodes; model hashes; extraction gap; external assets; paths (with inert-note false-positive resistance); endpoints (functional vs note-text); subgraphs; private models; native builds; manifest failures (not-ready vs JSON-invalid kept distinct); credentials (placeholder-only, denylist-scanned); environment HIGH (all six env codes); current-corpus shape (the shared MEDIUM+HIGH coexistence proof); provider capability unknowns; invalidation (9 stamps over the 8-field contract).

Role: **stable cross-lane evidence** — every manifest golden is built through the production `build_manifest` (valid by construction), pinned by canonical-hash goldens twice (expected file + descriptor), consumed read-only by G6 (signals/issues reconciliation), G7 (target matrix), G9 (preview smoke + corpus reconciliation through the REAL pipeline), G10 (stamp semantics through the real cache), G11 (fixture reconciliation through the route shell), and G12 (fake parity shapes). Redaction discipline: synthetic ids, `example.invalid` URLs, fake constants, no real ids/names/tokens anywhere.

---

## 30. SECURITY — FINAL CONTROLS

Route/module layer (all tested):

- single JSON artifact — **no ZIP extraction exists anywhere** (zip-slip/bomb class eliminated by construction);
- **10 MiB import cap** (`MAX_IMPORT_BODY_BYTES`; content-length pre-check AND post-read check → 413);
- JSON depth/element guard before parse (`MAX_JSON_DEPTH=64`, `MAX_JSON_ELEMENTS=200000`);
- NaN/Infinity refused (parse_constant rejector + `allow_nan=False` hashing fails closed);
- manifest filenames are DATA — never joined onto filesystem paths during import/export;
- **no install / fetch / shell on Import** — zero pip/git/Manager/network operations; installation stays behind the existing explicit approval flows;
- dependency URLs inert — rendered as text, never auto-fetched;
- **credential-like Export blocked**: artifact-wide scan (`detect_manifest_credential_shapes`: executable inputs, api_prompt sub-objects, UI-graph widget input names; Note nodes skipped) refuses download with 409 `credential_like_value_detected` — zero mutation, values never echoed;
- import reports the same finding deterministically (issues + security_findings, key names only) WITHOUT blocking (user may import their own export) — per frozen G5 contract;
- no secret value echoed anywhere (messages/evidence bounded; samples sorted/truncated);
- no local install paths exported (`local_path`/`install_path` never leave);
- the browser never auto-installs anything (specs assert ZERO requests matching `/studio/run`, `install-request`, model-download, or custom-node-install patterns across whole import/export/check flows; frontend reads the selected file as text only).

Pure-module guarantees (manifest codec, contract, risk engine, target rules, cache): stdlib-only imports, AST-allowlist-pinned purity, no I/O/network/exec (risk engine proven by patching `open`/`socket`/`urlopen` to raise).

---

## 31. ENDPOINT INVENTORY (FROZEN)

| Route | Method | Semantics |
|---|---|---|
| `/comfymodal/studio/workflows/versions/{version_id}/export` | GET | manifest-v1 download; `include_presets` default false; read-only; deterministic filename; 409 credential refusal |
| `/comfymodal/studio/workflows/import-manifest` | POST | dry_run default true; preview/commit; `import_presets`/`apply_default_preset` body policies; atomic commit |
| `/comfymodal/studio/workflows/versions/{version_id}/portability` | GET | G5 report via G10 cache; hit=zero analysis; miss/stale/invalid=recompute+put; fail-open; additive `portability_cache` metadata |
| `/comfymodal/studio/workflows` (list) + detail | GET | rows enriched with derived-only `portability_summary` (five-key shape or null); zero live analysis |
| `/comfymodal/studio/workflows/import` | POST | PRE-EXISTING raw-capture import (unchanged; distinct from manifest import) |

No second "compatibility"-named portability endpoint exists (asserted by test). Naming collision with model-compatibility annotations (`GET/PATCH /workflows/versions/{id}/compatibility`) is avoided by design: portability vocabulary is "portability"/"target readiness".

---

## 32. PERSISTENCE / CACHE INVENTORY

| Store | Role |
|---|---|
| `.studio_workflows.json` / `.studio_workflow_versions.json` / `.studio_workflow_mappings.json` / `.studio_workflow_presets.json` | source of truth (untouched shapes; versions write-once; mappings insert-once) |
| `.studio_model_library.json` / `.studio_custom_nodes.json` | dependency evidence authorities (local_path/install_path never exported) |
| `.studio_portability_reports.json` | NEW derived-only report cache sidecar (regenerable; never authority; never gates anything) |
| History V2 SQLite | untouched by Phase G |

---

## 33. REJECTED APPROACHES (with rationale)

| Rejected alternative | Rationale |
|---|---|
| `PortableWorkflow` duplicate entity / `portability` column as graph authority | duplicates graph authority, goes stale against immutable Versions, contradicts write-once store design |
| Second graph store / second graph authority | one canonical graph identity per version; forks breed divergence |
| Portable ExecutionPlan | plans embed environment/runtime specifics (GPU, base64 inputs, deployment identity); serializing them creates a second executable truth; replay already owns plan immutability |
| ZIP v1 package artifact | archive-extraction attack surface with no offsetting need; heavy bundling unwanted by default; single JSON suffices |
| Model-byte bundling | huge files; models are reference records (filename/sha256/source_urls) |
| Custom-node-code bundling | code travels via repo_url+revision references; embedding code is a security and size hazard |
| Auto-install on Import | import must stay inspect-before-execute; installs belong behind explicit approval flows |
| Browser-side risk engine | risk must be server-computed, contract-validated, cache-consistent; client logic would fork truth |
| Six provider execution engines | targets are advisory analysis; providers already accept graph JSON or have their own deployment models |
| Guessing UNKNOWN provider capability | fabricating support/failure destroys trust; tri-state evidence keeps unknowns honest |
| Cache as execution/import gate | cache is derived opinion; runnability stays governed by live derive_version_state |
| TTL cache freshness | staleness must be evidence-based (stamps), not time-based; TTL would serve stale truth or thrash |
| Environment HIGH contaminating Workflow/target risk | different dimensions; contamination would mislabel portable workflows (POLICY_ENVIRONMENT_ISOLATION) |
| Silent default-preset import | mutable preset state must never apply without explicit user choice |
| Partial import + manual JSON recovery (G4 §11.4 suggestion) | superseded by hard atomicity requirement; "user can edit JSON manually" is unacceptable |
| Fake model role for unknown loader (ModelPatchLoader) | inventing checkpoint role/folder would fabricate portability evidence; honest gap reporting instead |
| Local-path export leakage (`local_path`/`install_path`) | environment-bound machine details; leak surface + zero portability value |
| Uppercase wire risk values (G4 draft) | frozen lowercase to match house style; UI may render uppercase labels |
| S1–S12 numeric labels as public API | audit shorthand only; de-numbered descriptive keys are the wire contract |
| Force-refresh parameter on portability GET | identical evidence ⇒ deterministic hit; changed evidence ⇒ automatic stale; a refresh knob invites cache-thrash semantics |
| Reusing model-"compatibility" endpoints/naming for portability | terminology collision documented in G4; distinct vocabularies enforced |

---

## 34. DEFECT / FINDING LEDGER (FOUND → RESOLVED OR CLASSIFIED)

| # | Finding | Found by | Resolution |
|---|---|---|---|
| 1 | Registry `repo_url` host-fallback noise (ComfyUI URL on unrelated nodes) → revision evidence unreliable | G1/G2 | provenance vocabulary demotes repo_url-alone to non-exact; aux_id rescue replaces fallback repos when available |
| 2 | ModelPatchLoader model invisible to dependency_metadata/resolver | G1 | deliberate non-fix: `model_extraction_gap` signal+issue+export warning; no fake role (§12) |
| 3 | Model hashes largely absent → cannot pin model bytes | G1/G2 | detected/reported (`model_hash_unpinned`, env code); population is separate hardening work |
| 4 | Local core patch divergence (uncommitted comfy/model_management.py) | G2 | detected/reported (`local_core_patch_divergence`); not fixed in G |
| 5 | Floating torch trio / base-image tag / apt floats | G2 | detected/reported (`torch_stack_unpinned`, `base_image_digest_unpinned`); hardening deferred |
| 6 | Plugin working-tree deployment (124 dirty files) unreproducible from any ref | G2 | detected/reported (`plugin_worktree_dirty`); deployment hygiene deferred |
| 7 | Custom-node commits recorded nowhere (13/22 no .git) | G2 | detected/reported (`custom_node_source_unpinned`); bake-time recording deferred |
| 8 | No workflow export/import-manifest routes existed | G1/G4 | G9 wired both end-to-end |
| 9 | Import-failure partial-state risk (no delete endpoint to clean up) | G4 | SOLVED: `commit_import_transaction` + compensation; byte-equal restoration proven at all eight failure points |
| 10 | No public Workflow delete endpoint | G4 | reclassified: NOT an import-atomicity defect post-#9; not a roadmap requirement; later lifecycle capability (§8) |
| 11 | List enrichment N×analysis cost risk | G4 | SOLVED: derived cache + zero-analysis list proof (G11) |
| 12 | "compatibility" terminology collision | G4 | distinct portability vocabulary enforced; duplicate `getVersionCompatibility` definitions also cleaned up (verified gone in G12) |
| 13 | G4 wire example used uppercase risk values | G5 | frozen lowercase; UI renders labels freely |
| 14 | G4 manual-JSON-cleanup-after-failed-import suggestion | G5 | superseded by atomicity requirement (see #9) |
| 15 | Subgraphs risk over-classification | G5/G6 | `POLICY_SUBGRAPHS = target_sensitive_not_global_blocker`; LOW global finding; per-target severity |
| 16 | Absolute paths as universal HIGH | G5/G7 | `POLICY_ABSOLUTE_PATHS = global_finding_with_target_severity_override`; local self-consistent paths stay operational; remote targets HIGH via shared blocker object |
| 17 | G11 wrapper 185/190 fake failures | G11 | concurrent-lane transient (G12's in-flight untracked spec); superseded by G12 convergence 192/192; NOT current failures |
| 18 | Interim "189/189" fake count in coordination notes vs G12's written 192/192 | G13 | direct re-measurement: 192/192; arithmetic reconciled (176 baseline + 16 final spec tests); §1 chronology records it |
| 19 | Folder-hierarchy advisory absent from landed checklist | G13 audit | documentation-only reconciliation recorded in §25; acceptable (guidance-not-enforcement); no code change |
| 20 | G8 report says "50-file" corpus; directory measures 51 | G13 audit | counted and recorded (README included); harmless bookkeeping delta, fixtures themselves frozen |

---

## 35. TESTS / COUNTS HISTORY

Per-lane focused evidence (point-in-time, all green at landing): G5 contract 32/32 · G6 risk engine 28/28 · G7 target rules 33/33 · G8 fixtures 35/35 · G9 backend 45/45 + roundtrip 4/4 · G10 cache 40/40 · G11 integration 33/33 · manifest codec 21/21 · workflow domain 39/39 · workflow routes 19/19 · DependencyResolver 11/11 · route registry 298/298 (post-G11) · G12: 16/16 new browser spec + extended workflow-run unit 12 sections + focused 47/47.

Runner registration (G11): `STUDIO_PY_MODULES` += risk_engine, backend, roundtrip, cache_integration; `PYTEST_STYLE_FILES` += target_rules, fixtures, cache. No file registered twice; standalone execution retained.

**Authoritative closure numbers (re-measured by G13): Python 1991/1991 · Node units 21/21 files · Fake Playwright 192/192 — ALL STUDIO LANES GREEN.**

---

## 36. FINAL GAP CLASSIFICATION

Status legend: IMPLEMENTED / ADVICE-ONLY (deliberate Phase-G architecture) / DEFERRED (explicitly later work). "Phase-G blocker?" is judged strictly against the original roadmap.

| Item | Status | Phase-G blocker? | Destination |
|---|---|---|---|
| Public Workflow deletion | DEFERRED | NO — never a roadmap requirement; import atomicity removed the original motivation | Phase H or later product lifecycle |
| Model Library deep links (specific-entry targeting) | DEFERRED (UX enhancement) | NO — text fix hints already explain problems | Future UX polish |
| Custom-node deep links (beyond current bounded button) | DEFERRED (UX enhancement) | NO | Future UX polish |
| Actual source-environment pin hardening (torch pins, patch commit, node-commit recording, digest pin) | DEFERRED | NO — roadmap required reproducibility UNDERSTANDING/reporting, not mutating the Modal build; G detects/reports/explains | Separate infrastructure work |
| Model SHA population | DEFERRED | NO — detection/guidance shipped (`model_hash_unpinned` + fix hint); population needs real hashing runs | Separate model-library work |
| ModelPatchLoader extraction mapping | DEFERRED | NO — truthful gap diagnosis satisfies explainability; mapping requires per-loader contract proof (§12) | Future enhancement w/ proof |
| Provider capability data refresh (Cloud catalog, RunComfy native, Baseten storage) | DEFERRED | NO — tri-state evidence design accepts refresh without rule edits | Future evidence updater |
| Provider deployment automation (Dockerfile/Truss generation) | DEFERRED | NO — G3/G7 explicitly advice-only; no engines built | Future, if product wants |
| Real provider smoke tests (live import/execute per target) | DEFERRED | NO — Phase G is deterministic/offline by constraint; live validation never in G scope | Later live-validation campaign |
| Bundled input assets | DEFERRED | NO — assets travel as reference records by architecture; bundling rejected | Rejected approach / future separate download if ever needed |
| ZIP package | REJECTED | NO — single-JSON artifact is the frozen architecture | None (unless a future contract introduces it) |
| Automatic dependency installer | REJECTED for import | NO — inspect-before-execute is frozen | Existing explicit install-request flows remain the only path |
| Portability report cross-tab sync | DEFERRED (UX nicety) | NO — reload/refetch reflects truth; no storage-event listeners existed before either | Future polish |
| Folder-structure guidance | ADVICE-ONLY (landed: naming convention + fix hints + manifest folder fields; hierarchy convention documented in G4 §11 + §25 here) | NO — guidance existed; enforcement never required | Documented; optional checklist section someday |
| Dependency-pinning guidance | IMPLEMENTED (advice form) | NO | — |
| Rollback/recovery guidance | IMPLEMENTED (architecture + checklist + dialog copy) | NO | — |
| Import/export checklist | IMPLEMENTED | NO | — |
| Explainability | IMPLEMENTED | NO | — |
| Exact JSON portability | IMPLEMENTED (proven) | NO | — |
| Custom-node/model dependency understanding | IMPLEMENTED | NO | — |
| Runtime/platform restriction analysis | IMPLEMENTED (advisory, six targets) | NO | — |
| Reproducibility under dependency/ComfyUI changes | IMPLEMENTED as DETECT/REPORT (invalidation stamps + environment section) | NO | — |
| Per-workflow LOW/MEDIUM/HIGH risk | IMPLEMENTED (four-state) | NO | — |

No open item qualifies as a Phase-G blocker under the original roadmap.

---

## 37. MUST-PRESERVE INVARIANTS

Violating any of these is a regression even where no test catches it directly.

1. **WorkflowVersion is the portability analysis unit** — reports/cache/export key on `workflow_version_id`.
2. **One graph authority** — no PortableWorkflow entity, no second graph store, no portability column as authority.
3. **Manifest v1 is the sole portability artifact** — one JSON file; checklist is derived advice, never authority.
4. **ExecutionPlan is not a portability authority** — never exported/serialized as portability payload.
5. **Exact persisted graph/API JSON preserved** — export/import round-trips canonically byte-equal; no normalization/rewriting/stripping.
6. **Foreign ids are provenance only** — import mints fresh local ids; foreign ids never navigate or authorize.
7. **Import dry-run precedes commit** — default dry_run=true; no bypass path in UI or API flow.
8. **Committed import is atomic** — staged validation, workflow-row-last commit point, compensation restores byte-equal collections.
9. **Missing dependencies may import but never bypass run gating** — runnability stays governed by live derive_version_state/DependencyResolver.
10. **No auto-install/fetch/shell during import or export** — ever.
11. **Workflow risk ≠ target readiness** — separate dimensions, separate payloads.
12. **Workflow risk ≠ environment reproducibility** — POLICY_ENVIRONMENT_ISOLATION; environment never forces workflow/target levels.
13. **UNKNOWN never becomes LOW** — in verdicts, chips, targets, and environment.
14. **Target rules use the six frozen ids** — `local/modal/runpod/runcomfy/comfy_cloud/baseten`; aliases banned from wire.
15. **Cache is derived-only** — regenerable; never authority; never gates execution/import.
16. **Cache invalidation is evidence-based, not TTL** — stamps only; analyzed_at never an invalidation criterion.
17. **Null invalidation value never produces a valid hit** — null-vs-null included.
18. **The Workflow list never performs live portability analysis** — chips come from the cache or are null.
19. **The browser never computes risk** — it renders backend truth; fake backend seeds payloads, no rule logic.
20. **Manifest/checklist distinction maintained** — checklist self-labels as non-canonical.
21. **Provider-specific concerns never create provider-specific Workflow copies** — targets are advice rows over the one canonical version.
22. **Secrets and local install paths are never exported** — credential-shaped export refuses closed; `local_path`/`install_path` never leave.
23. **Graph identity = canonical hash of the executable API prompt** — UI-only capture changes with identical executable prompt may dedupe; intentional, not a bug.
24. **Unknown facts stay UNKNOWN** — provider capabilities, env facts, provenance: never guessed into support/failure/exactness.
25. **Issue rendering has a single authority** — all issue objects live once in the global pool; targets reference by code; duplication forbidden.
26. **Stale results are never presented as current** — stale views are copies marked stale; detail GET recomputes before responding; list marks stale/null distinctly.
27. **Cache corruption fails open** — a corrupt sidecar can never 500 a valid Workflow or yield an authoritative bad report.
28. **Portability vocabulary stays distinct from model-"compatibility"** — no shared endpoints, no shared naming.

---

## 38. PHASE H HANDOFF — WHAT H MAY SAFELY ASSUME

Phase H is **Studio Consolidation**. It may assume:

1. **Workflows is the canonical portability surface.** List chips, detail header chip, version-scoped panel, Export popover, Import dialog, checklist download all live there; no other surface hosts portability state.
2. **Portability routes/contracts are stable and frozen:** the three version-scoped routes (export / import-manifest / portability GET), the five-key `portability_summary` shape, the `{status, portability, portability_cache}` response envelope, lowercase four-state risk vocabulary, six target ids, issue/reference-by-code model, `rule_version = "portability-rules-v1"`.
3. **Old "compatibility" naming remains distinct** — model-compatibility annotations (`/workflows/versions/{id}/compatibility`) are a different feature; do not merge, rename across, or unify them with portability during consolidation.
4. **Manifest import/export must survive consolidation intact** — exact round-trip equality, dry-run-first flow, atomic commit, credential refusal, filename conventions are regression-guarded; treat any behavioral drift as a defect.
5. **WorkflowVersion identity/immutability must survive** — write-once versions, insert-once mappings, graph-hash identity rule (executable prompt), and the import transaction's compensation semantics.
6. **No legacy surface should become a second portability authority** — legacy snapshots/presets pages and the legacy canvas must never grow portability computation or alternate manifest codecs; the pure modules (`studio_workflow_manifest`, `portability_contract/risk/targets/cache/service/evidence`) are the only implementation.
7. **Portability panel/list chips must survive Workflows UI consolidation** — including the Medium+High coexistence rendering, stale/needs-check/not-analyzed distinctions, keyboard-operable chips with text labels, and the environment section's visual separation.
8. **The cache sidecar remains derived** — `.studio_portability_reports.json` may be deleted/regenerated at any time; consolidation may relocate it only beside the domain stores via `DEFAULT_SIDECAR_FILENAME`; never let it become authority or gain TTL semantics.
9. **Phase-H V1/legacy retirement must not break History's stored Workflow/version references** — History V2 rows carry `workflow_id`/`workflow_version_id`/`preset_id` and RequestSnapshots containing `execution_plan_json`; retiring V1 surfaces must keep those references resolvable-or-honestly-stale, and must not reinterpret or rewrite stored graphs.
10. The deterministic gate is green at **Python 1991 / Node 21 / Fake Playwright 192**; new work adds to the allowlist and re-runs `python tests/run_studio_tests.py --fake`.
11. Nothing in the tree is committed; the worktree remains intentionally dirty; version-control boundaries remain a deliberate later batch.
12. No live/paid validation is outstanding for Phase G: all G evidence is deterministic/offline; the last live evidence remains Phase E's E7, not invalidated by G (G touched no replay-execution semantics).

---

## 39. AUTHORITATIVE INPUT INDEX

- `PHASE_F_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md` (Phase-F baseline + invariants H inherits)
- Audits: `PHASE_G1_WORKFLOW_EXACT_JSON_PORTABILITY_AUDIT_2026-08-23.md`, `PHASE_G2_DEPENDENCY_REPRODUCIBILITY_AUDIT_2026-08-23.md`, `PHASE_G3_TARGET_ENVIRONMENT_PORTABILITY_MATRIX_2026-08-23.md`, `PHASE_G4_PORTABILITY_PRODUCT_ARCHITECTURE_AUDIT_2026-08-23.md`
- Contract freeze: `PHASE_G5_PORTABILITY_CONTRACT_FREEZE_2026-08-23.md` (+ `portability_contract.py`)
- Implementation reports: `PHASE_G6_PORTABILITY_RISK_ENGINE_2026-08-23.md`, `PHASE_G7_TARGET_READINESS_RULES_2026-08-23.md`, `PHASE_G8_PORTABILITY_FIXTURE_CORPUS_2026-08-23.md`, `PHASE_G9_PORTABILITY_BACKEND_INTEGRATION_2026-08-23.md`, `PHASE_G10_PORTABILITY_CACHE_INVALIDATION_2026-08-23.md`, `PHASE_G11_PORTABILITY_CACHE_INTEGRATION_2026-08-23.md`, `PHASE_G12_PORTABILITY_FRONTEND_UX_2026-08-23.md`
- Format spec: `WORKFLOW_MANIFEST_FORMAT.md` (+ `studio_workflow_manifest.py`)
- Landed modules: `portability_contract.py`, `portability_risk.py`, `portability_targets.py`, `portability_cache.py`, `portability_service.py`, `portability_evidence.py`, `studio_domain/store.py::commit_import_transaction`, `studio_workflow_routes.py`, `web/studio-portability.js`, `web/studio-portability-checklist.js`
- Fixtures: `tests/fixtures/portability/` (51 files), `tests/portability_fixtures.py`

---

## FINAL VERDICT

`PHASE G COMPLETE`

Deploy / live / GPU / generation / commit / push by this closure batch: **NONE**.
