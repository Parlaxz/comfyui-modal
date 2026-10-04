# P10 Agent 1 — persistent CLIP layout/meta cache + bounded UNET pre-resolve + VAE DynamicVRAM overlap

One combined bundle, deployed once, validated as a whole against
`Testing 1 (ws_e677ab553606)`.

**Verdict: ship tasks 1 and 5. Do NOT promote task 2.**

Tasks 1 and 5 reproduce their proven lineage on the current base with the exact
output SHA. Task 2 is correct, guarded and fail-soft, and it provably relocates
the work — but the targeted measurement shows it does **not** reduce the exposed
decode-time activation, so it does not meet its own success criterion.

---

## 1. Base and final SHA

| item | value |
|---|---|
| `BASE_SHA` | `ccc2c531bead6614d2435e3bd7fa157a900251a8` (= `origin/main`, verified after `git fetch`) |
| `HEAD` | `76e5c1ab7de6691aad468aad45158ef8d1451cc1` |
| `BRANCH` | `opt/p10-integration-cache-vae-unet` |
| `WORKTREE` | `.slim/worktrees/p10-agent1` (created for this task only) |

The dirty root checkout was never touched. Neither `.slim/worktrees/p8fix` nor
`.slim/worktrees/source-copy-isolation` was read or written. No worktree was
removed or pruned. No merge, no tag.

## 2. Commits (in order)

| SHA | subject | origin |
|---|---|---|
| `208b5b3c` | `perf(golden-unet): resolve the dynamic UNET layout during CLIP load` | cherry-pick of `2465d990`, clean |
| `73a37efb` | `fix(golden-unet): bound the layout pre-resolve join` | cherry-pick of `04dc0906`, clean |
| `69f45de5` | `perf(golden-clip): serve the layout/meta blueprint from a persistent cache` | cherry-pick of `e1bdddc`, 1 conflict resolved (below) |
| `76e5c1ab` | `perf(golden): overlap the VAE DynamicVRAM activation with sampling` | new work, this lane |

Base verified, not remembered: `git merge-base e1bdddc9 ccc2c531` ==
`ccc2c531`, i.e. the CLIP cache commit is a clean 22-commit descendant of main.

### The one cherry-pick conflict

`e1bdddc` was authored on top of `5b12fb47` (per-block source telemetry) and
`dce3c4ac` (source-stall classification). Its diff to
`golden_model_transport.py` therefore re-imported
`source_latency_telemetry` and `source_stall_classification`, neither of which
exists on this base. Resolved by keeping **only**
`from . import golden_model_metadata_cache`. Verified both modules are absent
(`Test-Path` False) and that the three apparent "usages" were the conflict
markers themselves. No arena-16-slot, Triton, or source-probe code was pulled in
— `git diff ccc2c531..HEAD --name-only -- config/ '*.toml'` is **empty**.

## 3. Was task 5 already present?

**`UNET_BOUNDED_JOIN_ALREADY_PRESENT=no`.** It was absent and was ported.

Evidence from the base, not assumed:

```
git grep -n "pre_resolve|preresolve" -- comfymodal_runtime   -> 0 hits
git grep -n "_parse_layout" -- comfymodal_runtime             -> golden_model_transport.py:304, :980 only
```

The task brief's SHA `fbd81c46` for the initial UNET pre-resolve work is
actually `fix(golden-c0): make the source-thread arena gate track its owning
module` (arena geometry — Agent 2's territory, deliberately not ported). The real
initial pre-resolve commit is **`2465d990`**, the parent of the bounded follow-up
`04dc0906`.

Note `04dc0906` states in its own message: *"Not deployed in this commit … it is
committed here as a reviewed follow-up and is explicitly unmeasured."* This
bundle is the first runtime evidence for the **bounded** join.

## 4. Source-level semantics

### 4.1 Persistent CLIP layout/meta cache (`e1bdddc`)

One normalized tensor table `(name, dtype, shape, offset, length)` serves both
layout parsing and CLIP metadata construction. No tensor objects are serialized.
Identity is `(canonical relative path, st_size, st_mtime_ns)` with the header
digest consulted **only** when the cheap identity disagrees. `st_dev`/`st_ino`
are deliberately not used.

The three previously-found defects are preserved by the ported regression tests:

| defect | guard | present |
|---|---|---|
| wrong mount path (`/root/...` vs V2 `/mnt/...`) | `CACHE_PATH` derives from `COMFYMODAL_V2_STATE_VOLUME_ROOT`; live run shows `/mnt/comfymodal_runtime_state/caching_data/golden_model_metadata.bin` | yes |
| memoized miss pins "absent" for container life | `hydrate()` memoizes **only** a successful load | yes |
| verification re-reads the header on every lookup | `lookup()` does `stat()` first; digest only on disagreement | yes |

Publisher is model-file truth (`ModalRuntimeEntrypoint.publish_model_metadata_cache`,
`v2ctl publish-model-metadata-cache`), hydration is warmed in `restore()`
immediately after `reload_runtime_state()`, i.e. off the request critical path.
Absent / corrupt / wrong-schema / truncated / stale / unknown all fall back to
the canonical parser with a visible `reason`.

### 4.2 Bounded UNET pre-resolve join (`2465d990` + `04dc0906`)

`golden_clip_load` (first checkpoint only) starts a background
`begin_layout_preresolve(unet_path)`. `golden_unet_load` joins it with
`LAYOUT_PRERESOLVE_JOIN_BUDGET_S = 2.0` and then **still performs its own
`inspect()`** — the exact existing parser, which remains the canonical operation.
On expiry the holder returns unfinished and `inspect()` simply does the parse,
i.e. exact pre-feature behaviour. Expiry is observable via
`LayoutPreresolve.completed` and `unet_layout_preresolve_join_completed`, so
"the join expired and this stage parsed inline" cannot be mistaken for a hit.

Dynamic semantics preserved: the UNET path comes from
`session.model_paths["unet"]`, no fixed-model assumption, unknown models work.

### 4.3 VAE DynamicVRAM relocation (new, `76e5c1ab`)

`comfymodal_runtime/vae_dynamicvram_overlap.py` + a hook in
`golden_sampling_vae_window`. After `golden_vae_load` returns, on the `vae_load`
leg, while `golden_sampling` still runs, it issues the **same canonical**
`model_management.load_models_gpu([patcher], force_full_load=vae.disable_offload)`
that `VAE.decode` makes. Activation semantics are unchanged and nothing is
faked; the decode-time call remains the canonical path for every failure.

Guard (audited §17): `id(vae) == id(session.vae)`, `id(patcher)`,
`patcher.is_dynamic()`, `load_device` unchanged; postconditions `registered`,
`resident = loaded_size() > 0`, `on_load_device`. Any miss returns a visible
record and leaves decode unchanged. No "no intervening eviction" clause was
added — audit §5 proves the VAE cannot be evicted before decode, and a vacuous
condition would read like a guarantee.

**Registry neutrality is a correctness requirement, not a nicety.**
`load_models_gpu` ends with an unconditional
`current_loaded_models.insert(0, loaded_model)` (verified in pristine `169fcf35`
and in the developer's local copy). `VAE.decode` calls it again unconditionally.
Leaving our entry behind would register the same `LoadedModel` **twice**, and
teardown's `free_memory(1e30)` walks the registry calling `model_unload` once per
entry — `model_unload` sets `self.model_finalizer = None` on its first call, so
the second call raises `AttributeError: 'NoneType' object has no attribute
'detach'`. The module therefore snapshots and restores
`current_loaded_models` around its call. The patcher's AIMDO host buffers, vbar
and `active=True` survive; the decode-time call re-derives its own single entry.

`_registered` compares registry entries by **identity**, not `in`/`__eq__`:
upstream stores `LoadedModel` and defines `LoadedModel.__eq__` as
`self.model is other.model`, while `ModelPatcher` defines no `__eq__`, so `in`
works only via reflected equality. Identity is what that `__eq__` means.

Overlap is **measured, not assumed**: the stage-pair bounds only exist after both
legs join, so `annotate_sampling_overlap` fills `inside_sampling` /
`hidden_by_sampling_ms` afterwards from real monotonic bounds.

Serial schedule untouched — with no concurrent sampling there is nothing to hide
behind, so relocating there would only move ~80 ms earlier and delay sampling.

## 5. Tests

| suite | result |
|---|---|
| `tests/test_golden_model_metadata_cache.py` + `tests/test_unet_layout_preresolve.py` + `tests/test_golden_metadata_precohort_cli.py` | **28 passed** |
| `tests/test_vae_dynamicvram_overlap.py` (new) | **21 passed** |
| broad transport/clip/source-probe selection, HEAD | 646 passed / 19 failed |
| the same selection on **pristine base** `ccc2c531` | 646 passed / **the identical 19 failed** |
| `python -m pytest tests -m fast_unit -q` on **base** | 2 failed, 563 passed, 7 skipped |
| `python -m pytest tests -m fast_unit -q` on **HEAD** | 2 failed, **591 passed**, 7 skipped |

The 19 broad-selection failures and the 2 fast-unit failures are **pre-existing on
pristine base** and byte-identical between base and HEAD (thumbnails/webp, model
library metadata, observability instrumentation, eviction, runtime_main). They
were documented, not "fixed".

The 2 pre-existing fast-unit failures are exactly
`tests/test_rx9p_h_identity_chain.py::test_success_path_exact` and
`::test_compact_nested_sage_observation_is_mismatch` — the two the `e1bdddc`
message itself names as pre-existing.

`+28` net new passing tests, **zero** new failures.

### Two honest caveats about the gates

1. **`tools/test_perf.py --fast` fails on pristine base too.** Base:
   `hard timeout exceeded (15.058s)` + `FAST_UNIT budget exceeded (6.393s max test
   wall)`. HEAD: same two failures with a **better** max test wall (4.684 s). The
   cause is `COLLECTION total_ms=5737` on this Windows host, not test behaviour.
   Per the AGENTS.md policy this was diagnosed rather than retried with a larger
   timeout, and the equivalent direct command was used.
2. **`test_three_model_hydration_is_bounded_and_compact` is a flaky wall-clock
   assertion**, not a regression. It failed once under full-suite load
   (`elapsed_ms < 75.0`), passes 5/5 in isolation, and passes on a full-suite
   re-run. Measured unloaded hydration of the same 6000-tensor / 84,660-byte
   blob: min 11.57, **p50 20.53**, max 33.10 ms — far inside the 75 ms budget.

## 6. Deployment identity

Destination is config-owned (`config/v2/modal_target.toml`); `v2ctl` rejects
`--workspace`/`--workspace-id` overrides by design.

Per the bundle rule, the workspace target was set **locally and left
uncommitted** (`git status` shows `M config/v2/modal_target.toml`, never staged):

```
workspace_id   = ws_e677ab553606
workspace_label = Testing 1
environment    = (default)
```

Verified through the project's own resolver, not by editing around it:
`modal_workspaces.resolve_modal_destination(".")` → `source=config/v2/modal_target.toml`,
`WORKSPACE_LABEL=Testing 1`, credentials present; every command printed
`DESTINATION_STATUS=VERIFIED` / `DEPLOYING TO=Testing 1 (ws_e677ab553606)`.
The shared registry at `.git/comfymodal/modal_workspaces.json` already had
Testing 1 active.

| role | app | fingerprint | source-probe |
|---|---|---|---|
| treatment | `p10a1-cache-vae-unet` | `5b2e43f003cffad566b2248dc3c15fbbdbc66616a83a80ee43c3c1b46ce45624` | `RESULT=PASS source_identity=MATCH`, `git_head=76e5c1ab7de6` |
| treatment (tracing) | `p10a1-cache-vae-unet` | `3bc9bb61…` | via `golden profile` |
| control (no VAE) | `p10a1-ctrl-novae` | `cc73efd5f99b2dace46c76d5afc71836b50ee733217d436964eda80126c4b6c3` | `RESULT=PASS source_identity=MATCH`, `git_head=69f45de5df11` |
| control (tracing) | `p10a1-ctrl-novae` | `a6b29c0a…` | via `golden profile` |

Profile: `golden_p1_parallel_c0_source_h100` (the only audited profile with both
`COMFYMODAL_GOLDEN_SAMPLING_VAE_SCHEDULE=overlap` and
`COMFYMODAL_GOLDEN_CLIP_UNET_SCHEDULE=overlap`, and
`expected_output_sha=3a6a0306…`). Method `run_golden_parallel_stream`, class
`ModalRuntimeEntrypointV2`, GPU `H100!`.

The control isolates **only** the VAE commit: `golden_serial.py` remote sha
`4ee22e38…` (treatment) vs `9ec3e060…` (control).

The protected production app was not touched. Two isolated experimental apps
were used; no source allowlists were added.

Metadata publication (required before the cohort, else every lookup falls back to
the canonical parser):

```
publish-model-metadata-cache -> RESULT=OK
cache_path=/mnt/comfymodal_runtime_state/caching_data/golden_model_metadata.bin
file_bytes=11811  runtime_config_volume=available
clip/unet/vae -> status=noop (identical identity already present from the P9 lane)
```

## 7. Correctness — 5 true-cold + 1 profile

`python -m pytest`-equivalent gates above; runtime cohort, serial, never
concurrent, no snapshot capture (`capture_guard.state=idle` throughout).

| # | request_id | valid | true_cold | restore_count | request_count | fallback | fatal | SHA |
|---|---|---|---|---|---|---|---|---|
| 1 | `golden-p1-0-7c106f3e7d7b` | yes | yes | 1 | 1 | None | false | exact |
| 2 | `golden-p1-0-4b2ddee3b2a7` | yes | yes | 1 | 1 | None | false | exact |
| 3 | `golden-p1-0-0cc5ecf178b2` | yes | yes | 1 | 1 | None | false | exact |
| 4 | `golden-p1-0-1fa7191eb561` | yes | yes | 1 | 1 | None | false | exact |
| 5 | `golden-p1-0-eaac7b1947d2` | yes | yes | 1 | 1 | None | false | exact |

`EXACT_SHA=5/5 = 3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`
`validation.output_sha_match=True` on every run.

Profiling request: trace `c0f2c09092c64ff9b024818a474a0484`,
`ROOT_WALL_MS=17216.14`, `ROOT_COMPLETE=True`, `THREAD_COVERAGE=COMPLETE (19/19 lanes)`,
`CLOCK_ALIGNMENT=PROVEN`. `GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE=NO` with the single
reason `no_root_corrupting_incomplete_calls: incomplete_calls=16` — fail-closed
and disclosed; the incomplete calls are not root-corrupting.

Per instructions the cohort was **not** expanded beyond 5+1; the extra 3 control
runs were spent on the one measurement the brief requires and that no prior lane
had (same-build decode-time A/B).

## 8. CLIP cache measurements (5/5)

| metric | proven P9 baseline | this bundle (n=5) |
|---|---|---|
| `layout_resolve_ms` (control) | **31.16** | — |
| `layout_lookup_ms` | 1.01 | **p50 1.178** (min 0.948, max 1.814, sd 0.335) |
| `clip_meta_cache_hit` | true | **true 5/5** |
| `layout_cache_source` | persistent | **persistent 5/5** |
| `metadata_cache_identity_match` | — | **true 5/5** |
| `metadata_cache_hydration_ms` | 5.50–7.83 | **p50 7.384**, max 62.444 |
| `residual_meta_build_ms` | 0.98–2.97 | p50 1.734 |
| `meta_blueprint_lookup_ms` | — | p50 0.644 |

`layout_resolve_ms` 31.16 → `layout_lookup_ms` **1.178** ≈ **-96%**, reproducing
the proven lineage on the current base. Hydration stays in restore (the
`golden_metadata_cache` event fires at mono 103.106 s, `REAL_RESTORE` at
103.102 s) with a 75 ms budget. The 62.444 ms outlier is a cold Volume read on a
sick host and still fits the budget; no fallback or miss reason was ever
recorded.

## 9. UNET pre-resolve measurements (5/5 + 3 control)

| metric | value |
|---|---|
| `status` | **completed 5/5** |
| `unet_layout_preresolve_join_completed` | **true 5/5** — bounded join landed inside its 2.0 s budget |
| bounded timeout / inline-parse fallback | **0 occurrences** |
| `completed_before_clip_forward` | **true 5/5** — no layout parse exposed later during CLIP forward |
| `layout_cache_hit` | **true 5/5** |
| `path_basename` | `z_image_turbo_bf16.safetensors` (from `session.model_paths`, dynamic) |
| `preresolve_ms` | p50 45.830 (min 13.967, max 56.891, sd 19.424) |

Empirical justification for the bound: **control run 2 measured
`preresolve_ms = 833.022`** on a sick host and still completed within budget
(`join_completed=true`). Without the 2 s cap that request would have put the
whole event loop behind a single header read — precisely the Production-009
failure shape the follow-up commit was written for.

## 10. VAE activation overlap measurements (5/5)

| metric | value |
|---|---|
| `status` / `reason` | **activated / ok 5/5** |
| `activation_ms` | 32.522, 80.053, 152.886, 51.478, 62.647 → **p50 62.647** |
| `inside_sampling` | **true 5/5** |
| `sampling_active_at_start` | **true 5/5** |
| `hidden_by_sampling_ms` | **== `activation_ms` exactly, 5/5** → 100 % hidden |
| `registered` / `resident` / `on_load_device` | true / true / true, 5/5 |
| registry before → during → after restore | `2 → 1 → 2`, `..._vae_count_after_restore=0` **5/5** |
| decode-time fallback invoked | **0** (the canonical decode-time call ran normally every time, as designed) |

The `80 ms` figures sit exactly in the audited exposed band (73.028 GOOD-fastest
/ 78.091 GOOD-healthy / 110.675 BAD), and `hidden_ms == activation_ms` is direct
evidence the work really landed under sampling rather than merely earlier.

`registry_entries_after_restore_vae_count=0` on every run is the direct proof
that the double-registration teardown hazard was avoided.

### 10.1 The exposed decode wall did NOT fall — measured, same build

Same-build A/B, profiled traces (`golden_vae_decode` → `VAE.decode`):

| | control `6f7ab945` | treatment `c0f2c090` |
|---|---:|---:|
| decode stage wall | 716.848 ms | 1051.127 ms |
| decode-time `load_models_gpu` | **54.516 ms** | **79.769 ms** |
| … `partially_load` | 51.028 ms | 77.413 ms |
| … `ModelPatcherDynamic.load` | 50.924 ms | 77.308 ms |
| … `_load_list` | 10.605 ms | 14.661 ms |
| … `restore_loaded_backups` | (not shown) | 8.583 ms |
| **`load_models_gpu` as share of decode stage** | **7.60 %** | **7.59 %** |

Normalised, the exposed decode-time activation is **unchanged**. Un-normalised
raw values are not comparable here: the treatment profiled run was ~52 % slower
at root overall (17216 ms vs 11318 ms), i.e. a slower host moment, not a
regression.

True-cold decode stage wall: control p50 773.734 ms (sd 303.618, n=3) vs
treatment p50 509.311 ms (sd 115.110, n=5). Favourable in direction, but the
ranges overlap (control min 468.074 < treatment p50) and the host is far too
noisy to carry the claim.

**Why, from pristine upstream source (not speculation).**
`VAE.decode` (`sd.py:1230`) calls `load_models_gpu` unconditionally →
`model_load` (`mm:782`) → `model_use_more_vram` (`mm:817`) →
`ModelPatcherDynamic.partially_load` (`mp:2141`) → `load` (`mp:1853`). `load`
runs `restore_loaded_backups()` (zeroes `model_loaded_weight_memory`) and then
rebuilds the **entire** per-module list via `_load_list` (`mp:945`, which returns
every module regardless of current device) and re-walks it. Only the AIMDO
host-buffer allocation is guarded by `if not pin_state["hostbufs_initialized"]`.
So the first-time registration is genuinely pre-paid by the relocation, but the
dominant cost — the repeated per-parameter pass — happens either way. The audit
reached the same conclusion from the other direction: *"the no-op fast path does
not exist for this call — `partially_load` always runs"* and §15 concluded
"how much wall can be **removed**? nothing".

Net effect of task 2 as it stands: it moves ~63 ms (p50) of real work into the
sampling window where it contends with sampling, in exchange for hiding first-time
AIMDO registration that is **not** the dominant term. No root-wall benefit is
demonstrable. Separately, the audit flagged that holding AIMDO pinned host
buffers during sampling is a GPU/host-memory policy change "which therefore
needs its own scoped change with its own measurement" — host memory was **not**
measured here.

## 11. Overall Golden / root timing

| cohort | n | min | p50 | mean | max | sd |
|---|---:|---:|---:|---:|---:|---:|
| treatment root wall (ms) | 5 | 16508.085 | 23861.485 | 36141.791 | 73122.543 | 23845.248 |
| control root wall (ms) | 3 | 26331.914 | 33276.749 | 36740.924 | 50614.109 | 12506.264 |

sd of 23.8 s on a 23.9 s median: this host cannot support a root-wall verdict at
n=5. Reported as measured, with no promotion claim.

Treatment per-stage (p50 of 5): `clip_load` 2480.166, `clip_forward` 3217.256,
`unet_load` 2790.636, `sampler_prepare` 26.991, `sampling` 3927.878,
`vae_load` 460.467, `sampler_tail` 0.017, `vae_decode` 509.311, `output` 240.662.
`sampling_vae.true_overlap=true` on 5/5.

## 12. Regressions and fallbacks

| item | status |
|---|---|
| new test failures | **none** |
| correctness regression | **none** — 8/8 requests (5 treatment + 3 control) exact SHA |
| CLIP cache miss / fallback reason | **none** recorded |
| UNET bounded-join expiry / inline parse | **none** |
| VAE guard failure / postcondition failure | **none** |
| VAE decode-time fallback | **0** |
| double registration / teardown `AttributeError` | **none** (registry VAE count 0 after restore, 5/5) |
| config / destination committed | **no** — `modal_target.toml` left modified-but-unstaged |
| experimental garbage inherited | **no** — no config/toml changes; Triton, arena-16, source-probe, Testing9→1 edits all excluded |

**One pre-existing benign warning, disclosed.** Every run emits
`OUTPUT_SHA_MISMATCH_WARNING` because the runtime compares against
`session.contract.expected_output_png_sha256` = `790c3052…` (the base `golden_p1`
serial value) while the parallel profile supplies `3a6a0306…` at the v2ctl layer.
This is a profile-inheritance property of running the parallel profile, not a
consequence of this bundle: `golden_output`'s own docstring makes a configured
expectation mismatch *"an explicit warning, not a write or durability failure"*,
and the authoritative `validation.output_sha_match=True` with
`observed_output_shas=[3a6a0306…]` holds on every run. None of these three
optimizations touch pixel encoding, and the bit-exact SHA proves it.

Also disclosed: the `comfymodal-golden-ops` skill cites expected SHA
`454dbda2…`. That is stale; the repo's authoritative value for this profile
family is `3a6a0306…` (`config/v2/profiles/golden_p1_parallel.toml:20`,
`golden_p1_parallel_c0_source_h100.toml:29`, `tools/p7_acceptance.py:5`), which
matches the brief.

## 13. Recommendation

**`RECOMMEND_FINAL_INTEGRATION=no` for the bundle as a single unit.**

Split it:

1. **`208b5b3c` + `73a37efb` — PROMOTE.** Both are the proven lineage, ported
   clean, and both reproduce their target behaviour at runtime (CLIP
   `layout_lookup` 31.16 → 1.178 ms; UNET join completed and cache-hit 5/5 with
   zero expiries). They are also mutually dependent: the CLIP cache diff was
   authored on top of the pre-resolve work, so integrating one without the other
   means re-deriving that diff.
2. **`76e5c1ab` — DO NOT PROMOTE YET.** Keep the commit; it is additive,
   isolated to one function, fail-soft, gated on the pre-existing overlap
   schedule, with the serial path byte-identical, so reverting it is a single
   `git revert` with no interaction with 1. It fails only its own performance
   criterion, not correctness. To revive it, one of these must change:
   - measure on a low-noise host / larger n — the current effect size (~0) is
     below this host's noise floor, so this alone may not be enough;
   - make the decode-time `partially_load` genuinely skippable, which means
     engaging with upstream `ModelPatcherDynamic.load` / `VAE.decode` and is
     explicitly out of scope for this bundle;
   - or quantify the pinned-host-memory cost during sampling and show the
     trade is worth it (the audit's own precondition, still unmeasured).

Do **not** merge, tag or promote anything from this branch. Agent 2's CUDA
context-init + arena-geometry work and the Triton owner's work are untouched and
independently mergeable.

## 14. Commits eligible for final integration

```
76e5c1ab7de6691aad468aad45158ef8d1451cc1  perf(golden): overlap the VAE DynamicVRAM activation with sampling   [DEFER]
69f45de5df11377450e19b8664794a8bb7f4d773  perf(golden-clip): serve the layout/meta blueprint from a persistent cache  [PROMOTE]
73a37efb                                 fix(golden-unet): bound the layout pre-resolve join                 [PROMOTE]
208b5b3c                                 perf(golden-unet): resolve the dynamic UNET layout during CLIP load   [PROMOTE]
```

Cherry-pick order matters: `208b5b3c` → `73a37efb` → `69f45de5`. The CLIP cache
commit `69f45de5` applies cleanly on top of the two UNET commits (that is how it
was validated here); applied alone it conflicts in the
`golden_model_transport.py` import block and needs the `source_latency_telemetry`
/ `source_stall_classification` imports dropped, since neither exists on main.

`config/v2/modal_target.toml` is deliberately **not** in any commit.

## 15. Evidence paths

| item | path |
|---|---|
| branch / worktree | `opt/p10-integration-cache-vae-unet` @ `.slim/worktrees/p10-agent1` |
| 5 treatment attempt artifacts | `artifacts/phase_p1_parallel_golden_v1/cohort_2026-10-04_0{4-53-29_7dac63,4-58-58_f5b7a1,4-59-19_587844,4-59-43_7dc942,5-00-34_3de56e}/attempt_0.json` |
| 3 control attempt artifacts | `…/cohort_2026-10-04_05-{10-07_7c4bdb,11-06_427a6a,11-44_4cb669}/attempt_0.json` |
| treatment profile report | `artifacts/golden_exhaustive_runs/c0f2c09092c64ff9b024818a474a0484/…/derived/golden_stage_report.md` |
| control profile report | `artifacts/golden_exhaustive_runs/6f7ab9454d524011b002421cd76dbd86/…/derived/golden_stage_report.md` |
| run manifests | `.v2ctl/runs/run_2026*.json` |
| deploy receipts | `.v2ctl/deployments/receipt_*_5b2e43f0….json`, `receipt_*_cc73efd5….json` |
| source-probe logs | `.v2ctl/` + captured stdout (`RESULT=PASS source_identity=MATCH`) |
| evidence extractors | `tools/p10a1_extract.py`, `tools/p10a1_stats.py` |

### Reproducing the numbers

```powershell
python tools/p10a1_stats.py <treatment_paths.txt> <control_paths.txt>
python tools/p10a1_extract.py <attempt.json> [...]
```
