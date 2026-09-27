# S3 S1/S2 Deploy Timing and Audit

Date: 2026-08-30  
Branch: `TESTING2`  
S3 app: `s3-s1-s2-timing-20260830` (isolated; production app untouched)

This is an independent audit. S1/S2 reports were treated as claims, not as
proof. During the audit phase, no source, dependency, skill, configuration,
test, Volume, or existing manifest was edited. The S3 deployment necessarily
created its own generated deployment manifest and raw logs. A later, separately
recorded remediation phase changed only the files listed below.

## Timing

The first S3 attempt stopped safely before native deployment because the
isolated publisher app did not exist. The supported publisher bootstrap then
completed successfully. The timed deploy below is the successful second
attempt. No identical redeploy was run.

| Phase | Wall |
|---|---:|
| Invocation -> actual native Modal deploy start | **130,837.599 ms** |
| Actual `modal deploy` | **59,828.000 ms** |
| Post-deploy (native return -> v2ctl exit) | **2,600.203 ms** |
| **Total v2ctl deploy wall** | **193,265.802 ms** |

Details:

- Invocation UTC: `2026-08-30T16:05:59.8191340Z`.
- Native process observed UTC: `2026-08-30T16:08:10.6546275Z`; process polling
  granularity was approximately 100 ms.
- v2ctl backend manifest boundary: `16:08:10Z` -> `16:09:10Z`,
  `elapsed_seconds=59.82799999997951`, exit `0`.
- v2ctl exit UTC: `2026-08-30T16:09:13.0849411Z`, authoritative stdout and
  manifest exit `0`. The PowerShell wrapper's separate exit-code field was
  blank, so it is not used as evidence.
- Easy pre-deploy breakdown: configuration/fingerprint, deploy lock,
  publisher decision/publication, and pre-version lookup are combined in the
  130,837.599 ms interval. S3 publication was `published`, generation
  `f1a6ebea8f5fff232e7ef9dd6980ce98`, 4,273 files, 497,509,642 bytes.
- The pre-deploy publisher operation is not counted as Modal V2 deploy start.

Raw evidence:

- `artifacts/s3_s1_s2_timing_20260830_timing.log`
- `artifacts/s3_s1_s2_timing_20260830_stdout.log`
- `artifacts/s3_s1_s2_timing_20260830_stderr.log`
- `.v2ctl/deployments/deploy_20260830-110910_f56ccb98.json`
- `artifacts/s3_s1_s2_publisher_bootstrap_20260830.log`
- `artifacts/s3_s1_s2_doctor_20260830.log`
- `artifacts/s3_s1_s2_source_probe_20260830.log`

Post-deploy source probe was `PASS / MATCH`; doctor was `OK`; status showed
matching deployment identity and source identity, but runtime health remained
`unverified` because no Golden inference request was made. The S3 deploy used
the dirty tree captured in its manifest (`git head b578f77c`, `dirty=true`).

## Audit matrix

| Area | Check | Result | Evidence / problem |
|---|---|---|---|
| S1 | Canonical Golden image-plan owner exists | PASS | `comfyapp.py:8778-8862` defines and materializes `CANONICAL_IMAGE_PLAN`. |
| S1 | One image/dependency owner with no duplicate heavyweight path | **FAIL** | Auxiliary image owners are present (`comfyapp.py:8864-8877`, many function images); `e16_source_io_modal.py:34-39` independently adds `fastsafetensors` with `.pip_install`. This is not one canonical heavyweight build path. |
| S1 | Canonical dependency install layer is stable-before-source | PASS | Foundation/dependency/accelerator/source ordering at `comfyapp.py:8319-8345`, `8427-8478`, `8839-8858`. |
| S1 | No normal runtime pip installation | PARTIAL | Golden production modes fail/validate rather than install, but runtime repair remains callable in `dev` (`comfyapp.py:14850-14917`) and startup/restore call the helper (`:18377`, `:21101`). |
| S1 | No hidden second installer in `modal_app.py` | PASS | No direct pip installer there; the runtime helper call at `comfymodal_runtime/modal_app.py:9326` is not a second installer implementation. |
| S1 | Stable dependencies avoid ordinary source ancestry | PASS | Canonical source is added after dependency boundaries (`comfyapp.py:8324-8325`, `8836-8858`). |
| S1 | Custom-node source/dependency identities are separate | PASS | Typed boundary fields and inputs are separate in `fingerprints.py:161-225` and `deployment_spec.py:164-181,449-473`. |
| S1 | Accelerator changes avoid unrelated custom-node dependency invalidation | PASS (code) | Accelerator layer is a later distinct boundary (`comfyapp.py:8427-8451`); no real cache proof was available. |
| S1 | Package/source inclusion is canonical and deterministic | PARTIAL | Shared `publication_policy` is used, but archive identity includes all semantic files while fallback generation hashes only `.py/.js/.mjs/.txt/.toml/.cfg` (`custom_nodes.py:331-405`, `publication_policy.py:82-89`). |
| S1 | Dependency identity changes only for dependency-relevant changes | PASS (code) | `FingerprintEngine.deploy_inputs()` limits registered flags to build/deploy and separates dirty source hashes (`fingerprints.py:68-105`). |
| S1 | Source identity changes for source changes | PASS (code) | Runtime/custom-node source hashes feed `deployment_spec.py:588-618`. |
| S1 | Deployment identity combines deploy-relevant identities | PASS (code) | `deployment_spec.py:449-458`; request identity is separately derived at `:459-473`. |
| S1 | Request-only changes do not masquerade as deploy/dependency changes | PASS (code) | Workload/run flags are in request inputs, not `deploy_inputs` (`fingerprints.py:107-129,210-224`). |
| S1 | Real Modal cache proof for source/dependency edits | **UNPROVEN** | S1 report/unit tests provide no complete raw image DAG cache-hit/miss evidence. Existing tests are static/unit contracts; deployment manifests provide timing/identity, not layer reuse proof. |
| S1 | S1 report deployment evidence | PARTIAL | Final f27 manifest exists, but the checked-in raw evidence is spread across multiple earlier fingerprints/attempts; no single raw S1 log independently reconstructs the claimed cache validation. |
| S2 | Golden deploy uses native Modal deploy | PASS | `backend.py:294-306`; `cli.py:1886-1915`; S3 raw stdout and manifest show `modal deploy -m comfymodal_runtime.modal_app`. |
| S2 | Golden path avoids BAT/`COMFYMODAL_DEPLOY_ONLY` compatibility routing | PASS | Legacy specs remain for non-Golden paths (`backend.py:272-292`), but Golden selects `native_deploy()` and passes only `--name` (`cli.py:1906-1912`). |
| S2 | No benchmark preflight/warmup/registry prime/run-artifact discovery/inference in deploy | PASS | Native Golden deploy has no selector or run backend; `cli.py:1886-1915`. |
| S2 | Exact skip requires complete trusted receipt | PASS | Receipt schema, protocol, policy, state, volume, publisher/ownership marker, integrity digest, generation, count, bytes, and manifest equality are required (`custom_nodes.py:513-546`). |
| S2 | Receipt/control files excluded from content identity | PASS | Explicit control exclusion (`custom_nodes.py:233-240,310-317`; `publication_policy.py:39-54`). |
| S2 | Archive and desired identity use one semantic file set | PASS | One collection feeds manifest, identity, and archive (`custom_nodes.py:613-636`). |
| S2 | Source-generation identity uses that entire same set | PARTIAL | Fallback generation intentionally filters to generation extensions (`custom_nodes.py:368-398`); the full-set manifest digest still protects exact skip from ordinary included-file drift. |
| S2 | Malformed/missing/stale/failed publication cannot skip | PASS | Fail-closed receipt parsing/evaluation and no receipt before verified publication (`custom_nodes.py:151-206,520-546,640-659`). |
| S2 | Publication ordering | PASS | Remote content extraction writes generation before one Volume commit (`comfyapp.py:9169-9201`); host reads generation, writes receipt, then reads/verifies receipt (`custom_nodes.py:642-659`). |
| S2 | Exact match precedes archive/gzip/upload/publisher commit | PASS (code/tests) | Receipt is read/evaluated before `build_archive`/publisher (`custom_nodes.py:611-646`); 223 focused tests passed, including no-archive/no-publisher fakes. |
| S2 | Real exact-match zero counters | PARTIAL | S2 manifest records `action=skip`, `reason=exact_match`, generation `6fccd8...` (`deploy_20260830-102100_397ed6a6.json:23-31`), but no raw counter log proves archive builds/uploads/publisher calls were each zero. |
| S2 | Modal async API fix | PASS | Volume construction is moved off-loop and real `.aio` methods are selected (`custom_nodes.py:453-461,576-597,617-625`); local sync fallback is narrow and injected/fake-only. |
| S2 | S1 canonical identity integration | **PARTIAL / UNFINISHED** | The provider seam exists (`custom_nodes.py:331-363`), but Golden CLI does not pass an S1 provider (`cli.py:1685-1690`); the live path therefore uses the compatibility MD5 fallback (`custom_nodes.py:364-398`). Do not add a second identity implementation. |
| Golden | Authorized warning-only SHA mismatch | PASS | `golden_serial.py:4917-4943` records expected/observed warning telemetry and continues. Acceptance tests require explicit warning evidence (`test_benchmark_v2_golden_acceptance.py:175-211`). |
| Golden | Configured SHA used consistently | PASS | Live profile, Golden constant, benchmark, and wiring tests use authorized configured SHA `8a9244...` (`golden_p1.toml:18`, `golden_serial.py:71`, `test_golden_p1_wiring.py:103-117`). |
| Golden | No active stale hard-fail on configured mismatch | PASS with latent finding | Golden durability calls `enforce_expected_sha=False` (`golden_serial.py:5094-5107,5153-5156`); lower-level helper defaults `True` at `:5041-5046`, an API hazard but not the active Golden caller. |
| Golden | Output integrity and durability remain separate | PASS | Observed SHA names/writes the asset and descriptor; commit, reopen, byte count, and observed-content hash remain fail-closed (`golden_serial.py:4944-5022,5069-5089`). |
| Golden | Final observed SHA evidence | PARTIAL | S1 raw artifact reports configured `8a9244...` and observed `bfb360...`; warning-only behavior is coherent, but canonical exactness is not established. No S3 inference was run and no SHA was changed or promoted. |
| Golden | Unauthorized/unrelated SHA change | PASS | The configured SHA change was explicitly authorized by the user. Current live-path references are consistent; old `454dbd...` references found were historical `.slim/worktrees`, not current source. |

## Unsupported, unfinished, dangerous, and unnecessary complexity

- **Unsupported S1 claim:** real deployment-cache validation is not established
  by the available raw evidence. Unit/static tests cannot prove Modal image DAG
  reuse.
- **Unsupported S2 subclaim:** the exact-match manifest proves the skip decision,
  but not independently logged zero archive/upload/publisher counters.
- **Unfinished integration:** S2 still defaults to the compatibility MD5
  generation path because S1's callable provider is not wired into the Golden
  publisher call.
- **Dangerous:** `e16_source_io_modal.py` can create a separate heavyweight
  dependency descendant; runtime `dev` repair remains an install-capable path.
- **Correct but complicated:** legacy BAT/deploy-only backends remain registered
  for non-Golden profiles while Golden has a native path. This is safe for the
  audited route but leaves a larger control surface than necessary.
- **S3 operational limitation:** status/source probe established identity, but
  runtime health was intentionally not promoted because no request was run.

Smallest later corrective actions: wire the existing S1 provider into the S2
Golden publisher call; either retire/isolate the E16 heavyweight image installer
or explicitly document it as non-canonical; and run a separately controlled
Modal cache experiment with raw layer reuse evidence. Do not change the SHA in
this audit.

## Post-audit remediation

- `tools/v2_control/cli.py` now passes a lazy S1 provider into Golden
  publication. The provider uses the pure
  `build_deployment_identity(...).custom_node_hash` source identity; the
  combined deployment hash is not used as the publication generation.
- `e16_source_io_modal.py` now explicitly identifies E16 as benchmark-only and
  non-canonical, and its construction error no longer says “production”. Its
  benchmark behavior and pinned dependency were not changed.
- Focused validation after remediation: `146 passed, 2 skipped`; changed Python
  files compiled successfully.
- Isolated post-remediation app `s3-cache-proof-20260830` deployed successfully
  using the existing shared publisher. Source probe was `PASS / MATCH` and
  doctor was `OK`; status remained `ready=False` only because no runtime
  request was made.
- Publisher bootstrap was attempted but correctly rejected the existing app's
  “Deployment skipped: no changes detected” result because its version did not
  advance. The subsequent Golden deploy succeeded.
- The post-remediation cache attempt is **INCONCLUSIVE**. The native Golden
  command's persisted output contained no authoritative `CACHED`, cache-hit,
  cache-miss, or layer-reuse marker, so timing, image IDs, and deployment
  success are not treated as cache proof. Raw artifacts are retained under
  `artifacts/s3_cache_proof_20260830_*` and
  `artifacts/s3_cache_proof_20260830_attempt2_*`.

## Verdict

`S1_VERDICT=FAIL`  
`S2_VERDICT=PASS_WITH_FINDINGS`  
`GOLDEN_CONTRACT_VERDICT=PASS_WITH_FINDINGS`

S3_AUDIT_COMPLETE=YES  
ORACLE_USED=NO  
AUDIT_PHASE_SOURCE_MODIFIED=NO  
AUDIT_PHASE_PRODUCTION_TOUCHED=NO  
POST_AUDIT_REMEDIATION_SOURCE_MODIFIED=YES  
POST_AUDIT_REMEDIATION_PRODUCTION_TOUCHED=NO  
INVOCATION_TO_DEPLOY_START_MS=130837.599  
MODAL_DEPLOY_WALL_MS=59828.000  
TOTAL_V2CTL_DEPLOY_WALL_MS=193265.802  
S1_VERDICT=FAIL  
S2_VERDICT=PASS_WITH_FINDINGS  
GOLDEN_CONTRACT_VERDICT=PASS_WITH_FINDINGS  
REPORT=S3_S1_S2_DEPLOY_TIMING_AND_AUDIT_REPORT.md
