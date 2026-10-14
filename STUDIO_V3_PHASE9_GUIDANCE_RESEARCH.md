# PHASE 9 — Guidance Research

Status: COMPLETE

Starting SHA: 977d465395a60c7a04f01b04fd61de83f1a31fe7

Worktree: `.slim/worktrees/studio-v3-phase9-guidance-research`

Branch: `research/studio-v3-phase9-guidance`

Research files:
- `STUDIO_V3_PHASE9_GUIDANCE_RESEARCH.md` (this report; only file produced)

Explorer batch (all completed, read-only, background):
- Explorer A — current model identity (explorer)
- Explorer B — Qwen Guidance (librarian / web)
- Explorer C — FLUX/Klein Guidance (librarian / web)
- Explorer D — Krea Guidance (librarian / web)
- Explorer E — graph structures (explorer)
- Explorer F — preprocessors (librarian / web)
- Explorer G — licensing/dependencies (librarian / web)
- Explorer H — product/UI flow (explorer)

Direct sources (primary; full URLs in sections below):
- `COMFYMODAL_STUDIO_V3_ROADMAP.md` Phase 9 (§1080–1190), adapter anchors (§402–417)
- `COMFYMODAL_STUDIO_V3_FULL_DESIGN_IMPLEMENTATION_RUNBOOK.md` Phase-3 insertion (§923–942), Phase 9 (§1446–1554)
- HF: `InstantX/Qwen-Image-ControlNet-Union`, `Comfy-Org/Qwen-Image-InstantX-ControlNets`, `Comfy-Org/Qwen-Image-DiffSynth-ControlNets`, `Qwen/Qwen-Image-2.1`
- HF: `black-forest-labs/FLUX.1-Canny-dev`, `FLUX.1-Depth-dev`, `FLUX.1-Krea-dev`, `FLUX.2-klein-9B`, `InstantX/FLUX.1-dev-Controlnet-Union`, `Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0`, `XLabs-AI/flux-controlnet-collections`
- Docs: `docs.comfy.org/tutorials/image/qwen/qwen-image`, Diffusers FLUX Canny/Depth control docs, `github.com/black-forest-labs/flux/blob/main/docs/structural-conditioning.md`
- Nodes: `Comfy-Org/ComfyUI` (`nodes_controlnet.py`), `Fannovel16/comfyui_controlnet_aux`, `XLabs-AI/x-flux-comfyui`, `facok/comfyui-krea2-controlnet`, `Tanmaypatil123/Krea-2-controlnet`
- Preprocessors: `huggingface/controlnet_aux`, `yzd-v/DWPose`, `DepthAnything/Depth-Anything-V2`, `lllyasviel/Annotators`
- Model cards / repos checked 2026-10-14. Community sources used only as secondary corroboration.

---

## Existing ComfyModal primitives we should reuse

1. **Model Library SHA-256 + reconciliation** — `model_library.py:104-115` (full SHA-256), `:401-415` (content change → new record, old `installed=False`), `:457-497` (resolve by `(folder, filename)` + SHA-256 + `(size, mtime_ns)` fingerprint). Strongest existing identity primitive. Reuse as-is; do not build a new hasher.
2. **Model manifests (expected identity)** — `model_manifest.py:56-74` (filename/URL/source/optional `sha256`), `:77-91` (matching currently folder+filename keyed), `:176-204` (export resolves by filename). Reuse as expected-identity/provenance; fix by verifying manifest hash against local file hash, not by trusting filename.
3. **Loader/model-stack extraction** — `workflow_metadata.py:302-335` (role + filename), `studio_domain/graph.py:1211-1274` (model_stack, node classes, custom-node metadata), `comparison.py:170-216` (already recognises `ControlNetLoader.control_net_name`). Reuse as the discovery seam: loader reference → Model Library resolution. Not itself an identity.
4. **Execution-only graph copy** — `comparison.py:874-914` (`copy.deepcopy` + slot injection into clone), `canonical_execution.py:1162-1167` (deep-copy before validation), `__init__.py:4452-4473` (queue path deep-copies `execution_workflow`). Reuse this exact pattern for guidance injection. Never mutate the stored workflow.
5. **Structural inspection helpers** — `production_workflow.py:736-769` (normalized node-ID + connection-tuple walk incl. latent/VAE). Reuse for sampler/conditioning anchor discovery.
6. **Wizard confirmation conventions** — `web/studio-workflow-setup-wizard.js:2577-2595` (read-only review + explicit Confirm), `:401-408` (ambiguous candidates do not satisfy save gate), `web/studio-graph-binding.js:602-644` (bounded candidate confirmation), `web/studio-backend-workspaces.js:437-475` (blocking message + explicit action + Cancel, no auto-continue). Reuse for Guidance confirm / anchor-pick dialogs.
7. **Dependency/missing-state UI** — `web/studio-model-library.js:1299-1427` (status banners, explicit groups, truthful "not installable"), `web/studio-history-v2-detail.js:1-56` (status/attempts/errors/metadata/diagnostics). Reuse for missing-checkpoint / missing-node / preprocessor-unavailable / history provenance display.
8. **ControlNet dependency classification** — `dependency_resolver.py:387`, `.model_manifest.json:44` (ControlNet model-folder). Reuse for dependency checks; it is environment provenance, not model identity.
9. **What NOT to reuse as identity** — `history_v2_models.py:81-150` + `web/studio-run-model.js:208-237` (run/output identity, no model hash); `studio_domain/models.py:135-165` (workflow-version graph hash + `compatible_models` — identifies the graph, not the weights). Record resolved model identity *into* history; do not key mappings by workflow/run ID.

---

## Model identity findings

Recommended identity: **`sha256:<full-file-digest>` of the actual loaded diffusion-model file, resolved via Model Library.**

Fallback chain (evidence-based):
1. **Exact immutable identity** — full SHA-256 from `model_library.py` (verified post-resolution). Required for a *trusted/confirmed* mapping.
2. **Strong metadata** — manifest expected `sha256` (verified against local file) + architecture/base metadata (`compatible_models`, model_stack family labels). Usable to *propose* a candidate mapping; never auto-confirm on this alone.
3. **Filename fallback (display only)** — loader `role + filename` (`workflow_metadata.py`, `model_manifest.py` export). Display context + manual-selection aid only. Never a compatibility key.

Where identity comes from:
- Loader reference extracted from the selected workflow (`model_stack` / semantic binding, incl. `UNETLoader.unet_name`) → `(folder, filename)` → Model Library record → verified SHA-256. The runtime today surfaces filenames, not hashes — the join is the missing one-step seam Phase 9 must add (pre-run resolution, before any graph copy is made).

When it is available:
- After Model Library discovery/reconciliation (hash), and at workflow-capture/run-context time (loader filename). Resolution must happen **before** execution-copy mutation, on the selected base workflow.

Invalidation:
- File content replacement → new SHA-256 → new `model_id`, old record `installed=False` → saved mapping does **not** carry over; require fresh review (treat as unknown/unconfirmed with old mapping shown as evidence only).
- Path/folder move without content change → same hash but lookup key changes → re-resolve by hash, preserve mapping, update display filename.
- Manifest correction / loader-input change / workflow-version change → does not change the weight identity, but requires re-resolution (the workflow now points at a different file → different identity).

Aliases/renames:
- Renamed file, same hash → **same model identity**; reuse confirmed mapping, show "filename changed, identity unchanged" notice, update display/history filename.
- Same filename, changed hash → **different model identity**; block reuse, show "this filename now refers to a different model", require review.

Cross-workflow reuse:
- All workflows resolving to the same `sha256:<digest>` share one confirmed mapping. Workflow name/version appears in history as provenance only and never selects the mapping.

Open questions for implementation (do not block research sign-off):
- Split stacks (diffusion + CLIP/VAE quant variants): key on diffusion-model hash alone for V1; record CLIP/VAE filenames as advisory metadata.
- Quantized/converted siblings sharing architecture labels are intentionally distinct identities.

---

## Qwen findings

Scope: Qwen-Image 1.x proven; **Qwen Image 2.1 unproven for all control weights below** (distinct `QwenImage21Pipeline`; all retrieved control metadata names `Qwen/Qwen-Image`).

- Pose:
  - InstantX Union ControlNet (Canny/soft-edge/depth/**pose**; DWPose/Openpose input) — proven for Qwen-Image 1.x via official ComfyUI workflow.
  - DiffSynth Union Control LoRA (Canny/depth/**pose**/openpose/lineart/softedge/normal) — proven for Qwen-Image 1.x; note it is a **LoRA/context-image adapter** (`LoraLoaderModelOnly`), not a classic ControlNet.
  - DiffSynth model patches: **no pose patch**.
- Depth:
  - InstantX Union (Depth Anything V2 input) — proven.
  - DiffSynth depth model patch (`qwen_image_depth_diffsynth_controlnet.safetensors`, via `ModelPatchLoader`) — proven.
  - DiffSynth Union LoRA — proven (widest).
- Canny/Edge:
  - InstantX Union (OpenCV `cv2.Canny`; soft-edge via `AnylineDetector`) — proven.
  - DiffSynth Canny patch — proven (also accepts line-art contours as *input*, not a lineart-trained mode).
  - Union LoRA — proven.
- Lineart:
  - Only credible Qwen-Image option is the **DiffSynth Union Control LoRA** (lineart listed). No dedicated InstantX lineart mode; no DiffSynth lineart patch. Confidence lower than the other three modes.
- Candidate provider(s): **InstantX** (classic ControlNet path) + **DiffSynth-Studio via Comfy-Org rehost** (patch + LoRA paths). Qwen mixes three mechanisms — classic ControlNet, model-patch, context-LoRA — there is no single "Qwen ControlNet node shape".
- Evidence: `InstantX/Qwen-Image-ControlNet-Union` (Apache-2.0, ~1.77B params BF16 / ~3.5 GB); Comfy-Org rehost `Comfy-Org/Qwen-Image-InstantX-ControlNets` (updated 2026-09-23); `Comfy-Org/Qwen-Image-DiffSynth-ControlNets` (Apache-2.0 collection, ~7.7 GB total; Canny/Depth/Inpaint patches + Union LoRA); official ComfyUI docs + workflow JSONs (`image_qwen_image_instantx_controlnet.json`, `image_qwen_image_union_control_lora.json`); Diffusers `QwenImageControlNetModel/Pipeline`, `QwenImageMultiControlNetModel`.
- Licensing/dependencies: InstantX Union **Apache-2.0** (permissive — best license story in this research); DiffSynth via Comfy-Org collection **Apache-2.0** (verify original ModelScope terms before redistribution); preprocessors via `comfyui_controlnet_aux` (Apache-2.0 code; per-checkpoint weight licenses still apply — DWPose/DepthAnything/TEED etc. audited separately).

---

## FLUX/Klein findings

- Pose: **Union Pro 2.0** (`Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0`, DWPose input, no mode embedding — used as ordinary ControlNet) is the strongest documented route for `FLUX.1-dev`. Original Union/Pro use `control_mode=4` + `SetUnionControlNetType`. No official BFL pose checkpoint.
- Depth: **BFL `FLUX.1-Depth-dev`** (official concatenated-control transformer via `FluxControlPipeline`, `control_image`, Depth-Anything-Large preprocessor, 12B params) — highest evidence; plus community `Shakker/...-ControlNet-Depth` / Union depth mode for native ControlNet graphs. BFL Depth LoRA also exists.
- Canny/Edge: **BFL `FLUX.1-Canny-dev`** (official, `controlnet_aux.CannyDetector` 50/200 @1024px) + BFL Canny LoRA; community `InstantX/FLUX.1-dev-Controlnet-Canny` (`controlnet_conditioning_scale≈0.6`) and Union Pro 2.0 (canny scale 0.7 / end 0.8; adds soft-edge via `AnylineDetector`).
- Lineart: **no official BFL lineart checkpoint found**. Only defensible FLUX routes are soft-edge/HED/Anyline *approximation* (Union Pro 2.0 soft-edge, XLabs HED) — not lineart-trained control. Must be labelled as such or deferred.
- Candidate provider(s): **Black Forest Labs** (official Canny/Depth transformers + LoRAs) for highest-evidence Canny/Depth; **Shakker-Labs Union Pro 2.0** for Pose (+Canny/Depth/soft-edge in one weight); **X-Labs** (`x-flux-comfyui` + `flux-controlnet-collections`: Canny/Depth/HED) as ComfyUI-native alternative.
- Evidence: BFL `flux` repo + `structural-conditioning.md`; Diffusers FLUX Canny/Depth control docs (`FluxControlPipeline` vs `FluxControlNetModel/Pipeline` — BFL models are **not** `ControlNetModel` objects, they concatenate control channels); ComfyUI native `ControlNetLoader` / `ControlNetApplyAdvanced` (strength/start/end) / `SetUnionControlNetType`; X-Labs guide + example workflows; Union Pro 2.0 card (explicit pose/canny/depth/soft-edge/gray claims + multi-control examples).
- Licensing/dependencies: **commercial blocker** — `FLUX.1-dev` base, BFL Canny/Depth (-dev and LoRAs), XLabs and InstantX FLUX-dev ControlNets all sit under the **FLUX.1-dev Non-Commercial License** (model-card `flux-1-dev-non-commercial-license`). Runtime auto-download is technically possible but does not cure the NC restriction: **do not bundle for commercial Studio; linking ≠ licensing**. `FLUX.1-schnell` is Apache-2.0 but has **no** official structural checkpoints. FLUX.2 Klein 9B (~29 GB VRAM, FLUX Non-Commercial) documents text-to-image + reference editing only — **no official ControlNet-style pose/depth/canny/lineart; do not cross-load FLUX.1 ControlNets onto Klein/schnell** (different pipeline/conditioning; classify as unverified).

---

## Krea findings

- Pose / Depth / Canny-Edge / Lineart for **Krea 1 (`black-forest-labs/FLUX.1-Krea-dev`, 12B, ~23–24 GB, FLUX.1-dev NC license)**: **no credible official Krea-specific adapter found for any of the four modes** (searched official BFL/Krea releases, model cards, ComfyUI nodes; `Krea-Arcana` node search returned nothing credible).
- Cross-loading FLUX.1-dev controllers onto Krea 1 is *architecturally plausible* (Krea announcement: "fully compatible with FLUX.1-dev… seamless integration with the existing ecosystem") but **officially unvalidated** — BFL Canny/Depth weights were trained for FLUX.1-dev behaviour. Classify as experimental, never as a shipped Studio mapping.
- Only strong Krea-family native control evidence is for **Krea-2** (different architecture, out of Phase-9 V1 scope): community `Patil/Krea-2-depth-controlnet` (862 MB Control-LoRA, Depth Anything V2 Large, 0.98–0.99 depth correlation) + `facok/comfyui-krea2-controlnet` nodes (Loader → Encode → Apply; pose/canny/lineart/normal graph paths exist but **matching public LoRAs for those modes were not found** — preprocessor support ≠ control support).
- Candidate provider(s): **none shippable for Krea 1 V1**.
- Evidence: `black-forest-labs/FLUX.1-Krea-dev` card (2025-07-31), `krea.ai/blog/flux-krea-open-source-release`, BFL `flux` repo structural model list (Canny/Depth only, `-dev` only), `krea/Krea-2-Raw`, `Comfy-Org/Krea-2`, `Patil/Krea-2-depth-controlnet` + `Tanmaypatil123/Krea-2-controlnet` repo.
- Licensing/dependencies: Krea 1 weights under FLUX.1-dev NC terms (commercial blocker inherited); Krea-2 under Krea 2 community license (verify before any use); no verified official Krea control checkpoint suitable for Studio auto-download — **do not bundle or auto-fetch; treat as unresolved blocker by default**.

---

## Preprocessor findings

Canonical choice: **`Fannovel16/comfyui_controlnet_aux`** (Apache-2.0, active — push 2026-10-11) as the single aggregate ComfyUI integration; **`huggingface/controlnet_aux`** (PyPI `controlnet-aux`, Apache-2.0) only if Studio ever needs a standalone Python service (note: DWPose now via optional `easy-dwpose` ONNX package).

- Pose: **DWPose** (`yzd-v/DWPose` assets `yolox_l.onnx` + `dw-ll_ucoco_384.onnx`, hundreds of MB; `DWPreprocessor`, OpenPose-JSON + skeleton `IMAGE`) — heaviest pose option, best quality; OpenPose body-only as lighter fallback; **avoid DensePose in V1** (Detectron2 burden, IUV output).
- Depth: **Depth Anything V2 Small (24.8M)** = fast V1 default, **Base (97.5M)** = quality/latency tradeoff; Large (335M) heavy; MiDaS (`dpt_hybrid`) = simplest compatibility baseline; avoid ZoeDepth/metric variants in V1. Comfy nodes: `MiDaS-DepthMapPreprocessor`, `Zoe-DepthMapPreprocessor`, `DepthAnythingPreprocessor`.
- Edge: **Canny** (OpenCV `cv2.Canny`, no model, CPU-trivial, `CannyEdgePreprocessor`) = V1 baseline; **TEED** (`fal-ai/teed` `5_model.pth`, `TEEDPreprocessor`) = best learned thin-edge value; HED/PiDiNet for soft/scribble variants.
- Lineart: realistic (`sk_model.pth`/`sk_model2.pth`, `LineArtPreprocessor` + coarse mode), anime (`netG.pth`, `LineArtAnimePreprocessor`), standard detector; Anyline/MistoLine = heavy, defer. All moderate PyTorch models — lighter than pose/depth but heavier than Canny.
- Output contract for Studio: normalized `RGB H×W float32 0..1` (+ optional batch dim) regardless of detector; pose may additionally carry OpenPose JSON; depth may retain raw float internally but ControlNet-facing output is the normalized visual map; record detector name/resolution/thresholds as metadata.
- Runtime tiers: lightweight = Canny; medium = TEED/HED/lineart/MiDaS; heavy = DWPose-full/DensePose/Zoe/DAv2-Large/Anyline. Keep detectors resident, cache instances, never load per-request. Minimal V1 install: OpenCV → +PyTorch/checkpoints for lineart/edge → +DAv2-S/B → +ONNX Runtime for DWPose. DensePose/Detectron2 stays optional.

---

## Graph topology findings

- Common anchors: the safe insertion point for ordinary ControlNet is the **sampler's conditioning inputs** (`positive`/`negative`), *not* the sampler's `MODEL` input. Shape: `conditioning producer (CLIPTextEncode etc.) → [ControlNetApply…] → sampler positive/negative`; controller branch `ControlNetLoader → Apply.control_net`; guide branch `LoadImage/source → preprocessor → Apply.image`. `ControlNetApplyAdvanced` carries `strength/start_percent/end_percent`; Union original/Pro needs `SetUnionControlNetType` first; Pro 2.0 drops the mode embedding. BFL Canny/Depth-dev is a different shape entirely (control channels concatenated at the transformer input via `FluxControlPipeline` — no `ControlNetLoader/Apply`); Qwen DiffSynth patches use `ModelPatchLoader`, and the Union LoRA uses `LoraLoaderModelOnly` into the context path. Studio's injector must branch on **controller mechanism**, not assume one node shape.
- Differing structures: benchmark corpus samplers are not always native `KSampler` (observed `ClownsharKSampler_Beta` with latent output + `OPTIONS`); positive/negative/latent input names vary across custom samplers; reference-latent branches exist; some graphs already contain ControlNet/Control-LoRA/IP-Adapter/Kontext-style conditioning where ordering/composition is unclear.
- Ambiguity cases: multiple sampler/generation branches; multiple model loaders feeding different branches; custom sampler input contracts; already-controlled graphs; nonstandard conditioning (model-patch path, context-LoRA path); preprocessor output contract unknown.
- Safe insertion conditions (ALL must hold): exactly one intended sampler (or user-selected); conditioning inputs structurally discoverable and type-compatible with the Apply node; guide image + preprocessor output match `Apply.image`; controller verified for the exact loaded-model identity; graph not already controlled in an ambiguous way; mutated copy passes ComfyUI validation; stored workflow hash unchanged.
- Refuse/manual-map conditions: any ambiguity above; unverified/conflicting/filename-only mapping; missing preprocessor or unknown output contract; controller node contract requires replacing rather than wrapping conditioning; hidden-anchor identity no longer matches after graph edit (fail closed, re-confirm). Wizard-confirmed hidden anchors are **not** needed for clean single-sampler graphs — use structural discovery; they are justified only as bounded confirmation ("sampler 42 or 57?", "which conditioning pair?", "append after existing chain or refuse?") storing a concrete node/input binding per workflow version as execution metadata.

---

## Recommended Phase-9 V1 scope

Ship in this order; do not force all four into V1:

1. **Canny/Edge — ship first.** Maturity: highest (official BFL + InstantX + Qwen InstantX/DiffSynth, runnable examples everywhere). Coverage: Qwen-Image 1.x + FLUX.1-dev. Complexity: lowest (Canny = no model, TEED = small). Dependency burden: OpenCV only for baseline. Confidence: **high**.
2. **Depth — ship second.** Maturity: high (BFL Depth-dev + Union/Depth ControlNets + Qwen patch/Union). Coverage: Qwen-Image 1.x + FLUX.1-dev. Complexity: medium (DAv2-S/B or MiDaS). Dependency burden: one depth checkpoint tier. Confidence: **high-medium**.
3. **Pose — ship third (or V1.1).** Maturity: medium-high but fragmented (Union Pro 2.0 + DWPose for FLUX; InstantX Union / Union-LoRA for Qwen). Coverage: Qwen-Image 1.x + FLUX.1-dev only. Complexity: highest preprocessor cost (DWPose two-stage, hundreds of MB, ONNX/CUDA sensitivity). Dependency burden: heavy. Confidence: **medium**. Include only after Canny+Depth injector is proven.
4. **Lineart — DEFER from V1.** Maturity: low/fragmented (no BFL FLUX lineart checkpoint; Qwen lineart only via Union-LoRA context path; "lineart" inputs to Canny patches are not trained lineart control). Coverage: Qwen-Image 1.x partial only. Complexity: moderate but semantically unverified per-checkpoint. Confidence: **low**. Ship only when a checkpoint card explicitly documents lineart training for the exact base model; until then label FLUX soft-edge/HED as approximation (not V1) or omit.

Explicitly out of V1: **Qwen Image 2.1** (no validated control weights — experimental/off-label only), **FLUX.1-schnell** (no official structural checkpoints), **FLUX.2 Klein 9B** (reference-editing pipeline, not ControlNet-compatible — do not cross-load), **Krea 1** (no native adapters — experimental cross-load at most, never a shipped mapping), **Krea-2** (different architecture + community-only depth LoRA).

---

## Recommended persisted mapping

Smallest concrete record — keyed by exact model identity, never by workflow. Only fields with concrete value:

```json
{
  "model_identity": {
    "sha256": "sha256:<full diffusion-model file digest>",
    "model_record_id": "<model_library model_id>",
    "filename": "<display only, e.g. qwen-image.safetensors>",
    "folder": "<e.g. diffusion_models>",
    "family": "<e.g. qwen-image-1x | flux1-dev>",
    "base": "<e.g. Qwen/Qwen-Image | black-forest-labs/FLUX.1-dev>"
  },
  "mode": "canny | depth | pose",
  "controller": {
    "mechanism": "controlnet | model-patch | control-lora | native-concat",
    "provider": "<e.g. InstantX | DiffSynth | Black-Forest-Labs | Shakker-Labs>",
    "checkpoint": "<exact file, e.g. Qwen-Image-InstantX-ControlNet-Union.safetensors>",
    "checkpoint_sha256": "<expected digest when published>",
    "source_url": "<exact HF URL>",
    "license": "<SPDX / license name>"
  },
  "preprocessor": {
    "name": "<e.g. CannyEdgePreprocessor | DepthAnythingPreprocessor | DWPreprocessor>",
    "package": "<e.g. comfyui_controlnet_aux @ pinned commit>",
    "params": { "low": 50, "high": 200 }
  },
  "strength_defaults": { "strength": 0.7, "start": 0.0, "end": 0.8 },
  "evidence": { "workflow_url": "<official example workflow>", "verified_for": "<exact base model>" },
  "audit": { "confirmed_at": "<iso8601>", "mapping_revision": 1 }
}
```

Rules: no package manager, no registry, no plugin SDK, no crawler. One record per (model-identity × mode). Manual `Change` creates a new revision; stale evidence (checkpoint/dependency/source drift) forces re-review, never silent replacement. `lineart` has no V1 record shape until a trained checkpoint is confirmed (do not mint speculative records).

---

## Recommended user flow

Open Guidance → Studio resolves the actual loaded diffusion model (loader → Model Library → SHA-256) and shows it → known mapping? yes → show exact confirmed provider/modes → no → propose evidence-backed candidate *for that model family only* → user reviews/confirms → remember for this model identity → all workflows with the same exact hash reuse it → `Change / Reconfirm` always visible. No `Auto` method anywhere. No silent fallback — every blocked state names its cause.

Copy is grounded and explicit (full state table in Explorer H): `resolving_identity` ("Checking compatibility…") → `known_confirmed` ("Guidance ready… Confirmed for this model identity") / `known_unconfirmed` ("Guidance mapping needs confirmation… [Confirm mapping] [Change]") / `unknown_model` ("Guidance unavailable for this model… Studio will not guess from the filename… [Choose mapping] [Cancel]") / `ready` / named blocked states below.

---

## Missing dependency flow

Each names the exact artifact and blocks execution until resolved or cancelled; installation/reboot stays user-triggered (existing Model Library conventions):

- Missing controller checkpoint: "Guidance cannot run — Missing controller checkpoint: `<exact file>`. The confirmed mapping requires this weight. [Find in Model Library] [Change mapping] [Cancel]".
- Missing custom node: "…Missing custom node: `<node/package>`. This workflow needs the node that provides `<provider/preprocessor>`. [Install / Find in Manager] [Change mapping] [Cancel]". No implicit install/restart.
- Unavailable preprocessor: "…Preprocessor unavailable: `<name>`. [Resolve dependency] [Change mapping] [Cancel]". No silent substitution.
- Structurally incompatible workflow: "…Required guidance anchor not found: `<conditioning/sampler/source-image anchor>`. No fallback method was selected. [Choose another workflow] [Cancel]".
- Multiple anchors: bounded radio list of concrete `node/type/location` candidates + `[Confirm anchor] [Cancel]` — never pick the first silently.
- Unsupported mode: "…supports `<list>` — it does not support `<requested>`. [Choose supported mode] [Change mapping] [Cancel]".

---

## Unknown model flow

"Guidance unavailable for this model — Loaded `<filename>`, Identity: Not verified. No verified guidance mapping was found. Studio will not guess from the filename. [Choose mapping] [Cancel]". Manual choice shows provider / exact checkpoint / preprocessor / mode / evidence and ends with `[Confirm and remember for this model] [Back]` — selection ≠ trust until confirmed.

---

## Stale mapping flow

"Previously confirmed mapping needs review — The model identity is the same, but this mapping's evidence changed: `<dependency/version/source/checkpoint>`. Studio will not replace the confirmed mapping automatically. [Review and reconfirm] [Keep existing mapping] [Cancel]". `Keep existing` is offered only while provider/checkpoint/preprocessor remain locally usable; otherwise execution stays blocked. Changed-file-same-filename (hash changed) is **not** stale — it is a new identity: block reuse, require fresh review.

---

## Temporary graph adaptation plan

1. Resolve identity pre-run: loader reference from selected base workflow → Model Library → verified SHA-256 (+ family metadata). Fail to `identity_unavailable` if unresolvable — never fall back to filename.
2. Load confirmed mapping for (`sha256`, `mode`); if none, present family-scoped proposal or `unknown_model` manual path. No `Auto`.
3. Normalize UI workflow → API graph; discover the single intended sampler + its positive/negative conditioning producers via connection-tuple walk (`production_workflow.py` pattern). Any ambiguity → bounded anchor confirmation or refuse.
4. `deepcopy` the graph (existing `comparison.py` / `canonical_execution.py` / queue-path pattern). Mutate **only** the copy.
5. Append minimal nodes per controller mechanism: guide-image input + required preprocessor + (`ControlNetLoader` + compatible `Apply…` [+ `SetUnionControlNetType`]) OR (`ModelPatchLoader` patch) OR (`LoraLoaderModelOnly`) OR native-concat control branch (BFL-dev shape). Rewire sampler conditioning through the Apply outputs (positive/negative as exposed); never inject ordinary ControlNet via `MODEL`.
6. Validate the mutated copy through normal ComfyUI validation; execute; discard the copy. Stored workflow bytes/hash unchanged.
7. No general patch DSL: the injector supports exactly the audited mechanism shapes above, one sampler wrap per run, no chaining onto already-controlled graphs without explicit anchor confirmation.

---

## History/provenance requirements

Per Guidance run, persist alongside existing status/attempts/errors (reuse `studio-history-v2-detail.js` surface): mode; loaded-model exact identity/hash (+ display filename); provider/controller + exact checkpoint (+ hash); preprocessor name/version (+ params); mapping revision + confirmed-at; workflow name/version **as provenance only**; failure reason naming the concrete missing/blocking artifact. This makes runs auditable and stale-mapping detection possible without ever keying compatibility to workflow identity.

---

## Risks

- **Qwen mechanism triad**: three node shapes (ControlNet / patch / LoRA) for one model family — injector must branch correctly; wrong-shape reuse fails closed, not silently.
- **Qwen 2.1 / FLUX.2 / schnell / Krea temptation**: tensor-shape acceptance ≠ trained compatibility. Gate every proposal on explicit `verified_for` base-model evidence.
- **FLUX NC licensing**: BFL-dev + derived FLUX ControlNets are non-commercial. Shipping them as default/bundled Studio behaviour without a BFL commercial license is the largest legal risk in this phase. Qwen InstantX/DiffSynth (Apache-2.0) is the clean-license path.
- **DWPose weight licensing**: per-file terms unresolved — verify each exact checkpoint before bundling/auto-download; Depth-Anything-V2 Base/Large/Giant are CC-BY-NC-4.0 (Small is Apache-2.0).
- **Preprocessor burden**: DWPose/Zoe/DAv2-Large can dominate latency/VRAM; resident caching + tiered install required.
- **Custom-sampler variance** (`ClownsharKSampler_Beta`, reference-latent branches): anchor discovery must refuse rather than guess.
- **ComfyUI core GPL-3.0**: keep Studio/process-boundary architecture in mind for distribution compliance (not a license opinion — escalate before bundling).

---

## Explicit anti-overengineering decisions

- No model-capability database / background crawler — one small record per confirmed (identity × mode); proposals come from a short curated evidence table, not a registry.
- No generic graph-patching DSL or plugin SDK — one narrow conditioning-wrap transform with fail-closed ambiguity.
- No universal package installer — surface exact missing artifact; reuse existing Model Library / Manager install paths.
- No `Auto` method, no silent fallback, no workflow-keyed config for what is model-identity data.
- No Krea / 2.1 / schnell / Klein support in V1 — saying "not supported, here is why" is the correct scope cut.
- No Lineart in V1 — fragmented training evidence; defer until a card proves lineart training for the exact base.

---

## Concrete implementation plan

1. **Identity seam** (small): loader→Library SHA-256 resolver pre-run + `sha256` surfaced in run context/history. Files: `model_library.py`, `workflow_metadata.py`, `studio_domain/graph.py`, history models + `studio-run-model.js` display. Tests: rename-same-hash reuses; same-filename-changed-hash blocks; multi-workflow same-hash shares.
2. **Mapping store** (small): CRUD for the JSON record above keyed by (`sha256`, `mode`), with revision + confirmed-at + evidence URLs. No registry UI beyond Change/Reconfirm. Tests: confirm/remember round-trip; stale-evidence forces re-review; workflow ID never selects mapping.
3. **Guidance panel states** (reuse Wizard/banners): resolving → known/unknown/confirmed/stale/blocked/ready + anchor-picker + missing-dependency copy. Tests: unknown-model never executes; unsupported-mode blocked; multi-anchor requires pick.
4. **Execution-copy injector** (narrow): sampler+conditioning discovery → deepcopy → mechanism-branched minimal node append + rewire → validate → execute → discard. Start with Canny, then Depth, then Pose. Tests: stored-workflow hash unchanged; single-sampler happy path per mechanism; multi-sampler/already-controlled/custom-sampler refuses or asks.
5. **Preprocessor tier** (pinned): `comfyui_controlnet_aux` pinned commit; V1 enables Canny (+TEED), DAv2-S/B (or MiDaS baseline), DWPose-ONNX; DensePose/Anyline/Zoe/metric deferred. Tests: output-contract check (RGB 0..1 H×W) per enabled preprocessor; missing-preprocessor blocked state.
6. **History/provenance**: record identity + mapping + preprocessor + revision per run; surface in detail view. Tests: succeeded + each blocked-state run preserves identity fields.
7. **Docs-as-evidence**: curated proposal table (provider × base × mode × checkpoint URL × license × workflow URL) maintained as data, not code — Qwen-1.x + FLUX.1-dev Canny/Depth/Pose only for V1.

---

## Files likely to change during implementation

- `model_library.py` (resolution helper; no new hash algo)
- `model_manifest.py` (hash verification against local file)
- `workflow_metadata.py` / `studio_domain/graph.py` / `comparison.py` (loader extraction + anchor discovery; `comparison.py` execution-copy pattern extended, not reinvented)
- `production_workflow.py` / `canonical_execution.py` / `__init__.py` queue path (injector hook on the copy only)
- `studio_domain/models.py` + history models (`history_v2_models.py`) — add resolved-identity + mapping-revision fields (additive)
- `web/studio-workflow-setup-wizard.js` + `web/studio-graph-binding.js` (confirm + anchor-picker reuse)
- `web/studio-model-library.js` + `web/studio-backend-workspaces.js` (missing/blocked copy)
- `web/studio-history-v2-detail.js` + `web/studio-run-model.js` (provenance display)
- New small modules only: guidance mapping store + mechanism-branched injector + curated proposal data (keep each < few hundred lines).

---

## Tests required during implementation

- FAST_UNIT: identity resolver (rename/hash-change/cross-workflow share); mapping store round-trip + stale gate; injector happy-path per mechanism (Canny→Depth→Pose) with stored-hash-unchanged assertion; refuse/ask matrix (multi-sampler, custom sampler, already-controlled, missing preprocessor/checkpoint/node, unsupported mode, unknown/stale identity); preprocessor output-contract checks; history provenance field presence incl. failure runs.
- HEAVY_LOCAL (explicit only): one end-to-end execution-copy run per shipped (base × mode) on real weights (Qwen-Image 1.x Canny/Depth; FLUX.1-dev Canny/Depth; Pose where DWPose available) proving conditioning alteration + sampler execution; never as part of ordinary FAST verification. Use `python tools/test_perf.py --fast -- tests -m fast_unit` ordinarily.
- No regression-test slop for deferred modes (Lineart/Krea/2.1/Klein/schnell): assert they present `unsupported/unknown` states rather than executing.

Ready for Phase-9 implementation prompt: **YES** — scoped to V1 (Canny → Depth → Pose; Lineart + Krea + Qwen-2.1 + schnell + Klein deferred with reasons above).
