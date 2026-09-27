# S2 Golden Deploy Hardening Report

## Pipeline

**Before:** `golden deploy` selected `deploy_and_run_v2_single.bat`, passed a
Golden selector, and inherited the combined BAT's deploy/benchmark control
surface. Custom-node publication independently rebuilt an archive and invoked
the compatibility `sync_custom_nodes_to_volume` function.

**Now:** `golden deploy` resolves the same profile/target, acquires the deploy
lock, proves the app version before and after deployment, and invokes the
native command `modal deploy -m comfymodal_runtime.modal_app --name <app>`.
It records the existing deployment manifest/provenance and preserves the
Golden class/method identity. Dry-run resolves and prints this command without
Modal import, Volume access, network, or subprocess execution.

Custom-node publication has one S2 semantic file set. That set drives the
archive, file count, byte total, manifest digest, and source identity. The
existing remote sync function remains the compatibility publisher; an exact
trusted receipt skips it before archive construction. Actual Modal Volume reads
use the async ``read_file`` interface. Receipts are verified, volume-scoped,
ownership marked, integrity-protected, and written only after successful
publication, generation readback, and receipt readback. The fallback generation
now matches the existing remote schema-2 per-node SHA256 plus md5 JSON identity.

## Removed from Golden deploy

- legacy BAT dispatch and `COMFYMODAL_DEPLOY_ONLY` routing;
- `benchmark_v2_direct`, warmup extraction, V1 app discovery, registry
  priming, run-artifact discovery, and inference from deploy-only control;
- duplicate source walks and competing publication/hash implementations in
  the S2 publisher.

## Baseline and proof

- Read-only baseline dry-run: approximately **834 ms**.
- Actual deploy timestamp: **not available in this lane**.
- Identity excludes receipt/control metadata and avoids timestamps/random IDs.
- Ownership requires the S2 publisher and ownership marker; malformed,
  unsupported, wrong-volume, incomplete, mismatched, or unverifiable receipts
  fail closed.
- Receipt finalization is after content success and generation readback only;
  receipt write/readback failure leaves the next invocation publishable.
- S1 canonical identity API: no callable provider was available to this lane.
  The compatibility md5 fallback is therefore the current remote-compatible
  adapter fallback, not a claim that S1 integration is complete.  The S1
  identity-provider seam remains intact and is consumed when a callable
  provider is supplied; no second image owner was added.

## A–E validation

- **A — local receipt/identity/archive tests:** PASS (`191 passed, 2 skipped`)
  across the focused S2/CLI/backend/fingerprint suite. This includes async
  Volume reads and batch uploads, fail-closed tree/receipt handling,
  no-archive exact skip, native Golden publication ordering/failure gating,
  uncertain app-version lookup, and remote-generation compatibility.
- **B — native dry-run/routing tests:** PASS (Golden namespace/backend tests;
  native command shown and no invocation performed).
- **C — focused regression suite:** PASS (`205 passed, 2 skipped`) across the
  combined S2, S1 publisher-bootstrap, CLI, backend, and fingerprint suites.
- **D — real remote deploy/publication:** PASS. On 2026-08-30, the isolated
  app `batch-s2-golden-ops-20260829` used the active workspace and the
  publication gate returned `skip_exact` for generation `6fccd8ee77fe` with no
  archive or publisher invocation. Native Modal deployment completed with exit
  code `0`; deployment manifest and target/profile fingerprints match.
- **E — real Golden run/evidence:** PASS for the isolated validation. The
  explicit Golden request and the later gate-selected serial request were both
  eligible, structurally valid, true-cold, durable, and reopen-verified. No
  confirmation campaign was run.

## Remaining legitimate work

The S1 publisher-bootstrap operation is complete. Preserve the exact deployment
identity before collecting any further observations. The configured output SHA
still differs from the observed content SHA under the warning-only contract;
this remains visible and must not be silently promoted.

FINAL_STATUS_LOCAL_IMPLEMENTATION=COMPLETE_REMOTE_VALIDATION=COMPLETE_ISOLATED
FINAL_STATUS_REAL_DEPLOYMENT=COMPLETE_ISOLATED
FINAL_STATUS_PARENT_VALIDATION=COMPLETE

## Publication API follow-up

The S2 failure was caused by using Modal 1.4.3's synchronous live-method
wrappers from the async publication coroutine. `Client.from_credentials` and
`Volume.from_name` are synchronous constructors, while `Volume.read_file` and
`Volume.batch_upload` expose native async interfaces through `.aio`. The old
path constructed the Volume on the event-loop thread and called the blocking
read/upload wrappers, producing `AsyncUsageWarning`; generation readback could
therefore not establish the proof required to finalize a receipt and the
deploy correctly failed closed as `publication_incomplete`.

The S2 path now constructs a Volume in `asyncio.to_thread`, uses
`read_file.aio` and `batch_upload.aio` when available, and retains only a
narrow fallback for local sync/async fakes. Golden callers pass the active
workspace directly, so credentials remain explicit. No receipt is finalized
without generation and receipt readback verification, and exact skips still
avoid archive construction and publisher invocation.

Focused combined validation: **205 passed, 2 skipped** across the S2, S1
publisher-bootstrap, CLI, backend, and fingerprint suites. Python compilation
and `git diff --check` passed. Regression coverage models the Modal 1.4.3
sync-callable/`.aio` method shape and verifies that the sync Volume factory runs
outside the async event loop.

## Final operational evidence

- App: `batch-s2-golden-ops-20260829` (isolated; production untouched).
- Deployment manifest:
  `.v2ctl/deployments/deploy_20260830-102100_397ed6a6.json`
- Deployment fingerprint:
  `397ed6a6acb628d57388a58dfefdc01221aa89cca264ea48bf2a9a8855febefd`
- Source probe: `PASS / MATCH`; class `ModalRuntimeEntrypointV2`; method
  `run_golden_serial_stream`; GPU `rtx-pro-6000`.
- Final status: `ready=True`; runtime health and source identity verified;
  target/fingerprint match; runtime overrides `0`; deploy lock inactive;
  doctor `OK`.
- Publication: exact receipt skip, generation `6fccd8ee77fe`; no archive or
  publisher call on the successful deploy.
- Explicit run manifest:
  `.v2ctl/runs/run_20260830-102319_f24950d1.json`; request
  `golden-p1-0-815193e3b046`; campaign
  `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_15-22-14_60296f/`.
- Gate artifact:
  `.v2ctl/gates/gate_20260830-152506_f24950d1.json`; it selected a later
  serial request `golden-p1-0-cdd46b12a253` from cohort
  `cohort_2026-08-30_15-24-45_a7c4d5/` and returned `valid=1`.
- Both retained requests had `valid=true`, `true_cold=true`,
  `restore_count=1`, `request_count=1`, no snapshot capture, zero seriality
  violations, `true_durable=true`, and `reopen_verified=true`.
- Configured output SHA:
  `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`.
  Observed output SHA:
  `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce`.
  This is an explicit warning-only mismatch under the S1 contract; the
  observed content SHA remains authoritative.
