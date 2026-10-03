# Production-009 — Easy Optimization Pass

Three changes, ten normal true-cold requests, three exhaustive profiles, and an
approval decision for each change. Nothing was promoted or tagged.

---

## 1. Exact source / deploy identity

### Where the work happened

The primary working directory (`comfyui-modal` at the top of the ComfyUI tree,
branch `TESTING8`, HEAD `61f99648`) is **dirty and behind** `production-009`, and
carries unrelated Studio/web work. It was not touched.

Work ran in the existing clean P9 development worktree:

```
C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\p8fix
```

detached at `ccc2c531bead6614d2435e3bd7fa157a900251a8`, which equals `origin/main`
and is the clean checkout that already contains `reports/golden_profiler_p9/`.
No new worktree was created. No branch, tag, stash or reset was touched.

### Identity chain

| item | value |
|---|---|
| `production-009` tag | `45f512ab4c9cd68d6ded9005fe939b1fb73679e1` |
| P9 profiler baseline source | `6b32025a` (tag + four latent-defect fixes + report addendum + two control-plane fixes) |
| Candidate base | `ccc2c531` (= `origin/main`, `git describe` = `profiler-001-feature-dirty` before commit) |
| **Candidate HEAD (measured)** | **`fbd81c46ba131ab44e7020fc2bc3f4005d8756fc`** |
| Follow-up HEAD, unmeasured | `04dc0906` (bounded pre-resolve join; see §17) |
| Expected output SHA | `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` |

### Deployment — normal cohort

| item | value |
|---|---|
| app | `batch-p9opt1-h100` |
| class / method | `ModalRuntimeEntrypointV2` / `run_golden_parallel_stream` |
| profile | `golden_p1_parallel_c0_p8_h100` |
| deploy fingerprint | `3f8d103da61137b4848f7b5ac691da39bac2369f09a81dc8f93474fe43fc9b60` |
| deployment manifest | `.v2ctl/deployments/deploy_20261003-005157_3f8d103d.json` |
| deployment receipt | `receipt_2_3f8d103d…json` |
| workspace | Testing 9, `ws_ee7221847f7d` (from `config/v2/modal_target.toml`) |
| GPU | `H100!` |
| source probe | `RESULT=PASS source_identity=MATCH`, `git_head=fbd81c46ba13`, `deployment_combined_hash=83416b0e7bb3345a` |
| doctor | `[v2ctl.doctor] OK`, fingerprint match 1, target match 1, runtime overrides 0 |
| profile config fingerprint | `bd18edd22b249c47ea22f7e60a1c3a6d9d68629207afb764b65d5ec972b1801e` |

The first deploy (`7f96c21b…`, manifest `deploy_20261003-004122`) was
**invalidated before any measurement**: it crash-looped at restore with
`source_threads_requires_8x64m_arena`. See §10. No run was taken against it.

### Deployment — profiler

| item | value |
|---|---|
| app | `batch-p9opt1-prof` (separate, so the counted deployment was never modified) |
| deploy fingerprint | `9eb93a2bff26c92bfb85a8946eeb4bd73bbb28ac33bbe3e7b4c7cb1553f83aec` |
| source probe | `RESULT=PASS source_identity=MATCH` before each of the three runs |

Same source `fbd81c46`, same profile, same workflow and models. The tracing
deploy adds the standard profiler flags; nothing else differs. The ten normal
runs and the three profiles are therefore two clean single-identity cohorts.

---

## 2. Implementation commits

| commit | change |
|---|---|
| `a6bd7d88` | `perf(golden-c0): deepen the source arena to 16 x 64 MiB` |
| `5b12fb47` | `feat(golden-telemetry): decisive per-block source latency and placement evidence` |
| `2465d990` | `perf(golden-unet): resolve the dynamic UNET layout during CLIP load` |
| `fbd81c46` | `fix(golden-c0): make the source-thread arena gate track its owning module` |
| `04dc0906` | `fix(golden-unet): bound the layout pre-resolve join` — **not deployed, not measured** |

`fbd81c46` is a correction *inside* change 2, described in §10. `04dc0906` is
described in §17.

---

## 3. Local tests

| suite | result |
|---|---|
| `tests/test_c0_source_threads.py` + `test_golden_model_transport.py` + `test_golden_parallel_foundation.py` | 96 passed, 5 skipped |
| + `test_source_latency_telemetry.py` | 121 passed, 5 skipped |
| + `test_unet_layout_preresolve.py` | 134 passed, 5 skipped |
| full `tests -m fast_unit` | **609 passed, 2 failed, 7 skipped** |

The two failures are pre-existing and unrelated:
`tests/test_rx9p_h_identity_chain.py::test_success_path_exact` and
`::test_compact_nested_sage_observation_is_mismatch`. That file imports only
`json`, `ast`, `pathlib`, `pytest` and `tools.v2_control.experiment_evidence`,
and references none of the four changed modules — proven by grep, not asserted.

Also pre-existing and untouched: `tests/test_golden_qd_transport.py::test_static_e27_arm_uses_fixed_ids_and_preserves_output_identity`
fails deterministically. Proven independent: importing
`comfymodal_runtime.golden_qd_transport` reaches **none** of
`golden_io_process_v2`, `golden_source_threads`, `golden_model_transport`,
`golden_serial`, `source_latency_telemetry` or `config_authority`
(checked via `sys.modules` after import).

`tests/test_p1_golden_serial.py` cannot be collected on this Windows host
(`ModuleNotFoundError: No module named 'comfy_api'`). Per `AGENTS.md` this is a
local startup-test dependency failure, not remote Golden evidence; it is not in
the `fast_unit` marker set.

### Test-performance policy note

The canonical wrapper `python tools/test_perf.py --fast -- tests -m fast_unit`
exceeds its 15 s hard timeout on this suite. This is **pre-existing**, proven by
re-running it with both new test files excluded: 494 tests collected, 4.9 s in
collection alone, killed at the same 15.08 s. Per policy I diagnosed rather than
escalated the timeout; the authoritative correctness signal is plain
`pytest tests -m fast_unit`, reported above.

### New tests added

- `tests/test_source_latency_telemetry.py` — 25 tests, synthetic operation
  records only. Percentiles, every stall threshold, per-reader aggregation,
  first-8 truncation and ordering, thirds split (including counts below 3 and
  not divisible by 3), first-H2D with each input missing, robustness to
  `None`/string/non-dict records, memoization, and a recursive compactness
  assertion that no list anywhere exceeds 8 entries.
- `tests/test_unet_layout_preresolve.py` — 11 tests on real temp safetensors:
  single-flight (exactly one parse, same holder), two paths parse separately,
  failure stays fail-closed with the identical error and no stale layout,
  identity change reparses, join for a never-begun path starts nothing, and
  **the bounded join returns within budget and reports `completed is False`**.
- `tests/test_golden_model_transport.py` — added
  `test_source_thread_arena_gate_follows_the_source_threads_module` and
  `test_arena_size_must_exactly_equal_slot_count_times_slot_bytes`.

---

## 4. Ten-run normal cohort

Ten true-cold, single-use `run_golden_parallel_stream` requests, run serially,
never concurrently, on `batch-p9opt1-h100` at fingerprint `3f8d103d`.

Every one of the ten: `valid=true`, `dnf=false`, `true_cold=true`,
`output_sha_match=true`, `failures=[]`, `restore_count=1`, `request_count=1`,
`min_containers=0`, single-use containers, `H100!`, no fallback, source identity
MATCH. **No run was discarded.** The capture guard was idle before the first run
and no request in the cohort was a snapshot capture.

| # | region | request wall ms | restore | setup | clip_load | clip_forward | unet_load | sampler_prepare | sampling | vae_load | vae_decode | output |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | us-west | 59324 | 0.2 | 1.9 | 1702.3 | 2967.3 | 2498.6 | 28.3 | 3895.6 | 396.1 | 718.8 | 236.1 |
| 2 | us-central | 19984 | 0.2 | 1.5 | 1749.4 | 2964.4 | 3119.2 | 31.0 | 3799.1 | 505.1 | 818.7 | 247.3 |
| 3 | us-central | 13573 | 0.3 | 1.4 | **1455.3** | 2200.4 | 2319.8 | 23.3 | 3624.1 | 590.4 | 468.6 | 207.4 |
| 4 | uk | 26859 | 0.2 | 3.4 | **7215.4** | 2715.3 | 2749.0 | 29.8 | 3986.6 | 384.0 | 521.8 | 251.2 |
| 5 | ca | 44185 | 0.5 | 1.5 | 1784.6 | 2096.9 | 2784.6 | 29.5 | 3663.7 | 351.4 | 515.1 | 193.9 |
| 6 | us-west | 15621 | 0.2 | 2.0 | 1626.2 | 2489.5 | 2700.8 | 30.5 | 3878.4 | 506.2 | 552.6 | 250.9 |
| 7 | us-east | 17184 | 0.2 | 1.4 | 2036.4 | 2887.8 | 3135.3 | 42.1 | 3839.3 | 707.1 | 589.1 | 240.8 |
| 8 | uk | 23420 | 0.2 | 4.5 | **5075.0** | 4821.4 | 4753.3 | 30.8 | 3934.8 | 484.3 | 531.7 | 236.2 |
| 9 | uk | 16159 | 0.3 | 1.4 | 1631.8 | 2556.5 | 2415.0 | 38.0 | 3673.4 | 414.6 | 537.1 | 207.8 |
| 10 | us-west | 68267 | 0.2 | 1.8 | 1570.1 | 2492.1 | 2557.9 | 29.0 | 3848.5 | 440.5 | 536.1 | 248.4 |

Regions seen: us-west ×3, us-central ×2, uk ×3, ca ×1, us-east ×1. Provider is
not recorded in the run identity; only region is available.

---

## 5. Aggregate statistics

Ten runs. p90 by nearest-rank on n=10; reported because it was asked for, not
because n=10 supports it.

| field | min | p50 | p90 | max | mean | SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|
| request wall ms | 13572.8 | 19984.3 | 59324.2 | 68266.9 | 30457.8 | 19746.4 | 0.648 |
| restore ms | 0.170 | 0.191 | 0.322 | 0.544 | 0.245 | 0.115 | 0.468 |
| setup ms | 1.408 | 1.515 | 3.371 | 4.513 | 2.086 | 1.038 | 0.498 |
| **clip_load ms** | 1455.3 | 1702.3 | 5075.0 | 7215.4 | 2584.7 | 1949.2 | 0.754 |
| clip_forward ms | 2096.9 | 2556.5 | 2967.3 | 4821.4 | 2819.2 | 764.3 | 0.271 |
| unet_load ms | 2319.8 | 2700.8 | 3135.3 | 4753.3 | 2903.4 | 704.2 | 0.243 |
| sampler_prepare ms | 23.3 | 29.8 | 38.0 | 42.1 | 31.2 | 5.2 | 0.168 |
| sampling ms | 3624.1 | 3839.3 | 3934.8 | 3986.6 | 3814.4 | 122.8 | **0.032** |
| vae_load ms | 351.4 | 440.5 | 590.4 | 707.1 | 478.0 | 107.3 | 0.225 |
| vae_decode ms | 468.6 | 536.1 | 718.8 | 818.7 | 579.0 | 107.1 | 0.185 |
| output ms | 193.9 | 236.2 | 250.9 | 251.2 | 232.0 | 21.0 | 0.091 |
| clip source wall ms | 1357.2 | 1576.8 | 4929.1 | 7085.6 | 2458.1 | 1943.4 | 0.791 |
| clip source GB/s | 1.135 | 4.917 | 5.548 | 5.927 | 4.409 | 1.659 | 0.376 |
| clip memcpy p50 ms | 18.0 | 46.9 | 57.3 | 59.3 | 46.4 | 11.5 | 0.247 |
| clip memcpy p90 ms | 56.2 | 63.4 | 138.4 | 152.6 | 79.9 | 35.3 | 0.442 |
| clip memcpy max ms | 71.4 | 80.9 | 2234.9 | 4283.4 | 721.0 | 1422.3 | 1.973 |
| clip slot wait ms | 0.0 | 0.0 | 0.0 | 0.0 | **0.0** | 0.0 | 0.0 |
| clip all-slots-occupied | 0 | 0 | 0 | 0 | **0** | 0 | 0.0 |
| clip time-weighted eff concurrency | 3.533 | 3.882 | 3.898 | 3.921 | 3.823 | 0.143 | 0.037 |
| clip first-H2D submit ms | 101.3 | 134.1 | 148.2 | 166.8 | 134.1 | 18.5 | 0.138 |
| clip gpu_ready_tail ms | 2.504 | 3.026 | 5.603 | 5.975 | 3.685 | 1.326 | 0.360 |
| clip layout_resolve ms | 30.9 | 34.3 | 36.8 | 42.4 | 34.9 | 3.4 | 0.098 |
| unet source wall ms | 2284.4 | 2503.0 | 3087.4 | 4642.9 | 2792.1 | 710.0 | 0.254 |
| unet source GB/s | 2.651 | 4.774 | 5.272 | 5.389 | 4.597 | 0.840 | 0.183 |
| unet memcpy p50 ms | 42.5 | 49.9 | 57.6 | 59.0 | 50.3 | 5.4 | 0.107 |
| unet memcpy max ms | 93.4 | 205.4 | 380.9 | 2036.1 | 409.9 | 576.8 | 1.407 |
| unet slot wait ms | 0.0 | 0.0 | 56.3 | 114.8 | 17.3 | 38.5 | 2.224 |
| unet all-slots-occupied | 0 | 0 | 525 | 577 | 116.7 | 230.1 | 1.972 |
| unet layout_resolve ms | 0.478 | 0.865 | 9.975 | 18.655 | 4.555 | 5.987 | 1.314 |
| unet gpu_ready_tail ms | 4.010 | 4.731 | 28.950 | 83.876 | 16.609 | 25.243 | 1.520 |

`sampling` is the most stable field in the entire request (CV 0.032).
`clip_load` is the least (CV 0.754).

---

## 6. Source latency histogram comparison

CLIP, 120 operations per run. Stall counts and percentiles in ms:

| # | region | p50 | p90 | max | >50 | >100 | >250 | >500 | >1000 | cap wait ms | ready-queue wait ms |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | us-west | 47.6 | 68.3 | 98.8 | 46 | 0 | 0 | 0 | 0 | 0.0 | 1417.2 |
| 2 | us-central | 50.1 | 63.7 | 87.2 | 61 | 0 | 0 | 0 | 0 | 0.0 | 1390.2 |
| 3 | us-central | 41.4 | 56.2 | 79.8 | 25 | 0 | 0 | 0 | 0 | 0.0 | 1187.9 |
| 4 | **uk** | **18.0** | 152.6 | **4283.4** | 38 | 18 | 11 | 9 | **8** | **2257.3** | **2080.6** |
| 5 | ca | 53.3 | 63.4 | 74.8 | 81 | 0 | 0 | 0 | 0 | 0.0 | 1515.4 |
| 6 | us-west | 46.4 | 61.2 | 80.9 | 28 | 0 | 0 | 0 | 0 | 0.0 | 1341.4 |
| 7 | us-east | 57.3 | 77.9 | 124.9 | 112 | 2 | 0 | 0 | 0 | 0.0 | 1717.9 |
| 8 | **uk** | 59.3 | 138.4 | **2234.9** | 76 | 22 | 9 | 7 | **4** | **1512.2** | **3789.3** |
| 9 | uk | 46.9 | 57.9 | 74.0 | 38 | 0 | 0 | 0 | 0 | 0.0 | 1316.7 |
| 10 | us-west | 44.0 | 58.8 | 71.4 | 33 | 0 | 0 | 0 | 0 | 0.0 | 1261.6 |

The eight healthy runs are indistinguishable from one another: p50 41–57 ms,
p90 56–78 ms, max 71–125 ms, **zero** stalls above 100 ms, zero capacity wait.

Two runs are pathological, and the shape is the important part.

**Run 4 is not "the whole file is slow".** Its p50 is 18.0 ms — *faster* than
every healthy run — while its max is 4283 ms. Per-reader totals are nearly
equal (6050 / 6036 / 7026 / 5923 ms across readers 0–3), so **all four readers
are hit**, not one. Thirds: first p50 75.5 max 2260, middle p50 15.2 max 61.7,
final p50 11.8 max 4283. The middle and final thirds are the fastest of any run
in the cohort. This is a **scattered long-tail**, not a first-wave penalty and
not a uniform slowdown: most copies complete faster than usual while a handful
hang for one to four seconds.

**Run 8 has a genuine first-wave component on top of the same tail.** First
eight operations: 104.7, 445.8, 508.1, 496.0, **1909.3**, 581.6, 50.0, 82.8 ms.
First-third p50 59.3 with max 1909; final third max 2235.

Neither bad run shows slot or capacity starvation of the P9 kind: slot wait is
0.0 ms with count 0 in **both**, and effective reader concurrency is 4 in both.
What appears instead is `capacity_wait` 2257 ms / 9 events (run 4) and 1512 ms /
6 events (run 8), plus `ready_queue_wait` of 2081 ms and 3789 ms across 120
events. `below_four_reader_ms` rises to 1268 ms (run 4) and 1055 ms (run 8)
against ~130 ms when healthy.

UNET shows the same mechanism with a heavier tail: memcpy max 205–2036 ms, and
stalls above 250 ms in runs 2, 3, 7 and 8 (1, 1, 1 and 14 operations
respectively).

---

## 7. GOOD vs BAD_SOURCE vs BAD_GLOBAL

Selected from the ten-run cohort:

- **GOOD** = run 3 — fastest healthy representative (highest source GB/s, lowest
  clip_load, lowest clip_forward).
- **BAD_SOURCE** = run 4 — worst source path, sampling and VAE normal.
- **BAD_GLOBAL** = run 8 — broadest sickness: source *and* clip_forward *and*
  unet_load all inflated together.

BAD_SOURCE and BAD_GLOBAL are different runs.

| metric | GOOD (run 3) | BAD_SOURCE (run 4) | BAD_GLOBAL (run 8) |
|---|---:|---:|---:|
| region | us-central | uk | uk |
| clip_load ms | 1455.3 | 7215.4 | 5075.0 |
| clip source wall ms | 1357.2 | 7085.6 | 4929.1 |
| clip GB/s | **5.93** | **1.14** | 1.63 |
| effective reader concurrency | 4 | 4 | 4 |
| time-weighted eff concurrency | 3.90 | 3.53 | 3.57 |
| slot wait ms / count | 0.0 / 0 | 0.0 / 0 | 0.0 / 0 |
| all slots occupied | 0 | 0 | 0 |
| capacity wait ms / count | 0.0 / 0 | 2257.3 / 9 | 1512.2 / 6 |
| ready-queue wait ms | 1187.9 | 2080.6 | 3789.3 |
| memcpy p50 / p90 / max ms | 41.4 / 56.2 / 79.8 | 18.0 / 152.6 / 4283.4 | 59.3 / 138.4 / 2234.9 |
| stalls >100 / >250 / >500 / >1000 | 0/0/0/0 | 18/11/9/8 | 22/9/7/4 |
| first 8 memcpy ms | 47.8 … (max 79.8) | 60.2, 74.3, 87.3, 91.5, 119.5, 135.4, 99.4, 125.1 | 104.7, 445.8, 508.1, 496.0, **1909.3**, 581.6, 50.0, 82.8 |
| first-H2D submit ms | 134.1 | 120.0 | 148.2 |
| first-H2D submit→completion ms | 5.76 | 6.43 | 4.03 |
| gpu_ready_tail ms | 2.5 | 5.1 | 6.0 |
| clip_forward ms | 2200.4 | 2715.3 | 4821.4 |
| unet_load ms | 2319.8 | 2749.0 | 4753.3 |
| unet GB/s | 5.39 | 4.67 | 2.65 |
| sampling ms | 3624.1 | 3986.6 | 3934.8 |
| vae_decode ms | 468.6 | 521.8 | 531.7 |
| setup ms | 1.4 | 3.4 | 4.5 |
| CPU affinity count | 28 | 28 | 28 |
| arena NUMA | unavailable | unavailable | unavailable |
| GPU | H100 80GB HBM3, cc 9.0 | identical | identical |
| PCI bus id | 00000000:0B:00.0 | 00000000:0B:00.0 | **00000000:8B:00.0** |
| NVML SM / mem MHz | 1980 / 2619 | 1980 / 2619 | 1980 / 2619 |
| NVML P-state / power W | 0 / 123.4 | 0 / 118.8 | 0 / 112.6 |
| PCIe gen / width | 4 / x16 | 4 / x16 | 4 / x16 |

Run 4's per-reader CLIP distribution: reader 0 = 16 ops / 1073.7 MB / max
2917.0 ms; reader 1 = 32 ops / 2139.4 MB / max 3456.2; reader 2 = 30 ops /
2013.3 MB / max **4283.4**; reader 3 = 42 ops / 2818.6 MB / max 2733.8. Run 8:
reader 0 = 37 / 2483.0 MB / 1909.3; reader 1 = 27 / 1811.9 MB / 2119.0;
reader 2 = 22 / 1468.3 MB / 1423.7; reader 3 = 34 / 2281.7 MB / 2234.9.

### A separate and important observation: request wall is not stage work

Run 10 has the **largest request wall in the cohort, 68267 ms**, with entirely
healthy stages (clip_load 1570.1, sampling 3848.5, vae_decode 536.1). Run 1 is
second at 59324 ms and is also healthy. Request wall CV is 0.648 while
sampling CV is 0.032, and the two are uncorrelated.

Whatever dominates `duration_ms` — container scheduling, snapshot
materialization, image pull, scale-up — is **outside every measured stage** and
outside all three optimizations. Any wall-clock target pursued at this layer is
being dominated by something none of this work touches. This is the single
largest remaining number in the request and it is currently unattributed.

---

## 8. Placement / NUMA / GPU correlation

Collected once per process by `collect_placement_telemetry`, memoized, attached
under `source_detail.placement` on every model load.

**What was observable, every run:**

- Parent CPU affinity: 28 CPUs, identical in all ten runs.
- Parent current CPU at collection: 2.
- cgroup: v1, `cgroup_likely_virtualized=true` — "gVisor runsc serves
  sentry-internal cgroupfs; outer worker cgroup not visible". A real host
  allowance is therefore **not obtainable** in this environment.
- Arena shared-memory name (e.g. `psm_8f56688d`), `arena_bytes=1073741824`.
- GPU: `NVIDIA H100 80GB HBM3`, capability 9.0, index 0, device_count 1.
- NVML: SM 1980 MHz, mem 2619 MHz, P-state 0, power 112.6–123.4 W of a 700 W
  limit, PCIe gen 4 x16.
- PCI bus id: present in all ten.

**What failed soft, as required:**

- `arena.numa_node_pages` — **unavailable** in all ten.
- `gpu.gpu_numa_node` — **unavailable** in all ten.
- `source.allowed_cpus` — **null** in all ten.
- `source.reader_threads[].cpu` — all report `cpu: 0`, which is not credible
  under gVisor and must not be read as "all readers ran on CPU 0".

`placement.status` is `degraded` in all ten, with the unavailable names listed.
No request failed, and nothing was guessed: `pci_bus_id` is only accepted when
sysfs yields a real PCI address (`0000:41:00.0` form), never inferred from a
directory name — a defect found and fixed during review, where a Windows-style
`realpath` basename of `device` was briefly being reported as a bus id.

**Correlation verdict: not established, and the reason is a measurement gap,
not a finding.** The one suggestive signal is region: both pathological CLIP
loads are `uk` (runs 4 and 8), and both `>1000 ms` stall clusters are `uk`
(8 and 4 operations). But run 9 is also `uk` and is completely healthy
(clip_load 1631.8, zero stalls above 100 ms), so region is neither necessary nor
sufficient. PCI bus id does not separate either — run 4 shares `0B:00.0` with
healthy runs 1, 6 and 10, and only run 8 differs at `8B:00.0`.

Critically, **NUMA placement cannot be tested at all here**: gVisor does not
expose arena page placement or a GPU NUMA node. A cross-NUMA 1 GiB arena is a
live hypothesis that this evidence cannot address, and it remains the most
plausible explanation for a per-block mapped-page cost that varies 50x between
otherwise identical hosts while reader count, block size and pacer gap are all
identical.

---

## 9. Sixteen-slot result

| acceptance item | result |
|---|---|
| 16 slots initialize FREE | pass — `new_control_buffer` fills all 16; `header[11] == FREE_MASK == 0xFFFF` |
| all 16 claimed independently | pass — 16 distinct slot indices, distinct range indices, distinct source and destination offsets |
| generations remain correct | pass — per-slot generation advances 0→1; plan install never rewinds |
| no slot aliasing | pass — slot 15 occupancy does not consume slot 0; asserted explicitly |
| no control-memory region overlap | pass — header / slot table / counters / error / op ring / plan proven disjoint and monotonic at 16 slots |
| READY / IN_FLIGHT / FREE state machine | pass |
| double-release protection | pass — `release_without_completion_ownership` |
| quiescence proves all 16 returned | pass — `quiescent()` false until every one of 16 is FREE |
| source process READY geometry matches parent | pass — both sides read `golden_source_threads.geometry()` |
| H2D release only after completion | pass |
| telemetry reports 16 / 1073741824 | pass — `c0_arena_bytes=1073741824` in all 10 runs and all 3 profiles |
| exact output SHA unchanged | pass — 13/13 |
| no fallback | pass |
| no source geometry mismatch | pass |

### The headline result

**CLIP slot starvation is gone.** Across all ten runs, CLIP `slot_wait_ms = 0.0`
with count 0, and `all_slots_occupied_count = 0`. Effective reader concurrency
is 4 in 10/10. Time-weighted concurrency 3.53–3.92, mean 3.823.

Against P9's healthy run, which showed ~654 ms cumulative CLIP slot wait and
`all_slots_occupied ~101` at an effective concurrency of ~3.51/4, that is the
elimination of the exact symptom this treatment targeted.

**But the bottleneck moved to UNET, and that is a real cost.** UNET now shows
slot wait in 3 of 10 runs — 114.8 ms / 525 all-slots-occupied (run 4),
56.3 ms / 577 (run 9), 2.1 ms / 65 (run 10). UNET is 184 operations and 12 GiB
against CLIP's 120 and 8 GiB, so the same total starvation simply reappears one
model later. Sixteen slots fixed CLIP; the arena is again the binding
constraint for the larger model.

Effective concurrency improved for UNET too (time-weighted mean 3.737, max
3.925), and UNET source throughput is the most stable large-model number in the
cohort: GB/s 2.651–5.389, CV 0.183.

### Cost of the extra 512 MiB

| arena | `backing_create_ms` | `register_ms` | samples |
|---|---:|---:|---|
| 512 MiB (six prior deployments) | 3.29–8.22 | **402.9 – 583.1** (median ~470) | 6 |
| 1 GiB (this candidate) | 3.50–6.93 | **552.5 – 956.7** (median ~713) | 10 |

Host registration roughly tracks size: +~240 ms median for +512 MiB, about +50 %
rather than 2x, because page-table setup is not purely proportional.
`backing_create_ms` is unchanged at 3.5–6.9 ms.

This cost is paid **once per container** and lands outside every measured
stage — `golden_restore` stayed at 0.17–0.54 ms across all ten runs. It is
inside the request wall and therefore inside the unattributed container
variance discussed in §7.

**Net: the treatment is worth it.** It buys the elimination of ~654 ms of
recurring CLIP slot wait and ~101 all-slots-occupied events for a one-time
~240 ms registration increase. The honest caveat is that it did not make the
*request* faster on the two bad runs — those were sick for a different reason
entirely — so this is a stability win, not a magnitude win.

---

## 10. UNET pre-resolve result

| acceptance item | result |
|---|---|
| dynamic UNET selection still works | pass — `session.model_paths["unet"]`, resolved per request |
| same exact existing inspect/parser used | pass — no second parser |
| no second parser implementation | pass |
| normal UNET load sees `layout_cache_hit=true` | pass — 10/10 normal runs, 3/3 profiles |
| request-time `_parse_layout` after CLIP forward begins = 0 | pass — 10/10 and 3/3 |
| unknown/new UNET still works | pass by construction — key is the resolved dynamic path |
| same path with changed identity remains safe | pass — cache still keyed on (dev, ino, size, mtime_ns); asserted by test |
| parse failure remains fail-closed | pass — the join deliberately does not raise, so `inspect()` reproduces the identical deterministic error; asserted by test |
| exact output SHA unchanged | pass — 13/13 |

Measured, per run:

| # | pre-resolve ms | completed before CLIP forward | joined | UNET cache hit | UNET `layout_resolve_ms` at request time |
|---:|---:|---|---|---|---:|
| 1 | 13.6 | true | true | true | 9.98 |
| 2 | 19.5 | true | true | true | 0.59 |
| 3 | 15.1 | true | true | true | 0.56 |
| 4 | 16.4 | true | true | true | 18.66 |
| 5 | 14.6 | true | true | true | 0.48 |
| 6 | 13.3 | true | true | true | 6.21 |
| 7 | 17.1 | true | true | true | 1.24 |
| 8 | 28.6 | true | true | true | 6.35 |
| 9 | 15.0 | true | true | true | 0.61 |
| 10 | 11.9 | true | true | true | 0.86 |

Profiles: 21.09 / 20.45 / 27.16 ms pre-resolve, all completed before CLIP
forward, all cache hits, request-time resolve 0.93 / 6.93 / 1.07 ms.

**The P9 lockstep inflation is gone.** P9 measured UNET `_parse_layout` at
214 / 918 / 1419 ms inflating together with CLIP tokenize at 212 / 898 /
1399 ms. Here the parse costs **11.9–28.6 ms** — roughly 15–50x cheaper — and
the request-time resolve is 0.48–18.66 ms. The reason is not that the parse got
faster; it is that it no longer runs while CLIP tokenization holds the event
loop. On an uncontended host a 12 GiB safetensors header parse is tens of
milliseconds, and P9's 918–1419 ms figures were mostly contention, not work.

**CLIP source was not harmed.** CLIP source GB/s in the 8 healthy runs is
4.78–5.93, against P9 GOOD's 4.69. The parse runs on one extra thread during
the window where CLIP bytes are still moving, and the measured effect on CLIP
throughput is not visible above run-to-run noise.

**One thing the profiles surfaced that the telemetry alone did not.** In the BAD
profile the *CLIP* layout parse inside `clip_load` took **1608.96 ms**, against
**30.60 ms** in the GOOD-fastest profile — a 52x inflation of the same
deterministic Python parse, with CLIP metadata extraction matching at
1632.07 vs 46.38 ms. Meanwhile the UNET pre-resolve in that same run cost only
27.16 ms. So the BAD run was sick at the Python/host level, not merely at the
source-copy level. This is consistent with the normal-run observation that the
two bad runs also had the cohort's highest `setup` times (3.4 and 4.5 ms
against a 1.5 ms median).

---

## 11. Three profiler results

| role | trace | traced timeline ms | request wall ms | valid |
|---|---|---:|---:|---|
| GOOD healthy | `ad2f1cf4b36046c2a797cb60243d445a` | 14590.0 | 87487 | yes |
| GOOD fastest | `25172b0c43f04a22a48878732ad07d10` | 13041.8 | 42604 | yes |
| BAD | `ddb6c39a7fdc4c4890a4724bd617038a` | 19222.3 | 86464 | yes |

Derived reports committed to `reports/golden_profiler_p9opt/` (see its
`README.md`). The first two came in under 16 s, so capture continued until one
exceeded it, which is where P9's WORST run sat (17.6 s).

All three: `valid`, exact output SHA, true-cold, `restore_count=1`,
`request_count=1`, single-use, `run_golden_parallel_stream`, no fallback, probe
PASS. All three report `GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE = NO`, reason
`no_root_corrupting_incomplete_calls: incomplete_calls=16` plus
`report_artifact_written`; clock alignment is clean (one traced process, 0 ns
skew) and `c_function_tracing` is false by design.

### Critical path

| stage | GOOD healthy | GOOD fastest | BAD |
|---|---:|---:|---:|
| `golden_restore` | 0.4 / 0.0% | 0.4 / 0.0% | 0.4 / 0.0% |
| `golden_request_setup` | 1.9 / 0.0% | 1.7 / 0.0% | 2.9 / 0.0% |
| `golden_clip_load` | 2015.8 / 99.8% | 1734.0 / 99.8% | 4605.2 / 99.9% |
| `golden_clip_forward` | 3308.2 / 15.4% | 3061.9 / 21.1% | 4122.7 / 25.9% |
| `golden_unet_load` | 2795.1 / 0.0% | 2414.2 / 0.0% | 3056.9 / 0.0% |
| `golden_sampler_prepare` | 55.1 / 89.3% | 56.0 / 99.2% | 79.9 / 96.1% |
| `golden_vae_load` | 878.9 / 0.0% | 554.8 / 0.0% | 826.0 / 0.0% |
| `golden_sampling` | 4413.6 / 80.0% | 4267.4 / 86.9% | 5247.8 / 84.1% |
| `golden_sampler_tail` | 0.1 / 0.0% | 0.0 / 0.0% | 0.1 / 0.0% |
| `golden_vae_decode` | 874.0 / 99.5% | 719.1 / 99.0% | 1013.8 / 99.2% |
| `golden_output` | 256.5 / 98.1% | 243.6 / 99.4% | 274.0 / 98.1% |

`golden_unet_load` remains 0.0% on the critical path in all three — fully hidden
behind CLIP forward, exactly as in P9. Nothing here justifies spending effort on
UNET load in isolation.

### A. CLIP LOAD decomposed

GOOD fastest, 1734.0 ms, 99.8% critical path:

| component | ms | nature |
|---|---:|---|
| source transport (`source_open_read`) | 1625.6 | real work |
| — telemetry source wall | 1524.0 at **5.279 GB/s** | real work |
| CLIP layout/meta resolve | 30.6 | cacheable |
| CLIP metadata extraction | 46.4 | cacheable |
| H2D first ready / submit / submit→completion | 62.2 / 64.1 / 5.8 | real work |
| destination setup (`GpuDestinationPool._allocate` self) | 5.5 | removable |
| storage adoption | 58.7 | removable/reducible |
| skeleton bind/assign | 25.9 | removable/reducible |
| ready proof | 6.9 | bookkeeping |

BAD, 4605.2 ms, 99.9% critical path:

| component | ms |
|---|---:|
| source transport (`source_open_read`) | 4481.2 |
| — telemetry source wall | 2795.0 at **2.878 GB/s** |
| CLIP layout/meta resolve (`_parse_layout`) | **1609.0** |
| CLIP metadata extraction | **1632.1** |
| H2D first ready / submit / submit→completion | 68.3 / 80.5 / 3.1 |
| storage adoption | 66.2 |
| skeleton bind/assign | 28.7 |
| ready proof | 8.1 |

Against P9: GOOD `source_open_read` 1800.7 ms, MIDDLE 3652.2 ms. New GOOD
fastest 1625.6 ms — the best source figure this codebase has produced. New BAD
4481.2 ms is worse than P9 MIDDLE.

REMOVE / CACHE / PARALLELISE candidates, in order of size and confidence:
layout resolve and metadata extraction (~77 ms when healthy, ~3.2 s when the
host is sick — so this is cheap to cache and expensive to leave exposed),
storage adoption (~59–66 ms), skeleton bind/assign (~26–29 ms), destination
setup (~5 ms), ready proof (~7–8 ms). The remainder, source reads and H2D, is
real work. Note the telemetry intervals overlap and are **not additive**; the
CLIP-load decomposition above cannot be reconciled to an exact total.

### B. CLIP FORWARD vs UNET LOAD

The lockstep inflation is gone — see §10. Pre-resolve completed before CLIP
forward in 3/3 profiles, all cache hits, request-time UNET resolve 0.93 / 6.93 /
1.07 ms.

Critical-path share moved in the right direction:

| trace | clip_forward | unet_load |
|---|---:|---:|
| P9 GOOD | 24.4% | 0.0% |
| P9 MIDDLE | 0.0% | **21.2%** |
| new GOOD healthy | 15.4% | 0.0% |
| new GOOD fastest | 21.1% | 0.0% |
| new BAD | 25.9% | 0.0% |

P9's MIDDLE run is the one where UNET load actually reached the critical path
(21.2%) while CLIP forward was fully hidden — that inversion is not reproduced.
In all three new traces UNET load is 0.0%.

Remaining overlap is genuine scheduled overlap, not demonstrated contention.
GOOD fastest: UNET load 2414.2 ms of which `golden.unet.source_h2d_transport`
2217.3 ms, running concurrently with CLIP forward. BAD: UNET load 3056.9 ms,
transport 2842.4 ms. **The artifacts do not establish GPU-resource contention**
between CLIP GPU work, UNET source activity and UNET H2D, and inclusive time is
not evidence of it. CLIP forward and UNET load are both off the critical path,
so neither is currently worth attacking.

### C. SAMPLING — remaining opportunity (not implemented)

GOOD fastest, 4267.4 ms, 86.9% critical path.

- **One-time first-use:** `golden_sampler_prepare` 56.0 ms, of which dependency
  closure is 54.2 ms (`EmptyImage.generate` 18.5 ms, `ImageRotate.execute`
  5.8 ms).
- **Repeated model-forward work:** `RK_Method_Exponential.__call__` 3260.9 ms
  total inclusive, `RK_Method_Beta.model_denoised` 3256.2 ms,
  `BaseModel.apply_model` 1801.4 ms across 17 evaluations.
- **Custom-node callbacks:** `ClownsharKSampler_Beta.main` 4218.8 ms,
  `SharkSampler.main` 4215.3 ms — wrappers with small self time.
- **Python orchestration:** `CFGGuider.inner_sample` 3841.4 ms inclusive but
  only 48.5 ms self; `sample_rk_beta` 3786.4 ms inclusive, 47.7 ms self.
- **Waits:** `EpollSelector.select` 2675.8 ms, **all self** — blocking wait, not
  CPU burn. `SourceThreadProcess._read_message` 3532.6 ms with 3524.3 ms self,
  which is transport activity, not sampler work.

The Python-visible cost is small: orchestration self time is under 50 ms per
wrapper. The multi-second walls are model-forward work the profiler cannot see,
because it traces Python frames only and GPU kernel time is invisible. **A
GPU-bound stage reads as waiting.** So the honest statement is: sampling is
86.9% critical and cheap in Python, and any real reduction has to come from the
model forward or the number of evaluations — neither of which is in scope here.
`sampling` is also the most stable field in the whole cohort (CV 0.032), which
argues against treating it as a stability problem.

### D. VAE DECODE

| trace | decode wall | `VAE.decode` inclusive | `VAE.decode` self | `load_models_gpu` | `partially_load` |
|---|---:|---:|---:|---:|---:|
| GOOD fastest | 719.1 | 718.2 | 636.0 | 73.0 | 65.5 |
| GOOD healthy | 874.0 | — | — | — | — |
| BAD | 1013.8 | 1011.3 | 895.5 | 110.7 | 100.1 |

The body is `VAE.decode` itself, and from Python it reads as GPU-bound; the
CUDA kernels are not in the trace.

**Yes, there is residual GPU-residency work before decode.** Despite
`golden_vae_load` having already run (554.8 ms GOOD / 826.0 ms BAD), decode
still calls `load_models_gpu` (73.0 / 110.7 ms) and
`ModelPatcherDynamic.partially_load` (65.5 / 100.1 ms). Whether that is
semantically redundant or required by the model-management policy is **not
determinable from these artifacts** — only the repeated load activity is
visible. It is flagged as the concrete next question for VAE, not as a proven
win.

### E. TRITON — remaining opportunity (not implemented)

Each function appears once per trace:

| function | GOOD healthy incl/self | GOOD fastest incl/self | BAD incl/self |
|---|---:|---:|---:|
| `CudaUtils.__init__` | 771.6 / 0.04 | 723.8 / 0.05 | 1009.1 / 0.04 |
| `compile_module_from_file` | 749.6 / 0.02 | 708.5 / 0.02 | 986.9 / 0.02 |
| `JITFunction._do_compile` | 353.0 / 0.06 | 315.2 / 0.05 | 441.2 / 0.05 |
| `Llama2_.compute_freqs_cis` | 1914.6 / 0.19 | 1850.9 / 0.29 | 2469.7 / 0.88 |
| `precompute_freqs_cis` | 1914.4 / 204.4 | 1850.6 / 201.0 | 2468.8 / 218.6 |

Self time is negligible for the compile chain (0.02–0.06 ms): the cost is
inside native work the Python tracer cannot resolve. `precompute_freqs_cis`
carries ~201–219 ms of real Python-adjacent self time.

`golden_sampler_prepare` was 55.1 / 56.0 / 79.9 ms against P9's 67 ms
reference — the two healthy traces are *below* P9, so the Triton pre-snapshot
warm is still doing its job on the sampler-prepare axis. But
`CudaUtils.__init__` and `compile_module_from_file` still appear inside CLIP
forward in all three traces at 0.7–1.0 s inclusive, so **first-use Triton cost
has not been eliminated from the request — only moved out of
`sampler_prepare`.** Given the size and the fact that CLIP forward is only
15–26% critical, the ceiling here is bounded.

---

## 12. Remaining CLIP-load optimization points

1. **Per-block mapped-page cost.** The dominant remaining item. Individual
   64 MiB copies vary from 41 ms to 4283 ms on identical code and identical
   geometry. Not a starvation problem — all four readers stay busy
   (per-reader totals within 20% of each other in the worst run). Candidate
   causes: NUMA placement of the arena, gVisor page-fault behaviour on
   Volume-backed files, or host memory bandwidth contention. **Not yet
   diagnosed**; the telemetry now makes it measurable, which is the point of
   change 1.
2. **Cache layout and metadata extraction.** 30.6 + 46.4 ms when healthy, but
   1609.0 + 1632.1 ms in the BAD profile. Cheap to cache, and the exposure
   scales with host sickness, so this is worth more than its healthy cost
   suggests.
3. **Adoption and binding.** Storage adoption 58.7–66.2 ms, skeleton
   bind/assign 25.9–28.7 ms, ready proof 6.9–8.1 ms, destination setup ~5 ms.
   Together ~100 ms of non-source work per model.
4. **Arena depth, again, for UNET.** 16 slots removed CLIP starvation but UNET
   (184 ops, 12 GiB) hits slot wait in 3 of 10 runs. A deeper arena would move
   the same wall further along rather than remove it.
5. **Not a CLIP-load target:** H2D. First submit 64–80 ms after source start,
   submit→completion 3–6 ms, gpu_ready_tail 2.5–6.0 ms. There is nothing here.

## 13. Remaining CLIP-forward / UNET contention

The parse/tokenize lockstep is resolved (§10). What remains is ordinary
scheduled overlap: UNET source and H2D run concurrently with CLIP forward, and
`golden_unet_load` is 0.0% critical in all three profiles.

The one genuine finding is that in the BAD profile the CLIP-side Python parse
inflated 52x while the UNET pre-resolve in the same run stayed at 27 ms. That
is evidence of **host-level Python slowness during that request**, not of
CLIP/UNET contention. It also predicts the normal-run observation that the two
bad runs had the highest `setup` times.

No measurement in this pass demonstrates GPU contention between CLIP forward and
UNET H2D. Establishing it would need CUDA event timelines or NVML sampling
across the overlap, which this telemetry does not collect.

## 14. Remaining sampling / VAE / Triton opportunities

- **Sampling:** 86.9% critical, CV 0.032, Python self time under 50 ms per
  wrapper. Real reduction requires attacking the model forward or the
  evaluation count. Not a stability lever.
- **VAE:** decode still performs `load_models_gpu` + `partially_load`
  (~139 ms GOOD / ~211 ms BAD) *after* `golden_vae_load` already ran. That
  repetition is the concrete thing to investigate; whether it is removable
  needs a semantic check against the model-management policy.
- **Triton:** compile chain still costs 0.7–1.0 s inclusive inside CLIP
  forward. Bounded upside because CLIP forward is only 15–26% critical.

---

## 15. Ten specific questions, answered

1. **How many of 10 CLIP loads are < 2.0 s?** **7 of 10.** The three exceptions
   are run 7 at 2036.4 ms (marginal), run 8 at 5075.0 ms and run 4 at 7215.4 ms.
2. **How many CLIP source spans are pathological?** **2 of 10** — runs 4
   (1.14 GB/s) and 8 (1.63 GB/s). Run 7 is slow but not pathological: 4.31
   GB/s, max 124.9 ms, two stalls above 100 ms, zero capacity wait.
3. **Does 16-slot QD4 eliminate GOOD-run source-slot starvation?** **For CLIP,
   yes, completely.** Slot wait 0.0 ms and all-slots-occupied 0 in 10/10, against
   P9 GOOD's ~654 ms and ~101. Effective concurrency 4 in 10/10 and
   time-weighted mean 3.823, against P9's ~3.51. **For UNET, no** — slot wait
   returns in 3 of 10 runs, up to 114.8 ms / 577 all-slots-occupied.
4. **Does source throughput improve?** **Yes, for CLIP.** Healthy runs reach
   4.78–5.93 GB/s against P9 GOOD's 4.69, and the best CLIP source wall in the
   cohort is 1357.2 ms. UNET reaches 5.389 GB/s best case.
5. **Do any runs still show the old MIDDLE pathology — ~QD4 concurrency, little
   or no slot wait, but very low GB/s?** **Yes: runs 4 and 8, exactly.** Both
   show effective concurrency 4 and slot wait 0.0/0, yet 1.14 and 1.63 GB/s.
   **This pass did not fix that mode; it explained it.**
6. **What happened to per-block memcpy durations? First wave or entire file?
   One reader or all readers?** Run 4: **scattered long tail across the entire
   file, hitting all four readers.** p50 18.0 ms is *faster* than any healthy
   run; middle and final thirds are the fastest in the cohort (p50 15.2 and
   11.8 ms); per-reader totals are 6050 / 6036 / 7026 / 5923 ms. Eight
   operations exceed 1 s, one reaching 4283 ms. Run 8 is the same tail **plus**
   a real first-wave component (first eight: 104.7, 445.8, 508.1, 496.0, 1909.3,
   581.6, 50.0, 82.8 ms). In both, slot wait is zero and capacity wait appears
   instead (2257 ms / 9 and 1512 ms / 6), with ready-queue wait 2081 and
   3789 ms. Mechanism: a few stuck blocks occupy slots until all 16 are held,
   the reader capacity semaphore blocks, and the H2D dispatcher starves.
7. **Does NUMA/CPU/GPU placement correlate with good/bad runs?** **Not
   established, and it cannot be from this evidence.** NUMA is unavailable
   under gVisor, so the leading hypothesis is untestable here. CPU affinity
   (28) and NVML clocks, P-state, power and PCIe are identical across all ten.
   Region is suggestive — both pathological runs are `uk` — but run 9 is also
   `uk` and healthy, so it is neither necessary nor sufficient. PCI bus id
   does not separate. `source.reader_threads[].cpu` reports 0 for every thread
   and must not be trusted.
8. **Does UNET layout pre-resolution eliminate the parse/tokenize overlap?**
   **Yes.** Pre-resolve completes before CLIP forward in 10/10 normal runs and
   3/3 profiles, at 11.9–28.6 ms, with `layout_cache_hit=true` in 13/13 and
   request-time resolve of 0.48–18.66 ms. P9's 918–1419 ms parse against
   898–1399 ms tokenize is gone.
9. **Does pre-resolve slow CLIP source?** **No measurable effect.** Healthy
   CLIP source is 4.78–5.93 GB/s, at or above P9 GOOD's 4.69, with zero slot
   wait. The parse competes for one thread during a window where the source is
   otherwise waiting on I/O.
10. **Did the 1 GiB arena increase restore/host-registration enough to matter?**
    **No, not enough to matter.** `register_ms` rises from a 402.9–583.1 ms
    range (512 MiB, six prior deployments) to 552.5–956.7 ms (1 GiB) —
    roughly +240 ms median, +50 % for +100 % size. It is paid once per
    container and lands outside every measured stage (`golden_restore` stayed
    at 0.17–0.54 ms). Against ~654 ms of recurring CLIP slot wait removed, it
    is comfortably net positive.

---

## 16. Approval status

### CHANGE 1 — TELEMETRY: **APPROVED**

- [x] Enough data to distinguish first-wave from steady-state sickness —
      `first_8_operations` plus `thirds` separate them cleanly: run 4's first
      third p50 is 75.5 ms while its middle and final thirds are 15.2 and
      11.8 ms, which no single average could show.
- [x] Per-reader sickness visible — run 4's four readers at
      6050 / 6036 / 7026 / 5923 ms with individual maxima 2917 / 3456 / 4283 /
      2734 ms.
- [x] Placement evidence available where supported — CPU affinity, cgroup
      (virtualized), GPU model, PCI bus id, NVML clocks, P-state, power and
      PCIe all captured. NUMA correctly reported unavailable.
- [x] Overhead negligible — summary derived once per model after drain; nothing
      added inside any copy path; compactness asserted by test.
- [x] Correctness unchanged — 13/13 exact SHA.
- [x] The stated goal was met: P9's unexplained 1.7 s-vs-3.4 s CLIP source
      spread is now attributed to scattered 1–4.3 s individual 64 MiB copies
      across all four readers, with capacity backpressure downstream.

### CHANGE 2 — 16 SLOTS: **APPROVED**

- [x] Correctness unchanged — 13/13 exact SHA.
- [x] No protocol or state-machine regression — all eight local acceptance
      items pass, plus a new test proving control-region disjointness at 16
      slots.
- [x] Healthy source slot starvation materially decreased — CLIP slot wait
      654 ms → 0.0 ms, all-slots-occupied 101 → 0.
- [x] Effective reader utilization improved — 4/4 in 10/10, time-weighted mean
      3.823 vs P9's ~3.51; CLIP throughput 4.69 → up to 5.93 GB/s.
- [x] Added registration cost does not erase the benefit — +240 ms one-time
      against ~654 ms recurring removed.
- **Caveat recorded, not waived:** the arena is again the binding constraint
  for UNET in 3 of 10 runs. This is a stability win, not a magnitude win; two
  runs remain source-path pathological for a different reason.

### CHANGE 3 — UNET PRE-RESOLVE: **APPROVED**

- [x] Correctness unchanged — 13/13 exact SHA.
- [x] Dynamic model semantics preserved — resolved per request from
      `session.model_paths["unet"]`.
- [x] UNET later gets a layout cache hit — 13/13.
- [x] Parse no longer runs during CLIP forward/tokenization — 13/13 completed
      before CLIP forward.
- [x] CLIP source not materially harmed — 4.78–5.93 GB/s on healthy runs.
- [x] Bad parse/tokenization lockstep inflation disappeared — P9's
      918/898 ms and 1419/1399 ms pairing is absent; pre-resolve costs
      11.9–28.6 ms and request-time resolve 0.48–18.66 ms.

**Not promoted and not tagged.** Promotion remains Ahmed's decision.

---

## 17. Exact next recommended experiment

**Measure per-block mapped-page cost directly, on a NUMA-visible host.**

This is the only remaining item that is both large and unattributed. In the two
pathological normal runs, CLIP source fell to 1.14 and 1.63 GB/s while all four
readers stayed busy and slot wait stayed at zero — individual 64 MiB copies
simply took up to 4283 ms. The arena is not the constraint, reader count is not
the constraint, and the code is identical across runs. The variance is in the
host.

Concretely, one experiment, four arms, nothing else changed:

1. Keep everything at `fbd81c46` and the 16-slot arena.
2. Add request-time NUMA evidence that actually works: the arena's node
   distribution from `/proc/self/numa_maps` is unavailable under gVisor, so
   either run the cohort on a non-gVisor host or read placement from the
   Volume-backed file's own mapping. Until arena NUMA is observable, the
   cross-NUMA hypothesis cannot be tested at all.
3. Record, per operation, the source file's mapping node alongside the existing
   memcpy interval, so a slow copy can be attributed to a specific page.
4. Arms: (a) control as measured; (b) arena first-touched by a thread bound to
   one node; (c) `MADV_HUGEPAGE` / large-page backing for the arena; (d) source
   file read with a single warm mapping reused across all four readers, which
   tests whether the per-block mapping acquisition is the cost.

Ten runs per arm, same fingerprint discipline as this pass. Success criterion:
the per-block memcpy max/p99 stops varying by 50x between hosts, and worst-case
CLIP GB/s rises above the 1.14 GB/s floor seen here.

Two cheaper items worth folding into the same deploy, since neither needs its
own cohort: bound the pre-resolve join (already committed at `04dc0906`, needs
one normal run to confirm the bounded path), and remove the repeated
`load_models_gpu` / `partially_load` inside `VAE.decode` (~139 ms healthy,
~211 ms in the BAD run) once it is established whether model management permits
it.

### The other thing that should be said plainly

The largest number in this request is not in any stage this pass measured. Run
10 spent **68267 ms** of request wall with entirely healthy stages; run 1 spent
59324 ms, also healthy. `duration_ms` has CV 0.648 while `sampling` has 0.032,
and the two do not correlate. Whatever that is — container scheduling, snapshot
materialization, scale-up — it is bigger than the entire CLIP source
improvement available here, and no part of the stage instrumentation sees it.
If wall-clock is the objective rather than stage stability, that is where the
next investigation belongs, and it should be scoped before another round of
source-path micro-optimization.

---

## Provenance summary

| cohort | deployment | fingerprint | runs |
|---|---|---|---|
| 10 normal | `batch-p9opt1-h100` | `3f8d103d…` | 10/10 valid, true-cold, exact SHA |
| 3 profiles | `batch-p9opt1-prof` | `9eb93a2b…` | 3/3 valid, true-cold, exact SHA |

Both from source `fbd81c46`. Neither cohort mixes deployment identities, and no
counted run was taken against the traced deployment or vice versa.

Derived profile reports: `reports/golden_profiler_p9opt/` (committed).
Raw request telemetry and run bundles: `artifacts/` (gitignored), re-fetchable
with `python tools/golden_profile_pipeline.py report <trace_id>`.

**Known limitation carried into this report:** commit `04dc0906` (bounded
pre-resolve join) is committed but was never deployed or measured. Applying it
before the profiles would have split the profile cohort's fingerprint. It is
behaviourally identical to the measured code on every run in this cohort — all
thirteen pre-resolves completed in 11.9–28.6 ms, far inside its 2 s budget —
but it is unmeasured in a container, and one normal run should confirm it.