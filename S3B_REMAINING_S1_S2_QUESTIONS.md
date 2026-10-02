# S3B Remaining S1/S2 Questions

Date: 2026-08-30  
Branch: `TESTING2`  
Scope: current post-remediation tree and isolated app
`s3-cache-proof-20260830` only. The protected Golden production app was not
touched.

## Answers

| Question | Answer | Basis and limitation |
|---|---|---|
| Did the shared-publisher path eliminate the old pre-deploy bottleneck? | **UNPROVEN** (architecture: **PASS**) | Golden now uses the shared publisher app and canonical S1 source identity (`tools/v2_control/cli.py:1653-1700`; `comfymodal_runtime/publication_policy.py:100-103`). The post-remediation deploy used an exact publication skip. Timing improved in the observed attempt, but the before/after states were not equivalent and no publisher counters prove causality. |
| Are S1's expensive dependency/image layers reused across ordinary source edits? | **UNPROVEN** | The canonical DAG places dependency work before source (`comfyapp.py:8264-8478`, especially `8319-8345`, `8427-8451`, `8836-8858`), and local diagnostics reported `decision=expected_hit`. Those facts do not prove remote layer reuse. Modal's documented per-method-call caching semantics support the design, but the installed client exposed no per-layer cache decision. |
| Does the current Golden production path have another heavyweight image/dependency owner? | **PASS — none found** | Golden materializes `CANONICAL_IMAGE_PLAN.final_image` (`comfyapp.py:8778-8862`). The heavyweight dependency/image construction is centralized in `comfyapp.py:8264-8478`. `publisher_image` and `download_image` are lightweight auxiliary images (`comfyapp.py:8864-8879`). E16 is explicitly benchmark-only/non-canonical (`e16_source_io_modal.py:1-5,39-50`) and has dedicated wrappers; it is not a Golden production caller. |

## Before/after deployment timing

These measurements are reported for context, not as a controlled causal
benchmark.

| Measurement | Before: S3 audit | After: S3B isolated app |
|---|---:|---:|
| Pre-native interval | **130,837.599 ms** | Not independently separated by the native-deploy manifest |
| Modal/native deploy wall | **59,828.000 ms** | **52,125 ms** backend manifest elapsed |
| Total v2ctl deploy wall | **193,265.802 ms** | **62,646.760 ms** wrapper wall |
| Publication state | `published`, 4,273 files, 497,509,642 bytes | `skip`, `exact_match`, 4,273 files, 497,525,285 bytes |

The S3 pre-native interval combined configuration/fingerprint, lock,
publication, and lookup work. The S3B wrapper wall includes publication and
control-plane overhead, while the manifest's 52.125 seconds is the native
backend interval. The S3B publisher-bootstrap probe separately took
57,199.732 ms but returned “Deployment skipped: no changes detected”; v2ctl
correctly rejected that as a version-advancement proof. The subsequent Golden
deploy reused the existing shared publisher and succeeded.

## Cache evidence boundary

The S3B deployment produced image ID `im-Wu5vjtZSbXJxTsZqXb79ut` and a source
probe `PASS / MATCH`. Its persisted deploy log contains only the v2ctl summary;
it contains no `CACHED`, cache-hit, cache-miss, or layer-reuse marker.

The documented stronger path was attempted:

```text
modal image logs im-Wu5vjtZSbXJxTsZqXb79ut --all
```

The installed Modal client is `1.4.3`; this CLI has no `modal image` command.
The installed Python SDK exposes `modal.enable_output`, `Image.from_id`, and
`Image.build`, but no `Image.logs` attribute. Therefore no stronger
per-layer evidence was available from this environment. Timing, image IDs,
successful deploys, and local `expected_hit` diagnostics are insufficient to
claim reuse across an ordinary source edit. No forced rebuild or synthetic
source edit was performed merely to manufacture a weaker comparison.

## Exact changes made

No source changes were made during S3B. The current tree already contained the
post-remediation changes audited here:

- `tools/v2_control/cli.py`: lazy S1 provider wired into Golden publication;
- `e16_source_io_modal.py`: benchmark-only/non-canonical declaration and
  corrected benchmark error wording.

S3B added this report and retained the isolated validation artifacts below.

## Raw evidence

- `S3_S1_S2_DEPLOY_TIMING_AND_AUDIT_REPORT.md` — original S3 findings and
  post-remediation record.
- `artifacts/s3_s1_s2_timing_20260830_timing.log` — original S3 timing.
- `artifacts/s3_s1_s2_timing_20260830_stdout.log` — original S3 deploy output.
- `artifacts/s3_s1_s2_publisher_bootstrap_20260830.log` — original bootstrap.
- `artifacts/s3_cache_proof_20260830_attempt2_timing.log` — S3B bootstrap and
  deploy timing.
- `artifacts/s3_cache_proof_20260830_attempt2_publisher_bootstrap.log` —
  no-change publisher bootstrap and version-advancement rejection.
- `artifacts/s3_cache_proof_20260830_attempt2_deploy.log` — successful native
  Golden deploy summary and exact publication skip.
- `.v2ctl/deployments/deploy_20260830-132246_b39d53e0.json` — authoritative
  S3B deployment manifest, image-independent deployment identity, publication
  decision, and 52.125-second backend timing.
- `artifacts/s3_cache_proof_20260830_attempt2_source_probe.log` — remote image
  ID and source identity match.
- `artifacts/s3_cache_proof_20260830_attempt2_status_after.log` — matching
  deployment/source identity; runtime health unverified because no request ran.
- `artifacts/s3_cache_proof_20260830_attempt2_doctor_after.log` — doctor `OK`.
- `artifacts/s3b_image_logs_im-Wu5vjtZSbXJxTsZqXb79ut.log` — unsupported
  installed-CLI `modal image logs` attempt.
- `artifacts/s3b_modal_version_20260830.log` — installed Modal version.
- `artifacts/s3b_modal_help_20260830.log` and
  `artifacts/s3b_modal_app_help_20260830.log` — installed CLI capabilities.

## Verdict fields

```text
S3B_REPORT_COMPLETE=YES
S3B_SHARED_PUBLISHER_ARCHITECTURE=PASS
S3B_PREDEPLOY_BOTTLENECK_ELIMINATED=UNPROVEN
S3B_EXPENSIVE_LAYER_REUSE=UNPROVEN
S3B_GOLDEN_COMPETING_HEAVY_OWNER=PASS_NONE_FOUND
S3B_SOURCE_MODIFIED=NO
S3B_PRODUCTION_TOUCHED=NO
```
