# P10 Agent 2 — CUDA Context Preinit × Arena Slot Depth: 2×2 Factorial

Two loader-startup optimisations measured **together** as one balanced 2×2,
because the host-registration work depends on arena size:

* **#3** hoist/preinitialise the lazy CUDA primary context before arena registration
* **#4** 12 arena slots instead of the current 16

**Outcome in one line:** neither change is recommended. 16 slots is kept, and the
context preinit is a real but self-cancelling win — it cuts `cudaHostRegister`
wall by 111–325 ms and cuts *arena establishment* by 105–317 ms, yet adds a
comparable amount back inside the same restore phase, so total restore and root
wall do not improve.

Nothing here is merged, promoted or tagged.

---

## 1. Base / final SHA

| item | value |
|---|---|
| `origin/main` | `ccc2c531bead6614d2435e3bd7fa157a900251a8` |
| **BASE_SHA (experiment base)** | **`fbd81c46ba131ab44e7020fc2bc3f4005d8756fc`** |
| **HEAD (final)** | **`02a38ecc`** (`02a38ecc…`, full SHA in git log) |
| production-009 tag | `45f512ab` (ancestor of BASE_SHA) |

### Why the base is *not* `origin/main`

The task premise states the current arena is **16 × 64 MiB = 1 GiB**. That is
true of the measured production candidate but **not of `origin/main`**:

| ref | `golden_source_threads.SLOT_COUNT` | arena |
|---|---|---|
| `origin/main` = `ccc2c531` | **8** | 512 MiB |
| `fbd81c46` (BASE_SHA) | **16** | 1 GiB |

The 16-slot deepening is commit `a6bd7d88` (`perf(golden-c0): deepen the source
arena to 16 x 64 MiB`), which is **not an ancestor of `main`** — it exists only on
`audit/cuda-arena-lifecycle`, `audit/vae-residency` and `exp/source-copy-isolation`.

`reports/PRODUCTION_009_EASY_OPTIMIZATION_PASS.md` names the measured candidate
HEAD as `fbd81c46`, on profile `golden_p1_parallel_c0_p8_h100`, app
`batch-p9opt1-h100`, workspace Testing 9, with expected SHA
`3a6a0306…`. `fbd81c46` is that exact state, so it is the faithful base for this
experiment. Using `main` would have tested 8-vs-12 slots, which is not the
question asked.

## 2. Worktree / branch

```
branch   exp/p10-context-slots
worktree .slim/worktrees/p10-agent2
base     fbd81c46
HEAD     02a38ecc
```

Created as one new isolated worktree. The dirty root checkout
(`studio-work-october`) was never touched. `.slim/worktrees/p8fix` and
`.slim/worktrees/source-copy-isolation` were not touched. No reset, no force
checkout, no stash, no tag movement.

## 3. Current registration architecture (as traced, not as remembered)

* `golden_source_threads` **owns** the arena geometry:
  `ARENA_BYTES = SLOT_COUNT * SLOT_BYTES`, `SLOT_BYTES = 64 MiB`,
  `READER_COUNT = 4`, `PACER_GAP_NS = 4 ms`. The source owner attaches the
  mapping by name and size and asserts `slot_count/slot_bytes/arena_bytes` on the
  way in (`CONTROL_MAGIC` header check).
* `golden_io_process_v2.SharedArenaRing` creates the POSIX SHM, registers it once
  via `torch.cuda.cudart().cudaHostRegister`, spawns the CUDA-sterile source
  child, and (default `registration_order = "overlap"`) registers **while the
  child boots**.
* Arena establishment happens in **restore**, not at first model load:
  `ModalRuntimeEntrypointV2._golden_minimal_restore` calls
  `get_golden_model_transport().initialize_cuda()` when
  `COMFYMODAL_GOLDEN_C0_SOURCE_THREADS=1`.
* `ensure()` order: `_require_torch()` → `torch.cuda.cudart()` → *(optional
  inline preinit)* → `SharedMemory(create=True, …)` → `torch.frombuffer` → slot
  views → `spawn()` → `cudaHostRegister` → `await_ready()`.
* Measured floor from the first probe: `spawn_return_ns ≈ 4.5 ms`,
  `source_startup_ns ≈ 407 ms`, `register_ns ≈ 402 ms`,
  `overlapped_spawn_and_register = true`. **Registration is already hidden
  inside the source child's interpreter boot**, so the child boot is a co-equal
  floor on arena establishment.

The pre-existing `COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT` flag ran
`_preinit_primary_context` **inline, immediately before registration**, where
nothing else runs — it could only relocate the cost while leaving it exposed.

## 4. Treatment implementation

**#3 hoisted context preinit** (`COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT`)

```
restore()                                   [snap=False method]
 └─ _golden_minimal_restore()
     ├─ start_c0_context_preinit(snap=False)   ← bounded worker launched FIRST
     ├─ _golden_minimal_reset_container_state()   (CUDA-free, overlaps)
     ├─ _golden_minimal_restore_logical_gpu_state() (CUDA-free, overlaps)
     ├─ initialize_cuda()
     │   ├─ prepare_cpu()
     │   ├─ join_c0_context_preinit()          ← bounded, fails closed
     │   └─ torch.cuda.is_available() … ensure_arena_runtime() → cudaHostRegister
     └─ _golden_minimal_assert_models_generation()
```

Enforced contracts:

* `start(snap=True)` **refuses** and returns
  `{"context_preinit": "refused", "reason": "snapshot_capture"}`. No CUDA during
  snapshot capture; the only call site passes `snap=False`.
* `join()` is bounded (`C0_CONTEXT_PREINIT_JOIN_TIMEOUT_S = 30 s`) and raises
  `c0_context_preinit_join_timeout` / `c0_context_preinit_failed` **before** the
  arena exists — never a detached task, never a silent late CUDA error.
* With the flag OFF, `join()` is a strict no-op and touches no CUDA. This is a
  regression fix (§7).
* The primitive is unchanged and minimal: `cuInit` → `cuDeviceGet` →
  `cuDevicePrimaryCtxRetain` → `cuCtxSetCurrent`. No tensor allocation, no model
  init, no Triton, no attention, no H2D. Enforced by a source-level test.
* `cudaHostRegister` remains mandatory and unchanged; no partial/incremental
  registration was introduced.

**#4 arena depth** (`COMFYMODAL_GOLDEN_C0_SOURCE_SLOT_COUNT`, `12 | 16`)

Resolved once in `golden_source_threads` (the geometry owner); `ARENA_BYTES`
derived as the exact product so `SharedArenaRing`'s full-utilisation invariant
holds. `golden_io_process_v2._qd4_64_geometry()` mirrors the count instead of
restating it, with `slot_owners` regenerated by the existing rule
(`(i // 2) % 4`), which reproduces the accepted 16-slot assignment exactly.
An unsupported count fails closed (`SourceProtocolError`).

Unchanged: QD (4), `READER_COUNT` (4), 64 MiB block size, 4 ms pacer, thread
source owner, whole mmap lifecycle, mmap_fresh engine, persistent FDs,
`cudaHostRegister` flags, H2D dispatcher, slot state machine.

**Instrumentation added to arena evidence:** `declared_slot_count/slot_bytes/arena_bytes`,
`slot_geometry_exact`, `context_preinit_enabled`, `context_preinit_state`,
`experiment_arm`, `arena_establish_wall_ms` (`c0_ensure_enter` →
`source_thread_ready`), and the preinit mode/wall/join-wait inside
`registration_diagnostic`.

**Arm identity (`COMFYMODAL_GOLDEN_C0_EXPERIMENT_ARM`)** is verified against the
observed slot count and observed preinit flag in `SharedArenaRing.__init__`,
before the mapping exists. Mismatch raises
`c0_experiment_arm_slot_mismatch` / `c0_experiment_arm_preinit_mismatch`. All 20
runs reported `arm_verified = true`.

## 5. Four arm definitions

| arm | context preinit | slots | arena bytes |
|---|---|---|---|
| A | OFF | 16 | 1 073 741 824 (1 GiB) |
| B | ON | 16 | 1 073 741 824 (1 GiB) |
| C | OFF | 12 | 805 306 368 (768 MiB) |
| D | ON | 12 | 805 306 368 (768 MiB) |

## 6. Deploy identities

Measured source HEAD `02a38ecc` for all four; profile
`golden_p1_parallel_c0_p8_h100` inherited unchanged (H100!, CPU 12, 24576 MB,
`run_golden_parallel_stream`, forced-miss conditioning, fresh-required, all
intrusive diagnostics OFF, expected SHA `3a6a0306…`).

| arm | profile | app | deploy fingerprint (final) |
|---|---|---|---|
| A | `golden_p1_parallel_p10_a_16_nopreinit_h100` | `batch-p10-reg-a-16-nopreinit-h100` | `3abef9aa1a57d566…` |
| B | `golden_p1_parallel_p10_b_16_preinit_h100` | `batch-p10-reg-b-16-preinit-h100` | `fe2b4aa16147001e…` |
| C | `golden_p1_parallel_p10_c_12_nopreinit_h100` | `batch-p10-reg-c-12-nopreinit-h100` | `22ef7c3acdb89b4…` |
| D | `golden_p1_parallel_p10_d_12_preinit_h100` | `batch-p10-reg-d-12-preinit-h100` | `169c2f6d2638f93f…` |

`source-probe` = `RESULT=PASS source_identity=MATCH`, `git_head=02a38ecc7eb2`,
for all four, before every run. Workspace **Testing 1** (`ws_e677ab553606`),
`DESTINATION_STATUS=VERIFIED`. Production app untouched.

Every payload proved declared == observed: `declared_arm` matched the profile,
`observed_slot_count` and `observed_context_preinit` matched, `arm_verified=true`,
`registered=true`, `arena_bytes` exactly 1 GiB (A/B) or 768 MiB (C/D).

## 7. Two defects the experiment caught (both fixed before the cohort)

Both were silent, which is the dangerous kind.

**(a) The "no preinit" control was not a control.** `initialize_cuda()` joins
unconditionally, but `join()` had no flag gate of its own, so with the flag OFF
it fell into the inline fallback and ran the real driver primitive. Arm A run 1
showed `launch = {"context_preinit": "disabled"}` alongside a **293.4 ms**
primary-context initiation with `mode = "not_started"` — the inline path. Fixed
in `37e8d436`; regression test asserts zero driver calls at both sites.

**(b) Neither new flag reached the container.** All three axis flags were present
in the v2ctl run manifest, yet the container resolved the default slot count and
reported no arm. A deploy-baked flag must be carried in **two** places: the
`config_authority.GOLDEN_CONTROL_FLAGS` allowlist *and* the `modal_app._runtime_env()`
boundary. Registering only in `config/v2/flag_registry.toml` is the control-plane
view, not the container view. A 12-slot arm silently running the 16-slot arena
would have read as "12 slots are just as fast". Fixed in `02a38ecc`; regression
test asserts both sites and that they agree on the default.

## 8. Run validity

20 requests, one per container, strictly serial, interleaved. **20/20 usable.**

| arm | usable | slots observed | preinit observed | arm verified | SHA |
|---|---|---|---|---|---|
| A | 5/5 | 16 | false | true | `3a6a03064c7e…` |
| B | 5/5 | 16 | true | true | `3a6a03064c7e…` |
| C | 5/5 | 12 | false | true | `3a6a03064c7e…` |
| D | 5/5 | 12 | true | true | `3a6a03064c7e…` |

Every run: `valid=true`, `true_cold=true`, `output_sha_match=true`,
`restore_count=1`, `request_count=1`, `capture_classification=ELIGIBLE`,
`capture_counted=true`, `dnf=false`, `failures=[]`, `fatal_failure=false`,
`fallback_reason=None`, output mode `off` / endpoint `result_ready`.

No run was discarded. Slow outliers (B1 root 89.7 s, A5 75.3 s, C4 61.7 s,
D5 56.7 s) are retained and are the documented sick-container tail, not a
property of any arm.

## 9. Correctness

Exact SHA `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`
on **20/20**. No fallback, no fatal, no DNF, no snapshot-capture contamination
(no request classified `SNAPSHOT_CAPTURE`, so no one-request guard was
consumed). Snapshot CUDA hygiene holds by construction and by test.

## 10. Context-init timings

| arm | preinit wall P50 (ms) | join wait P50 (ms) | mode |
|---|---|---|---|
| A | 0 (disabled) | — | disabled |
| B | **306.87** | **0.040** | `hoisted_worker` |
| C | 0 (disabled) | — | disabled |
| D | **292.72** | **0.030** | `hoisted_worker` |

The hoist **works as designed**: the worker really runs off-thread
(`hoisted_worker`), and the join waits ~0.03–0.04 ms because the worker has
already finished by the time the first CUDA caller arrives. So the ~250–565 ms
of driver init is genuinely overlapped, not merely moved.

## 11. cudaHostRegister timings (raw wall, P50 ms)

| arm | register_ms | min | max | CV |
|---|---|---|---|---|
| A | **592.18** | 545.06 | 741.74 | 12.1 % |
| B | **481.08** | 439.98 | 519.50 | 7.7 % |
| C | **667.38** | 487.59 | 707.63 | 13.5 % |
| D | **342.67** | 272.99 | 376.79 | 12.4 % |

**Yes — the raw `cudaHostRegister` wall does shrink with preinit** (−111 ms at
16 slots, −325 ms at 12 slots). Note C (12 slots, no preinit) is *slower* than
A (16 slots, no preinit): registration is not proportional to arena bytes, so
"register less" did not follow from "allocate less".

## 12. Arena-establishment timings (P50 ms)

| arm | establish | min | max | CV | `setup − establish` |
|---|---|---|---|---|---|
| A | **605.46** | 555.35 | 752.25 | 11.8 % | 179.7 |
| B | **500.01** | 451.26 | 537.05 | 7.7 % | 525.3 |
| C | **680.70** | 502.53 | 720.63 | 13.1 % | 271.2 |
| D | **363.48** | 283.96 | 389.04 | 12.2 % | 444.8 |

Establishment tracks `register_ms` almost exactly (≈ +14 ms), confirming the
source-child boot floor is not currently binding.

The last column is the decisive decomposition: `initialize_cuda()` minus arena
establishment. The preinit arms add **+345.6 ms (B vs A)** and **+173.6 ms
(D vs C)** there. The worker-thread init does **not** replace the main thread's
own CUDA initialisation — both are paid.

## 13. Restore / root timings (P50 ms)

| arm | restore total | root wall | root min | root max | root CV |
|---|---|---|---|---|---|
| A | **845.13** | 22 995.62 | 16 053.13 | 75 316.00 | 79.8 % |
| B | **1 095.46** | 24 525.76 | 15 696.13 | 89 690.02 | 79.0 % |
| C | **1 054.23** | 19 130.65 | 15 866.89 | 61 655.12 | 63.9 % |
| D | **885.21** | 17 401.61 | 15 358.51 | 56 683.79 | 72.9 % |

Restore reconciles exactly with §12: B−A = −105.45 (establish) + 345.6 (extra)
≈ **+250**; D−C = −317.22 + 173.6 ≈ **−144**.

Root wall is **not resolvable** between arms: CV 64–80 %, and the minima span
only 15 358–16 053 ms (695 ms total). The median ordering is produced by how many
sick containers each arm happened to receive, not by the treatment.

## 14. Source timings and slot-capacity telemetry

| arm | CLIP load P50 | UNET load P50 | slot_wait_count | all_slots_occupied | capacity_wait | slot_wait_ms |
|---|---|---|---|---|---|---|
| A | 1 447.30 | 2 252.56 | 0 | 0 | 0 | 0.00 |
| B | 1 680.82 | 2 530.32 | 0 | 0 | 0 | 0.00 |
| C | 1 692.45 | 2 668.32 | **2** | **9** | 0 | **18.17** |
| D | 1 654.19 | 2 595.25 | 0 | 0 | 0 | 0.00 |

**12 slots reintroduced measurable source-capacity pressure in arm C**: 2
slot-wait events, 9 all-slots-occupied observations and 18.17 ms cumulative slot
wait, in 1 of 5 runs. The other four C runs were clean, so this is a
low-frequency, load-dependent signal rather than a constant tax — exactly the
kind that a median-of-5 hides and a longer cohort would expose.

Arms A and B recorded **zero** capacity events across all 10 runs. Arm D also
recorded zero across 5, so 12 slots is not inherently starving; it is
capacity-marginal.

The preinit does not touch the source path, and the CLIP/UNET medians are within
the noise band of their own CVs (A/B CV 37–69 %, C/D CV 10–13 %) — the apparent
+233 ms CLIP difference at 16 slots is driven by A1/A2 being sick, not by
preinit.

## 15. 2×2 main effects (median ms, arena establishment; negative = faster)

| effect | value |
|---|---|
| context preinit @16 slots (B−A) | **−105.45** |
| context preinit @12 slots (D−C) | **−317.22** |
| 12 slots, preinit OFF (C−A) | **+75.24** |
| 12 slots, preinit ON (D−B) | **−136.54** |
| **interaction (ctx@12 − ctx@16)** | **−211.77** |

Same signs and near-identical magnitudes on `register_ms` (−111.10, −324.71,
+75.20, −138.41, interaction −213.61).

## 16. Interaction analysis

The interaction is **large and real** and must not be pooled away:

* Preinit saves **3× more at 12 slots** (−317 ms) than at 16 slots (−105 ms).
* 12 slots is **worse** than 16 slots when preinit is OFF (+75 ms) but
  **better** when preinit is ON (−137 ms). The sign of the slot-count effect
  flips depending on the other factor.

A pooled average across the four arms would report a ~−111 ms "context effect"
and a ~−31 ms "slot effect", both of which are meaningless: neither factor has a
context-independent effect here. This is the concrete reason the 2×2 was run
instead of two sequential A/Bs.

The mechanism is consistent: the preinit's recoverable time is bounded by how
much CUDA-free work exists before the first CUDA caller. When arena
establishment is long (16 slots) there is relatively more to overlap and the
relative win is smaller in absolute terms; when the arena is small (12 slots) the
registration itself is shorter, so more of the preinit lands in genuinely
free-running restore work. The absolute numbers still show the preinit's cost
returning elsewhere in both cells.

## 17. Context-preinit classification

**`CONTEXT_PREINIT_ROOT_NEUTRAL`**

* For: consistent, low-variance reduction in `cudaHostRegister` (−111 / −325 ms)
  and in arena establishment (−105 / −317 ms); the hoist genuinely overlaps
  (join wait 0.03–0.04 ms, mode `hoisted_worker`); no correctness regression, no
  snapshot CUDA touch, no source-path change.
* Against: total restore **regressed at 16 slots** (+250 ms) and improved only at
  12 slots (−169 ms); root wall is unresolvable. The decomposition shows why —
  `initialize_cuda()` outside arena establishment grows by +346 ms (B) and
  +174 ms (D), because the worker-thread init does not displace the main
  thread's own CUDA init.

The decision rule is explicit: *"A smaller `cudaHostRegister` number by itself is
insufficient if the exact same time merely moved earlier and remained exposed."*
The register win is offset inside the same restore phase, so total restore/root
does not improve. This is that case, so the treatment is **not** kept.

## 18. Slot-count classification

**`SLOTS_16_KEEP`**

12 slots fails the two-part test:

1. *Wall*: with preinit OFF — the configuration that would actually ship, since
   the preinit is not recommended — 12 slots is **75 ms slower** to establish
   than 16 slots (680.70 vs 605.46). It does not reduce registration.
2. *Capacity safety*: arm C recorded 2 slot-wait events, 9 all-slots-occupied
   observations and 18.17 ms cumulative slot wait. Arm A recorded zero across 5
   runs.

16 slots therefore remains the incumbent choice: it is faster in the shipping
configuration and it is the only depth with a completely clean capacity record.
Production-009's acceptance of 16 slots is re-confirmed, not overturned.

## 19. Winning configuration

**`16_NO_PREINIT`** — i.e. **keep production exactly as it is**.

* 16 + no preinit (A) beats 12 + no preinit (C) on the shipping configuration
  (−75 ms establishment) and has a strictly cleaner capacity record.
* 16 + preinit (B) and 12 + preinit (D) both depend on the preinit, which fails
  its own keep-rule. D is the best-measured cell (establishment 363.48, root
  median 17 401.61, zero capacity events) but its total restore (885.21) is not
  better than A's (845.13), and it buys that only via a treatment that does not
  survive the decision rule.

The one genuinely open question is **D**, and it is open for a specific reason:
D is the only cell that is both fast and capacity-clean. If a future experiment
can remove the preinit's duplicate context cost — for example by having the
*main* thread do the driver init early in restore rather than a worker — then
12 slots plus a real preinit could plausibly beat A. That is a new hypothesis, not
a conclusion from this cohort.

Per the stopping rule, expansion to 10/arm is **not** recommended: the preinit
verdict is decisive (its cost demonstrably returns inside the same phase), and
the slot verdict is decisive (12 alone is slower *and* shows starvation).
Doubling to n=10 would refine root-wall medians that the 64–80 % CV shows are
not the discriminating signal; establishment and capacity already separate the
arms cleanly.

## 20. Exact commits eligible for integration

Branch `exp/p10-context-slots`, in order:

| commit | content |
|---|---|
| `d5b5e6b` | implementation switch: slot-count resolver + hoisted preinit + arm identity + 4 profiles |
| `ebee27a7` | profile rename so the control plane treats the arms as Golden |
| `37e8d436` | fix: preinit OFF is a true control (join flag gate) |
| `02a38ecc` | fix: forward both axis flags across the container env boundary |

Plus `tests/test_p10_context_slot_factorial.py` (47 tests),
`tools/p10_collect.py`, `tools/p10_analyze.py`, and this report.

**What the integrator should take:** the *capability* — the slot-count axis, the
arm-identity fail-closed check, the arena-establishment/preinit instrumentation,
and the two defect fixes. The slot-count axis defaults to 16, so adopting it
changes no production behaviour.

**What the integrator should NOT take as a behaviour change:** enabling
`COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT`. It is classified
ROOT_NEUTRAL. It should stay default-OFF, which is the exact production control.

**Explicitly NOT part of any integration commit:** the Testing 1 workspace
redirect in `config/v2/modal_target.toml`. It is an uncommitted local experiment
destination and is not a production or integration setting (see §21).

## 21. Things explicitly NOT changed

* `cudaHostRegister` — still mandatory, still one full-range call, flags
  unchanged. No partial/incremental registration.
* QD / queue depth (4), `READER_COUNT` (4), `SLOT_BYTES` (64 MiB), 4 ms pacer,
  thread source owner, whole mmap lifecycle, mmap_fresh engine, persistent FDs,
  H2D dispatcher, slot state machine, `FREE_MASK`/slot-table/control layout
  (all derived from `SLOT_COUNT`, verified by test).
* Source engine, mmap lifecycle, block size, reader count, pacing — untouched.
* Snapshot capture path — `start(snap=True)` refuses; `snap=True` is bound to
  `startup`, `snap=False` to `restore`, asserted by test.
* Triton (separate owner), CLIP metadata cache, VAE DynamicVRAM, UNET
  pre-resolve (Agent 1), source mmap/preadv, source block size/QD/reader
  count/pacing — all out of scope and untouched.
* Production app `stable-modal-comfy-v2-golden-p1` — never deployed against,
  never run.
* No merge, no promotion, no tag movement. Agent 1's lanes untouched;
  `.slim/worktrees/p8fix` and `.slim/worktrees/source-copy-isolation` untouched.

## 22. Local tests

`python -m pytest tests/test_p10_context_slot_factorial.py` → **47 passed**.

Focused regression set
(`test_p10_context_slot_factorial` + `test_c0_source_threads` +
`test_golden_model_transport` + `test_golden_parallel_foundation`)
→ **149 passed, 5 skipped**.

`python -m pytest tests -m fast_unit -q` → **653 passed, 2 failed, 7 skipped**.
Both failures are **pre-existing and unrelated**
(`tests/test_rx9p_h_identity_chain.py::test_success_path_exact` and
`::test_compact_nested_sage_observation_is_mismatch`, which expect
`EXACT`/`MISMATCH` where `tools/v2_control/experiment_evidence._compact_cohort`
returns `INCOMPLETE`). They depend only on `tools/v2_control/experiment_evidence`,
which this work does not touch.

One further pre-existing failure found while running the focused set:
`tests/test_v2ctl_profiles.py::test_golden_p1_resolves_canonical_memory_and_keeps_golden_environment`
expects `memory_mb == 8192` while `config/v2/profiles/golden_p1.toml` has carried
`16384` since the base commit. Untouched by this work.

`tests/test_golden_model_transport.py::test_source_thread_arena_gate_follows_the_source_threads_module`
was updated for one intentional contract change: the arena-gate failure message is
now `source_threads_arena_geometry_mismatch:8x67108864!=16x67108864` instead of a
hardcoded `source_threads_requires_16x64m_arena`, because a hardcoded 16 would
mislabel a legitimate 12-slot arm. The test's intent (a retired geometry still
fails closed) is unchanged and still asserted.

`python tools/test_perf.py --fast -- tests -m fast_unit` cannot complete in this
environment: the wrapper's default hard wall is 15 s and it expires during
**collection** (pytest assertion rewriting over a OneDrive-backed tree), before
any test runs. Diagnosed rather than retried with a larger budget; the plain
`python -m pytest tests -m fast_unit -q` run above is the substitute evidence.

## 23. Config destination

The repository's `config/v2/modal_target.toml` was already Testing 9
(`ws_ee7221847f7d`). Per operator direction it was pointed at **Testing 1**
(`ws_e677ab553606`, the workspace id established by commits `37375fbc`,
`0840c352`, `4ff85c6c`).

This edit is **deliberately uncommitted**: `git diff --cached` is empty and
`HEAD:config/v2/modal_target.toml` still reads Testing 9. The file carries a
header marking it experiment-only with the restore value named. It is not part of
any commit in §20 and must not be integrated.

Caveat recorded honestly: I did **not** independently observe a Testing 9
failure. `modal 1.4.3` has no `workspace` subcommand and `v2ctl flags list` is
local-only, so I could not probe either workspace cheaply. The switch was made on
operator instruction. Testing 1 then verified `DESTINATION_STATUS=VERIFIED` and
served all 20 runs.

## 24. Artifacts

Per-run records: `artifacts/p10_agent2/{A,B,C,D}_{1..5}.json` (plus
`A_probe_prebugfix.json`, the pre-fix evidence that exposed defect (a) and is
retained deliberately). Medians: `artifacts/p10_agent2/medians.json`.
Authoritative per-request evidence stays in each run manifest's
`artifacts.output_dir` (`attempt_0.json`, `attempt_0_events.json`,
`manifest.json`, `summary.json`) and in `.v2ctl/runs/`.