# RA7 durable commit variance and decomposition report

## Scope and local evidence

RA7 is a source-and-test change only.  No Modal deployment, remote request, or
Modal benchmark was run.

`golden_durable_commit` now records one authoritative stage and the following
non-overlapping host monotonic-nanosecond decomposition:

1. `pre_commit_bookkeeping`
2. `volume_commit_call_wall`
3. `commit_return_to_reopen_start`
4. `reopen_open`
5. `stat`
6. `readback`
7. `readback_sha256`
8. `byte_count_content_verification`
9. `close_finalize`

The return boundary from the one blocking `Volume.commit` API is also the start
of `commit_return_to_reopen_start`.  All marks use the recorder-injectable
monotonic clock.  The raw `DURABLE_COMMIT_SUBSPANS` event receives a copied
snapshot, so later telemetry cannot add or rewrite its fields.

`true_durable_result_marker_publication` is deliberately **not** a commit-stage
subspan.  `mark_true_durable()` executes after the commit stage has ended and
publishes a separate `DURABLE_RESULT_MARKER_PUBLICATION` raw event with
`outside_durable_commit_stage=true` and the explicit
`post_commit_result_marker` boundary.  This preserves the true-durable order
without attributing result-marker work to the commit stage.

Modal exposes `Volume.commit` as one blocking API to this process.  There is no
lower-level server-side commit timing available locally, so no internal Modal
service phase is inferred.

## Variance attribution: proven versus unproven

The reported approximately **0.95–2.27 s** spread cannot be attributed from two
runs.  The decomposition makes future attribution possible, but source alone
does not supply a population of observations.

| Analysis question | Local status | Basis |
|---|---|---|
| Does the path call the real blocking Volume commit before reopen? | **Proven** | `golden_durable_commit` awaits `commit.aio()` when available, otherwise the real sync/awaitable `commit()`, then emits completion and performs reopen verification. |
| Are commit-call wall, return-to-reopen, reopen, stat, readback, hash, verification, and close separately bounded? | **Proven by source; magnitude unmeasured** | The nine raw spans are marked at their named host boundaries and reconcile to the enclosing stage only as a wall decomposition; no remote values were collected. |
| How much of the 0.95–2.27 s variance is server-side Volume commit service time? | **Unproven** | `Volume.commit` is a single blocking API with no lower-level server timing in this process. |
| Is the variance caused by commit, reopen/readback, provider/network, container, or filesystem conditions? | **Unproven** | Two observations cannot establish a causal cohort, and no remote cohort was run for RA7. |
| Does reopen prove the committed PNG's stat size, byte count, and content SHA? | **Proven** | `verify_committed_object` reopens the mounted asset, stats it, reads it, hashes the readback bytes, and fail-closes on mismatches. |
| Is the configured expected output SHA a durability gate? | **Proven not to be a gate in Golden** | Golden passes `enforce_expected_sha=False`; the configured mismatch is recorded as warning-only while pending/reopened content identity remains strict. |
| Does TRUE_FIRST_DURABLE_RESULT occur only after commit and reopen proof? | **Proven** | The recorder requires a successful commit interval and typed reopen proof; the top-level order calls `mark_true_durable()` afterward. |
| Is there a locally proven optimization that makes this endpoint sub-1 s? | **Unproven** | No valid same-deployment cohort or causal timing evidence exists locally. |

No optimization claim should be made from the two-run spread.  Safe candidates
may be considered only after the cohort below identifies a consistently large,
owned component; the current source provides no locally proven sub-1-second
optimization.

## Required same-deployment cohort

Before attributing variance or changing the path, collect at least **three
eligible valid observations from the same deployment**, retaining outliers:

1. Keep app/source/configuration identity, provider, region, image, workflow,
   model, seed, request contract, and output durability contract constant.
2. Run one request per experiment invocation.  Record the complete raw telemetry
   event stream and the enclosing `golden_durable_commit` wall.
3. Exclude only structurally invalid or failed observations from latency
   summaries; retain them, plus all valid slow outliers, in the evidence set.
4. Confirm every eligible observation has commit start/complete, a successful
   typed reopen proof, all nine nonnegative spans, byte-count/content-SHA
   agreement, and the true-durable ordering.
5. Compare per-span distributions and residuals across the cohort.  Treat the
   Modal commit span as an opaque blocking component, not as a fabricated
   server-side decomposition.

Three is the minimum for this gate, not a strong performance sample.  More
observations are appropriate before an optimization decision.

## Output and sidecar ownership audit

`golden_output` encodes the PNG, hashes the exact encoded bytes, and writes the
asset as `<sha256>.png` under the checked Volume mount.  The PNG name and
`PendingDurability.sha256`/`byte_count` are content-derived; the asset is the
durable object protected by commit, reopen, and readback verification.

The adjacent `<sha256>.json` file is an atomic, fsynced descriptor containing
the observed SHA, byte count, dimensions, `request_id`, and volume-relative
asset path.  It is therefore a request receipt/descriptor, not a second
content-integrity proof.  It is written into the same mounted Volume and is
included in the commit operation, but `verify_committed_object` only checks
that its path is inside the mount; it does not reopen or hash the sidecar.
Because the sidecar path is content-hash based, a later request producing
identical PNG bytes can replace that request receipt.  The asset's content
identity and the request receipt must not be conflated.

This distinction is why RA7's commit/reopen claim is limited to the committed
PNG asset and why the configured expected SHA remains an explicit warning-only
observation.
