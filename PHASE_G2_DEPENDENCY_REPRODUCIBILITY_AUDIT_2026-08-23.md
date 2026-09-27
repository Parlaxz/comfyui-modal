# PHASE G2 — Dependency & Custom-Node Reproducibility Audit (2026-08-23)

Lane: **G2 — Custom-Node, Dependency & Reproducibility Portability**
Mode: READ-ONLY audit. No production/test edits. No deploy/live/Modal/GPU. No commits.
Scope ownership: dependency + custom-node portability. (G1: Workflow JSON · G3: target-platform runtime restrictions · G4: product integration architecture.)

---

## 1. Executive Verdict

The remote execution environment is **reproducible in outline but not in exact version identity**. ComfyUI core is pinned to an exact upstream commit; a 7-package Python lock family is enforced with a build gate; SageAttention is pinned to a tag and built from source. Everything else floats: the CUDA base image is referenced by tag (not digest), the torch/torchvision/torchaudio cu130 stack has no version pins, apt packages are unpinned, and all 22 production custom nodes are deployed as **unversioned working-tree copies** whose git HEADs (where they exist) are recorded nowhere and enforced by nothing. Two structural divergences mean "install standard ComfyUI + nodes" would NOT reproduce current behavior:

1. The local validation ComfyUI checkout carries an **uncommitted 145-line patch to `comfy/model_management.py`** (soft-empty-cache gate importing `comfymodal_runtime.empty_cache_bypass`). The Modal image checks out pristine upstream `f49bdb6` — local and remote soft-cache policy differ today.
2. Compiled production workflows rewrite output nodes to `ComfyModalProductionOutput` / `ComfyModalProductionImageComparerOutput`, classes that exist only inside the private `Parlaxz/comfyui-modal` plugin, currently deployed from a working tree with **124 uncommitted changes** on branch `r42-golden-reconciliation` — no git ref reproduces it.

Overall dependency-side risk contribution to Phase G: **HIGH**, driven by torch/CUDA float, base-image float, working-tree-only plugin deployment, and absent model hashes.

---

## 2. Current Installation Architecture (as-found)

### 2.1 Remote Modal image construction (`comfyapp.py:8022–8433`)

| Step | Command / mechanism | Pin state | Evidence |
|---|---|---|---|
| Base image | `modal.Image.from_registry("nvidia/cuda:13.0.0-devel-ubuntu24.04", add_python="3.11")` | FLOATING registry tag, no digest | comfyapp.py:8023–8026 |
| System packages | `.apt_install("git","libgl1","libglib2.0-0","libsm6","libxrender1","libxext6","ffmpeg","build-essential","ninja-build","clang")` | FLOATING apt versions | comfyapp.py:8028–8043 |
| Installer CLI | `.pip_install("comfy-cli==1.3.7", "httpx>=0.27.0")` | comfy-cli PINNED; httpx FLOATING range | comfyapp.py:8044 |
| ComfyUI install | `comfy --skip-prompt install --nvidia` (run on `gpu="a10g"` at build) | clones default branch (nightly), then re-pinned | comfyapp.py:8045–8048 |
| ComfyUI pin | `git fetch --depth=1 origin f49bdb655707b97952dcef40e12e5af1f08d2007 && git checkout --force <sha>` | PINNED commit (= v0.24.0 lightweight tag) | comfyapp.py:8010, 8051–8056 |
| Torch stack | `pip install --upgrade --force-reinstall torch torchvision torchaudio --index-url .../whl/cu130` | FLOATING latest cu130 wheels | comfyapp.py:8058–8063 |
| Triton | `pip install --upgrade 'triton>=3.0.0'` | PARTIALLY PINNED range | comfyapp.py:8065–8067 |
| SageAttention | `CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=12.0+PTX MAX_JOBS=4 pip install git+...SageAttention.git@v2.2.0 --no-build-isolation --no-deps` + `.so` presence + import gates | PINNED tag v2.2.0, source build | comfyapp.py:8012–8013, 8068–8086 |
| CacheDiT lock | lock file baked to `/opt/comfymodal/cachedit_dependency_lock.txt`; applied as `-c` constraint to every custom-node pip install; final `--no-deps -r lock` ensure; build-time `CACHEDIT_LOCK_GATE` asserts 7 exact versions + flash-attn-2 availability probe | PINNED (7 packages) | comfyapp.py:6794–6797, 8150–8238; cachedit_dependency_lock.txt |
| Custom-node requirements build context | `_prepare_custom_node_requirements_build_context()` stages per-node dep files into `.custom_node_requirements/<node>/`; mounted via `add_local_dir(... "/root/comfy-build/custom_node_requirements")`; one pip loop installs each `requirements.txt` with `-c "$_lock"` | requirements-file hashes tracked; package resolution floats within constraints | comfyapp.py:7949–7986, 8149–8182 |
| Custom-node sources | `add_local_dir(_LOCAL_CUSTOM_NODES → /root/comfy/ComfyUI/custom_nodes)` combined mode (or per-node); ignores `.git/`, caches, secrets, reports | WORKING-TREE copy; no version recorded | comfyapp.py:8245–8286 |
| Baked manifest | `build_custom_node_dependency_manifest()` → `.baked_custom_node_deps/custom_node_deps_baked.json` → `/opt/comfymodal/custom_node_deps_baked.json`; records per-node dependency-file SHA-256s, overall hash, `production_custom_node_generation` | content hashes only; NO git commits/versions | comfyapp.py:8294–8368; .baked_custom_node_deps/custom_node_deps_baked.json |
| Runtime env | `_V2_RUNTIME_ENV` (~40 vars incl. `COMFYMODAL_REQUIREMENTS_REPAIR_MODE=fail_fast`) baked via `.env()`; two flags baked from caller env at deploy time | deterministic per deploy invocation | comfyapp.py:8091–8143 |

### 2.2 Runtime custom-node supply chain

- Modal Volume `custom_nodes_vol` mounted at `/root/custom_nodes_vol`, symlinked into `ComfyUI/custom_nodes` by `sync_custom_nodes_into_comfy()` (volume is source of truth; stale real dirs moved aside). Evidence: comfyapp.py:3915–3982.
- Generation parity: content-derived generation token (MD5 of canonical py/txt/toml/cfg bytes fingerprint, schema v2) compared baked ↔ persisted ↔ actual tree (`comfymodal_runtime/custom_node_parity.py`).
- Requirements repair modes (`_install_custom_node_requirements`, comfyapp.py:14396–14529): `off` / `fail_fast` (production default — never pip-installs, raises if baked manifest not prepared) / `dev` (runtime pip allowed, constraints applied). Production therefore fails closed on any requirements drift.
- Local host: nodes live directly in `ComfyUI/custom_nodes/`; `_resolve_local_custom_nodes_root()` validates the root; duplicate/worktree copies of comfyui-modal are filtered from the image (comfyapp.py:6800–6977).

### 2.3 Model helpers

- Master model manifest `.model_manifest.json` (`model_manifest.py`): entries carry `folder, filename, url, source_kind, requires_hf_token, requires_civitai_token, sha256, notes, remove_on_swap`. **Observed data: every entry has `"sha256": null`.**
- Model library store `.studio_model_library.json` (`model_library.py`): filename, size, source_urls, provider, revision, sha256 computed on scan, fingerprint = size+mtime_ns.
- Workspace swap plan builds download plans from URLs (`build_workspace_swap_plan`); workflow export maps node model refs → manifest entries (`export_workflow_manifest`).

### 2.4 Frontend extensions

- ComfyUI frontend: pinned transitively by core requirements `comfyui-frontend-package==1.44.19` (installed during `comfy install` at build). Moves only when the ComfyUI pin moves.
- Node JS extensions (`web/`, `js/` dirs of 11+5 nodes) are baked together with node source into image and volume — no separate frontend build pipeline exists.

---

## 3. ComfyUI Version Authority

| Surface | Authority | Value | Reproducible? |
|---|---|---|---|
| Remote image ComfyUI | explicit commit constant | `f49bdb655707b97952dcef40e12e5af1f08d2007` (tag v0.24.0, Comfy-Org/ComfyUI) | YES for code identity; comment documents comfy-cli 1.3.7 nightly default was re-pinned deliberately (comfyapp.py:8004–8010) |
| Local validation ComfyUI | same commit + **uncommitted patch** | v0.24.0 @ f49bdb6 + modified `comfy/model_management.py` (+145/−12) + untracked empty `comfy/__init__.py` | NO — no ref contains the patch |
| Patch content | soft-empty-cache reason gate: `soft_empty_cache(soft_cache_reason=...)`, `execute_soft_cache` imported from `comfymodal_runtime.empty_cache_bypass` (local file line 2027) | V2 performance work (D18/E5 lane), separate from product/runtime patches | patch lives only in working tree; test `test_v2_batch_e5_empty_cache_bypass.py::TestE5SourceBranchWiring` asserts the patched source text locally |
| Image digest | none | base image referenced by mutable tag | NO |
| Floating branch risk | none while pin constant exists; pin change requires code edit (also busts layer cache by design) | — | controlled |

**Finding:** "install standard ComfyUI" reproduces the REMOTE image exactly (commit-pinned) but NOT the LOCAL validation environment (patched core). Conversely the local environment cannot be reproduced from any published ref. No mechanism applies the local core patch to the image or volume (searched: no copy/patch step for `comfy/model_management.py` outside tests).

---

## 4. Custom-Node Inventory (authoritative, evidence-based)

Sources: filesystem git probes (2026-08-23), `pyproject.toml` versions, `.baked_custom_node_deps/custom_node_deps_baked.json` (comfyapp_version 2.16.30, 21 dependency nodes + manager), class attribution from `latest_benchmark_workflow.json` payload prompt verified against local core/node sources.

### 4.1 Nodes REQUIRED by the current benchmark workflow

| Node dir | Repo URL | Git HEAD @ install | Declared version | Install method | Pinned? | Py requirements | Native/system | Frontend ext | Workflow classes supplied |
|---|---|---|---|---|---|---|---|---|---|
| RES4LYF | github.com/ClownsharkBatwing/RES4LYF | `119679d8d8d26e6db52757e705488abb6399d7d4` (main) | UNKNOWN (no tag desc) | git clone (working tree) | FLOATING | requirements.txt (hashed in baked manifest) | none known | web/ | PairConditioningSetProperties, ClownsharKSampler_Beta |
| comfyui-impact-pack | UNKNOWN (no .git) | UNKNOWN | 8.28.3 (pyproject) | zip/manual or Manager-zip | FLOATING | requirements.txt + install.py staged | segment-anything family deps | js/ | ImpactIfNone, ImpactSwitch |
| comfyui-easy-use | UNKNOWN (no .git) | UNKNOWN | 1.3.6 | zip/manual | FLOATING | requirements.txt | none known | web/ | easy showAnything/ifElse/imageSize/float/int/globalSeed/indexAnything/stringToIntList |
| comfyui-custom-scripts | UNKNOWN (no .git) | UNKNOWN | 1.2.5 | zip/manual | FLOATING | none (pyproject only) | none | js/ | SystemNotification&#124;pysssss, SimpleMath+ |
| comfyui-levelpixel | UNKNOWN (no .git) | UNKNOWN | 1.3.3 | zip/manual | FLOATING | requirements.txt | none known | web/ | StringToCombo&#124;LP |
| rgthree-comfy | UNKNOWN (no .git) | UNKNOWN | 1.0.2605082257 | zip/manual | FLOATING | requirements.txt | none | web/ | Image Comparer (rgthree), Any Switch (rgthree) |
| ComfyUI_LayerStyle | github.com/chflame163/ComfyUI_LayerStyle | `d94bef1ee5ed3656f5ff1bb2830a4ffd94f40935` (main) | UNKNOWN | git clone | FLOATING | requirements.txt (large: opencv, etc.) | ffmpeg-adjacent deps possible | web/ | LayerUtility: PurgeVRAM V2 |
| ComfyUI-CacheDiT | github.com/Jasonzzt/ComfyUI-CacheDiT (fork) | `ab1a1448a2476a33493c9a9b04e1685971b9e73a` (main) | UNKNOWN | git clone | FLOATING | requirements.txt | depends on locked cache-dit stack | none found | CacheDiT_Model_Optimizer |
| ComfyUI-KJNodes | github.com/kijai/ComfyUI-KJNodes | `3df15ed824045ca45ba668869965a72c7d9d9825` (main) | UNKNOWN | git clone | FLOATING | requirements.txt | sageattention (baked pkg) | web/ | PathchSageAttentionKJ |
| masquerade-nodes-comfyui | github.com/BadCafeCode/masquerade-nodes-comfyui | `432cb4d146a391b387a0cd25ace824328b5b61cf` (tags/v0.9-6-g432cb4d) | v0.9 (+6) | git clone | FLOATING | none found | none | none found | CombineHooks8 |
| comfyui_lg_samplingutils | UNKNOWN (no .git) | UNKNOWN | 1.0.2 | zip/manual | FLOATING | none (pyproject only) | none | web/ | LGNoiseInjectionLatent |
| ComfyUI core (pinned f49bdb6) | github.com/Comfy-Org/ComfyUI | pinned commit | 0.24.0 | comfy-cli + git pin | PINNED | core requirements.txt (frontend==1.44.19 etc.) | see §6 | bundled frontend | VAELoader, VAEDecode, CLIPLoader, UNETLoader, CLIPTextEncode, ConditioningZeroOut, EmptySD3LatentImage, SaveImage, ModelSamplingAuraFlow, ModelPatchLoader, PrimitiveFloat, PrimitiveStringMultiline, CustomCombo, ImageRotate, EmptyImage |
| comfyui-modal (this repo) | github.com/Parlaxz/comfyui-modal | `0c59f46e3238f421378e8852ebc548da815b70af` (branch r42-golden-reconciliation) + **124 dirty files** | comfyapp_version 2.16.30 | private git + working-tree bake | FLOATING (working tree) | self-contained (stdlib + modal/PIL/torch) | Modal platform | web/ (comfymodal-progress.js, history-v2-*.js, modal-*.js) | ComfyModalProductionOutput, ComfyModalProductionImageComparerOutput (injected by production compiler, production_workflow.py:620,880,909) |

### 4.2 Nodes baked into every image but NOT used by the current workflow

| Node dir | Git? | URL | HEAD | Declared version | Notes |
|---|---|---|---|---|---|
| cg-use-everywhere | NO | UNKNOWN | — | 7.8 | Anything Everywhere family (present in older workflow revisions) |
| comfyui-detail-daemon | NO | UNKNOWN | — | 1.1.3 | requirements.txt present |
| ComfyUI-Flux2Klein-Enhancer | YES | github.com/capitan01R/ComfyUI-Flux2Klein-Enhancer.git | `7b8176a2c33d43eaccc96ab19a9c655f18863e90` (main) | UNKNOWN | fork URL |
| comfyui_fill-nodes | NO | UNKNOWN | — | 2.7.9 | |
| comfyui_image_metadata_extension | NO | UNKNOWN | — | 1.3.4 | |
| comfyui-lora-manager | NO | UNKNOWN | — | 1.0.11 | |
| comfyui-manager | YES | github.com/ltdrdata/ComfyUI-Manager | `7ddad11d2844da42b58b98c833cba3b6dc2e8e39` (≈3.39.3+263 past tag; pyproject says 3.40) | 3.40 | Manager itself is baked/synced like any node |
| ComfyUI-SeedVR2_VideoUpscaler | YES | github.com/numz/ComfyUI-SeedVR2_VideoUpscaler | `4490bd1f482e026674543386bb2a4d176da245b9` (v2.5.23-2-g4490bd1) | v2.5.23+2 | heavy reqs (gguf, omegaconf, peft…) |
| comfyui-workflow-encrypt | NO | UNKNOWN | — | 1.0.0 | |
| comfyui_controlnet_aux | NO | UNKNOWN | — | 1.1.5 | |
| comfyui_essentials | NO | UNKNOWN | — | 1.1.0 | |
| comfyui_sam3 | NO | UNKNOWN | — | 0.2.1 | |
| comfyui-modal-r41.disabled | excluded | — | — | — | filtered by duplicate/content markers before bake |

Version provenance legend: "UNKNOWN (no .git)" = repository URL and commit are unrecoverable from the installation; only the declared pyproject version string survives. Per audit instructions these are marked UNKNOWN rather than guessed.

---

## 5. Pinning Quality Classification

| Dependency | Class | Basis |
|---|---|---|
| ComfyUI core (image) | **PINNED** | explicit commit constant + forced checkout (comfyapp.py:8010, 8051) |
| ComfyUI core (local validation) | **PARTIALLY PINNED** | pinned commit + uncommitted source patch (divergence, §3) |
| nvidia/cuda base image | **FLOATING** | registry tag, no digest |
| torch / torchvision / torchaudio (cu130) | **FLOATING** | unpinned force-reinstall from cu130 index |
| triton | **PARTIALLY PINNED** | `>=3.0.0` |
| SageAttention | **PINNED** | tag v2.2.0 source build (but its transitive torch interplay floats) |
| comfy-cli | **PINNED** | ==1.3.7 |
| httpx (base) | **FLOATING** | >=0.27.0 |
| CacheDiT lock family (cache-dit, transformers, diffusers, huggingface-hub, accelerate, safetensors, tokenizers) | **PINNED** | exact ==versions in lock + constraints on all custom-node installs + build gate |
| All other transitive Python deps (numpy, scipy, pillow, aiohttp, kornia, spandrel, pydantic …) | **FLOATING** | resolved at build time; only 7-package constraints apply |
| Custom nodes (all 22) | **FLOATING** | working-tree copies; commits incidentally observable, never recorded/enforced; 13 of 22 lack `.git` entirely |
| comfyui-frontend-package | **PINNED (transitive)** | ==1.44.19 via core requirements; moves with ComfyUI pin |
| Python interpreter | **PARTIALLY PINNED** | `add_python="3.11"` fixes major.minor; micro float |
| apt packages | **FLOATING** | name-only on Ubuntu 24.04 |
| Node JS extension assets | **FLOATING** | travel with node working trees |

### Ways reproducibility currently breaks

1. **Git HEAD drift**: any upstream push changes a fresh clone relative to today's working trees; nothing detects it because commits are not recorded anywhere.
2. **PyPI ranges**: httpx, triton, and every unconstrained transitive dep resolve to build-day latest.
3. **Transitive deps**: the 7-package lock does not constrain their own dependencies (numpy, regex, filelock, etc.).
4. **CUDA/Torch coupling**: floating cu130 torch × floating SageAttention build × Blackwell arch list — a new torch can invalidate the baked SageAttention `.so` ABI assumptions; only build-time import gates protect, and they run at image build, not per restore.
5. **ComfyUI API changes**: moving the pin forward silently changes core APIs the runtime monkeypatches (`free_memory`, `soft_empty_cache`, `load_models_gpu` wrappers at comfyapp.py:15118+, `cast_to` forensics) — guarded fail-open, but behavior then diverges silently.
6. **Frontend-extension changes**: node web/js assets float with node trees; core frontend package moves with the pin.
7. **Manager package updates**: Manager itself is baked at an arbitrary main-branch commit (263 past its last tag) — its own DB-driven restore behavior is not reproducible either.
8. **Working-tree deployment**: the plugin's 124 uncommitted changes are invisible to any git-based restoration.

---

## 6. Manual / Container Requirements (high-value portability risks)

| Requirement | Detail | Evidence |
|---|---|---|
| apt/system packages | git, libgl1, libglib2.0-0, libsm6, libxrender1, libxext6, ffmpeg, build-essential, ninja-build, clang (Ubuntu 24.04) | comfyapp.py:8028–8043 |
| CUDA toolkit (devel) | CUDA 13.0 devel base required at BUILD time for SageAttention compile; `TORCH_CUDA_ARCH_LIST=12.0+PTX` targets Blackwell | comfyapp.py:8024, 8069 |
| GPU during image build | torch index resolution + sage build steps run with `gpu="a10g"` | comfyapp.py:8045–8086 |
| C/C++ toolchain env | `CUDA_HOME=/usr/local/cuda`, `MAX_JOBS=4`, `--no-build-isolation` | comfyapp.py:8069–8072 |
| Specific Torch/CUDA | cu130 wheel index mandatory for current behavior | comfyapp.py:8058–8063 |
| Browser/frontend build | none required (prebuilt node web assets copied verbatim) | §2.4 |
| Environment variables | ~40 baked runtime vars (`_V2_RUNTIME_ENV`), incl. inductor/triton cache paths, preload policy, repair mode; 2 baked from caller shell at deploy | comfyapp.py:8091–8143 |
| Credentials | HF / Civitai tokens needed for some model downloads; token FILES (`.hf_token`, `.civitai_token`) explicitly excluded from image; manifests record `requires_*_token` flags | comfyapp.py:6865–6866, 6896–6897; model_manifest.py:67–68 |
| Persistent filesystem | 4 Modal Volumes: models (`/root/models`), custom-nodes (`/root/custom_nodes_vol`), runtime-config, prompt-cache; snapshot certificates + generation records persisted there | comfyapp.py:8438–8479; custom_node_parity.py:9–16 |
| Compilation | SageAttention CUDA extension (only source-built Python artifact) | §2.1 |
| Modal platform | account, `modal` Python package on host, snapshot/restore machinery (GPU-arch-coupled memory snapshots) | __init__.py:973–974; comfyapp.py:387 |

---

## 7. ComfyUI Manager Restorability Classification

Manager is installed locally (declared 3.40, git ≈3.39.3+263) and baked into the image like any node. Classification of workflow-required nodes (Manager restores *a* version from its DB; **no evidence** it guarantees today's exact commits — claimed ambiguous where applicable):

| Node | Classification | Rationale |
|---|---|---|
| comfyui-impact-pack | MANAGER-BUT-VERSION-AMBIGUOUS | listed in Manager DB; local copy has no git so exact build unknown; 8.28.3 recoverable only if DB still serves it |
| comfyui-easy-use | MANAGER-BUT-VERSION-AMBIGUOUS | same pattern (v1.3.6 declared) |
| comfyui-custom-scripts | MANAGER-BUT-VERSION-AMBIGUOUS | same (v1.2.5) |
| comfyui-levelpixel | MANAGER-BUT-VERSION-AMBIGUOUS | same (v1.3.3) |
| rgthree-comfy | MANAGER-BUT-VERSION-AMBIGUOUS | same (v1.0.2605082257) |
| comfyui_lg_samplingutils | UNKNOWN | small-distribution node; DB presence unverified in this audit |
| RES4LYF | MANAGER-BUT-VERSION-AMBIGUOUS | DB-listed upstream; commit `119679d8` not guaranteed |
| ComfyUI_LayerStyle | MANAGER-BUT-VERSION-AMBIGUOUS | same for `d94bef1e` |
| ComfyUI-KJNodes | MANAGER-BUT-VERSION-AMBIGUOUS | same for `3df15ed8` |
| masquerade-nodes-comfyui | MANAGER-BUT-VERSION-AMBIGUOUS | tag v0.9 base recoverable; +6 commits not guaranteed |
| ComfyUI-CacheDiT | MANUAL-GIT | **fork** (Jasonzzt) — Manager may map to a different upstream repo; commit `ab1a1448` must be checked out manually |
| PathchSageAttentionKJ's sageattention pkg | SYSTEM/DOCKER REQUIRED | CUDA source build at pinned tag; impossible via Manager |
| CacheDiT python stack | MANUAL-PYTHON | 7-package constraints lock + build gate must be replicated |
| comfyui-modal (plugin) | MANUAL-GIT (+ working tree) | private repo Parlaxz/comfyui-modal; branch r42-golden-reconciliation @ 0c59f46 + 124 uncommitted changes — **no ref reproduces the deployed bytes** |
| ComfyModalProduction* classes | NOT RESTORABLE ANYWHERE ELSE | internal-only classes injected into compiled workflows |
| ComfyUI core | MANUAL-GIT/PINNED | Manager updates float; exact reproduction requires the explicit commit checkout |

---

## 8. Model Dependency Manifest — metadata assessment

Identity fields a portable description needs vs. what persists today:

| Field (proposed) | `.model_manifest.json` | `.studio_model_library.json` | workflow export (`export_workflow_manifest`) | Studio manifest format (WORKFLOW_MANIFEST_FORMAT.md — routes NOT wired) |
|---|---|---|---|---|
| role/type | folder + `WORKFLOW_ROLE_FOLDERS` mapping | folder | role via `extract_workflow_model_refs` | role, model_type, compatibility |
| filename | ✔ | ✔ | ✔ | ✔ |
| relative model folder | ✔ | ✔ | ✔ | folder |
| SHA-256 | field exists, **null in every observed entry** | computed on scan | not exported | optional, validated 64-hex |
| size | ✗ | ✔ | ✗ | optional int |
| source/provider reference | url + source_kind + token flags | source_urls, provider, revision | url, source_kind, token flags | provider, revision, source_urls[] |
| swap/remove semantics | remove_on_swap | — | — | — |

Gap summary: hashes are never populated in the master manifest; the wired export path omits size/hash; the well-designed Studio manifest format (models[] with sha256/size/provider/revision/source_urls, custom_nodes[] with **required** repo_url+revision+classes) exists as a pure module (`studio_workflow_manifest.py`) but nothing imports it in production yet. No network/download behavior is proposed here — identity fields only.

---

## 9. Reproducibility Under Updates — detection capability

| # | Scenario | What current system detects | Verdict |
|---|---|---|---|
| 1 | Same workflow JSON, newer ComfyUI | Pin is a code constant — silent unless someone edits it; runtime does NOT verify the running ComfyUI commit against any manifest; local-vs-image patch divergence undetected remotely | NOT DETECTED at runtime |
| 2 | Same JSON, newer custom-node HEAD | Content-generation hash (canonical py/txt/toml/cfg bytes) changes → baked-manifest mismatch → `fail_fast` RuntimeError at startup; generation parity report logs direction | DETECTED (fail-closed) — but only for syncable trees, and identifies *that* something changed, not which version is correct |
| 3 | Same node packages, newer Python deps | Runtime validation compares requirements-file HASHES, not installed dists; a PyPI-side float with unchanged requirements.txt passes; only the 7 locked packages are enforced | MOSTLY NOT DETECTED |
| 4 | Same dep versions, different Torch/CUDA | Nothing pins torch; `snapshot_build_manifest` records `torch_version`/python at snapshot time (observability only); SageAttention `.so` gates run at build only | OBSERVED, NOT ENFORCED |
| 5 | Renamed/removed node class | Execution fails with ComfyUI's missing-class error; studio-side `DependencyResolver.resolve_custom_node_refs` can flag missing nodes for managed versions; benchmark path has no preflight class-presence check | PARTIAL (late, execution-time) |
| 6 | Changed node widget schema | No schema fingerprinting across node versions; graph_hash changes only when the JSON itself changes | NOT DETECTED |
| 7 | Model renamed, same bytes | Manifest/library keyed by (folder, filename) → rename breaks resolution ("unresolved"); sha256 exists in library but is not used to re-bind | NOT RECOVERABLE automatically |
| 8 | Same filename, different bytes | Library `record_is_installed` checks size+mtime fingerprint (weak); master manifest never verifies bytes; execution proceeds with whatever bytes are present | WEAK / NOT DETECTED |

---

## 10. Proposed Portability Manifest (design only — do not implement here)

Minimum manifest to ship alongside an exported workflow for deterministic diagnosis/restoration. Reuses existing project conventions (canonical JSON hashing per `production_workflow.py`; section shapes from `WORKFLOW_MANIFEST_FORMAT.md`):

```json
{
  "manifest_version": 1,
  "comfyui": {
    "repo_url": "https://github.com/Comfy-Org/ComfyUI",
    "commit": "<64-hex>", "tag": "v0.24.0", "version": "0.24.0",
    "local_patches": [{ "path": "comfy/model_management.py", "sha256": "<64-hex>" }]
  },
  "python": { "version": "3.11" },
  "torch_stack": {
    "torch": "<resolved>", "torchvision": "<resolved>", "torchaudio": "<resolved>",
    "index_url": "https://download.pytorch.org/whl/cu130", "triton": "<resolved>"
  },
  "system": {
    "base_image": "nvidia/cuda:13.0.0-devel-ubuntu24.04",
    "base_image_digest": "<optional digest>",
    "apt_packages": ["git", "libgl1", "..."],
    "cuda_arch_list": "12.0+PTX"
  },
  "custom_nodes": [
    { "name": "...", "repo_url": "...", "revision": "<commit-or-tag>",
      "classes": ["..."], "requirements_sha256": "<64-hex>",
      "install_method": "manager|git|zip", "manager_id": "<optional>" }
  ],
  "python_lock": {
    "constraints_file_sha256": "<64-hex>",
    "resolved": { "cache-dit": "1.2.3", "transformers": "4.55.2, "...": "..." }
  },
  "models": [
    { "role": "unet", "folder": "diffusion_models", "filename": "...",
      "sha256": "<64-hex|null>", "size": 0,
      "source_urls": ["..."], "provider": "huggingface", "revision": "main",
      "requires_tokens": [] }
  ],
  "frontend": { "comfyui_frontend_package": "1.44.19" },
  "env_keys": ["COMFYMODAL_REQUIREMENTS_REPAIR_MODE", "..."],
  "warnings": [
    "torch stack unpinned at capture time",
    "node X has no git provenance (version Y declared)",
    "workflow references plugin-internal classes: ComfyModalProductionOutput"
  ]
}
```

Rules: no secret values (token file contents, API keys) ever enter the manifest — only boolean/token-required flags; every field above traces to an observed need (§2–§9); unresolved values stay `null` with a warning rather than being guessed. The existing pure module already validates the two hardest sections (models, custom_nodes) — wiring it is G4 territory.

---

## 11. Risk Contribution to Phase G

| Area | Risk | Driver |
|---|---|---|
| ComfyUI core (remote) | LOW | commit-pinned, deliberate re-pin flow, layer-cache-busting pin string |
| CacheDiT python family | LOW | exact lock + constraints + build gate |
| SageAttention | LOW–MEDIUM | tag-pinned but source-built against floating torch; arch-list coupling |
| Custom nodes WITH git remotes (9 of 22) | MEDIUM | commits discoverable today but recorded nowhere; Manager restore ≠ exact commit |
| Custom nodes WITHOUT git (13 of 22) | MEDIUM–HIGH | provenance = declared version string only; exact build unrecoverable |
| apt/base-image/python-micro floats | MEDIUM | deterministic-in-practice short-term, unverifiable long-term |
| torch/torchvision/torchaudio cu130 | HIGH | fully floating; couples SageAttention, snapshot certs, numerics |
| comfyui-modal plugin itself | HIGH | private repo + working-tree deploy (124 dirty files) + internal output classes embedded in compiled workflows |
| Local ComfyUI patch divergence | HIGH | local ≠ remote soft-cache behavior; patch exists in no ref |
| Model identity | HIGH | sha256 never populated; rename/byte-swap scenarios undetectable |

**Derived recommendation:** dependency side enters Phase G as HIGH risk; the cheapest de-risking sequence is (1) populate model hashes, (2) record custom-node commits/versions at bake time into the existing baked manifest, (3) pin the torch trio to resolved versions, (4) reconcile or ship the local model_management patch.

---

## 12. Test / Validation Plan (future, no implementation in this audit)

1. **Manifest generation determinism** — same custom-node tree twice → byte-identical portability manifest (extends existing `_maybe_write_baked_manifest` idempotence guarantees).
2. **Pin fidelity** — property test: every `custom_nodes[]` entry has non-empty `repo_url`+`revision`; torch_stack entries are exact versions, not ranges; manifest fails readiness when a required node lacks revision (reuse `check_readiness` semantics).
3. **Missing-node diagnosis** — pure function: (workflow class set ∪ manifest) → deterministic `{missing_classes, unmapped_nodes, core_classes}` report; golden-file tested.
4. **Version-mismatch diagnosis** — simulate node at older/newer revision than manifest → stable warning strings + exit codes.
5. **No-secret export** — exported manifest asserted free of `.hf_token`/`.civitai_token` contents and key-shaped strings; denylist grep over serialized bytes.
6. **Reproducibility-report stability** — fixture tree → golden hash of the full report; any schema change must bump `manifest_version`.
7. **Drift blind-spot documentation test** — mutate a tracked (.py/.txt/.toml/.cfg) file → generation MUST change; mutate an untracked extension (e.g., .json config) → assert documented non-change (pins current fingerprint scope as intentional).
8. **Core-parity check** — compare running ComfyUI `git rev-parse HEAD` + patched-file hashes against manifest at startup in `fail_fast` (closes §9 scenario 1).

---

## 13. Evidence Index

- Image construction: `comfyapp.py:8004–8433` (pin constant 8010; base/apt/pip 8022–8087; env 8091–8143; requirements loop 8149–8238; node copy 8245–8286; baked manifest 8294–8368)
- Lock file: `cachedit_dependency_lock.txt` (7 exact pins)
- Requirements repair: `comfyapp.py:14396–14529`; production mode baked `fail_fast` (comfyapp.py:8117)
- Volume sync/parity: `comfyapp.py:3915–3982`; `comfymodal_runtime/custom_node_parity.py`
- Fingerprints: `comfyapp.py:3814–3880` (content-hash generation, schema v2)
- Dependency manifest logic: `comfymodal_runtime/dependency_manifest.py` (identity = combined hash + CN fingerprint + generation + repair mode; no ComfyUI commit, no package versions)
- Registry/discovery: `custom_node_registry.py` (records repo_url + installed_commit opportunistically; empty when no .git)
- Resolver: `dependency_resolver.py` (installed/missing/wrong_version/unknown states)
- Models: `model_manifest.py`, `model_library.py`, `.model_manifest.json` (sha256 null), `WORKFLOW_MANIFEST_FORMAT.md` (unwired portable format)
- Local core patch: `git status` of ComfyUI root (M comfy/model_management.py; ?? comfy/__init__.py); local file lines 2027–2057 import `comfymodal_runtime.empty_cache_bypass`; `tests/test_v2_batch_e5_empty_cache_bypass.py:210–221`
- Plugin working tree: `git log` → 0c59f46 (r42-golden-reconciliation); `git status --porcelain` → 124 entries
- Workflow node classes: `latest_benchmark_workflow.json` payload.prompt; core attribution verified against `nodes_model_patch.py`, `nodes_images.py`, `nodes_logic.py`, `nodes_primitive.py`, `nodes_sd3.py`, `nodes_model_advanced.py`
- Frontend pin: ComfyUI `requirements.txt:1` (`comfyui-frontend-package==1.44.19`)
- Deploy-time env baking: `comfyapp.py:8128–8142`; deploy fingerprints under `.v2ctl/deployments/`

Audit complete. Deploy/live/GPU/commit/push: **NONE**.
