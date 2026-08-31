# S4 Custom-Node Full-Content Publication Trust Repair

## Scope and boundary

This lane repairs one P0 correctness issue: receipt-only recovery must not
certify a desired full custom-node publication from a narrower code/deployment
identity. Local/unit/static validation was performed only. No Modal deployment,
live Volume mutation, or Golden remote run was performed.

## Pre-fix reproducer

The focused reproducer created one node containing unchanged `__init__.py` and
an included `config.json`, then changed only the JSON:

```python
before = compute_custom_node_hash([root])
before_manifest = build_source_identity(root).manifest_digest
(root / "NodeA" / "config.json").write_text('{"v":2}\n')
after = compute_custom_node_hash([root])
after_manifest = build_source_identity(root).manifest_digest
```

Observed before the fix:

```text
before == after                         True
before_manifest != after_manifest       True
```

Thus `publish_or_skip()` could read a persisted generation equal to the narrow
hash and recover a receipt containing the new full manifest without publishing
the changed JSON.

## Identity model

### Before

```text
canonical semantic publication files -> full manifest / archive
narrow .py/.js/.mjs source hash       -> generation record
receipt recovery: persisted generation == narrow hash -> trust full manifest
```

The two identities had different ownership but were used as though they were
the same proof.

### After

```text
code/source identity (.py/.js/.mjs)
  -> deployment/source concerns only

canonical semantic publication set (every non-excluded published path/byte)
  -> canonical manifest digest
  -> published-content generation
  -> desired identity, archive parity, Volume generation record/readback,
     post-publication proof, and receipt recovery
```

`build_source_identity()` now makes the manifest digest the publication
generation. An optional narrow provider value is retained separately as
`source_generation` and is not used to authorize full-content recovery.
`comfyapp.custom_node_source_generation()` and the remote post-extract record
use the shared full publication-generation helper. The stable shared
`comfyui-custom-nodes-publisher` ownership remains unchanged.

Exact receipt skips still return before archive construction or publisher
invocation. Missing, stale, or malformed receipts recover only after the
authoritative persisted full-content generation matches; otherwise publication
is required. Receipt writing remains after successful publisher status and
authoritative generation readback, followed by receipt reread/validation.

## Tests and checks

Successful local commands and results:

```text
rtk pytest -q tests/test_s2_golden_deploy.py tests/test_source_identity_publication.py
39 passed

rtk pytest -q tests/test_v2_custom_node_generation_identity.py tests/test_custom_node_generation_parity.py
32 passed, 1 skipped

rtk pytest -q tests/test_s1_publisher_bootstrap.py tests/test_runtime_deployment_spec.py
56 passed, 1 skipped

python -m py_compile comfyapp.py comfymodal_runtime/publication_policy.py \
  comfymodal_runtime/deployment_spec.py tools/v2_control/custom_nodes.py
passed

rtk git diff --check
passed
```

Total: **127 passed, 2 skipped**. The focused coverage includes exact skip,
missing/stale receipt recovery, malformed receipt fail-closed behavior, narrow
identity unchanged plus changed included JSON requiring publication, consumer
identity independence, ordinary runtime/source separation, true content
generation changes, archive/extract parity, authoritative remote generation
readback, and receipt ordering.

## Owned changed files

- `comfymodal_runtime/publication_policy.py` — canonical publication walker,
  canonical bytes, manifest digest, and full-content generation.
- `comfymodal_runtime/deployment_spec.py` — explicit documentation that the
  deployment hash remains the narrower source/code identity.
- `comfyapp.py` — remote/runtime generation records now use full-content
  generation.
- `tools/v2_control/custom_nodes.py` — publication identity and recovery now
  authorize against the full manifest generation; narrow provider identity is
  separate.
- `tests/test_s2_golden_deploy.py`
- `tests/test_v2_custom_node_generation_identity.py`
- `.opencode/skills/comfy-modal-core/SKILL.md`
- `.opencode/skills/comfymodal-golden-ops/SKILL.md`

Other files currently dirty in the shared worktree belong to concurrent RA
lanes and were not modified by S4.

## Durable skill updates

Both durable skills now state that receipt recovery requires authoritative full
published-content identity; code/deployment identity cannot prove full shared
Volume contents; missing receipt is not missing content, while matching narrow
source identity is not matching full content; and one canonical full-content
generation must span desired identity, publication, Volume readback, and
receipt recovery.

## Minimal later remote proof

Run only after an approved remote-validation window, using a fresh isolated
experimental app and the canonical control plane:

```powershell
python tools/v2ctl.py golden status --app <experimental-app>
python tools/v2ctl.py doctor --profile golden_p1 --app <experimental-app>
python tools/v2ctl.py golden deploy --app <experimental-app>
python tools/v2ctl.py --profile golden_p1 --app <experimental-app> source-probe
python tools/v2ctl.py golden status --app <experimental-app>
python tools/v2ctl.py doctor --profile golden_p1 --app <experimental-app>
python tools/v2ctl.py golden run --app <experimental-app>
```

The remote proof must show the publisher's persisted full-content generation
equals the desired generation after publication, and that a subsequent
missing/stale-receipt recovery with matching full generation performs no
archive/upload while a narrow-generation-only mismatch republishes. Do not
use the protected production app, deploy/run legacy BAT paths, mutate a live
Volume manually, or run Golden remotely as part of this batch.

S4_IMPLEMENTATION_COMPLETE=YES
PREFX_STALE_CONTENT_RECOVERY_REPRODUCED=YES
FULL_CONTENT_GENERATION_CANONICAL=YES
NARROW_IDENTITY_CAN_CERTIFY_FULL_CONTENT=NO
MISSING_RECEIPT_MATCHING_FULL_CONTENT_REPUBLISHES=0
MISSING_RECEIPT_MISMATCHING_FULL_CONTENT_RECOVERS=0
LOCAL_TESTS=127 passed, 2 skipped; py_compile passed; git diff --check passed
READY_FOR_REMOTE_VALIDATION=YES
REPORT=S4_CUSTOM_NODE_FULL_CONTENT_PUBLICATION_TRUST_REPORT.md
