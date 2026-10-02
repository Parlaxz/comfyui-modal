# Production-008 Integration Report

Candidate commit: **`d8fe911135955f579e47b17178af15e16fa974c0`**
Branch: `integration/production-008-main-bridge`
Worktree: `.slim/worktrees/golden-best-003` (pre-existing, clean, reused)

> **Status: integration and local validation COMPLETE. Promotion NOT performed.**
> Phases 8 (10 authoritative Golden attempts) and 9 (fast-forward `main`, push,
> `production-008` tag) have **not** been executed. Reasons in section 10.

---

## 1. Merge topology

```
                 7bc05e1a  (shared base of P7 and TESTING8)
                /        \
  9de63e61 <--16--          --30--> 61f99648  (TESTING8 / profiler-001-feature)
  promotion/production-007                    |
        |                                     |
        |  (P7 tip is the BASE of the deploy branch)
        +--22--> 8a53bd77  (diag/deploy-latency-sep30)
                    |
   integration/production-008-modern
        129b66d   merge(profiler)   parent1=9de63e61  parent2=61f99648
        1e19899   merge(deploy)     parent1=129b66d  parent2=8a53bd77
                    |
   integration/production-008-main-bridge
        a46b756   bridge merge      parent1=f8f2da5b (main)  parent2=1e19899e
        d8fe911   + P8 profile
```

`main` diverged from P7 far earlier, at `c8c4db40`.

## 2. Safety refs created (additive only)

| Ref | SHA |
|---|---|
| `safety/pre-p008-main` | `f8f2da5b46becd33cf8e6cc17be804cc56760018` |
| `safety/pre-p008-origin-main` | `25b856221c9334eadecaabc3d4d4f9e113dad26d` |
| `safety/pre-p008-production-007` | `9de63e619568fa64de7fee624152e0bbf2d62e4b` |
| `safety/pre-p008-profiler` | `61f99648bd9dafbb5796e6ed5bd2d717d90b5c0e` |
| `safety/pre-p008-deploy` | `8a53bd77fc3e10ca5196716857e0e2f993e82224` |
| `safety/pre-p008-m1b` | `9fa78ccf7b6e147e2f66acb1270bb1e9bc425373` |

No pre-existing ref was moved. `production-007` and `profiler-001-feature` were
not retagged. All of these are retained.

## 3. Conflicts encountered and exactly how each was resolved

### 3.1 Merge 1 — profiler into P7 base (4 conflict hunks, 2 files)

**`comfymodal_runtime/golden_model_transport.py` :: `load()`**
Resolved to the **profiler** side. Before accepting, I read
`full_execution_trace.thread_traced` and confirmed it resolves the tracer at call
time and is a plain passthrough when no tracer is bound
("an unbound tracer makes this a plain passthrough. Tracing failures never
escape into the load."). With profiling off the production path is unchanged.

**`comfymodal_runtime/golden_parallel.py` — 3 hunks**
- *root span*: profiler opens `golden_root_span(...)` manually and closes it in
  the `finally` after teardown, replacing P7's `with _golden_trace_span(...):`
  block. Verified `golden_root_span` is documented and implemented as **"Inert
  when no tracer is bound"** (`full_execution_trace.py:365`, and the
  `if tracer is None: yield; return` early exit). The surrounding scaffolding
  auto-merged correctly — `golden_root: Any = nullcontext()` default before the
  `try`, and `golden_root.__exit__(None, None, None)` inside the `finally` — so
  the already-dedented body needed no re-indentation and no P7 runtime invariant
  was altered.
- *post-request exit gate signature*: profiler changed
  `gate_s: float = POST_REQUEST_EXIT_GATE_S` to `gate_s: float | None = None`
  resolved at arm time.
- *traced gate budget*: added `POST_REQUEST_EXIT_GATE_TRACED_S = 120.0` and
  `_resolve_post_request_exit_gate_s()`. With
  `COMFYMODAL_V2_FULL_TRACE` off the resolver returns the unchanged production
  `POST_REQUEST_EXIT_GATE_S = 15.0`, so P7's fail-closed `os._exit(71)` behaviour
  is preserved exactly. This matters: the traced path genuinely does need 120s
  because removing the `include_files` whitelist raised a request to ~1.2M
  entries whose serialization legitimately overruns 15s.

**Verification after resolution:** both files were confirmed **byte-identical to
their TESTING8 versions** (`git diff 61f99648 -- <file>` empty for both), and
`python -m py_compile` passed on each.

### 3.2 Merge 2 — deploy into the modern tree (2 conflicts)

**`__init__.py` :: `POST /comfymodal/sync/custom-nodes`** — resolved by
**combining both sides**, not choosing one. The deploy side wraps the route in
`_acquire_studio_publication_lock()` with a 409 refusal on
`LockHeldError`/`LockStaleError`; the profiler side invalidates
`remote_inventory` after a verified publication. Final body keeps both: lock
acquired → sync → inventory invalidation → `finally: publication_lock.release()`
→ response. Releasing in `finally` preserves single-publisher behaviour even when
the sync raises. Verified `_acquire_studio_publication_lock` (line 3311),
`LockHeldError`/`LockStaleError` (line 40) and the sibling lock-guard route at
line 3568 were all present after auto-merge.

**`.gitignore`** — kept **both**: the P7-lineage benchmark-output comment and
`*benchmark*/` pair, plus `.comfymodal_first_party_sources/` from the deploy
side (part of the staged-mount publication path).

No `--ours`/`--theirs`/`-X ours`/`-X theirs`/`git restore`/`git reset` was used
in either merge.

## 4. Deletion audit

Required check after every merge. `git diff --name-status <pre>..<post>` filtered
for `D`:

| Step | Scope | `D` records |
|---|---|---|
| Merge 1 | profiler merge, 39 files | **0** (0 modified, 0 added, 0 deleted) |
| Merge 2 | deploy merge, 36 files | **0** |
| Full | **P7 `9de63e61` -> modern `1e19899e`, whole tree** | **0** |
| Bridge | `main` -> bridge, whole tree | **0** |

Final P7→modern delta: **48 modified, 21 added, 0 deleted.**

## 5. Bridge content-authority proof (machine-checkable)

Computed on the committed tree objects via `git write-tree` /
`git ls-tree -r`, comparing path→blob maps:

| Check | Result |
|---|---|
| Bridge tree object | `e841a57b0da69d18fe42265c1c46ea7b1142ece4` |
| Modern tree object | `08573e6d93598140b9ae5bd3e440aee748f7c302` |
| Total paths in bridge | 8378 |
| Total paths in modern | 8363 |
| **Paths in modern MISSING from bridge** | **0** |
| **Blob mismatches on common paths** | **0** |
| Bridge-only retained paths (main-only) | **15** |

Every path tracked by the modern tree exists in the bridge with byte-identical
content. Zero differences to document.

### 5.1 The 15 retained main-only files (preserved, NOT deleted)

```
tests/test_image_packaging_refactor.py
tests/test_studio_live_progress.py
tests/test_task3_progress_annotations.py
web/modal-comparison.js
web/studio-history.js
web/studio-legacy.js
web/testing-ab-slider.js
web/testing-api.js
web/testing-dashboard.js
web/testing-history.js
web/testing-profiles.js
web/testing-results.js
web/testing-settings.js
web/testing-setup.js
web/testing-setup-adapter.js
```

These exist in `main` and not in the modern tree. Deletion is not authorized, so
all 15 were preserved. Each was individually confirmed still present in the
bridge index.

## 6. Proof nothing unauthorized was deleted or moved

- **Files:** 0 `D` records across all three merges (section 4).
- **Branches:** no `git branch -d/-D` was run. No branch removed.
- **Tags:** no `git tag -d`. `production-007` -> `9de63e61` and
  `profiler-001-feature` -> `61f99648` unchanged. `production-008` not created.
- **Stashes:** none taken or dropped.
- **History:** no rebase, no amend, no `reflog expire`, no `gc`/`prune`.
- **Pushes:** none. No force push.
- **Worktrees:** none created, none removed. All pre-existing worktrees intact.
- **Other agents' dirty work:** untouched. The root checkout is on `TESTING8`
  with ~40 modified files and 4 uncommitted deletions; that working tree was
  **never** checked out, stashed, committed or cleaned. Integration used the
  pre-existing clean `golden-best-003` worktree, whose previous detached commit
  `965da7af` remains preserved by tag `golden-best-003`.
- The `production-007` and `golden-sep14-repro` worktrees hold other parties'
  uncommitted work and were likewise never touched. `diag/deploy-latency-sep30`
  was verified clean before and after being used read-only for reproduction.

## 7. Test results

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| `pytest tests -m fast_unit` | 522 | 2 | 7 |
| `pytest tests -m heavy_local` | 12 | 1 | 0 |
| Targeted deploy/profiler/publication/child-trace (11 files) | 175 | 2 | 2 |
| **Total** | **709** | **5** | **9** |

Plus `python -m compileall comfymodal_runtime` clean, `py_compile` clean on
`__init__.py` / `comfyapp.py`, and `git diff --check 9de63e61 1e19899e` clean.

### 7.1 Every failure classified PRE-EXISTING — zero new regressions

| Failure | Class | Proof it is pre-existing |
|---|---|---|
| `test_rx9p_h_identity_chain.py::test_success_path_exact` | **PRE-EXISTING** | Reproduced on a **pristine P7 extraction** (`git archive 9de63e61` of the test + its only imports, run standalone). Identical assertion. Test file and `experiment_evidence.py` are byte-identical across P7/TESTING8/deploy/bridge. |
| `test_rx9p_h_identity_chain.py::test_compact_nested_sage_observation_is_mismatch` | **PRE-EXISTING** | Same pristine-P7 reproduction. |
| `test_rx9p_g_lifecycle_simulation.py::test_direct_golden_repaired_lifecycle_persists_and_projects_every_gate` | **PRE-EXISTING** | Swapped **P7's** `full_execution_trace.py` into the integration tree and re-ran: identical failure. Not caused by the profiler merge. |
| `test_source_identity_publication.py::test_default_root_is_parent_custom_nodes_for_all_publishers` | **PRE-EXISTING** | Reproduced on the **pristine `diag/deploy-latency-sep30` worktree**. Identical failure. |
| `test_comfyapp_packaging.py::test_image_fused_verification_command_uses_safe_quotes` | **PRE-EXISTING** | Same pristine-deploy reproduction. |

Corroborating signal: the root checkout has
`M tests/test_rx9p_h_identity_chain.py` uncommitted — another agent is
actively working on this exact stale test, which corroborates that it predates
this task. Per the brief, no runtime semantics were modified to make these pass.

**NEW REGRESSION: 0. ENVIRONMENTAL: 0. FLAKY: 0.**

## 8. Production-008 profile

Added: `config/v2/profiles/golden_p1_parallel_c0_p8_h100.toml` (additive; no P7
profile mutated). Extends `golden_p1_parallel_c0_p7_h100`, so P7 invariants are
inherited rather than restated. Only the target app differs
(`batch-c0-p7-h100` -> `batch-c0-p8-h100`).

### 8.1 Proof that P8 changes no runtime behaviour

Resolved both configs and compared over **172 resolved keys**:

```
v2ctl --profile golden_p1_parallel_c0_p7_h100 --json config
v2ctl --profile golden_p1_parallel_c0_p8_h100 --json config
```

**Flag VALUE differences between P7 and P8: 0.**

The only differences are identity labels and the fingerprints that follow from
them: `profile` name, `owner` (`production-007` -> `production-008`), the
`source:` label on each inherited flag, `target.app`, and the three derived
fingerprints:

| | P7 | P8 |
|---|---|---|
| deploy_fingerprint | `b767658c8c7508ec43eda10797fb6dd4fe5d71415b8e8697559033b39bf78e0f` | `4886bf8a2621920eb1785f1d6d152daf6de065a41f8e044d32938180a334909e` |
| profile_config_fingerprint | `f91b039d763f34265acf62ed869050ae890173948921ae51801ff79d4f992edf` | `e74f8f73b4854108cce1fa67b8ba842ed9018de1285d8e5eec2c2d4becbd5bea` |
| run_fingerprint | `2fc9755715ffa537ce436972a6afaec6d60356a4489a98377009ddd76bc42a00` | `53ffc8937c495ed4acb8a7d33071d894363e9ea8af4b27606a855e4c96bf0927` |

### 8.2 P8 runtime invariants confirmed on the resolved config

| Invariant | Resolved value |
|---|---|
| GPU / CPU / memory | `H100!` / `12` / `24576` |
| `COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE` | `whole` |
| `COMFYMODAL_GOLDEN_C0_SOURCE_WORKER_KIND` | `thread` |
| `COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE` | `mmap_fresh` |
| `COMFYMODAL_GOLDEN_{IO_PROCESS_V2,C0}_*_GEOMETRY` | `qd4_64` |
| `COMFYMODAL_GOLDEN_IO_PROCESS_V2_PERSISTENT_FDS` | `1` |
| `COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN` | `1` |
| Correctness SHA | `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` (identical to P7) |
| Conditioning | `conditioning_cache=forced_miss`, `fresh_required=true` |

### 8.3 Profiler DEFAULT-OFF on P8

`COMFYMODAL_V2_FULL_TRACE=0`, `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=0`,
`COMFYMODAL_V2_E27_FORENSICS=0`, `COMFYMODAL_GOLDEN_C0_WINDOW_TRACE=0`,
`COMFYMODAL_SAMPLING_DEEP_PROFILE=off`,
`COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER=0`. Full VizTracer, exhaustive profiling,
Torch profiler and the C0 child VizTracer are all OFF. WILLNEED/prewarm, Volume
V2 and alternative source geometry are not enabled. No M1B/M1C copy probe or
diagnostic profile is present.

### 8.4 Target destination audit (the "Testing 8 / Testing 9" risk)

`config/v2/modal_target.toml` resolves to `workspace_id = ws_ee7221847f7d`,
`workspace_label = "Testing 9"`. **This is unchanged from Production-007** —
`git show 9de63e61:config/v2/modal_target.toml` is byte-identical to the current
file. The profiler stack did **not** retarget production; "Testing 9" is the
P7-established destination and was deliberately preserved. `v2ctl doctor`
confirms config ownership is respected (`runtime_override_policy=forbid`,
`runtime_overrides.present=0`).

## 9. Source identity probe

Not run against the candidate. `v2ctl doctor` reports
`deployment.manifest=none` — no deployment exists for
`batch-c0-p8-h100`, so there is no remote container to probe. The historical
probe evidence is real but stale (section 3.3 of the inventory: it ran against
`batch-golden-shared-transport` / `golden_p1` / `Testing 5` at git
`5f86b06aa22d`). **Fresh source-identity proof for `d8fe911` requires Phase 7
deployment, which has not run.**

## 10. Why promotion was not performed

Phases 8 and 9 were not executed. Not a destructive-operation blocker — the
non-destructive path is available and rehearsed. Two things need Ahmed's
decision first:

1. **A premise of the plan could not be confirmed.** The brief stated the deploy
   optimization was proven with a 3868-file byte-equivalence result
   (`CONTENT_DIFFERENCES=0 / PATH_DIFFERENCES=0 / MODE_MISMATCHES=0`) and asked
   me to confirm the evidence exists. **It does not exist anywhere in the
   repository or its history.** Every occurrence of `3868` is an unrelated
   timing value. Tagging `production-008` and pointing `main` at code whose
   headline acceptance artifact is absent would publish a claim that cannot be
   substantiated.

2. **Pushing `main` publishes 17 previously-unpushed commits.** Local `main` is
   `f8f2da5b`, 17 commits ahead of `origin/main` (`25b85622`), dated 2026-08-06
   to 2026-08-09 ("lean-snapshot candidate + snapshot-build manifest + entry-probe
   tooling", "restore-mode region pin", "reconcile validated TWO-LANE production
   candidate into main"). A fast-forward promotion and normal push would publish
   all of them to the public repository for the first time. `origin/main` **is** an
   ancestor of local `main`, so this needs no force and destroys nothing — but it
   is an outward-facing publication that was not part of the stated plan.

Everything needed to finish is staged and verified. On approval the remaining
work is mechanical:

1. Deploy `batch-c0-p8-h100` via `v2ctl deploy`; run the source-identity probe
   and a real KJNodes/JoinStrings container-registration probe against
   `d8fe911`.
2. Run exactly 10 Golden attempts on the P8 profile; compare against the P7 cohort.
3. `git checkout main && git merge --ff-only integration/production-008-main-bridge`,
   push, then create annotated tag `production-008` on the exact tested SHA.

If acceptance fails, the prescribed path applies: nothing is deleted, no reset,
no tag moved, `production-007` untouched, `main` not force-moved, and the
candidate branch plus all evidence stay intact.

## 11. Final SHA

| Item | SHA |
|---|---|
| **Candidate (tested-to-be)** | **`d8fe911135955f579e47b17178af15e16fa974c0`** |
| Modern integration | `1e19899e3ef8f4290b133f90700f51471730cfe7` |
| Bridge merge | `a46b756c3220c20796d0e1c6ee4db8346c113ded` |
| P7 | `9de63e619568fa64de7fee624152e0bbf2d62e4b` |
| Profiler | `61f99648bd9dafbb5796e6ed5bd2d717d90b5c0e` |
| Deploy | `8a53bd77fc3e10ca5196716857e0e2f993e82224` |
| main (local, unmoved) | `f8f2da5b46becd33cf8e6cc17be804cc56760018` |
| origin/main (unmoved) | `25b856221c9334eadecaabc3d4d4f9e113dad26d` |

**10 Production-008 request IDs: none — cohort not run.**
**P7 vs P8 table: not produced — cohort not run.**
**`production-008` tag: NOT created.**