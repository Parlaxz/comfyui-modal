# Loader-Process A/B — control baseline + publication-generation fix (2026-09-11)

App: `batch-lproc-control` · profile `golden_p1_parallel` · method
`run_golden_parallel_stream` · RTX PRO 6000 · source HEAD `eebea83` (TESTING2)
· deploy fingerprint `51b266577c0a9f0cd325f4b0ed6a6a073bcec78193ec063fc122378c8c1ea155`
· deploy manifest `.v2ctl/deployments/deploy_20260911-144908_51b26657.json`
· canonical output SHA-256 `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d`.

## 1. Loader-process handoff verdict: INVALID (implementation path stopped)

The literal cross-process handoff of the three loaded models is impossible
with the existing ownership semantics, so no treatment arm exists to measure:

- `golden_clip_load` returns a live upstream `comfy.sd.CLIP` built from
  zero-copy QD CUDA views (`comfymodal_runtime/golden_serial.py:11348`,
  owner attached `:11376`).
- `golden_unet_load` returns a dynamic `CoreModelPatcher` whose parameters are
  `assign=True`-bound to QD views (`:12620`, return `:12665`, owner `:12646`).
- `golden_vae_load` returns a live `comfy.sd.VAE(sd=views, device="cuda", ...)`
  (`:13410`, return `:13523`, owner `:13460`).
- The storage is a process-local `torch.empty(..., device="cuda")` buffer
  (`clip_qd_reader.py:1647`, `golden_serial.py:5690/6466/6951`) owned by
  `QdGpuOwner` (`clip_qd_reader.py:1359-1365`): "zero-copy views ... only
  valid while this owner is alive".
- No `multiprocessing`/`shared_memory`/CUDA-IPC mechanism exists anywhere in
  the Golden path (grep: only `cpu_count`/`active_children` telemetry).
- The parent's fail-closed adoption proofs are per-process (`data_ptr`
  storage identity `validate_unet_binding:12139`, `validate_qd_adoption:12204`);
  a remapped address cannot satisfy them without rewriting the proofs.

The only ways the parent could use the models — a new CUDA-IPC
handle-export + wrapper-reconstruction architecture, CPU re-materialization +
re-H2D, or moving inference into the child — are explicitly out of scope.
Oracle review concurred (`INVALID`, no counterexample mechanism).

A parallel lane's kept, disabled-by-default implementation in this tree
(`comfymodal_runtime/golden_loader_process.py`, flag
`COMFYMODAL_GOLDEN_LOADER_PROCESS=0`) reaches the same fail-closed verdict
(`loader_process_handoff_invalid`) and was not modified or reverted here.

## 2. Control cohort (1 snapshot-build exclusion + 6 valid measured runs)

All runs: `valid=True`, `dnf=False`, `true_cold=True`, capture guard
`ELIGIBLE`, zero `SNAPSHOT_CAPTURE` events, `seriality.ok=True`, exact output
SHA. First app run excluded by the established per-app convention (kept).
Audit: no stage overlap; `golden_unet_load` starts strictly after
`golden_clip_forward` ends; sum(stage walls) reconciles to FRR within
3.1–3.9 ms. No measurement was accepted that folded a preceding wait into a
stage.

Median over the 6 measured runs (ms), raw values underneath:

| Metric                           | Control (median) |  Mean  | Raw values (run 2..7) |
|----------------------------------|-----------------:|-------:|-----------------------|
| CLIP load                        |           1723.3 | 2022.9 | 3213.5, 1622.6, 1716.3, 1484.9, 2369.7, 1730.3 |
| CLIP forward                     |           1507.5 | 1553.7 | 2074.3, 1514.8, 1385.1, 1503.1, 1511.9, 1333.4 |
| UNET load                        |           2018.4 | 2726.4 | 6766.6, 2110.0, 1950.9, 2034.5, 1494.2, 2002.2 |
| sampler                          |           4756.8 | 4773.6 | 4915.0, 4743.3, 4652.0, 4903.5, 4770.3, 4657.7 |
| VAE load                         |             98.8 |  173.3 | 548.1, 98.9, 91.2, 92.6, 98.6, 110.6 |
| FIRST_RESULT_READY (from golden_restore entry) | 10964.4 | 12171.0 | 18568.0, 10985.3, 10656.8, 10943.5, 11201.2, 10671.0 |

Additional recorded boundaries (medians): platform restore window 826.0 ms;
`golden_restore` 4.4 ms; request setup 2.6 ms; sampler prepare 204.4 ms;
sampler tail 0.011 ms; decode 532.5 ms; output 160.9 ms; FRR from platform
restore end 11070.2 ms.

Notes: measured#1 is a retained slow valid outlier (storage-cold CLIP/UNET
loads); measured#2's request wall absorbed ~10 min of platform queueing while
its internal stages stayed normal. Exclusion run (kept): request
`9784081e03ee`, CLIP load 6000.9 ms, UNET 4480.7 ms, FRR 18424.6 ms.

Requests: exclusion `9784081e03ee`; measured `26f6ad5ad417`, `d42336022cbd`,
`0740ce734405`, `950d4a489bc7`, `ca3bf19456fc`, `ab77d3df3a3a`.
Run manifests: `.v2ctl/runs/run_20260911-{145318,145740,150821,151058,151259,151459,152024}_7eb9b6e6.json`.

## 3. Publication-generation fix (unblocks deploys)

`tools/v2_control/cli.py`:
- `_resolve_publication_generation` replaces the fail-closed
  `_assert_publication_generation`: a `published_verified`/receipt-verified
  publication is authoritative; a pre-publication mismatch is logged
  (`[custom_nodes.publish] pre-publication generation differs...`) and never
  blocks. Missing verified generations and real publication/verification
  failures still fail closed.
- The final deploy fingerprint is captured only after the resolved generation
  is known; the resolved generation feeds the final `require_ready` preflight.
- Log line (produced live): `[v2ctl.deploy] desired_generation=...
  verified_generation=... resolved_generation=... fingerprint=...`.

Evidence:
- Two identical dry-runs: `deploy_fingerprint=51b26657...`,
  `run_fingerprint=7eb9b6e6...` (only the per-invocation ID differs; not a
  fingerprint input).
- Real Golden Parallel deploy exit 0: generation `54242a20...`
  desired = verified = resolved, `READY_FOR_CONSUMER_DEPLOY=YES`,
  fingerprint `51b26657...` (matches dry-run), receipt
  `.v2ctl/deployments/receipt_1_51b26657....json`.
- `source-probe` PASS/MATCH; `golden status` `deployment_fingerprint_match=True`.
- Focused FAST_UNIT: 59 passed (rx9p control plane, s2 deploy contracts,
  golden deploy version verification).
- Fingerprint investigation: dry-run and deploy share the canonical
  `FingerprintEngine` logic; the earlier `d35f2bd4 → ab851460` delta was
  concurrent third-party edits to deploy-relevant paths
  (`comfymodal_runtime/`, `config/v2/`) between those invocations. No
  timestamps/randomness/ambient inputs are present in the fingerprint.
- Pre-existing failures unrelated to this change (reproduced on unmodified
  HEAD): `test_config_golden_p1_uses_dedicated_target_method_and_flag`
  (profile memory 8192 vs dirty-tree 16384), two
  `test_s1_publisher_bootstrap` cases, and 19
  `test_custom_node_redeploy` cases (git common-dir resolution in the test
  environment).

## 4. Evidence

- Boundary summary + raw values: `artifacts/loaderproc_ab/boundary_summary.txt`
- Raw attempts (hashed): `artifacts/phase_p1_parallel_golden_v1/cohort_2026-09-11_{19-52-05_4e5b64,19-55-23_ea4653,19-58-37_274187,20-09-16_7470c9,20-11-56_7aa22d,20-14-03_506d01,20-16-01_12caed}/attempt_0.json`
- Dry-run / deploy / source-probe logs: `artifacts/loaderproc_ab/{dryrun_1,dryrun_2,deploy_batch-lproc-control,source_probe}.txt`
- Per-run command logs: `artifacts/loaderproc_ab/run_logs/`
- Auto-generated evidence MDs: `EXPERIMENT_EVIDENCE_golden_p1_parallel_*_2026-09-11.md`

## 5. Answers

1. Literal loader-process handoff technically valid? **No** — process-local
   CUDA-backed live model objects; no transfer mechanism; per-process
   adoption proofs. Path stopped per instructions.
2. Any model payload reloaded/copied across the process boundary? **No.**
   No process hop was measured; the invalid path would require a reload or
   payload copy, which is why it was stopped.
3. Output exact? **Yes** for control (all 7 requests, canonical SHA).
   Treatment N/A.
4. FIRST_RESULT_READY better/worse/flat? **N/A (no valid treatment).**
   Control median 10964.4 ms over 6 valid runs.
5. Which load stages changed? **N/A (no valid treatment).** Control stage
   medians are in §2.
