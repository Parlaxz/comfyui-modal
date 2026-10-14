# PHASE 9 — Guidance Architecture Correction (RESEARCH/DESIGN ONLY)

Status: COMPLETE

Research base commit: 3457bbba (`research(studio-v3-phase9): guidance research handoff`)

Worktree: `.slim/worktrees/studio-v3-phase9-guidance-architecture-correction`

Branch: `research/studio-v3-phase9-guidance-architecture-correction`

Existing report (retained, not modified): `STUDIO_V3_PHASE9_GUIDANCE_RESEARCH.md`

This file: `STUDIO_V3_PHASE9_GUIDANCE_ARCHITECTURE_CORRECTION.md` (only file produced)

No production code was touched. No merges performed.

---

## 1. Why this correction exists

The base research report is retained as the **evidence base** (ecosystem tables, preprocessor tiers,
license audit, UX state copy). Its Section "Concrete implementation plan", step 7 — a curated proposal
table scoped as "Qwen-1.x + FLUX.1-dev Canny/Depth/Pose" — and its mapping record fields `family` /
`base`, read naively, invite this production shape:

```text
if Qwen: ...
elif Flux: ...
elif Krea: ...
```

That shape is rejected. V3 is model-agnostic and graph-structural. Every model/provider-specific fact
must live in **data**; every structural operation must live in **generic mechanism code** that never
names a model family.

---

## 2. Corrected architecture

```text
loaded diffusion model
  → resolve exact SHA-256 (Model Library join, pre-run, on base workflow)
  → load confirmed mapping for (model_sha256, guidance mode)   [DATA lookup]
  → mapping says: mechanism + controller checkpoint + preprocessor + node types + defaults
  → generic structural mechanism adapter, selected by mechanism NAME STRING ONLY
  → anchor discovery (structural walk, no family knowledge)
  → temporary graph copy (deepcopy, existing pattern) + validate + execute + discard
```

Hard rule: **no code path takes a different branch based on model family, provider, or checkpoint
name.** The executor's only decision is `ADAPTERS[mapping.mechanism]`. An unknown mechanism string
fails closed with "mapping requires mechanism X, not implemented in this Studio version".

---

## 3. Minimal generic mapping schema

One record per `(model_sha256, mode)`. Key is the pair; nothing else is keyed.

```json
{
  "model_sha256": "sha256:<full diffusion-model file digest>",
  "mode": "canny | depth | pose | <future>",
  "mechanism": "CONTROLNET_CONDITIONING | MODEL_PATCH | CONTROL_LORA",
  "controller": {
    "checkpoint": "<exact filename, e.g. flux1-dev-controlnet-union-pro-2.safetensors>",
    "folder": "controlnet",
    "checkpoint_sha256": "<hex when published, else null>",
    "source_url": "<evidence URL — data only, never fetched by executor logic>",
    "license": "<SPDX or license name — data only>"
  },
  "nodes": {
    "loader": "<exact ComfyUI class_type, e.g. ControlNetLoader>",
    "apply": "<exact ComfyUI class_type, e.g. ControlNetApplyAdvanced>",
    "preprocessor": "<exact ComfyUI class_type, e.g. CannyEdgePreprocessor>"
  },
  "conditioning": { "strength": 0.7, "start": 0.0, "end": 0.8 },
  "suggest": {
    "family": "<hint only, e.g. flux1-dev>",
    "display_filename": "<hint only>"
  },
  "evidence": { "workflow_url": "<official example>", "verified_for": "<exact base model>" },
  "audit": { "confirmed_at": "<iso8601>", "mapping_revision": 1 }
}
```

Schema rules (normative):

1. Executor, identity resolver, mapping store, anchor discovery, and adapters **MUST NOT read**
   `suggest.*`, `evidence.*`, `controller.source_url`, or `controller.license` for any control-flow
   decision. These fields exist for UI display and audit only. A test asserts this by executing a
   mapping whose `suggest`/`evidence` fields are deliberately wrong — execution must still succeed
   (or fail only on structural grounds).
2. `nodes.*` class_type strings come from data, constrained at confirm-time to node types actually
   installed (ComfyUI `object_info`). The adapter then **validates slots structurally** before wiring
   (required inputs present with compatible types). Unvalidated node strings are never instantiated.
3. `conditioning.*` defaults are data; adapters clamp to sane ranges but never substitute providers.
4. No `family`/`base`/`provider` field outside `suggest`. The base report's `family` + `base`
   mapping fields are hereby **reworded to `suggest.family` (hint, non-keyed)**.
5. Store is CRUD keyed by `(model_sha256, mode)` plus revision/audit. No registry queries by family,
   no capability matrix, no versioned provider tables in code.

---

## 4. Minimal real mechanism vocabulary

Exactly three mechanisms are specified. Each is a **structural contract**, named without any model
reference. Only mechanisms with concrete workflow evidence are retained.

### 4.1 CONTROLNET_CONDITIONING

Classic ControlNet: a separately loaded controller wraps the sampler's conditioning inputs.

- Evidence: FLUX Union / InstantX / X-Labs ComfyUI graphs (`ControlNetLoader → [SetUnionControlNetType]
  → ControlNetApplyAdvanced → sampler`); Qwen InstantX workflow (official ComfyUI docs JSON).
- Required anchors: (a) one sampler with discoverable `positive` + `negative` conditioning inputs;
  (b) the conditioning producer nodes feeding them; (c) a guide-image source slot.
- Transform on the deep copy only:
  1. append `nodes.preprocessor` fed by the guide image;
  2. append `nodes.loader` with `control_net_name = controller.checkpoint`;
  3. append `nodes.apply` with `control_net` ← loader, `image` ← preprocessor output,
     `conditioning` ← original positive/negative producer outputs (both, where the Apply node
     exposes both), `strength/start/end` ← `conditioning.*`;
  4. rewire sampler positive/negative inputs ← Apply outputs.
- Validation: sampler has exactly one intended instance (or a user-confirmed anchor id); Apply node
  exposes the slots the mapping claims; preprocessor output type matches `Apply.image`; mutated copy
  passes normal ComfyUI validation.
- Fail closed: multiple samplers; custom sampler without recognizable conditioning inputs;
  already-controlled graph (existing ControlNet/Control-LoRA/IP-Adapter/Kontext conditioning with
  unclear ordering); slot mismatch on any of the three node types.

### 4.2 MODEL_PATCH

A patch module is loaded and applied to the diffusion model object itself.

- Evidence: Qwen DiffSynth Canny/Depth patches via ComfyUI model-patch loader nodes
  (official ComfyUI Qwen docs + `Comfy-Org/Qwen-Image-DiffSynth-ControlNets`).
- Required anchors: (a) the diffusion-model loader output edge feeding the sampler's `model` input;
  (b) a guide-image/preprocessed-image entry the patch node consumes.
- Transform on the deep copy only: append patch-loader node (`controller.checkpoint`), insert it on
  the model edge (loader output → patch → sampler `model` input), attach preprocessed guide image.
- Validation: single model edge to the intended sampler; patch node slot contract verified
  structurally; copy validates.
- Fail closed: multiple model loaders feeding different sampler branches; patch node class not
  installed; guide input contract unknown; graph already contains a model-patch path.

### 4.3 CONTROL_LORA

A LoRA adapter modifies the base model; the control image enters through the conditioning/context path.

- Evidence: Qwen DiffSynth Union Control LoRA (`LoraLoaderModelOnly` workflow, official ComfyUI JSON);
  community Krea-2 depth Control-LoRA graph shape (Loader → Encode → Apply).
- Required anchors: (a) the diffusion-model loader output; (b) the conditioning/context entry the
  LoRA'd model consumes; (c) guide-image slot.
- Transform on the deep copy only: append LoRA loader (`controller.checkpoint`) on the model edge,
  route the preprocessed control image into the conditioning entry per the mapping's slot contract.
- Validation and fail-closed: as MODEL_PATCH, plus refusal when the LoRA/context slot contract
  cannot be established structurally.

### 4.4 Deliberately excluded: NATIVE_CONTROL_INPUT

The base report documents a fourth shape — BFL `FLUX.1-Canny-dev` / `Depth-dev` concatenated-control
transformers (`FluxControlPipeline`, control channels at transformer input). It is **excluded from the
mechanism vocabulary and from V1** for two independent reasons:

1. It replaces the *model itself* with a different checkpoint, which breaks the "same exact model
   identity executes" invariant the whole mapping design rests on (the mapping is keyed by the base
   model hash, but execution would load different weights).
2. It inherits the FLUX.1-dev Non-Commercial license; routing V1 through it maximizes legal exposure
   for zero coverage gain (community ControlNets cover Canny/Depth/Pose on `FLUX.1-dev` via 4.1).

If ever needed, it must be proposed as a new mechanism contract with an explicit
replacement-model identity rule — not smuggled into an existing adapter.

### 4.5 V1 mechanism scope

**V1 implements exactly one adapter: CONTROLNET_CONDITIONING.** It covers every V1
(base × mode) pair: Qwen-Image 1.x Canny/Depth/Pose via InstantX Union; FLUX.1-dev Canny/Depth/Pose
via Union Pro 2.0 (or InstantX equivalents). MODEL_PATCH and CONTROL_LORA are **specified above
(contracts frozen) but not implemented** until a V1-excluded mode demands them — adding one later
means one new adapter module registered under its name string plus data rows; no existing code path
changes (extension without modification).

---

## 5. Which modules/functions are model-agnostic (normative list)

| Component | Contract | Must never contain |
|---|---|---|
| Identity resolver | loader `(folder, filename)` → Model Library → verified `sha256` | family/provider conditionals; filename-trust fallback |
| Mapping store | CRUD by `(model_sha256, mode)`; revision/audit; returns opaque record | family-keyed queries; proposal logic |
| Anchor discovery | connection-tuple walk → sampler / conditioning producers / model edge / guide slot, or ranked ambiguity | node-name allow-lists per provider; family-specific slot names |
| Mechanism adapters (one module per §4) | `(graph_copy, anchors, mapping, guide_image) → mutated_copy or Refusal` reading only `nodes.*`, `controller.checkpoint/folder`, `conditioning.*` | any model/provider/checkpoint/family string literal |
| Executor | `ADAPTERS[mapping.mechanism]` dispatch; deepcopy → adapt → validate → run → discard | `if/elif` on anything except mechanism-name lookup miss |
| Proposal UI | reads proposal **data file** (§6); renders evidence; collects Confirm/Change | hardcoded provider branches, per-family panels |
| History writer | fixed schema: mode, `model_sha256`, mechanism, checkpoint (+hash), preprocessor node, mapping revision, failure cause | provider-specific fields or sub-schemas |

Shared refusal type: adapters and discovery return a structured `Refusal(reason, candidates?)`
where `candidates` (e.g. anchor picks) feed the existing bounded-confirmation UI — never an
automatic choice.

---

## 6. What model/provider knowledge lives only in data

- All provider names, checkpoint filenames/URLs/hashes, family labels, preprocessor recommendations,
  strength defaults, evidence links, license strings.
- Curated built-in recommendations ship as **plain versioned JSON data file(s)**
  (e.g. `guidance_proposals.json`), keyed by `model_sha256` (exact) with a secondary
  family-hint section explicitly marked `untrusted_suggestion`. Updating recommendations =
  replacing the JSON file; **no Python/JS change, no Studio release required for a data update**.
- The proposal UI reads this file and the mapping store only. The executor never imports it.
- Forbidden in code (non-test): `KNOWN_QWEN`, `KNOWN_FLUX`, `KNOWN_*` constants; hardcoded
  checkpoint URLs in executor/adapter logic; hardcoded family compatibility tables in Python/JS;
  provider-specific UI branches; provider-specific History sub-schemas.

---

## 7. Future-model manual flow (acceptance-critical, no code changes)

A model released after this Studio version, usable via an already-implemented mechanism, must be
mappable by the user with zero code changes:

1. Unknown `model_sha256` → `unknown_model` state ("Studio will not guess from the filename").
2. User picks: mode → mechanism (from implemented list) → installed controller checkpoint
   (listed from the Model Library `controlnet` folder — no typed URLs) → installed preprocessor
   node (listed from `object_info`) → guide image.
3. Studio runs anchor discovery on the selected workflow, shows concrete anchors
   (`node id / class_type / input slot`), user confirms (bounded pick if several).
4. Studio validates slots structurally against the chosen node types; any mismatch fails closed
   with the exact missing slot named.
5. User reviews the assembled record (all §3 fields visible, incl. evidence = "manual mapping,
   user-confirmed") → `[Confirm and remember for this model]`.
6. Record saved under `(model_sha256, mode)`; all workflows resolving to the same hash reuse it.
7. If the installed controller later proves structurally incompatible at execution, the run fails
   with the concrete cause preserved in History — the mapping stays until the user changes it
   (no silent invalidation, no silent replacement).

This flow uses only generic UI (lists of installed artifacts + anchor picker + review screen) and
therefore cannot contain provider branches by construction.

---

## 8. Fail-closed graph ambiguity (normative)

Refuse-and-ask-manual (bounded confirmation) or refuse outright when ANY holds:

- zero or ≥2 plausible generation samplers (unless user already confirmed an anchor id for this
  workflow version);
- conditioning producers ambiguous (multiple targets, custom conditioning nodes with unknown contract);
- multiple model loaders feeding different sampler branches;
- graph already contains guidance-type conditioning (ControlNet / Control-LoRA / patch /
  IP-Adapter / Kontext-style) with unclear composition order;
- chosen node types' slots do not match the mechanism contract (missing/untyped slot);
- preprocessor unavailable or output contract unknown — never substitute another preprocessor;
- mapping `mechanism` string has no registered adapter;
- stored anchor binding no longer matches after a graph edit (re-confirm, fail closed);
- `model_sha256` unresolvable (Model Library miss) — never proceed on filename.

Allowed automatic path: exactly one sampler, structurally discoverable conditioning/model-edge
anchors, installed node types with verified slots, confirmed mapping for the exact hash, clean
validation of the mutated copy, stored workflow bytes unchanged.

---

## 9. How we avoid a registry/framework

- The mapping store is a **key-value record file**, not a registry: no queries by family, no
  capability inference, no version negotiation, no provider plugins. Lookup is
  `get(sha256, mode)` — one exact-key read.
- The proposal JSON is a **static data file**, not a framework: no code reads it except the
  proposal panel renderer; no schema migration machinery; rows are added by editing JSON.
- Mechanism dispatch is a **plain dict from name string to module**, not a plugin SDK: no
  registration API, no third-party adapter loading, no dynamic imports. A new mechanism is a
  code change to one new module + one dict entry — accepted, because mechanisms are rare
  (three specified, one in V1) while models are unbounded.
- No background crawler, no package manager, no compatibility service. Missing artifacts resolve
  through existing Model Library / Manager paths.

---

## 10. What remains from the original research (adopted as-is)

- Model-identity strategy and ranking (exact SHA-256 > verified manifest/arch metadata > filename
  display-only), invalidation/rename/cross-workflow rules.
- Ecosystem evidence tables for Qwen / FLUX / Krea (Sections Qwen/FLUX/Krea findings) — adopted
  **as data sources for authoring `guidance_proposals.json` rows**, with `verified_for` base-model
  strings copied into `evidence`, never into code.
- Preprocessor tiers and the single-aggregate-package recommendation
  (`comfyui_controlnet_aux`, pinned commit; Canny → DAv2-S/B → DWPose-ONNX).
- License audit outcomes as shipping constraints: FLUX-dev-derived weights stay NC-blocked
  (reinforces §4.4 exclusion); Qwen InstantX/DiffSynth Apache-2.0 is the clean-license V1 path;
  per-checkpoint preprocessor weight terms verified before bundling/auto-download.
- UX state model and grounded copy (resolving → known/unknown/confirmed/stale/blocked/ready),
  missing-dependency / unknown-model / stale-mapping flows, History provenance field list.
- Execution-copy-only mutation pattern and existing-primitive reuse list
  (Model Library SHA-256 `_sha256_file`, deepcopy sites, Wizard confirm gate, dependency banners).
- V1 mode order Canny → Depth → Pose, Lineart deferred; Krea / Qwen-2.1 / schnell / Klein deferred.

## 11. What is rejected or reworded

| Original | Verdict |
|---|---|
| Implementation step 7: curated proposal table "Qwen-1.x + FLUX.1-dev" as a build step | **Reworded**: the table becomes `guidance_proposals.json` DATA; no build-step code reads family names |
| Mapping fields `family` / `base` alongside identity | **Reworded**: collapsed into non-keyed `suggest.*` hints; executor/store MUST NOT read them (§3 rule 1, tested) |
| Injector "branches on controller mechanism" discovered per family research | **Reworded**: dispatch is `ADAPTERS[mapping.mechanism]` by name string; adapters are family-blind |
| `strength_defaults` as a top-level mapping concept | **Reworded**: `conditioning.*` data consumed only by the adapter's generic strength/start/end wiring |
| V1 covering BFL Canny/Depth-dev native models | **Rejected**: excluded per §4.4 (identity-invariant break + NC license); V1 FLUX coverage comes from community ControlNets via 4.1 |
| Any future text implying per-family executor paths ("FLUX graph shape" as code) | **Rejected**: graph shapes are per-MECHANISM contracts (§4); families appear only in data rows |
| `lineart` record shape reservation | **Rejected**: no speculative schema entries; new modes extend the `mode` string in data when evidence exists |

---

## 12. Implementation order (corrected)

1. **Mapping store + §3 schema** (key-value, `(sha256, mode)` key, revision/audit). No proposal logic.
2. **Identity seam**: loader → Library SHA-256 resolver surfaced pre-run + into run context/History.
3. **Anchor discovery** (structural walk; returns anchors or ranked ambiguity — family-blind).
4. **CONTROLNET_CONDITIONING adapter** (§4.1) + `ADAPTERS` dict dispatch + unknown-mechanism refusal.
5. **Guidance panel states** reusing Wizard/banners (generic copy; zero provider branches).
6. **Manual-map flow** (§7) driven entirely by installed-artifact listings + anchor picker.
7. **History provenance** (fixed generic fields).
8. **Proposal data file** (small: exact-sha rows for validated V1 pairs + marked family-hint section).
9. Contracts for MODEL_PATCH / CONTROL_LORA frozen (§4.2–4.3); implementation deferred until a
   shipped mode requires them.

## 13. Likely files (unchanged set, corrected responsibilities)

- New small: guidance mapping store; `adapters/controlnet_conditioning.py`; `guidance_proposals.json`
  (data); anchor-discovery helper (or extension of `production_workflow.py` walk pattern).
- Touch (additive only): `model_library.py` (resolver helper), `workflow_metadata.py` /
  `studio_domain/graph.py` / `comparison.py` (extraction + copy-pattern reuse), queue/validation
  paths (`__init__.py`, `canonical_execution.py`) for the injector hook on the copy,
  `studio_domain/models.py` + history models (resolved-identity + revision fields),
  `web/studio-workflow-setup-wizard.js` + `studio-graph-binding.js` (confirm + anchor picker),
  `web/studio-model-library.js` + `studio-backend-workspaces.js` (blocked copy),
  `web/studio-history-v2-detail.js` + `studio-run-model.js` (provenance display).

## 14. Tests required (corrected)

- FAST_UNIT (all family-blind by construction):
  - store round-trip + stale-evidence re-review gate; workflow id never selects a mapping;
  - `suggest`/`evidence` poisoning test (§3 rule 1);
  - identity: rename-same-hash reuses, same-filename-changed-hash blocks, cross-workflow share;
  - adapter happy path on synthetic graphs (no real family checkpoints — synthetic node types with
    the mechanism's slot shape); stored-workflow hash unchanged;
  - refusal matrix: multi-sampler, custom sampler, already-controlled, slot mismatch, missing
    preprocessor/checkpoint/node, unknown mechanism string, unresolvable sha, stale anchor binding;
  - manual flow end-to-end on synthetic installed artifacts (no code change to add a "new model");
  - **hardcoding gate test**: assertion over the guidance code surface (see §15).
- HEAVY_LOCAL (explicit only): one execution-copy run per shipped V1 (base × mode) on real weights
  via CONTROLNET_CONDITIONING; never in ordinary FAST verification
  (`python tools/test_perf.py --fast -- tests -m fast_unit`).
- No tests for deferred modes/mechanisms beyond asserting they present `unsupported/unknown` states.

## 15. Explicit NO MODEL-FAMILY BRANCHING acceptance gate

The implementation is REJECTED if any of the following holds:

1. Static: case-insensitive grep for `qwen|flux|krea|instantx|shakker|xlabs|diffsynth|bfl|black.forest`
   over non-test guidance executor/adapter/identity/store/panel code returns any hit
   (comments explaining evidence provenance are allowed only if they contain no branching logic;
   safer: zero hits, evidence links live in data rows).
2. Static: any `if/elif/match/switch` (or dict keyed by family/provider/checkpoint) that selects
   behavior from a model, family, provider, or checkpoint value anywhere in the guidance path.
3. Static: checkpoint URLs, family tables, or provider constants in Python/JS outside
   `guidance_proposals.json`, test fixtures, and the manual-flow's installed-artifact listings.
4. Behavioral: adding support for a new model that fits an implemented mechanism requires any
   change under the guidance code directories (it must be satisfiable via §7 manual flow + data row).
5. Behavioral: provider-specific History fields, provider-specific panel variants, or per-family
   strength/behavior tweaks exist.
6. Schema: mapping lookup accepts any key component other than `(model_sha256, mode)`.

---

*End of correction. The base report remains the evidence base; this document governs the
implementation shape. Where the two conflict, this document wins.*
