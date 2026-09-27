# September UNET/CLIP experiments: deterministic host-only reporting contract

This directory records frozen experiment evidence.  It is a reporting bundle,
not a control plane.  A report is allowed to describe remote execution, but
the report builder must never cause remote execution.

## 1. Collection boundary

The collection owner records one immutable deployment and one separately
identified request per invocation.  A deploy-relevant source/configuration
change stops the cohort.  Do not repair the tree or redeploy inside that
cohort.  The following are collection rules, not actions for the report
builder:

* use an isolated experimental app and exactly one deployment;
* issue serial requests, one request per invocation, with the prescribed gap;
* retain the authoritative capture-guard result after every request;
* retain every attempt, including S (snapshot capture), P (direct follower),
  pre-capture, invalid, DNF, exactness failure, and slow valid outlier;
* count only valid eligible R1--R5 observations after S and P; never infer a
  capture boundary from timestamps, file order, or modification time.
* `--acknowledge-volume-drift` may be used only on explicit operator order; it
  skips solely the exact-content publisher gate, binds the same immutable
  receipt, and is recorded per-run via
  `COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT=1` in the run manifest.
* an operator-asserted capture boundary against a silent guard is allowed only
  when the operator states it explicitly; the report must preserve both the
  guard record and the override, and S/P stay excluded from statistics.

## 2. Host-only generator contract

`build_experiment_report.py` is a deterministic standard-library-only
renderer.  It accepts explicit manifest and output paths as arguments and may
read only paths named by that manifest.  It must not import Modal, call a
deploy/run command, use subprocess or network access, mutate runtime state, or
discover evidence with globbing, directory scans, newest-file logic, or mtime
ordering.  Re-running it is safe and has no remote side effects.

Evidence is joined by the manifest's deployment, invocation, request, and
cohort IDs.  A path is not evidence of association merely because it is newer
or has a plausible filename.  Missing explicit paths are rendered as
`UNAVAILABLE`/`ABSENT`; they are never silently replaced by another file.

## 3. Required input manifest

The manifest must explicitly identify:

1. experiment, worktree, branch, HEAD, dirty state, tracked diff and complete
   untracked inventory;
2. app, profile, class, method, GPU, deployment fingerprint, deployment
   manifest/receipt, profile and run fingerprints, experiment ID, content
   generation, and both expected-output SHA and skill-identity SHA;
3. effective environment and the applicable SHA/validity policies;
4. ordered attempts, each with attempt key, role, classification, invocation
   ID, request ID (or an explicit unavailable value), capture-guard record,
   artifact paths, console paths, and derived/raw evidence paths;
5. the exact status/doctor/source-probe/deploy captures and the explicit raw
   evidence root.

The generator preserves manifest order.  It does not decide which attempt is
"good".  It resolves an attempt only through its explicit invocation/request
   binding and retains all listed attempts.

## 4. Required report schema

Every report is self-contained and contains these sections, even when the
cohort is incomplete:

* status at the top, including literal
  `PERFORMANCE_COMPARISON=NOT_PERFORMED` and
  `PERFORMANCE_VERDICT=NOT_PROVIDED`;
* experiment/deployment identity, dirty and untracked inventory, environment,
  raw evidence root, and both SHA policies;
* ordered attempt ledger with exact eligible request IDs and counted R1--R5;
* five-run stage table and statistics section.  If fewer than five counted
  observations exist, retain the schema rows but mark the table
  `NOT_APPLICABLE_INCOMPLETE` and do not compute mean, median, SD, CV, or
  other cohort statistics from n=1;
* CLIP, UNET, VAE, output/durability, and invariant/decomposition sections.
  Missing future fields remain `UNAVAILABLE` rather than being deleted;
* per-attempt appendices containing verbatim deployment, probe, status/doctor,
  run stdout, manifests, capture guard, and applicable raw/derived evidence;
* an audit path inventory, with explicit `ABSENT` records for checked-but-not-
  produced artifacts.  Large JSON may be represented by its complete required
  identity/capture/validation/cold sections plus byte size and SHA-256.

## 5. Interpretation rules

Raw evidence outranks summaries.  Stage walls retain their declared boundary
(TOTAL, PARTIAL, DERIVED, or UNKNOWN) and nested values are not added as if
they were independent.  `true_cold`, restore/request counts, output hash,
seriality, teardown, and capture classification are reported as observed.
No report makes a cross-experiment performance comparison or supplies a
performance verdict unless a complete, valid five-observation cohort and the
separate comparison contract exist.  A stopped or contaminated cohort is
`INCOMPLETE`, never silently repaired.
