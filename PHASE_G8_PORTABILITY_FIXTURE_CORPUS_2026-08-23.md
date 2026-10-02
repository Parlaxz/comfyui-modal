# PHASE G8 — Portability Fixture Corpus (2026-08-23)

**Batch:** G8 · **Type:** test-infrastructure (fixtures + self-consistency tests) · **Mode:** pure fixture corpus. No risk rules, no target rules, no routes, no cache, no frontend, no provider calls, no dependency installers, no manifest format changes, no deploy/live/GPU/generation, no commit/push/branch/worktree/reset.

**Deliverables by THIS lane (all NEW; nothing else touched):**

| File | Status |
|---|---|
| `tests/fixtures/portability/` | NEW — 50-file deterministic fixture corpus |
| `tests/portability_fixtures.py` | NEW — pure path-relative loader API |
| `tests/test_portability_fixtures.py` | NEW — 35 self-consistency tests |
| `PHASE_G8_PORTABILITY_FIXTURE_CORPUS_2026-08-23.md` | NEW — this report |

Untouched per ownership boundary: `portability_contract.py`, `portability_risk.py`, `portability_targets.py`, production Workflow/domain files, `tests/run_studio_tests.py` (no runner registration in this batch).

---

## 1. Verdict

**G8 PASS.** One reusable deterministic fixture corpus now exists at `tests/fixtures/portability/` with 18 frozen scenario ids covering manifest codec, workflow portability risk, target readiness, import preview/commit inputs, cache invalidation, security/no-secret behavior, and future frontend fake parity. Every manifest golden is built through the existing `studio_workflow_manifest.build_manifest` (valid by construction), pinned by canonical-hash goldens, and verified by 35/35 self-tests that import ONLY `studio_workflow_manifest` + `portability_contract` — G8 passes while G6/G7 are still being written.

## 2. Scenario inventory (18 ids, frozen in `portability_fixtures.SCENARIO_IDS`)

| scenario_id | kind | encodes |
|---|---|---|
| `core_clean` | workflow | canonical base: Workflow + Version #1 immutable capture + Mapping + default preset; core nodes only; basename model with pinned fake hash; exact roundtrip; no paths/endpoints/subgraphs/assets |
| `custom_exact` | workflow | provenance **exact**: repo + 40-hex commit + known class mapping |
| `custom_unpinned` | workflow | provenance **declared**: version string, commit absent |
| `unresolved_node` | workflow | provenance **unresolved**: required class with no trustworthy source identity (manifest stays ready) |
| `model_hash_missing` | workflow | basename ref without sha256 → readiness fails while risk dimension stays separate |
| `model_extraction_gap` | workflow | `FixturePatchLoader` mirrors the audited ModelPatchLoader blind spot |
| `input_asset_required` | workflow | LoadImage-like basename asset; manifest assets[] reference metadata only; asset travels separately |
| `absolute_path` | workflow | Windows + POSIX paths in functional positions; inert note-text path for false-positive resistance |
| `external_endpoint` | workflow | functional HTTP input vs inert markdown note URL |
| `subgraph_frontend` | workflow | smallest valid `definitions.subgraphs`; target-sensitive frontend requirement (`POLICY_SUBGRAPHS`), not a global blocker |
| `private_model` | workflow | gated model on synthetic host; boolean-shaped access facts only |
| `native_build_dependency` | workflow | CUDA-toolchain native build requirement |
| `manifest_not_ready` | workflow | valid JSON + valid manifest failing `check_readiness` |
| `credential_like_value` | workflow | api_key/token/authorization/password = synthetic placeholder only |
| `popular_custom` | workflow | Manager-common popular custom node (declared provenance) |
| `current_corpus_shape` | workflow | compact synthetic reconciliation of the G1 corpus (see §5) |
| `environment_repro_high` | environment | G2 source-environment debt, all six frozen env codes |
| `unknown_target_capability` | capability | RunComfy native-build capability = unknown |

Provenance level **inferred** is represented inside `current_corpus_shape` (registry host-fallback attribution bug from G1 §8).

## 3. Fixture schema & layout

```
tests/fixtures/portability/
├── README.md                     scenario explanations + consumption guide
├── scenarios/<id>.json           descriptor: kind, audit_basis, manifest pointer,
│                                 manifest_sha256_canonical, readiness expectation,
│                                 expected {signals, issue_codes, provenance_quality,
│                                 risk_level_hint_nonnormative}, classification{}
├── manifests/<id>.manifest.json  pretty sorted-key manifest-v1 goldens
│                                 (+ unknown_section_fields / unknown_root_section.invalid)
├── evidence/*.evidence.json      environment, corpus-shape, unknown-capability,
│                                 five target-characteristic capability files
├── expected/*.expected.json      normative: current_corpus_shape reconciliation,
│                                 target_matrix, invalidation semantics, golden hashes
├── invalidation/stamps.json      9 stamps (A, A2, 6 single-field variants, null)
└── raw/malformed_manifest.txt    truncated JSON (JSON-invalid ≠ structurally-invalid)
```

Descriptor signals use only frozen `SIGNAL_NAMES` (bool/count types re-validated via `normalize_signals`); issue codes ⊆ `FOUNDATIONAL_ISSUE_CODES`; provenance ∈ `PROVENANCE_QUALITY_VALUES`; every risk value anywhere ∈ lowercase `RISK_LEVELS`. `risk_level_hint_nonnormative` is advisory; normative expectations live only under `expected/`.

## 4. Real-audit facts represented (synthetic/redaction policy)

- **G1**: exact roundtrip PROVEN → `exact_roundtrip_proven: true` everywhere; zero absolute paths / zero functional endpoints in the real corpus → fixtures exercise the *detectors* with sanctioned synthetic strings instead; URLs-in-note-text-only pattern reproduced; ModelPatchLoader extraction gap; subgraph definitions; ≥10-repo custom spread compressed to 4 synthetic repos with mixed exact/declared/inferred provenance including the registry host-fallback bug.
- **G2**: environment HIGH debt encoded as shape, not machine state — core commit-pinned but locally patched, torch trio unpinned, base-image digest unpinned, working-tree node provenance incomplete, dirty plugin worktree (synthetic count), zero model-hash coverage.
- **G3**: five characteristic rows with per-target capability facts.
- Redaction: all ids `wf_fixture_*`/`wv_*`/`wm_*`/`wpres_*`; all URLs `https://example.invalid/...`; hashes are fake constants (`deadbeef`×8 etc.), never model bytes; path examples exactly `C:\example\models\foo.safetensors`, `/opt/example/input/foo.png`, `/opt/example/notes/related-fixtures.md`; no real workflow ids/names/tokens anywhere.

## 5. Current-corpus reconciliation fixture

`current_corpus_shape` + `expected/current_corpus_shape.expected.json` is the shared G6 proof: **workflow portability = medium AND environment reproducibility = high coexist** in one artifact, with `coexistence.policy == POLICY_ENVIRONMENT_ISOLATION`, matching signal sets (14 signals), issue-code set `{custom_node_unpinned, model_hash_unpinned, model_extraction_gap, subgraph_frontend_requirement}`, and honest `manifest_readiness.ready=false` (3 unhashed models) demonstrating concept separation.

## 6. G3 target-matrix fixtures

`expected/target_matrix.expected.json` freezes one deterministic outcome per cell for the five characteristics × six targets, each backed by `evidence/target_characteristic_<c>.evidence.json` capability facts (cross-checked equal by tests):

- CORE: local/modal/runpod/runcomfy/comfy_cloud low, baseten medium.
- POPULAR CUSTOM: runcomfy resolved **low** via supplied auto-setup evidence (exact pin not required); comfy_cloud resolved **low** via supplied on-curation-list allowlist evidence; off-list branch documented as `high`.
- NATIVE BUILD: local medium, modal low, runpod high, comfy_cloud high, baseten resolved **medium** (verified setup path tie-break for the audited medium–high range), runcomfy **unknown**.
- ABSOLUTE PATH: local low (self-host-sensitive), all remote high (severity override).
- PRIVATE MODEL: local/modal low, runpod/runcomfy medium, comfy_cloud **high** via catalog-miss evidence (catalog-hit branch documented as `low`).
- UNKNOWN CAPABILITY: RunComfy native-build `capability=unknown` → rule must emit `target_capability_unknown` with risk `unknown`.

Where G5/G3 did not freeze a single result, the fixture supplies the explicit evidence so G7 produces one contract-compliant answer; alternatives are data, not code.

## 7. Invalidation fixtures

9 stamps over the exact 8-field contract: `stamp_a` ≡ `stamp_a2` (reusable), six single-field variants (graph_hash, model_library_generation, custom_node_registry_generation, rule_version, manifest_version, comfyui_version) each stale on exactly its flipped field, and `stamp_null_field` (null `dependency_metadata_hash`) conservatively stale even against itself. Semantics asserted through `portability_contract.invalidation_mismatches` — no cache logic implemented.

## 8. Security fixtures & no-secret assertion

`credential_like_value` carries four credential-shaped fields whose values are exclusively the documented placeholder; descriptors classify them for future export-scrub/refusal and import-warning tests (scrub logic NOT implemented here). Self-tests denylist Modal `ak-`/`as-`, HF `hf_`, GitHub `ghp_`/`github_pat_`, AWS `AKIA…`, `sk-…`, Civitai token shapes across all corpus bytes, and prove the placeholder appears ONLY inside the two credential-scenario files.

## 9. Manifest roundtrip golden result

17 valid manifests parse → validate → canonical-serialize stably (`canonical_json(parse(x)) == canonical_json(json.loads(x))` and idempotent re-parse); stored bytes are byte-deterministic (pretty sorted-key dump); identity pinned twice — `expected/manifest_golden_hashes.expected.json` and each descriptor's `manifest_sha256_canonical`. `manifest_hash(include_metadata=False)` proven stable when only metadata timestamps vary (identity excludes timestamps per existing semantics). Unknown section-level fields survive parsing (lenient evolution pinned) while an unknown ROOT section is rejected — distinction self-tested. Negative shapes kept distinct: `manifest_not_ready` (valid JSON, readiness fails) vs `raw/malformed_manifest.txt` (JSON-invalid).

## 10. Self-test counts

- `python tests/test_portability_fixtures.py` → **35/35 passed** (pytest-discoverable: 35 passed).
- Neighbors untouched and green: `test_studio_workflow_manifest.py` 21/21, `test_portability_contract.py` 32/32.
- Coverage maps to all 24 mandated checks plus descriptor-vocabulary, matrix↔evidence cross-consistency, branch-alternative, loader-purity, and byte-determinism extras.

## 11. How G6/G7/G9 consume the corpus

- **G6 (risk engine)**: iterate `scenarios/*.json` for inputs + expected signals/issue codes; reconcile summary against `expected/current_corpus_shape.expected.json`; use `classification.functional_paths/inert_note_paths` (absolute_path) and `functional_endpoints/inert_note_urls` (external_endpoint) to prove false-positive resistance; detect credentials via `credential_like_value`.
- **G7 (target rules)**: read `evidence/target_characteristic_*.json` capability facts, emit results equal to `expected/target_matrix.expected.json`; honor `branch_alternatives` only when alternative evidence is supplied; emit `target_capability_unknown` for the RunComfy native case.
- **G9 (routes/cache/frontend)**: `raw/malformed_manifest.txt` for JSON-invalid handling; `manifest_not_ready` for readiness failures; `invalidation/*` for stamping; lowercase wire vocabulary throughout. Loader: `fixture_manifest(name)` / `fixture_evidence(name)` / `fixture_expected(name)` / `load_scenario` / `load_invalidation_stamps` / `load_raw_text` — pure readers, paths relative to the test file.

## 12. Constraints compliance

Production logic implemented: NONE · Protected files modified: NONE · Runner registration: NONE (later integration batch registers G6/G7/G8 together) · Deploy/live/GPU/generation: NONE · Commit/push/branch/worktree/reset: NONE.

*G8 complete.*
