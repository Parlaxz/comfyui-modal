# PHASE G3 — Cross-Environment Runtime Portability Matrix

**Date:** 2026-08-23 · **Batch:** G3 · **Mode:** READ-ONLY research/audit (no production/test edits, no deploy/live/GPU, no VCS operations)
**Scope:** Portability of workflows created in this Studio (comfyui-modal) across exactly six targets: **Local ComfyUI, RunPod, RunComfy, Comfy Cloud, Modal, Baseten**.

## Evidence legend

- `[R]` Repository truth (current working tree, file:line).
- `[V]` VERIFIED external fact — official provider documentation, accessed 2026-08-23 (links in §12).
- `[I]` INFERRED — reasoned from verified facts; not an official guarantee.
- `[U]` UNKNOWN — no official evidence obtained; deliberately not guessed.

---

## 1. Verdict summary

The product's portable core is the **canonical workflow JSON plus a derivable dependency manifest** (custom nodes with repo URL + installed commit `[R] custom_node_registry.py:29-47`, per-node requirements with a constraints lock `[R] comfyapp.py:8149-8174`, model filenames in standard ComfyUI buckets `[R] model_library.py:25-62`). Every Modal-specific concern (GPU names, volumes, workspaces, deployment classes, `modal://`) lives below the workflow layer and is **History/provider-managed, never part of portable workflow JSON**. Exact-JSON import succeeds broadly on five of six targets; *executable* portability is gated by each target's dependency/model freedom, and only Local, Modal, RunPod, and RunComfy offer full dependency control.

---

## 2. Current-product assumption inventory (repository truth)

| # | Assumption | Evidence | Classification |
|---|---|---|---|
| A1 | Plugin must live at `<ComfyUI root>/custom_nodes/comfyui-modal`; ComfyUI root derived as `plugin.parent.parent` | `[R] local_artifacts.py:44-59` | Product implementation |
| A2 | Local data root `<ComfyUI root>/comfymodal-data`, override `COMFYMODAL_LOCAL_DATA_DIR`; outputs under `outputs/studio`, `outputs/modal` | `[R] local_artifacts.py:5-26` | Product implementation |
| A3 | Model layout = standard ComfyUI `folder_paths` buckets (checkpoints, unet/diffusion_models, clip/text_encoders, vae, loras, controlnet, upscale_models…) | `[R] model_library.py:25-62` | Workflow |
| A4 | Custom nodes discovered from `<comfyui_root>/custom_nodes` with `repo_url` + `installed_commit` (pinning metadata exists) | `[R] custom_node_registry.py:1-58` | Dependency environment |
| A5 | Remote models volume `comfyui-models` mounted at `/root/models`; custom-nodes volume `comfyui-custom-nodes` at `/root/custom_nodes_vol`; app name `comfyui` | `[R] comfyapp.py:6686-6691, 7988-7989` | Execution provider |
| A6 | Remote ComfyUI root `/root/comfy/ComfyUI` (pinned commit `f49bdb65…`, v0.24.0 lineage) | `[R] comfyapp.py:8004-8056; comfymodal_runtime/modal_app.py:8773` | Dependency environment |
| A7 | Image recipe: `nvidia/cuda:13.0.0-devel-ubuntu24.04` + Python 3.11, comfy-cli 1.3.7, torch cu130 force-reinstall, SageAttention v2.2.0 source build, apt packages (git, libgl1, ffmpeg, build-essential, clang…) | `[R] comfyapp.py:8022-8087` | Dependency environment |
| A8 | Custom-node requirements baked into image at deploy time from `.custom_node_requirements` against a constraints lock (`COMFYMODAL_REQUIREMENTS_REPAIR_MODE=fail_fast`) | `[R] comfyapp.py:8091-8174` | Dependency environment |
| A9 | GPU vocabulary is Modal-canonical (`RTX-PRO-6000` default, `A100-80GB`, `L40S`, `H100!`, `B200`…); env `COMFYMODAL_V2_GPU` + fallbacks | `[R] gpu_catalog.py:3-37` | Execution provider |
| A10 | Deployment classes generated per GPU entry: `timeout=3600`, `retries=0`, `min_containers=0`, `scaledown_window=4`, `enable_memory_snapshot`, optional GPU snapshot | `[R] comfyapp.py:23233-23261` | Execution provider |
| A11 | Workspace identity: `.modal_workspaces.json` registry, `ws_*` ids, Modal token pairs (`ak-`/`as-`) per workspace, per-workspace deploy state | `[R] modal_workspaces.py:8-130` | Execution provider |
| A12 | `modal://<workspace_id>|<gpu>|<backend_path>` managed-asset references (historical `\|\|` variants in audits); parsed in serving/export paths only | `[R] history_v2_routes.py:1094-1125; playground_service.py:635; history_v2_export.py:569-572` | **History only** |
| A13 | Input images: collected locally, base64-encoded into the dispatch payload, materialized remotely into `/root/comfy/ComfyUI/input` — no host path ever crosses the wire | `[R] canonical_execution.py:824, 1668-1671; comfyapp.py:3350-3366` | Product implementation |
| A14 | Output bytes persist to Modal volumes; local auto-save optional; legacy save route rejects remote-only `modal://` assets | `[R] output_saver.py:24-60; studio_run_adapter.py:2121,2173` | History only / Product implementation |
| A15 | Runtime configuration via `COMFYMODAL_*` env vars resolved by a central config authority and baked into image env at deploy | `[R] comfyapp.py:27-41, 8091-8142` | Dependency environment |
| A16 | Credentials = Modal token id/secret only; no other provider credentials anywhere in tree | `[R] modal_workspaces.py:45-55` | Execution provider |
| A17 | Server lifetime: scale-to-zero serverless (cold start mitigated by memory snapshot), 1 h per-call ceiling | `[R] comfyapp.py:23249-23253` | Execution provider |

**Key separation:** `modal://` (A12) is a History-managed provenance URI resolved through authenticated workspace credentials. It appears in `assets.managed_path`, never in dispatched workflow JSON. Portable-workflow requirements must not be conflated with it.

---

## 3. Exact-JSON portability — import vs. execution

For every target: **(a)** does the same workflow JSON import unchanged, and **(b)** does it actually execute?

| Target | (a) JSON import unchanged | (b) Executes successfully | Distinction notes |
|---|---|---|---|
| Local ComfyUI | YES (reference environment) | YES for anything runnable here | Baseline; both properties trivially hold `[R]` |
| RunPod | YES — worker accepts API-format graph in `/run`,`/runsync` payload `[V] worker-comfyui README/docs` | CONDITIONAL — only if every node class + model exists in that endpoint's image/volume | Syntactic success ≠ execution; missing node ⇒ `node_errors`/failed job |
| RunComfy | YES — drag-drop/upload JSON; auto-setup parses graph and installs missing nodes/models `[V] runcomfy.com/auto-setup-comfyui-workflow` | LIKELY after auto-setup; private/gated models need attached tokens `[V]` | Auto-setup closes most gaps; exotic native deps remain a risk `[I]` |
| Comfy Cloud | YES — same `/api/prompt` interface as OSS ComfyUI `[V] docs.comfy.org/development/cloud/overview` | RESTRICTED — only pre-installed custom nodes (supported list) and pre-installed models (+ Civitai LoRA import; HF "coming soon") `[V] comfy.org/cloud/supported-nodes; docs.comfy.org/get_started/cloud` | Import succeeds widely; execution fails for off-list nodes/models — the largest import/executes gap of the six |
| Modal | YES — product's own dispatch path (this is the origin environment) | YES (within product-supported envelope) | Native target `[R]` |
| Baseten | PARTIAL — workflow JSON is consumed, but the Truss pattern embeds it as `data/comfy_ui_workflow.json` inside a deployment (handlebars slots for values), not free per-request submission `[V] baseten.co/library/comfy-ui; truss-examples/comfyui-truss` | CONDITIONAL — executes after nodes/models are baked via `build_commands` | Same JSON can execute, but the deployment unit is workflow+environment, not ad-hoc graphs |

---

## 4. Path / model differences

- **Model directory names/subfolders:** All six environments use the standard ComfyUI bucket layout (`models/checkpoints`, `models/loras`, …). Workflows carrying bare filenames (this Studio's convention) port cleanly; workflows carrying absolute paths do not port anywhere. `[R] model_library.py:36-46; [V] RunPod network-volumes docs`
- **Provider mount roots differ:** Local = Windows host paths; Modal = `/root/models` volume `[R] comfyapp.py:7988`; RunPod = `/runpod-volume/models/...` `[V] worker-comfyui customization.md`; RunComfy = `/ComfyUI/...` browser-visible tree `[V] comfyui-guides.runcomfy.com`; Comfy Cloud = content-addressed asset store where `subfolder`/`type` fields are **ignored** `[V] docs.comfy.org Cloud API OpenAPI`; Baseten = paths chosen by your own `build_commands` inside the image `[V]`.
- **Inputs:** This product already decouples inputs from paths (base64 transport, remote materialization, A13). Raw JSON imported elsewhere still expects the named file in that environment's input dir — an operational step, not a JSON edit.
- **Outputs:** Local auto-save to data root `[R] output_saver.py`; RunPod returns base64 or S3 upload `[V]`; Comfy Cloud content-addressed downloads `[V]`; Modal volumes + `modal://` `[R]`; RunComfy/Baseten return payloads per their APIs.
- **Custom-node roots:** differ per env (`custom_nodes/` everywhere, but provisioned differently — see §5).
- **Recommendation posture:** No hardcoded provider rewrites. The existing abstractions (filename-only widget values, bucket-name mapping `FOLDER_MODEL_TYPES`, base64 input transport, dependency manifest) are sufficient; what is missing is a **per-provider path/mount profile** (a small mapping table: logical bucket → provider mount prefix), not string rewriting of workflow JSON. Providers making direct filesystem assumptions impossible/fragile: **Comfy Cloud** (content-addressed, subfolder ignored) and partially **RunComfy** (opaque managed containers).

## 5. Custom node restrictions

| Capability | Local | RunPod | RunComfy | Comfy Cloud | Modal | Baseten |
|---|---|---|---|---|---|---|
| Install arbitrary nodes | SUPPORTED | SUPPORTED WITH SETUP (bake via custom Dockerfile; network volume explicitly *not* for nodes `[V]`) | SUPPORTED (Manager UI in session `[V]`) | RESTRICTED — curated supported list only `[V]` | SUPPORTED (any image layer) | SUPPORTED WITH SETUP (`build_commands` git clone `[V]`) |
| Pin commits | SUPPORTED (registry stores `installed_commit` `[R]`) | SUPPORTED (checkout in Dockerfile `[I]` from `[V]` mechanics) | RESTRICTED — snapshot pins implicitly; explicit ref control UNKNOWN `[U]` | UNSUPPORTED (platform-managed versions) | SUPPORTED (pinned ComfyUI commit precedent `[R] comfyapp.py:8010`) | SUPPORTED (checkout in build_commands `[V]`) |
| Add requirements | SUPPORTED | SUPPORTED (Dockerfile pip) | SUPPORTED (session pip; bundled on Cloud Save `[V]`) | UNSUPPORTED | SUPPORTED (lock-constrained `[R]`) | SUPPORTED (`requirements:` `[V]`) |
| Build native deps | SUPPORTED | SUPPORTED (apt in Dockerfile) | UNKNOWN `[U]` | UNSUPPORTED | SUPPORTED (apt + source builds `[R]`) | SUPPORTED (`system_packages`, build_commands `[V]`) |
| Private repos | SUPPORTED (local git creds) | SUPPORTED (registry/GH creds `[V]`) | UNKNOWN `[U]` | UNSUPPORTED | SUPPORTED (Secrets-mounted creds `[I]`) | SUPPORTED (secrets + OIDC `[V]`) |
| Restart/rebuild after install | SUPPORTED (restart ComfyUI) | Rebuild image + redeploy endpoint | Session restart; Cloud Save re-snapshot `[V]` | N/A | Redeploy app (layer-cached) | `truss push` rebuild |

## 6. Resource / runtime restrictions (portability compatibility only)

| Factor | Local | RunPod | RunComfy | Comfy Cloud | Modal | Baseten |
|---|---|---|---|---|---|---|
| Timeout | none (user machine) | Configurable execution timeout per endpoint; exact cap not verified `[U]` | Session-based; deployment limits undocumented here `[U]` | Credit/subscription-governed; caps undocumented `[U]` | Per-call `timeout` (product: 3600 s; platform supports far longer `[V]` docs example 24 h) | Request-scoped serving timeouts; caps undocumented here `[U]` |
| Cold start | N/A | Scale-from-zero; Flash Boot recommended `[V]` | Session spin-up | Machine allocated per run `[V]` | Snapshot-accelerated `[R] comfyapp.py:23255-23259` | Scale-from-zero; weights cached in image `[V]` |
| Ephemeral instance | N/A | Container disk ephemeral; network volume persists | Containers claimed persistent per workflow snapshot `[V]` marketing — treat as snapshot-reproducible `[I]` | Content-addressed assets persist; compute ephemeral | Volumes persist; containers ephemeral | Container FS ephemeral between autoscale events; persistence mechanism `[U]` |
| VRAM | User GPU | Chosen per endpoint GPU | Chosen per deployment GPU | Fixed fleet (RTX 6000 Pro class `[V]`) | Per-class GPU profile `[R]` | Per `accelerator` `[V]` |
| GPU model availability | User hardware | Broad menu; region-dependent `[I]` | Selection offered at deploy `[V]` | Single documented class `[V]` | Catalog incl. RTX-PRO-6000/H200/B200 `[R]/[V]` | T4→B300 incl. RTX_PRO_6000 `[V]` |
| Storage quota | Disk-bound | Volume size per plan `[U]` | Plan-dependent `[U]` | Asset quota per tier `[U]` | Volume quota per plan `[U]` | Image size practicality `[U]` |
| Max artifact size | Disk-bound | Payload/S3-bound `[U]` | `[U]` | Tier limits `[U]` | Payload limits exist (large-payload guidance) `[U]` | Base64-in-JSON responses observed `[V]` |
| Networking | Full | Outbound allowed (S3/HF patterns `[V]`) | Outbound downloads supported (Civitai/HF/GDrive `[V]`) | Platform-mediated; Partner Nodes need key in `extra_data` `[V]` | Full egress by default | Full egress at build; runtime per config `[I]` |

## 7. Platform-specific risk (from "importing a workflow created in this Studio")

Risk is **workflow-characteristic dependent**, not a blanket provider ranking:

| Workflow characteristic | Local | RunPod | RunComfy | Comfy Cloud | Modal | Baseten |
|---|---|---|---|---|---|---|
| Core nodes + standard checkpoint | LOW | LOW | LOW | LOW | LOW | MEDIUM (deployment-bake model) |
| Popular custom nodes (Manager-common) | LOW | MEDIUM (image rebuild per change) | LOW–MEDIUM (auto-setup) | LOW if on supported list, else **UNSUPPORTED** | LOW | MEDIUM |
| Native-build custom nodes (e.g., SageAttention-class) | MEDIUM (local toolchain) | HIGH (Docker build complexity) | HIGH/UNKNOWN | UNSUPPORTED | LOW (already solved in image `[R]`) | MEDIUM–HIGH |
| Hardcoded host/absolute paths in JSON | LOW (self-consistent) | HIGH | HIGH | HIGH | HIGH (unless produced via A13 path) | HIGH |
| Private/gated models | LOW | MEDIUM (token plumbing) | MEDIUM (token attach `[V]`) | HIGH (catalog-bound) | LOW | MEDIUM |
| Multi-output / video / large artifacts | LOW | MEDIUM (payload/S3 design needed) | MEDIUM | MEDIUM (tier quotas `[U]`) | LOW (volume-backed `[R]`) | MEDIUM |

## 8. Portability matrix

Values: **S** SUPPORTED · **S/SETUP** SUPPORTED WITH SETUP · **RES** RESTRICTED · **UNSUP** UNSUPPORTED · **UNK** UNKNOWN

| Dimension | Local | RunPod | RunComfy | Comfy Cloud | Modal | Baseten |
|---|---|---|---|---|---|---|
| Arbitrary workflow JSON | S | S | S | S (import) / RES (exec) | S | RES (embedded per-deployment) |
| Custom-node install | S | S/SETUP | S | RES (curated list) | S | S/SETUP |
| Node version pinning | S | S/SETUP | RES/UNK | UNSUP | S | S |
| Python package install | S | S/SETUP | S | UNSUP | S | S |
| Native/system packages | S | S/SETUP | UNK | UNSUP | S | S |
| Custom container/Docker | N/A (host) | S | UNSUP (platform-built) | UNSUP | S | S (Truss/base_image/docker_server) |
| ComfyUI version control | S | S (image tag/bake) | RES (repo-synced; pin UNK) | UNSUP (auto-current) | S (commit pin proven `[R]`) | S (checkout in build) |
| GPU choices | Own hardware | S (wide) | S (deploy-time select) | RES (fixed fleet) | S (catalog + fallbacks `[R]`) | S (T4→B300) |
| VRAM/resource control | S | S (endpoint sizing) | S (deployment sizing) | RES (tier-based) | S (cpu/mem/gpu profiles `[R]`) | S (accelerator/cpu/memory) |
| Persistent model storage | S (disk) | S/SETUP (network volume) | S (snapshot/container) | RES (managed catalog + uploads) | S (volumes `[R]`) | UNK (image-baked; volume mount UNK) |
| Model folder conventions | S | S (`/runpod-volume/models`) | S (`/ComfyUI/models`) | RES (content-addressed; subfolder ignored) | S (`/root/models`) | S (self-defined in build) |
| Upload/import mechanisms | S | S (payload/S3) | S (browser upload/auto-setup) | S (upload/assets API) | S (payload→volume `[R]`) | S (build-time fetch) |
| Filesystem persistence | S | RES (ephemeral disk + volume) | S (snapshot) | RES (asset store only) | S (volumes) | UNK |
| Absolute path behavior | S (self) | FRAGILE (mount differs) | FRAGILE (managed tree) | BROKEN (no fs semantics) | FRAGILE (container paths) | FRAGILE (image-defined) |
| Network access | S | S | S | RES (mediated) | S | S |
| Outbound download restrictions | None | None documented | None (download helpers) | Managed by platform | None by default | Build-time open; runtime per config |
| Secrets/env vars | OS env | Endpoint env vars `[V]` | Token attach `[V]`; broader UNK | API key model `[V]` | Secrets/env `[V]` | Secrets/env `[V]` |
| Input asset handling | S | S (payload/S3) | S (upload/browser) | S (compat endpoints; fields ignored) | S (base64→input dir `[R]`) | S (handlebars slots) |
| Output asset handling | S (auto-save) | S (base64/S3) | S (API results) | S (assets API) | S (volume + `modal://` History) | S (base64 responses) |
| Startup/bootstrap lifecycle | Manual | Handler boot per scale-up | Session boot / deployment boot | Managed per job | Image layers + snapshot `[R]` | Build + readiness probes `[V]` |
| Long-run execution constraints | Hardware-bound | Timeout cap UNK | UNK | Credits/tier UNK | 3600 s configured; extendable `[V]` | Request-timeout UNK |
| Serverless/session lifecycle | N/A | Scale-to-zero endpoint | Session + serverless deployments | Job queue per user | Scale-to-zero classes `[R]` | Autoscale model serving |
| API/automation | Local HTTP API | REST `/run /runsync /health` `[V]` | Deployments + overrides API `[V]` | OSS-compatible `/api/prompt` (experimental) `[V]` | Product dispatch + web endpoints | Predict endpoint (+custom server) `[V]` |
| Reproducibility | Manual (snapshot tools) | S (image digest) | S (Cloud Save image) | RES (platform-controlled) | S (pinned image + env authority `[R]`) | S (Truss config in VCS) |

## 9. Portability adapter implications (no implementation)

| Environment | Needed adapters |
|---|---|
| Local ComfyUI | **No adapter** (native). |
| Modal | **No adapter** (native execution provider). Keep GPU-name/fallback vocabulary internal. |
| RunPod | **Dependency manifest → Dockerfile recipe** (nodes+pins+requirements from existing registry/lock `[R]`), **path-mapping profile** (`/runpod-volume/models`), **output adapter** (base64 vs S3), **provider instructions**. No second execution engine: worker-comfyui already speaks graph-JSON. |
| RunComfy | **Provider instructions + manifest ingestion** (its auto-setup consumes plain workflow JSON `[V]`); **Cloud Save** replaces our manifest; thin **overrides-API adapter** only if automation is desired. |
| Comfy Cloud | **Node allowlist checker + model-catalog mapper** before export; **no dependency manifest possible**, **no container recipe possible**. Honest degradation: report non-portable nodes/models rather than attempt adaptation. |
| Baseten | **Dependency manifest → Truss config** (`build_commands`, `requirements`, `system_packages`, `accelerator`), **model mapping into image**, **workflow-embedding adapter** (values template) or a **custom container recipe** (`docker_server`) if a generic graph-submission facade is wanted. |

Cross-cutting: one **portability descriptor** (workflow hash, node manifest with commits, requirement lock, model filename→bucket table, input slot inventory) satisfies RunPod, RunComfy, and Baseten generation targets without six execution engines. Comfy Cloud is the only target requiring a *restriction-awareness* adapter instead of a *provisioning* adapter.

## 10. Rollback / recovery semantics per environment

| Environment | Restore workflow JSON | Restore dependency versions | Restore container/image | Restore model mapping | Return to original environment |
|---|---|---|---|---|---|
| Local | Version store exists (`.studio_workflow_versions.json`, `.studio_snapshots.json` `[R]` not_indexed listing) | Reinstall pinned nodes/requirements (registry holds commits `[R]`) | N/A | Library records retain metadata for removed files `[R] model_library.py:1-11` | Trivial (native) |
| RunPod | Re-submit prior JSON | Redeploy prior image tag/digest | Yes (registry tags) | Re-point volume dirs | Always (JSON + manifest kept client-side) |
| RunComfy | Reload prior JSON | Roll back to earlier Cloud Save snapshot `[V]` (snapshot-versioning claim) | Via snapshot | Re-upload/re-link models | Always |
| Comfy Cloud | Re-submit prior JSON | UNSUP (platform-managed) | UNSUP | Re-map to catalog equivalents | Always |
| Modal | Prior JSON | Prior deploy (per-workspace `deploy_state_by_workspace` `[R] modal_workspaces.py:11-13`) | Layer-cached redeploy of prior recipe | Volume contents persist; injection repeatable | Always |
| Baseten | Prior JSON/values | Previous `truss push` deployment `[I]` (platform retains deployment history) | Yes (prior build) | Re-run build_commands | Always |

## 11. Unknowns (explicitly not guessed)

1. RunPod: maximum serverless execution-timeout cap; volume size ceilings per plan.
2. RunComfy: explicit commit-level pinning controls; native/apt package support inside sessions; deployment timeout caps.
3. Comfy Cloud: job wall-clock limits; full model-catalog breadth; timeline for HF model import; behavior for non-listed nodes beyond failure.
4. Baseten: persistent volume/storage options for ComfyUI-style model trees; request timeout caps; cold-start envelope for large images.
5. Region-dependent GPU availability for RunPod/RunComfy/Modal/Baseten at any given time.
6. Whether RunComfy's "persistent containers" survive independent of Cloud Save snapshots (marketing claim treated as INFERRED, not guaranteed).

## 12. Sources (accessed 2026-08-23)

- RunPod worker-comfyui (official repo/docs): README, `docs/deployment.md`, `docs/customization.md` (network volume `/runpod-volume/models`, custom Dockerfile, S3 outputs, Flash Boot) — https://github.com/runpod-workers/worker-comfyui ; https://docs.runpod.io/tutorials/serverless/comfyui
- RunComfy: Custom Workflows / Core Concepts / auto-setup / API overview — https://docs.runcomfy.com/serverless/custom-workflows ; https://docs.runcomfy.com/serverless/core-concepts ; https://www.runcomfy.com/auto-setup-comfyui-workflow ; https://www.runcomfy.com/comfyui-api ; https://comfyui-guides.runcomfy.com (uploads)
- Comfy Cloud: Cloud overview & API reference (OSS-compatible `/api/prompt`, ignored fields, X-API-Key, subscription tiers), supported custom-node packs, cloud-vs-local table — https://docs.comfy.org/development/cloud/overview ; https://docs.comfy.org/development/cloud/api-reference ; https://comfy.org/cloud/supported-nodes/ ; https://docs.comfy.org/get_started/cloud
- Modal: Function SDK (`timeout`, `gpu` lists/fallbacks, volumes, secrets, scaledown) — https://modal.com/docs/sdk/py/latest/Function ; https://frontend.modal.com/docs/examples/gpu_fallbacks
- Baseten: Truss configuration (accelerators T4…RTX_PRO_6000…B300, build_commands, secrets, base_image/docker_server), ComfyUI Truss + library — https://docs.baseten.co/reference/truss-configuration ; https://github.com/basetenlabs/truss-examples/tree/main/comfyui-truss ; https://www.baseten.co/library/comfy-ui/
- Repository truth: all `[R]` citations in §2 (working tree, read-only).

---
*G3 audit artifact only. No deploy, live, GPU, commit, or push operations performed.*
