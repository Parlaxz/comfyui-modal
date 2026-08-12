# V2 Active-Profile Critical-Path Report

## Executive conclusion

The multi-second "active-profile" work observed before every generation
submission was **dead weight on the default single-invocation V2 path**.

On the default `inherit` path, `execute_plan` ran a remote **checker**
(`check_active_warmup_profile`, a cold CPU Modal function, ≈4.1 s) followed on
miss by a remote **setter** (`set_active_warmup_profile`, cold function +
Volume commit, ≈5.3 s) before submitting `run_plan_stream`. The state they
maintain — `active_next_profile.json` on the `comfymodal-runtime-config`
volume — is **never read by the single-invocation V2 container** (`modal_app.py`
contains zero references to `active_next`; the container derives its seed from
the request via `build_invocation_seed_payload`, `seed_source=invocation_plan`).
The observed `inherit → inherit` result with no override applied was correct
behavior: `inherit` is a no-op request override in-container.

**Fix:** the normal already-correct path is now a local no-op. `execute_plan`
skips the remote checker/setter entirely when the requested effective profile
is `inherit`/empty and no warmup-profile consumer is active (CPU-model
snapshot, persistent CLIP cache, legacy V1 warmup). The full checker/setter
machinery is preserved for explicit profile changes (`production`,
`diagnostic`) and for every consumer deployment. Instrumentation proves
checker/setter remote calls, timings, the submission, and the resulting
profiles on both paths.

## Previous active-profile path

Request flow before this change (all timings from the four valid
single-invocation snapshot-reuse runs):

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
`tools/benchmark_v2_direct.py:1027-1028, 2277-2278` and
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
the setter whenever the volume did not already match.

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

4. **What state was validated/changed:** `active_next_profile.json` on the
   `comfymodal-runtime-config` volume — a warmup/restore identity record
   (model stack, profile token, prompt bundle). The checker compared a stable
   restore key; the setter rewrote the record + committed the volume.

5. **Is it still necessary after the single-invocation changes?** No, on the
   default path. The warmup-profile mechanism predates the single-invocation
   design (introduced in the volume-publication era, `f5b522f`; V2 publication
   removed in `e34d777`, seed now request-derived). Today the published record
   is consumed only by:
   - `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1` deployments — container startup
     snapshot build (`modal_app.startup` → `_cpu_snapshot_profile` →
     `_load_active_next_profile`),
   - legacy V1 restore preload (`ENABLE_WARMUP`, `ComfyApp.restore`) and V1
     `run_prompt` persistent-CLIP-cache prompt-bundle reads,
   - `COMFYMODAL_PERSISTENT_CLIP_CACHE` prompt-bundle reads.

   None of these are active on the default `inherit` single-invocation V2
   request path.

## Implementation

New gate helper in `warmup_profile.py`:

```python
def active_next_publication_required(env_profile: str | None = None) -> bool:
```

Returns `True` (publication must run) when:
- the effective requested env profile is a concrete profile (`production`,
  `diagnostic`, … — i.e. an explicit profile change), or
- `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1` (startup snapshot build consumes it), or
- `COMFYMODAL_PERSISTENT_CLIP_CACHE` is enabled, or
- legacy `ENABLE_WARMUP` is set.

Returns `False` (safe local no-op) when:
- the requested profile is `""`/`"inherit"` (deploy default, no-op override),
  **and** no consumer above is active, or
- `DISABLE_ACTIVE_NEXT_WRITE` is set (publication already disabled).

`execute_plan` now resolves the effective requested profile
(request-carried `request_origin_info.env_profile` first, process env
fallback) and gates the profile-prep block on
`profile_setter is not None and active_next_publication_required(...)`. When
skipped, a new `elif profile_setter is not None:` branch emits full no-op
instrumentation and proceeds directly to submission. The existing
checker/setter block is byte-identical (only the condition changed); the
dry-run branch for `setter=None` is unchanged.

Desired normal path, now achieved for the default case:

```
local request
→ local profile validation (env-profile resolution, ms)
→ no-op (decision=skipped_inherit_noop; zero remote calls)
→ immediate Modal run_plan_stream submission
```

## Changed files

| File | Change |
|---|---|
| `warmup_profile.py` | Added `active_next_publication_required()` gate helper (+34 lines) |
| `canonical_execution.py` | `execute_plan`: resolved requested env profile; gated profile-prep block; added `elif` no-op branch with instrumentation (+75/−1) |
| `tests/test_v2_active_profile_inherit_noop.py` | NEW: 18 tests — inherit no-op gate (8) + `active_next_publication_required` decision table (10) |
| `tests/test_runtime_canonical_v2.py` | Class fixtures pin `COMFYMODAL_V2_ENV_PROFILE=production` for setter-invocation tests |
| `tests/test_v2_local_pre_submit_optimization.py` | Same fixtures for cache/dedup/setter-count classes |
| `tests/test_local_submission_critical_path.py` | Same fixtures for operation-count/dedup classes |
| `tests/test_v2_lane_a_disk_persistence.py` | Same fixtures for disk-cache classes |
| `tests/test_warmup_profile_dedup.py` | Same fixture for `TestProfileCheckerMatchedBreakdown` |
| `tests/test_canonical_execution.py` | Unchanged — `prepare_modal_execution` path is ungated by design; verified green |

Untouched by design (per scope): snapshot/eviction, native fast-disk loader,
CLIP/UNET overlap, conditioning-cache semantics, output persistence,
Sampling/CacheDiT, and `modal_app.py`/`model_preload.py` (other agents' work).

## Correctness proof

Bounded validation (no benchmark campaign), `python -m pytest` on all touched
files + new tests: **299 passed, 9 failed**. All 9 failures are
`TestBenchmarkPrefixInstrumentation` (C8 runtime-shape validation: deployed
thread-policy/snapshot-order/CPU/memory identity is unavailable in the test
environment) — verified pre-existing via `git stash` and unrelated to the
profile path (fixer's stash check; assertions concern thread policy and
snapshot order, not checker/setter behavior).

Evidence of the new semantics (from `tests/test_v2_active_profile_inherit_noop.py`):

| Case | checker remote | setter remote | decision | submission |
|---|---|---|---|---|
| Default (`inherit`, no consumers) | **0** | **0** | `skipped_inherit_noop` | consumed ✓ |
| `COMFYMODAL_V2_ENV_PROFILE=production` | 1 | 1 | `published` | ✓ |
| `inherit` + `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1` | 1 | 1 | `published` | ✓ |
| `inherit` + `COMFYMODAL_PERSISTENT_CLIP_CACHE=1` | 1 | 1 | `published` | ✓ |
| Request-carried `env_profile=production`, process `inherit` | 1 | 1 | `published` | ✓ |
| Request-carried `inherit`, process `production` | **0** | **0** | `skipped_inherit_noop` | ✓ |

Instrumentation emitted on the no-op path (trace event
`active_profile_inherit_noop` + metadata + one stdout line):
- `profile_checker_performed=False`, `profile_setter_performed=False`,
  `profile_remote_call_performed=False` → **checker remote call: no; setter
  remote call: no**
- `active_profile_checker_ms=0.0`, `active_profile_setter_ms=0.0`,
  `active_profile_total_ms≈0` → **active_profile_ms ≈ 0**
- `active_profile_prepare_start` → `modal_submission_attempt` span still
  records **local request → actual submission** (existing breakdown fields
  unchanged, e.g. `local_receive_to_actual_submission_ms`)
- `profile_requested_env`, `profile_container_default`, `profile_effective`,
  `profile_override_applied=False` → **requested/container/effective profile
  and override-not-applied are recorded**
- stdout: `[active_profile.publish] decision=skipped_inherit_noop
  requested=inherit container_default=inherit checker_remote=0 setter_remote=0
  active_profile_noop_ms=<ms>`

Pre-existing pinned behavior still passes: profile-prep cache hit skips the
setter on the second identical request; different model stacks call the setter
per identity; checker-match skips the setter; setter errors never advance the
cache; dry-run with `setter=None` emits `status=dry_run`; `prepare_modal_execution`
(V1) forwards the checker/setter unconditionally (ungated, preserved).

## Before vs after

| Metric | Before (default inherit run) | After (default inherit run) |
|---|---|---|
| Checker remote call | yes, ≈4.1 s cold | **no** (0 calls) |
| Setter remote call | yes, ≈5.3 s cold | **no** (0 calls) |
| `active_profile_ms` | 0 / 10109 / 2844 / 9453 | ≈0 (local resolution only) |
| Remote profile publication | always when setter wired | only when load-bearing |
| Container seed source | request (`invocation_plan`) — unchanged | unchanged |
| Request → submission | delayed by checker+setter | immediate |

No behavioral change for: `production`/`diagnostic` requests (full path),
CPU-model-snapshot deployments, persistent-CLIP-cache deployments, legacy V1
warmup, and any deployment that sets a consumer flag.

## Remaining profile behavior

- **Explicit profile changes are preserved.** A concrete requested profile
  (`production`, `diagnostic`, any non-inherit value) keeps the complete
  checker → setter publication path, including the production-identity payload
  fields and the `[warmup_profile] phase=checker_start/setter_start` remote
  calls.
- **Consumer deployments are preserved.** `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`,
  `COMFYMODAL_PERSISTENT_CLIP_CACHE=1`, and `ENABLE_WARMUP` all force the
  publication path even under `inherit`.
- **Nothing was deleted.** The checker/setter functions, `prepare_active_next_profile`,
  all cache layers, and the volume record format are untouched; the gate is
  purely additive at the `execute_plan` boundary.
- **Override semantics unchanged in-container.** `inherit` remains a no-op
  request override; a concrete request profile still applies when the
  container is on `""`/`inherit` (`modal_app.py:14224-14227`).

## Recommended next action

1. Optionally run one real single-invocation request through
   `tools/run_fresh_requests.py` (or `benchmark_v2_direct.py`) with
   `COMFYMODAL_V2_ENV_PROFILE` unset/inherit and confirm the log shows exactly
   one `[active_profile.publish] decision=skipped_inherit_noop` line with
   `checker_remote=0 setter_remote=0`, and that
   `local_receive_to_actual_submission_ms` no longer contains a 4–10 s
   profile gap.
2. If the team no longer runs `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`
   deployments, consider a follow-up that removes the publication machinery
   entirely (checker/setter wiring, `active_next_profile.json` volume record,
   and `warmup_profile.prepare_active_next_profile` call sites) — the gate
   makes it safe to do so incrementally, deployment by deployment.
3. Investigate whether the harness call sites (`benchmark_v2_direct.py`,
   `run_fresh_requests.py`) should stop wiring `profile_setter`/`profile_checker`
   for `inherit` runs entirely; the gate already makes it a no-op, but removing
   the wiring would simplify the harness contracts.
