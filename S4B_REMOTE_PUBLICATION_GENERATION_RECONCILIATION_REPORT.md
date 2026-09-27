# S4B Remote Publication Generation Reconciliation

**Date:** 2026-08-30  
**Scope:** custom-node publication generation/readback only  
**Protected Golden app:** not touched

## Executive result

RV2 stopped before deployment because the old shared publisher returned a
narrow source identity and no authoritative readback:

```text
expected_generation=e9c604ad4d43e95a...
result_generation=7fc71a1f6e08ad80...
readback_generation=null
```

The exact local values proved that `7fc71a1f6e08ad8057c50b64117994eab86c95b7a96afa01e21ca7d8af0b9d04`
was the narrow deployment/source hash, not the full publication-content hash.

The final repaired remote publication established this single chain:

```text
desired_full_content_generation
= publisher_content_generation
= committed_volume_readback_content_generation
= receipt_content_generation
= f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014
```

The final unchanged-content check returned `action=skip`, `reason=exact_match`,
and the publisher callback was not invoked.

## Final identity table

| surface | value | algorithm | exact bytes/manifest represented | producer | consumer |
|---|---|---|---|---|---|
| `desired_full_generation` | `f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014` | SHA-256 | 4,273 canonical semantic files; 496,786,363 canonical bytes; manifest entries are normalized relative `path`, canonical `size`, and per-file SHA-256 | `collect_semantic_files()` / `build_source_identity()` | publication gate and archive builder |
| `publisher_request_generation` | `f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014` | same manifest SHA-256 | the deterministic tar.gz archive built from the exact desired semantic file tuple; the request transport is `archive_data: bytes` and intentionally has no separate ambiguous generation field | host `prepare_publication()` / `build_archive()` | shared `sync_custom_nodes_to_volume(archive_data)` |
| `publisher_computed_generation` | `f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014` | same manifest SHA-256 after extraction | extracted Volume tree, walked through the same canonical policy after resolving the Modal mount-root symlink | remote `custom_node_source_generation()` | publisher result and generation record |
| `publisher_result_generation` | `f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014` | explicit `content_generation` field | publisher-computed full content identity; `generation` is no longer accepted as the certification field | remote result object | host `publish_or_skip()` |
| `volume_written_generation` | `f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014` | same manifest SHA-256 | `.comfymodal_control/custom_nodes_generation.json`, schema 2, `content_generation`; compatibility `generation` echo equals it | remote publisher before one Volume commit | host readback |
| `volume_readback_generation` | `f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014` | same manifest SHA-256 | committed Volume record read through logical path `.comfymodal_control/custom_nodes_generation.json` | host `Volume.read_file()` after publisher return | receipt gate |
| `receipt_generation` | `f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014` | same content identity; receipt integrity is an additional SHA-256 over canonical receipt JSON | verified schema-2 receipt at `.comfymodal_control/custom_nodes_publication_receipt.json`, including file count, byte count, manifest digest, publisher/ownership marker, and integrity digest | host receipt creation after readback | exact skip/recovery and Golden publication precondition |

Separate deployment/source identity at the final source tree:

```text
narrow_source_generation=
a27093ebd4d7647c06976f430c46883b223e0a7159fc0a214130a46da0436c8c
```

That value is SHA-256 over the narrower `.py`/`.js`/`.mjs` source file map,
using sorted names, per-file SHA-256 values, and path/NUL separators. It is
not used to certify Volume content.

## Canonical identity trace

1. **Semantic walker** — `publication_policy.iter_publication_files()` walks
   only approved top-level custom-node directories, excludes control/build/test
   state, rejects inner symlinks/special files, and resolves only the expected
   Modal mount-root symlink in `comfyapp.custom_node_source_generation()`.
2. **Semantic manifest** — each included file is represented by normalized
   relative path, canonical byte size, and SHA-256 of canonical bytes. Text
   extensions are CRLF/LF normalized; other included files are byte exact.
3. **Desired generation** — sorted manifest entries are serialized with
   `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))`
   and hashed with SHA-256.
4. **Source/deployment identity** — `deployment_spec.compute_custom_node_hash()`
   remains a separate narrow `.py`/`.js`/`.mjs` identity. The caller may retain
   it as `source_generation`, but `CustomNodeSourceIdentity.content_generation`
   is always the manifest digest.
5. **Publication request** — the host packages the already-collected semantic
   files into deterministic gzip/tar bytes (`mtime=0`, uid/gid 0, fixed mode)
   and sends those bytes as `archive_data`. The archive is not treated as a
   content-generation substitute.
6. **Shared publisher input** — the stable
   `comfyui-custom-nodes-publisher` receives the archive and extracts it into
   staging on the `comfyui-custom-nodes` Volume.
7. **Publisher calculation** — after replacement, the publisher computes the
   full manifest generation from the extracted tree, not the narrow deployment
   hash and not the transport/archive hash.
8. **Publisher result** — the result exposes the full value explicitly as
   `content_generation`, with `status=ok` and the generation-record path.
9. **Volume record** — the publisher writes schema-2
   `.comfymodal_control/custom_nodes_generation.json` with `content_generation`
   and an equal compatibility `generation` echo, then performs one commit.
10. **Receipt** — the host does not create a receipt until publisher status,
    direct committed Volume record readback, and full-generation equality all
    pass. It writes schema-2/protocol-2 receipt content and rereads/validates it.
11. **Authoritative readback** — on the host, Modal's direct `Volume.read_file()`
    is authoritative. Container-only `Volume.reload()` is not called from the
    host control plane; calling it there raises `reload() can only be called
    from within a running function`.
12. **Golden precondition** — the control plane accepts publication only for a
    `published_verified` or full-generation-authorized recovery decision. A
    result mismatch, missing/malformed record, failed readback, or receipt
    mismatch remains a hard failure.

## Root cause

### Primary cause: stale shared publisher generation algorithm

The RV2 result was not arbitrary:

```text
current pre-repair full semantic generation = e9c604ad4d43e95a278e26cd2ff0b7d13009bf3d58559ab281fd8e980d92c437
current pre-repair narrow source generation  = 7fc71a1f6e08ad8057c50b64117994eab86c95b7a96afa01e21ca7d8af0b9d04
RV2 result generation                       = 7fc71a1f6e08ad8057c50b64117994eab86c95b7a96afa01e21ca7d8af0b9d04
```

The stable shared publisher was running a deployment whose publication
generation behavior still represented the narrow source identity. Its
`comfyapp_version` was `2.16.31`, which was not a sufficient source identity.
The publisher was redeployed through the canonical bootstrap path after each
publication-only correction; the final valid deployment advanced Modal app
version `6 -> 7`.

### Secondary causes of `readback_generation=null` / failed certification

Two independent readback issues were exposed while repairing the stale
publisher:

* The Modal Volume mount appears in the remote container as the symlink
  `/root/custom_nodes_vol`. The canonical walker initially rejected that
  expected mount root. The adapter now resolves that root while continuing to
  reject symlinked content within the publication tree.
* The host control plane attempted container-only `Volume.reload()`. Modal
  raised `RuntimeError: reload() can only be called from within a running
  function`. The host now reads the committed record directly with
  `Volume.read_file()` and fails closed on any read ambiguity.

The publisher itself writes the record before its single commit. The final
remote result and direct host readback prove that commit and readback are
working after those corrections.

## Hypothesis disposition

| hypothesis | disposition | evidence |
|---|---|---|
| A. Local desired full, deployed publisher narrow | **PROVEN** | RV2 result exactly equals the narrow SHA-256 and differs from desired full. |
| B. Publisher hashes archive/transport bytes | **REFUTED for final path** | Final remote result is `content_generation` equal to the semantic manifest; archive/transport hashes are separate fields in local regression coverage. |
| C. Caller passes one hash, publisher overwrites it | **NOT the primary cause** | Request contains archive bytes; the stale publisher independently selected the narrow algorithm. Final publisher computes and returns the full field. |
| D. Stable publisher deployment was stale | **PROVEN** | Behavior matched the pre-S4 narrow algorithm; bootstrap advanced the stable publisher from version 1 to 7 across source repairs. |
| E. Result field was a legacy hash while record was correct | **REFUTED** | RV2 result was the narrow algorithm, and readback was null. Final result has explicit `content_generation`; a `generation`-only result is rejected. |
| F. Volume record path differed | **REFUTED in final path** | Remote result path `/root/custom_nodes_vol/.comfymodal_control/custom_nodes_generation.json` and host logical path agree. |
| G. Commit/reopen ordering caused null | **REFUTED as final cause** | Publisher writes record before one commit; final direct readback equals the publisher result. Host `reload()` misuse, not missing commit, was the refresh error. |
| H. Record schema changed and reader ignored it | **SUPPORTED as hardening risk, not RV2 primary cause** | Schema-1/generation-only records are now rejected; schema-2/content-generation records are required. |
| I. Recovery returned receipt identity only | **REFUTED** | Final recovery/skip requires authoritative Volume content-generation equality; receipt-only or narrow-only equality cannot skip. |
| J. Walker/normalization differed | **SUPPORTED as a discovered remote mount adaptation** | The expected mount-root symlink needed resolution; the canonical semantic policy remains shared after resolution. |

## Repair and regression coverage

The repair is limited to custom-node publication identity/readback:

* one shared semantic walker and manifest digest;
* explicit `content_generation` on source identity, publisher result, Volume
  record, and receipt;
* schema/protocol versioning and fail-closed legacy/malformed handling;
* strict no-fallback generation-record writer;
* explicit failure when remote canonical generation computation fails;
* expected Modal mount-root resolution only;
* direct host committed-record readback instead of container-only reload;
* publisher-result, Volume-readback, and receipt equality before certification;
* exact unchanged receipt skip/recovery retained.

Local final publication/control-plane validation:

```text
rtk pytest -q tests/test_s2_golden_deploy.py tests/test_source_identity_publication.py tests/test_v2_custom_node_generation_identity.py tests/test_custom_node_generation_parity.py tests/test_s1_publisher_bootstrap.py tests/test_runtime_deployment_spec.py tests/test_golden_p1_wiring.py
164 passed, 3 skipped

python -m py_compile comfyapp.py comfymodal_runtime/publication_policy.py comfymodal_runtime/deployment_spec.py tools/v2_control/custom_nodes.py tools/v2_control/cli.py modal_client.py tests/test_s2_golden_deploy.py tests/test_s1_publisher_bootstrap.py tests/test_v2_custom_node_generation_identity.py tests/test_custom_node_generation_parity.py
passed

rtk git diff --check
passed
```

Focused tests cover identical caller/publisher manifest generation, changed
JSON with unchanged narrow identity, explicit publisher result fields,
schema-2 record/readback, stale/malformed receipt and record fail-closed
behavior, exact skip, archive/transport separation, legacy generation-only
writer rejection, mounted-root adaptation, inner symlink rejection, and
host/fake Volume refresh semantics.

## Complete raw deployment/publication verification log

The following are the complete outputs of the remote actions in this lane.
All publisher deployments used the canonical shared publisher bootstrap; no
Golden deploy/run command was invoked.

### Initial stale-publisher evidence from RV2

```text
command: python tools/v2ctl.py --profile golden_p1 --set COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1 golden deploy --app batch-rv2-golden-baseline
ERROR: Golden deploy requires verified custom-node publication: publication_incomplete result={"comfyapp_version":"2.16.31","error":null,"expected_generation":"e9c604ad4d43e95a","readback_generation":null,"reason":null,"result_generation":"7fc71a1f6e08ad80","status":"ok"}
EXIT_CODE=1
```

### Final stable identity measurement before successful smoke

```text
desired_full_content_generation=f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014
repeat_equal=True
manifest_digest=f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014
narrow_source_generation=a27093ebd4d7647c06976f430c46883b223e0a7159fc0a214130a46da0436c8c
file_count=4273
total_bytes=496786363
generation_record_schema=2
generation_record_path=.comfymodal_control/custom_nodes_generation.json
publisher_source_file=comfyapp.py
comfyapp_version=2.16.31
```

### Shared publisher bootstrap history

```text
command: python tools/v2ctl.py --profile golden_p1 golden publisher-bootstrap
[v2ctl.publisher-bootstrap] app=comfyui-custom-nodes-publisher command=modal deploy -m comfyapp --name comfyui-custom-nodes-publisher
[v2ctl.publisher-bootstrap] exit=0 version=1->2

command: python tools/v2ctl.py --profile golden_p1 golden publisher-bootstrap
[v2ctl.publisher-bootstrap] app=comfyui-custom-nodes-publisher command=modal deploy -m comfyapp --name comfyui-custom-nodes-publisher
[v2ctl.publisher-bootstrap] exit=0 version=2->3

command: python tools/v2ctl.py --profile golden_p1 golden publisher-bootstrap
[v2ctl.publisher-bootstrap] app=comfyui-custom-nodes-publisher command=modal deploy -m comfyapp --name comfyui-custom-nodes-publisher
[v2ctl.publisher-bootstrap] exit=0 version=3->4

command: python tools/v2ctl.py --profile golden_p1 golden publisher-bootstrap
[v2ctl.publisher-bootstrap] app=comfyui-custom-nodes-publisher command=modal deploy -m comfyapp --name comfyui-custom-nodes-publisher
[v2ctl.publisher-bootstrap] exit=0 version=4->5

command: python tools/v2ctl.py --profile golden_p1 golden publisher-bootstrap
[v2ctl.publisher-bootstrap] app=comfyui-custom-nodes-publisher command=modal deploy -m comfyapp --name comfyui-custom-nodes-publisher
[v2ctl.publisher-bootstrap] exit=0 version=5->6

command: python tools/v2ctl.py --profile golden_p1 golden publisher-bootstrap
[v2ctl.publisher-bootstrap] app=comfyui-custom-nodes-publisher command=modal deploy -m comfyapp --name comfyui-custom-nodes-publisher
[v2ctl.publisher-bootstrap] exit=0 version=6->7
```

The redeploys corresponded to the proven stale algorithm, strict writer,
fail-closed computation diagnostics, mount-root adaptation, host refresh
attempt, and final host-reload correction. No publisher redeploy was performed
after the final successful validation.

### Intermediate fail-closed publication observations

```text
command: python tools/publish_custom_nodes_volume.py
[v2.volume_publish] source_root=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes
[v2.volume_publish] nodes=24
[custom_nodes.publish] decision=publish reason=publication_incomplete generation=4b9efcc198a7 schema=2 policy=1
[v2.volume_publish] status=failed
[v2.volume_publish] remote_status=error

direct result:
{"action":"publish","reason":"publication_incomplete","result":{"error":"generation_record_write_failed: ValueError('content_generation is required for a publication record')","status":"error"}}

direct result after fail-closed computation repair:
{"action":"publish","reason":"publication_incomplete","result":{"comfyapp_version":"2.16.31","error":"generation_computation_failed: comfyapp_version=2.16.31; reason=custom_node_source_generation raised ValueError","generation_failure_reason":"custom_node_source_generation raised ValueError","status":"error"}}

direct result with bounded exception detail:
{"action":"publish","reason":"publication_incomplete","result":{"comfyapp_version":"2.16.31","error":"generation_computation_failed: comfyapp_version=2.16.31; reason=custom_node_source_generation raised ValueError: symlink is not a publishable source root: /root/custom_nodes_vol","generation_failure_reason":"custom_node_source_generation raised ValueError: symlink is not a publishable source root: /root/custom_nodes_vol","status":"error"}}

command: python tools/publish_custom_nodes_volume.py
[v2.volume_publish] source_root=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes
[v2.volume_publish] nodes=24
[custom_nodes.publish] decision=publish reason=volume_refresh_failed generation=324427f5f4df schema=2 policy=1
[v2.volume_publish] status=failed
[v2.volume_publish] remote_status=ok

command: python tools/publish_custom_nodes_volume.py
[v2.volume_publish] source_root=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes
[v2.volume_publish] nodes=24
[custom_nodes.publish] decision=publish reason=volume_refresh_failed generation=19e428435834 schema=2 policy=1
[v2.volume_publish] status=failed
[v2.volume_publish] remote_status=ok

host diagnostic:
refresh_error=RuntimeError:reload() can only be called from within a running function
```

These attempts were retained as raw evidence and were not treated as success.

### Successful canonical smoke

```text
command: python tools/publish_custom_nodes_volume.py
[v2.volume_publish] source_root=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes
[v2.volume_publish] nodes=24
[custom_nodes.publish] decision=published reason=published_verified generation=f4c12e9b7573 schema=2 policy=1
[v2.volume_publish] status=ok
[v2.volume_publish] remote_status=ok
```

### Exact full remote result, committed readback, receipt, and exact skip

```json
{
  "desired_full_content_generation": "f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014",
  "manifest_digest": "f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014",
  "publisher_result": {
    "comfyapp_version": "2.16.31",
    "content_generation": "f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014",
    "generation_record_path": "/root/custom_nodes_vol/.comfymodal_control/custom_nodes_generation.json",
    "nodes": ["ComfyUI-CacheDiT", "ComfyUI-Flux2Klein-Enhancer", "ComfyUI-KJNodes", "ComfyUI-SeedVR2_VideoUpscaler", "ComfyUI_LayerStyle", "RES4LYF", "cg-use-everywhere", "comfyui-custom-scripts", "comfyui-detail-daemon", "comfyui-easy-use", "comfyui-impact-pack", "comfyui-levelpixel", "comfyui-lora-manager", "comfyui-manager", "comfyui-modal", "comfyui-workflow-encrypt", "comfyui_controlnet_aux", "comfyui_essentials", "comfyui_fill-nodes", "comfyui_image_metadata_extension", "comfyui_lg_samplingutils", "comfyui_sam3", "masquerade-nodes-comfyui", "rgthree-comfy"],
    "status": "ok"
  },
  "publisher_content_generation": "f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014",
  "volume_readback_content_generation": "f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014",
  "receipt_content_generation": "f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014",
  "receipt_manifest_digest": "f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014",
  "receipt_schema_version": 2,
  "generation_record_schema_version": 2,
  "generation_record_path": ".comfymodal_control/custom_nodes_generation.json",
  "file_count": 4273,
  "total_bytes": 496786363,
  "exact_skip_action": "skip",
  "exact_skip_reason": "exact_match",
  "exact_skip_publisher_called": false
}
```

### Final publisher status identity

```json
{
  "capture_guard": {
    "deployment_identity": "{\"app_name\":\"comfyui-custom-nodes-publisher\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"feca1b0663f36c47062f50d48029aacdd0d7e4fa5aebe4418fcb8b3a5e3e4e76\",\"deployment_combined_hash\":\"\",\"gpu\":\"rtx-pro-6000\"}",
    "state": "idle",
    "post_capture_guard_pending": false
  },
  "deployment_fingerprint_current": "feca1b0663f36c47062f50d48029aacdd0d7e4fa5aebe4418fcb8b3a5e3e4e76",
  "deployment_manifest": null,
  "deployed_state_app": "batch-ra2-active-patcher",
  "deployed_state_target_match": false,
  "profile": "golden_p1",
  "target": {
    "app": "comfyui-custom-nodes-publisher",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "ready": false,
  "remote_checks": "not_performed"
}
```

The generic Golden status command has no publisher-specific deployment manifest
and reports the unrelated local `batch-ra2-active-patcher` deployed state; it
is not used as publisher health proof. The authoritative publisher identity
evidence here is the canonical bootstrap version advance, current resolver
fingerprint, source behavior, and exact remote publication result/readback.

## Boundary confirmation

No changes were made to RA3, RA6, RA7, RA8, Golden stage timing, sampling,
model loading, durability, snapshot logic, or performance code. No RV2 Golden
request was resumed. No protected production Golden app was touched.

```text
S4B_COMPLETE=YES
ROOT_CAUSE_PROVEN=YES
ROOT_CAUSE=stale shared publisher used the narrow deployment/source hash; host readback also called container-only Volume.reload and the mount-root walker rejected Modal's expected root symlink
EXPECTED_FULL_GENERATION=f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014
PUBLISHER_FULL_GENERATION=f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014
VOLUME_READBACK_GENERATION=f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014
RECEIPT_GENERATION=f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014
ALL_FULL_GENERATIONS_MATCH=YES
NARROW_IDENTITY_CAN_CERTIFY_CONTENT=NO
READBACK_PROVEN=YES
S4_REMOTE_SMOKE_COMPLETE=YES
PRODUCTION_GOLDEN_APP_TOUCHED=NO
READY_TO_RESUME_RV2=YES
REPORT=S4B_REMOTE_PUBLICATION_GENERATION_RECONCILIATION_REPORT.md
```
