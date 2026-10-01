---
name: comfymodal-golden-ops
description: Canonical operating procedure for ComfyUI Modal Golden deployments, single-run validation, and performance experiments. Use this for every future Golden deploy/run/experiment.
---

# ComfyModal Golden Operations

Use this skill whenever deploying, running, validating, or benchmarking the ComfyUI Modal Golden path.

This is an operational contract. Do not rediscover or bypass the control plane unless you are explicitly repairing it.

## Golden identity

Canonical runtime:

- profile: `golden_p1`
- class: `ModalRuntimeEntrypointV2`
- method: `run_golden_serial_stream`
- GPU: `rtx-pro-6000`
- expected PNG SHA-256: `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`

Protected production app:

`stable-modal-comfy-v2-golden-p1`

Never use the production app for ordinary experiments.

Custom-node source is a shared, resource-scoped publication. Publish through
the stable `comfyui-custom-nodes-publisher` authority on the
`comfyui-custom-nodes` Volume, never an app derived from the consuming Golden
app. A verified receipt is content identity, not
consumer identity: exact receipt skips happen before publisher resolution,
archive creation, and content upload. A missing/stale receipt may be finalized
from the Volume only when its authoritative generation exactly matches the
canonical desired generation; otherwise publication fails closed.
Receipt recovery requires authoritative **full published-content** identity:
code/deployment identity alone cannot prove the full shared Volume contents.
Missing receipt != missing content, but matching a narrow source identity !=
matching full content. Use one canonical full-content generation for desired
identity, publication, Volume readback, and receipt recovery.

Every experiment gets an explicit isolated app, e.g.:

`batch-ra-r2-cachedit`

Use legal Modal app names. Do not add source-code allowlists for new batch names.

## Generated-output durability policy

Read `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for the current output
contract. `COMFYMODAL_OUTPUT_DURABILITY` accepts only `off` or `strict`;
missing/`off` resolves to `off`, and an invalid explicit value is a
configuration error: `configuration error: COMFYMODAL_OUTPUT_DURABILITY must
be off or strict`. Generated-output durability is **off by default**.

The normal Golden request therefore measures and returns:

```text
encode -> observed SHA/bytes -> FIRST_RESULT_READY -> return
```

An experiment that explicitly selects `strict` must instead prove:

```text
write/fsync -> Volume.commit -> reopen/hash proof
-> TRUE_FIRST_DURABLE_RESULT -> return
```

Strict failure rejects the run; it must not downgrade to `off`. Do not add
persistent output workers, background durability work, deduplication, or
shortcuts. This generated-output choice never weakens S4/source publication:
the shared custom-node publication and full-content identity/readback contract
remain mandatory.

## Supported public commands

Run from the repository root.

```powershell
python tools/v2ctl.py golden status --app <experimental-app>

python tools/v2ctl.py doctor --profile golden_p1 --app <experimental-app>

python tools/v2ctl.py golden deploy --app <experimental-app>

python tools/v2ctl.py --profile golden_p1 --app <experimental-app> source-probe

python tools/v2ctl.py golden run --app <experimental-app>

python tools/v2ctl.py golden run --app <experimental-app> --acknowledge-volume-drift

python tools/v2ctl.py gate --profile golden_p1 --app <experimental-app>

python tools/v2ctl.py --profile golden_p1 --app <experimental-app> confirm --from <gate-manifest> --runs 5
```

`source-probe` and `confirm` are top-level commands. Their global options must precede the subcommand.

Do not directly use:

- `run_v2_single.bat`
- `deploy_and_run_v2_single.bat`
- generic `run`
- `deploy-run`
- `run_plan_stream`
- multi-request backend invocations

If the public Golden interface breaks, fix the public interface instead of bypassing it.

`--acknowledge-volume-drift` deliberately skips only the exact-content
publisher preflight gate (`require_ready`) on `golden run`. The run still
binds the immutable deployment receipt, still requires source-probe evidence,
and records `COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT=1` in the run
manifest. Use it only when the operator explicitly accepts that the shared
custom-nodes Volume may not match the local tree (e.g. another authorized lane
is writing publishable files mid-cohort). It never overrides the deployment
fingerprint, the receipt, or the output contract.

## Normal experiment procedure

1. Choose a new isolated experimental app.
2. Run `doctor` / `golden status`.
3. Freeze the deploy-relevant source/configuration.
4. Run `golden deploy`.
5. Run `source-probe`.
6. Run `golden status` and `doctor` again.
7. Require matching source/deployment identity, verified runtime health, no unintended overrides, and `ready=True`.
8. Run exactly ONE `golden run`.
9. Inspect its structural classification and evidence.
10. If valid, run only the additional observations the experiment needs, normally 1–2 more, separately and serially.
11. Use `gate` / `confirm` only when the experiment explicitly requires a larger confirmation cohort.

Never launch Golden experiment requests concurrently.

### Deploy-baked experiment flags

Before using an experiment-only environment variable:

1. Register it in `config/v2/flag_registry.toml` with its type, default,
   `consumed_at`, `change_requires`, owner, and allowed values.
2. Carry deploy-baked values in the resolved profile used by the canonical
   Golden command. Do not depend on a process-local inherited environment value
   for a later request.
3. Do not pass a deploy-required flag to `golden run`; run-only validation will
   reject it even if the deployed value is identical.
4. Verify the stored/current deployment fingerprints with the same profile used
   for deployment before collecting evidence.

The `golden` command is pinned to `golden_p1`. If an experiment needs a
deploy-baked diagnostic flag and the command cannot select a separate profile,
use the isolated experimental app, record the temporary profile change, and
restore the baseline profile before the next phase.

## Snapshot-capture rule

Inspect EVERY request. Modal may perform a request-time snapshot capture even after several normal runs, including on a different provider, region, worker, or lifecycle path.

A request-time `SNAPSHOT_CAPTURE` never counts.

The ONE experiment request directly after that capture also never counts.

After that directly-following request, later requests are eligible again.

```text
A = SNAPSHOT_CAPTURE       -> INVALID
B = directly after A       -> INVALID
C = normal                 -> ELIGIBLE

D = SNAPSHOT_CAPTURE       -> INVALID
E = directly after D       -> INVALID
F = normal                 -> ELIGIBLE
G = normal                 -> ELIGIBLE
```

A snapshot capture does NOT permanently taint the deployment and does NOT by itself require redeployment.

If the directly-following request is itself another `SNAPSHOT_CAPTURE`, the new capture re-arms the one-request guard.

Normal snapshot creation during deployment/startup is not an experiment request and does not trigger this rule.

Never count a capture or directly-post-capture request merely because its output SHA is correct.

## What makes a run valid

Process exit code `0` is not enough.

An accepted Golden observation must structurally prove the current Golden contract, including:

- correct experimental app
- `ModalRuntimeEntrypointV2`
- `run_golden_serial_stream`
- exactly one Golden request / terminal result
- no generic `run_plan_stream` execution
- current deployment/source identity
- expected workflow/model identity
- `restore_count == 1`
- `request_count == 1`
- authoritative true-cold/restored identity
- expected PNG SHA
- output mode and its matching endpoint evidence
- in `off` mode: observed encoded bytes/SHA and `FIRST_RESULT_READY`
- in `strict` mode: `true_durable == true`, reopen verification, and
  commit-before-reopen ordering
- strict seriality / zero seriality violations
- valid snapshot/quiescence proof
- completed Golden teardown
- required Golden dynamic-VRAM / loader invariants
- no silent fallback relevant to the experiment

Single-use containers, `min_containers=0`, scaledown, or a long delay are not proof of a valid true-cold restored request.

## Source freeze and redeploy

Deployment fingerprint/source identity is authoritative.

Prefer a committed deploy-relevant source state. If intentionally deploying a dirty tree, retain the exact dirty source hash/fingerprint in the deployment manifest.

After deployment:

- any deploy-relevant source/config change -> stop and redeploy;
- do not continue collecting measurements from a stale deployment;
- reports, logs, raw evidence, and passive request-only diagnostics do not require redeployment unless they actually change deployed behavior.

Do not edit deploy-relevant source between observations in one comparison cohort.

If deployment identity changes, do not combine observations from different deployments into one homogeneous same-deployment cohort.

## Evidence handling

Retain every attempt, including:

- snapshot captures
- directly-post-capture invalid requests
- DNFs/platform failures
- slow valid outliers
- successful runs

Use the invocation-bound run/cohort/gate manifests as authority.

Never select evidence solely by newest modification time.

Preserve:

- deployment manifest/fingerprint
- request ID
- app/class/method
- provider/region
- restore/request identity
- workflow/model identity
- output SHA
- durability/reopen evidence
- seriality
- result classification
- run/cohort manifest paths
- raw command/event logs when investigating performance

If stdout and the authoritative artifact disagree, fail closed.

## Performance experiments

For a new change:

1. Deploy the exact candidate.
2. Run one request.
3. Classify it.
4. If it is a snapshot capture, discard it and also discard the directly-following request; then continue.
5. If the first eligible run fails exactness, identity, its selected output
   endpoint/durability contract, routing, or the experiment-specific gate,
   diagnose it before launching confirmation runs.
6. If it passes, collect the remaining requested observations separately.
7. Compare only equivalent timing boundaries. Always ask whether a number is a full stage or a partial sub-span.
8. Preserve complete raw logs; do not rely only on profiler summaries.

For three valid observations report raw values plus mean, median, min, max, range, sample SD, and CV. Do not report a meaningful p90 from `n=3`.

## Profiling a Golden run

When the question is **where the time went**, not whether the run passed, use the
profiling path. It deploys with tracing, runs one request, then downloads and
analyzes the trace.

```text
python tools/v2ctl.py golden profile --app <experimental-app>
```

That single command does the whole loop: deploy with tracing flags, verify the
deployment actually landed via source-probe, run one request, resolve the trace
id, download and SHA-verify the bundle, analyze it, and write the decision
documents. It prints the final report path when done.

- It performs a **real deploy and a real run**. That costs GPU time. Use
  `--dry-run` first if you only want to see the plan.
- It **aborts if source-probe does not report `RESULT=PASS`**, so a stale
  deployment is never profiled.
- Tracing flags are added automatically; do not pass them yourself:
  `COMFYMODAL_V2_FULL_TRACE=1`, `COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER=1`,
  `COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN=1`, and `COMFYMODAL_V2_GOLDEN_DEEP_TRACE=1`
  on the run.

Options: `--min-ms FLOAT` (call-tree expansion floor, default 1.0),
`--skip-analyze` (reuse existing artifacts, only re-render),
`--workspace-id ID`.

### Re-analysing an existing trace without spending GPU time

The bundle fetch, analysis and rendering are usable standalone. This costs
nothing beyond a download:

```text
python tools/golden_profile_pipeline.py latest                  # recent trace ids + bundle sha
python tools/golden_profile_pipeline.py fetch <trace_id>        # download, SHA-verify, extract
python tools/golden_profile_pipeline.py analyze <session_dir>   # parse + analyze + artifacts
python tools/golden_profile_pipeline.py render <session_dir>    # decision documents only
python tools/golden_profile_pipeline.py report <trace_id>       # fetch + analyze + render
python tools/golden_profile_pipeline.py report <trace_id> --skip-analyze   # render only
```

### Reading the output

Final artifact:

```text
artifacts/golden_exhaustive_runs/<trace_id>/<trace_id>/session/derived/golden_stage_report.md
```

The session directory is **doubly nested**; glob for `session` rather than
assuming the path.

Read the report in this order:

1. **Critical path and stage overlap** — read this first. Sum of stage walls
   exceeds the timeline union because stages overlap, so stage size alone
   misranks targets. The `on critical path` column is the uncontended
   fraction: time during a stage when no other stage was running. A stage at
   0% is fully hidden behind a longer sibling, and optimising it moves root
   wall by nothing.
2. **Function rollup** — whole-request totals per function: call count, mean,
   max, total inclusive, total self. Use totals, not means. Inclusive wall
   contains its callees, so totals are not additive down a tree; `total self` is
   the non-overlapping part and separates real work from wrappers.
3. **Per-stage call trees** — recursive, expanded at the `--min-ms` floor.
   Depth is uncapped on purpose; the wall floor bounds it.

### Limits worth stating before you trust it

- The profiler traces **Python frames only** (`ignore_c_function=True`). GPU
  kernel time is invisible, so a GPU-bound stage reads as waiting.
- Large "exclusive self time" in a thread worker or `select`/`EpollSelector`
  is **blocking wait**, not CPU burn.
- The report is **observational**. It localises cost; it does not prove a
  change helps. Confirm every optimisation with an A/B run.
- `GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE = NO` is fail-closed; read the listed
  reasons before trusting coverage.

### Gotcha

The bundle SHA-256 is **not** in the v2ctl run manifest —
`provenance.artifact_sha256` is always `None`. It exists only in
`artifact.json` next to the bundle on the profile volume, and the pipeline reads
it from there and refuses to extract on mismatch. Do not go looking for it in
the run manifest.

## Operational failures

Before calling something a blocker, distinguish:

- unfinished work
- source/control-plane bug
- Modal/platform failure
- stale deployment
- invalid experiment attempt
- external security/repository hygiene

Do not turn unrelated repository-secret hygiene into a Golden deployment prerequisite unless the current runtime actually consumes that secret.

Local startup-test dependency failures are not remote Golden evidence. Record
the exact import/version error, run the focused control-plane and runtime-env
tests relevant to the change, and rely on source-probe plus the authoritative
remote run artifact for deployment conclusions.

For worker-thread diagnostics, verify both the request trace and per-lane trace
context paths. A wrapper that sees no request context may legally no-op even
when its deploy flag and source are correct; the remote artifact must prove the
worker-side event was emitted.

For experiment-owned runtime modules, source-probe should also prove the remote
`__file__`/hash, effective diagnostic level, wrapper registration, and concrete
dispatch owner before a full Golden request. If source identity passes but the
first eligible artifact contains none of the experiment events, stop and add a
module/execution-path probe instead of repeatedly redeploying blind.

If a lock is active, use `status`/`doctor` and the supported recovery path. Never manually delete control-plane lock files or steal an active owner.

## Non-negotiable "never" list

Never:

- experiment against `stable-modal-comfy-v2-golden-p1`
- call legacy BAT deploy/run paths directly
- let Golden fall through to generic execution
- run multiple Golden experiment requests concurrently
- count a request-time snapshot capture
- count the one request directly after a snapshot capture
- permanently invalidate a deployment merely because a capture occurred
- require redeployment solely because a capture occurred
- call a run valid from exit code alone
- infer true-cold status from timing gaps or single-use intent
- continue after a deploy-relevant source change without redeploying
- mix different deployment identities into a homogeneous cohort
- discard invalid attempts or slow valid outliers
- choose canonical evidence by mtime
- trust a timing label without confirming whether it measures a total or a partial span

## Proven R0 reference

R0 proved this operating model on isolated app:

`batch-r0-golden-ops`

with:

- source probe `PASS / MATCH`
- verified runtime health
- `ready=True`
- no runtime overrides
- five valid true-cold Golden runs
- exact expected PNG SHA
- valid gate
- five-run confirmation
- stable production untouched

The R0 app is historical proof of the procedure, not the permanent app name for future experiments.
