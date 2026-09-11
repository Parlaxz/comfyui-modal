# Full Golden loads in a spawned process — A/B result (2026-09-11)

App: `batch-lproc-full` · profile `golden_p1_parallel` · method
`run_golden_parallel_stream` · deploy fingerprint
`f62148e14a65b0d6d59026583eba5c7c0d232b7b41f448de11cb3c59b0fd79e2` · flag
`COMFYMODAL_GOLDEN_LOADER_PROCESS=1` (deploy-baked) · source-probe PASS/MATCH ·
canonical output SHA `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d`.

## Mechanism (works)

- One persistent `multiprocessing` `spawn` worker
  (`comfymodal_runtime/golden_loader_process.py`) runs the three real
  canonical loaders (`golden_clip_load` / `golden_unet_load` / `golden_vae_load`)
  serially, including their full QD source read + H2D (8.04 GB / 12.31 GB /
  0.34 GB) and construction.
- The worker sends the adopted CUDA view tensors to the parent through a
  `torch.multiprocessing` pipe; PyTorch's CUDA-IPC reductions share the
  existing device storage. The parent re-binds with the *same* canonical
  loaders via a `preloaded_transports` / `preloaded_transport` injection path
  (zero transport I/O, no second H2D) and runs the same fail-closed
  pointer-identity proofs.
- Each preloaded transport carries a parent-side `GoldenQDOwner` around the
  same IPC-mapped base buffer, so owner registration/teardown keeps working.
- The worker stays alive for the whole request and is stopped only after
  Golden teardown.
- Literal wrapper transfer (sending the constructed `CLIP` /
  `CoreModelPatcher` / `VAE` objects) is blocked and was probed at runtime
  every run: `Can't pickle local object 'te.<locals>.ZImageTEModel_'`,
  `'model_sampling.<locals>.ModelSampling'`, `'VAE.__init__.<locals>.<lambda>'`
  (plus `ModelPatcherDynamic`'s native AIMDO `HostBuffer`/`ModelVBAR`
  ctypes handles). Only the CUDA storage can cross, which is what this
  implementation does.

## Control vs treatment (medians over 6 valid measured runs, ms)

| Metric (median) | Control | Treatment | Δ |
| --- | ---: | ---: | ---: |
| CLIP load | 1723.3 | 2061.9 total = worker 1804.1 + handoff 34.7 + rebind 213.1 | +338.6 |
| CLIP forward | 1507.5 | 1420.9 | −86.6 |
| UNET load | 2018.4 | 1996.6 total = worker 1932.6 + handoff 31.9 + rebind 25.4 | −21.8 |
| sampler | 4756.8 | 4675.0 | −81.8 |
| VAE load | 98.8 | 146.8 total = worker 102.4 + handoff 20.7 + rebind 19.2 | +48.0 |
| decode | 532.5 | 526.6 | −5.9 |
| FIRST_RESULT_READY | 10964.4 | 16790.9 | +5826.5 |
| worker startup (treatment only) | — | 5488.0 | — |
| IPC handoff, all three (treatment only) | — | 87.3 | — |

Raw treatment values (m1..m6): CLIP worker `1384.7, 1789.6, 1860.1, 1587.0,
1854.0, 1818.5`; CLIP handoff `23.7, 39.7, 35.3, 25.3, 53.0, 34.2`; CLIP rebind
`173.9, 219.0, 206.5, 216.4, 209.8, 222.9`; UNET worker `1460.1, 2054.4,
1934.7, 2100.9, 1574.9, 1930.5`; UNET handoff `26.9, 31.9, 38.9, 30.2, 31.9,
38.0`; UNET rebind `23.7, 23.8, 26.2, 81.0, 26.0, 24.9`; VAE worker `80.4,
100.0, 104.8, 125.9, 96.7, 105.3`; VAE handoff `17.1, 28.9, 25.7, 14.9, 20.4,
20.9`; VAE rebind `17.7, 19.0, 22.0, 19.1, 20.3, 19.4`; FRR `14995.7, 16754.7,
16751.8, 17159.5, 16847.4, 16827.0`; worker startup `5133.2, 5523.8, 5462.7,
5413.2, 6006.7, 5513.2`. Control raw values: `artifacts/loaderproc_ab/boundary_summary.txt`.

Stage semantics note: in the treatment the parent `golden_*_load` stage timers
measure only the parent re-bind (canonical construction + proofs on the
IPC-mapped views); the actual load work is the separately-recorded worker
time. The unaccounted FRR residual (median 9463.9 ms) equals worker startup +
the three worker loads + handoffs.

## Proofs recorded per run

- No duplicate payload/H2D: parent `parent_allocated_delta_bytes = 0` for all
  three models in all 6 runs; worker H2D bytes are the single physical copy
  (8,044,936,192 / 12,309,817,472 / 335,278,732).
- CUDA storage identity: `golden_unet_load` parent proof
  `same_storage_count=453/453`, `post_qd_allocation_delta_bytes=0`,
  `adoption_peak_delta_bytes=0`, `skeleton_peak_delta_bytes=0`,
  `assign_mode=assign_true`; CLIP `compute_scope_storage_proven=true`;
  VAE 244/244 parameters adopted.
- Lifetime: one worker pid alive across all three loads and the parent's
  forward/sampling/decode; stopped only after teardown.
- Exactness: 6/6 measured runs `output_sha_match=true`; `seriality.ok=true`;
  no stage overlap; UNET strictly after CLIP forward.
- Validity: all runs `valid=true`, `dnf=false`, `true_cold=true`, capture
  guard ELIGIBLE.

## Excluded/invalid attempts (kept)

- `6c454a` request `e306d9a7e6b9`: first run of the app, flag passthrough not
  yet baked (normal-path run; evidence that no silent fallback happens).
- `412aea` request `4c92bdc5f81d`: first treatment attempt failed with
  `read_file_qd_gpu() missing 1 required keyword-only argument: 'role'`
  (worker capture-spy bug, fixed).
- `e63cde` / `6473bf`: requests killed by local command walls during a slow
  platform window (empty cohorts, no data).
- Treatment exclusion run: `0bf378` request `5229b0cedee4` (first successful
  treatment run).

## Environment notes

- Modal delivered 20–25 minute request walls during part of the campaign
  (one measured run took ~24 minutes wall while internal stages stayed
  normal); command walls were re-sized accordingly.
- Two deploys aborted with Modal's "resfile modified during build" for
  `RES4LYF\res4lyf.config.json`, rewritten by a locally running ComfyUI
  process; retried in a quiet window.
- Local fast-suite: 130 collected, 128 passed; the 2 failures
  (`test_rx9p_h_identity_chain.py`) are pre-existing stale-schema tests
  unrelated to these modules.

## Answers

1. Full CUDA-backed model handoff worked — the parent ran forward, sampling
   and decode on the worker-loaded models with `0` bytes of parent CUDA
   allocation and exact output.
2. Mechanism: PyTorch CUDA IPC (`torch.multiprocessing` shared-storage
   reductions) for the view tensors + the canonical preloaded re-bind path in
   the parent; the worker owns and outlives the storage.
3. No duplicate payload copy or H2D: one physical H2D per model in the
   worker; parent allocation deltas 0; 453/453 UNET pointers identical.
4. All three models remained usable by the parent (forward, sampling, decode,
   exact SHA).
5. Load times: worker-side loads are ~unchanged vs control (CLIP 1804 vs
   1723; UNET 1933 vs 2018; VAE 102 vs 99), plus 20–35 ms IPC handoff and
   19–213 ms parent re-bind each.
6. FIRST_RESULT_READY worsened by ~5.8 s (16791 vs 10964 median), dominated
   by the serial worker startup (5488 ms) plus handoffs/re-binds; this is the
   cost of running the loads in a separate process with no overlap yet.

Implementation kept, disabled by default (`COMFYMODAL_GOLDEN_LOADER_PROCESS`
default `0`); the treatment app is the only deployment with it enabled.
