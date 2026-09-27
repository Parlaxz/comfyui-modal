# RX8 — Custom-Node Deployment and Snapshot Footprint Slimming

Date: 2026-09-01  
Branch: `TESTING2`  
Repository: `custom_nodes/comfyui-modal`

## Result

The reported roughly 4 GB is primarily local checkout history, worktrees,
artifacts, reports, and development state. It is not the Modal custom-node
image payload and is not a CPU memory snapshot size.

| Measurement | Before (bytes) | After (bytes) | Change |
|---|---:|---:|---:|
| Local `comfyui-modal` checkout | 4,421,916,068 | not mutated | — |
| Modal custom-node image source payload | 574,169,494 | 241,399,253 | -332,770,241 (-57.95%) |
| Volume canonical custom-node content | 497,394,869 | 240,548,979 | -256,845,890 (-51.64%) |
| Volume reproducible gzip archive | 380,522,756 | 158,855,710 | -221,667,046 |

Image counts are raw bytes selected for `Image.add_local_dir(copy=True)`;
Volume counts are canonical semantic file bytes. The archive size is included
to show transport size, but is not substituted for Volume content size.

The deployment source root is the parent `ComfyUI/custom_nodes` directory,
which was 1,218,375,666 bytes at the initial accounting pass. This is a
separate number from the 4,421,916,068-byte `comfyui-modal` checkout.

## Why the checkout is approximately 4 GB

The read-only live filesystem audit used recursive file sizes, not Git-tracked
files. Category totals overlap by design because an artifact can also be a log
or a Markdown report.

| Category | Bytes | Files |
|---|---:|---:|
| `.git` | 126,397,350 | 1,028 |
| Worktrees (`.slim/worktrees`, `.git/worktrees`) | 2,459,773,751 | 33,436 |
| Reports/docs/text | 647,362,469 | 7,864 |
| Tests | 403,110,959 | 12,213 |
| Artifacts/logs | 2,227,506,460 | 7,404 |
| Archives | 2,340,162 | 119 |
| Images/media | 113,276,764 | 857 |
| Databases | 602,112 | 3 |
| Caches | 335,502,941 | 5,024 |
| `node_modules`/virtual environments | 68,403,362 | 3,631 |
| Python/source/assets by source extensions | 2,629,705,785 | 20,722 |

Largest checkout directories:

| Directory | Bytes |
|---|---:|
| `.slim` | 2,483,302,572 |
| `artifacts` | 1,256,445,708 |
| `.git` | 126,397,350 |
| `tests` | 62,014,432 |
| `.opencode` | 51,051,357 |
| `.repowise` | 26,696,555 |
| `.v2ctl` | 26,696,555 |
| `node_modules` | 17,415,023 |
| `ra11f` | 15,475,823 |
| `comfymodal_runtime` | 14,648,212 |

Largest individual checkout files:

| File | Bytes |
|---|---:|
| `.git/objects/pack/pack-7279c5c8d37212538082d72ec8e56d14041344f5.pack` | 104,612,641 |
| `my-repo.bundle` | 55,169,033 |
| `comfyui-modal-P4-all.bundle` | 50,344,927 |
| `repo.bundle` | 50,311,501 |
| `comfyui-modal-2026-08-30-updated.bundle` | 50,295,287 |
| `RV2B_REMOTE_GOLDEN_BASELINE_RAW_LOG.md` | 37,747,881 |
| `.repowise/parse_cache.pkl` | 26,201,255 |
| `V2_BATCH_E28_CRITICAL_PATH_IMPLEMENTATION_AND_VALIDATION.md` | 12,846,926 |

The existing `.gitignore` and `.modalignore` already excluded most checkout
noise. The important deployment bug was that the old explicit image ignore
list did not express recursive intent correctly for Modal: `*` does not cross
path separators, so `*/__pycache__/`, `*/*.md`, and similar patterns only
reached limited depth.

## Deployment paths audited

### Image

`comfyapp.py` resolves `_LOCAL_CUSTOM_NODES` to the parent custom-node root.
The default `CUSTOM_NODE_COPY_MODE` is `combined`. The active image path is
`comfyapp.py:8551-8557`:

```text
Image.add_local_dir(_LOCAL_CUSTOM_NODES,
                    "/root/comfy/ComfyUI/custom_nodes",
                    copy=True,
                    ignore=_COMBINED_CUSTOM_NODE_IGNORE_PATTERNS)
```

The per-node path at `comfyapp.py:8562-8569` uses the same base ignore policy.
The image now adds `image_ignore_patterns("**/")`, the recursive
Modal/Dockerignore form. It also uses the shared policy for generated JSON,
case variants of Markdown, screenshot/validation images, and the proven
non-runtime directories.

### Volume publication

`tools/publish_custom_nodes_volume.py:52-55` calls S2 `prepare_publication()`.
`tools/v2_control/custom_nodes.py:263-298` collects the semantic set from
`iter_publication_files()`, and `:355-374` builds the deterministic gzip/tar
archive. The Volume publisher is `comfyapp.py:9141-9301`: it validates and
extracts into staging, replaces old Volume content, writes the content-derived
generation record, and commits once.

The Volume policy intentionally publishes only syncable top-level custom-node
directories. Root-level files are not part of the shared Volume archive.

### Startup, import, and restore

`@modal.enter(snap=True)` startup is at `comfyapp.py:18410-18439`. It reloads
the Volume and calls `_sync_custom_nodes_from_volume()`. That function at
`:11727-11877` reads the authoritative generation/cheap state and, when
needed, calls `sync_custom_nodes_into_comfy()`; the latter creates the
Volume-managed directory links at `:3910-3997`.

ComfyUI's root-level custom-node Python files are loaded by upstream
`nodes.py`. The local `CustomNodeDiscovery._import_nodes()` at
`custom_node_registry.py:117-123` imports `nodes`, while directory discovery
is at `:143-192`. This is why the image deliberately retains root-level
`websocket_image_save.py` rather than excluding all root files.

## What was excluded and why

Already excluded before RX8 by the active policy were repository metadata,
tests, ordinary docs/reference, caches, virtual environments, dependency
build contexts, runtime output, duplicate ComfyModal worktrees, and archive/
log/patch extensions where the policy explicitly named them.

RX8 made these narrow changes:

1. Replaced the one-level image pattern construction with recursive `**/`
   patterns. This removes nested generated state, bytecode caches, reports,
   logs, and development directories that the Volume policy already rejected.
2. Added `.repowise`, `ra11f`, and `reports` to the shared directory policy.
   `.repowise` is a repository-analysis cache/database; `ra11f` is an
   experiment harness used by tests/reports; `reports` contains generated
   reports. Source grep found no runtime imports of these paths.
3. Added `example_workflows` and `workflows` to the shared directory policy.
   The current instances contain only example images/JSON, and source grep
   found no runtime imports or path reads for them. The singular `workflow`
   and `example_workflow` names were not added, avoiding broad narrowing of
   other nodes.
4. Made image patterns express the existing publication exclusions for
   generated JSON prefixes, screenshot/validation image names, and
   case-insensitive Markdown extensions. No blanket image, JSON, pickle,
   model, or text extension exclusion was added.

Root-level `websocket_image_save.py` (1,348 bytes) and
`example_node.py.example` (5,281 bytes) remain in the image. The former is
runtime-loaded by ComfyUI; retaining both avoids silently narrowing generic
root-level custom-node behavior. Their absence from the Volume is an existing
directory-only Volume contract, not an RX8 deletion.

## Before/after inclusion accounting

The accounting used the installed Modal `FilePatternMatcher` against the
actual filesystem, with directory pruning and relative-path matching. It did
not use Git-tracked files as a proxy.

| Set | Before files | Before bytes | After files | After bytes |
|---|---:|---:|---:|---:|
| Image `add_local_dir` selection | 6,344 | 574,169,494 | 4,007 | 241,399,253 |
| Volume semantic publication | 4,287 | 497,394,869 | 4,005 | 240,548,979 |

Using the 1,218,375,666-byte deployment source root:

| Excluded from | Before bytes | After bytes |
|---|---:|---:|
| Image selection | 644,206,172 | 976,976,413 |
| Volume semantic set | 720,980,797 | 977,826,687 |

Top included directories after slimming (image raw bytes):

| Directory | Bytes | Files |
|---|---:|---:|
| `ComfyUI_LayerStyle` | 64,183,405 | 510 |
| `comfyui_sam3` | 58,230,127 | 479 |
| `comfyui-modal` | 25,533,653 | 457 |
| `comfyui_controlnet_aux` | 22,824,245 | 716 |
| `comfyui-lora-manager` | 21,655,531 | 467 |
| `comfyui-manager` | 11,035,071 | 78 |
| `comfyui_fill-nodes` | 6,952,648 | 311 |
| `comfyui-easy-use` | 5,862,053 | 189 |
| `rgthree-comfy` | 3,384,440 | 247 |
| `RES4LYF` | 3,215,694 | 85 |

Largest retained files are runtime assets or source, not accidental checkout
state: `hand_landmarker.task` (7,819,105 bytes), SAM3 assets such as
`dog.gif` (7,111,659), `MANO_LEFT.pkl`/`MANO_RIGHT.pkl` (about 3.45 MB each),
and runtime Python such as `comfyapp.py` (1,235,048) and
`model_preload.py` (1,018,301). These were not removed by extension.

## Snapshot-memory distinction

### A. Modal image build/upload

**Proven affected.** The old and new file selections were run through Modal's
installed matcher. The recursive policy removes nested files from the
`copy=True` image build context. Actual Modal upload bytes can still differ
from included-tree bytes because Modal content-addresses/deduplicates already
uploaded blobs; no cache-dependent upload claim is made.

### B. Custom-node Volume

**Proven affected.** The shared semantic publication walker now excludes the
five proven non-runtime directory classes. The deterministic archive and
content byte totals were recomputed from the current filesystem. Publication
identity remains content-derived and deterministic; publisher app and Volume
names were not changed.

### C. CPU memory snapshot resident state

**NONE_FOUND for this change.** Filesystem bytes are not snapshot bytes. The
excluded directories contain no imports from the runtime path found in source
inspection. Removing them prevents filesystem/image/Volume shipping but does
not remove already-imported Python objects or native libraries from a process.
Conversely, retained custom-node modules can contribute to snapshot RSS if
ComfyUI imports them, and registries/caches can contribute if populated; that
is an import/runtime-state question, not a file-size conversion.

Existing evidence supports this separation: the snapshot trace records
`loaded_module_count=10404`, model-eviction RSS observations, and explicit
cleanup of model/worker state before capture. Those measurements do not
attribute filesystem bytes to snapshot RSS and do not prove that this filter
change changes RSS. No direct CPU RSS experiment was justified or performed.

## Runtime reachability and controls

The active source selection still reports 24 syncable custom-node directories,
including canonical `comfyui-modal` and all Golden-required external nodes.
The final publication set contains 4,005 files, including 288 published
Python/JavaScript source files and 89 files under
`comfyui-modal/comfymodal_runtime`.

No loader, sampler, CLIP, UNET, VAE, or QD code was changed. The canonical
control remains untouched: RTX PRO 6000, CPU 4, RAM 16384 MiB, legacy QD,
cast-once off, diagnostics off, durability off. No generic custom-node
directory or runtime asset was excluded based only on extension.

## Tests and probes

Passed:

```text
python -m unittest tests.test_runtime_deployment_spec tests.test_v2_custom_node_production_filter tests.test_s2_golden_deploy
Ran 52 tests in 0.139s — OK (skipped=1)

python -m unittest tests.test_comfyapp_packaging
Ran 14 tests in 0.797s — OK

python -m unittest tests.test_ra11f_resolver tests.test_ra11f_process tests.test_ra11f_subprocess
Ran 9 tests in 1.773s — OK
```

The focused image/build-context test from the first implementation pass also
passed 15 tests. A broader earlier suite reported one unrelated pre-existing
failure: `tests.test_comfyapp_volume_lifecycle.TestMountCollisionRegression.test_COMFYAPP_VERSION_bumped`
expects `COMFYAPP_VERSION = "2.16.27"`, while source is already `2.16.31`.
The custom-node parity suite also has a pre-existing error because
`tools.publish_custom_nodes_volume` no longer exports the removed
`_CUSTOM_NODE_SYNC_EXCLUDE_DIRS` compatibility name. Neither was changed to
mask RX8.

No remote Modal build-size probe was performed. The local installed Modal
matcher and deterministic archive builder were sufficient; no paid Golden
performance cohort was run.

## Exact files changed

```text
comfyapp.py
comfymodal_runtime/publication_policy.py
tests/test_comfyapp_build_context.py
tests/test_runtime_deployment_spec.py
RX8_CUSTOM_NODE_DEPLOYMENT_AND_SNAPSHOT_FOOTPRINT_SLIMMING_REPORT_2026-09-01.md
```

Untracked RX7 report files already present in the shared checkout were not
modified or staged.

LOCAL_TOTAL_BYTES=4421916068
IMAGE_INCLUDED_BEFORE_BYTES=574169494
IMAGE_INCLUDED_AFTER_BYTES=241399253
VOLUME_INCLUDED_BEFORE_BYTES=497394869
VOLUME_INCLUDED_AFTER_BYTES=240548979
SNAPSHOT_IMPACT=NONE_FOUND
RUNTIME_BEHAVIOR_CHANGED=NO
QD_CONTROL_CHANGED=NO
