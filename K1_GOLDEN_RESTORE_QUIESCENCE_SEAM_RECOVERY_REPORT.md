# K1 Golden Restore Recovery — Snapshot-Quiescence Seam Experiment Report

> **SUPERSESSION NOTICE (2026-08-30):** Historical Golden experiment report;
> preserve its restore evidence, but use
> `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for current generated-output
> semantics. Output durability is off by default; strict commit/reopen/hash
> proof is opt-in. S4 source publication durability remains mandatory.

Date: 2026-08-25
Batch: K1 (single hypothesis: unconditional `prove_snapshot_quiescence()` at the snapshot capture boundary is responsible for a substantial portion of the restore regression)
Verdict: **K1_SELECTED = YES** (change left UNCOMMITTED in the deployment lane worktree)

---

## 1. Exact before-state

### 1.1 Orchestration checkout (`custom_nodes\comfyui-modal`) — read-only baseline for this batch

- HEAD: `0c59f46e3238f421378e8852ebc548da815b70af` (branch `TESTING2`, E39 prune commit, golden lineage)
- Dirty R44-era worktree preserved untouched (full status: `.v2ctl/k1_manifest/git_status_full.txt`)
- SHA256 before any edit (recorded in `.v2ctl/k1_manifest/sha256_before.txt`):
  - `comfymodal_runtime/modal_app.py` = `55722C892D7331D24E98ECDE02DD88FF5AB8A341452E602AC6FAFEEF227F8137`
  - `tests/test_e40_canonical_authority.py` = `BB24106A45F978DD303F33A5FD203C5782C63DD68BDA669E209E0006D84F7553`
  - `comfymodal_runtime/snapshot_capture_hygiene.py` = `CE60431609CCCFBA9FF8A7919A85B286EBAC7A08AF1B4FB41A832E05F49F2037`
  - `comfymodal_runtime/clip_conditioning_cache.py` = `0660C367F67110384C160D60C9EBF58D9444B3C655EE0CE90FA846EE9D169842`
- Effective profile/flags captured: `.v2ctl/k1_manifest/config_before.json`, `flags_before.json`
  (resolved deploy fingerprint at session start per v2ctl config: `e945750c…`; doctor stored deployment `f15874bd…`)
- Diff vs `9a428fd` captured: `.v2ctl/k1_manifest/diff_9a428fd_seam_files.patch`, `diff_stat_vs_9a428fd.txt`
- Minimal GPU teardown: NOT changed by any user/agent in this worktree (no teardown-semantics +/- lines in the modal_app.py diff; only an unrelated `_teardown_diagnostics.record_file_write` diagnostic hook addition in the output path). Recorded as immutable baseline.
- This checkout received a temporary K1 seam edit + E40 test flip during lane discovery; **both were reverted byte-exact** (post-revert hashes match the before-state hashes above). It also received one INVALID paid deploy+run (see §6); it is otherwise exactly as found.

### 1.2 Deployment lane (`custom_nodes\comfyui-modal-r42`) — the J1/current-class lane, where K1 was executed

- HEAD: `6040c459f2766f2ccb2f97799c08ff53b616d54a` (branch `r42-golden-reconciliation`) — identical to the git_head recorded in the current-bad reference provenance (`v2_2026-08-25_02-55-12`)
- Dirty J1-era source preserved (status: `.v2ctl/k1_manifest/r42_git_status.txt`): modified `modal_app.py`, `config_authority.py`, `request_*_fastsafe.py`, `sampler_telemetry.py`, profiles; untracked `early_model_prep.py`, R44J1/J2 tests and reports
- modal_app.py SHA256 before edit: `B7AD894C49337E7FB88284E83E4637D9BC875F49A0926F009EA0324FFFEF2673` (`.v2ctl/k1_manifest/r42_sha256_before.txt`)
- Diff vs `9a428fd`: `.v2ctl/k1_manifest/r42_diff_9a428fd_modal_app.patch` (387 lines — J1 early model prep et al.)
- Minimal teardown: J2 post-result lifecycle diagnostics exist in this dirty state (`test_r44j2_post_result_lifecycle.py`, `_teardown_diagnostics` additions). Treated as immutable starting baseline per brief; not edited.
- Stored deployment fingerprint before my deploy: `32d4119609eca0ccabc22cbb875f23352647e65f13b62ae8266a01e66ef763f5` — EXACTLY the deploy_fingerprint of the current-bad reference run. Lane identity confirmed.
- Profile `r44-request-fastsafe` present on disk here (SHA256 `98CB8F58…`), extends `r42-golden-qd4` → `e29-tracer`.

## 2. Golden vs current behavior at the seam

### Golden (R43 era)

- `git log --all -S prove_snapshot_quiescence -- comfymodal_runtime/modal_app.py` → the call exists ONLY in `9a428fd` (Aug-24, "checkpoint proven BF16 same-storage cold path (R44I3 ARM A)") and descendants. The golden-lineage commit `0c59f46` contains NO such call anywhere in the startup/capture path (only the unrelated request-scoped `COMFYMODAL_V2_UNET_QUIESCED_TRANSFER`).
- At HEAD-era `snapshot_capture_hygiene.py` the module contains only the flag-gated (default-OFF) allocator-hygiene pass — no proof function at all.
- Golden capture boundary therefore ran: eviction policy → restore-memory freeze → runtime-state baseline → (flag-gated manifest/hygiene) → capture. No cache quiesce, no flush, no worker teardown.

### Current (pre-K1, r42 lane @ `6040c459` + J1 dirty)

`modal_app.py:9984-9994` (J6 identified this region as ~`:9877-9892`; drifted by J1 additions):

```python
# ── Snapshot quiescence proof (fail closed) ───────────────────────
# This is unconditional: the callback must not return a snapshot-ready
# state while conditioning-cache or registered executor work is live.
from .snapshot_capture_hygiene import prove_snapshot_quiescence
_snapshot_quiescence = prove_snapshot_quiescence()
_restore_timing["snapshot_quiescence"] = _snapshot_quiescence
if not _snapshot_quiescence.get("proven", False):
    raise RuntimeError(
        "snapshot capture quiescence could not be proven: "
        f"{_snapshot_quiescence}"
    )
```

### What `prove_snapshot_quiescence()` actually does (capture-state effect analysis)

(`snapshot_capture_hygiene.py:211`, `clip_conditioning_cache.py:2499`)

It is NOT a passive observer. Per invocation it:

1. Sets `ExactClipConditioningCache._snapshot_quiescing = True` — persistent instance state that is serialized INTO the snapshot;
2. Waits every prefetch event (bounded 10 s);
3. Calls `flush(remaining)` — synchronous persistence drain + final `_commit()` (Volume write);
4. Requires BOTH cache worker threads (`_worker`, `_lru_worker`) to be DEAD for `quiesced=True` — i.e. it forces worker teardown into the captured process shape.

All of these effects survive into the Modal memory snapshot and therefore into every restored container. The fail-closed RuntimeError is secondary; the capture-state mutation is the regression candidate, exactly as the brief hypothesized.

## 3. The K1 edit (exact hunks)

`.v2ctl/k1_manifest/r42_k1_seam_hunk.patch` (full diff incl. pre-existing J1 drift). The K1 hunk is:

```diff
-        # ── Snapshot quiescence proof (fail closed) ───────────────────────
-        # This is unconditional: the callback must not return a snapshot-ready
-        # state while conditioning-cache or registered executor work is live.
-        from .snapshot_capture_hygiene import prove_snapshot_quiescence
-        _snapshot_quiescence = prove_snapshot_quiescence()
-        _restore_timing["snapshot_quiescence"] = _snapshot_quiescence
-        if not _snapshot_quiescence.get("proven", False):
-            raise RuntimeError(
-                "snapshot capture quiescence could not be proven: "
-                f"{_snapshot_quiescence}"
-            )
+        # ── Snapshot quiescence proof: absent (K1 golden-restore seam) ────
+        # Golden R43 ran no quiescence proof at this capture boundary.  The
+        # post-R43 unconditional proof mutated pre-capture cache state
+        # (quiesce/flush join + worker teardown persisted into the snapshot)
+        # and is removed here; quiesce_for_snapshot stays available for its
+        # other callers.  Kept as None for the diagnostic manifest below.
+        _snapshot_quiescence = None
```

Plus the mirrored seam-test flip in `tests/test_e40_canonical_authority.py` (`test_capture_boundary_calls_quiescence_proof` → `test_capture_boundary_has_no_unconditional_quiescence_proof`, asserting absence). `quiesce_for_snapshot` itself remains in the codebase for its other callers — no unrelated snapshot safety removed.

**Why this is semantically equivalent to golden at this seam:** golden had NO statement at this position; the replacement re-establishes exactly that (no call, no timing key, no fail-closed branch), while defining `_snapshot_quiescence = None` solely so the pre-existing flag-gated diagnostic-manifest call at `:10025` (`quiescence=_snapshot_quiescence`, default-OFF via `COMFYMODAL_V2_SNAPSHOT_MANIFEST`) keeps compiling unchanged — on a measured run that block never executes, so captured state is byte-for-byte the golden semantics. No new flag introduced.

## 4. Local verification (r42 lane)

- `py_compile` OK on both edited files.
- Focused suites: `test_e40_canonical_authority.py`, `test_v2_snapshot_capture_hygiene.py`, `test_v2_snapshot_build_manifest.py`, `test_v2_snapshot_manifest_hygiene_extensions.py`, `test_e37_control_plane.py`.
- With K1 edit: 53 passed + 2 failed; without K1 edit (temporarily reversed, then re-applied byte-exact): identical failures. The 3 distinct failures observed across those files (`TestLoaderSelectionAuthority::test_inherited_speculative_flag_cannot_become_requested`, `::test_requested_clip_qd4_when_qd_reader_enabled`, `test_clean_lane_proof_validator_fails_closed_for_fallback_and_quiescence`) are **pre-existing dirty-J1-baseline failures**, reproduced without my edit — not my regression.
- ARM A / FastSafe reachability: `same_storage_assign` adoption verified remotely on every run (§7); E40 suite green except pre-existing items above.

## 5. Deployment identity (the ONE K1 deployment)

- Command: `python tools/v2ctl.py --profile r44-request-fastsafe --owner k1-quiescence-seam --json deploy-run` from `custom_nodes\comfyui-modal-r42`
- Deploy fingerprint: `34686e386040dece80db6bde2eb7aad8b8b23535fdf1c05ee07b749d82106206`
- Manifest: `comfyui-modal-r42\.v2ctl\deployments\deploy_20260825-015120_34686e38.json`
- Selector: `E37_CLEAN_LANE_VALIDATION` (canonical BAT), `COMFYMODAL_ACTIVE_SOURCE_DIR=comfyui-modal-r42`
- Provider/region: left at profile default (unpinned) to keep single-variable parity with the reference deployment. Observed placement varied per run (§7). AWS us-east-2 was NOT forced because doing so would require config modification beyond the one source change (brief §6 permits keeping existing selection).
- Image: `im-GIMsC0WZNtcZBSrLjGaaKK`; resources 12 CPU / 32768 MB / RTX-PRO-6000 (profile-resolved, matches golden resource shape).

## 6. Invalid first attempt (disclosed sunk cost)

Before identifying the r42 deployment lane, ONE deploy+run was executed from the orchestration checkout (`comfyui-modal`) with bare default profile `production`:

- Deploy `1697ed561d9f3bd1…` (manifest `comfyui-modal\.v2ctl\deployments\deploy_20260825-011527_1697ed56.json`), run `v2_2026-08-25_06-16-03`, request `v2-benchmark-0-32f5e2c99d39`.
- Gate FAILED (`runtime_status_not_nominal:DEGRADED`, clip loader unobserved/mismatch) — root cause: wrong config universe (production profile resolves CLIP to snapshot-resident `native_comfy`; no REQUEST_FASTSAFE family), NOT the seam. Evidence retained in `.v2ctl/k1_manifest/{run1_log,gate1_log}.txt`.
- That checkout's edits were reverted byte-exact afterwards. This attempt is excluded from all K1 evidence.

## 7. STEP-1 structural gate + 3-run cohort (deployment `34686e38…`)

Gate: `[v2ctl.gate] valid=1` (`comfyui-modal-r42\.v2ctl\gates\gate_20260825-065726_44c49708.json`) — snapshot HIT, exact canonical SHA, NOMINAL, zero fallback, zero generation reload all enforced by the validator.

Per-run raw-artifact evidence (boundaries from `run_001_sample.json`; no waterfall authority):

| Metric | Reference (current-bad) `v2_2026-08-25_02-55-12` | Run 1 `06-51-50` | Run 2 `06-56-0x*` | Run 3 `06-57-4x*` |
|---|---|---|---|---|
| request_id | `v2-benchmark-0-61b4e2bd9f9e` | `v2-benchmark-0-8e43af5eed14` | `v2-benchmark-0-0cd7501c769f` | `v2-benchmark-0-518c470f4b49` |
| provider/region | GCP (per artifact) | GCP us-east1 | AWS us-east-2 | AWS eu-south-2 |
| Modal UI restore | n/a | USER_UI_REQUIRED | USER_UI_REQUIRED | USER_UI_REQUIRED |
| restore_total_ms | 1670.909 | **300.133** | **680.098** | **480.695** |
| snapshot_restore_ms | 743.63 | **269.04** | **640.71** | **440.47** |
| restore_gpu_state_ms | 553.9 | **230.38** | **288.84** | **327.04** |
| cuda_init_ms | 3.46 | 4.99 | 8.09 | 5.12 |
| restore→method | startup (snapshot) | startup (snapshot) | startup (snapshot) | startup (snapshot) |
| Python first-boundary→durable (`first_remote_event_to_final_result_ms`) | 14494.099 | 14313.273 | 28619.637 | 24280.114 |
| output SHA | `20b10e1f…e5260` | same exact | same exact | same exact |
| RuntimeStatus | NOMINAL | NOMINAL | NOMINAL | NOMINAL |
| fallback / generation reload | 0 / 0 | 0 / 0 (`skipped_generation_match`, `cert_volume_reload_ms=0.0`) | 0 / 0 | 0 / 0 |
| CLIP same-storage | 398/398 | 398/398 (`same_storage_assign`, non_same_storage=0) | 398/398 | 398/398 |
| UNET storage identity | 453/453 | 453/453 | 453/453 | 453/453 |
| snapshot HIT | true | true (`consumed=true`, cert `plan_validation_fast_path`) | true | true |

\* run dirs under `comfymodal-data\benchmarks\runs\` (see `.v2ctl/runs/run_20260825-{020113,020221}_44c49708.json` manifests for exact paths).

No duplicate model-sized representation (CLIP `non_same_storage_count=0`, adoption `same_storage_assign`); no second model-sized H2D (single same-storage bind; UNET early source prep path untouched).

Cohort stats (restore_total_ms): **median 480.7, best 300.1, worst 680.1**. Improvement vs current-class reference: 1370.8 / 990.8 / 1190.2 ms — every run ≥700 ms better; replication rule satisfied with 3 runs.

Historical golden internal band: restore_total ≈ 258–394 ms (run 1 at 300.1 sits inside it; runs 2–3 on AWS regions sit in "clearly recovered" ≤700 ms).

Note on `python_to_durable`: placement is unpinned by design; runs 2–3 landed on AWS regions with inflated first-boundary→durable values (single samples immediately after the prior request, including provisioning noise on that boundary). Best like-for-like region sample (run 1) is statistically flat vs the reference (14.31 s vs 14.49 s).

## 8. Findings

1. The unconditional snapshot-quiescence proof IS the dominant cause of the internal restore regression: removing only its capture-state mutation recovered restore_total from ~1671 ms to 300–680 ms across all three true-cold runs, with snapshot_restore 744→269–641 ms and restore_gpu_state 554→230–327 ms. Mechanism: the proof's mutating pre-capture effects (`_snapshot_quiescing=True`, forced flush+commit, forced cache-worker teardown) were serialized into the snapshot and paid for on every materialization/restore.
2. Restore recovery did NOT by itself bring Python-first-boundary→durable result under 10 s (~14.3 s best, flat vs reference on the same boundary). Post-restore/request-path costs dominate that metric; the brief's projected ~9.8 s does not materialize from restore recovery alone. Also note: the brief's quoted 11.205 s representative does not match the raw artifact field of the cited reference run (14.494 s); raw-boundary numbers are used throughout per instructions.
3. Modal UI restore time is not programmatically available in artifacts → reported as USER_UI_REQUIRED, not synthesized.

## 9. Final verdicts

- **K1_SELECTED = YES** — seam change left UNCOMMITTED in `custom_nodes\comfyui-modal-r42` (`modal_app.py` + `tests/test_e40_canonical_authority.py`). No commit/push performed anywhere.
- **K1_RESTORE_REGRESSION_EXPLAINED = YES** (internal restore path fully explained; UI-level claim pending user-visible measurement).
- **K1_MODAL_RESTORE_TARGET_MET = USER_UI_REQUIRED**
- **K1_INTERNAL_RESTORE_TARGET_MET = YES** (all cohort runs ≤700 ms; best 300.1 ms inside the golden 258–394 ms band)
- **K1_PYTHON_TO_RESULT_SUB10 = NO**

Not done (per brief): wrapper-seeding changes, generation-authority changes, CLIP/UNET scheduling, FastSafe params, QD, sampler, GC, VAE, CUDA first-touch, teardown, profiler, flag-system cleanup, commits.

## 10. Evidence index

- Experiment manifest (before-state, hashes, diffs, logs): `comfyui-modal\.v2ctl\k1_manifest\`
- Deployment manifest: `comfyui-modal-r42\.v2ctl\deployments\deploy_20260825-015120_34686e38.json`
- Run manifests: `comfyui-modal-r42\.v2ctl\runs\run_20260825-{015448,020113,020221}_44c49708.json`
- Gate record: `comfyui-modal-r42\.v2ctl\gates\gate_20260825-065726_44c49708.json`
- Raw run artifacts: `comfymodal-data\benchmarks\runs\v2_2026-08-25_*\run_001_sample.json` (+ reference `v2_2026-08-25_02-55-12`)
