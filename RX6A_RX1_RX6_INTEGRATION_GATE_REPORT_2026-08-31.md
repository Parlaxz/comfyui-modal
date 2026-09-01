# RX6A — RX1–RX6 Integration Gate Report

Date: 2026-08-31

## Canonical state

- Canonical branch: `TESTING2`
- Canonical pre-integration HEAD: `e60e605d96a28dc451f2248851210bcc6c68ee11`
- Final canonical HEAD: `76f0d2a5c2f7a2a0f3e1c8ca8d0e1755752827e2`
- The pre-existing newer dirty work and untracked files were preserved. No
  reset, stash, clean, revert, forced checkout, or unrelated staging was used.

## Integrated commits

The lane commits were integrated by non-destructive semantic replay. The
resulting canonical commit IDs are listed beside each source commit.

### Runtime implementation

- RX1 `749b6cc89e35e2896dfeef5f13502440c0021ef2` → `21d56c7eed0a395bc616a0b693671563c3ba972d`
- RX2 `97cb9cbfb6e5ed80df447685d861fe88d6ecbebd` → `caaa945416a5469cb9a84c4cfb92c548654091d1`
- RX3 `85dc140bb5c839b919f92bf87c7ecc3e9daa4436` → `d8e78649e4add9ef98a2037506276d49e8e34ebb`
- RX6 `fdcb1be0cc339489fb74e534ede8030add1ee885` → `8f7db36445fb1020f84dae6e459d5881c126f47f`

### Closure reports

- RX1 `960fee02317d396672f6a537b994295737d0151a` → `fd4e346837bf7b1ed1da7a557beaef110b38ceca`
- RX2 `90457b43c18826431e2d263893678b8085f4bee5` → `421a9dd25c4d99ec0c3cafc2620ead9bb3e4255f`
- RX3 `6f889dff2c72655fbe1099ac259dddfae344391a` → `c67c7caf58aa0892cf9f81fa96b8b1f8057475d0`
- RX6 `52adf9f41d788e2c53bf3b000d231688cf402b55` → `76f0d2a5c2f7a2a0f3e1c8ca8d0e1755752827e2`

RX4 report commit `707419aa9d2c24d3f6813f788858f4a7683c3e87` and RX4 canonical
finalization commit `e60e605d96a28dc451f2248851210bcc6c68ee11` were already on
canonical history. RX5 remained represented by its existing report commit
`707419aa9d2c24d3f6813f788858f4a7683c3e87`.

## Conflicts and resolutions

- RX1, RX2, and RX3 all overlapped newer canonical edits in
  `comfymodal_runtime/golden_serial.py`. The lane telemetry/decomposition
  behavior was retained while the newer canonical CLIP hydration, FP32
  ownership, residency, and configuration changes were preserved.
- RX6 overlapped newer canonical lifecycle work in
  `comfymodal_runtime/modal_app.py`. The post-result log/tail cleanup was
  retained without replacing the newer modal lifecycle behavior.
- No report-file conflicts required content loss. Existing RX4/RX5 report
  files remained unchanged.

## Exact files changed by the RX integration

- `__init__.py`
- `comfymodal_runtime/clip_conditioning_cache.py`
- `comfymodal_runtime/golden_qd_transport.py`
- `comfymodal_runtime/golden_serial.py`
- `comfymodal_runtime/modal_app.py`
- `comfymodal_runtime/sampling_deep_profile.py`
- `tests/test_golden_qd_transport.py`
- `tests/test_golden_sampling_diagnostics.py`
- `tests/test_p2_golden_snapshot_adapter.py`
- `tests/test_ra9c_golden_qd_integration.py`
- `tests/test_rx3_clip_forward_decomposition.py`
- `tests/test_v2_sampling_deep_profile.py`
- `tests/test_waterfall_restoration_wiring.py`
- `RX1_QD4_TELEMETRY_REPAIR_REPORT_2026-08-31.md`
- `RX2_GOLDEN_SAMPLING_FULL_WALL_DECOMPOSITION_REPORT_2026-08-31.md`
- `RX3_CLIP_FORWARD_DEEP_DECOMPOSITION_REPORT_2026-08-31.md`
- `RX6_GOLDEN_LOG_CLEANUP_AND_POST_RESULT_TAIL_REPORT_2026-08-31.md`

All six required dated RX1–RX6 reports exist in the final worktree.

## Verification

- RX1 focused tests: **56 passed**.
- RX2 focused tests: **54 passed**.
- RX3 focused tests: **9 passed**.
- RX6 focused tests: **28 passed**.
- Relevant Golden regression suites: **268 passed, 0 failed, 3 skipped**.
- Combined RX-focused run: **164 passed, 2 failed**. The two failures are
  pre-existing exact-source-string assertions in
  `tests/test_waterfall_restoration_wiring.py` against newer dirty Studio
  adapter work; the RX6-focused snapshot adapter suite passed independently.
- Changed Python files compiled successfully with `python -m py_compile`.
- `git diff --check` passed for both the working tree and the integration
  range.
- No remote Modal deployment or Golden run was performed in this integration
  gate.

## Scope confirmations

- RX4 remained research/design-only; RX4 runtime code: **NONE**.
- RX5 remained research-only; RX5 runtime code: **NONE**.
- No RX7 optimization was introduced. The integration contains no QD
  scheduling change, dispatcher-loop optimization, dedicated CUDA stream,
  H2D-size change, new cast-once conclusion, sampler optimization,
  CLIP-forward optimization, or parallelization.
