# V2 Waterfall Final Correctness Report

## Verdict

**COMPLETE — final acceptance: PASS.**

The corrected V2 waterfall passed the final production-workflow live run with exclusive top-level accounting, real timing provenance, a single readable ASCII table, an authoritative conditioning-cache exact hit, and a reconciliation error within the 10 ms target.

Final evidence:

- Deployment: `v2_waterfall_deploy_5.log`
- Deployment hash: `3820ca42d45376e1`
- Custom-nodes generation: `2f1f3d2891088a3b`
- ComfyUI core parity: `f49bdb655707b979` on host and deployment (`comfyui_core_match=1`)
- Validation/setup request: `v2-benchmark-0-ad9f4d0c7b80`
- Final acceptance request: `v2-benchmark-0-168633131460`
- Final console log: `v2_waterfall_run_8_final_acceptance.log`
- Final structured artifact: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-13_08-57-39\run_001_sample.json`

## Final acceptance metrics

| Metric | Final value | Gate |
|---|---:|---|
| Command to response | 84,299.810 ms | Informational envelope |
| Modal scheduling | 47,323.499 ms | Informational and excluded |
| TOTAL WALL | 36,976.311 ms | `command_to_response - scheduling` |
| Accounted top-level stages | 36,978.543 ms | Exclusive numbered stages only |
| Reconciliation | -2.231 ms | PASS: absolute value <=10 ms target and <=50 ms hard ceiling |
| Validation status | `COMPLETE` | PASS |
| Reconciliation status | `OK` | PASS |
| Conditioning cache | `exact_hit`, zero encode calls | PASS |
| Checkpoint active read | 1,042.471 ms | Real measured read |
| Synchronized H2D | 2,246.457 ms at 5.5 GB/s | Separate from checkpoint read |
| Remote result handoff | 601.128 ms | Direct remote emit to local receipt |
| Local result handling | 16.000 ms | Direct local receipt to caller return |
| Output | PNG, 1088x1920, 2,874,640 bytes | PASS |
| Output SHA-256 | `895deda228cc96c7bcb7de2f6b262dbb2cb62615b707cfb8fc7d2ec0093c14e7` | Matches validation/setup output |

## Exact final live waterfall

```text
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-168633131460  Instance: 387759f9d0024597a2ac96b5e59947e3  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east4
TOTAL WALL:           36.976s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:    84.300s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 423.973 ms | 423.973 ms |   1.147% | #                                        |
|   2 | Modal handle and submission                    |    16.280s |    16.704s |  44.027% | ##################                       |
|   3 | Modal pre-Python snapshot restoration          |     7.404s |    24.108s |  20.024% | ########                                 |
|   4 | Python/application restore                     |     1.356s |    25.464s |   3.668% | #                                        |
|   5 | Restore-to-method entry                        |  13.094 ms |    25.477s |   0.035% | #                                        |
|   6 | Remote method setup                            |  65.512 ms |    25.543s |   0.177% | #                                        |
|     |   graph setup                                  |  44.482 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |     1.246s |    26.789s |   3.370% | #                                        |
|     |   execution to cached                          |     1.106s |            |          |                                          |
|     |   cached to first node                         | 139.351 ms |            |          |                                          |
|   8 | Pre-sampler execution                          |     2.382s |    29.171s |   6.442% | ###                                      |
|     |   Conditioning cache exact_hit lookup=377.7... | 377.710 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           |  62.926 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  25.024 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 161.205 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.042s |            |          |                                          |
|     |   Read end -> construction done                |   0.509 ms |            |          |                                          |
|     |   UNET get_model                               | 235.651 ms |            |          |                                          |
|     |   Bind                                         |  65.408 ms |            |          |                                          |
|     |   Synchronized H2D (5.5 GB/s)                  |     2.246s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.742 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 135.823 ms |    29.307s |   0.367% | #                                        |
|     |   lane acquired to actual stage                | 135.798 ms |            |          |                                          |
|  10 | Sampling                                       |     4.949s |    34.256s |  13.385% | #####                                    |
|  11 | Post-sampling / VAE transition                 |     1.015s |    35.271s |   2.745% | #                                        |
|  12 | VAE decode                                     | 420.577 ms |    35.692s |   1.137% | #                                        |
|     |   VAE load/H2D                                 |     1.045s |            |          |                                          |
|  13 | Output encode / descriptor                     | 669.550 ms |    36.361s |   1.811% | #                                        |
|     |   PNG encode                                   | 596.998 ms |            |          |                                          |
|  14 | Remote result handoff                          | 601.128 ms |    36.963s |   1.626% | #                                        |
|  15 | Local result handling / caller return          |  16.000 ms |    36.979s |   0.043% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |    47.323s |            |          |                                          |
|     | RECONCILIATION                                 |  -2.231 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
```

## Correctness gates

### Accounting and rendering

- `TOTAL WALL = COMMAND->RESPONSE - Modal scheduling` exactly in the artifact.
- Scheduling has `accounting_role=informational`, is not numbered, and has no cumulative value, percentage, or bar.
- Only `top_level` stages contribute to `accounted_ms`; detail and overlap-detail rows remain non-accounting diagnostics.
- No fabricated residual stage is present.
- The console contains one host-reconciled boxed ASCII table.
- Unavailable and useless sub-millisecond details are omitted from the console while remaining available in the structured artifact.
- No `Expanded diagnostics`, `Advanced`, `GLOBAL RESIDUAL`, `RESIDUAL %`, `INVALID`, or `PENDING_HOST_RECONCILIATION` output is present.
- User-visible transition labels use portable ASCII `->`; the renderer and golden test contain no U+2192 or U+001A characters.

### Timing provenance

- The checkpoint row is backed by the matched active-read wall interval: 1,042.471 ms for the UNET read.
- H2D is independently measured as 2,246.457 ms at 5.5 GB/s; it is not used as a checkpoint-read fallback.
- Active-read association uses restored-instance, restore-session, request when available, and UNET owner/path identity.
- Remote result handoff is measured from `remote_result_emit` to `local_result_received`.
- Local result handling is measured from `local_result_received` to `caller_return`.
- The host replaces the remote partial report with the final reconciled report.
- Final artifact flags are clean: `partial_flags=[]`, `boundary_flags=[]`, `data_flags=[]`, and `warnings=[]`.

### Cache, Step-3, and parity

- The authoritative cache decision is `exact_hit` with `identity_status=valid`, `entry_count=1`, and `encode_calls=0`.
- A later no-op `miss_not_stored` event does not override the real hit in the console.
- Step-3 was consumed: `certificate_read_outcome.cert_decision=plan_validation_fast_path`, `consumed=true`, `hit=true`, and `preflight_skip=true`.
- Deployment hash, custom-node generation, dependency proof, and workflow registry all match.
- Registry parity is 31 host-proved / 31 snapshot-proved / 31 workflow classes, with zero missing or identity-mismatched classes.
- `registry_fingerprint_match=false` is diagnostic only; the authoritative workflow registry and dependency proof gates pass.
- Validation request 7 and exact-hit request 8 produced the same PNG SHA-256, dimensions, and byte count.

### Preserved behavior and deployment shape

- CPU model snapshot, native fast-disk UNET, VAE snapshot, exact CLIP conditioning cache, late UNET activation, sampling-end VAE activation, persistent local handle, UNET snapshot exclusion, and CLIP/VAE retention remained enabled as required.
- The deployment remained on the requested restore-only shadow application and RTX PRO 6000 target.
- Cloud and region were not pinned; Modal selected GCP `us-east4` for the final run.
- The accepted workflow retained its CacheDiT/SageAttention/sampling/PNG/output behavior; no run-health classifier was added.

### Persistence lifecycle

- The benchmark completed without `Task was destroyed` or pending V2 persistence-drain errors.
- Direct output sink completion was successful; deferred commit was skipped by design for that output path.
- The trailing ComfyUI-Manager registry-fetch shutdown warning is unrelated to the V2 persistence-drain registry and occurred after successful benchmark completion.

## Verification record

- Final-state focused merged suite: **304 passed**.
- Final renderer contract suite: **36 passed**.
- Python compilation: passed for all changed runtime modules.
- `git diff --check`: passed; only existing line-ending notices were emitted.
- Renderer/golden codepoint scan: zero U+2192 and zero U+001A.
- Independent final evidence review: **GO**.

## Run accounting

- Successful deployments used for this correction cycle: **5**.
- Successful generation requests: **8**.
- One earlier malformed shell wrapper did not locate `run_v2_single.bat`, submitted no request, and is not counted.
- Deployment 5 and requests 7-8 are the authoritative final-source evidence. Earlier runs remain useful only as defect-discovery history.

## Non-blocking notes

- `plan_proof_decision.reason=not_eligible` remains a cosmetic default-field inconsistency while its authoritative fields say `decision=plan_validation_fast_path` and `consumed=true`. The independent certificate event confirms the fast path was consumed.
- The older `timing.local_timing.reconciliation_status=incomplete` belongs to a separate local-dispatch diagnostic namespace with an unavailable direct-benchmark queue boundary. It is not the final waterfall gate; `final_reconciled_waterfall` is `COMPLETE` and `OK`.
- Local ComfyUI startup emits unrelated missing optional custom-node dependency warnings. The executed 43-node workflow, parity proof, output, and final waterfall all completed successfully.
