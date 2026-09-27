# PHASE G7 — Target Readiness Rule Adapters (2026-08-23)

**Batch:** G7 · **Type:** pure implementation · **Mode:** pure stdlib/pure-data module + tests + this document. No provider SDKs, no HTTP, no filesystem, no credentials, no environment mutation, no route registration, no deploy/live/GPU/generation, no commit/push/branch.

**Deliverables by THIS lane:**

| File | Status |
|---|---|
| `portability_targets.py` | NEW — six pure per-target readiness adapters over prepared evidence |
| `tests/test_portability_target_rules.py` | NEW — 33 deterministic tests (plain-run + pytest) |
| `PHASE_G7_TARGET_READINESS_RULES_2026-08-23.md` | NEW — this document |

Untouched per ownership boundary: `portability_contract.py`, G6's `portability_risk.py` (not required at import time; only the contract is imported), G8 fixtures, routes, domain persistence, cache, frontend, manifest codec, runtime/provider execution, GPU/performance code, `tests/run_studio_tests.py`.

---

## 1. Verdict

**G7 PASS.** Six pure adapters (`local`, `modal`, `runpod`, `runcomfy`, `comfy_cloud`, `baseten` — exact frozen G5 ids, aliases rejected via `normalize_target_id`) now answer: "given prepared WorkflowVersion portability evidence, what is its readiness for THIS target?" Target readiness stays a separate dimension from global Workflow risk (one target may be HIGH while summary risk is MEDIUM). UNKNOWN provider capabilities from G3 are preserved as explicit uncertainty (`target_capability_unknown` + UNKNOWN risk level), never assumed supported or failed. Comfy Cloud is fail-honest. Regression: new suite 33/33, `test_portability_contract.py` 32/32, `test_studio_workflow_manifest.py` 21/21, pytest 65 passed. Deploy/live/GPU/commit/push: NONE.

## 2. Pure API

```python
import portability_targets as t

evidence = t.build_target_evidence(...)          # validated prepared-evidence object
outcome  = t.evaluate_target_readiness(evidence) # {"rule_version", "targets", "issues"}
single   = t.evaluate_single_target("runpod", evidence)
```

- `rule_version` is exactly the frozen `portability-rules-v1` (re-exported from the contract; no separate target-rule version exists).
- `targets` has exactly the six frozen keys in contract order; each value is a canonical `make_target_result()` shape `{risk_level, issue_codes, advice}`.
- `issues` is the deduplicated pool of target-only issue objects (each minted ONCE, deterministically sorted via `sort_issues`). Targets reference codes per the G5 §7.2 reference-by-code model.
- Composer duty (documented + tested): the report's global pool = target-only mints ∪ canonical objects for every code listed in `global_issue_codes`. Targets reference globals but never re-mint them.
- `evaluate_single_target` rejects wire aliases (`comfy-cloud`, `comfycloud`, `run_comfy`) through the contract.

## 3. Target capability inputs (evidence shape)

`build_target_evidence()` validates and normalizes:

- `global_issue_codes` — codes already in the global pool that targets may reference (`local_path_reference`, `model_hash_unpinned`, `subgraph_frontend_requirement`, `manifest_not_ready`, …).
- `signals` — validated through `normalize_signals` (frozen vocabulary).
- `custom_nodes[]` — `name`, `provenance` (exact/declared/inferred/unresolved), `manager_restorable`, `product_internal`, `install_status` (installed/missing/unknown), flags `requires_python_install` / `requires_system_packages` / `requires_native_build` / `requires_cuda_build`, and tri-state `target_supported: {target_id: true|false|null}` allowlist evidence.
- `models[]` — `name`, `sha256|null`, `private_or_gated`, `present_locally`, tri-state `target_catalog_available`.
- `absolute_paths[]` — `path`, `source_host_consistent`, `product_materialized` (product input-materialization abstraction).
- `requires_input_asset`, `uses_subgraphs`, `frontend_version` (source pin "1.44.19"), `manifest_ready`.
- `frontend_support: {target_id: bool}` — explicit per-target subgraph/frontend confirmation.
- `runcomfy_native_capability`: `supported|unsupported|unknown` (G3 UNKNOWN default).
- `baseten_persistent_storage`: `available|unknown` (G3 UNKNOWN default).

No provider node lists are hardcoded: catalog facts arrive exclusively as tri-state evidence, so a later provider-evidence updater can supply fresh data without touching rules.

## 4. Per-target rule philosophy

- **local** — reference/native environment. Core → LOW. Missing local installs → HIGH (`local_dependency_missing`); native-build burden → MEDIUM; unresolved provenance → MEDIUM (explainable, not blocking); source-host-consistent absolute paths stay operational while the global finding remains referenced; missing local models → HIGH.
- **modal** — native product target with broad dependency control. Python/native/system needs → LOW (image layers solve them); product-internal plugin classes → supported (no issue); unresolved provenance → MEDIUM (deploy bake lacks a pin); absolute paths HIGH unless the path record is `product_materialized`; models LOW unless evidence explicitly marks them unavailable on volumes.
- **runpod** — same JSON broadly usable, everything else is image setup. Any custom node → MEDIUM `runpod_image_setup_required`; native/system/CUDA build → HIGH; unresolved source → HIGH (cannot bake unpinned); private/gated models → MEDIUM token plumbing; subgraphs → MEDIUM "ship a subgraph-capable frontend" (user-controlled image). No Dockerfiles generated — advice states what would be required.
- **runcomfy** — strong plain-JSON import + auto-setup. Manager-restorable declared/exact nodes → LOW; others → MEDIUM auto-setup; native deps follow the supplied capability input: `supported` → HIGH provisioning, `unsupported` → HIGH blocked, `unknown` (default) → `runcomfy_native_capability_unknown` + `target_capability_unknown` + UNKNOWN level; exact-pin provenance adds a LOW commit-pinning caveat (Manager-restorable ≠ exact-revision-restorable); private/gated → MEDIUM token attach; subgraphs unverified → capability unknown.
- **comfy_cloud** — strongest restriction awareness, fail-honest. Node explicitly off-catalog → HIGH `comfy_cloud_node_off_catalog`; catalog membership unknown → `comfy_cloud_node_support_unknown` + `target_capability_unknown` + UNKNOWN level (never assume support or failure); arbitrary Python install fires HIGH when the node is known off-catalog (with unknown membership the uncertainty codes carry it); native/system requirement → HIGH always; off-catalog model → HIGH; gated model with unknown catalog → UNKNOWN; curated/core-only graph → LOW. Advice truthfully says the target cannot satisfy unsupported requirements; nothing is "adapted".
- **baseten** — capable custom build, deployment-embedding model. Every result starts MEDIUM `baseten_deployment_embedding_required` (workflow embeds into a Truss deployment; no graph-per-request parity claimed); custom nodes → MEDIUM bake advice; CUDA build → HIGH, other native/system → MEDIUM; unresolved source → HIGH; private/gated → MEDIUM secrets setup; persistent-storage UNKNOWN surfaced as `baseten_storage_capability_unknown` + shared uncertainty code without inflating the level. No Truss configs built.

## 5. UNKNOWN handling

Decision-relevant UNKNOWNs emit `target_capability_unknown` (one canonical shared object, medium severity) and set the target's risk to UNKNOWN unless a known HIGH blocker exists (HIGH wins so actionable findings are never masked; uncertainty remains visible via codes). Risk precedence: high > unknown > medium > low. Preserved G3 unknowns: RunComfy native/system control and commit pinning, RunPod timeout/volume ceilings (not decision inputs here), Comfy Cloud catalog breadth/wall-clock, Baseten persistent storage/timeouts. Subgraph support on platform-managed targets (runcomfy, comfy_cloud) is uncertainty; on user-baked targets (runpod, baseten) it is achievable setup (medium), and local/modal default to supported given the pinned 1.44.19 frontend.

## 6. Target-sensitive path/subgraph behavior

Absolute paths: global finding exists independently (`local_path_reference` referenced, never duplicated). Local keeps a self-consistent host path operational at LOW; stale paths (`source_host_consistent=false`) are HIGH even locally. All five remote targets go HIGH via one shared `target_absolute_path_blocker` object; Modal alone is exempted per-path when `product_materialized=true` (product input transport). A basename input transported by the product never triggers any of this — only explicit absolute-path records (or the `has_absolute_path` signal fallback) do. Subgraphs are never a global blocker here: presence references `subgraph_frontend_requirement` and severity is decided per target as §5.

## 7. G3 golden characteristic matrix (encoded deterministically)

| Characteristic | local | modal | runpod | runcomfy | comfy_cloud | baseten |
|---|---|---|---|---|---|---|
| A core + standard checkpoint | low | low | low | low | low | medium |
| B popular custom nodes | low | low | medium | low (manager-friendly) | unknown→low/high by supplied catalog evidence | medium |
| C native-build dependency | medium | low | high | unknown (capability input; `supported`→high) | high | high (CUDA) / medium |
| D absolute host path | low (self-consistent) | high (unless materialized) | high | high | high | high |
| E private/gated model | low (present) | low (supplied) | medium | medium | unknown→high/low by catalog evidence | medium |

All five rows are asserted literally in tests using explicit prepared evidence (no machine state).

## 8. Issue/advice dedupe & determinism

Issues aggregate PER CODE inside an accumulator: repeated triggers merge subject names into ONE bounded object (message shows ≤5 sorted names + "; and N more"; evidence carries count + ≤8 names, well under the 2048-byte bound). Shared multi-target codes (`target_absolute_path_blocker`, `dependency_source_unresolved`, `product_internal_dependency`, `target_capability_unknown`, `manifest_not_ready`) use target-agnostic messages so exactly one canonical object serves all referencing targets; conflicting renders raise. `issue_codes` are emitted sorted; advice lines are first-occurrence ordered and deduped; no set iteration reaches output. Byte-stability is asserted via `canonical_json` equality across runs. Provenance distinction is enforced throughout: exact pin + installable target ≠ declared package ≠ inferred guess ≠ unresolved source (unresolved → HIGH on every provisioning target).

## 9. Tests

`tests/test_portability_target_rules.py` — 33 tests covering all 24 mandated points plus extras: exact six keys; alias rejection; golden matrices A–E (including comfy_cloud/baseten conditional variants); Comfy Cloud off-catalog/python/native HIGH trio; RunPod setup advice + native risk; RunComfy manager-friendly LOW (+ exact-pin caveat) and unknown-native uncertainty; Modal product-internal support; Baseten embedding advice + storage-unknown note; subgraph target sensitivity incl. explicit confirmation clearing uncertainty; `target_capability_unknown` emission; missing-SHA non-failure; unresolved-source HIGH set; deterministic order/bytes; single-object aggregation; name-cap bounding; purity (AST import allowlist `__future__|re|portability_contract` + network/exec token scan); rule_version exactness; composed-report `validate_report()` cleanliness; manifest-not-ready blocking all six; evidence-builder rejection of bad payloads/aliases; input-asset advice without risk inflation; `has_absolute_path` signal fallback.

Not modified: `tests/run_studio_tests.py` (registration deferred to later integration, per batch).

## 10. Deliberately unimplemented provider evidence refresh

No provider docs were re-fetched; G3's audited facts are the frozen baseline. Not built here (later lanes / future evidence updaters): live catalog allowlists for Comfy Cloud, RunComfy capability verification, RunPod/Baseten timeout/storage ceilings, Dockerfile/Truss generation, pricing/GPU scheduling, availability checks, and any global Workflow summary-risk computation. When provider facts refresh, they enter exclusively as tri-state evidence fields — no rule edits required.

---

*Regression evidence: `python tests/test_portability_target_rules.py` → 33/33; `python tests/test_portability_contract.py` → 32/32; `python tests/test_studio_workflow_manifest.py` → 21/21; `python -m pytest` on both portability suites → 65 passed. Deploy/live/GPU/generation/commit/push: NONE.*
