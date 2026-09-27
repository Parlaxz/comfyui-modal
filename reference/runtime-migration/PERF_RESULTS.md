# Performance results

No trustworthy new baseline has been recorded yet. The external Modal and
Playwright cold-run harness must be run with the existing production workflow,
model stack, GPU, seed, and output settings before performance conclusions are
made. Unavailable runs will be recorded as unavailable rather than fabricated.

## Existing baseline artifact (reference only)

Source: `playwright-cold-benchmark-2026-07-16.json`.

- Direct median wall time: 25,245 ms; p90/max are not meaningful from only
  three runs. Playground median: 29,493 ms.
- Direct restore median: 6,338.7 ms; inference median: 8,896.3 ms; remote
  median: 14,682.84 ms.
- Direct traces report `cold_unet_early_load_status=not_started` and
  `cold_unet_graph_wait_ms=0`; graph UNET wait is still about 4.8 s. This is
  not evidence of useful early overlap.
- Playground reports `production_plan_used=yes`; direct output node is `107`.
- The artifact has no selected-backend or output-source field, so those facts
  cannot be inferred honestly from it.

## Truthful local baseline run

Captured during this migration before production changes:

- Focused legacy suite: **121 passed, 17 failed** in 14.98 s. Failures are
  existing packaging/production-sink AST/API mismatches at the anchor; they
  were not introduced by this migration.
- Local ComfyUI port 8188: available.
- Modal credentials: unavailable (`MODAL_TOKEN_PRESENT=False`), so no paid cold
  generation was attempted.
- Real Playwright cold spec: **NOT_RUN: local `node_modules/@playwright/test`
  is absent**. The attempted `npx playwright test ...` failed before browser
  launch with `ERR_MODULE_NOT_FOUND`.
- A fresh `python run_tests.py` attempt was started from the checkout and hit
  the 120-second execution limit while the existing packaging-heavy suite was
  still running. It produced no complete aggregate result and is not used as a
  pass/fail claim. Focused migration gates remain separately reported.

## Baseline diagnosis before extraction

1. Early UNET is `not_started` because `COLD_UNET_EARLY_LOAD` defaults to
   false (`comfyapp.py:986`) and the recorded request did not provide the
   request-level `modal_options.runtime.cold_unet_early_load.enabled` override.
   The normal direct UNET preload and direct warmup UNET flags also default to
   false; the graph therefore pays its own UNET load.
2. Backend selection is statically `in_process` by default
   (`comfyapp.py:355`), with a sticky subprocess fallback only after startup
   failure (`comfyapp.py:15022`). The baseline artifact does not record the
   selected backend, so the run-specific selection remains **unobserved**.
3. The current in-process collector first attempts the production direct-memory
   registry, then executor history, prompt-queue history, request-window file
   scan, and an unrestricted recent-files fallback when no request boundary is
   available (`comfyapp.py:14521-14840`). The artifact does not record which
   source succeeded; collector selection is therefore **unobserved**.
4. Restore-affecting fields are the normalized model profile (mode,
   checkpoint or UNET/CLIP/VAE identities, CLIP type, explicit loader config),
   model-generation identity, and—when exact prefill is enabled—the prompt
   bundle hash (`warmup_profile.py:49-113`). Prompt-only fields currently alter
   the combined stable key when exact prefill is enabled; they should become a
   separate `PrefillKey` in v2.
5. Normal generations write runtime-config files such as active profile,
   last-model-stack, known-good profiles, dependency/sage caches, and
   validation certificates. These schedule runtime-config commits through the
   legacy per-label worker. The inspected code explicitly documents that it
   does not commit the models Volume, but no complete per-request write/commit
   report is emitted yet.
6. Trace overhead is not measurable from the captured artifact: it has no
   paired profile-off/profile-on run with identical settings. Deep profiling is
   env-gated in `_execute_in_process`; treat overhead as **unmeasured**, not
   zero.
