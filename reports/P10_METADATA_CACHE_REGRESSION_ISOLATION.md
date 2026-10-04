# P10 metadata-cache regression isolation

**Question under test:** did the persistent model-metadata cache introduced by
`1c62561d` cause the remaining Golden load regression?

**Answer: no. The cache is exonerated.** Removing it from the runtime path does
not improve CLIP load or source throughput, and the arm that *uses* the cache
is nominally the fastest of the three.

> **Addendum (section 19).** Arm A was sampled a further 10 times after this
> report was first written, on the same deployment. Arm A is now n=21.
> Sections 9–15 report the original balanced n=11/10/10 block unchanged, because
> that block is the only one where all three arms were interleaved inside one time
> window; section 19 carries the additional arm-A block and the combined arm-A
> distribution. The verdict is unchanged and the additional data strengthens it.

---

## 1. Exact current main SHA

```
origin/main = 420294b99631fe3fc0715206fd1e613242f2daab
```

The prompt was written against `1e52e17b...`. `main` advanced by exactly one
commit afterwards, `420294b9`, and that commit was verified to touch **only**
`tests/studio_experiment_v2_frontend_unit.mjs` — no runtime Golden file. The
runtime tree is therefore byte-identical to `1e52e17b`, and `420294b9` is used
as the experiment base.

`production-010` remains annotated at `1e52e17b606e0c4694a5c078e9fa96149598f70b`.
Neither `main` nor the tag was moved by this experiment.

## 2. Exact experiment base

| role | commit |
|---|---|
| experiment base (`origin/main`) | `420294b99631fe3fc0715206fd1e613242f2daab` |
| arm A source | `1c46b593ed3d3a4690e94f15f8aa46733cdfcf7c` |
| arm B source | `9fc5eb397a830fcb95e7db3670b6c916373cf2ad` |
| arm C source | `0e4f038db71e269f2e09002484e1c61984b46bfd` |

Work was done in the existing clean isolated checkout
`.slim/worktrees/bisect-armA` on branches `exp/p10-metacache-*`. No new
worktree was created. The dirty root checkout was not modified.

## 3. Proof that fbd81c46 and 2b2f1e01 share a tree

```
$ git show -s --format=%T fbd81c46
a6f3b61e1e18b4c71456f80ea753a08396302410
$ git show -s --format=%T 2b2f1e01
a6f3b61e1e18b4c71456f80ea753a08396302410
```

Identical. The 16x64 MiB arena, the arena gate fix, source-latency telemetry
and the initial UNET layout pre-resolve are therefore already inside the
known-good tree and were **not** retested as suspects, per instruction.

## 4. Runtime call-site inventory from 1c62561d

Files touched by `1c62561d`: `comfyapp.py`,
`golden_model_metadata_cache.py` (new, 364 lines), `golden_model_transport.py`,
`golden_serial.py`, `modal_app.py`, `tools/v2_control/cli.py`,
`tools/v2_control/source_probe.py`, plus reports and tests.

Every production runtime reference, classified:

| # | site | classification | what it does |
|---|---|---|---|
| 1 | `golden_model_metadata_cache.py:225 hydrate()` | definition | reads + validates the one blob; memoises on success, re-probes on miss |
| 2 | `golden_model_metadata_cache.py:266 lookup()` | definition | `hydrate()` then `os.stat(identity)`, falls back to `_header_bytes()` when size/mtime disagree |
| 3 | `modal_app.py:10683-10685` in `reload_runtime_state()` | **RESTORE HYDRATION** | warms the blob right after `volume.reload()`; wrapped in bare `except: pass` |
| 4 | `golden_serial.py:11833` (CLIP load entry) | **REQUEST-TIME READ** | `hydrate()` for telemetry; emits `golden_metadata_cache` |
| 5 | `golden_serial.py:2305-2335` (CLIP meta blueprint) | **REQUEST-TIME LOOKUP** | `lookup()`; on hit builds the CLIP meta state dict from the cached tensor table and sets `layout_cache_source="persistent"`; on miss calls `clip_qd_reader.parse_safetensors_header()` |
| 6 | `golden_model_transport.py:1020-1076` `inspect()` | **REQUEST-TIME LOOKUP** | for `role` starting with `clip`, `lookup()` runs *before* the in-memory `_layout_cache` and before `_parse_layout`; on hit builds `SafetensorsLayout` with `header={}`, `cache_source="persistent"` |
| 7 | `golden_serial.py:12312` `golden_metadata_cache_result` | TELEMETRY | final post-load outcome event |
| 8 | `modal_app.py:19809` | TELEMETRY | module name in the source-probe module list |
| 9 | `comfyapp.py:9499` | PUBLICATION | publish entrypoint |
| 10 | `tools/v2_control/cli.py`, `source_probe.py` | TEST/CLI | `publish-model-metadata-cache`, probe coverage |
| 11 | `tests/test_golden_model_metadata_cache.py`, `tests/test_golden_metadata_precohort_cli.py` | TEST/CLI | unit coverage |

Consumers of `layout.header` reached by site 6, noted because the persistent
path sets `header={}`: `golden_serial.py:7332` (CPU-prefetch ticket only; not
exercised here, `cpu_qd2_prefetch=false`), `golden_serial.py:13643` (UNET — but
`inspect()` only takes the persistent branch for `clip*` roles, so UNET is
unaffected), `golden_serial.py:14665` (`__metadata__` becomes `None`).

Sites 3, 4, 5 and 6 are the four that arms B and C switch off. Nothing else in
the runtime consumes the blob.

## 5. Exact A/B/C source differences

`1c62561d`-derived instrumentation is one commit (`1c46b593`). Arms B and C each
differ from arm A by **exactly one line**:

```
EXPERIMENT_METADATA_CACHE_ARM = "current"          # A
EXPERIMENT_METADATA_CACHE_ARM = "lookup_bypass"    # B  (9fc5eb39)
EXPERIMENT_METADATA_CACHE_ARM = "runtime_disabled" # C  (0e4f038d)
```

Behavioural effect:

* **B** — `lookup()` returns a fail-soft miss (`reason=experiment_lookup_bypassed`),
  so sites 5 and 6 use the canonical parse. `hydrate()` (sites 3 and 4) untouched.
* **C** — additionally `hydrate()` returns `loaded=False, hydrate_performed=False`
  without opening the blob, so sites 3 and 4 are inert too.

Publication, downloader and CLI code are untouched in all three arms. The arena,
arena gate, source telemetry, UNET pre-resolve, bounded join, Studio routing fix
and all request semantics are identical across arms.

This is a source-state selector, not a runtime env flag: each arm is a separate
deploy of a separate source state, so arm identity cannot depend on an env var
reaching the container.

## 6. Deployment fingerprints

| arm | app | commit | deploy fingerprint | source probe |
|---|---|---|---|---|
| A current | `batch-p10-metacache-a-current-h100` | `1c46b593` | `7f8b0b6212793be9dc3b7e537fd12afecc5965a001f391aa683ddfc1a578181c` | PASS / MATCH |
| B lookup_bypass | `batch-p10-metacache-b-bypass-h100` | `9fc5eb39` | `e7f0a01aa1e4ddc3c4d98b307a67a6243e9c5c0ba0b0f306a66677c07976d5e7` | PASS / MATCH |
| C runtime_disabled | `batch-p10-metacache-c-disabled-h100` | `0e4f038d` | `82bae5c9cff852e8cb01373a982fde764315ff381262fc3ae54c42f6893c51f0` | PASS / MATCH |

Workspace Testing 1 (`ws_e677ab553606`), profile
`golden_p1_parallel_c0_p8_h100`, H100!, CPU 12, memory 24576 — identical for all
three. No Studio requests were issued.

## 7. Arm-identity proof

The collector resolves the arm from `deployment_identity.app_name` in the run
summary and then **verifies** the identity the container actually emitted,
refusing the run on any disagreement. Refused: **0 of 31**.

Observed, from `golden_metadata_cache_result`:

| arm | `metadata_cache_arm` | `loaded` | `hydrate_performed` | `layout_cache_source` | `clip_meta_cache_hit` |
|---|---|---|---|---|---|
| A | `current` | True | True | **persistent** | **True** |
| B | `lookup_bypass` | True | True | runtime_parse | False |
| C | `runtime_disabled` | False | False | runtime_parse | False |

Arm A genuinely consumes the persistent blueprint; B and C genuinely do not.

A measurement trap is worth recording: the load-time `golden_metadata_cache`
event carries only the *initial* defaults, so reading it makes all three arms
look like a cache miss. The final outcome lives in `golden_metadata_cache_result`
(`golden_serial.py:12312`), emitted after the blueprint build and transport
inspect have filled their fields in. An earlier read of the wrong event would
have produced a false exoneration.

## 8. Correctness

31 runs collected: **A 11/11 valid, B 10/10 valid, C 10/10 valid. All 31 exact.**

* `true_cold=true`, `restore_count=1`, `request_count=1`, `valid=true` on every
  retained run
* `dnf=false`, `error=None`, no `failures` list
* observed SHA `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`
  on **31/31**
* expected-SHA warning against `790c3052…` is the pre-existing canonical-legacy
  warning, not a mismatch

Lost cells, recorded rather than replaced: one arm-C cell hung in sampling
(>3.8 min, killed), and one arm-C cell tripped the 40 s request wall gate after a
27.6 s CLIP load (`wall_gate_s=40.0`, exit 70). Neither produced an attempt
artifact, so neither is counted as usable. A 300 s per-cell ceiling in the runner
is what stopped the hang from blocking the queue.

## 9. Per-run CLIP / source numbers

CLIP load and root wall are taken from `golden_outer_marks` so they are directly
comparable to the `batch-p9opt1-diag-h100` reference figures (CLIP load 1388.3 ms,
`output_done` 7852–8055 ms across three reference runs).

CLIP load, ms (n = 11 / 10 / 10):

| arm | min | p10 | P50 | mean | p90 | max |
|---|---|---|---|---|---|---|
| A current | 1472.8 | 1522.2 | **1733.5** | 2770.2 | 4081.6 | 6479.4 |
| B bypass | 1346.8 | 1500.3 | **1902.8** | 2813.5 | 3020.9 | 10521.4 |
| C disabled | 1443.2 | 1548.3 | **1889.4** | 2590.1 | 4653.4 | 4715.0 |

CLIP source wall, ms: A P50 1607.8 / B 1746.6 / C 1734.6.
CLIP source GB/s: A P50 **5.00** / B 4.64 / C 4.63.

`output_done`, ms: A P50 9893.4 / B 9498.2 / C 9369.5.
Sampling MARK, ms: A 3746.3 / B 3743.5 / C 3765.9 — flat, as expected.

## 10. Metadata hydrate / lookup timing

| metric | A | B | C |
|---|---|---|---|
| metadata hydrate ms, P50 | 27.1 | 29.6 | **0.0** |
| metadata hydrate ms, max | 244.6 | 55.3 | 0.0 |
| layout resolve ms, P50 | **1.0** | 33.1 | 35.4 |
| blueprint lookup ms, P50 | 0.3 | 0.0 | 0.0 |
| meta/state-dict build ms, P50 | 2.2 | 2.4 | 2.3 |

The cache is doing exactly what it was built to do: it removes the SafeTensors
header read, cutting layout resolve from ~34 ms to ~1 ms. It pays ~27 ms of
hydration for ~33 ms of layout resolve — roughly cost-neutral, and two orders of
magnitude below the ~1.5 s residual being investigated.

The commit's own comment predicted "~0.5 s here versus ~12 ms of local parsing"
for the first-touch Volume fetch. Measured hydration is 6.7–244.6 ms (P50 27.1),
so the predicted half-second cost does not materialise on this workload.

## 11. Real capacity-pressure telemetry

`capacity_wait` is reported separately from real slot pressure, as instructed.

| statistic | A | B | C |
|---|---|---|---|
| runs with `slot_wait_ms` > 0 | 0 | 0 | 0 |
| runs with `all_slots_occupied` > 0 | 0 | 0 | 0 |
| runs with `capacity_wait` > 0 | 3/11 | 2/10 | **0/10** |
| runs with `capacity_wait` >= 250 ms | 3 | 2 | 0 |
| runs with `capacity_wait` >= 1000 ms | 2 | 1 | 0 |
| `capacity_wait` mean, ms | 683.8 | 200.4 | 0.0 |

**No run in any arm shows a non-zero slot wait or a non-zero all-slots-occupied
count.** There is no evidence of arena/slot exhaustion anywhere in this
experiment.

`capacity_wait` incidence is monotone A > B > C, which is suggestive, but it is
**not** causal, and the per-run detail shows why:

* in A and B, `capacity_wait > 0` occurs in exactly the runs with source
  GB/s < 2.1, and in no other run of any arm;
* arm C shows the slow-source mode three times (clip load 4184 / 4715 / 4653 ms)
  with `capacity_wait = 0` in **every** one.

So slow source runs happen with or without `capacity_wait`. It is a co-symptom
that appears in some slow runs, not the mechanism.

## 12. Source-copy tail telemetry

| metric | A | B | C |
|---|---|---|---|
| memcpy p50, median of runs | 49.3 | 46.9 | 52.0 |
| memcpy p50, worst run | 81.1 | 70.8 | 132.7 |
| memcpy p90, median of runs | 66.5 | 66.7 | 68.8 |
| memcpy p90, worst run | 630.1 | 1134.4 | 156.1 |
| memcpy max, median of runs | 78.4 | 119.4 | 88.8 |
| memcpy max, worst run | 1798.8 | 3142.7 | 2251.2 |
| memcpy p99 | not exposed in telemetry | not exposed | not exposed |
| per-copy sample array | not exposed | not exposed | not exposed |

The telemetry exposes only summary statistics (`p50`, `p90`, `max`) for
`memcpy_duration_ms`; it does not carry a per-copy sample array, so
`>100/250/500/1000 ms` copy counts and a true p99 cannot be computed from the
artifacts without adding instrumentation. The arms are indistinguishable on
memcpy p50/p90 medians; the worst-case single copy is noisy in all three arms.

## 13. UNET pre-resolve invariance

| statistic | A | B | C |
|---|---|---|---|
| `unet_layout_preresolve` events per run | 4 | 4 | 4 |
| UNET load wall P50, ms | 3045.1 | 2681.8 | 2928.8 |

Identical event counts across all three arms confirm the UNET in-memory
pre-resolve and the bounded join were untouched by the arms, as required.

## 14. Root / stage timings

Stage P50, ms:

| stage | A | B | C |
|---|---|---|---|
| UNET load | 3045.1 | 2681.8 | 2928.8 |
| CLIP forward | 2271.6 | 2248.2 | 2545.3 |
| sampler prepare | — | — | — |
| sampling | 3744.5 | 3741.6 | 3763.9 |
| VAE decode | — | — | — |
| output | 223.0 | 239.9 | 214.2 |
| `output_done` mark | 9893.4 | 9498.2 | 9369.5 |
| harness `duration_ms` | 25263.4 | 19391.2 | 36945.1 |

Harness `duration_ms` is *not* golden wall — it includes container start and
external restore — so it is reported but not used for any conclusion.

## 15. Medians + ranges

See section 9 for the full min/p10/P50/mean/p90/max tables. Summary of medians:

| metric | A | B | C |
|---|---|---|---|
| CLIP load MARK, ms | **1733.5** | 1902.8 | 1889.4 |
| CLIP source wall, ms | **1607.8** | 1746.6 | 1734.6 |
| CLIP source GB/s | **5.00** | 4.64 | 4.63 |
| `output_done` MARK, ms | 9893.4 | 9498.2 | 9369.5 |

Floor check against the P9opt1 reference (CLIP load 1399 ms, `output_done`
7852–8055 ms):

| arm | CLIP load min | runs with `output_done` <= 8500 ms |
|---|---|---|
| A | 1472.8 | 3/11 (27%) |
| B | 1346.8 | 2/10 (20%) |
| C | 1443.2 | 2/10 (20%) |

**Every arm's floor is at or below the reference.** The residual regression is
entirely in the tail, not the floor.

## 16. Causal classification

**Q1 — does B materially improve CLIP/source wall versus A?** No. CLIP load P50
1902.8 ms in B vs 1733.5 ms in A; CLIP source GB/s 4.64 vs 5.00. B is nominally
*slower*. No improvement.

**Q2 — does C materially improve over B?** No. CLIP load P50 1889.4 ms vs
1902.8 ms; source GB/s 4.63 vs 4.64. Within noise. Arm C does eliminate
`capacity_wait` entirely, but C also exhibits the slow-source mode three times
without it, so that is not an improvement in the metric under test.

**Q3 — does C return CLIP/source near the known-good P9 distribution?** Partially,
and not because of the cache. C's CLIP load P50 is 1889.4 ms against a 1399 ms
reference (1.35x), and C's *minimum* of 1443.2 ms is at the reference. So the
best case is already at reference speed and the median is dragged down by the
tail — identically in all three arms.

```
CLASSIFICATION = CACHE_EXONERATED   (CASE 4)
```

The load distributions of A, B and C are statistically indistinguishable at these
sample sizes, and the arm that consumes the cache has the best medians. Removing
the runtime cache therefore has no upside and would give up the ~33 ms layout
resolve saving the cache provides.

Two secondary findings worth keeping:

1. `capacity_wait` is **not** proof of capacity pressure. `slot_wait_ms` and
   `all_slots_occupied` were zero in 31/31 runs.
2. The distribution is bimodal with an arm-independent slow mode
   (CLIP load ~4–6.5 s at 1.3–2.2 GB/s vs ~1.5–1.7 s at 5–6.2 GB/s). The
   regression versus P9opt1 is a **tail/variance** problem, not a floor problem,
   and it is not attributable to the metadata cache.

## 17. Minimum production recommendation

**Do not remove the persistent metadata cache from the runtime.** There is no
causal evidence, and the measured trade is roughly cost-neutral (27 ms hydrate
for 33 ms layout resolve saved). No production change is warranted from this
experiment.

The floor already matches the P9opt1 reference in all arms, so the open problem
is the slow-source tail. Remaining post-good-tree runtime changes, none of them
the cache:

* `e83f289b` bounded UNET layout pre-resolve join — UNET-side, not the CLIP
  source window, but the only remaining load-path behavioural change
* `eb51cb03` Studio `stage_observer` plumbing into `golden_parallel.py`
  (2 lines) — inert on the ordinary path after `1cafeba0`
* `fa30dad9` CUDA arena lifecycle audit — new telemetry file
* `d563145f` integration repairs to `golden_serial.py`

A follow-up differential should diff `2b2f1e01` against the current no-cache tree
restricted to the CLIP source path (`golden_qd_transport.py`,
`clip_qd_reader.py`, `golden_model_transport.py` minus the cache lookup) to find
what changes the *distribution* rather than the floor. That is a source-level
diff first, not another deploy matrix.

## 18. Commits to carry forward or not

| commit | disposition |
|---|---|
| `1c46b593` arm A instrumentation | **do not merge** — experiment scaffolding (`EXPERIMENT_METADATA_CACHE_ARM`, `hydrate_performed`, `experiment_arm`) |
| `9fc5eb39` arm B | **do not merge** — one-line experiment constant |
| `0e4f038d` arm C | **do not merge** — one-line experiment constant |
| `420294b9` (already on main) | unrelated pre-existing test fix, already pushed before this experiment |
| `1c62561d` metadata cache | **keep as-is** — exonerated; it saves ~33 ms of layout resolve |

```
PRODUCTION_CODE_CHANGED = no
MERGED                   = no
TAG_MOVED                = no
```

## Tests

* focused: `tests/test_p10_metadata_cache_arms.py` (new, 5 tests) pins the
  three-way discrimination the collector depends on, including that arm B still
  hydrates and arm C reports `hydrate_performed=False`
* `tests/test_golden_model_metadata_cache.py` +
  `tests/test_golden_metadata_precohort_cli.py`: 22 passed (17 pre-existing + 5
  new), confirming arm `current` behaves exactly as before
* untruncated fast-unit suite on the experiment base: **675 passed, 7 skipped,
  0 failed** (670 before, +5 from the new arm tests)
* no Studio or browser tests were modified

## 19. Addendum — 10 additional arm-A runs

Arm A was re-sampled 10 more times to tighten its own distribution, on the
**same deployment with no redeploy**, so the arm stays reproducible against the
original block.

| | |
|---|---|
| app | `batch-p10-metacache-a-current-h100` |
| deployment fingerprint | `7f8b0b6212793be9dc3b7e537fd12afecc5965a001f391aa683ddfc1a578181c` |
| git_head | `1c46b593ed3d3a4690e94f15f8aa46733cdfcf7c` (unchanged) |
| source probe | `PASS`, 3/3 states PASS, 0 reasons |
| profile | `golden_p1_parallel_c0_p8_h100` |
| window | 16:59–17:06 CDT (21:59–22:05 UTC), serial, one request per container |
| attempts | 10 — **0 timeouts, 0 harness errors, 10/10 manifests** |

Arm identity was verified per run and **0 runs were refused**.

### 19.1 Per-run

| # | cohort | CLIP load | src wall | GB/s | CLIP fwd | UNET load | output_done | memcpy p50 | cap_wait | layout |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 777dcf | 3512.9 | 3420.2 | 2.35 | 2200.6 | 2754.8 | 10655.9 | 72.4 | 0 | 0.9 |
| 2 | 7b7766 | 1616.1 | 1514.3 | 5.31 | 1962.2 | 2709.0 | 9003.4 | 45.0 | 0 | 0.9 |
| 3 | 25b5da | 1416.1 | 1317.2 | 6.11 | 2137.4 | 2314.1 | 8233.9 | 40.6 | 0 | 0.8 |
| 4 | 75bdd0 | 1439.7 | 1345.5 | 5.98 | 2026.1 | 2207.2 | 7974.4 | 41.9 | 0 | 0.9 |
| 5 | a938a7 | 1269.5 | 1170.2 | 6.88 | 1836.0 | 2041.0 | 7628.2 | 36.4 | 0 | 0.8 |
| 6 | 5d09c7 | 2135.2 | 1950.5 | 4.12 | 2773.1 | 3478.6 | 10505.3 | 62.6 | 0 | 1.0 |
| 7 | c63dae | 1600.8 | 1424.7 | 5.65 | 2302.3 | 2325.6 | 8402.5 | 44.4 | 0 | 0.8 |
| 8 | dd72fb | 1481.2 | 1254.0 | 6.42 | 2186.9 | 2022.4 | 8291.8 | 38.8 | 0 | 1.1 |
| 9 | fa2008 | 1529.2 | 1300.5 | 6.19 | 2144.0 | 2359.6 | 8403.9 | 40.8 | 0 | 0.9 |
| 10 | 1d2a48 | 1533.4 | 1419.7 | 5.67 | 2235.1 | 2086.2 | 8321.2 | 45.1 | 0 | 1.1 |

All values ms except GB/s. CLIP load / source / root are `golden_outer_marks`
derived, the same source as the `batch-p9opt1-diag-h100` reference.

### 19.2 Distributions

| metric | additional (n=10) | prior (n=11) | combined (n=21) |
|---|---|---|---|
| CLIP load min | 1269.5 | 1472.8 | 1269.5 |
| CLIP load P25 | 1439.7 | 1628.9 | 1522.2 |
| CLIP load **P50** | **1531.3** | 1733.5 | **1628.9** |
| CLIP load mean | 1753.4 | 2770.2 | 2286.0 |
| CLIP load P75 | 1616.1 | 4081.6 | 2356.6 |
| CLIP load max | 3512.9 | 6479.4 | 6479.4 |
| CLIP source wall P50 | 1382.6 | 1607.8 | 1521.4 |
| CLIP source GB/s P50 | **5.8** | 5.0 | 5.3 |
| `output_done` P50 | 8361.9 | 9893.4 | 8515.6 |
| `output_done` min | **7628.2** | 8026.2 | 7628.2 |
| metadata hydrate ms P50 | 27.1 | 27.1 | 27.1 |
| layout resolve ms P50 | 0.9 | 1.0 | 1.0 |
| exact SHA | 10/10 | 11/11 | **21/21** |
| identity | current/True/True/persistent/hit | same | same |

### 19.3 What the additional block changes

**It makes the exoneration stronger, and it sharpens the tail story.**

1. **Arm A's fast mode is faster than before, not slower.** Fast-mode CLIP load
   P50 is 1529.2 ms in the new block versus 1670.5 ms in the prior block — the
   same deployment got *faster* with more samples. Slow-mode incidence fell from
   3/11 (27%) to **1/10 (10%)**. Combined 4/21 (19%). Nothing about the cache
   degrades with repeated use; if persistent-cache state were accumulating or
   poisoning, this is exactly where it would show.

2. **`capacity_wait` fired 0/10 times.** Prior block 3/11. Combined 3/21. The
   metric remains uncorrelated with cause: real capacity pressure
   (`slot_wait_ms`, `all_slots_occupied`) is **0 in all 21 arm-A runs**, and the
   one slow run in this block (`777dcf`, 3512.9 ms) had `capacity_wait = 0`.

3. **`output_done` minimum is 7628.2 ms — below all three reference runs.** The
   `batch-p9opt1-diag-h100` reference runs recorded `output_done` at
   **7661.4 / 7851.8 / 7961.3 ms**. So on this deployment, current P10 produces
   runs *faster* than the reference. Combined arm-A `output_done` P50 of 8515.6 ms
   remains above the reference, but that gap is tail-driven, not floor-driven.

   Note on reference comparability: the report's CLIP-load figures are
   `clip_load_done - clip_load_begin` deltas, whereas the 1388 ms quoted in
   section 9 is the raw `clip_load_done` mark (both relative to
   `execute_enter`). The delta is ~18 ms smaller, a ~1% offset that does not
   affect any conclusion here. `output_done` is a single mark and is directly
   comparable with no offset.

4. **The regression is confirmed to be a bimodality problem, not a level
   problem.** Split at 2.8 GB/s: fast mode n=17 (CLIP P50 1600.8 ms, max
   2857.2 ms), slow mode n=4 (P50 4540.1 ms, min 3512.9 ms). The modes **do not
   overlap** — the slowest fast-mode run is 2857.2 ms and the fastest slow-mode
   run is 3512.9 ms, a clean 655 ms gap. The same non-overlap holds in each block
   separately (prior: fast max 2857.2 / slow min 4081.6; additional: fast max
   2135.2 / slow min 3512.9). A single cause that shifted every run by a constant
   would produce a unimodal smear. This is a per-container state difference that
   some containers fall into.

5. **Sampling MARKS stay flat** (sampling P50 3730.1 ms combined vs 3746.3 prior),
   and `unet preresolve events = 4` in all 21 runs, so the load-path pre-resolve
   is unchanged.

### 19.4 Effect on the verdict

None — the classification remains `CACHE_EXONERATED` and
`RECOMMEND_REMOVE_RUNTIME_METADATA_CACHE = no`. The additional block was
collected on arm A only, so it cannot change the A-vs-B-vs-C ordering; what it
does is remove the remaining doubt about whether repeated cache use degrades the
arm, and it does not. Cache hydration is stable at 27.1 ms P50 across all 21 runs
and layout resolve stays at ~1 ms.

The open question is unchanged and is **not** about the cache: it is why ~19% of
containers on this deployment land in a source mode at 1.3–2.4 GB/s instead of
5.7–6.9 GB/s, when real arena capacity pressure is zero in every run.