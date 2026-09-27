# PHASE G1 — Workflow Corpus & Exact-JSON Portability Audit

Date: 2026-08-23 · Lane: G1 (workflow-data / exact-JSON side only) · Mode: READ-ONLY AUDIT
Scope: workflow persistence, JSON fidelity, environment-specific values, model/asset/custom-node references, static portability signals. Dependencies/platform/runtime are owned by G2/G3/G4.

---

## 1. Verdict (TL;DR)

1. **A portable Workflow in the current product = a `Workflow` identity + one or more immutable `WorkflowVersion` records + exactly-one `Mapping` per version + version-scoped `WorkflowPreset`s.** The portable payload is the *capture pair*: `graph_json` (verbatim ComfyUI UI/LiteGraph serialization) and `api_prompt_json` (verbatim ComfyUI `{workflow, output}` API format), plus derived `dependency_metadata`.
2. **Canonical authority for graph identity is the canonical SHA-256 of the *executable prompt* (`api_prompt_json.output`)** via `production_workflow._canonical_workflow_hash` (sort_keys, compact separators, ensure_ascii=False, allow_nan=False). `graph_json` is stored but is **not** part of the hash.
3. **Exact round-trip: PROVEN for what is persisted, on the real corpus.** Stored `graph_hash` recomputes identically from stored bytes for both corpus versions; save/load performs no normalization, no rewriting, no node stripping, no ID regeneration, no default insertion, no schema migration. One deliberate lossy rule exists at capture time (see §4.3).
4. **The corpus is clean of host-bound values**: zero absolute paths, zero drive letters, zero localhost/IPs in any workflow store; URLs appear only inside embedded markdown note text (data, not functional).
5. **Model references are basenames** (`z_image_turbo_bf16.safetensors`) → portable-with-mapping. **Input assets are basenames resolved against local `input/`/`output/` dirs at plan-build time** → raw workflow JSON alone cannot recreate asset references elsewhere.
6. **Custom-node identity evidence exists but is partially unreliable** (several registry rows carry `repo_url` pointing at the ComfyUI repo instead of the true node repo) and 3 of 39 corpus classes are unresolved by the registry snapshot.

---

## 2. Architecture Map — UI → API → Store → Serialization → Execution

### 2.1 Modern domain (V2, authoritative)

```
ComfyUI frontend (web/)
  studio-backend-capture.js::captureCurrentComfyGraph()
      graph.serialize()          -> graph_json      (LiteGraph UI JSON, verbatim)
      app.graphToPrompt()        -> api_prompt_json ({workflow: <UI copy>, output: <API prompt>}, verbatim)
        │  POST /comfymodal/studio/workflows/import   (create + first version)
        │  POST /comfymodal/studio/workflows/{id}/versions   (new version capture)
        ▼
studio_workflow_routes.py (HTTP translation only; no mutation of capture)
        ▼
studio_domain/services.py::WorkflowDomainService
  create_version_from_capture():
      graph_hash       = graph_hash_from_capture(capture)
                         = _canonical_workflow_hash(extract_executable_prompt(api_prompt_json))
      dedupe           : same hash within workflow -> REUSE latest matching version (idempotent re-capture)
      executable_prompt= extract_executable_prompt(api_prompt_json)   # "output" sub-dict preferred
      graph_json       = dict(capture["graph_json"])                  # shallow top-level copy
      api_prompt_json  = dict(capture["api_prompt_json"])             # shallow top-level copy
      dependency_metadata = {model_stack: extract_model_stack(prompt),
                              node_classes: sorted(class_types)}
      compatible_models   = copied from Workflow record
  create_mapping_revision(): copies graph_json/api_prompt_json/executable_prompt/graph_hash
                         VERBATIM from source version; new wv_id + new Mapping (graph-hash dedupe bypassed)
        ▼
studio_domain/store.py::WorkflowDomainStore  (write-once versions; insert-only mappings)
        ▼
studio_store.py::StudioJsonStore  (thread-safe, tmp+os.replace atomic,
                                   json.dump(indent=2, ensure_ascii=False); NO transform)
        ▼
<node_dir>/.studio_workflows.json / .studio_workflow_versions.json /
          .studio_workflow_mappings.json / .studio_workflow_presets.json
```

Run path (does not mutate stored graphs):

```
GET .../{id}/run-context            -> bundle {workflow, version, mapping, default_preset, state, control_schema}
studio_workflow_run.py::build_workflow_execution_plan(bundle, values, ...)
    apply_workflow_values_to_prompt()  : deepcopy(executable_prompt); write mapped values VERBATIM;
                                         read-back assert identical (hard error on mismatch)
    _repair_missing_clip_inputs/_repair_missing_vae_inputs   # run-time repair on the COPY only
    workflow_hash = prompt_sha256(applied prompt)
    output_node_ids = [mapping.output_node_id]   (mandatory)
    production: canonical_execution.build_execution_plan(...)  -> frozen ExecutionPlan
                (embeds compiled workflow, model_stack, input_images base64, validation proof,
                 deployment_identity, request_metadata incl. selected_gpu + studio meta)
    non-production: direct ExecutionPlan(workflow=applied copy, ...)
        ▼
RequestSnapshot (history_v2_models.py) persisted in SQLite <data_root>/.studio_history_v2/history_v2.db
    columns: workflow_json, request_json, execution_plan_json, deployment_identity_json,
             workflow_hash, workflow_version_id, generation_params, preset_snapshot
```

### 2.2 Other persistence surfaces inventoried

| Surface | File/Location | Status | Portability relevance |
|---|---|---|---|
| Workflow / Version / Mapping / Preset | `.studio_workflows.json`, `.studio_workflow_versions.json`, `.studio_workflow_mappings.json`, `.studio_workflow_presets.json` | **Canonical modern store** | The portability payload |
| Legacy Snapshot | `.studio_snapshots.json` (`graphJson`/`apiPromptJson`, camelCase, `nodeBindings`, `controlSchemas`) | Legacy, still written by snapshots page & read by `studio_run_adapter.py` | Same verbatim-capture pattern; superseded shape |
| Legacy Preset | `.studio_presets.json` (`preset_*` ids, `snapshotId` ref) | Legacy | References snapshot, no graph bytes |
| Playground selection | browser localStorage (`studio-playground-state.js`) — stores **only** `presetId` + `featureId`; drafts/results caches | Ephemeral UI state | Not part of workflow portability |
| Experiments (modern) | `experiment_modern_plan.py` resolves `(workflow_id, workflow_version_id, preset_id)` bundles through the same domain service; cells reference versions, never embed graphs | Reference-only | Portable by construction |
| Experiment presets/state | `.comfymodal_experiments/comfymodal_experiment_*.json` | Runtime tuning knobs | Not workflow data |
| History V2 / RequestSnapshot | `<data_root>/.studio_history_v2/history_v2.db` (SQLite) | **Not present on this machine** (no DB found) | Immutable per-run replay record |
| Model Library | `.studio_model_library.json` | Local registry | Contains absolute Windows `local_path` — env-bound, but NOT part of workflow JSON |
| Custom-node registry | `.studio_custom_nodes.json` | Local registry | `repo_url`+`installed_commit`+`classes`; some rows have wrong `repo_url` (see §7) |

### 2.3 Import/export today

- **Import**: `POST /workflows/import` accepts a capture body (`graph_json` + `api_prompt_json`) — i.e., import-from-live-capture exists; there is no file-upload import endpoint.
- **Export**: none for workflows. `history_v2_export.py` exports history/generation records (F-lane), not workflow files. The portable-manifest module exists but is **unwired** (§6).

---

## 3. Canonical Source-of-Truth per Layer

| Layer | Authority | Notes |
|---|---|---|
| Graph bytes | HTTP capture body (frontend `graph.serialize()` + `app.graphToPrompt()`) | Passed through untouched by routes/service |
| Graph identity | `_canonical_workflow_hash(executable_prompt)` — sha256 over canonical JSON of `api_prompt_json.output` | Single implementation; fail-closed on NaN/Inf; shared with manifest module and history |
| Version immutability | `WorkflowDomainStore.insert_version` (write-once; raises `ImmutableVersionError`) | No update/delete path exists |
| Mapping | `insert_mapping` — exactly one per version, immutable after insert | Edits create new version via `create_mapping_revision` |
| Preset values | `.studio_workflow_presets.json` rows | Validated against mapping kinds/bounds; `0/False/""/0.0` are valid values |
| Derived state | computed at read time (`derive_version_state` + `DependencyResolver.reasons_for`) | Never persisted on the version record |

---

## 4. Exact-JSON Fidelity Verdict

### 4.1 What is preserved (observable fact)

Verified against code paths AND recomputed on the live corpus:

- **Node IDs** — preserved verbatim in both representations, including composite subgraph IDs (`"935:481"`, `"1149:1146"`) present in the corpus.
- **Node class/type** — preserved (`class_type` in API prompt; `type` in UI graph).
- **Widget inputs** — preserved verbatim (`inputs` dicts).
- **Links** — preserved (`links` array in UI graph; `["<node>", slot]` connection specs in API prompt).
- **Graph structure** — full LiteGraph payload preserved: `id, revision, last_node_id, last_link_id, nodes, links, groups, definitions (subgraphs!), config, extra, version`.
- **Frontend-only fields** — preserved: `pos`, `size`, `flags`, `order`, `mode`, `title`, `widgets_values`, `properties` (incl. `aux_id` custom-node provenance like `"kijai/ComfyUI-KJNodes"`), `extra.ds` view state, `reroutes`, `ue_links` (Anything Everywhere virtual links), `linkExtensions`, `frontendVersion`, `workflowRendererVersion`.
- **Unknown/custom fields** — no schema filter anywhere in the chain; unknown keys survive.
- **Ordering** — Python `json.load`/`json.dump` preserve document key order; list order untouched. Stored key order == frontend serialization order.

### 4.2 What save/load does NOT do (observable fact)

No normalization, no rewriting, no node stripping, no model-path rewriting, no ID regeneration, no default insertion, no schema migration, no lossy conversion. `StudioJsonStore` is a plain atomic `json.dump`. The only transformations anywhere near the path:

1. Shallow top-level `dict(...)` copies (values shared, never mutated afterwards).
2. `extract_executable_prompt` selects `api_prompt_json["output"]` as the executable view (a projection, not a rewrite).

### 4.3 Deliberate non-exactness rules (observable fact)

- **Hash scope**: identity covers ONLY the executable prompt. Two captures with different `graph_json` but identical API prompts dedupe to the SAME version (`test_workflow_domain.py:249` codifies this). Consequence: **UI-only edits (positions, titles, layout) after an earlier capture are silently discarded on re-capture** — the newer `graph_json` never lands. This is the single intentional fidelity gap.
- **Mapping revisions intentionally duplicate identical graph bytes across versions** (allowed; dedupe bypassed; asserted equal at `test_workflow_domain.py:761`).

### 4.4 Deterministic corpus verification (executed during this audit, read-only)

Script over `.studio_workflow_versions.json` using the production hash function:

```
wv_8821af78d5c8408d  stored 7911b4070925df26…  recomputed 7911b4070925df26…  MATCH
wv_487585a9c3cb4f32  stored 7911b4070925df26…  recomputed 7911b4070925df26…  MATCH
graph_json canonical-equal across v1/v2: True
api_prompt_json canonical-equal across v1/v2: True
```

Corpus structure confirms: `api_prompt_json = {workflow: <full UI-format copy>, output: <60-node API prompt>}` — the UI graph is effectively stored twice (top-level `graph_json` + `api_prompt_json.workflow`).

### 4.5 Residual fidelity risks (inferred, not observed)

- `json.dump` default `allow_nan=True`: a NaN/Infinity widget value would be written as non-standard JSON literals; the canonical hash would then fail closed (empty hash → `GraphHashError` at capture), so this cannot silently corrupt identity — but it would make the store file non-interoperable JSON. Not observed in corpus.
- Float round-trip through CPython `repr` is exact for doubles; JS numbers are doubles; safe.
- No test currently proves byte-level `graph_json` equality across a full HTTP POST → store → GET cycle with a *large realistic* graph (domain tests use small fixtures; corpus check above covers storage-side equality only).

---

## 5. Environment-Specific Value Scan (corpus + contracts)

Regex sweeps over ALL persisted workflow stores (`.studio_workflow_versions.json`, `.studio_snapshots.json`, mappings, presets):

| Pattern class | Hits | Classification |
|---|---|---|
| Windows drive-letter paths (`X:\...`) | **0** | — |
| POSIX absolute paths (`/home`, `/mnt`, `/tmp`, …) | **0** | — |
| localhost / IP addresses | **0** | — |
| `input/`/`output/`/`temp/` directory refs | **0** | — |
| External URLs (`https://huggingface.co/...`, github) | Present — **inside markdown note/title text only** (model download instructions embedded by the original workflow author) | portable (data, not functional) |
| API keys / secrets / tokens | **0** | — |
| Device/GPU identifiers | **0** in workflow stores; `selected_gpu` lives in ExecutionPlan `request_metadata` (run-time artifact, not workflow JSON) | environment-bound but outside the portable payload |
| Absolute paths | Present in `.studio_model_library.json` (`local_path`) and `.studio_custom_nodes.json` (`install_path`) — **local registries, NOT workflow JSON** | environment-bound; must never be exported with a workflow |
| `filename_prefix` (SaveImage) | `"z-image"` — relative prefix | portable |
| ComfyUI folder aliases | model refs are bare filenames relying on standard folder resolution (`diffusion_models`, `text_encoders`, `vae`) | portable-with-mapping |

Conclusion: **the saved workflow JSON itself is environment-clean**. Environment binding enters only through (a) basename→local-folder resolution semantics, (b) input-asset file presence, (c) installed custom-node set, (d) run-time plan metadata (GPU, comfyui_root).

---

## 6. Model References

Inventory of how the corpus identifies models (all in `executable_prompt.inputs`):

| Node | Class | Input | Value form | Class |
|---|---|---|---|---|
| 66 | UNETLoader | `unet_name` | `z_image_turbo_bf16.safetensors` | basename |
| 62 | CLIPLoader | `clip_name` | `qwen_3_4b.safetensors` (+ `type: "lumina2"`) | basename |
| 1277 | VAELoader | `vae_name` | `ae.safetensors` | basename |
| 151 | **ModelPatchLoader** (custom) | `name` | `Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors` | basename |

- Form: **basename only** (ComfyUI convention: resolved against configured folder `models/<bucket>/<subfolders>`). No absolute paths, no provider IDs, no product abstraction inside the JSON.
- Extraction coverage gap (observable): `workflow_metadata._LOADER_MAPPINGS` / `_MODEL_REF_MAPPINGS` cover CheckpointLoader(Simple), UNETLoader, CLIPLoader, DualCLIPLoader, VAELoader, LoraLoader*, ControlNetLoader. **`ModelPatchLoader` is not covered**, so the corpus's ControlNet-Union patch model appears in `executable_prompt` but NOT in `dependency_metadata.model_stack` — the dependency resolver therefore cannot report it missing/wrong-version. Any third-party loader class has the same blind spot.
- Hashes: model library rows mostly have empty `hash` (only tiny `.metadata.json` sidecars got hashed); `source_urls` empty. So today's corpus cannot pin model bytes — portability scoring must treat model identity as filename-only (MEDIUM-class evidence).
- Product abstraction exists OUTSIDE the JSON: `compatible_models` on Workflow/Version + preset `model_choices` validated against it (portable semantic layer, still basename-keyed).

## 7. Input / Asset References

- LoadImage-family nodes persist **basenames** (optionally suffixed `" [output]"` / `" [input]"` / `" [temp]"`).
- At plan build, `canonical_execution._collect_input_images()` resolves those names against `<comfyui_root>/input|output(/temp)` and **base64-embeds the bytes into `ExecutionPlan.input_images`**. http(s) URLs are skipped (passed through as-is).
- Therefore: **raw workflow JSON alone is sufficient to recreate the GRAPH elsewhere, but NOT the user assets.** Workflow portability ≠ workflow+assets portability. An export format that omits referenced input files yields a workflow that imports cleanly but cannot run without manual asset placement. The unwired manifest format already models this correctly (`assets` reference records with sha256/size/mime/role).
- Current corpus contains no LoadImage nodes (txt2img-only), so asset-binding risk is structural, not yet exercised.

## 8. Custom-Node Identity (corpus classification)

Using `.studio_custom_nodes.json` (23 repos, classes lists) + core-node knowledge:

- **Total distinct class_types in corpus version 1: 39**
- **Core ComfyUI (14)**: SaveImage, CLIPLoader, UNETLoader, CLIPTextEncode, EmptySD3LatentImage, VAEDecode, VAELoader, ConditioningZeroOut, ModelSamplingAuraFlow, PrimitiveFloat, PrimitiveStringMultiline, PairConditioningSetProperties, ImageRotate, EmptyImage
- **Registry-matched custom (22)** spanning ≥10 repos: cg-use-everywhere, rgthree-comfy, ComfyUI-CacheDiT, RES4LYF, Impact Pack (+SE `CombineHooks8`? see below), KJNodes, LayerStyle, comfyui_essentials, comfyui-levelpixel, comfyui-custom-scripts (pysssss), comfyui-easy-use, comfyui_lg_samplingutils
- **Unresolved by registry snapshot (3)**: `CombineHooks8` (Impact Pack SE — repo present but class not listed), `CustomCombo`, `ModelPatchLoader`
- **Evidence-quality caveat (observable)**: several registry rows carry `repo_url: https://github.com/Comfy-Org/ComfyUI` with the ComfyUI commit while `name` says e.g. `rgthree-comfy` — discovery fell back to the host repo URL. Revision pinning for those rows is **unreliable**; portability evidence must prefer UI-graph `properties.aux_id` (present in corpus, e.g. `kijai/ComfyUI-KJNodes`) and treat registry `repo_url` as secondary until fixed.
- Subgraph usage: corpus carries `definitions.subgraphs` (frontend ≥1.44 feature). Older ComfyUI frontends cannot load these — a version-compatibility hazard independent of node availability.

---

## 9. Static Portability Signals (proposal — design only, nothing implemented)

All computable WITHOUT execution, from persisted records + local registries. Each signal states observable-fact vs inferred-risk.

| # | Signal | Source (static) | Type |
|---|---|---|---|
| S1 | `has_absolute_path` — drive-letter/POSIX-abs regex over graph_json + api_prompt_json + preset values | version record | observable fact |
| S2 | `has_unresolved_node_type` — class_type ∉ (core set ∪ registry classes) | dependency_metadata.node_classes + registries | observable fact (relative to local evidence) |
| S3 | `custom_node_count` / `custom_repo_count` | node_classes × registry | observable fact |
| S4 | `custom_node_revision_pinned` — every custom repo has trusted repo_url + commit | registry + aux_id cross-check | observable fact (with trust caveat §8) |
| S5 | `model_ref_basename_only` — all loader refs match `[^\\/:]+\.safetensors`-style basenames | executable_prompt | observable fact |
| S6 | `model_hash_pinned` — every model ref resolvable to library row with non-empty sha256 | model library | observable fact |
| S7 | `model_extraction_gap` — string-valued inputs on loader-suffixed classes not covered by `_MODEL_REF_MAPPINGS` (e.g. ModelPatchLoader) | executable_prompt | observable fact |
| S8 | `requires_input_asset` — LoadImage/LoadVideo/LoadAudio/LoadMask/VHS_Load* classes present | node_classes | observable fact |
| S9 | `has_external_endpoint` — http(s) values in functional positions (inputs), excluding note text | api_prompt_json | observable fact |
| S10 | `uses_subgraphs` — `definitions.subgraphs` non-empty | graph_json | observable fact (frontend-version risk) |
| S11 | `exact_roundtrip_proven` — stored graph_hash == recomputed canonical hash AND graph_json/api_prompt_json canonical-stable | version record | observable fact |
| S12 | `env_bound_registry_leak` — export would include `local_path`/`install_path` fields | export seam review | inferred risk (future-proofing) |

Risk mapping (proposed criteria, derived from this repository's actual evidence model — mirrors `DependencyResolver` states):

- **LOW** — S1 false ∧ S2 false ∧ S8 false ∧ S10 false ∧ all model refs basename-only (S5) ∧ S11 true. Core-only or fully-resolved custom nodes with pinned revisions. (Importable anywhere ComfyUI runs; models need manual placement.)
- **MEDIUM** — LOW conditions hold except: known custom nodes required (S3>0) even if unpinned, OR model hashes unpinned (S6 false), OR extraction gaps (S7), OR requires input assets (S8) that must travel separately. Reproducible setup needed; failure mode is explicit ("missing model/node").
- **HIGH** — S2 true (unknown/unresolvable node types), OR S1 true (host paths baked in), OR S9 true (external endpoints in functional inputs), OR revision-pinning impossible (S4 unresolvable), OR subgraph/frontend-version constraints (S10) combined with custom nodes. Failure mode may be silent or require unavailable artifacts.

A score must embed the triggering signal list (explainability requirement); every signal above maps to a concrete field/range in existing stores.

---

## 10. Corpus Results (per-Workflow table)

Local corpus = 1 workflow, 2 versions, 2 mappings, 2 presets (+1 legacy snapshot, +1 legacy preset). No secrets present; note-text URLs are public HF/github links (redacted to host+path-shape below where long).

| Field | Value |
|---|---|
| Workflow | `wf_9bbcfc104a35412d` "Smoke Test Workflow" (default preset `wpres_8c8d7555c36a4450`) |
| Versions | `wv_8821af78d5c8408d` (v1), `wv_487585a9c3cb4f32` (v2, mapping revision — identical graph bytes, hash `7911b4070925df26…`) |
| Node count | 176 UI nodes / 150 links / 60 API-prompt nodes; subgraph definitions present |
| Core / custom / unknown | 14 core / 22 registry-matched custom / 3 unresolved (`CombineHooks8`, `CustomCombo`, `ModelPatchLoader`) |
| Model refs | clip `qwen_3_4b.safetensors`, unet `z_image_turbo_bf16.safetensors`, vae `ae.safetensors` (basenames; hashes unpinned) + **untracked** patch model via ModelPatchLoader (extraction gap S7) |
| Path-bound refs | none |
| External asset refs | none (no LoadImage family) |
| External endpoints | none functional (URLs in note text only) |
| Round-trip | PROVEN on both versions (hash recompute MATCH; v1≡v2 canonical bytes) |
| Provisional static risk | **MEDIUM** — heavy multi-repo custom-node set (≥10 repos) with partially unreliable revision pinning + one extraction-gap model + subgraph definitions; no host paths, no external endpoints, no missing assets. Explainable triggers: S3>0, S4 partial, S6 false, S7 true, S10 true. |
| RequestSnapshot corpus | **EMPTY locally** — `.studio_history_v2/history_v2.db` does not exist on this machine; snapshot-based analysis deferred until a DB exists (schema supports `workflow_json`/`execution_plan_json`/`deployment_identity_json`). |

Legacy surface: `snap_0f15d89f6c7b4fa8` "7-30-26" — same verbatim-capture pattern, camelCase keys, `nodeBindings` map roles→nodes; same env-clean result.

---

## 11. Round-Trip Test Plan (minimal deterministic future tests — no implementation in G1)

1. **Export-bytes test**: serialize a Version (`graph_json`, `api_prompt_json`) to a workflow file; assert `sha256(canonical(graph_json))` and `sha256(canonical(api_prompt_json))` unchanged vs store bytes.
2. **Import-idempotence test**: POST exported file to `/workflows/import`; assert new version's `graph_hash` == source `graph_hash`, and canonical bytes of both payloads identical.
3. **Re-import stability**: importing the SAME file twice yields same graph_hash (dedupe) and does not create extra versions.
4. **Mapping/preset survival**: imported version accepts a mapping + preset; `copy-to-version` forward preserves values verbatim (read-back assertion already implemented in `apply_workflow_values_to_prompt` — reuse pattern).
5. **Hash-semantics test**: `manifest_hash(m, include_metadata=True)` changes when metadata changes; `include_metadata=False` stable — pins the "timestamps excluded from identity" contract before wiring.
6. **Unknown-field preservation**: graph containing alien keys/types round-trips untouched (exists at manifest level: `test_unknown_executable_content_treated_as_data`; add store-level equivalent with a large realistic graph).
7. **NaN fail-closed**: capture containing NaN raises `GraphHashError` and writes nothing.
8. **Snapshot parity**: for a generation with RequestSnapshot, `snapshot.workflow_hash` == version `graph_hash` and `execution_plan_json.workflow` canonicalizes to the applied prompt (plan rebuild determinism).

## 12. Recommended Implementation Seams (exact)

1. **Export/import routes**: `studio_workflow_routes.py` — new `GET /workflows/versions/{version_id}/export` and `POST /workflows/import` (file variant) assembling via `build_manifest(workflow=..., version=..., mapping=..., presets=..., models=..., custom_nodes=..., assets=...)` from `studio_workflow_manifest.py` (pure, stdlib-only, tested; deliberately unwired today — `WORKFLOW_MANIFEST_FORMAT.md` §10 pre-registers these exact wiring points). Use `parse_manifest` on import; `check_readiness` as pure pre-check; keep all I/O in the route layer.
2. **Static signals**: extend `dependency_resolver.py::resolve_version` (already returns models/custom-nodes states + summary; never raises) with signals S1–S12; feed `reasons_for` so LOW/MEDIUM/HIGH derives from the same evidence path the UI already displays.
3. **Extraction-gap fix**: add configurable loader mappings in `workflow_metadata.py::_MODEL_REF_MAPPINGS` (or derive from registry classes ending in "Loader") to close S7 (ModelPatchLoader et al.).
4. **aux_id provenance**: harvest `properties.aux_id` from `graph_json.nodes[]` into `dependency_metadata.custom_node_requirements` at capture time (`studio_domain/graph.py::extract_dependency_metadata`) to pin repo identity independently of the buggy registry `repo_url`.
5. **Asset manifests**: on capture, record LoadImage-family basenames into `dependency_metadata` (S8 evidence) so export can emit `assets` reference records (sha256 optional) without embedding bytes.
6. **Never export** `.studio_model_library.json` `local_path` / `.studio_custom_nodes.json` `install_path` fields; export only `filename/folder/hash/source_urls/repo_url/revision/classes`.

## 13. Questions Requiring G2/G3 Evidence

- G2 (dependencies): is the registry `repo_url`=ComfyUI fallback a discovery bug to fix, and can `installed_commit` be trusted per-repo? Which of the 22 custom classes resolve on RunPod/RunComfy/Cloud images?
- G2: model acquisition story for basename refs (which provider fills `source_urls`/`sha256`?) — determines whether MEDIUM can ever be raised to LOW.
- G3 (platform/runtime): do target platforms accept subgraph `definitions` (frontend ≥1.44) and `ue_links`/reroutes in UI JSON? Does Comfy Cloud strip frontend-only fields on import?
- G3: is `api_prompt_json.workflow` (embedded UI copy) needed by any target, or should export carry `graph_json` + `output` only (halving payload)?
- G4 (product): should export include presets/mappings (product-specific semantics) or raw-JSON-only mode for maximum interop?

## 14. Constraints Compliance

Production code modified: NONE · Tests modified: NONE · Deploy/live/GPU/generations: NONE · Commit/push/branch/worktree/reset: NONE · Files created: this audit only.
