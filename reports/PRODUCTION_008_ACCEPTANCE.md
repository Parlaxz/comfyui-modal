# Production-008 Acceptance Report

**Candidate commit: `d8fe911135955f579e47b17178af15e16fa974c0`**
Branch: `integration/production-008-main-bridge`

---

## OUTCOME: ACCEPTANCE NOT RUN — CANDIDATE NOT PROMOTED

**No Production-008 Golden attempt was executed. `main` was not advanced. The
`production-008` tag was not created.**

This report is deliberately explicit about what is *not* claimed. Nothing below
should be read as an acceptance pass.

---

## 1. Acceptance cohort status

| Item | Status |
|---|---|
| Attempts run | **0 of 10** |
| Request/run IDs | **none** |
| Deployment fingerprint for a deployed candidate | **none** (`deployment.manifest=none`) |
| Deployed image ID | none |
| `valid=true` count | 0 |
| Correct output SHA verified in-container | **not verified** |
| Fallback observed | not measured |
| Fresh source-identity proof for `d8fe911` | **not obtained** |

## 2. P7 vs P8 comparison

**Not produced.** A comparison requires the P8 cohort. No CLIP/UNET source ms,
GB/s, full-load ms, startup, restore, sampler, VAE, output, teardown or total-wall
statistic exists for P8, so no min/p50/p90/max/mean/CV can be computed and no
failure-rate or fallback-rate delta can be stated.

The prior P7 10-run cohort was **not** re-measured or altered, and no attempt was
made to synthesise P8 numbers from the P7 baseline or from profiler runs on
TESTING8. Profiler runs are not comparable to counted production runs: the P8
profile has `COMFYMODAL_V2_FULL_TRACE=0`, and no run was performed with it on.

Placement (provider x region) is likewise unreported for P8. The earlier finding
that provider x region explains only a minority of source variance still stands
for P7 but has no P8 measurement to accompany it.

## 3. Deployment acceptance

Not performed. `v2ctl doctor` reports `deployment.manifest=none`, so there is no
`batch-c0-p8-h100` deployment to inspect. Unproven for the candidate:

- archive path active in a real deployed container
- custom-node payload identity correct
- real plugins load (KJNodes / JoinStrings)
- publication generation correct
- no stale staging content
- Studio sync status behaviour intact
- image mode does not falsely show unsynced
- dependency rebuild separate from normal warm deploy
- no production outage / import crash

Warm-deploy wall was not measured; no cold-deploy benchmarking was created.

**Important, per the deploy-agent lesson: a successful image build would not have
counted as proof anyway.** Container health and plugin registration require an
actual in-container probe, and no such probe was run against `d8fe911`.

### 3.1 Historical deploy evidence — what exists and what does not

Verified during inventory (details in `PRODUCTION_008_COMMIT_INVENTORY.md` §3):

**Present and real** — a genuine live-registry plugin classification:

```json
"join_strings": {"classification":"real_kjnodes","owner":"KJNodes",
  "reason":"live_registry_points_to_real_kjnodes","registered":true,
  "source":"real_kjnodes",
  "source_file":"/root/comfy/ComfyUI/custom_nodes/ComfyUI-KJNodes/nodes/nodes.py"}
```
plus `RESULT=PASS source_identity=MATCH` from
`unetClipExperimentsSeptember/evidence_text/exp00_source_probe_stdout.txt`.

But it is **stale**: `app=batch-golden-shared-transport`, `profile=golden_p1`,
`workspace=Testing5`, `git_head=5f86b06aa22d…` (2026-09-26). It is not evidence
about `d8fe911`.

**ABSENT** — the headline byte-equivalence proof. Searches across the whole
repository and its history for `CONTENT_DIFFERENCES`, `PATH_DIFFERENCES` and
`MODE_MISMATCHES` returned **zero** files. All 20 occurrences of the literal
`3868` are unrelated timing values (`"wall_ms": 3868.656271`,
`"duration_ms": 3868.728896`, `5.3868`). The claimed
`3868 files / CONTENT_DIFFERENCES=0 / PATH_DIFFERENCES=0 / MODE_MISMATCHES=0`
result **cannot be substantiated**.

The deploy *mechanism* is present and locally covered (archive build in
`_build_custom_nodes_archive`, publication readback, single-publisher
`DeployLock`, `COMFYMODAL_CUSTOM_NODES_VOLUME` identity, per-node dependency
layers), and all fifteen reported deploy features were confirmed present in the
final tree. What is missing is the specific reported artifact.

## 4. Runtime invariants — verified by configuration, not by execution

These were proven on the **resolved P8 config** (`v2ctl --profile
golden_p1_parallel_c0_p8_h100 --json config`) and by a 172-key comparison against
the resolved P7 config. That comparison returned **0 flag-value differences**, so
P8 provably carries P7's runtime semantics forward unchanged. It has **not** been
proven by a running container.

| Required invariant | Config-resolved | Observed in a P8 run |
|---|---|---|
| H100! | yes | not measured |
| CPU=12 | yes | not measured |
| min_containers=0 / single-use | yes (`SINGLE_USE_CONTAINERS=1`) | not measured |
| whole mmap lifecycle | `whole` | not measured |
| thread source owner | `thread` | not measured |
| mmap_fresh engine identity | `mmap_fresh` | not measured |
| qd4_64 geometry | `qd4_64` | not measured |
| 512 MiB arena / 8 x 64 MiB | inherited via qd4_64 chain | not measured |
| persistent FDs | `1` | not measured |
| MINIMAL_GPU_TEARDOWN=1 | `1` | not measured |
| current P7 H2D / source path | inherited unchanged | not measured |
| forced miss, no fallback | `forced_miss`, `fresh_required=true` | not measured |
| no stale READY/protocol failure | P7 `ce0a765e` inherited | not measured |
| no gate failure | gates inherited | not measured |

### 4.1 Profiler default-OFF — verified by configuration

`COMFYMODAL_V2_FULL_TRACE=0`, `GOLDEN_STAGE_DIAGNOSTICS=0`,
`V2_E27_FORENSICS=0`, `GOLDEN_C0_WINDOW_TRACE=0`,
`SAMPLING_DEEP_PROFILE=off`, `GOLDEN_C0_CHILD_VIZTRACER=0`.

Full VizTracer, exhaustive profiling, Torch profiler and C0 child VizTracer are
OFF. This is the configuration the 10 attempts *would* have used. WILLNEED /
prewarm, Volume V2 and alternative source geometry are not enabled.

### 4.2 Known profiler limitations carried into Production-008

Integrated but inert; recorded for the tag message:

- The post-request exit bound is 120s (not the production 15s) **only** when
  `COMFYMODAL_V2_FULL_TRACE` is on. With it off the bound is unchanged at 15s.
- Under full trace the `include_files` whitelist is dropped, raising a Golden
  request from ~40k to ~1.2M entries; final VizTracer serialization then
  legitimately exceeds 15s. This is why the traced gate exists.
- `thread_traced` only reaches threads created after
  `enable_thread_tracing()`; without the `load()` handoff the C0 UNET path
  records zero frames while reporting `source_read_count=184`.
- `golden_root_span` exists because VizTracer 1.1.1 hardcodes `cat="FEE"` in
  `VizEvent.__exit__`, making an explicit root span and the automatic call record
  indistinguishable. Two competing roots make the exhaustive profiler fail
  closed.

## 5. Local test acceptance (the part that did run)

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| `pytest tests -m fast_unit` | 522 | 2 | 7 |
| `pytest tests -m heavy_local` | 12 | 1 | 0 |
| Targeted deploy/profiler/publication/child-trace (11 files) | 175 | 2 | 2 |
| **Total** | **709** | **5** | **9** |

All 5 failures were **reproduced on the relevant parent** and are therefore
**PRE-EXISTING**:

| Failure | Reproduced on |
|---|---|
| `test_rx9p_h_identity_chain.py::test_success_path_exact` | pristine P7 extraction |
| `test_rx9p_h_identity_chain.py::test_compact_nested_sage_observation_is_mismatch` | pristine P7 extraction |
| `test_rx9p_g_lifecycle_simulation.py::test_direct_golden_repaired_lifecycle_persists_and_projects_every_gate` | P7's `full_execution_trace.py` swapped in |
| `test_source_identity_publication.py::test_default_root_is_parent_custom_nodes_for_all_publishers` | pristine `diag/deploy-latency-sep30` |
| `test_comfyapp_packaging.py::test_image_fused_verification_command_uses_safe_quotes` | pristine `diag/deploy-latency-sep30` |

**NEW REGRESSION: 0. ENVIRONMENTAL: 0. FLAKY: 0.**

`compileall comfymodal_runtime` clean; `py_compile` clean on `__init__.py` and
`comfyapp.py`; `git diff --check 9de63e61 1e19899e` clean.

## 6. Deletion / preservation audit

Zero file deletions across all three merges (profiler, deploy, bridge). 15
main-only files preserved and listed in `PRODUCTION_008_INTEGRATION.md` §5.1. No
branch, tag, stash, worktree or ref removed or moved. No force push. No rebase,
amend, reflog expire or gc. The root checkout's uncommitted work by other agents
was never touched.

## 7. What is required to complete acceptance

1. Deploy `batch-c0-p8-h100` from `d8fe911` via `v2ctl deploy` (v2ctl only —
   never raw `modal deploy`, per repo policy).
2. Run the source-identity probe and confirm remote module SHAs match the exact
   candidate. Record the deployment fingerprint and image ID.
3. Run a real in-container KJNodes/JoinStrings registration probe. A green image
   build is not sufficient.
4. Run **exactly 10** Golden attempts on `golden_p1_parallel_c0_p8_h100`, no
   treatment arm, no profiler, no prewarm, no Volume V2. Record per attempt:
   request ID, deployment fingerprint, git SHA, profile, app, provider, region,
   image ID, startup, restore, CLIP source ms / GB/s / full load / forward,
   UNET source ms / GB/s / full load, sampler, VAE, output, teardown,
   backend/request wall, correctness SHA, fallback status.
5. Compare against the P7 10-run cohort (min/p50/p90/max/mean/CV for CLIP and
   UNET source ms, GB/s, full load; plus startup, restore, forward, sampler, VAE,
   output, teardown, total wall, failure rate, correctness, fallback rate),
   reporting provider x region as context without normalising it away.
6. If 10/10 pass with no code change since `d8fe911`:
   `git checkout main && git merge --ff-only integration/production-008-main-bridge`,
   push (no force), then create annotated tag `production-008` on that exact SHA.
   `origin/main` is an ancestor of local `main`, so this needs no force.

### Two decisions needed from Ahmed first

1. **The 3868-file byte-equivalence proof does not exist.** Either produce it, or
   accept promotion without it and record that absence in the tag message.
2. **Pushing `main` publishes 17 previously-unpushed commits** (local `main`
   `f8f2da5b` is ahead of `origin/main` `25b85622`, dated 2026-08-06..09). Safe
   (fast-forward, no rewrite) but outward-facing and outside the stated plan.

## 8. Final state

| Ref | SHA | Action taken |
|---|---|---|
| `integration/production-008-modern` | `1e19899e3ef8f4290b133f90700f51471730cfe7` | created |
| `integration/production-008-main-bridge` | `d8fe911135955f579e47b17178af15e16fa974c0` | created |
| `safety/pre-p008-*` (6 refs) | see integration report §2 | created, retained |
| `main` | `f8f2da5b46becd33cf8e6cc17be804cc56760018` | **unmoved** |
| `origin/main` | `25b856221c9334eadecaabc3d4d4f9e113dad26d` | **unpushed, unmoved** |
| tag `production-007` | `9de63e61…` | **unmoved** |
| tag `profiler-001-feature` | `61f99648…` | **unmoved** |
| tag `production-008` | — | **NOT created** |

All candidate branches, safety refs, worktrees, evidence and reports are
retained for audit. Production-007 remains untouched.