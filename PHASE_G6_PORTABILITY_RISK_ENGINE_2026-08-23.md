# PHASE G6 — Pure Workflow Portability Risk Engine (2026-08-23)

**Batch:** G6 · **Type:** pure implementation · **Mode:** stdlib-only engine + tests + this document. No routes, no cache, no frontend, no target rules, no DependencyResolver changes, no Modal/runtime/GPU, no deploy/live/generation, no commit/push/branch/reset.

**Files created by THIS lane:**

| File | Status |
|---|---|
| `portability_risk.py` | NEW — pure deterministic risk engine (imports: `re`, `dataclasses`, `datetime`, `typing`, `portability_contract` only) |
| `tests/test_portability_risk_engine.py` | NEW — 28 deterministic tests, runnable standalone and unittest-discoverable |
| `PHASE_G6_PORTABILITY_RISK_ENGINE_2026-08-23.md` | NEW — this document |

No existing file was modified. G5 contract freeze untouched (`portability_contract.py`, `studio_workflow_manifest.py`, audits).

---

## 1. Verdict

**G6 PASS.** A pure, I/O-free risk engine now computes all 14 frozen static signals, emits deterministic issues from prepared evidence, assembles Workflow portability risk separately from environment reproducibility, and produces `validate_report()`-clean full reports that accept externally supplied target results. The reconciled audited corpus resolves **MEDIUM** workflow portability while supplied environment evidence resolves **HIGH**, and environment HIGH never contaminates workflow or target levels.

## 2. Pure API

```python
PortabilityEvidence            # frozen dataclass: all facts passed IN
make_evidence(**fields)        # normalized constructor (rejects unknown fields)
evidence_from_version_record(version, *, model_rows, custom_node_rows,
    core_classes, manifest_readiness, ...)   # DependencyResolver adapter
compute_signals(evidence) -> dict            # all 14 frozen signal names
analyze_workflow_version(evidence, analyzed_at=None) -> partial report
build_environment_result(env_facts) -> {"risk_level", "issues", "source"}
assemble_report(workflow_result, *, target_results=None,
    environment_result=None, invalidation=None, analyzed_at=None,
    stale=False) -> validated full report
build_workflow_report(evidence, *, analyzed_at=None, **assemble_kwargs)
```

The module performs no filesystem scans, no network, no git, no installs, no provider SDKs, and holds no global mutable state (proven by test 24: analysis completes with `builtins.open`/`socket.socket`/`urllib.request.urlopen` patched to raise; source is statically asserted free of I/O imports).

## 3. Input evidence contract

`PortabilityEvidence` fields (all supplied by a later route/service adapter): `version_id`, `graph_hash`, `executable_prompt` / `api_prompt_json` (`output` projection preferred, mirroring `extract_executable_prompt`), `graph_json`, `dependency_metadata` (`model_stack`, `node_classes`), `model_evidence` / `custom_node_evidence` (exact current `DependencyResolver.resolve_version()` row shapes), `node_provenance` (per-class `{quality, repo, revision}` using the frozen `exact|declared|inferred|unresolved` vocabulary), `core_classes`, `manifest_readiness` (verbatim `check_readiness()` result — consumed, never reimplemented), `referenced_assets`, `extraction_gap_refs`, `models_available` / `custom_nodes_available` (explicit provider availability), `env_bound_registry_leak`, `exact_roundtrip_proven_override`.

Provenance precedence: explicit `node_provenance` map → row `provenance` field → conservative derivation from resolver state (`installed`+commit→`declared`; `installed` w/o commit→`inferred`; `wrong_revision`→`declared`; `missing`+repo→`declared`; else `unresolved`). A non-empty registry `repo_url` alone is NEVER trusted as exact (G1/G2 host-fallback noise).

## 4. Static signals

All frozen names from `portability_contract.py`, always emitted, types enforced by `normalize_signals`: `has_absolute_path`, `has_unresolved_node_type`, `unresolved_node_count`, `custom_node_count`, `custom_repo_count`, `custom_node_revision_pinned` (true iff every custom class has `exact` provenance AND a revision), `model_ref_basename_only`, `model_hash_pinned` (64-hex per ref; vacuous true), `model_extraction_gap`, `requires_input_asset`, `has_external_endpoint`, `uses_subgraphs`, `exact_roundtrip_proven` (recomputed via `sha256_of_canonical(executable_prompt)` unless overridden), `env_bound_registry_leak`. No S1–S12 labels anywhere.

## 5. Detection rules

- **Paths**: Windows drive (`X:\…`), UNC (`\\srv\share\…`), multi-segment POSIX absolute. URL substrings are stripped before path matching so ordinary http(s) URLs never classify as filesystem paths. Functional scan = executable-prompt string inputs + non-note UI `widgets_values`; `Note`/`MarkdownNote` node text is documentation and never scanned.
- **Endpoints**: only executable-input strings starting `http(s)://`. Note/label/metadata URLs are ignored.
- **Credentials**: credential-shaped input KEY names (`api_key`, `token`, `password`, …) with non-empty values → HIGH issue; values never enter messages or evidence.
- **Extraction gap**: loader-suffixed class with model-extension string input lacking any supplied model-evidence row (motivating case `ModelPatchLoader.name`); explicit `extraction_gap_refs` honored. `_MODEL_REF_MAPPINGS` NOT touched.
- **Assets**: `LoadImage/LoadMask/LoadVideo/LoadAudio/LoadImageMask` + `VHS_Load*` prefixes + supplied `referenced_assets`. Setup requirement (medium), not a blocker.
- **Subgraphs**: `definitions.subgraphs` non-empty → signal + LOW issue (`POLICY_SUBGRAPHS`); never a universal blocker.

## 6. Issue mapping

Foundational codes used: `local_path_reference`(med), `unresolved_node_type`(HIGH), `custom_node_unpinned`(med), `model_hash_unpinned`(med), `model_extraction_gap`(med), `required_input_asset`(med), `external_endpoint_reference`(med), `subgraph_frontend_requirement`(low), `manifest_not_ready`(HIGH), `dependency_missing`(med when every missing item has a source/repo candidate, HIGH when any model lacks sources — per G4 §6.1), `dependency_wrong_revision`(med), `credential_like_value_detected`(HIGH). Three NEW stable documented codes for audited conditions the frozen set cannot represent: `graph_hash_mismatch`(med), `env_bound_registry_leak`(med), `analysis_unavailable`(med; UNKNOWN verdict carrier). Frozen codes were not renamed; subjects come only from `SUBJECT_VOCABULARY`; one issue per code (aggregated, deterministic messages, bounded ≤2048-byte evidence, samples sorted/truncated).

## 7. Summary-risk algorithm

Deterministic over the emitted workflow-issue list only:
`UNKNOWN` (structural unreadability | missing executable prompt | invalid graph_hash | explicitly unavailable critical evidence provider) → else `HIGH` if any high-severity issue → else `MEDIUM` if any medium → else `LOW`. Missing optional metadata never escalates by itself. Absolute paths are a global medium finding; cross-target severity belongs to G7 (`POLICY_ABSOLUTE_PATHS`). Manifest readiness failure is HIGH but distinct from dependency availability (no synthetic `dependency_missing`). Counts derive from the actual list; issues sort severity desc → code → subject (`sort_issues`).

## 8. Environment isolation proof

`build_environment_result` maps six prepared boolean facts to exactly the six frozen env codes (`torch_stack_unpinned` H, `custom_node_source_unpinned` H, `plugin_worktree_dirty` H, `local_core_patch_divergence` H, `model_hash_unpinned` M, `base_image_digest_unpinned` M); unknown facts fabricate nothing; all-unknown → UNKNOWN + explanatory issue. The section carries `source="current_studio_environment"` and its issues never enter workflow counts/issues/risk. Tests 3 and 4 prove: env HIGH + corpus MEDIUM → MEDIUM; env HIGH + core-only LOW → LOW.

## 9. Current-corpus expected result

Golden fixture reproduces the audited facts (G1 §10 reconciled with G2 §4.1): roundtrip proven, zero host paths, zero functional endpoints, 5 custom classes across 5 repos with declared/inferred provenance, 3 unhashed model refs, one `ModelPatchLoader` extraction gap (class itself verified core per G2 — registry snapshot gap only), 2 subgraphs, no input assets. Engine result: **risk=medium**, counts `{high:0, medium:3, low:1}`, issues `custom_node_unpinned`, `model_hash_unpinned`, `model_extraction_gap`, `subgraph_frontend_requirement`. Fully pinned variant → LOW; adding one truly-unresolved class → HIGH.

## 10. Determinism

Same inputs ⇒ identical signals/issues/counts/risk; two reports at the same injected `analyzed_at` are canonically byte-equal, and differing timestamps differ in `analyzed_at` only (test 20). All orderings sorted; no randomness; canonical JSON per project convention.

## 11. Test counts

- New suite: **28/28 passed** (`python tests/test_portability_risk_engine.py`, also `python -m unittest tests.test_portability_risk_engine`).
- Regression: `test_portability_contract.py` **32/32**; `test_studio_workflow_manifest.py` **21/21**; `tests.test_dependency_resolver` **11/11**. (Contract/manifest suites are pytest-style modules run directly per repo convention.) Live/paid tests: none run.

## 12. Delegated assumptions (NOT owned here)

- **G7**: all per-target risk levels/advice; G6 defaults absent targets to honest `unknown` ("target rules not evaluated") and validates caller-supplied results through `make_target_result`.
- **Routes/backend**: gathering evidence from `.studio_model_library.json` / `.studio_custom_nodes.json` / stores into `PortabilityEvidence` (adapter provided; stores never opened by the engine), HTTP wiring, import/export flows.
- **Report cache**: staleness computation (`stale` flag passthrough), stamp lifecycle; stamps accepted verbatim and validated.
- **DependencyResolver**: unchanged; `evidence_from_version_record` accepts its current output shape (fixture-tested).
- **Model extraction fix**: `_MODEL_REF_MAPPINGS` untouched; gap surfaced via frozen code/signal.

*G6 complete. Deploy/live/GPU/generation/commit/push: NONE.*
