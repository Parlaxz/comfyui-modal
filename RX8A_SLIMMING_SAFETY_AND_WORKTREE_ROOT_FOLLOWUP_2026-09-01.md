# RX8A — Slimming Safety and Isolated-Worktree Root Follow-up

Date: 2026-09-01  
Branch: `TESTING2`  
Scope: RX8 recheck plus the RX7 isolated-worktree root-resolution defect

## Executive result

RX8's filtering remains safe for the production custom-node runtime. RX8A made
one additional correctness fix only: Modal image patterns now encode
case-insensitive variants of the already-existing excluded directory names and
prefixes. No new lower-case exclusion class was added.

The RX7 root defect was real. The old resolver could select the collection
directory `.slim/worktrees` because it looked like a root containing several
node-like children. The canonical resolver now recognizes an isolated
`.slim/worktrees/<lane>` checkout, prefers its staged
`.slim/<lane>-custom-nodes` root, otherwise uses the canonical checkout's
`ComfyUI/custom_nodes` root, and never accepts the worktree collection itself.

## Independent accounting

The accounting used the actual parent `ComfyUI/custom_nodes` filesystem and the
installed Modal `FilePatternMatcher`, not Git-tracked files. The combined image
path also applied the runtime duplicate-directory filter used by `comfyapp.py`.
Volume content used the canonical `iter_publication_files()` walker and archive
builder.

| Set | RX8 report | RX8A live audit | Drift |
|---|---:|---:|---:|
| Image included bytes | 241,399,253 | 241,588,833 | +189,580 |
| Image included files | 4,007 | 4,010 | +3 |
| Volume semantic bytes | 240,548,979 | 241,582,204 | +1,033,225 |
| Volume semantic files | 4,005 | 4,008 | +3 |
| Deterministic gzip archive | 158,855,710 | 158,899,218 | +43,508 |

The drift is filesystem drift from concurrent work in the shared canonical
worktree, including changes inside the publishable `comfyui-modal` node; it is
not a new slimming decision. The current image-only set is exactly:

```text
example_node.py.example
websocket_image_save.py
```

Their combined size is 6,629 bytes, accounting for the image/Volume difference.
The current audit found 24 syncable custom-node directories. Building the same
archive twice produced identical bytes:

```text
archive_bytes=158899218
archive_sha256=a2a7315b7ed0fd8f56ef4cacfdaee706582c518eaa6c17920c1629122f68b71f
repeat_equal=True
generation=88f33efd2b0e74f7f72bd8ba4cd581704d2c6de5fca5a79f452e970d2627cb74
```

## Exclusion safety audit

### Recursive `**/` conversion

The old one-level image patterns used `*/` forms that did not cross multiple
path separators. RX8A retains those patterns and adds recursive `**/` forms.
Modal's installed matcher was exercised against nested paths. Directory
pruning remains safe because all patterns are positive ignores and no negated
pattern was introduced.

### `.repowise`

The live canonical node contains three files (about 26.8 MB): a pickle parse
cache and two analysis databases. No Python, JavaScript, package metadata, web
extension, node-registration, model, or runtime path read outside the cache
references `.repowise`. It is repository-analysis state, not a node resource.

### `ra11f`

The live canonical node contains the experiment harness and generated state
(15 files, about 15.7 MB in the audit, including bytecode). Its Python files
are used by the local experiment harness and tests, not by ComfyUI startup or
custom-node registration. No production runtime path read outside this
directory was found. Excluding it removes experiment tooling, not node
behavior.

### `reports`

The live report tree contains generated `.mjs`, JSON/JSONL, Markdown, and
screenshots. No production Python/JavaScript path read or package metadata
references it as a runtime directory. The `studio/workflows` matches found by
search are HTTP route names, not filesystem reads of `reports`.

### `example_workflows`

The audited instances contain example workflow JSON plus paired example media.
The largest is `RES4LYF/example_workflows` at about 170 MB. These files do not
provide node registration, package metadata, runtime Python, JavaScript web
extensions, models, or required configuration. They are optional example
content. The production workflow system lives in retained source and web
trees; no runtime path read of these directories was found.

### `workflows`

The audited instances are workflow reference media, principally
`RES4LYF/workflows` PNGs (about 53.7 MB), plus test/example JSON and repository
CI files under `.github/workflows`. No runtime Python or JavaScript resource
under these directories was found. Generic workflow execution and the Studio
workflow UI are retained outside these optional/reference trees.

### Generated JSON, screenshot/validation images, and Markdown

Generated JSON remains limited to known prefixes (`temp_`, `_last_`, `studio-`,
`clean_`, `latest_benchmark_`, `.modal_`, `.model_`, `.last_`, and `.profile_`)
with JSON case variants. Screenshot/validation filtering only matches those
words in image filenames and supported image extensions, with case variants.
Markdown uses explicit `.md`, `.mD`, `.Md`, and `.MD` patterns, including
recursive forms. Ordinary JSON metadata, runtime images/assets, and text files
remain publishable. Mixed-case directory/prefix patterns are now mirrored in
Modal and Python policies.

The audit searched Python, JavaScript, JSON, TOML/package metadata, web
extensions, node registration, and runtime path literals. No newly excluded
directory contained a production registration resource, required package
metadata, runtime model/asset, or runtime configuration. Users who relied on
bundled example workflow files will no longer receive those optional examples;
this is an intentional content trade-off, not runtime loss.

## Root-level generic-node behavior

The local ComfyUI `nodes.py` contract was verified:

- `init_external_custom_nodes()` enumerates both files and directories under
  each custom-node path (`nodes.py:2299-2308`).
- `.py` files are passed to `load_custom_node()` (`nodes.py:2192-2212`), which
  imports the file and consumes `NODE_CLASS_MAPPINGS`
  (`nodes.py:2240-2247`).
- `websocket_image_save.py` remains in the image and defines
  `SaveImageWebsocket` plus its mapping (`websocket_image_save.py:13-48`).
- Root files inside syncable node directories remain included, including
  `__init__.py`, node modules, package metadata, web directories, and permitted
  runtime assets. The only image-only files are the two direct parent-root
  files listed in the accounting section.

RX8 did not turn image publication into a directories-only contract. The
combined image path still copies the parent custom-node root and adds duplicate
directory patterns only after the canonical top-level filter.

## Isolated-worktree root resolution

The canonical implementation is `comfymodal_runtime/custom_node_root.py`. It
returns a `CustomNodesRootResolution(root, method, candidates)` record and
exposes its method/candidate list through `as_dict()`.

Resolution order:

1. Non-empty `COMFYMODAL_LOCAL_CUSTOM_NODES` configuration wins. An explicit
   empty value and an invalid configured root fail clearly.
2. For `<repo>/.slim/worktrees/<lane>`,
   `<worktree>/.slim/<lane>-custom-nodes` wins when it contains one or more
   syncable custom-node directories under the canonical publication policy.
   The structural check uses the same syncable-node list as archive, image,
   Volume, and hash generation; unrelated/excluded entries do not qualify.
3. Without a staged root, canonical `ComfyUI/custom_nodes` wins. The
   `.slim/worktrees` collection is explicitly rejected.
4. More than one valid inferred/fallback root fails with an ambiguity error;
   no arbitrary ordering is used.
5. No valid root fails with an actionable configured-root message.

`comfyapp.py` now calls `resolve_custom_nodes_root_details()` directly and
records `custom_nodes_root_resolution_method` and
`custom_nodes_root_candidates` in build-context and requirements diagnostics.
The publication-policy resolver remains a compatibility wrapper to the same
canonical implementation, preventing image, archive, identity, and runtime
callers from drifting again.

The regression fixture reproduces RX7's topology:

```text
ComfyUI/custom_nodes/comfyui-modal/.slim/worktrees/rx7
ComfyUI/custom_nodes/comfyui-modal/.slim/worktrees/rx7a
ComfyUI/custom_nodes/comfyui-modal/.slim/worktrees/rx8
ComfyUI/custom_nodes/comfyui-modal/.slim/rx7-custom-nodes/
```

It covers canonical checkout, staged worktree roots containing zero, one, two,
three, and many syncable nodes, misleading excluded entries, unstaged worktree,
explicit root, empty root, ambiguous fallback candidates, collection
rejection, and diagnostics. The tests extract the actual resolver functions
from `comfyapp.py` with source-path fidelity, without executing unrelated
import-time build work.

## Remaining RX8 suite problems

The version test was stale: source is already `COMFYAPP_VERSION = "2.16.31"`,
while the old assertion hard-coded historical `2.16.27`. It now matches the
current source contract; the version was not reverted.

The publisher no longer owns a second `_CUSTOM_NODE_SYNC_EXCLUDE_DIRS` list.
The canonical owner is `publication_policy.EXCLUDED_DIR_NAMES`. The parity test
now asserts that `comfyapp.py`'s compatibility alias points to that canonical
policy and compares the authoritative set. No duplicate publisher alias was
restored.

## Validation

Focused checks passed:

```text
python -m unittest tests.test_rx8a_custom_node_root
Ran 10 tests — OK

python -m unittest tests.test_runtime_deployment_spec
Ran 52 tests in 0.546s — OK (skipped=1)

python -m unittest tests.test_comfyapp_volume_lifecycle
Ran 31 tests — OK

python -m unittest tests.test_custom_node_generation_parity.TestRoundTripAndPurity.test_generated_dirs_is_superset_of_archive_excludes tests.test_comfyapp_volume_lifecycle.TestMountCollisionRegression.test_COMFYAPP_VERSION_bumped
Ran 2 tests — OK
```

With a temporary configured root to avoid scanning the concurrent shared
worktree during ComfyApp import, the complete relevant set passed:

```text
tests.test_rx8a_custom_node_root
tests.test_runtime_deployment_spec
tests.test_comfyapp_volume_lifecycle
tests.test_custom_node_generation_parity
tests.test_comfyapp_packaging
tests.test_v2_custom_node_production_filter
tests.test_s2_golden_deploy
Ran 126 tests in 81.007s — OK (skipped=1)
```

No Modal deployment, remote probe, GPU request, or paid Golden run was made.
Unrelated concurrent modifications and staged files were not reset, cleaned,
or included in this lane's staging.

## Lane files

```text
comfyapp.py
comfymodal_runtime/custom_node_root.py
comfymodal_runtime/publication_policy.py
tests/test_comfyapp_volume_lifecycle.py
tests/test_custom_node_generation_parity.py
tests/test_runtime_deployment_spec.py
tests/test_rx8a_custom_node_root.py
RX8A_SLIMMING_SAFETY_AND_WORKTREE_ROOT_FOLLOWUP_2026-09-01.md
```

RX8 implementation files already committed at `dc94449` were not restaged as
part of this follow-up. Other agents' modified or untracked files remain
untouched.

RX8_ACCOUNTING_REPRODUCED=YES
RX8_RUNTIME_REACHABILITY_SAFE=YES
ROOT_LEVEL_NODE_BEHAVIOR_SAFE=YES
WORKTREE_ROOT_RESOLUTION_FIXED=YES
STALE_VERSION_TEST_RECONCILED=YES
PUBLICATION_COMPAT_TEST_RECONCILED=YES
IMAGE_INCLUDED_BYTES=241588833
VOLUME_INCLUDED_BYTES=241582204
REMOTE_CALLS=0
PAID_RUNS=0
RX8_ACCEPTED=YES
