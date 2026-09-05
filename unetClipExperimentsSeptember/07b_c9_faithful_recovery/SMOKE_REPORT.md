# C9 Faithful Recovery — Smoke Gate

## Result

**FAIL / STOPPED before performance measurement.** Smoke A was run exactly as
specified: UNET, QD8, 32 MiB physical requests, CPU12, Testing 7/main, two
serial fresh-container requests, with a five-minute outer timeout.

Both requests reached the corrected Testing 7 deployment but failed before
the worker threads started:

```text
RuntimeError:source_pinned_buffer_page_lock_unavailable:mlock:12:Cannot allocate memory
```

The source-only container has no NVIDIA driver, so the historical Torch
`pin_memory=True` allocator is unavailable. The corrected no-GPU replacement
uses anonymous mmap plus libc `mlock`, but the Testing 7 worker rejects the
32 MiB page-lock request under its memory-lock limit. The implementation
correctly fails closed rather than silently measuring pageable memory.

Therefore neither request has `SOURCE_WALL_MS`, effective GB/s, physical
read evidence, or an eligible classification. No timing threshold can be
evaluated. Smoke B and the 36-observation cohort were not run.

## Raw evidence

- First request: `smoke_a_mlock/runs/20260905T045259_81f99b8f_c9_o01_unet_qd8.json`
- Second request: `smoke_a_mlock/runs/20260905T045259_81f99b8f_c9_o02_unet_qd8.json`
- Ledger: `smoke_a_mlock/ledger.json`
- Invocation log: `smoke_a_mlock.log`

Both raw artifacts prove:

- workspace deployment identity: Testing 7/main via the deployment manifest;
- requested CPU 12 and runtime-shape CPU 12;
- image `im-pRuoShxQdHkBw9S8WDefq2`;
- no CUDA/H2D/model construction;
- failure occurred during required pinned-buffer setup;
- no measured source result was produced.

## Gate decision

The fast-path claim is **unestablished**. Do not run Smoke B or the full
cohort until the environment can satisfy the required pinned-host-buffer
contract without adding CUDA/H2D to the primary source-only arm, or until the
experiment policy explicitly changes that requirement.
