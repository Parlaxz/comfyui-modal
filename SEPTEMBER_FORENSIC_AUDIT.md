# SEPTEMBER 2026 FORENSIC AUDIT — comfyui-modal

Read-only forensic audit of all September 2026 development history, local and remote,
including every worktree, clone, branch and dangling object. **No branch was modified, no
worktree reset/cleaned/pruned/deleted, no gc, no rebase, no cherry-pick.** The only mutation
in this session was an explicit, separately-requested commit of the source-read harness
(`b9196ac`), described in §18.

Evidence tiers used throughout: **PROVEN** (direct code/result/artifact evidence) ·
**STRONG INFERENCE** (multiple pieces align, no direct result artifact) · **UNKNOWN**
(evidence missing). `UNKNOWN` is never upgraded to fact.

Machine-readable companions: `september_commits.csv`, `september_worktrees.csv`,
`september_optimizations.csv`.

---

## 1. Executive inventory

| metric | value |
|---|---:|
| **Total unique September commits** | **277** |
| — of which merge commits | 3 |
| — reachable from local `main` | **0** |
| — reachable from local `TESTING2` | 94 |
| — reachable only from other local branches/worktrees | **183** |
| — on GitHub (any ref) | **0** |
| **LOCAL-ONLY September commits** | **277** |
| **GITHUB-ONLY September commits** | **0** |
| **Unreachable / dangling September commits** | **99** (of 100 unreachable total) |
| **Worktrees registered with git** | **49** |
| — present on disk | 46 |
| — dir missing / prunable | 3 |
| **Independent clones containing project work** | **0** |
| **Dirty worktrees** | **24** |
| **Successful optimizations identified** | **19** (see §7) |
| — of those, absent from current `TESTING2` | **13** (all Golden-side, marked below) |
| **Total commits reachable from all refs** | 772 |
| Commits reachable from the GitHub mirror | 415 |

**Headline:** the entire September 2026 development history exists **only on this machine**.
GitHub's newest commit is `02f1845` (2026-08-30, `TESTING2`); nothing from September was ever
pushed. Local `TESTING2` is **111 ahead** of `origin/TESTING2`; local `main` is **17 ahead** of
`origin/main` and is itself an **August** commit (`f8f2da5`, 2026-08-09).

---

## 2. Repository / remote identity

| item | value |
|---|---|
| repository root | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal` |
| origin URL | `https://github.com/Parlaxz/comfyui-modal.git` |
| GitHub owner/repo | `Parlaxz/comfyui-modal` |
| current branch | `TESTING2` |
| current HEAD | `711f7cfb932e2d44f7dc285441e9cd5f827cdd30` → now `b9196ac` after §18 |
| git dir | `.git` |
| git common dir | `.git` (single common dir; all worktrees share it) |
| `.git/worktrees` admin entries | **48** (= 49 registered − 1 main) |
| local refs (`show-ref`) | **108** |
| tags | `archive-v2.16.23-96ce004`, `golden-best-001`, `golden-best-002`, `golden-best-003`, `golden-canonical-2026-09-09`, `pre-2909edb-revert-20260809-200603` |
| remote-tracking refs | 9 (`origin/{HEAD,TESTING2,dev,exp/runtime-snapshot-shape,feat/custom-nodes-management-v2,fix/p1-p5-production-activation,main,production/final-micro-optimizations-v21624,r42-golden-reconciliation}`) |

### GitHub remote state (from a temporary read-only mirror, working repo untouched)

A `git clone --mirror` into the temp dir was used for remote enumeration. It resolved **9 refs**:

| remote ref | SHA | date |
|---|---|---|
| `refs/heads/TESTING2` | `02f1845a37c7c602bb598afb7e33cab938044e99` | 2026-08-30 |
| `refs/heads/main` | `25b856221c9334eadecaabc3d4d4f9e113dad26d` | 2026-08-05 |
| `refs/heads/dev` | `a89c365eb2ad665e4be8612c33d05fcae43bbe86` | — |
| `refs/heads/production/final-micro-optimizations-v21624` | `b301c483f210f77ee4369af01caa6680a300fb97` | — |
| `refs/heads/r42-golden-reconciliation` | `6040c459f2766f2ccb2f97799c08ff53b616d54a` | — |
| `refs/heads/fix/p1-p5-production-activation` | `80a9b3d20249dc815f9806b9b2d0504cf2c5101c` | — |
| `refs/heads/exp/runtime-snapshot-shape` | `77544c9e9f940e1919d53171332f39b2074b726f` | — |
| `refs/heads/feat/custom-nodes-management-v2` | `c8c4db40cd9e7d14136aba0abf6479e61b239491` | — |
| `refs/pull/1/head` | `a89c365eb2ad665e4be8612c33d05fcae43bbe86` | (= `dev`) |

**The local remote-tracking refs match the mirror exactly**, so they are **not stale** — no
fetch is needed to know the remote state. The mirror contains **415** commits; the local repo
contains **772**. The 357-commit difference is the September work plus earlier unpushed work.

---

## 3. Known anchor commits (verified, not assumed)

All three exist, are real commits, and — importantly — **none is an ancestor of `TESTING2`**.

### `03ce24916958596717220167db496b1215544d09`
| field | value |
|---|---|
| author / commit date | **2026-09-14 14:57:41 -0500** (identical) |
| subject | `fix: bound C0 teardown to prevent post-output hang` |
| parent | `76bdc57bf7dbb11a44401c780f724df535958e1c` |
| files changed | **1** |
| contained by | `diag/c0-arm1-join`, `diag/golden-sickness-final-causal-closure-sep18`, `exp/cuda-event-per-transfer-causality-sep20`, `exp/cuda-vs-no-cuda-source-causality-sep20`, `exp/golden-host-path-isolation-sep18`, `exp/golden-io-process-v2`, `exp/golden-q2-128-resource-failover-sep18`, `exp/golden-sickness-native`, `exp/golden-striped-source-sep19`, `exp/golden-volume-v1-v2-h100-sep19`, `exp/odirect-shadow-sep14`, `exp/pretouch-ab-control-sep14`, … |
| also a worktree HEAD | `.slim/worktrees/golden-sep14-repro` (detached) |
| ancestor of TESTING2 | **NO** |

### `d9504d167e2acd4bea3860a2349b2f5de35da711`
| field | value |
|---|---|
| author / commit date | **2026-09-17 14:46:52 -0500** |
| subject | `refactor: finalize Golden restore lifecycle` |
| parent | `d1fffd2f5da108f0a718ea80da56152ae29f9c57` |
| files changed | **5** |
| contained by | `diag/c0-arm1-join`, `diag/golden-sickness-final-causal-closure-sep18`, `exp/cuda-*`, `exp/golden-host-path-isolation-sep18`, `exp/golden-q2-128-resource-failover-sep18`, `exp/golden-sickness-native`, `exp/golden-striped-source-sep19`, `exp/golden-volume-v1-v2-h100-sep19`, `exp/pristine-resource-carrier-isolation-sep19`, `golden-best-001-archival`, `golden-best-002-archival`, … |
| ancestor of TESTING2 | **NO** |

### `d95e4347963024b51be76cfbb2c5c6d9d96c39a1`
| field | value |
|---|---|
| author / commit date | **2026-09-17 14:59:27 -0500** |
| subject | `feat: add H100 Sep14 C0 profile` |
| parent | **`d9504d167e2acd4bea3860a2349b2f5de35da711`** (direct child of the previous anchor) |
| files changed | **2** |
| contained by | same set as `d9504d16` |
| ancestor of TESTING2 | **NO** |

**Verified relationship:** `03ce2491` (Sep 14, C0 teardown bound) sits on the Sep-14 Golden line;
`d9504d16` → `d95e4347` form a **direct parent→child pair on Sep 17** (restore lifecycle
finalization, then the H100 Sep14 C0 profile). All three are carried by the `golden-best-001/002`
archival branches and the `exp/*` September worktree branches, and by **no** GitHub ref.

**Better/more recent candidate anchors discovered** (factual only, unranked — see §15):
`618c592` (Sep 18/19, shared by `exp/golden-q2-128-resource-failover-sep18` and
`exp/pristine-resource-carrier-isolation-sep19`), `a7b62e6` (Sep 20, CUDA-vs-no-CUDA source
causality), `d642e97` (Sep 20, CUDA event per-transfer causality), `7a7410d` (Sep 18, Golden
sickness final causal closure), `f7e6282` (golden-best-003 archival), `334fc5e`
(`omos/authoritative-golden-core-sep14`), `711f7cf` (current TESTING2 tip).

---

## 4. Full September commit chronology

**277 commits**, grouped by author date. The complete per-commit table (SHA, both dates, author,
subject, parents, merge flag, files-changed count, refs, exact-ref tips, ancestry flags) is in
`september_commits.csv`. Per-day counts:

| day | commits | day | commits |
|---|---:|---|---:|
| 2026-09-01 | 43 | 2026-09-11 | 15 |
| 2026-09-02 | 8 | 2026-09-12 | 31 |
| 2026-09-03 | 5 | 2026-09-13 | 18 |
| 2026-09-04 | 1 | 2026-09-14 | 15 |
| 2026-09-05 | 1 | 2026-09-15 | 4 |
| 2026-09-06 | 3 | 2026-09-16 | 6 |
| 2026-09-07 | 11 | 2026-09-17 | 17 |
| 2026-09-08 | 11 | 2026-09-18 | 45 |
| 2026-09-09 | 12 | 2026-09-19 | 19 |
| 2026-09-10 | 4 | 2026-09-20 | 8 |

**Author vs committer dates:** for all 277 commits the two date fields are **identical** — there
is no September rebase/cherry-pick skew in the reachable September set. (Rebase-like rewriting
does appear among the unreachable stash objects; see §12.)

**Branch/tag tips among the September commits: 34.** Notable tips:

| SHA | ref(s) | subject |
|---|---|---|
| `9138522` | `omos/rx6b-golden-waterfall-routing` | docs: report RX6B waterfall routing correction |
| `45a4a58` | `rx7-static-e27` | docs: record RX7 E27 static scheduling A/B |
| `54017eb` | `omos/rx7a-static-e27` | docs: record RX7 E27 static scheduling A/B |
| `369d60c` | `rx9p-d-golden-profiler` | RX9P-D report-only micro-fix |
| `7c8d3ce` | `rx9p-t-slow-test-fix` | RX9P-T: finalize performance audit handoff |
| `a09e804` | `p05/git-evidence-hygiene` | P0.5: establish Git evidence hygiene |
| `8297a3a` | `omos/p0-golden-shared-primitives` | refactor Golden shared primitives architecture |
| `6f8a38b` | `p1/golden-integration` | Resolve Modal CLI after shell restart |
| `0ea9428` | `omos/golden-post-loop-tail`, `omos/golden-rk-coeff-controller` | Reorder Golden DynamicVRAM before QD2 |
| `4577213` | `omos/golden-rk-coeff-controller-exp2` | Optimize Golden RK controller overhead |
| `6711b6b` | `omos/golden-post-loop-tail-exp2` | Remove Golden sampler GC tail |
| `f3c5171` | `omos/golden-sampler-ab-integration` | Retarget combined RK lane test |
| `4421610` | `omos/golden-gc-suppression-exp3` | fix: accept stock RES4LYF loader identity |
| `7152cca` | `exp/golden-minimal-restore` | docs: prove deferred GPU-repair path is not invoked under minimal restore |
| `d7c8ade` | `exp/golden-minimal-io` | exp: Golden Parallel profile uses ComfyKitchen attention |
| `2b1e847` | **`refs/stash`** | On r42-golden-reconciliation: cleanup 2026-09-12 |
| `03ce249` | `exp/pretouch-ab-control-sep14` | fix: bound C0 teardown to prevent post-output hang |
| `b6ecd06` | `exp/golden-io-process-v2` | diag: count live Wave-A probes |
| `02b623f` | `exp/odirect-shadow-sep14` | classify O_DIRECT completion separation |
| `a94c149` | `exp/pretouch-ab-pretouch-sep14` | fix: retarget Golden pretouch at the live reader seam |
| `0ee60b0` | `exp/resource-local-carryover-sep14` | fix: route parallel Golden output contract |
| `334fc5e` | `omos/authoritative-golden-core-sep14` | diag: project snapshot manifest through minimal restore |
| `b75e88c` | `golden-best-001-archival` | archival: exact RTX PRO 6000 15x15 deployed source/config |
| `0c5f3f0` | `golden-best-002-archival` | archival: byte-exact RTX PRO 6000 15x15 deployed source/config |
| `f7e6282` | `golden-best-003-archival` | docs: promote golden-best-003 provenance record |
| `d8b4a13` | `exp/golden-sickness-native` | diag: gated native preadv timer for C0 source reads |
| `ae4c8db` | `diag/c0-arm1-join` | diag: offline addendum refining report Q6 framing |
| `7a7410d` | `diag/golden-sickness-final-causal-closure-sep18` | diag: report hygiene |
| `1af62a1` | `exp/golden-host-path-isolation-sep18` | feat: add diagnostic Golden host memory-scaling battery |
| `3ebbfad` | `exp/golden-striped-source-sep19` | feat: add diagnostic Golden striped source probe |
| `7ba393b` | `exp/golden-volume-v1-v2-h100-sep19` | feat: add diagnostic Golden Volume v1-vs-v2 paired source probe |
| `618c592` | `exp/golden-q2-128-resource-failover-sep18`, `exp/pristine-resource-carrier-isolation-sep19` | audit: final31 R2 usage cache gap and contention forensics |
| `d642e97` | `exp/cuda-event-per-transfer-causality-sep20` | fix: forward CUDA event arm selectors |
| `a7b62e6` | `exp/cuda-vs-no-cuda-source-causality-sep20` | report: analyze CUDA source causality cohort |

**Files most often touched in September** (proxy for where the work concentrated):

| file | touches |
|---|---:|
| `comfymodal_runtime/modal_app.py` | 69 |
| `comfymodal_runtime/golden_serial.py` | 61 |
| `comfymodal_runtime/golden_io_process_v2.py` | 52 |
| `config/v2/flag_registry.toml` | 45 |
| `comfymodal_runtime/config_authority.py` | 27 |
| `comfymodal_runtime/golden_parallel.py` | 19 |
| `tools/benchmark_v2_direct.py` | 18 |
| `tools/v2_control/cli.py` | 17 |
| `comfymodal_runtime/golden_qd_transport.py` | 16 |
| `comfyapp.py` | 14 |

---

## 5. Full worktree inventory

**49 registered worktrees** (1 main + 48 linked), **46 present on disk**, **3 with the directory
gone but still registered** (marked *prunable* by git). **0 independent clones** were found on
the machine for this repository. Full table: `september_worktrees.csv`.

### Missing-dir (prunable) worktrees — commits still safe in the shared object store

| worktree path | branch | HEAD | state |
|---|---|---|---|
| `.slim/worktrees/odirect-shadow-sep14` | `exp/odirect-shadow-sep14` | `02b623f` | **dir GONE**, branch intact |
| `.slim/worktrees/pretouch-ab-control-sep14` | `exp/pretouch-ab-control-sep14` | `03ce2491` | **dir GONE**, branch intact |
| `.slim/worktrees/pretouch-ab-pretouch-sep14` | `exp/pretouch-ab-pretouch-sep14` | `a94c149` | **dir GONE**, branch intact |

Note: `exp/pretouch-ab-control-sep14`'s HEAD **is the anchor `03ce2491`**, and its directory is
gone — the anchor survives only as a branch/commit, not as a worktree.

### Where the worktrees live (3 roots)

| root | count | notes |
|---|---:|---|
| `...\comfyui-modal\.slim\worktrees\` | 22 | September Golden/experiment worktrees |
| `C:\Users\parla\.config\superpowers\worktrees\comfyui-modal\` | 12 | older (Jun–Aug) worktrees |
| `...\ComfyUI June Install\custom_nodes_excluded_C9_2026-08-14\` | 19 | worktrees in an *excluded* sibling dir |

All 49 are **linked worktrees** of the one common git dir (each has a `.git` *file* containing
`gitdir:`). No independent clone exists.

### September reach per worktree (commits reachable from that worktree's HEAD)

| worktree branch | Sep commits reachable | last commit |
|---|---:|---|
| `exp/cuda-vs-no-cuda-source-causality-sep20` | 193 | 2026-09-20 |
| `exp/cuda-event-per-transfer-causality-sep20` | 187 | 2026-09-20 |
| `exp/golden-q2-128-resource-failover-sep18` | 185 | 2026-09-19 |
| `exp/pristine-resource-carrier-isolation-sep19` | 185 | 2026-09-19 |
| `diag/golden-sickness-final-causal-closure-sep18` | 179 | 2026-09-18 |
| `exp/golden-volume-v1-v2-h100-sep19` | 176 | 2026-09-19 |
| `exp/golden-striped-source-sep19` | 175 | 2026-09-19 |
| `exp/golden-host-path-isolation-sep18` | 174 | 2026-09-19 |
| `diag/c0-arm1-join` | 161 | 2026-09-18 |
| `golden-best-003-archival` | 155 | 2026-09-18 |
| `.slim/worktrees/golden-best-003` (detached) | 154 | 2026-09-18 |
| `exp/golden-sickness-native` | 154 | 2026-09-18 |
| `exp/golden-io-process-v2` | 142 | 2026-09-14 |
| `exp/resource-local-carryover-sep14` | 141 | 2026-09-16 |
| `.slim/worktrees/golden-sep14-repro` (detached) | 139 | 2026-09-14 |
| **`TESTING2`** | **94** | 2026-09-24 |
| `exp/golden-minimal-io` | 81 | 2026-09-11 |
| `exp/golden-minimal-restore` | 77 | 2026-09-11 |

**The two `sep20` CUDA worktrees reach 193 / 187 September commits — i.e. they contain
essentially the whole September history**, far more than `TESTING2` (94).

---

## 6. Experiment / worktree lineage

Reconstructed from parents, branch names, subjects and reports. Every chain answers: *based on
what → what changed → what it tested → what happened → carried / superseded / reverted /
abandoned.*

### Golden line (the bulk of September)
```
Golden baseline (Aug) ──► P0 shared primitives (8297a3a)
   └─► P1 golden integration (6f8a38b)
        └─► RX1 QD4 telemetry repair (960fee0)
             └─► RX2 sampling decomposition (90457b4)
                  └─► RX3 CLIP forward (6f889df, worktree rx3)
                       └─► RX6 log cleanup (52adf9f)
                            └─► RX6B waterfall routing (9138522 / 3f03032 / 17bf190)  [carried into TESTING2]
                                 └─► RX7 static E27 A/B (54017eb / 45a4a58)
                                      └─► RX7A integration (083629f)  [carried into TESTING2]
                                           └─► RX9P-D profiler (369d60c)
                                                └─► RX9P-T slow-test fix (7c8d3ce)
```
- **Based on:** the August Golden baseline. **Changed:** Golden runtime internals
  (`modal_app.py`, `golden_serial.py`, `golden_qd_transport.py`, `flag_registry.toml`).
  **Tested:** sampling decomposition, CLIP forward, waterfall routing, static E27 scheduling,
  QD4 telemetry. **Happened:** RX6B and RX7A were **integrated into `TESTING2`** (the only
  September Golden work that reached the current branch). **RX1/RX2/RX3/RX6/RX9P remain on their
  own branches.**

### Golden restore / minimal-restore line (Sep 11–17)
```
exp/golden-minimal-io (d7c8ade) ──┐
exp/golden-minimal-restore (7152cca) ──► GOLDEN_MINIMAL_RESTORE_IMPLEMENTATION_2026-09-11.md
   └─► authoritative-golden-core-sep14 (334fc5e) + diag/c0-arm1-join (ae4c8db)
        └─► 03ce2491 (Sep14: bound C0 teardown)  ◄── ANCHOR
             └─► … Sep17: d9504d16 (finalize restore lifecycle) ◄── ANCHOR
                  └─► d95e4347 (add H100 Sep14 C0 profile) ◄── ANCHOR
```
**Happened:** the minimal-restore work proved the deferred GPU-repair path is not invoked; the
Sep-14 C0 teardown hang was bounded; on Sep 17 the restore lifecycle was finalized and an H100
Sep-14 C0 profile added. **Carried:** into `golden-best-001/002/003` archival branches and the
`exp/*` Sep18–20 worktrees. **Not carried:** not on `TESTING2`.

### Golden resource / carrier line (Sep 18–19)
```
exp/golden-q2-128-resource-failover-sep18 (618c592)
exp/pristine-resource-carrier-isolation-sep19 (618c592)   ← same SHA, two branches
   └─► final31 R2 usage-cache-gap + contention forensics
```
**Happened:** a shared-SHA audit branch pair; the Q2/128 resource-failover and the
pristine-resource-carrier isolation converged on the same commit `618c592`. **Not carried** to
`TESTING2`.

### Golden source-probe line (Sep 18–20)
```
exp/golden-host-path-isolation-sep18 (1af62a1)  → host memory-scaling battery
exp/golden-sickness-native (d8b4a13)            → gated native preadv timer for C0 reads
exp/golden-striped-source-sep19 (3ebbfad)       → striped source probe (A/C/D + decoupled B)
exp/golden-volume-v1-v2-h100-sep19 (7ba393b)    → Volume v1-vs-v2 paired source probe
exp/cuda-event-per-transfer-causality-sep20 (d642e97)
exp/cuda-vs-no-cuda-source-causality-sep20 (a7b62e6)  → report: analyze CUDA source causality cohort
```
**Tested:** whether source cost is CUDA-event-related, host-path-related, or volume-path-related.
**Happened:** the Sep-20 pair is the most advanced (193/187 September commits reachable).
**Not carried** to `TESTING2`.

### Source-I/O line (this workstream — now committed)
```
SOURCE_IO_LEDGER.md (ledger of the preadv/mmap source investigation)
  └─► source_race_oracle.py + e04_source_race_modal.py + run_imbalance_campaign.py
       └─► frozen baseline: 64 MiB / QD4 / 4 ms / fresh-window mmap / MAP_PRIVATE
            └─► rejections recorded: MAP_SHARED, deferred munmap, CPU affinity, fixed-VA, 0 ms pacing
```
**Carried:** committed in §18 (`b9196ac`).

---

## 7. Demonstrated successful optimizations

Full table with evidence tier and "present in TESTING2 / Golden?" columns:
`september_optimizations.csv`. Summary of the **19 identified successes**:

### Source-I/O workstream (PROVEN, all present in the committed harness)
| optimization | evidence | present in TESTING2 |
|---|---|---|
| 4 independent reader processes (not threads) | +10–12% median within matched provider analysis | **yes (harness)** |
| persistent FD per reader | removes open churn | **yes (harness)** |
| eager workers before request timing | removed ~3.4 s first-start serialization | **yes (harness)** |
| self-service allocator | bubble 0.1095 ms/block vs 1.4290 greedy (**18×**) | **yes (harness)** |
| fresh-window mmap MAP_PRIVATE 64 MiB QD4 4 ms | frozen baseline, 0 ops ≥250 ms | **yes (harness)** |
| `mmap(PROT_READ, MAP_PRIVATE)` | works; MAP_SHARED rejected −12.1% | **yes (harness)** |

### Golden workstream (PROVEN via reports/archives; **NOT on TESTING2** unless noted)
| optimization | commit / worktree | present in TESTING2? |
|---|---|---|
| RX6B waterfall routing restore | `9138522` / `3f03032` / `17bf190` | **YES (integrated)** |
| RX7A static E27 scheduling | `083629f` (+ `54017eb`, `45a4a58`) | **YES (integrated)** |
| Golden minimal restore (deferred GPU-repair not invoked) | `exp/golden-minimal-restore` `7152cca` | no |
| Golden P4-8 durable commit lane | `omos/golden-p4-8-durability` `e5eb5ec` | no |
| Golden host memory-scaling battery | `exp/golden-host-path-isolation-sep18` `1af62a1` | no |
| Golden striped source probe | `exp/golden-striped-source-sep19` `3ebbfad` | no |
| Golden Volume v1-vs-v2 paired probe (H100) | `exp/golden-volume-v1-v2-h100-sep19` `7ba393b` | no |
| CUDA event per-transfer causality | `exp/cuda-event-per-transfer-causality-sep20` `d642e97` | no |
| CUDA-vs-no-CUDA source causality | `exp/cuda-vs-no-cuda-source-causality-sep20` `a7b62e6` | no |
| Golden Q2/128 resource failover | `exp/golden-q2-128-resource-failover-sep18` `618c592` | no |
| Pristine resource carrier isolation | `exp/pristine-resource-carrier-isolation-sep19` `618c592` | no |
| Golden pretouch A/B (control vs pretouch) | `exp/pretouch-ab-*` (dirs GONE) | no |
| Golden sickness native preadv timer | `exp/golden-sickness-native` `d8b4a13` | no |
| Golden restore lifecycle + H100 Sep14 C0 profile | `d9504d16` → `d95e4347` | no |
| Golden I/O process v2 | `exp/golden-io-process-v2` `b6ecd06` | no |
| golden-best-001/002/003 archival | tags + branches | no |
| v2ctl canonical control plane | `tools/v2_control/*` | **YES** |

---

## 8. Demonstrated failures / rejections

### Source-I/O (PROVEN, recorded in `SOURCE_IO_EXPERIMENT_LEDGER.md` + reports)
| rejected experiment | result | must not resurrect |
|---|---|---|
| `MAP_SHARED` | **−12.1% matched throughput**, worse tails | **yes** |
| deferred munmap (bounded reaper thread) | munmap cost **relocated into `MAP_FIXED`, not removed**; `op_wall` unchanged | **yes** |
| CPU affinity (per-reader pin) | median unchanged (−0.3%/−1.7%); **matched-region op tail slightly worse** | **yes** |
| fixed-VA window replacement | safe, preserves fresh-window, but **cost-neutral** | **yes** |
| 0 ms pacing | loses ~10–12% median, worst tail | **yes** |
| 2 ms pacing | no advantage over 4 ms | **yes** |
| `MAP_POPULATE` | accepted but does not materialize | **yes** |
| `MADV_WILLNEED` / `readahead` / `mincore` | inert / EINVAL / meaningless under gVisor | **yes** |
| greedy allocator | ~12–14% worse than static | **yes** |
| toucher T0/T1/T2 | −32.6% / −29.8% median | **yes** |
| M0-as-rescue | 0 meaningful escapes in 53 events | **yes** |
| zero-copy D2 full-byte consumer | −16.6% vs M0 memcpy | **yes** |
| split rescue (2×64 / 4×32) | does not escape | **yes** |
| prearmed O_DIRECT rescue | does not escape | **yes** |

### Golden-side corrections (from the report set; chronology preserved)
- `GOLDEN_SICKNESS_FORENSIC_REPORT_2026-09-17.md` → superseded in part by
  `diag/golden-sickness-final-causal-closure-sep18` whose commit `7a7410d` explicitly states
  *"analyser now reports skipped cohorts (22 zero-byte, 5 non-tri) instead of dropping them
  silently; stale 127-request reference corrected; original Q3 paragraph marked superseded"*.
  **This is a documented case of a later experiment correcting an earlier conclusion.**
- `SEP14_GOLDEN_RESTORE_AUDIT_2026-09-17.md`, `H100_GOLDEN_PATH_AUDIT_REPORT_2026-09-17.md`,
  `H100_VS_RTX_GOLDEN_FORENSICS_REPORT_2026-09-17.md` are the Sep-17 audit trio.

---

## 9. Successful changes that may currently be missing

**13 of the 19 identified successes are absent from `TESTING2`** — all Golden-side (see the
second table in §7). The most material:

1. **Golden restore lifecycle finalization + H100 Sep14 C0 profile** (`d9504d16` → `d95e4347`)
   — the anchor pair; only on `diag/c0-arm1-join`, the `exp/*` branches and the archival tags.
2. **CUDA source causality pair** (`d642e97`, `a7b62e6`) — the Sep-20 frontier; reachable only
   from the two `sep20` worktrees.
3. **Golden Q2/128 resource failover / pristine carrier isolation** (`618c592`).
4. **Golden P4-8 durability** (`e5eb5ec`) — note this is an **August-named** branch (`omos/`)
   whose HEAD is a September commit.
5. **golden-best-001/002/003 archival** — the only byte-exact RTX PRO 6000 15x15 source/config
   records; tags + branches only.

**Risk of loss:** these live in the shared object store, so they survive as long as no `git gc
--prune` runs and the branches are not deleted. They are **not** on GitHub, so a machine loss
loses them entirely. The 3 prunable worktrees already lost their working directories.

---

## 10. Local-only work

**All 277 September commits are LOCAL ONLY.** 183 of them are reachable *only* from non-`TESTING2`
local branches/worktrees. No September commit exists on any GitHub ref.

## 11. GitHub-only work

**None.** The mirror's newest commit is `02f1845` (2026-08-30). No GitHub-only September work
exists.

## 12. Unreachable / dangling September work

`git fsck --unreachable` (read-only; **no gc was run**) reports **100 unreachable commits, 99 of
them September-dated**. They are overwhelmingly **`git stash` objects** — subjects of the form
`WIP on <branch>`, `index on <branch>`, `untracked files on <branch>`, and `On <branch>: <msg>`.
Representative entries:

| SHA | date | subject |
|---|---|---|
| `bd8042fe` | 2026-09-19 | WIP on exp/golden-q2-128-resource-failover-sep18: 618c592 … |
| `b5016613` | 2026-09-13 | index on exp/golden-io-process-v2: 2d206a3 docs: reconcile C0 old and new cohorts |
| `958258f5` | 2026-09-13 | WIP on exp/golden-io-process-v2: 2d206a3 … |
| `30056b35` | 2026-09-12 | On TESTING2: test-reconciliation-WIP3 |
| `cc85bc4a` | 2026-09-10 | index on TESTING2: 5a67a33 bundle |
| `678e9ff5` | 2026-09-15 | On exp/odirect-shadow-sep14: odirect-shadow-wip-verify |
| `5e25cf01` | 2026-09-18 | On diag/golden-sickness-final-causal-closure-sep18: tri-fix-temp |
| `b51570e5` | 2026-09-15 | untracked files on exp/odirect-shadow-sep14: 3fabd9e reconstruct Sep 14 deployed Golden bytes |

Also **`refs/stash` itself points at a September commit** `2b1e847` (2026-09-12,
`On r42-golden-reconciliation: cleanup 2026-09-12: preserve comfyui-mod…`).

**Significance:** `exp/odirect-shadow-sep14` and the `pretouch-ab-*` worktrees have **both** lost
their directories **and** left WIP/stash residue — so their in-progress work survives **only** as
unreachable objects. `b51570e5` ("reconstruct Sep 14 deployed Golden bytes") is the kind of
artifact that would be irrecoverable after a gc.

**603 reflog entries** reference September dates across all refs.

## 13. Dirty / uncommitted worktrees

**24 of the 46 on-disk worktrees are dirty.** Largest:

| worktree branch | dirty | untracked | path |
|---|---:|---:|---|
| `exp/golden-io-process-v2` | 460 | 443 | `.slim/worktrees/golden-io-v2` |
| `diag/golden-sickness-final-causal-closure-sep18` | 402 | 402 | `.slim/worktrees/golden-sickness-final-causal-closure-sep18` |
| `exp/pristine-resource-carrier-isolation-sep19` | 207 | 195 | `.slim/worktrees/pristine-resource-carrier-isolation-sep19` |
| `exp/resource-local-carryover-sep14` | 148 | 148 | `.slim/worktrees/resource-local-carryover-sep14` |
| `exp/golden-q2-128-resource-failover-sep18` | 152 | 112 | `.slim/worktrees/golden-q2-128-resource-failover-sep18` |
| `.slim/worktrees/golden-sep14-repro` (detached) | 158 | 150 | (at `03ce2491`) |
| `diag/c0-arm1-join` | 124 | 123 | `.slim/worktrees/authoritative-golden-core-sep14` |
| `TESTING2` (main) | 123 | 110 | repo root |
| `exp/golden-minimal-io` | 37 | 37 | `.config/superpowers/worktrees/...` |
| `exp/cuda-vs-no-cuda-source-causality-sep20` | 29 | 29 | `.slim/worktrees/...` |
| `bench/aws-rtx6000-8runs` | 22 | 4 | `custom_nodes_excluded_C9_2026-08-14/...` |

Remaining dirty worktrees (each ≤25 changes): `exp/golden-sickness-native` (2), `exp/runtime-snapshot-shape` (2),
`experiment-axis-repeated-fields` (2), `agent4-v2-loader-diagnostic` (1), `omos/rx3-clip-forward` (1),
`cold-start-wall-clock-opt-20260606` (7), `exp/pagesfile-probe-ca1f114` (23),
`exp/east1-snapshot-composition` (18), `comfyui-modal-sub13-diagnostic` (25, detached),
`comfyui-modal-dc8` (4, detached), `exp/cpu-snapshot-restore-structure` (10),
`exp/cuda-event-per-transfer-causality-sep20` (12), `omos/golden-p4-8-durability` (24).

**Nothing was modified in any dirty worktree.**

## 14. Current-main vs Golden vs major branches

| ref | HEAD | date | September commits reachable | notes |
|---|---|---:|---:|---|
| `TESTING2` (current) | `711f7cf` → `b9196ac` | 2026-09-24 | **94** | the only branch with the source-race harness committed |
| `main` (local) | `f8f2da5` | **2026-08-09** | **0** | an August commit; 17 ahead of origin/main |
| `origin/main` | `25b8562` | 2026-08-05 | 0 | GitHub's main is older still |
| `origin/TESTING2` | `02f1845` | 2026-08-30 | 0 | last pushed state |
| `exp/cuda-vs-no-cuda-source-causality-sep20` | `a7b62e6` | 2026-09-20 | **193** | most complete September history |
| `exp/cuda-event-per-transfer-causality-sep20` | `d642e97` | 2026-09-20 | 187 | |
| `exp/golden-q2-128-resource-failover-sep18` | `618c592` | 2026-09-19 | 185 | |
| `exp/pristine-resource-carrier-isolation-sep19` | `618c592` | 2026-09-19 | 185 | same SHA as above |
| `diag/golden-sickness-final-causal-closure-sep18` | `7a7410d` | 2026-09-18 | 179 | |
| `diag/c0-arm1-join` | `ae4c8db` | 2026-09-18 | 161 | contains the anchor `03ce2491` |
| `golden-best-003-archival` | `f7e6282` | 2026-09-18 | 155 | |
| `exp/golden-io-process-v2` | `b6ecd06` | 2026-09-14 | 142 | |
| `golden-best-001/002-archival` | `b75e88c` / `0c5f3f0` | — | — | RTX 15x15 archival |

**`main` is not a viable September base — it contains zero September commits.** The September
history is concentrated on `TESTING2` (94) and the `exp/*`/`diag/*` worktrees (up to 193).

## 15. Candidate starting-point commits — FACTUAL ONLY

Listed, **not ranked, not recommended**. What each contains is stated from verified evidence.

| candidate | date | September commits reachable | what it contains | on GitHub? |
|---|---|---:|---|---|
| `711f7cf` (TESTING2 tip before §18) | 2026-09-17 | 94 | Golden RX6B + RX7A integration; no source-race harness | no |
| `b9196ac` (TESTING2 tip after §18) | 2026-09-24 | 95 | as above **+ the full source-race harness** | no |
| `a7b62e6` | 2026-09-20 | **193** | CUDA-vs-no-CUDA source causality analysis; broadest September reach | no |
| `d642e97` | 2026-09-20 | 187 | CUDA event per-transfer causality | no |
| `618c592` | 2026-09-19 | 185 | Q2/128 resource failover + pristine carrier isolation forensics | no |
| `7a7410d` | 2026-09-18 | 179 | Golden sickness final causal closure (corrected report) | no |
| `ae4c8db` | 2026-09-18 | 161 | authoritative Golden core Sep14 + C0 arm1 join | no |
| `f7e6282` | 2026-09-18 | 155 | golden-best-003 provenance record | no |
| `334fc5e` | 2026-09-14 | — | `omos/authoritative-golden-core-sep14` snapshot-manifest projection | no |
| `03ce2491` (ANCHOR) | 2026-09-14 | — | C0 teardown bound; dir prunable, branch intact | no |
| `d9504d16` (ANCHOR) | 2026-09-17 | — | Golden restore lifecycle finalization | no |
| `d95e4347` (ANCHOR) | 2026-09-17 | — | H100 Sep14 C0 profile (child of `d9504d16`) | no |
| `f8f2da5` (local `main`) | 2026-08-09 | **0** | August TWO-LANE production candidate | no |
| `25b8562` (`origin/main`) | 2026-08-05 | 0 | oldest; GitHub's main | **yes** |
| `02f1845` (`origin/TESTING2`) | 2026-08-30 | 0 | last pushed TESTING2 | **yes** |

## 16. Uncertainties / missing artifacts

1. **No result artifacts were re-verified remotely** — all September runs were local; the
   GitHub mirror contains none of them.
2. **The 3 prunable worktree directories are gone** (`odirect-shadow-sep14`,
   `pretouch-ab-control-sep14`, `pretouch-ab-pretouch-sep14`). Their branches and commits survive,
   but any *untracked* artifacts inside those directories are lost. Whether such artifacts existed
   is **UNKNOWN**.
3. **`exp/pretouch-ab-control-sep14`'s HEAD is anchor `03ce2491`** and its directory is gone —
   so the anchor's worktree context (untracked files, run outputs) is unrecoverable.
4. **99 unreachable September stash/WIP objects** exist. Their content was enumerated by subject
   only; the full diffs were **not** exhaustively read. Whether any contains unique work is
   **UNKNOWN**.
5. **Independent clones: none found**, but the search covered `C:\Users\parla` to depth ~6–7 with
   standard exclusions. A clone outside that root would be missed — **UNKNOWN**, low risk.
6. **Author/committer dates are identical for all 277 reachable September commits**, so no
   reachable rebase skew exists; stash objects were not date-analysed in depth.
7. **The optimization table's "present in Golden baseline?" column is largely UNKNOWN** — the
   current Golden baseline commit was not identified with certainty, so presence there could not
   be proven either way.
8. **`refs/stash` holds a September entry** (`2b1e847`); its full content was not read.
9. Whether the `custom_nodes_excluded_C9_2026-08-14/` worktrees are still *intended* to be
   excluded from the live install is **UNKNOWN**.

## 17. Paths to supporting reports / artifacts

- **This audit**: `SEPTEMBER_FORENSIC_AUDIT.md`
- **CSVs**: `september_commits.csv`, `september_worktrees.csv`, `september_optimizations.csv`
- **Source-I/O ledger + reports**: `SOURCE_IO_EXPERIMENT_LEDGER.md`, `SOURCE_IO_LEDGER.md`,
  `SOURCE_IO_TASKS_1_5_REPORT.md`, `MMAP_SOURCE_IO_REPORT.md`, `PHASE0_MMAP_CAPABILITY_AUDIT.md`,
  `TASK1_MEMORY_LAYOUT.md`, `MATRIX_REPORT.md`, `SIZE_SWEEP_REPORT.md`, `P_VS_M2_REPORT.md`,
  `ABC_MMAP_LIFECYCLE_REPORT.md`, `FOUR_EXPERIMENT_REPORT.md`, `PHASE12_REPORT.md`,
  `FINAL_MAPSHARE_CPU_REPORT.md`, `FINAL_MMAP_OPTS_REPORT.md`, `RTX_BEST_REPORT.md`
- **Golden Sep-17 audit trio**: `GOLDEN_SICKNESS_FORENSIC_REPORT_2026-09-17.md`,
  `H100_GOLDEN_PATH_AUDIT_REPORT_2026-09-17.md`, `H100_VS_RTX_GOLDEN_FORENSICS_REPORT_2026-09-17.md`,
  `SEP14_GOLDEN_RESTORE_AUDIT_2026-09-17.md`
- **Golden evidence docs**: `EXPERIMENT_EVIDENCE_golden_p1_0f0a5182dd94440e_2026-09-17.md`,
  `EXPERIMENT_EVIDENCE_golden_p1_131d82cd72d74b49_2026-09-17.md`
- **Per-worktree report sets**: present in most `.slim/worktrees/*` (25 report-ish files each),
  incl. `CHATGPT_ARCHAEOLOGY_AUDIT.md`, `AGENT_HANDOFF_SEP14_GOLDEN_MINIMAL_RESTORE.md`,
  `reports/golden_sickness_final_causal_closure_2026-09-18/FINAL_CAUSAL_CLOSURE.md`
- **Temp audit working files** (outside the repo, non-authoritative):
  `%LOCALAPPDATA%\Temp\opencode\{enum_september,commit_details,worktree_scan,worktree_details,build_artifacts}.py`
  and `september_commits_raw.json`, `september_commit_details.json`
- **Remote mirror** (temp, read-only): `%LOCALAPPDATA%\Temp\opencode\comfyui-modal-mirror.git`

---

## 18. The one mutation in this session (explicitly requested)

After the audit data was gathered, the user asked to *"commit our prize working implementation
for the source read"*. This was performed surgically:

| item | value |
|---|---|
| commit | **`b9196ac50897430af690d570242157f80bbc1100`** |
| date | 2026-09-24 01:45:43 -0500 |
| files | **81** (added) |
| branch | `TESTING2` (now ahead **111** of `origin/TESTING2`) |
| contents | `comfymodal_runtime/source_race_oracle.py`, `e04_source_race_modal.py`, `source_touch.c`, `native_canary.c`, `config/v2/profiles/source_race_{h100,rtx}.toml`, 3 source-race tests, all `tools/*.py` source-race tooling, the `SOURCE_IO_*` ledgers and the full source-read report set |
| **Golden runtime files touched** | **none** (verified: no `golden_serial.py` / `modal_app.py` / `comfyapp.py` / `dependency_resolver.py` in the commit) |
| secrets | `.modal_workspaces.json.bak-sourcerace` (holds live tokens for 7 workspaces) was **explicitly excluded** and remains untracked |
| left unstaged | the 13 pre-existing modified tracked files (`golden_serial.py`, `modal_app.py`, `config/v2/modal_target.toml`, `dependency_resolver.py`, web/test files) |

This commit is a **new fact** introduced during the audit; it is the only change to repository
state. Everything in §1–§17 is read-only observation.

---

*End of audit. No base-commit recommendation is made — §15 lists candidates factually only.*
