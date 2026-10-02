# Production-008 Commit Inventory

Scope: every ref, branch, tag and worktree in the local repository, inventoried
**before** any merge. No ref was moved, no file deleted, no branch removed.

Repository: `comfyui-modal`
Inventory taken on branch `integration/production-008-modern` /
`integration/production-008-main-bridge` (clean worktree).

---

## 0. Ref facts as verified locally (not taken from the brief)

| Ref | SHA | Note |
|---|---|---|
| `main` (local) | `f8f2da5b46becd33cf8e6cc17be804cc56760018` | **17 commits AHEAD of `origin/main` and unpushed** |
| `origin/main` | `25b856221c9334eadecaabc3d4d4f9e113dad26d` | matches the brief |
| `promotion/production-007` | `9de63e619568fa64de7fee624152e0bbf2d62e4b` | matches |
| tag `production-007` | object `5cfea3ad…` -> `9de63e61…` | annotated, matches |
| `TESTING8` | `61f99648bd9dafbb5796e6ed5bd2d717d90b5c0e` | matches |
| tag `profiler-001-feature` | object `db745d4a…` -> `61f99648…` | annotated, matches |
| `diag/deploy-latency-sep30` | `8a53bd77fc3e10ca5196716857e0e2f993e82224` | local-only, recovered OK |
| tag `production-008` | **DOES NOT EXIST** | confirmed |

Two facts in the brief needed correcting against local reality:

1. **`main` is not `25b85622` locally.** Local `main` is `f8f2da5b`, which is
   17 commits ahead of `origin/main`. `origin/main` **is** an ancestor of local
   `main`, so this is a pure fast-forward relationship, not a divergence that
   would require a force update. See "Consequences for Phase 9".
2. **`diag/deploy-latency-sep30` has 22 commits after Production-007, not 9.**
   The agent report's "9 commits" is wrong. Full enumeration in section 3.

Merge base of `production-007` and `TESTING8`: `7bc05e1a5c1b6f61c1d54bbd9da2bce422d0bc21` — confirmed.
`main` diverged much earlier, at `c8c4db40cd9e7d14136aba0abf6479e61b239491`.

---

## 1. Production-007 stack — VERIFIED EXACTLY AS BRIEFED

16 commits after `7bc05e1a`, oldest first. Every hash and subject matched.

| # | SHA | Subject |
|---|---|---|
| 1 | `1b2f02029d4d10028dec684fe992331accbce9e2` | production-006: stabilize C0 whole source lifecycle |
| 2 | `d3dd77a7e2e12b9522879f3a3411f70f5b53c000` | production-006: bound total Golden request wall + heartbeat |
| 3 | `c1fa89fb026d25e4ecff385caa0c4428b859fd7e` | production-006: scope request gate / bound post-request exit |
| 4 | `5d41f742f42eb2fbddc3bbfa5641fe01dd35faa6` | production-006: add outer-method lifetime marks |
| 5 | `42cf4d048a8dbc66535753a857cc5cd99135f074` | production-006: add product… (baseline documentation) |
| 6 | `852fc55139be2fe342335c28b9186da7d65385d4` | production-006: persist out… |
| 7 | `ff8a4448b972e9b236abbb31080d4aa6e0fb373b` | production-006: emit outer-… |
| 8 | `528abddbf7e67c2968e500542664133494e86b48` | production-006: include inn… |
| 9 | `ec76b64cc59578dadf7a1aa560be2079ca7b4a7d` | production-006: minimal pos… |
| 10 | `5ac6f704389b9d96d9a2b7cad5c40b98d85c45f5` | production-006: stop duplic… |
| 11 | `821c7760a52f05e970c12c668dd57caac5928801` | production-006: measure hea… |
| 12 | `ce0a765e1fea505728eb91eff26a05b1b1a25ec5` | production-006: recover REA… |
| 13 | `6efecb7ab77f67b8e4dc48cfe64d2533912f0803` | diagnostics: record container snapshot/region facts |
| 14 | `c19e61c11b743069a81a4f3f16f3908f199e792d` | diagnostics: persist container snapshot/region facts |
| 15 | `f37dcc78b2d4b438fea83ef0b31cd3d98ec0cac5` | production-007: promote the healthy live-control runtime |
| 16 | `9de63e619568fa64de7fee624152e0bbf2d62e4b` | production-007: baseline report and acceptance tooling |

`git rev-list --count 7bc05e1a..promotion/production-007` = **16**. Confirmed.

---

## 2. TESTING8 / profiler-001-feature stack — VERIFIED EXACTLY AS BRIEFED

30 commits after `7bc05e1a`. Sequence matches the brief exactly, including both
intentional commit/revert pairs. Reverted behaviour was **not** resurrected and
history was **not** rewritten.

| # | SHA | Subject |
|---|---|---|
| 1 | `e851c7b75bd72a8f3059c6246481b38de925167b` | feat: exhaustive multiprocess Golden execution profiler |
| 2 | `72df5c3371585644621153e2138175b409d51b2b` | fix: attach the C0 child VizTracer trace into the parent bundle |
| 3 | `2ac07d2921db5d739d3f5f92a88e3a74ce177b19` | feat: state where Golden wall actually went |
| 4 | `471d8cf702e2e7352b64731078f0bade588b09a0` | feat: emit and resolve every Parallel Golden stage span |
| 5 | `44e71ac9415475146d8675c228463f9efa011e6e` | feat: attribute cross-thread… |
| 6 | `e399d5b995dae58e96a409fbfbb876d8fbe95ee6` | fix: trace GoldenModelTransport… |
| 7 | `a746d8d18645d7cfe54e60e5ecb18da3d6c7e067` | fix: restore the `role=` load… |
| 8 | `a869ec68e36bdc488dc362c49cae85a7ec4d4cc2` | fix: resolve dependencies against Modal Volume |
| 9 | `ce7fc973472a4e824986812b95aaad3cc6e2a034` | feat: add read-only custom-node sync status |
| 10 | `65dd3cf4aa119edf7d19011510923576ef7f7f84` | **REVERT of #9** |
| 11 | `a2e5a21c5f11c593c7779c7e2496b531b634c87f` | fix: stop losing VizTracer include_files subtree |
| 12 | `9f293ffdb03e679e9e7f63454e3c192843d02546` | perf: fix profiler O(n^2) blowups |
| 13 | `80571035ca2509959d37fc41f31dbac5f5325790` | feat: per-stage Golden Gantt |
| 14 | `0b2ac3db4ac1dfa2ed6ba10389bd009e6284d792` | perf: stop 381 MB summary serialization |
| 15 | `af81dbd5b6d679848d39e0667debce0f7bc8ddce` | feat: recursive per-stage Golden call tree |
| 16 | `ee499db1f7e8f7d9a411c30fdb9f6b7e3da4b309` | feat: single Golden stage decision report |
| 17 | `37c390995a34a3c8a4ce4de2d2fcc5cd19bf741d` | perf: streaming JSON artifact output |
| 18 | `8ce1371466d11eef504d8ce4223929e2c672505a` | feat: `golden profile` end-to-end |
| 19 | `537b5562db4fa5522405f76b204d902130560197` | docs: profiler workflow skill |
| 20 | `be8ecfd1d8874ed5b43e836580facba3a0c3b083` | fix(gitignore): stop ignoring… |
| 21 | `ba6722ef4a3b68948ec0c517c6df34de944e5e5c` | perf: cut profiler resident memory |
| 22 | `d20e42057cc9996dd40f5147b57d3213e663562f` | feat: streamline profile flow / deterministic trace ID |
| 23 | `bacf27ba8dc9af6fd748e184b690f49c4b48aa9d` | fix: resolve the Golden app from the profile |
| 24 | `f72733eeec51e1bfb6f9b6a97849a8b6341b9618` | attempted incomplete-call contract fix |
| 25 | `f50e37f0812e5788c063d3fe00db885d74a25457` | **REVERT of #24** |
| 26 | `394877b576ef7026a7f535f733e81905808ddd2f` | perf: render the report once instead of twice |
| 27 | `74fb64a48189f3f3f5acb6ef2322b8c398e26721` | fix: `golden deploy --for-profiling` |
| 28 | `758c4e68b09ca5aaa1bca836f8a222e0afc5749a` | fix: distinguish "no child ran" from "child ran untraced" |
| 29 | `56d3b4bb67198cd90e525d98de0005253aab8805` | fix: report a child-manifest write failure |
| 30 | `61f99648bd9dafbb5796e6ed5bd2d717d90b5c0e` | fix: record an unknown child-trace state |

`git rev-list --count 7bc05e1a..TESTING8` = **30**. Confirmed.

Note: commit #9 `ce7fc973` "add read-only custom-node sync status" was reverted by
#10, but the *same feature* was later re-landed independently by the deploy stack
as `0a1b01ae`. The revert therefore does not remove the capability from the
consolidated tree; it removes it from the profiler lineage. Both histories are
preserved verbatim.

---

## 3. Deploy branch `diag/deploy-latency-sep30` — 22 COMMITS, NOT 9

The agent report claimed 9 commits. Local enumeration shows **22 commits after
Production-007**, including 2 merge commits. `diag/deploy-latency-sep30` is a
**descendant** of `production-007` (`git merge-base` = `9de63e61`), not a sibling,
so it merges into a P7-based tree without a base conflict.

Oldest first, with the files each commit touched (from `git show --stat`):

| # | SHA | Subject | Files |
|---|---|---|---|
| 1 | `95d7334f6e9a53d7bcbfcfea47025072e5a06842` | stop publishing host experiment evidence into the image | `publication_policy.py`, `test_source_identity_publication.py` |
| 2 | `f036395a7434a9edae31d20f01580ea8b8c7696c` | exclude remaining host experiment evidence | `publication_policy.py` |
| 3 | `5d0f1e03e6d8c4337032096d4d9aabc1cad681f0` | ship first-party sources as one staged mount, not fifteen | `.gitignore`, `.modalignore`, `comfyapp.py`, `publication_policy.py`, 2 tests |
| 4 | `47014452b524c47bf053f8455875b14dba17d9eb` | rename workspace env vars out of the MODAL_ namespace | 5 `.bat`, `benchmark_v2_direct.py`, `publish_custom_nodes_volume.py`, 4 `v2_control/*` |
| 5 | `ce5b583c91180edce9392f7bb91fbea9b9fd6420` | stop publishing first-party benchmark harness nodes | `publication_policy.py`, 1 test |
| 6 | `b36551a89a9afc22b6f454c1441ad23dae1bf5dd` | per-node dependency layers with fail-closed verification | `comfyapp.py`, 2 tests |
| 7 | `7fce793b0b09f36cc75b2d83e0e55af069ff3ce4` | add opt-in Volume-backed custom node delivery | `comfyapp.py`, `modal_app.py`, 1 test |
| 8 | `1a27cff65477afdd1c5bc102f682cd3a5a3a93b3` | mount the custom-node Volume at exactly one path | `modal_app.py`, 1 test |
| 9 | `1115f39b` | *merge* `fix/workspace-env-naming-clean` | — |
| 10 | `beae987c` | *merge* `opt/exclude-harness-nodes-clean` | — |
| 11 | `eeb9c08a3001adac25f226adfe8dba29f072d2fd` | verify custom node publication readback | `custom_nodes.py`, `deployment_receipt.py`, 3 tests |
| 12 | `de52fc243b0b8ebedf139a956d2505eee871a8aa` | build the custom-node verification layer only on the deploy path | `comfyapp.py` |
| 13 | `d8575bd7abe4794de85e5269785b095b8f26e9ef` | bound volume delivery and publication readback | `comfyapp.py`, `modal_app.py`, 2 tests, `custom_nodes.py` |
| 14 | `3b93e89c680bfe615a417f9fbf7fdc553bab5099` | honor `COMFYMODAL_CUSTOM_NODES_VOLUME` in publication policy | `publication_policy.py` |
| 15 | `fadec016e2c2ed5a44cd61c4c465d05a67adf862` | build the volume-delivery image plan against a minimal node tree | 1 test |
| 16 | `0a1b01aeb53b65824c46baf05665cf1b1267495f` | add read-only custom-node sync status | `custom_node_identity.py`, `custom_node_registry.py`, `model_library_routes.py`, 1 test |
| 17 | `cf20f61068f9a866d66a81e415869e55de809a1c` | add studio custom-node sync warning | 1 `.mjs` test, 2 `web/*` |
| 18 | `c09d46b53b6e5d4341537556889fa4040db6b050` | serialize custom-node publication, isolate per-invocation staging | `__init__.py`, `comfyapp.py`, 1 test |
| 19 | `399f8fa974e9394b9c0bb8695c85a2052f5282b7` | wire studio custom-node sync actions | `__init__.py`, `model_library_routes.py`, 2 tests, 2 `web/*` |
| 20 | `4b6ba86a64546eb474e55654c542bd5505e89295` | test: cover sync lock refusal | 1 test |
| 21 | `16bdad5fb01471789687aa02f57e5ba458aed4d3` | optimize custom-node image delivery archive | `__init__.py`, `comfyapp.py`, 1 test, `custom_nodes.py` |
| 22 | `8a53bd77fc3e10ca5196716857e0e2f993e82224` | test: assert source delivery by behaviour, not `add_local_dir` | 1 test |

### 3.1 Claimed feature checklist — verified PRESENT in the final tree

All fifteen reported features are present. Defining locations:

| Feature | Status | Where |
|---|---|---|
| Archive-based custom-node/plugin delivery | PRESENT | `__init__.py:_build_custom_nodes_archive`, `tools/v2_control/custom_nodes.py` |
| Warm deploy reduction | PRESENT | `__init__.py` warmup state/actions |
| Deterministic byte-equivalence logic | PRESENT | `tools/v2_control/custom_nodes.py`, `comfymodal_runtime/publication_policy.py` |
| Custom-node Volume publication safety | PRESENT | `__init__.py` publication path |
| Single-publisher / locking | PRESENT | `__init__.py:_acquire_studio_publication_lock`, `tools/v2_control/locking.py:DeployLock` |
| Per-invocation ephemeral staging | PRESENT | `tools/v2_control/custom_nodes.py` |
| Actual published content verification | PRESENT | `publish_or_skip` / `verified_publication` |
| Configurable Volume identity agreement | PRESENT | `publication_policy.py`, `COMFYMODAL_CUSTOM_NODES_VOLUME` |
| Custom-node Git own-root verification | PRESENT | custom-node identity/verification code |
| Studio Backend -> Deployment sync status | PRESENT | `__init__.py`, `web/studio-backend-deployment.js` |
| Push plugins action | PRESENT | `web/studio-backend-deployment.js` |
| Dependency rebuild action | PRESENT | `__init__.py` dependency rebuild handling |
| Image-mode `not_applicable` behavior | PRESENT | `__init__.py` |
| Publication cleanup behavior | PRESENT | `__init__.py` |
| Dependency-change state | PRESENT | `__init__.py` / sync-status code |

### 3.2 Claimed evidence — ONE PROOF NOT FOUND

The brief asked me to confirm this evidence exists. **It does not.**

Searched the whole deploy worktree and git history for
`CONTENT_DIFFERENCES`, `PATH_DIFFERENCES`, `MODE_MISMATCHES` and `3868`:

- **0 files** contain `CONTENT_DIFFERENCES`, `PATH_DIFFERENCES` or
  `MODE_MISMATCHES` anywhere in the repository or its history.
- The 20 hits for the literal `3868` are **all unrelated timing values**
  (e.g. `"wall_ms": 3868.656271`, `5.3868`, `"duration_ms": 3868.728896`).
  None is a file count.

**Verdict: the claimed 3868-file byte-equivalence proof
(`CONTENT_DIFFERENCES=0 / PATH_DIFFERENCES=0 / MODE_MISMATCHES=0`) is NOT
present in the repository and cannot be confirmed.** The byte-equivalence
*mechanism* is present in code and covered by `test_source_identity_publication.py`
and `test_custom_node_publication_guard.py`, but the specific reported artifact
is absent. This is recorded as an open discrepancy, not silently accepted.

### 3.3 Plugin registration probe — CONFIRMED, but STALE

The real KJNodes/JoinStrings probe evidence does exist:

`EXPERIMENT_EVIDENCE_golden_p1_45180f215a7c4c7f_2026-09-26.md` (probe block):

```json
"join_strings": {"classification":"real_kjnodes","owner":"KJNodes",
  "reason":"live_registry_points_to_real_kjnodes","registered":true,
  "source":"real_kjnodes",
  "source_file":"/root/comfy/ComfyUI/custom_nodes/ComfyUI-KJNodes/nodes/nodes.py",
  "source_module":"/root/comfy/ComfyUI/custom_nodes/ComfyUI-KJNodes.nodes.nodes"}
```

`unetClipExperimentsSeptember/evidence_text/exp00_source_probe_stdout.txt`:

```text
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH
```

Caveat: that probe ran against `app=batch-golden-shared-transport`,
`profile=golden_p1`, `workspace=Testing5`, `git_head=5f86b06aa22d…`. It is a
**historical** run on an older app/profile/workspace. It proves the
classification mechanism works and that real KJNodes registers, but it does
**not** prove the current Production-008 candidate's archive-delivered container
loads plugins. Fresh proof for the exact candidate requires the Phase 7/8
deployment, which has not been run.

---

## 4. Complete local-ref audit for other post-007 work

Method: enumerated every ref (`100` local branches, `17` remote refs, `18`
tags = `135` refs) and computed, per branch, the commits not reachable from
`{promotion/production-007, TESTING8, diag/deploy-latency-sep30}`. 52 unique
commits in the post-P7 window were examined individually
(`git show --stat`, message, parent).

### 4.1 Already represented — NOT separately included

The first-pass classifier flagged these as INCLUDE candidates; they were
**false positives** and are already inside the deploy stack. Verified with
`git merge-base --is-ancestor <sha> diag/deploy-latency-sep30`:

| SHA | Subject | Verdict |
|---|---|---|
| `5d0f1e03` | ship first-party sources as one staged mount | **ALREADY IN DEPLOY** (ancestor confirmed) |
| `f036395a` | exclude remaining host experiment evidence | **ALREADY IN DEPLOY** |
| `95d7334f` | stop publishing host experiment evidence | **ALREADY IN DEPLOY** |

`ab-mountfix` (tip `5d0f1e03`) and `ab-control` (tip `f036395a`) are not separate
lineages at all — `git merge-base ab-mountfix diag/deploy-latency-sep30` returns
`5d0f1e03`, i.e. they are **ancestors of the deploy branch**.

### 4.2 The one genuinely unique post-P7 candidate: `3e720a4b` — EXCLUDED

`3e720a4b43919c25e6b1f1ecda8b0ca56e42d927` on
`integration/m1b-correctness-fixes` (tip `9fa78ccf`) is the **only** post-P7
commit not already represented. It is **not** an ancestor of P7, TESTING8 or the
deploy stack (all three `merge-base --is-ancestor` checks returned false).

Classification: **DIAGNOSTIC / EXPERIMENT ONLY — NOT INCLUDED.**

Evidence for that decision:

- Its own message says the probe is *"default OFF and the profile targets a
  separate diagnostic app"* and that it was ported *"so future experiments
  inherit the fixes instead of rediscovering them"*. That is diagnostic
  scaffolding, not production optimization.
- It injects a **42-line hook into `golden_parallel.golden_parallel_execute`**,
  the Golden hot path, plus 7 lines into `modal_app._runtime_env`.
- It adds `comfymodal_runtime/m1_copy_probe.py` (698 lines) and a diagnostic
  profile `golden_p1_parallel_c0_copydiag_h100.toml`.
- It registers two new flags in `flag_registry.toml`
  (`COMFYMODAL_M1B_COPY_PROBE`, `COMFYMODAL_M1B_LEVEL`).
- Decisive: the **Production-007 profile itself** states the intended policy —
  *"No M1B/M1C copy probes, diagnostic profiles, arena globals or other
  experiment-only machinery are present in this lineage."* Merging this commit
  would contradict the production lineage's own stated invariant, and the task
  requires P8 to preserve the P7 execution/runtime invariants.
- Its sibling commits (`9fa78ccf`, `c210d922`, `7e3e1f8a`, `3c77a818`) are
  report/evidence only (`tools/variance.py` plus `reports/m1_copy_rootcause/*`).

The branch is preserved at `safety/pre-p008-m1b` (`9fa78ccf`) and remains
available for a future diagnostic lineage. Nothing was deleted.

Two items inside `3e720a4b` are arguably portable dev tooling rather than
diagnostic machinery — `tools/golden_evidence_gate.py` (acceptance gate on real
fields rather than `event_count`, which reads 1 on every run) and
`tools/run_golden_bounded.ps1` (bounds a run that otherwise has no timeout).
They were **not** imported unilaterally because neither is a post-P7 production
optimization; flagging them for a decision instead.

### 4.3 Everything else

The remaining ~47 unique commits are on diagnostic/treatment-arm branches and
classify as EXPERIMENT ONLY or REPORT ONLY:

| Branch | Commits | Classification | Reason |
|---|---|---|---|
| `diag/m1-copy-root-cause` | 12 | EXPERIMENT ONLY | "M1-CB" factorial calibration harness arms, sentinel instrumentation |
| `diag/m1-loader-forensics` | 9 | EXPERIMENT ONLY / REPORT ONLY | Level-1/2 forensic probes and reports |
| `exp/inprocess-pinned-source-threads` | 16 | EXPERIMENT ONLY / REPORT ONLY | pinned-vs-pageable A/B treatment arms |
| `integration/m1b-correctness-fixes` | 4 (of 5) | REPORT ONLY | M1C reports + `tools/variance.py` |
| `TESTING8-before-github-publish` | 4 | EXPERIMENT ONLY / REPORT ONLY | superseded by the selected TESTING8 stack |
| historical/archive refs | 8 | PRE-P7, OUT OF SCOPE | dated 2026-09-26/27, before P7 |

**No `UNKNOWN` items remain.**

### 4.4 Decision summary

| Class | Count | Commits |
|---|---|---|
| INCLUDED | 51 | P7 (16) + profiler (30) + deploy (22 non-merge) + `ab-*` already inside deploy |
| ALREADY REPRESENTED | 3 | `5d0f1e03`, `f036395a`, `95d7334f` |
| REVERTED (preserved in history, not resurrected) | 2 pairs | `ce7fc973`→`65dd3cf4`, `f72733ee`→`f50e37f0` |
| EXCLUDED — DIAGNOSTIC | 1 | `3e720a4b` |
| EXPERIMENT ONLY | ~37 | `diag/m1-*`, `exp/inprocess-*` |
| REPORT ONLY | ~10 | M1C/M1 reports |
| UNKNOWN | 0 | — |