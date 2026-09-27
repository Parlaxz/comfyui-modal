# Golden Loader-Process A/B — implementation + boundary audit (2026-09-11)

## Implementation (kept, disabled by default)

- New module: `comfymodal_runtime/golden_loader_process.py`
  - One persistent `multiprocessing` `spawn` worker (`GoldenLoaderProcess`).
  - Serial tickets only (`clip` → `unet` → `vae` order defined, no overlap).
  - `start()` returns separate `worker_startup_ms` so startup is never hidden
    inside a model-load timer; `golden_parallel` emits
    `golden_loader_process_started` with `worker_startup_ms` + `worker_pid`.
  - Child returns picklable metadata only; any request for actual model state
    fails closed with `loader_process_handoff_invalid`.
- Gate: `COMFYMODAL_GOLDEN_LOADER_PROCESS` (default `0`/OFF), registered in
  `config/v2/flag_registry.toml` (`method_entry`, `change_requires=deploy`,
  owner `golden-loader-ab`).
- Wiring: `comfymodal_runtime/golden_parallel.py::golden_parallel_execute`
  checks the flag first. Default OFF path is byte-for-byte the previous serial
  composition (restore → setup → CLIP load → CLIP forward → UNET load →
  sampler prepare → VAE load → sampling → tail → decode → output). ON path
  starts the worker, records startup, then fails closed before any loader
  without reloading or copying payload.
- No new dependencies, no loader algorithm change, no overlap, no refactors.
- Not integrated into production/default behavior.

## Loader return/ownership semantics (inspected)

- `golden_clip_load` (`golden_serial.py:10980-11651`): returns live upstream
  CLIP; parent keeps `session.clip`, `clip_owner(s)`, all QD owners,
  compute scope + identity. Shallow dict copies preserve SAME QD tensor
  objects (`11344-11353`).
- `golden_unet_load` (`golden_serial.py:12463-12665`): returns dynamic
  `CoreModelPatcher`; parent keeps `session.patcher`, `session.unet_owner`.
  `model.load_model_weights(dict(views), "", assign=True)` (`12620`) adopts
  views; `validate_unet_binding` proves `data_ptr` identity (453 tensors).
- `golden_vae_load` (`golden_serial.py:13347-13523`): returns live upstream
  VAE; parent keeps `session.vae`, `session.vae_owner`. `comfy.sd.VAE(...)`
  (`13410`) + `validate_qd_adoption` (`13448`) prove zero-copy adoption.
- Transport (`read_file_qd_gpu`, `golden_serial.py:6712+`): one contiguous
  CUDA `torch.empty` buffer (`6951`) + typed views (`5621-5627`, `7295-7300`)
  wrapped in `GoldenQDOwner` (`7302`); views valid only while owner lives
  (`4973-4980`). Pinned slots, CUDA events, threads, fds are process-local.
- Teardown: `release_staging()` only; "process exit owns CUDA/model reclaim"
  (`14306-14340`). No cross-process owner transfer exists.

## Handoff verdict: INVALID (literal path stopped)

`loader_process_handoff_invalid`: a `spawn` child has a fresh CUDA context;
`gpu_buf`, views, `GoldenQDOwner`, CUDA events, pinned slots, fds, threads,
and constructed `CLIP`/`CoreModelPatcher`/`VAE` are not picklable, and a
copied `data_ptr` integer is a dangling address. The parent cannot receive/use
the loaded model state without a reload or a full-payload copy. No CUDA-IPC
was invented; inference was not moved into the child. Independent Oracle
review concurs.

## Timing boundaries (audited, for the A/B when lanes clear)

- Recorder: `begin_stage` forbids overlap (`1440-1454`); `end_stage`
  (`1456-1486`) marks authoritative wall `entry → end/ready`.
- `golden_clip_load`: begin `11010-11011`, end `11614-11650` (after QD
  quiescence + adoption/readiness proofs). Return `11651`.
- `golden_clip_forward`: begin `11737`; ends before UNET (function through
  `12462`). Must NOT include UNET wait.
- `golden_unet_load`: begin `12474-12475`, end `12649-12664` (after
  `assign=True` adoption + `binding_validation` + quiescence + allocation
  anti-copy gates). Return `12665`.
- `golden_sampler_prepare` (`12671+`), `golden_sampling` (begin `12827`;
  TOTAL = recorder entry→END; `SAMPLER_TOTAL_START/END` separate), tail, then
- `golden_vae_load`: begin `13357-13359`, end `13500-13522`. Return `13523`.
- `golden_vae_decode`: begin `13546`, end `13612-13613`.
- `golden_output` → `FIRST_RESULT_READY` via `mark_first_result_ready`
  (`1665-1675`, call `13861`) in `off` mode (canonical:
  `encode → observed SHA/bytes → FIRST_RESULT_READY → return`). Strict mode
  uses `TRUE_FIRST_DURABLE_RESULT` instead.
- UNET-load audit rule: accept only the recorder `golden_unet_load` wall;
  reject any number spanning CLIP-forward tail or sampler-prepare head.

## Control configuration (frozen for the A/B)

- Profile `golden_p1_parallel` extends `golden_p1`:
  `ModalRuntimeEntrypointV2::run_golden_parallel_stream`, GPU `rtx-pro-6000`,
  expected PNG SHA
  `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`
  (serial-canonical SHA in `golden_p1.toml:25` is
  `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d`;
  confirm which SHA the parallel path emits on the first run and freeze it).
- Current best flags: `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=1`,
  `COMFYMODAL_GOLDEN_CPU_QD2_PREFETCH=1`,
  `COMFYMODAL_GOLDEN_QD_TRANSPORT=static_e27`,
  `COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=0`,
  `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=0`,
  `COMFYMODAL_GOLDEN_RES4LYF_GC_SUPPRESSION=1`,
  `COMFYMODAL_OUTPUT_DURABILITY=off`.

## Remote A/B status: BLOCKED (execution lane down, awaiting ready)

- `bash` tool returns `OpenCode session is not bound to a Paseo agent` for
  every command, so `v2ctl golden deploy/run` cannot be issued from this
  session. No control runs were collected; no values are fabricated.
- When lanes clear, procedure (per `comfymodal-golden-ops`, serially, one
  request per invocation):
  1. Isolated experimental app; `doctor`/`golden status`; freeze source.
  2. `golden deploy`; `source-probe`; `ready=True`, no overrides.
  3. Control: 1× `golden run` (snapshot-build exclusion, mark INVALID if
     `SNAPSHOT_CAPTURE` + discard the directly-following request too), then
     6 valid runs; preserve all raw manifests/logs; record restore, CLIP
     load, CLIP forward, UNET load, sampler, VAE load, decode/output,
     FIRST_RESULT_READY from raw recorder walls; verify canonical SHA.
  4. Treatment: same deployment settings with
     `COMFYMODAL_GOLDEN_LOADER_PROCESS=1` deployed; expected result is
     fail-closed `loader_process_handoff_invalid` with separate
     `worker_startup_ms` — record it as such, do NOT reload/copy to force
     a green run.
  5. Fill the table below from medians of the 6 valid runs + raw values.

## Report table (pending remote evidence)

| Metric             | Current control | Loader process | Δ |
| ------------------ | --------------: | -------------: | -: |
| CLIP load          | PENDING         | INVALID PATH   | - |
| CLIP forward       | PENDING         | INVALID PATH   | - |
| UNET load          | PENDING         | INVALID PATH   | - |
| sampler            | PENDING         | INVALID PATH   | - |
| VAE load           | PENDING         | INVALID PATH   | - |
| FIRST_RESULT_READY | PENDING         | INVALID PATH   | - |

Raw runs: none collected yet (see blocked status). Bad runs will be kept and
marked, never deleted.

## Answers (current)

1. Literal loader-process handoff technically valid? **No** — stopped with
   `loader_process_handoff_invalid` (reason above).
2. Any model payload reloaded/copied across the boundary? **No** — the
   implementation refuses instead of reloading/copying.
3. Output exact? **N/A** — treatment cannot produce output on the invalid
   path; control exactness pending runs (canonical SHA gate applies).
4. FIRST_RESULT_READY better/worse/flat? **Unknown** — pending runs.
5. Which load stages changed? **None by default** — OFF path is unchanged;
   ON path fails closed before any loader.
