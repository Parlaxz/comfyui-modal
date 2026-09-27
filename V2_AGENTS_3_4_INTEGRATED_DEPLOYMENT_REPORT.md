# V2 Agents 3 + 4 Integrated Deployment Report

Status: **COMPLETE — 4 valid generation runs on the UNET-absent architecture**
Generated: 2026-08-12 (~01:15 local)
HEAD: `e5483d5` (no commits made by this session)

---

## Why previous deployment was wrong

The previous run produced `effective_profile=production`, `unet_present=1`, `expected_unet=1`,
and RSS ~21.2 GiB. Root cause chain, from code:

1. **Production is the wrapper default.** `deploy_and_run_v2_single.bat:68` and
   `run_v2_single.bat:11` do `if not defined COMFYMODAL_V2_ENV_PROFILE set "COMFYMODAL_V2_ENV_PROFILE=production"`.
   Any deploy not explicitly driven through the restore-only branch defaults to production.

2. **The production branch unconditionally clobbers the eviction contract.**
   `deploy_and_run_v2_single.bat:74-76` (mirrored at `run_v2_single.bat:17-19`):
   - `COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=0`
   - `COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0`
   - `COMFYMODAL_V2_EVICT_RETAIN_ROLE=` (cleared)
   These are `set` (not guarded), so a user-supplied eviction env is wiped whenever the
   profile resolves to `production`.

3. **UNET absence is produced only by the startup eviction gate, not by snapshot construction.**
   - `modal_app.py:1082-1088` — `_snapshot_exclude_unet_enabled()` is an identity/reporting gate only.
   - `modal_app.py:8195-8199` — `_evict_snapshot_models` runs only when
     `_parse_evict_models_before_snapshot()` (`modal_app.py:2501`) is true.
   - `modal_app.py:2506-2531` — `_parse_evict_retain_role()` (`clip_vae` = strict retain).
   - `modal_app.py:2532-2556` — `_parse_evict_restore_idle_seconds()`.
   With eviction forced off (step 2), the UNET stays in the snapshot → `unet_present=1`.

4. **Production profile actively REQUIRES the UNET-full snapshot.**
   `modal_app.py:1137-1145` — `production_snapshot_invariant()` demands `actual_unet == 1`;
   the pass line prints `expected_unet=1 actual_unet=1` (`modal_app.py:1174`).

5. **`effective_profile=production` follows from the wrapper default + request origin.**
   `modal_app.py:14492-14525` computes the effective profile from the request-origin
   `env_profile` (`modal_transport.py:600-604` injects the submitting process's profile)
   or the container-baked profile (`modal_app.py:2876-2878`). Both were `production`.

Consequence: snapshot-UNET activation path (9.4s UNET activation, 6.8s sampler wait,
RSS ~21.2 GiB) — the old architecture this task must not reproduce.

### Correct mechanism used (no script changes needed)

`V2_BENCHMARK_MODE=snapshot_restore_only` activates `deploy_and_run_v2_single.bat:47-67`,
which FORCES `COMFYMODAL_V2_ENV_PROFILE=inherit` (line 60), `SNAPSHOT_EXCLUDE_UNET=1` (50),
`EVICT_MODELS_BEFORE_SNAPSHOT=1` / `EVICT_RETAIN_ROLE=clip_vae` / `EVICT_RESTORE_IDLE_SECONDS=0`
(53-55), `SNAPSHOT_CONSTRUCTION=1` (66). Profile = `inherit` ⇒ the production branch (69-80)
can never run and cannot wipe the eviction contract. The deploy invocation exits without
probes (line 465). All explicit env values passed through unmodified.

---

## Exact effective deployment manifest

Verified from the actual effective process environment before Modal invocation
(`MANIFEST_VERIFIED` — every critical field matched intended):

```
V2 INTEGRATED DEPLOYMENT MANIFEST
env_profile=inherit
cpu_model_snapshot=1
vae_snapshot=1
snapshot_exclude_unet=1
evict_models_before_snapshot=1
evict_retain_role=clip_vae
evict_restore_idle_seconds=0
native_fast_disk_unet=1
conditioning_cache=1
conditioning_async_persistence=1*   (* unconditional when cache enabled — no env flag exists)
output_deferred_persistence=1*      (* unconditional — no env flag exists)
execution_unet_h2d_delay_ms=0
unet_activation_mode=late
vae_activation_mode=sampling_end
publish_restore_plan=0
single_use_containers=1
minimal_gpu_teardown=1
release_gpu_after_request=1
cpu=12
memory_mb=32768
memory_request=32768
gpu=rtx-pro-6000
cloud=   (unrestricted)
region=  (unrestricted)
```

Deploy-time echo (attempt-3 log, `deploy_agents34_construction3.log`): `env_profile=inherit`,
`eviction_enabled=1`, `eviction_role=clip_vae`, `eviction_idle_seconds=0`,
`snapshot_exclude_unet=1`, `snapshot_construction=1`, `native_fast_disk_unet=1`,
`release_gpu_after_request=1`, `[v2.region_pin] region=unpinned cloud=unpinned`.
Image bake: step 37 `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1`, steps 41-43 CPU=12/MEM=32768.

### Agent 3 feature flags (verified present; exact names from code)

| feature | env flag | requested | effective | code location |
|---|---|---|---|---|
| cache enable | `COMFYMODAL_V2_CLIP_CONDITIONING_CACHE` | 1 | 1 | clip_conditioning_cache.py:45,1631; baked modal_app.py:2911-2913 |
| prompt-cache Volume | `COMFYMODAL_PERSISTENT_CLIP_CACHE` (OR-gated) | 1 | created | modal_app.py:3265-3275 (`comfymodal-prompt-encoding-cache`, :283) |
| async persistence worker | (unconditional) | — | on | clip_conditioning_cache.py:1197-1222 (`_ensure_worker`), loop :1224-1261 |
| coalesced Volume commit | (unconditional) | — | on | clip_conditioning_cache.py:1263-1370 (`_persist_batch`→`_commit` :724-739), hook :1606-1617 |
| throttled reload | `COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_RELOAD_INTERVAL_S` | default 15.0 | default | clip_conditioning_cache.py:53,64,673 |
| teardown flush | (unconditional stage) | — | on | clip_conditioning_cache.py:1372-1430; stage `conditioning_cache_flush` modal_app.py:4928-4937 |
| enqueued vs persisted accounting | (unconditional) | — | on | counters :690-711; `enqueued` :1173, `persisted` :1361; reported model_preload.py:9566-9568 |

Evidence markers: `[v2.clip_conditioning_cache] event=mode/decision` (clip_conditioning_cache.py:101-102,113,1647);
`log_conditioning_cache_decision` model_preload.py:9428/9452/9556 (`lookup_wall_ms`,
`cache_store_wall_ms`, `enqueued=`, `persisted=`); trace `clip_conditioning_cache_lookup`
(model_preload.py:9406) / `clip_conditioning_cache_decision` (:9439/9574/9595).

### Agent 4 feature flags (verified present)

Deferred output persistence is **unconditional** (no env flag). Yield-before-commit ordering:
`modal_app.py:15298` (result event yield) → `modal_app.py:15305-15307` (`_finalize_deferred_commit`
awaited AFTER yield; definitive persistence event emitted after). Descriptor at :12826; commit
stashed :12838-12841, backgrounded :13448. Local: caller breaks on `result`
(`canonical_execution.py:2032-2034`); shielded drain `modal_transport.py:1001-1014`;
`_PERSISTENCE_STATUS_BY_PROMPT` (:44-81,139-172). Bounded asset retry 5 attempts
(`__init__.py:6682-6720`). Markers: `output_encode_start/end` (modal_app.py:12022/12036),
`output_persist_start/end` (:12814/:12832), `deferred_commit_start/end` (:13485,:13470,:13504;
local emit modal_transport.py:164), `final_result_received` (modal_transport.py:978).

---

## Snapshot construction proof (from construction container, `app_logs_agents34_full.txt`)

- `[v2.snapshot_model_eviction] stage=snapshot_pre_capture enabled=1 status=full_eviction_complete
  retain_role=clip_vae ... original_unet_alive_after_full_eviction=0 full_eviction_rss_drop_mib=8269.1`
- `[v2.snapshot_model_eviction] stage=snapshot_pre_capture enabled=1 status=ready ...
  container_retained=1 normal_cpu_snapshot_models_present=1 clip_present=1 vae_present=1
  unet_present=0 ... after_full_eviction_rss_mib=16252.02` (one non-fatal RSS-floor diagnostic:
  `status=non_fatal_floor_failure floor=final_reduction actual_mib=-1776.4` — capture RSS stayed
  elevated because fresh CLIP+VAE were reloaded into the retained container before capture;
  `unet_present=0` is the authoritative gate and held)
- `Snapshot created. Restoring Function from memory snapshot.`
- `[v2.snapshot_model_eviction] stage=restore_observed marker=1 cpu_snapshot_models_present=1
  clip_present=1 unet_present=0 retained_role=clip_vae rss_after_restore_mib=11477.02` (Run 1;
  11.2 GiB — the 12-13 GiB class, vs 21.2 GiB in the old bad run)
- `[v2.snapshot_model_eviction] stage=restore_release_retained retain_role=clip_vae
  status=container_retained container_present=1 clip_present=1 vae_present=1 unet_present=0`

## Restore proof (per run; trace events `snapshot_activation_invariant`)

| run | profile | models_container_present | clip_present | unet_present | status | instance |
|---|---|---|---|---|---|---|
| 1 | inherit | 1 | 1 | **0** | pass | 3ef16c9a… |
| 2 | inherit | 1 | 1 | **0** | pass | ff2a4ba2… |
| 3 | inherit | 1 | 1 | **0** | pass | 0bf69e59… |
| 4 | inherit | 1 | 1 | **0** | pass | 1cfcae91… |

All runs also show `[v2.env_profile] effective_profile=inherit container_profile=inherit
request_override_applied=0`, `[active_profile.publish] decision=skipped_post_snapshot_noop
checker_remote=0 setter_remote=0 active_profile_noop_ms=0.0`, `[v2.restore_publish] skipped
reason=flag_disabled`, and restore totals 392/1376/549/549 ms (restore_gpu_state 165/449/264/236 ms).

## Agent 3 runtime proof

**Run 1 (genuine cold miss):** `clip_conditioning_cache_lookup` hit_count=0 miss_count=1
(`lookup_wall_ms=197.1`, manifest read 196.5 ms — throttled reload). Decision
`miss_stored`, key `04bbc41a…ed2`, `encode_calls=1`, `encode_loop_wall_ms=3452.5`,
`cache_store_wall_ms=8.845` (foreground serialization+enqueue: serialization 8.2 ms,
enqueue 0.4 ms — **foreground did NOT wait for a Volume commit**; decision-time
`commit_ms=0.0`, `persisted=0`, `persist_failed=0`, `commit_failed=0`, `queue_depth=1`).

**Runs 2-4 (cross-container durability):** same key `04bbc41a…ed2` → `exact_hit`,
`encode_calls=0` (full conditioning served from the persisted entry, no CLIP encode):
- Run 2: lookup hit=1 miss=0, `lookup_wall_ms=2060.7` (cold entry read-back:
  `entry_lookup_ms=1841.7`, `data_bytes_read=3125640` = full 3.1 MB payload;
  manifest 59→60 entries — the Run-1 entry was added), fresh instance `ff2a4ba2…`.
- Run 3: hit=1 miss=0, `lookup_wall_ms=140.3` (reload interval cached), fresh instance.
- Run 4: hit=1 miss=0, `lookup_wall_ms=146.1`, fresh instance.

Chain proven: Run 1 enqueued → container exited → Runs 2-4 fresh single-use containers
reloaded the manifest from the shared Volume and hit the exact persisted entry.

## Agent 4 runtime proof

Run 1 ordering (wall-clock trace, `v2_2026-08-12_05-58-22/run_0.json`):
`output_encode_start 88.546s → output_encode_end 88.549s (593.1 ms, node 107, 2,938,565 bytes)
→ output_chain_end (descriptor ready, attempts=1 successful=1) → output_persist_end (4.857 ms)
→ result yielded → final_result_received local 89.117s (remote handoff 0.821 s) → remote/local
return 0.019 s`. Commit at collection time: `[v2.output] commit_ms=0.0 commit_status=skipped`
(registry sink already wrote the asset; finalizer emits the definitive persistence event with
`skipped=True, status=ok, detail="no commit needed"` AFTER the yield per
`modal_app.py:15305-15307`). Result path is provably not awaiting the commit: encode→persist
finished in ~0.6 s and the result left the container immediately; the old 0.9-1.3 s synchronous
commit no longer sits in the path.

**Asset retrievability (verified):** `modal volume ls comfymodal-runtime-config output_assets`
lists `output_assets/5da3cb38…fef.png`; `modal volume get` downloaded 2,938,565 bytes whose
SHA-256 **matches** the descriptor identity `5da3cb38aae1adf561c61bf2e0df35667cf67529cea0a9f8785d9c076c069fef`
exactly. Same deterministic asset id across all 4 runs (same prompt/seed).

## Teardown proof

No `[v2.teardown]` JSON diagnostics were produced because `COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS`
was not part of the mandated env list and is baked at deploy (propagation gate
`modal_app.py:3041-3042`). Teardown-mode proof instead:

- **Code path:** in-container `COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN` is empty → fallback
  `minimal_teardown = _resolve_single_use_containers()` = True (baked `SINGLE_USE_CONTAINERS=1`)
  at `modal_app.py:5050-5056`; `unload_all_models` only runs under `if not minimal_teardown`
  (`modal_app.py:5310` etc.) ⇒ **unload_all_models_ran=false**.
- **Behavioral:** the old full path took ~6.65 s unload + ~7.26 s GPU release before command
  return; here result→command-return was 0.019 s (Run 1) / 0.015 s (Run 2) — no full teardown
  window on the request path. Every run used a fresh restored instance (restore_count=1),
  consistent with single-use minimal teardown.

## Run 1 — cold-miss (unique conditioning identity)

Platform: GCP/us-east4 (unpinned). `command_start_to_restore_start_ms=77012.4` (scheduling),
`restore_total_ms=392.1` (python), `restore_gpu_state_ms=165.5`, `command_to_response_ms=88550.7`.
Pre-sampling: `pre_sampler_ms=3905.1`, graph_setup 1064.5 ms, cache lookup 197.1 ms
(cold miss), encode 3452.5 ms, foreground store/enqueue 8.8 ms, UNET fast-disk
`[v2.native_fast_disk_unet] decision=complete` (get_model 270.8 ms, bind 66.9 ms, to_device
2009.98 ms, 12.3 GB params, one construction/one read/one bind), execution H2D delay 0
(unet_h2d 5.5 ms prefill-lane). Sampling: `[v2.sampler_boundary] sampling_start→sampling_end
= 4787.9 ms` (8 steps). Output: encode 593.1 ms → persist 4.857 ms → result → local receipt;
asset fetch verified (see above). **Agent 3: cold miss + async enqueue + no foreground commit
block. Agent 4: yield-before-commit ordering + asset durable.**

## Run 2 — cross-container durability (same identity, fresh container)

Platform: GCP/us-east1. Scheduling 22.8 s, `restore_total_ms=1376.5` (first post-capture
restore of a new container; callback age 493 s), `command_to_response_ms=39897.4`.
Cache: **exact_hit**, encode_calls=0, payload read back 3,125,640 bytes, manifest 59→60.
Sampling 5349.8 ms. Same asset id; asset still retrievable. This is the Run-1-persisted-entry
consumed by a fresh container — Agent 3 durability item 4 proven.

## Run 3 — repeat hit (fresh container)

Platform: GCP/us-east1. Scheduling 214.6 s (horrible but valid — not repeated per protocol),
`restore_total_ms=548.9`, `command_to_response_ms=215172.0`. Cache: **exact_hit**,
encode_calls=0, lookup 140.3 ms (reload interval cached). Sampling 4879.7 ms. All gates pass.

## Run 4 — repeat hit (fresh container)

Platform: GCP/us-east1. Scheduling 22.0 s, `restore_total_ms=549.3`,
`command_to_response_ms=22566.6`. Cache: **exact_hit**, encode_calls=0, lookup 146.1 ms.
Sampling 4880.8 ms. All gates pass.

## Scheduling vs application wall

| run | command→response | scheduling (pre-python) | python restore | app wall (excl. restore) | sampling |
|---|---|---|---|---|---|
| 1 | 88.55 s | 77.01 s | 392.1 ms | ~11.1 s | 4787.9 ms |
| 2 | 39.90 s | 22.76 s | 1376.5 ms | ~15.7 s | 5349.8 ms |
| 3 | 215.17 s | 214.64 s | 548.9 ms | ~13.5 s | 4879.7 ms |
| 4 | 22.57 s | 22.00 s | 549.3 ms | ~12.8 s | 4880.8 ms |

Scheduling dominates; application behavior is stable (sampling 4.8-5.3 s, restore <1.4 s).

## Pass/fail

| gate | result |
|---|---|
| Deploy (attempt 3, after 2 infra/race failures) | PASS — `V2 deploy verified OK` |
| Snapshot composition (CLIP=1, VAE=1, UNET=0, retain=clip_vae) | PASS (all 4 runs) |
| Restore (inherit, unet_present=0, RSS 11.5 GiB class) | PASS (all 4 runs) |
| Active profile (checker/setter remote=0) + restore-publish disabled | PASS (all 4 runs) |
| Native fast-disk UNET, one read/bind/H2D, H2D delay 0 | PASS (all 4 runs) |
| Teardown minimal (code-path + behavioral, unload_all_models not run) | PASS |
| Agent 3 — cold miss, async persistence, no foreground commit block | PASS |
| Agent 3 — cross-container exact hit (Runs 2-4) | PASS |
| Agent 4 — result before persistence; commit after yield; asset fetch sha256 match | PASS |
| Generation budget | 4 valid runs (user requested 2 extra) |

## Evidence Agents 3 and 4 can use in their final reports

- Root-cause diagnosis of the production-profile clobber (file:line refs above).
- Feature-flag inventory for both agents (tables above); no code changes were needed.
- Per-run trace JSON: `comfymodal-data\benchmarks\runs\v2_2026-08-12_05-58-22` (Run 1),
  `…_06-07-06` (Run 2), `…_06-09-10` (Run 3), `…_06-12-53` (Run 4) — `run_0.json` +
  `summary.json`.
- Container logs: `app_logs_agents34_full.txt` (construction + restore evidence).
- Deploy log: `deploy_agents34_construction3.log`; wrapper logs `run{1..4}_agents34.log`.
- Asset: `output_assets/5da3cb38…fef.png` in Volume `comfymodal-runtime-config`
  (downloaded copy `asset_fetch_check.png`, sha256 verified).

## Changed files (this session)

- `latest_benchmark_workflow.json` — prompt uniqueness token (node 1497):
  `combined-diagnostic-run-1-20260811` → `agents34-integrated-deploy-20260812-run1`
  (one substring; guarantees a genuine cold miss; identical across runs for the hit proof).
- Evidence files (untracked): `deploy_agents34_construction{1,2,3}.log`,
  `run{1,2,3,4}_agents34.log`, `app_logs_agents34.txt`, `app_logs_agents34_full.txt`,
  `vol_ls.txt`, `vol_get.txt`, `asset_fetch_check.png`.
- `V2_AGENTS_3_4_INTEGRATED_DEPLOYMENT_REPORT.md` (this file).
- No commits; HEAD unchanged `e5483d5`; no agent code modified.
