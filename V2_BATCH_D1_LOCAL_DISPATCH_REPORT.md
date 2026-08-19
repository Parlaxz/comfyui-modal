# V2 BATCH D1 — LOCAL DISPATCH ZERO-GAP REPORT

**Task:** Explain and eliminate the ~20.8 s pre-Modal stall (Batch D1 local dispatch),
then remove the registry cost from the TRUE external-command critical path.
**Constraint:** local-code-only — 0 Modal requests, 0 deploys, no commit, main branch
only, surgical edits (concurrent Phase D workers active).

---

## PHASE 1 — Root cause and attribution fix (prior D1 round)

### 1. Root cause

**The ~20.8 s is the one-time full ComfyUI node-registry preload of the benchmark
harness, running INSIDE the run-1 measured window.**

`_run_one` stamps `local_receive` (T1) and then executes
`await _ensure_full_node_registry()` — which imports the full `nodes` registry,
constructs a network-free `PromptServer` mirror, loads every comfy_extras module
and every custom node (1999 classes on this host) — BEFORE stamping `worker_start`.

Measured locally (standalone probe, no Modal): **87.9 s** (`registry_init_ms=87861.2`,
classes=1999). The codebase's own prior instrumentation documented **17.093 s**
(RUN 3). The observed **20.8 s** is the same load. Duration varies widely
(17 / 20.8 / 87.9 s) because the load is file-I/O dominated and this tree lives
under OneDrive ("AI HUB\ComfyUI June Install"), so disk-cache state and sync
contention dominate.

### 2. Deliberate or accidental? — **B (accidental stall)**

- `GAP_SECONDS` (V2_BENCHMARK_GAP_SECONDS) sleeps **between** runs
  (`if index + 1 < RUN_COUNT: await asyncio.sleep(GAP_SECONDS)`), i.e. AFTER a run
  and BEFORE the next run's `local_receive` stamp — it can never be inside a
  `local_receive → worker_start` window.
- The whole window is the registry preload; the "adjacent 2.9 s run" is run 2+ of
  the same process (registry cached → window ≈ 0, only scheduling/restore remains).
- The stall is benchmark-harness-only: production runs inside a long-lived ComfyUI
  server whose registry is preloaded at startup.

### 3. Phase-1 fix (attribution)

Preload the registry once in `main` before the run loop; `_run_one`'s await
short-circuits, so run-1 `local_receive → worker_start` ≈ 0 and the preload is
reported explicitly as `node_registry_preload_ms` (harness setup, never scheduling
— C3 semantics preserved). Instrumentation added: `cli_entry` mono,
`benchmark_iteration_selected`, `local_worker_submit`, `intentional_cold_wait`
wall+mono brackets, `modal_handle_ready` (direct/persistent_ipc), and the per-run
`[v2.trigger_to_submission]` reconciliation line (residual ≈ 0 target).

**Phase-1 limitation (this continuation):** the external command still paid the
17–90 s import between trigger and submission — the fix moved it out of the per-run
accounting window but NOT out of the command clock.

---

## PHASE 2 — Zero-gap: remove the registry from the external command path

### 4. Why the prior preload-before-loop fix was insufficient for an external command

`run_v2_single.bat` launches a FRESH Python process per command. The registry is
loaded once per process; no state survives between commands. Phase 1 moved the load
to `main()` before the run loop — but for an externally-invoked command that is
still "after command start", so:

- COMMAND → RESPONSE still included interpreter startup + the full registry preload;
- `user_equivalent_trigger → modal_submission_attempt` still measured 17–90 s.

Per the task's permanent semantics, scheduling = local trigger → Modal enqueue +
Modal scheduling; work after the trigger that is not scheduling must not be hidden —
it must be genuinely eliminated from the trigger path.

### 5. Research: why plan construction needs the live 1999-class registry

`build_execution_plan` (benchmark path: `validate=False`,
`collect_validation_proof=True`) needs the live `NODE_CLASS_MAPPINGS` for EXACTLY
two payloads:

1. **Deployment identity** (`_collect_plan_deployment_identity`):
   - `compute_registry_fingerprint(roots=...)` — sha256 over
     `name=module.qualname` entries, root-filtered;
   - `build_workflow_registry_proof(workflow, roots=...)` — per-class canonical
     identity (class name + logical module path + module-file sha256) over the
     workflow's class set.
   Both are **pure deterministic functions of registry content + workflow** and
   produce **plain serializable JSON payloads** (verified in
   `comfymodal_runtime/contracts.py:627` and `comfymodal_runtime/registry_proof.py`).
2. **Validation proof** (`_collect_plan_validation_proof` →
   `execution.validate_prompt`) — a plain dict, already cached in-process by
   `_PLAN_VALIDATION_MEMO` keyed by `_memo_key_plan_validation`
   (workflow_hash + deployment_combined_hash + custom_nodes_generation +
   stable_hash(registry_proof) + schema version).

Everything else in the benchmark plan-build path is registry-free (verified:
`optimizations.py` is repo-local stdlib-only; `compile_production_workflow` is pure
dict work; `validate=False` skips class-type checks; `prompt_sha256` /
`extract_model_stack` / `_collect_input_images` are pure).

**Conclusion:** the registry is required only to *produce* two serializable proof
payloads. No live class objects are needed at plan-build time once those payloads
exist. There is no fundamental reason a fresh command must import 1999 classes.

### 6. Options evaluated (task order)

1. **Reuse a running ComfyUI process** — the local server serves `/comfymodal/*`
   over HTTP (127.0.0.1:8188) and benchmarks already POST there (benchmark_modal.py),
   but the V2 harness runs standalone and the server may not be running; querying it
   for proof payloads adds a live-server dependency to the canonical command.
   Rejected as the primary path (fragile), noted as a future option.
2. **Persistent helper process** — the project ALREADY has one:
   `comfymodal_runtime/local_handle_client.py` + `local_handle_owner.py` spawn a
   detached owner that survives benchmark processes (loopback TCP, `owner.json`
   state). It caches Modal handles, not registry proofs; extending it would add IPC
   ops and an owner-side registry load. Equivalent benefit to disk persistence with
   more moving parts on Windows (no fork). Rejected as primary; documented as
   available if live-serving is ever needed.
3. **Persisted lightweight registry metadata keyed by generation/identity/hash —
   SELECTED.** A disk store holding the registry fingerprint + workflow registry
   proof + validation payload, keyed by the **deploy-frozen identity**
   (`.deployed_state.json`: `custom_nodes_generation` + `deployment_combined_hash`
   + `comfyui_version` + `comfyui_commit`) + normalized `comfyui_root` + workflow
   hash. On a valid hit, plan construction reuses the payloads verbatim — no
   registry import. Fail-closed on ANY key mismatch (generation changed →
   recompute).
4. **Cached execution plan keyed by workflow+generation** — superseded by 3: the
   plan's expensive inputs ARE the proof payloads; once they are persisted the plan
   build itself is ~100 ms, so caching the plan adds nothing.
5. **Existing persistent-IPC/control mechanisms** — the `.cache/v2_*.json`
   cross-process atomic disk-cache pattern (canonical_execution.py:71-239) and the
   `.deployed_state.json` deploy-frozen identity record were REUSED by the store
   (same atomic-write/thread-lock/schema/bounded pattern; same identity source).
6. **Full registry fundamentally required?** — NO (see §5). It is required only
   once per identity-generation to build the persisted payloads.

Correctness note: the store is keyed by the **deployed** generation (container
readback), so the persisted proof reflects the deployed registry — parity-correct
even if the local tree later drifts (the drift is not deployed; a new deploy
freezes a new generation and recomputes).

### 7. Selected architecture

**Disk-persisted registry-proof + validation-proof store**
(`comfymodal_runtime/registry_proof_store.py`, new, stdlib-only):

- Store file: `<repo>/.cache/v2_registry_proof_store.json` (env override
  `COMFYMODAL_V2_REGISTRY_PROOF_STORE`); identity record path overridable via
  `COMFYMODAL_V2_DEPLOYED_STATE_JSON`.
- `lookup(workflow_hash, comfyui_root)` — fail-closed (file/schema/anchor/key match
  all required); `save(fields)` — best-effort, atomic, thread-locked, bounded
  (8 entries, oldest evicted), merge-on-same-key; `has_generation_entry()` —
  generation-level priming check; `current_identity_anchor()` — all four
  `.deployed_state.json` fields or `{}`.
- Seams (canonical_execution.py):
  - `_collect_plan_deployment_identity` — store hit (frozen identity + workflow
    hash) reuses persisted `registry_fingerprint`/`registry_proof`; miss falls back
    to the live computation verbatim.
  - `build_execution_plan` — the validation memo now checks the disk store between
    the in-memory memo and `execution.validate_prompt`; after the build, the full
    entry (fingerprint + proof + validation) is persisted for the next process.
- Harness (tools/benchmark_v2_direct.py):
  - `_registry_proof_store_covers(workflow)` — store-hit decision (requires
    validation payload when `COMFYMODAL_V2_PLAN_VALIDATION_PROOF` is on).
  - `_run_one` / `_run_acceptance_request` — skip `_ensure_full_node_registry()`
    on store hit (`[v2.harness] registry_load=skipped store_hit=yes`); else timed
    load (which populates the store via the plan build).
  - `main` preload — skipped when `has_generation_entry()`
    (`[v2.harness] node_registry_preload_skipped store_generation_entry=yes`).
  - **`--prime-registry-proof`** CLI mode: loads the registry ONCE, builds the
    canonical benchmark workflow plan (no transport, no Modal, no submission), and
    persists the store entry — invoked from `deploy_and_run_v2_single.bat` right
    after `record_deployment_identity.py` in BOTH deploy branches.
- New per-run `[v2.user_trigger]` line reporting the three never-conflated clocks
  + store state; `user_equivalent_trigger_to_modal_submission_ms` also added to
  `[v2.host_submission_breakdown]`.

### 8. Registry work now occurs WHEN

- **At deploy time** (recommended path): `deploy_and_run_v2_single.bat` runs
  `--prime-registry-proof` after freezing `.deployed_state.json` — the one-time
  17–90 s load happens BEFORE any user benchmark trigger.
- **On the first benchmark command after a deploy that did not prime** (fallback):
  the command itself pays the load once and persists the store entry; every
  subsequent command (same deployment) is fast.
- **Never** after a valid store entry exists: fresh external commands skip the
  registry entirely.

### 9. Expected healthy numbers

| metric | expected |
|---|---|
| `user_equivalent_trigger_to_modal_submission_ms` (primed) | interpreter boot (~1–2 s, measured 0.9–1.7 s) + submission-path work (~100–200 ms: plan build ~94 ms + transport ms) → **~1.2–2.2 s total; submission-path portion < ~500 ms** |
| `user_equivalent_trigger_to_response_ms` | above + Modal scheduling + restore + execution (deployment-dependent; scheduling ~1.6–2.9 s unchanged) |
| `process_start_to_response_ms` | boot + all of the above (same as trigger-to-response when the trigger ≈ process start) |
| run-1 `local_receive_to_worker_start_ms` | ≈ 0 (was 20 828 ms) |
| `[v2.trigger_to_submission]` residual | ≈ 0, `reconciliation_status=complete` |
| `scheduling_ms` | unchanged in magnitude (only local-attributable time was moved) |

### 10. Files changed (Phase 2)

- `comfymodal_runtime/registry_proof_store.py` — NEW store (fail-closed, atomic,
  bounded, thread-locked).
- `canonical_execution.py` — store fast path in `_collect_plan_deployment_identity`
  (~L1235), disk validation-memo check (~L1355), persist block (~L1388).
- `tools/benchmark_v2_direct.py` — `prompt_sha256` import, `_registry_proof_store_covers`,
  store-gated registry in `_run_one` (~L2477) and `_run_acceptance_request`
  (~L4113), `build_user_trigger_line` (~L2426) + per-run print (~L2971),
  `user_equivalent_trigger_to_modal_submission_ms` in the host breakdown (~L2321),
  generation-gated main preload (~L8450), `--prime-registry-proof` (~L8307, L9100).
- `deploy_and_run_v2_single.bat` — `--prime-registry-proof` after BOTH
  `record_deployment_identity.py` calls (L301-306, L452-457).
- Tests (new + pinned adjustments): `tests/test_v2_batch_d1_registry_proof_store.py`
  (NEW, 22 tests); store-isolation setUp in `test_benchmark_v2_proof_collection.py`,
  `test_plan_validation_proof.py`, `test_deployment_proof.py`, `test_step3_fast_path.py`
  (additive env isolation; no semantics changed); call-site count 2→3 in
  `test_harness_call_sites_request_proof_collection` (the prime path is the third
  legitimate `build_execution_plan` call site).

`run_v2_single.bat` — **unchanged** (the canonical user command stays
copy-pasteable).

### 11. Tests

| suite | result |
|---|---|
| `test_v2_batch_d1_registry_proof_store` (NEW: store round-trip/fail-closed/bounded/merge, identity fast path, validation disk-hit, miss-persist, coverage helper, `_run_one` store-hit skips registry, user-trigger line, prime mode) | 22/22 OK (0.9 s) |
| `test_v2_batch_d1_local_dispatch` (prior D1 suite) | 9/9 OK |
| `test_v2_host_submission_breakdown` + `test_benchmark_v2_proof_collection` | 19/19 OK |
| `test_plan_validation_proof` + `test_deployment_proof` + `test_step3_fast_path` | 60/60 OK |
| `test_batch_c1_immutable_plan_identity` + step3 parity suites | 59/59 OK |
| `test_v2_benchmark_trace_handoff` | 33/33 OK (23.7 s) |
| `py_compile` (4 files) | OK |

No sleeping in tests — mocks/fake clocks/synthetic store data only. Real store
file verified absent after every run.

commit = **none** · Modal requests = **0** · deploys = **0**

---

## 12. Final D1 deliverable fields

- **prior root cause** = one-time full ComfyUI node-registry preload
  (`_ensure_full_node_registry`, 17–90 s; observed 20.8 s) inside the run-1
  `local_receive → worker_start` window — accidental (B), not the GAP cooldown.
- **why prior preload-before-loop fix was insufficient for external command** =
  a fresh `run_v2_single.bat` process paid the import after command start; the
  fix only improved attribution/production-equivalent per-run timing, not the
  external command clock.
- **selected architecture** = disk-persisted registry-proof + validation-proof
  store (`.cache/v2_registry_proof_store.json`) keyed by deploy-frozen identity
  (generation + deployment hash + comfyui version/commit) + comfyui_root +
  workflow hash; `--prime-registry-proof` at deploy; store-gated registry load in
  the harness; fail-closed on every key mismatch.
- **registry work now occurs when** = once at deploy time (prime), or once on the
  first unprimed command per deployment; never on later commands.
- **true user-equivalent trigger→submission expected** = submission-path work
  (~100–200 ms) after interpreter boot (~1–2 s); run-1 `local_receive→worker_start`
  ≈ 0; residual ≈ 0.
- **process-start overhead** = interpreter + module imports ~0.9–1.7 s (measured)
  — reported separately, never conflated (three clocks: `process_start_to_response_ms`,
  `user_equivalent_trigger_to_response_ms`, `user_equivalent_trigger_to_modal_submission_ms`).
- **files changed** = `comfymodal_runtime/registry_proof_store.py` (new),
  `canonical_execution.py`, `tools/benchmark_v2_direct.py`, `deploy_and_run_v2_single.bat`,
  `tests/test_v2_batch_d1_registry_proof_store.py` (new) + 4 pinned-test files
  (additive isolation).
- **tests** = 203 total green (22 new + prior D1 9 + pinned 172).
- **commit** = none · **Modal requests** = 0 · **deploys** = 0
- **READY_FOR_D6 = YES** — mechanism fully implemented and locally proven
  deterministic (no remote behavior change; dispatch path untouched).
- **remaining remote validation** = after the next deploy: (1) confirm
  `--prime-registry-proof` prints `prime_ok:true` at deploy; (2) `run_v2_single.bat`
  prints `registry_load=skipped store_hit=yes` + `node_registry_preload_skipped
  store_generation_entry=yes`; (3) `user_equivalent_trigger_to_modal_submission_ms`
  ≈ boot + < ~500 ms submission path; (4) `scheduling_ms` unchanged (~1.6–2.9 s);
  (5) `[v2.trigger_to_submission]` residual ≈ 0 and `intentional_cold_wait_before_run_ms`
  ≈ configured gap on run 2+; (6) batch acceptance gates still pass with the
  persisted proof (parity with container manifest).
