# Golden Serial QD2 lazy CPU backing report

## Decision

Do **not** keep or commit this candidate. Anonymous writable `mmap` removed the
upfront CPU backing creation cost, but the cost moved into source reads and the
whole endpoint regressed. The worktree should be restored to committed reorder
`0ea9428`; no lazy-backing source change is committed.

## Frozen identity

| item | value |
|---|---|
| worktree | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal` |
| base | `0ea9428` (`Reorder Golden DynamicVRAM before QD2`) |
| candidate app | `batch-golden-q2-lazybacking` |
| workspace | `Testing 6` / `ws_175a616152c5` |
| target | `ModalRuntimeEntrypointV2.run_golden_serial_stream` |
| GPU / CPU / memory | `rtx-pro-6000` / `4` / `16384 MiB` |
| attention | Sage; resolved `sage`, runtime `baked_cuda` |
| QD2 | `cpu_raw_qd2_preadv_prefetch`, 2 workers, 128 MiB extents |
| coverage | `8,044,936,192` bytes, 60 ready extents |
| deep profiler | request `deep_trace=false`, effective `off` |
| workflow SHA | `e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5` |
| output SHA | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` |
| deployment fingerprint | `f18f86eeb53c619b431fb23fd483823192ccaaf700f3124292b0a5fc8b63a100` |
| source probe | `PASS / MATCH` |

## Lazy candidate timing runs

Times are milliseconds. Source start and first extent are relative to remote
restore end. `total CLIP source` is `CPU_PREFETCH_START` to
`CPU_PREFETCH_SOURCE_COMPLETE`. `Golden call` is the persisted
`golden_request_setup` entry boundary.

| run | backing creation | QD2 source start | first extent ready | total CLIP source | restore end → Golden call | H2D span | resume → FRR | exact SHA / fallback / validity |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.062 | 57.809 | 91.429 | 2068.327 | 130.066 | 418.781 | 12670.280 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid=true, true_cold=true |
| 2 | 0.073 | 73.170 | 108.652 | 2321.359 | 150.807 | 607.775 | 13107.359 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid=true, true_cold=true |
| 3 | 0.096 | 76.836 | 110.221 | 2799.951 | 119.718 | 808.924 | 13844.044 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid=true, true_cold=true |
| 4 | 0.058 | 51.166 | 92.626 | 2500.490 | 101.689 | 830.773 | 13590.439 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid=true, true_cold=true |
| 5 | 0.075 | 52.452 | 95.981 | 2204.640 | 99.545 | 515.319 | 13009.003 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid=true, true_cold=true |

Means: backing creation `0.073 ms` (median `0.073`, range `0.058–0.096`);
source duration `2378.953 ms`; H2D span `636.314 ms`; restore end → Golden
call `120.365 ms`; resume → FRR `13244.225 ms` (median `13107.359`).

All runs proved `qd=2`, `worker_count=2`, `cpu_backing_bytes=8044936192`,
`bytes_read=8044936192`, `ready_extent_count=60`, actual `os.preadv`, exact
workflow hash, exact output SHA, `restore_count=1`, `request_count=1`,
`seriality.count=0`, completed teardown, and no runtime fallback.

## Direct comparison with the 0ea9428 cohort

The committed-reorder cohort used the same Golden Serial/Sage/true-QD2 shape,
workflow SHA, output SHA, and five-run endpoint values supplied for this test.

| metric | 0ea9428 mean | lazy candidate mean | delta |
|---|---:|---:|---:|
| backing creation | 689.647 ms | 0.073 ms | -689.574 ms |
| total CLIP source | 1208.254 ms | 2378.953 ms | +1170.699 ms |
| H2D span | 575.583 ms | 636.314 ms | +60.731 ms |
| restore end → Golden call | 829.458 ms | 120.365 ms | -709.093 ms |
| resume → FRR | 12770.067 ms | 13244.225 ms | **+474.158 ms** |

The candidate removes nearly all eager creation time, but source reads become
about `1.97x` slower on average and H2D is also slower. Whole resume → FRR is
`3.71%` worse, so the primary E2E question is refuted. This is not a clean win
and the candidate must not be committed.

## Local validation

- Focused QD2/control tests: `15 passed`.
- `py_compile` for changed runtime/tests: pass.
- No DynamicVRAM, transport, loader, H2D, or other optimization changes were
  made in the candidate.

## Raw evidence paths

Deployment and source probe:

- `.v2ctl/deployments/deploy_20260908-140127_f18f86ee.json`
- `.v2ctl/deployments/receipt_1_f18f86eeb53c619b431fb23fd483823192ccaaf700f3124292b0a5fc8b63a100.json`
- `.v2ctl/source-probes/probe_1_f18f86eeb53c619b431fb23fd483823192ccaaf700f3124292b0a5fc8b63a100.json`

Correctness smoke:

- `EXPERIMENT_EVIDENCE_golden_p1_e63ced59e5144139_2026-09-08.md`
- `.v2ctl/runs/run_20260908-140353_73887de7.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-03-13_1a0079/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-03-13_1a0079/attempt_0_events.json`

Timing runs 1–5:

- `EXPERIMENT_EVIDENCE_golden_p1_8715d67d04e54165_2026-09-08.md`
- `.v2ctl/runs/run_20260908-140509_73887de7.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-04-40_e61bcf/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-04-40_e61bcf/attempt_0_events.json`
- `EXPERIMENT_EVIDENCE_golden_p1_a3570eef01e5448d_2026-09-08.md`
- `.v2ctl/runs/run_20260908-140609_73887de7.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-05-40_e715e9/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-05-40_e715e9/attempt_0_events.json`
- `EXPERIMENT_EVIDENCE_golden_p1_8c9c2e23e9e44afc_2026-09-08.md`
- `.v2ctl/runs/run_20260908-140712_73887de7.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-06-41_a045e3/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-06-41_a045e3/attempt_0_events.json`
- `EXPERIMENT_EVIDENCE_golden_p1_00888fde5b434afe_2026-09-08.md`
- `.v2ctl/runs/run_20260908-140817_73887de7.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-07-46_835996/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-07-46_835996/attempt_0_events.json`
- `EXPERIMENT_EVIDENCE_golden_p1_d10233310d6441a9_2026-09-08.md`
- `.v2ctl/runs/run_20260908-140920_73887de7.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-08-50_a50a24/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_19-08-50_a50a24/attempt_0_events.json`

Direct 0ea9428 comparator raw artifacts:

- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_17-46-52_1d90ca/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_17-59-55_a4940c/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_18-03-16_5a6e87/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_18-08-23_96b03d/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_18-12-43_1a4eb5/attempt_0.json`
