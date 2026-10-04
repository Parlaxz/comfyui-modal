# P9 source prefetch / population experiment (arms A, A2, A3)

## 1. Answer

**`CLASSIFICATION=INCONCLUSIVE_CURRENT_COHORT`**

Neither `POSIX_FADV_WILLNEED` nor `MAP_POPULATE` removed the mapped-source copy
stall, and the setup-cost evidence says why: **on this platform both mechanisms
are accepted by the ABI and then do nothing.** They are not weak treatments that
lost a statistical race. They are inert.

The interesting part of this experiment is not the null result. It is that the
null result is *explained* by a directly measured quantity rather than left as a
hypothesis, and that the pooled decision rule would have reported a **false
positive** had it been allowed to stand alone.

| arm | treatment | containers | copies | p50 ms | p90 ms | p99 ms | max ms | >100 ms | >250 ms | >1 s | pooled verdict | sick containers |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--|--:|
| A | none (control) | 5 | 1280 | 44.68 | 58.24 | 246.07 | 2040.95 | 18 (1.41%) | 12 | 6 | pathological | **1 / 5** |
| A2 | `posix_fadvise(WILLNEED)` | 5 | 1280 | 41.69 | 66.26 | 296.39 | 1256.21 | 22 (1.72%) | 14 | 1 | pathological | **2 / 5** |
| A3 | `MAP_POPULATE` | 5 | 1280 | 45.10 | 66.59 | 96.11 | 2103.20 | 12 (0.94%) | 6 | 2 | not pathological | **2 / 5** |

All three rows are the same deployment (`9537b199…`), so this is one code state
compared against itself.

## 2. Why the classification is not `BACKING_POPULATION_CONFIRMED`

Apply the pre-registered rule on its own — pathological iff ≥1% of copies exceed
100 ms **and** p99 ≥ 100 ms, over ≥2 containers — and A3 fails it on both counts:

```
A3  over_100ms_fraction = 0.94%   (floor 1.00%)
A3  p99                 = 96.11 ms (floor 100.00 ms)
```

That produces `BACKING_POPULATION_CONFIRMED`, and it is wrong. Per container, A3
is:

| A3 container | p50 ms | p99 ms | max ms | >100 ms | >250 ms | >1 s |
|:--|--:|--:|--:|--:|--:|--:|
| `golden-p1-0-b0dee210fa82` | 50.72 | 60.42 | 82.80 | 0 | 0 | 0 |
| `golden-p1-0-eaefe6c765be` | 34.66 | 73.85 | 85.67 | 0 | 0 | 0 |
| `golden-p1-0-ca0cdb781f85` | 46.69 | 59.74 | 74.71 | 0 | 0 | 0 |
| `golden-p1-0-30b5d62fe086` | 42.15 | 84.64 | 484.81 | 2 | 1 | 0 |
| `golden-p1-0-d76e47d8e4e8` | 62.97 | 864.86 | **2103.20** | 10 | 5 | **2** |

The MAP_POPULATE arm still contains a 2.1-second copy — worse than the control's
2.04 s — and one container in five goes pathological on **every** arm including
the control. Pooling four healthy containers with one catastrophic one dilutes
the sick container below any threshold. That is a property of the pooling, not
evidence about the treatment.

`tools/source_copy_isolation_report.py` therefore now requires a treatment arm to
contain **zero** pathological containers before it is credited, and reports the
disagreement explicitly:

```json
"population_decision": {
  "classification": "INCONCLUSIVE_CURRENT_COHORT",
  "reasons": ["pooled_thresholds_and_per_container_evidence_disagree",
              "control_spans_multiple_deployments"],
  "pooled_healthy_treatment_arms": ["A3"],
  "healthy_treatment_arms": [],
  "pathological_containers": {"A": 1, "A2": 2, "A3": 2}
}
```

This is the second time in this lane that a pooled summary has hidden a real
failure, the first being the fifteen wrong containers in the A/B/C/D phase.

## 3. Why both treatments are inert here — the measured explanation

The arm payload records the wall time of each treatment call, against a mapping
of `12309866400` bytes (12.31 GB):

| arm | call | wall p50 | wall max | implied throughput for 12.31 GB | n |
|:--|:--|--:|--:|--:|--:|
| A | `mmap(MAP_PRIVATE)` | 0.410 ms | 0.539 ms | 30 GB/s | 5 |
| A2 | `posix_fadvise(WILLNEED)` | **0.040 ms** | 0.075 ms | **308 GB/s** | 5 |
| A3 | `mmap(MAP_PRIVATE｜MAP_POPULATE)` | **0.774 ms** | 1.733 ms | **16 GB/s** | 5 |

Reading 12.31 GB takes at least ~1.2 s. Neither treatment call came close.

* **A2 is a guaranteed no-op by specification.** `POSIX_FADV_WILLNEED` is
  advisory and non-blocking; it is permitted to return before any I/O is done,
  and 40 microseconds is what returning without doing anything looks like. A2 was
  never a candidate treatment for a synchronous stall, which is exactly what the
  result shows. This arm's value is negative: it forecloses the whole advisory
  prefetch family as a fix for a first-touch stall.
* **A3 was accepted and not performed.** `MAP_POPULATE` is specified to
  synchronously populate the whole range before `mmap` returns. gVisor's Sentry
  accepted the flag — the payload records
  `mmap_flags=32770` (`MAP_PRIVATE｜MAP_POPULATE`), `map_populate_requested=true`,
  `map_populate_in_flags=true`, `map_populate_accepted_by_mmap=true` — and
  returned in 0.77 ms instead of ~1.2 s. A3's `mmap` is 2–4× slower than the
  control's, so *something* was done, but it is ~1000× too little to be
  population.

The honest statement of the mechanism is therefore: **`MAP_POPULATE` is a no-op
on this platform's syscall layer, and because it is a no-op, A3 is
indistinguishable from A.** The 12.31 GB file is on a Modal Volume, reached
through gVisor Sentry; these are host-side page-cache mechanisms being requested
against a filesystem whose data path is not the host's page cache.

Page residency was **not** directly observable here, and the experiment records
that rather than guessing: `page_population_observable=false`,
`page_population_evidence="unavailable_under_gvisor_mincore"`. The mincore-based
residency probe is unreliable for a file-backed mapping on a mounted Volume. The
inference above rests on call wall times, which are measured, not on a residency
claim, which is not.

## 4. Setup costs, so a fast copy loop cannot hide a slow setup

Every container's own accounting, `concurrent4` variant, milliseconds:

| arm | request | fd_open | fadvise | mmap | plan_build | gen→setup | setup→1st copy | copy loop | total |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| A | `dbd446aa4f23` | 0.329 | — | 0.354 | 0.722 | 474.42 | 170.29 | 2456.43 | 2930.85 |
| A | `cc8dbc7afd08` | 0.252 | — | 0.509 | 0.815 | 561.96 | 306.11 | **5762.32** | 6324.28 |
| A2 | `296884125427` | 0.218 | 0.035 | 0.427 | 0.853 | 482.16 | 296.56 | **4525.19** | 5007.35 |
| A3 | `d76e47d8e4e8` | 0.310 | — | 1.733 | 2.136 | 840.94 | 286.94 | **4914.62** | 5755.56 |
| A3 | `eaefe6c765be` | 0.482 | — | 0.774 | 1.335 | 595.00 | 263.27 | 2229.78 | 2824.78 |

The treatment itself costs between 0.03 ms (fadvise) and 1.7 ms (MAP_POPULATE
`mmap`). Neither moved meaningful time. The `gen→setup` column (~445–841 ms) is
dominated by the experiment's own 1 GiB pinned-arena construction and
`cudaHostRegister`, not by the source treatment — which is why the control pays it
too.

## 5. Ordinal 0–7 head versus tail

The head (first eight copies) is not distinguishable from the tail in any arm,
so the stall is not a "first touch the mapping" artefact:

| arm | head n | head p50 | head max | tail n | tail p50 | tail max |
|:--|--:|--:|--:|--:|--:|--:|
| A | 8 | 60.32 | 1140.47 | 1272 | 44.63 | 2040.95 |
| A2 | 8 | 55.78 | 972.30 | 1272 | 41.23 | 1256.21 |
| A3 | 8 | 71.57 | 1161.17 | 1272 | 45.02 | 2103.20 |

## 6. What was run

Lane `exp/source-copy-isolation`, base `211d204b06f1246bbd2b5b591473d7d08b629030`.
Destination `Testing 9 / ws_ee7221847f7d` was over its Modal spend limit, so the
operator redirected the experiment to `Testing 1 / ws_e677ab553606`.

| arm | profile | app | deploy fingerprint | image | source/config identity |
|:--|:--|:--|:--|:--|:--|
| A | `golden_p1_parallel_p9_srccopy_a-control_h100` | `batch-p9srccopy-a-control-h100` | `52fd4bfc…` | `im-SsDoHioUqo4C6YPS0AtUB9` | `9537b199…` |
| A2 | `golden_p1_parallel_p9_srccopy_a2-willneed_h100` | `batch-p9srccopy-a2-willneed-h100` | `da37dcd7…` | `im-kpQpQEAv14eKq22vu…` | `9537b199…` |
| A3 | `golden_p1_parallel_p9_srccopy_a3-populate_h100` | `batch-p9srccopy-a3-populate-h100` | `fb43c940…` | `im-p3V82DeT6l0dIv81d…` | `9537b199…` |

Three deploys, three images — one image per arm is correct, because the arm is a
deploy-baked value and each arm owns its own app identity. All three share one
source/config identity, which is what makes the comparison homogeneous; the two
pre-fix requests ran on source/config identity `a9cfa0b4…` and are reported
separately in §7. `source-probe` returned `RESULT=PASS source_identity=MATCH` for
all three, including the new module:

```
comfymodal_runtime/source_population_policy.py: MATCH remote_sha=12a417359a972367 expected_sha=12a417359a972367
```

Geometry unchanged from the A/B/C/D phase: `H100!`, `CPU=12` requested, memory
24576 MB, `ModalRuntimeEntrypointV2`, `run_golden_parallel_stream`, whole mmap
lifecycle, thread source owner, 64 MiB blocks, 16 × 64 MiB pinned arena,
`conditioning_cache=forced_miss`, `fresh_required=true`, expected output SHA
`3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`,
`min_containers=0`, single-use containers.

### The treatment is process-local, and the deployed arm is not

`COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_POPULATION` is deliberately **not** a
deployed environment value. It is raised by `source_copy_isolation._PopulationGate`
only around the experiment's own `build_plan` call and popped immediately after.
A test asserts it never appears in a profile. The reason is a real risk, not
hygiene: `MAP_POPULATE` on a 12 GiB mapping beside a 1 GiB pinned arena in a
24 GiB container can OOM, and the real Golden source owner runs later in the same
container. Every request in this cohort proves the scoping held: the 15 payloads
report `declared_arm == observed_arm` and `satisfied: true`, and the Golden
requests that followed them all completed.

## 7. Per-arm run validity

17 requests across the three new profiles, run strictly serially, never
concurrently, one `golden run` per request.

| check | result |
|:--|:--|
| attempts | 17 |
| valid | 16/17 |
| DNF | 0 |
| true-cold | 17/17 |
| exact output SHA | 16/16 valid (`3a6a0306…`, 3083864 bytes) |
| `restore_count` / `request_count` | 1 / 1 on all 17 |
| single-use containers, `min_containers=0` | yes |
| capture guard | `ELIGIBLE`, `counted=true` on all 17; **no `SNAPSHOT_CAPTURE`** |
| arm status `ok` | 16/17 |
| variants complete | 16/17 |
| teardown `cudaHost_unregistered` | `true`, `rc=0`, on every request |
| in the homogeneous cohort (`9537b199…`) | **15** (5 per arm) |

Two requests are outside the 15-container cohort, and both are kept rather than
discarded:

1. `cohort_2026-10-04_00-51-06_9415b2` — the first A2 request, **invalid**. Its
   arm payload was perfect (`fadvise_called=true`, `count=1`, `advice=3`, `rc=0`,
   `mmap_flags=2`, teardown unregistered) and the Golden request still failed.
   Cause in §8.1.
2. `cohort_2026-10-04_00-48-15_72819c` — the first A request, **valid**, on the
   pre-fix deployment `a9cfa0b4…` / `im-PZgjeOgLRgY…`. It is a usable
   single-container observation but a different deployment identity from the 15
   that form the cohort, so it is reported as its own cohort rather than pooled
   into arm A. Its numbers (p99 923 ms, 31/256 copies over 100 ms, max 1275 ms)
   are consistent with the arm-A control it was meant to be.

Its single container, for the record: 1 of 1 containers pathological, p50
54.38 ms, p99 923.24 ms, max 1274.91 ms, 31 copies over 100 ms, 11 over 250 ms,
2 over 1 s.

## 8. Two runtime bugs this experiment found

Neither was reachable locally. Both are recorded because the local suite passed
before each one bit.

### 8.1 A declared treatment arm broke production in the same container

The first A2 request produced a correct arm payload and then killed the real
Golden request:

```
SourceProtocolError: SourcePopulationError:
source_population_arm_requires_gate:A2:COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_POPULATION
```

`active_arm()` raised whenever a treatment arm was declared but the gate was off.
The gate is process-local *by design*, so the experiment's `build_plan` ran
treated and the real Golden source owner — a different process in the same
container, gate popped — ran untreated and raised. Declaring a treatment at deploy
time therefore broke the production path, which is the single thing the gate
existed to prevent.

Fixed in `4ff85c6`: a gate-off address space is always the untreated control.
This is not a relaxation of fail-closed. `population_contract` still compares the
declared arm against the arm the payload recorded and rejects a mismatch, so a
treated arm that silently ran as the control is still refused — with better
evidence, scoped to the mapping where the claim is actually made.

### 8.2 `population_contract` would have made the completed B/C/D cohort unrunnable

`declared_arm()` accepted only A/A2/A3 while `population_contract` ran for every
arm, so requesting arm B, C or D raised `unsupported_source_population_arm`. The
already-published A/B/C/D result could not have been reproduced.

Fixed in `ef88713`: `declared_arm` accepts every arm the selector offers, and
`population_contract` reports `applicable: false / arm_maps_no_source` for arms
that map no source (C, D) instead of a false failure. Arm B keeps its mapped
source and is still checked as the untreated control.

## 9. Local verification

* `python -m pytest tests -m fast_unit -q` → **609 passed, 2 failed, 7 skipped**.
  The two failures are the pre-existing `test_rx9p_h_identity_chain` ones that
  `211d204b` already documented and that reproduce on a pristine tree.
* `python -m pytest tests/test_source_population_isolation.py
  tests/test_source_copy_isolation.py tests/test_c0_source_threads.py
  tests/test_source_copy_probe.py tests/test_v2ctl_source_probe.py
  tests/test_golden_flag_reaches_container.py
  tests/test_source_child_script_launch.py -q` → **235 passed, 6 skipped**.
* `tools/source_copy_isolation_report.py --root . --profile-prefix
  golden_p1_parallel_p9_srccopy --out artifacts/source_population/summary_population.json`

One process note: an early `pytest -k "source or isolation or …"` without
`-m fast_unit` collected heavyweight runtime tests and ran past 40 minutes. The
cause was the selection, not a slow test; no timeout was escalated.

## 10. What this does not establish

* **It does not show that page population cannot fix the stall.** It shows that
  these two mechanisms cannot, *on gVisor Sentry against a Modal Volume*, because
  they do not execute. A synchronous, userspace proof of residency followed by a
  deliberate `memcpy` is a different experiment.
* **It does not establish a rate.** Five containers per arm cannot resolve a
  mechanism that fires in roughly one container in five; the 1/5, 2/5, 2/5 counts
  are consistent with no effect and also with a modest one. Distinguishing those
  needs a cohort sized to the observed rate, not five.
* **It does not prove residency either way.** `page_population_observable=false`
  is recorded, not worked around.
* **It says nothing about the destination side.** Arms C and D from the previous
  phase remain the authority there; the pinned shared arena was untouched here.

## 11. Commits

| commit | content |
|:--|:--|
| `ef88713` | A/A2/A3 harness: policy module, `build_plan` hooks, arms, profiles, registry, probe, tests; fixes §8.2 |
| `4ff85c6` | §8.1: gate-off address space is the untreated control |
| `9505860` | report: deployment-keyed cohorts, per-container gate on crediting a treatment, setup-cost evidence |

Base `211d204b06f1246bbd2b5b591473d7d08b629030`. No merge, no tag movement, no
production app touched.
