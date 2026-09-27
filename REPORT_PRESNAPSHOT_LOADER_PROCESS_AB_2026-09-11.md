# Pre-snapshot persistent loader process — snapshot survival + full A/B (2026-09-11)

Implementation commit: `0d9a75c` (on top of `c3aceb3`/`accf345`/`b815106`).
Flags (both default `0`, deploy-baked):
`COMFYMODAL_GOLDEN_LOADER_PROCESS` and
`COMFYMODAL_GOLDEN_LOADER_PROCESS_PRESNAPSHOT`.

## Phase A — snapshot survival probe

| Question | Verdict | Evidence (raw, 7/7 runs) |
| --- | --- | --- |
| Pre-spawned worker survived snapshot? | **YES** | pre-capture PID `30` = post-restore PID `30`; `/proc/<pid>/stat` start-ticks identical (per container); UUID identical; parent PID `2`; PPID check true; `spawn_count == 1` in every run (no post-restore spawn path) |
| Same IPC channel survived? | **YES** | same pipe fds (parent `18`, child `19`), `child_fileno_match=true`; PING→PONG median **3.9 ms**; PONG at **9.0 ms** after the request-side restore boundary |
| Worker CUDA-clean at capture? | **YES** | child `cuda_initialized=false`, `cuda_tasks_run=0`; parent `parent_cuda_initialized=false`; snapshot quiescence proof passed with the child present |

Pre-capture worker record (per container): `worker_pid=30`, `startup_ms≈1664`,
`conn_fileno_parent=18`, `conn_fileno_child=19`, UUID per deployment.
Post-restore worker session init: **143.9 ms** median; worker CUDA first touch
(activation + `torch.cuda.init()`): **3998.3 ms** median (range 3465–5926).

### Initial failure and its exact root cause (preserved)

First restored runs failed closed with
`presnapshot_cuda_init_failed: golden_aimdo_activation_failed:import_failed |
No CUDA GPUs are available`. Instrumented diagnosis:

- child (PID 30, restored): `cuInit_rc=100` (CUDA_ERROR_NO_DEVICE),
  `cuDeviceGetCount_rc=3`, `/dev/nvidia0..7` present,
  `CUDA_VISIBLE_DEVICES` **unset** (stale spawn-time env).
- parent (PID 2, restored): `CUDA_VISIBLE_DEVICES="0"`, `cuInit_rc=0`,
  device count 1.

Root cause: the child's environment is frozen at spawn time and did not carry
the post-restore GPU-visibility values Modal sets in the parent. Fix
(`0d9a75c`): the parent forwards `CUDA_VISIBLE_DEVICES` /
`NVIDIA_VISIBLE_DEVICES` / `NVIDIA_DRIVER_CAPABILITIES` with the `init_cuda`
ticket; the child adopts them before CUDA init (`env_applied` recorded), after
which `cuInit_rc=0`, device count 1, torch available.

## Phase B — full loader-process A/B (no overlap, unchanged serial order)

All runs (all three arms) executed on **RTX PRO 6000 Blackwell** — no GPU
mixing. Primary metric per steering: `NON_SAMPLING_TOTAL = FRR − sampling`.

### Per-run measured values (GPU | FRR | sampling | non-sampling, ms)

| Arm | m1 | m2 | m3 | m4 | m5 | m6 |
| --- | --- | --- | --- | --- | --- | --- |
| Control (RTX 6000) | 18568 / 4915 / 13653 | 10985 / 4743 / 6242 | 10657 / 4652 / 6005 | 10943 / 4903 / 6040 | 11201 / 4770 / 6431 | 10671 / 4658 / 6013 |
| Request-time worker | 14996 / 4609 / 10387 | 16755 / 4664 / 12091 | 16752 / 4705 / 12047 | 17160 / 5035 / 12124 | 16847 / 4667 / 12181 | 16827 / 4684 / 12143 |
| Pre-snapshot worker | 22528 / 4702 / 17825 | 16015 / 4769 / 11246 | 17858 / 4989 / 12869 | 22194 / 4989 / 17205 | 17233 / 4711 / 12522 | 15621 / 4721 / 10901 |

### Medians (6 valid measured runs)

| Metric | Control | Request-time worker | Pre-snapshot worker | Δ pre-snap vs control |
| --- | ---: | ---: | ---: | ---: |
| restore (platform window) | 826.0 | 812.3 | 660.0 | — |
| worker start/wake (pre-snapshot: probe PONG) | — | 5488.0 (startup) | 9.0 | — |
| worker session init | — | — | 143.9 | — |
| worker CUDA first touch | — | (in 5488) | 3998.3 | — |
| CLIP worker load | (1723.3 in-process) | 1804.1 | 2135.0 | — |
| CLIP IPC handoff | — | 34.7 | 34.0 | — |
| CLIP parent rebind | — | 213.1 | 217.3 | — |
| CLIP forward | 1507.5 | 1420.9 | 1676.3 | +168.8 |
| UNET worker load | (2018.4) | 1932.6 | 2215.1 | — |
| UNET IPC handoff | — | 31.9 | 39.8 | — |
| UNET parent rebind | — | 25.4 | 31.1 | — |
| sampling | 4756.8 | 4675.0 | 4744.6 | — |
| VAE worker load | (98.8) | 102.4 | 118.1 | — |
| VAE parent rebind | — | 19.2 | 20.3 | — |
| decode | 532.5 | 526.6 | 574.2 | +41.7 |
| output | 160.9 | 159.3 | 162.0 | — |
| **FIRST_RESULT_READY** | **10964.4** | **16790.9** | **17545.5** | **+6581.1** |
| sampling | 4756.8 | 4675.0 | 4744.6 | −12.2 |
| **NON_SAMPLING_TOTAL (primary)** | **6141.0** | **12107.4** | **12695.4** | **+6554.4** |

Decomposition of the pre-snapshot arm's non-sampling total (median ms):
probe PONG 9 + session init 144 + child CUDA first touch 3998 + worker loads
4468 + handoffs 96 + parent rebinds (in stages) 269 + remaining parent stages
≈ 2.3k (forward 1676, decode 574, prepare 200, output 162, VAE 20 …) plus a
~1.0–1.1k run-level residual from boundary/gap accounting.

## Answers

1. **Child survived the CPU snapshot?** Yes — same PID, start-ticks, UUID,
   PPID, and pipe fds in 7/7 runs; `spawn_count` stayed 1 (no respawn).
2. **Existing IPC channel survived?** Yes — same fds, PING→PONG median
   3.9 ms, PONG 9.0 ms after the restore boundary.
3. **Was worker init removed from request-time FRR?** Partially: the
   spawn+import startup (1664 ms, done pre-snapshot) is gone, but the
   still-required post-restore pieces (probe 9 + session init 144 + CUDA first
   touch 3998 = ~4151 ms) remain on the request path vs the previous
   5488 ms request-time startup — a net ~1.34 s of process overhead removed,
   consumed by ~0.6 s slower restored-child loads and stage noise.
4. **Post-restore worker startup/wake/CUDA cost:** wake/PONG 9.0 ms; session
   init 143.9 ms; CUDA first touch 3998.3 ms (that is the dominant remaining
   loader-process cost).
5. **CUDA IPC handoff still works identically?** Yes — exact same path and
   proofs: UNET `same_storage_count=453/453`,
   `post_qd_allocation_delta_bytes=0`, `adoption_peak/skeleton_peak=0`,
   `assign_mode=assign_true`; CLIP `compute_scope_storage_proven=true`; VAE
   244/244 parameters; `parent_allocated_delta_bytes=0` for all three models.
6. **Any duplicate source read / H2D / parent allocation?** No — worker H2D is
   the single physical copy (8,044,936,192 / 12,309,817,472 / 335,278,732
   bytes; source read counts 243 / 370 / 13), parent allocation delta 0.
7. **Every run exact?** Yes — 7/7 treatment runs and 6/6 control runs returned
   the canonical SHA `790c3052…`, `valid=true`, seriality clean.
8. **Residual non-sampling delta after pre-spawning?** +6554.4 ms vs control
   (12695.4 vs 6141.0); vs the previous request-time worker arm it is
   +588.1 ms (12695.4 vs 12107.4).
9. **Where does the residual come from?** Child post-restore CUDA first touch
   (~4.0 s) + slower restored-child loads (~0.6 s: CLIP 2135 vs 1804, UNET
   2215 vs 1933) + IPC handoffs/rebinds (~0.36 s) + parent-stage shifts
   (forward +169 ms, decode +42 ms) + ~1.0 s run-level residual. The
   pre-snapshot arm saved ~1.34 s of spawn/import but paid ~0.6 s in slower
   restored-child reads and ~0.4 s in extra stage/noise, so it is net slower
   than the request-time arm on the primary metric.
10. **Close enough for UNET-load/CLIP-forward overlap?** No. The remaining tax
    is dominated by the child's post-restore CUDA first touch (~4.0 s) and
    slower restored-child loads, neither of which the serial UNET↔CLIP-forward
    overlap can hide (CLIP forward is only ~1.4–1.7 s). A more promising
    overlap for a later experiment would be the child CUDA first touch during
    the restore window (not tested here; overlap intentionally excluded).

## GPU fallback policy (per steering)

Mechanism already present: `gpu_catalog.parse_gpu_request()` builds an ordered
`(primary, *fallbacks)` tuple from `COMFYMODAL_V2_GPU` +
`COMFYMODAL_V2_GPU_FALLBACKS` (comma-separated), passed to Modal's `gpu=[...]`.
Modal documents that it **respects list ordering** and falls back in order.
For future cohorts deploy with e.g.
`--set COMFYMODAL_V2_GPU=rtx-pro-6000 --set COMFYMODAL_V2_GPU_FALLBACKS=h100,a100-80gb,h200`.

## Auditability

- Worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`
  (branch `TESTING2`); starting HEAD `eebea83`; prior commits `b815106`,
  `accf345`, `c3aceb3`; implementation commit `0d9a75c`.
- App names / fingerprints:
  - control (reused existing cohort): `batch-lproc-control`, fp
    `51b266577c0a9f0cd325f4b0ed6a6a073bcec78193ec063fc122378c8c1ea155`
  - request-time worker arm: `batch-lproc-full`, fp
    `f62148e14a65b0d6d59026583eba5c7c0d232b7b41f448de11cb3c59b0fd79e2`
  - pre-snapshot arm: `batch-prelproc-full`, fp
    `f4b837e2fd5db603b54af4393604f352f7989562ae23f5f60b05960c4979872b`
    (receipt `receipt_5_…`), profile `golden_p1_parallel`, flags
    `COMFYMODAL_GOLDEN_LOADER_PROCESS=1`,
    `COMFYMODAL_GOLDEN_LOADER_PROCESS_PRESNAPSHOT=1`, GPU `rtx-pro-6000`.
- Control config identical profile/workflow/output contract, both loader flags
  OFF (default).
- Report: this file.
- Boundary summaries: `artifacts/loaderproc_ab/presnapshot/final_ab_summary.txt`
  (all three arms), `…/treatment_boundary_summary.txt`,
  `artifacts/loaderproc_ab/boundary_summary.txt` (control).
- Raw artifacts (pre-snapshot arm, `artifacts/phase_p1_parallel_golden_v1/`):
  exclusion `cohort_2026-09-12_01-20-00_6a2478`; measured
  `_01-21-43_826d02`, `_01-27-37_b0ba4f`, `_01-28-21_e58427`,
  `_01-30-05_a28624`, `_01-32-43_73603c`, `_01-33-29_38c5ef`.
- Raw artifacts (control): `cohort_2026-09-11_19-52-05_4e5b64` (exclusion) +
  `_19-55-23_ea4653`, `_19-58-37_274187`, `_20-09-16_7470c9`,
  `_20-11-56_7aa22d`, `_20-14-03_506d01`, `_20-16-01_12caed`.
- Raw artifacts (request-time worker): `cohort_2026-09-11_21-48-03_0bf378` +
  `_21-49-44_dd655c`, `_22-05-12_113718`, `_22-55-41_56a694`,
  `_23-02-39_cd8cee`, `_23-03-35_564b53`, `_23-05-11_9484d8`.
- Excluded/invalid attempts (kept):
  - `cohort_2026-09-11_23-49-23_b7c0e4` — first pre-snapshot attempt, child
    `comfy_aimdo` import failed (no diagnostic yet).
  - `cohort_2026-09-12_00-02-15_0ee31d`, `_00-02-41_69444a` — child CUDA
    failure with full cause chain.
  - `cohort_2026-09-12_00-43-49_1ecded` — CUDA visibility diagnosis run
    (`cuInit=100` / device nodes present / stale env).
  - `batch-prelproc-control` deploy `deploy_20260911-203653_e41d9537` —
    abandoned per steering before any run; not used.
- Run manifests: `.v2ctl/runs/run_20260911-{185127_0afaf49e,190227_0921e5ea,191048_0921e5ea,194759_ab496df8,202041_747a690f,202722_747a690f,202805_747a690f,202940_747a690f,203228_747a690f,203314_747a690f,203425_747a690f}.json`.
