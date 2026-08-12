# V2 Active-Profile Critical-Path Report

## Executive conclusion

The multi-second "active-profile" work observed before every generation
submission was **dead weight on the default single-invocation V2 path**.

On the default `inherit` path, `execute_plan` ran a remote **checker**
(`check_active_warmup_profile`, a cold CPU Modal function, ≈4.1 s) followed on
miss by a remote **setter** (`set_active_warmup_profile`, cold function +
Volume commit, ≈5.3 s) before submitting `run_plan_stream`. The state they
maintain — `active_next_profile.json` on the `comfymodal-runtime-config`
volume — is **never read by a restored single-invocation V2 container**
(`modal_app.py` restore path contains zero references to `active_next`; the
container derives its seed from the request via
`build_invocation_seed_payload`, `seed_source=invocation_plan`). The observed
`inherit → inherit` result with no override applied was correct behavior:
`inherit` is a no-op request override in-container.

Two fixes were applied, in sequence:

1. **Inherit no-op gate** (commit `6a84c16`): the normal already-correct path
   became a local no-op when the requested effective profile is
   `inherit`/empty and no warmup-profile consumer is active.
2. **Lifecycle-accurate gate** (this revision): the first gate still forced the
   remote checker/setter whenever `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`, because
   it treated that deployment capability flag as a consumer. Investigation
   proved the flag conflates two lifecycle phases — snapshot **construction**
   (the only phase that reads `active_next_profile.json`) and normal **restored
   generation** (which never reads it). The gate now keys on the construction
   lifecycle, so post-snapshot restored generations skip the remote
   checker/setter even under `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`, while the
   construction/warmup path keeps publication available via an explicit
   deploy-side marker (`COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1`).

Instrumentation on the normal path reports `decision=skipped_post_snapshot_noop`
(or `skipped_inherit_noop`), `snapshot_build_phase`, `cpu_model_snapshot_enabled`,
`consumer_requires_publication`, checker/setter remote call flags, timings, and
the requested/container/effective profiles.

## Previous active-profile path

Request flow before this change (timings from the four valid single-invocation
snapshot-reuse runs):

```
local request
  → execute_plan
    → active_profile_prepare_start
    → [if profile_setter wired] compute_profile_identity_keys (local, ms)
    → _PROFILE_PREP_CACHE lookup (local, ms)
    → cache miss → prepare_active_next_profile:
        → CHECKER: modal_client.check_active_warmup_profile(stable_key)
            = cold Modal @app.function (cpu=1, mem=256, timeout 60s)
            ≈ 4.1 s — cold function start + volume read of
              active_next_profile.json; {"matched": True} → skip setter
        → miss/fail-open → SETTER: modal_client.set_active_warmup_profile(payload)
            = cold Modal @app.function (cpu=2, mem=4096, timeout 120s)
            ≈ 5.3 s — cold start + file write + synchronous Volume commit
    → active_profile_prepare_end   ← active_profile_ms = 0 / 10109 / 2844 / 9453
    → restore publication (already removed / local-only on default path)
    → transport.run_plan_stream    ← actual Modal submission
```

Callers that wired the remote checker+setter into `execute_plan`:
`tools/benchmark_v2_direct.py:1023-1028, 2277-2278` and
`tools/run_fresh_requests.py:232-237` (the four measured runs came from these
harnesses). `__init__._execute_job` (V2 mode) already passed
`profile_setter=None`; the V1 `execute_modal_prompt` callers
(`__init__.py:2481-2496`, `studio_run_adapter`, `experiment_runner`) also wired
them.

Three cache layers already existed to amortize the cost: the process-local
`_last_stable_profile_cache` (TTL 3600 s), the `execute_plan`-level
`_PROFILE_PREP_CACHE` (+ disk `v2_profile_cache.json`), and the volume-backed
checker for cold processes. Despite them, a fresh process per request
(single-invocation architecture) paid the checker on every first request and
the setter whenever the volume did not already match. `.cache/v2_profile_cache.json`
recorded a normal run paying `checker_ms=7421` + `setter_ms=4454` ≈ **11.9 s**
of pre-submission latency under `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`.

## Root cause

1. **Why the check ran before every submission:** `execute_plan` entered the
   profile-prep block whenever a `profile_setter` was provided, and the
   benchmark/harness callers wired the real `modal_client` functions
   unconditionally — independent of whether the request asked for any profile
   change.

2. **Why checker and setter each take seconds:** both are **remote Modal
   function calls**, not cached control-plane reads. Each invocation pays a
   cold function start on a small CPU container; the setter additionally
   performs a synchronous `runtime_config_volume.commit()`. Timeouts
   (`COMFYMODAL_PROFILE_CHECKER_TIMEOUT` 60 s, `COMFYMODAL_PROFILE_SETTER_TIMEOUT`
   120 s) bound them, but the typical cost was 4–10 s combined.

3. **Why `inherit` requests needed a setter at all:** they did not. The env
   profile (`COMFYMODAL_V2_ENV_PROFILE`, default `"inherit"`) was never used to
   gate the publication; the checker/setter ran regardless. `inherit` is a
   no-op request override in-container (`modal_app.py:14211-14244`): it never
   flips an explicit container profile and never changes the env, which is why
   the remote request reported `inherit → inherit` with no override applied.

4. **Why the first fix still paid the cost under CPU-model-snapshot
   deployments:** `active_next_publication_required()` returned True whenever
   `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`, treating the deployment capability
   flag as a publication consumer. The flag is baked into the container env and
   the snapshot fingerprint, and is set on **both** construction and normal-run
   invocations by the harness scripts — so every post-snapshot generation kept
   paying the remote checker/setter.

## CPU-model-snapshot lifecycle distinction

`COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1` is a **deployment capability** flag that
conflates two Modal container-lifecycle phases:

| Phase | Modal lifecycle | Reads `active_next_profile.json`? |
|---|---|---|
| **Snapshot construction** | `startup()`, `@modal.enter(snap=True)` (modal_app.py:15279-15283) — one-time cold start when Modal's snapshot cache misses | **YES** — `startup()` → `_cpu_snapshot_profile(api)` (modal_app.py:7635) → `api._snapshot_preload_profile()` → comfyapp `_load_active_next_profile()` (comfyapp.py:10450) |
| **Normal restored generation** | `restore()`, `@modal.enter(snap=False)` (modal_app.py:15284) — every subsequent container start | **NO** — restore path never consults the volume record; request state comes solely from `invocation_plan` (`_derive_request_snapshot_seed`, modal_app.py:14319-14406) |

Key evidence: `Select-String` over `comfymodal_runtime/*.py` finds **zero**
`active_next` references; the profile read happens only inside the startup
(snap=True) construction path; Modal skips `startup()` entirely when a
compatible snapshot exists (restore path runs instead).

## active_next_profile readers

| Reader (file:line) | Lifecycle phase | Gate / condition | Reachable on default inherit V2? |
|---|---|---|---|
| `modal_app._cpu_snapshot_profile` → `_snapshot_preload_profile` → `_load_active_next_profile` (modal_app.py:7635 → comfyapp.py:10910 → 10450) | **SNAPSHOT BUILD** (snap=True enter) | `startup()` (modal_app.py:7356, `_modal.enter(snap=...)` :15279-15283) + `_cpu_model_snapshot_enabled()` (:7617) | Only during the one-time build; Modal skips `startup()` when a snapshot exists |
| `ComfyApp.restore()` (comfyapp.py:20341 → 10910) | legacy V1 restore | `ENABLE_WARMUP` (:20315) | No (V1 surface) |
| `ComfyApp.run_prompt()` (comfyapp.py:22806 → 10910) | legacy V1 request execution | inside `run_prompt` | No |
| persistent CLIP cache (comfyapp.py:22586 → 10450) | V1 run_prompt / persistent cache | `COMFYMODAL_PERSISTENT_CLIP_CACHE` (:22582) | No (opt-in flag) |
| diagnostics (`_log_remote_identity` :1675, storage diag :8897/:20204) | any | — | log-only, non-load-bearing |

Writer side: `set_active_warmup_profile` (comfyapp.py:8480-8503) →
`_write_active_warmup_profile_payload` (:8592-8648) — validation, file write,
synchronous Volume commit. Checker side: `check_active_warmup_profile`
(:8506-8539) — read-only identity seam, no commit.

## Snapshot-build vs post-snapshot ownership

- **Construction (snap=True)**: `_cpu_snapshot_profile` consumes the published
  profile to decide which CPU models/profile to prepare and preload before
  capture. If the profile is unavailable: **fail-soft on `inherit`**
  (`[v2.cpu_snapshot] status=skipped reason=profile_unavailable
  action=skip_model_build`, modal_app.py:7642-7647) — construction still
  completes; **fail-hard on `production`** (RuntimeError
  "Production CPU snapshot profile is unavailable", :7637-7641). Construction
  is a one-time cold start, keyed by `_snapshot_target_fingerprint` (app/class/
  resources/env hash).
- **Restored generation (snap=False)**: owns no profile responsibility. The
  container restores the captured snapshot (CLIP/VAE retained, UNET absent for
  the exclude-unet identity), validates the request plan against the restored
  models, and executes — never reading `active_next_profile.json`.
- **Local submitter**: cannot observe Modal's snapshot-cache state directly.
  The lifecycle is identified by **which invocation** is running: the deploy
  bat's `snapshot_restore_only` branch is the labeled/excluded construction
  invocation; `run_v2_single.bat` issues normal restored generations. Both set
  identical capability env, which is why a lifecycle marker (below) is the
  unambiguous local signal.

## Corrected gate

`warmup_profile.active_next_publication_required(env_profile=None)` — the
deployment capability check was **removed** and replaced by a lifecycle marker:

```python
# OLD (removed):
    if os.environ.get("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", "").strip() == "1":
        return True

# NEW:
    if os.environ.get("COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION", "").strip() == "1":
        return True
```

Full decision table:

| Requested profile | `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION` | Other consumers | Publication |
|---|---|---|---|
| `inherit`/empty (default) | 0 (normal restored generation) | none | **skipped** → `skipped_post_snapshot_noop` |
| `inherit`/empty | 1 (construction/warmup invocation) | — | **required** (full checker/setter path) |
| `production`/`diagnostic` (explicit change) | any | — | **required** (unchanged) |
| `inherit` | — | `COMFYMODAL_PERSISTENT_CLIP_CACHE=1` | **required** (unchanged) |
| `inherit` | — | `ENABLE_WARMUP` (legacy V1) | **required** (unchanged) |
| `inherit` | — | `DISABLE_ACTIVE_NEXT_WRITE=1` | skipped (unchanged) |

`execute_plan`'s no-op branch now derives lifecycle instrumentation:
`_cpu_snapshot_enabled` (capability flag), `_snapshot_build_phase` (marker),
`_noop_reason` = `"post_snapshot"` when the capability is enabled else
`"inherit_default_no_consumer"`, and the decision string
`skipped_post_snapshot_noop` / `skipped_inherit_noop`. The trace event was
renamed `active_profile_inherit_noop` → `active_profile_skip_noop` (metadata:
reason, requested/container profile, `snapshot_build_phase`,
`cpu_model_snapshot_enabled`, `consumer_requires_publication=0`, checker/setter/
override flags). The `[active_profile.publish]` line reports
`decision=... cpu_model_snapshot=... snapshot_build_phase=...
consumer_requires_publication=0 checker_remote=0 setter_remote=0
active_profile_noop_ms=...`.

The construction marker is set **only** by `deploy_and_run_v2_single.bat`'s
`snapshot_restore_only` branch (the labeled/excluded construction invocation);
`run_v2_single.bat` never sets it, so normal restored generations take the
no-op path. The deploy bat's warmup profile extraction
(`tools/extract_warmup_profile.py`) remains the deploy-time channel; the
request-time publication is not the construction feed for the current harness
(the deploy invocation issues no requests — construction reads whatever valid
record the volume carries, and fails soft on `inherit` if absent; this is
pre-existing behavior, unchanged by this fix).

## Implementation

1. `warmup_profile.py` — `active_next_publication_required()`: replaced the
   `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1 → True` rule with
   `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1 → True`; docstring updated to
   document the lifecycle distinction.
2. `canonical_execution.py` — `execute_plan` no-op branch: lifecycle
   instrumentation, dynamic reason/decision, renamed event, extended
   `[active_profile.publish]` line.
3. `deploy_and_run_v2_single.bat` — `snapshot_restore_only` branch sets
   `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1` + summary echo.
4. `tests/test_v2_active_profile_inherit_noop.py` — gate decision table and
   gate tests updated to the lifecycle semantics (see Local proof).

## Changed files

| File | Change |
|---|---|
| `warmup_profile.py` | `active_next_publication_required`: CPU_MODEL_SNAPSHOT capability rule → SNAPSHOT_CONSTRUCTION lifecycle marker (+docstring) |
| `canonical_execution.py` | `execute_plan` no-op branch: lifecycle metadata, `skipped_post_snapshot_noop` decision, `active_profile_skip_noop` event, extended publish line |
| `deploy_and_run_v2_single.bat` | Construction branch sets `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1` (+echo) |
| `tests/test_v2_active_profile_inherit_noop.py` | Decision table flipped (CPU snapshot alone → no publication), construction-marker cases added, event/decision assertions updated |
| `V2_ACTIVE_PROFILE_CRITICAL_PATH_REPORT.md` | This report (lifecycle sections added) |

Unchanged by design: snapshot/eviction composition, native fast-disk loader,
CLIP/UNET overlap, conditioning-cache semantics, output persistence,
Sampling/CacheDiT, `modal_app.py`/`model_preload.py` (other agents' work),
restore-path seed derivation (`invocation_plan` remains authoritative).

## Local proof

`python -m pytest tests/test_v2_active_profile_inherit_noop.py
tests/test_runtime_canonical_v2.py tests/test_v2_local_pre_submit_optimization.py
tests/test_local_submission_critical_path.py tests/test_v2_lane_a_disk_persistence.py
tests/test_warmup_profile_dedup.py tests/test_canonical_execution.py -q`
→ **305 passed, 9 failed**. The 9 failures are the pre-existing
`TestBenchmarkPrefixInstrumentation` C8 runtime-shape validation failures
(deployed identity data unavailable in the test environment; verified
pre-existing via `git stash` in the prior task — thread-policy/snapshot-order
assertions, unrelated to profile publication).

`tests/test_v2_active_profile_inherit_noop.py` (24 tests) proves:

1. `inherit` + `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1` + **normal restored
   generation** → checker remote **0**, setter remote **0**, stream consumed,
   `active_profile_publish_decision=skipped_post_snapshot_noop`,
   `snapshot_build_phase=0`, `cpu_model_snapshot_enabled=1`,
   `consumer_requires_publication=0`, `active_profile_total_ms < 5000`.
2. Snapshot-build lifecycle still publishes: `inherit` + CPU_MODEL_SNAPSHOT=1
   + `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1` → setter invoked.
3. Explicit `production`/`diagnostic` still publishes (unchanged).
4. V1 behavior unchanged (`ENABLE_WARMUP` → publication required;
   `prepare_modal_execution` path ungated, `test_profile_checker_forwarded...`
   green).
5. Persistent CLIP cache still consumes: `COMFYMODAL_PERSISTENT_CLIP_CACHE=1`
   → setter invoked (unchanged).
6. Request-carried `invocation_plan` remains authoritative after restore:
   post-snapshot inherit run submits with `profile_remote_call_performed=False`.
7. No profile publication reappears before normal `run_plan_stream` submission
   (stream iterated; `profile_remote_call_performed=False` on the no-op path).

## Remote acceptance

Exactly **one** real post-snapshot inherit run (hard stop after it), against
the existing deployed UNET-absent snapshot app:

- App: `stable-modal-comfy-v2-restore-only-shadow` (deployed; UNET-absent
  snapshot identity)
- Env: `COMFYMODAL_V2_ENV_PROFILE=inherit`,
  `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`,
  `COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1`,
  `COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1`,
  `COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae`,
  `COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0`,
  GPU `rtx-pro-6000`, 12 CPU, 32768 MiB, `V2_BENCHMARK_RUNS=1`
- Command: `python tools\benchmark_v2_direct.py` (EXIT=0)

Proven from the run log:

| Criterion | Evidence |
|---|---|
| Snapshot already existed/reused | `restore_count=1`, `restored_instance_id=5710dda82ef14a1f81f4fa263932a6ed`, `restore_session_id=bd189a33ff144e17aee5d7b54fe32218`, `snapshot_restore_ms=4592.93`, `restore_total_ms=6547.965` (restore/snap=False path — no construction) |
| `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1` | `cpu_model_snapshot=1` in publish line; identity fingerprint `1e97fdba...` (env includes capability flags) |
| checker_remote=0 | `checker_remote=0`, `profile_checker_performed` false, `active_profile_checker_ms=0.0` |
| setter_remote=0 | `setter_remote=0`, `profile_setter_performed` false, `active_profile_setter_ms=0.0` |
| active_profile_ms≈0 | `active_profile_ms=0.0`, `active_profile_total_ms=0.0`, `active_profile_noop_ms=0.0` |
| One `run_plan_stream` submission | identity `method_name=run_plan_stream`, `request_count=1` |
| UNET absent / CLIP+VAE retained | `cpu_snapshot_unet_mode=reuse`; UNETLoader node loads per-request during execution (node 6.160s, not from snapshot); `reload_models_ms=2279.0`, `cpu_snapshot_retargeting_ms=0.0` |
| Valid output | sampling 3.753s, VAE 0.879s, output persistence 0.586s, remote result handoff 0.426s; waterfall fully accounted (168.112s, 100%); EXIT=0 |
| No multi-second profile gap before submission | `local_receive_to_actual_submission_ms=16.0` (was ~11.9 s of checker+setter) |
| invocation_plan authoritative | `[v2.seed_build] source=invocation_plan schema=2 topology_available=1 persisted=1 workflow_hash=5fdebc3c5d8f450b loader_nodes=3 sampler_nodes=1 reachable_nodes=43` |

The publish line from the run:
`[active_profile.publish] decision=skipped_post_snapshot_noop requested=inherit
container_default=inherit cpu_model_snapshot=1 snapshot_build_phase=0
consumer_requires_publication=0 checker_remote=0 setter_remote=0
active_profile_noop_ms=0.0`

Note: a benign `asyncio` shutdown exception (persistence-drain task spawn after
completion) appears at interpreter teardown in the harness log; the run itself
completed successfully (EXIT=0, full accounting, valid output). No further runs
were performed.

## Before vs after

| Metric | Before (snapshot deployment, inherit run) | After (same identity) |
|---|---|---|
| Checker remote call | yes, ≈7.4 s cold | **no** (0) |
| Setter remote call | yes, ≈4.5 s cold | **no** (0) |
| `active_profile_ms` | 0 / 10109 / 2844 / 9453 | **0.0** |
| `local_receive_to_actual_submission_ms` | includes checker+setter (≈4–12 s) | **16.0** |
| Decision | `published` (or `skipped_inherit_noop` on cache hit) | `skipped_post_snapshot_noop` |
| Container seed source | request (`invocation_plan`) — unchanged | unchanged |
| Snapshot construction publication | available (capability flag) | available (construction marker) |

## Remaining publication cases

Publication (full remote checker/setter) runs only where code proves it is
load-bearing:

1. **Snapshot construction / warmup** — `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1`
   (set by `deploy_and_run_v2_single.bat`'s `snapshot_restore_only` branch;
   any construction-role invocation may set it). The profile preloads the CPU
   model stack into the snap=True capture.
2. **Explicit profile changes** — `production` / `diagnostic` (or any
   non-`inherit` requested env profile, request-carried or process env). Also
   required for production construction (fail-hard without a profile).
3. **Legacy V1 warmup** — `ENABLE_WARMUP` (ComfyApp.restore preload) and V1
   `run_prompt` path.
4. **Persistent CLIP cache** — `COMFYMODAL_PERSISTENT_CLIP_CACHE=1` prompt-
   bundle reads.
5. `DISABLE_ACTIVE_NEXT_WRITE=1` still suppresses all publication (unchanged).

Nothing was deleted: the checker/setter functions, `prepare_active_next_profile`,
all cache layers, and the volume record format are untouched; the change is the
gate condition plus lifecycle instrumentation. Post-snapshot restored
generations with the default `inherit` profile now take the local no-op path
under `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`,
`COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1`,
`COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1`,
`COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae`.

## Recommended next action

1. Confirm the construction deploy still prints the warmup profile env summary
   with `snapshot_construction=1` and that the full publication path is
   available on that invocation (deploy-time channel remains
   `extract_warmup_profile.py`; request-time publication is a no-op there by
   design).
2. If the team no longer runs `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`
   deployments, consider a follow-up that removes the publication machinery
   entirely (checker/setter wiring, `active_next_profile.json` volume record,
   `prepare_active_next_profile` call sites) — the lifecycle gate makes that
   safe to do incrementally.
3. Investigate whether the harness call sites (`benchmark_v2_direct.py`,
   `run_fresh_requests.py`) should stop wiring `profile_setter`/`profile_checker`
   for inherit runs entirely; the gate already makes it a no-op, but removing
   the wiring would simplify the harness contracts.
