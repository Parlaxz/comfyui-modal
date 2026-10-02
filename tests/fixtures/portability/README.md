# Phase-G Portability Fixture Corpus (G8)

Reusable, deterministic, synthetic fixtures for the Phase-G portability lanes.
Everything here is **data only**: no production logic, no G6/G7 imports, no
secrets, no real user data, no absolute host paths beyond the sanctioned
synthetic examples.

- Contract authority: `portability_contract.py` + `PHASE_G5_PORTABILITY_CONTRACT_FREEZE_2026-08-23.md`
- Manifest authority: `studio_workflow_manifest.py` (v1, unchanged)
- Scenario evidence: `PHASE_G1/G2/G3_*_2026-08-23.md`
- Self-tests: `tests/test_portability_fixtures.py` (loader: `tests/portability_fixtures.py`)

## Layout

```
tests/fixtures/portability/
├── scenarios/    one self-describing descriptor per scenario id
├── manifests/    manifest-v1 JSON goldens (pretty, sort_keys) + 2 special shapes
├── evidence/     prepared environment / corpus / target-capability evidence
├── expected/     normative expectations (reconciliation, G3 matrix, golden hashes)
├── invalidation/ stamps.json + semantics.expected.json
└── raw/          malformed_manifest.txt (invalid JSON for route tests)
```

## Scenario inventory (18 ids, frozen)

| scenario_id | kind | represents |
|---|---|---|
| `core_clean` | workflow | canonical clean base workflow; exact roundtrip; core nodes only; pinned fake model hash; preset present |
| `custom_exact` | workflow | custom node provenance **exact** (repo + commit + class mapping) |
| `custom_unpinned` | workflow | provenance **declared** (version string, no commit) |
| `unresolved_node` | workflow | required class with **unresolved** source identity |
| `model_hash_missing` | workflow | basename model ref without sha256 (readiness fails; risk separate) |
| `model_extraction_gap` | workflow | loader input outside extraction mappings (ModelPatchLoader-class blind spot) |
| `input_asset_required` | workflow | LoadImage-like asset by basename; reference metadata only; asset travels separately |
| `absolute_path` | workflow | Windows + POSIX paths in functional positions; inert note-text path for false-positive resistance |
| `external_endpoint` | workflow | functional HTTP input vs inert markdown note URL |
| `subgraph_frontend` | workflow | smallest `definitions.subgraphs`; target-sensitive frontend requirement, not a global blocker |
| `private_model` | workflow | gated/private model reference (synthetic host, boolean-shaped flags) |
| `native_build_dependency` | workflow | CUDA-toolchain native build requirement |
| `manifest_not_ready` | workflow | valid JSON + valid manifest that fails `check_readiness` |
| `credential_like_value` | workflow | api_key/token/authorization/password fields holding the synthetic placeholder |
| `popular_custom` | workflow | Manager-common popular custom node (declared provenance) |
| `current_corpus_shape` | workflow | compact synthetic reconciliation of the audited G1 corpus (MEDIUM/HIGH coexistence proof) |
| `environment_repro_high` | environment | G2 source-environment debt; all six frozen env codes; never forces workflow/target risk |
| `unknown_target_capability` | capability | RunComfy native-build capability = unknown → `target_capability_unknown` |

## Descriptor schema (`scenarios/<id>.json`)

```json
{
  "scenario_id": "...", "kind": "workflow|environment|capability",
  "title": "...", "description": "...", "audit_basis": ["..."],
  "manifest_file": "manifests/<id>.manifest.json",
  "manifest_sha256_canonical": "<sha256 of canonical bytes incl. metadata>",
  "manifest_readiness_expected": {"ready": true, "missing_count": 0},
  "expected": {
    "signals": { "<frozen SIGNAL_NAMES>": bool|int },
    "issue_codes": ["<FOUNDATIONAL_ISSUE_CODES>"],
    "provenance_quality": "exact|declared|inferred|unresolved",
    "risk_level_hint_nonnormative": "low|medium|high|unknown",
    "semantic_notes": ["..."]
  },
  "classification": {
    "functional_paths": [], "inert_note_paths": [],
    "functional_endpoints": [], "inert_note_urls": [],
    "credential_placeholder": "...", "asset_travels_separately": true
  },
  "evidence_file": "evidence/..."
}
```

`risk_level_hint_nonnormative` is advisory context only. Normative expectations
live exclusively in `expected/`.

## Manifests

Every `manifests/*.manifest.json` except
`unknown_root_section.manifest.invalid.json` parses and validates through
`studio_workflow_manifest.parse_manifest`. Files are pretty-printed with sorted
keys; their identity is the sha256 over canonical bytes recorded in
`expected/manifest_golden_hashes.expected.json` and in each descriptor's
`manifest_sha256_canonical`.

Two deliberate negative shapes:

- `manifest_not_ready.manifest.json` — valid JSON, valid manifest,
  `check_readiness` fails (model hash missing). Observed module semantics: a
  custom-node entry lacking repo_url/revision fails full *validation*, so the
  model-hash gap is the only valid-but-not-ready shape.
- `unknown_root_section.manifest.invalid.json` — rejected with
  `unknown root section` (root sections are closed).
- `unknown_section_fields.manifest.json` — extra keys inside `workflow` /
  `metadata` survive parsing: section-level lenient evolution is pinned.

`raw/malformed_manifest.txt` is truncated JSON (JSON-invalid), kept strictly
separate from structural invalidity above.

## Synthetic / redaction policy

- All ids are obviously synthetic (`wf_fixture_*`, `wv_fixture_*`, `wm_fixture_*`,
  `wpres_fixture_*`); all repo/model URLs use `https://example.invalid/...`.
- Model hashes are valid fake 64-hex constants (`deadbeef`×8 etc.); no model
  bytes exist anywhere.
- Absolute-path examples are exactly `C:\example\models\foo.safetensors`,
  `/opt/example/input/foo.png`, `/opt/example/notes/related-fixtures.md`.
- The credential fixture uses only the placeholder constant named in its
  descriptor; no real Modal/HF/Civitai/AWS/GitHub token shapes appear anywhere
  (self-tested).
- Environment evidence numbers are synthetic stand-ins for the audited shape of
  the debt, not copies of machine state.

## Key normative expectations

- `expected/current_corpus_shape.expected.json` — workflow portability **medium**
  AND environment reproducibility **high** coexist (PHASE_G5 §2 resolution);
  shared reconciliation proof for G6.
- `expected/target_matrix.expected.json` — broad G3 matrix for the five
  characteristics × six targets, with explicit determinism rules and documented
  branch alternatives so G7 emits single deterministic outcomes.
- `evidence/environment_repro_high.evidence.json` — all six frozen environment
  codes; explicitly does NOT dictate workflow/target risk.
- `evidence/unknown_target_capability.evidence.json` — capability `unknown`;
  future rule must emit `target_capability_unknown`.
- `invalidation/stamps.json` + `semantics.expected.json` — A≡A2 reusable; any
  concrete difference stale; any null conservative recompute (PHASE_G5 §11).

## How later lanes consume this

- **G6 (risk engine)**: read `scenarios/*.json` descriptors for inputs +
  expected signals/issue codes; reconcile against
  `expected/current_corpus_shape.expected.json`; use `absolute_path` /
  `external_endpoint` classifications to prove functional-vs-note-text
  resistance; use `credential_like_value` for detection tests.
- **G7 (target rules)**: read `evidence/target_characteristic_*.json` capability
  facts and emit per-target results matching `expected/target_matrix.expected.json`;
  honor `branch_alternatives` only when the alternative evidence is supplied;
  emit `target_capability_unknown` for the RunComfy native-build case.
- **G9 (routes/cache/frontend parity)**: `raw/malformed_manifest.txt` for
  JSON-invalid handling; `manifest_not_ready` for readiness failures;
  `invalidation/*` for cache stamping; lowercase wire values throughout.
- Loader API: `tests/portability_fixtures.py`
  (`load_portability_fixture`, `fixture_manifest`, `fixture_evidence`,
  `fixture_expected`, `load_scenario`, `load_invalidation_stamps`,
  `load_raw_text`). Pure path-relative readers; no hidden state.
