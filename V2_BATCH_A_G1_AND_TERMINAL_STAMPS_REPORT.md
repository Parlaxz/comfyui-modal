# V2 Batch A — G1 Plan-Receipt UNET Scheduling + Terminal Cleanup Stamps

Date: 2026-08-14
Scope: implementation of the two already-researched Batch-A items, per the batch A brief. No deploy, no Modal runs, no commit, no branch.

Reference:
- `V2_UNET_READ_H2D_OVERLAP_RESEARCH.md` (D1 design, §5/§13, stop conditions §14)
- `V2_GENERIC_FIRST_NODE_PRESAMPLER_DELAY_RESEARCH.md` (G1 confirmation)
- `V2_RESULT_HANDOFF_RESTORE_AND_SETUP_RESEARCH.md` (§5 item 5 — two-stamp instrumentation)

---

## 1. Exact old schedule point

`comfymodal_runtime/modal_app.py` `_run_in_process` — the execution-phase fast-disk UNET lane was submitted at what is now `modal_app.py:11387-11401` (was 11416 pre-edit):

```python
        _snapshot_models = self._cpu_snapshot_models
        _snapshot_unet_absent = bool(
            _cpu_snapshot_active
            and _snapshot_models is not None
            and getattr(_snapshot_models, "unet", None) is None
        )
        _execution_unet_scheduled = False
        if _snapshot_unet_absent:
            _execution_unet_scheduled = bool(
                self._preload_bridge.schedule_execution_unet(
                    trace=trace,
                    request_id=str(context.request_id),
                )
            )
```

i.e. after: `_configure_runtime`, `_load_legacy_runtime`, `graph_execution_start`, the entire CPU-snapshot binding block, `_enforce_snapshot_activation_invariant`, and `schedule_execution_prefill`. The lane's `read_start` therefore fired only after that whole serial setup (~90–110 ms into the request on healthy runs).

**This call is UNCHANGED and remains as the safety path.**

## 2. Exact new schedule point

`_run_plan_stream_impl` — immediately after plan receipt. New call at `modal_app.py:16066-16069`, directly after `plan = ExecutionPlan.from_dict(...)` (`:16053`) and `_deserialize_end_ns` (`:16055`):

```python
        self._maybe_schedule_execution_unet_at_plan_receipt(
            plan,
            request_id=str(_t4_request_id or request_id),
        )
```

The lane's `read_start` can now fire ~70–110 ms earlier on healthy exact-hit runs (research D1 expected saving).

Nothing was moved into `startup(snap=True)`, `restore()`, or before plan parse. The earliest-safe boundary (plan receipt) is respected exactly.

## 3. Identity derivation path (single source of truth)

New method `ModalRuntimeEntrypoint._maybe_schedule_execution_unet_at_plan_receipt` (`modal_app.py:7517-7660`) derives identity with the **exact same three calls the binding block uses**:

```python
workflow = _thaw(plan.workflow) if hasattr(plan, "workflow") else {}
model_stack = dict(plan.model_stack) if hasattr(plan, "model_stack") else {}
request_model_key = derive_model_key(workflow)
request_prefill_key = derive_prefill_key(request_model_key, workflow)
request_model_spec = build_restore_model_spec(workflow, model_stack)
```

The derived values are stashed on the instance (`_plan_receipt_request_model_key/_prefill_key/_model_spec`) and the binding block (`modal_app.py:11168-11204`) **reuses the stash instead of re-deriving**; it falls back to its own derivation only when the stash is absent (non-eligible shapes, e.g. retained-UNET configs — identical to prior behavior). A cheap re-derivation compare emits `[v2.g1_identity_guard] plan_receipt_key!=binding_key` if the two ever diverge (diagnostic only — the downstream sampler `verify_retained_unet_identity` remains authoritative and untouched). No parallel identity implementation was created.

## 4. Snapshot-UNET-absent hard gate

Early scheduling runs ONLY when the container-level predicate definitively proves snapshot-UNET absence, plus the two ambiguity guards that make the later binding decision knowable at plan receipt:

1. `self._cpu_snapshot_models is not None` — else skip (legacy / no snapshot; the legacy background UNET defer owns UNET exactly as before).
2. `getattr(self._cpu_snapshot_models, "unet", None) is None` — the definitive retained-UNET-absent fact (the same core of the later `_snapshot_unet_absent` predicate at `:11387-11391`).
3. If the container is present-but-**inactive**, require a retained CLIP (`getattr(models, "clip", None) is not None`) — otherwise the binding block takes the never-serve path (bridge clear) and an early read would be wasted. This is the "if retained-UNET state is ambiguous: do nothing early" rule.
4. Role-match gate: `_canonical_role_match_report(request_model_spec, snapshot_model_spec)["compatible"]` — mirrors the binding block's own check; when incompatible the binding block clears the bridge / raises in production, so early scheduling is skipped.
5. `request_model_key.unet_identity` truthy — missing/malformed identity skips safely (returns False, never raises).

Retained-UNET, legacy, ambiguous, and mismatched configurations behave **exactly as before** (later scheduling path untouched).

## 5. Single-flight proof

Three independent layers, all pre-existing (none weakened):

1. **Bridge guard** — `V2LoaderBridge.schedule_execution_unet` (`model_preload.py:10275-10281`): `if prep.unet_future is not None: return True` (emits `unet_execution_schedule reason=already_prepared`).
2. **Coordinator atomic check-and-set** — `ModelPreloadCoordinator.schedule_execution_unet` (`model_preload.py:8690-8697`): under `_pool_lock`, `if prep.unet_future is not None: return prep.unet_future` — the pool is the only enqueue point.
3. **Carry-over** (new, `model_preload.py:10465-10484`): a clip-only publication (`unet is _LOADER_MISS`) that follows the plan-receipt schedule keeps the exact in-flight future (`not done()` and same `model_key`) on the new preparation, sharing the diagnostics object so the worker's completion timestamps stay readable. A **done** future (previous request) or a different key is deliberately NOT carried, so every request still gets its own lane on multi-use containers.

The later `_run_in_process` call at `:11387-11401` sees `prep.unet_future is not None` → `True` no-op (`already_prepared`). Exactly one UNET active read, one bind, one H2D per request. Verified by `test_coordinator_schedule_execution_unet_is_single_flight`, `test_carry_over_*` (in-flight carried; done/different-key not carried), and `test_g1_inflight_lane_is_respected_single_flight`.

## 6. Retained / legacy behavior

- **Retained CPU-snapshot UNET** (`unet is not None`): gate 2 fails → no early path; binding block serves the retained object; later scheduling/early-activation unchanged.
- **Legacy / no snapshot** (`_cpu_snapshot_models is None`): gate 1 fails → untouched; the legacy background UNET defer keeps full ownership.
- **Diagnostic UNET bypass** (snapshot has UNET, bypass flag set): gate 2 fails → unchanged.
- **Never-serve partial container** (inactive, no CLIP): gate 3 fails → unchanged.
- **Production identity mismatch**: gate 4 fails → early path silent; the binding block still raises / clears as today.
- **Multi-use container**: the stash is reset per request at method entry; the carry-over only bridges an in-flight (same-request) future, so a new request always schedules its own lane.

## 7. Error-semantics proof

- The early schedule is submitted through the **existing** single-flight scheduler and the **existing** `_execution_unet` → `_load_unet` worker — no new worker pool, thread, H2D path, checkpoint reader, UNET future, GPU stream, or copy mechanism.
- A failed early lane surfaces at graph demand exactly as today: `_consume_model_impl` turns the future exception into `_LOADER_MISS` with the existing fallback (bridge miss → original loader with all native fast-disk guards). `_LOADER_MISS` handling, future exception propagation, and fallback behavior are untouched.
- The early path is best-effort and never raises (`except Exception` → `[v2.execution_unet] plan_receipt_schedule_skipped reason=error:...` → returns False); every failure falls back to the unchanged `_run_in_process` safety schedule.
- No early failure is fatal before the normal consumer reaches it.

## 8. Trace / timestamp fields

Existing execution-UNET trace markers reused (`unet_execution_schedule`, `preload_submitted`, `preload_worker_started`, `unet_prepare_start/end`, `read_start/read_end` via the lane trace). One compact new marker, emitted into the request trace at plan receipt:

- `unet_execution_plan_receipt_schedule` — metadata: `request_id`, `unet_identity_hash` (16 chars), `snapshot_unet_absent`, `snapshot_active`, `role_compatible`.

To keep worker events in the request trace, the plan-receipt path creates the request `RuntimeTrace` at submit time; the `ExecutionContext` created later (`modal_app.py:16285-16293`) reuses it via `_plan_receipt_trace`, so lane events and the rest of the request share one trace (waterfall accounting unchanged — same event names, same fields, no new accounting rows).

New terminal-cleanup fields (module helper `_stamp_terminal_cleanup`, `modal_app.py:5059-5084`), written into the terminal `event["data"]` next to `remote_result_emit_wall_unix_ns`/`remote_result_emit_mono_ns` (fallback: the event dict itself when no `data`):

| Field | When |
|---|---|
| `terminal_cleanup_start_wall_unix_ns` | outer wrapper identifies terminal result, immediately before `_run_terminal_cleanup_sync` (`modal_app.py:15813`) |
| `terminal_cleanup_start_mono_ns` | same point |
| `terminal_cleanup_end_wall_unix_ns` | immediately after `_run_terminal_cleanup_sync`, before the outer yield (`modal_app.py:15819`) |
| `terminal_cleanup_end_mono_ns` | same point |

The exception path (`:15830-15859`) stamps the synthesized error event identically. Host reconciliation can now derive:

- `remote_cleanup_ms = terminal_cleanup_end_mono_ns − terminal_cleanup_start_mono_ns` (same-process monotonic)
- `transport_after_cleanup_ms = local_result_received_wall − terminal_cleanup_end_wall_unix_ns`

No extra RPC. No cleanup deferral. No result-delivery or persistence semantics changed.

## 9. Files changed

- `comfymodal_runtime/modal_app.py` — new method `_maybe_schedule_execution_unet_at_plan_receipt`; plan-receipt call; `ExecutionContext` trace reuse; binding-block identity reuse + divergence diagnostic; new `_stamp_terminal_cleanup` helper; stamp calls in `run_plan_stream` (normal + exception paths).
- `comfymodal_runtime/model_preload.py` — in-flight UNET future carry-over in `_init_ready_preparation`.
- `tests/test_v2_batch_a_g1_terminal_stamps.py` — NEW narrowly scoped test file (16 tests, all passing).

## 10. Local checks (all run; no deploy, no Modal generation)

| Check | Result |
|---|---|
| `ast.parse` both files | OK |
| `import comfymodal_runtime.modal_app` / `model_preload` | OK |
| `tests/test_v2_batch_a_g1_terminal_stamps.py` (16 tests) | **16 passed** |
| early schedule eligibility (fast-disk shape) | schedules, stashes identity, emits marker |
| duplicate schedule remains no-op | coordinator + bridge single-flight proven (same future) |
| retained UNET skips early path | skipped, no bridge touch |
| legacy / no-snapshot skips | skipped |
| inactive-without-CLIP (ambiguous) skips | skipped |
| role mismatch skips | skipped |
| missing/malformed identity skips safely | returns False, never raises |
| carry-over: in-flight same-key survives clip-only publication | carried (shared diagnostics) |
| carry-over: done previous-request future / different key | NOT carried |
| terminal stamps populated on result data + error fallback | fields set, existing fields untouched |

## 11. Expected healthy saving

≈70–110 ms wall on healthy exact-hit runs (read starts at plan receipt instead of after the full binding block; research D1: healthy <200 ms bucket, ≈600 ms slow-first-request host, ≈220 ms bad-bandwidth host). This is a scheduling fix only — NOT an H2D-bandwidth fix; the structural ~2.5–2.9 s exposed UNET pipeline on exact hits is unchanged.

## 12. Remaining integration requirements

1. One benchmark cohort run (existing harness, no code change) to confirm: exactly one UNET active read, one bind, one real H2D; `[v2.execution_unet] scheduled=1 via=plan_receipt` printed at plan receipt and the later schedule logging `already_prepared`; `[v2.g1_identity_guard]` divergence print never fires; waterfall accounting unchanged; graph/sampler identity verification passes.
2. Host-side reconciliation consumption of the four `terminal_cleanup_*` fields (derivation formulas in §8) — no host code was required by this task, but the next batch/report should surface `remote_cleanup_ms` and `transport_after_cleanup_ms`.
3. Confirm the early read does not regress read/H2D throughput on a run-4-class host (research stop condition 4 — A/B on a bad-bandwidth host; the research's run-4 analysis says no contention shift is expected).

---

## Completion output

report path = `V2_BATCH_A_G1_AND_TERMINAL_STAMPS_REPORT.md`
changed files = `comfymodal_runtime/modal_app.py`, `comfymodal_runtime/model_preload.py`, `tests/test_v2_batch_a_g1_terminal_stamps.py`
commit = none
deploy count = 0
Modal runs = 0

G1 implemented = YES
early schedule boundary = immediately after `ExecutionPlan.from_dict` (plan receipt), `modal_app.py:16066-16069`
same identity derivation reused = YES (`derive_model_key`/`derive_prefill_key`/`build_restore_model_spec`, stashed and reused by the binding block)
snapshot-unet-absent hard gate = YES (`_cpu_snapshot_models.unet is None` + role-match + activation-eligibility guards; ambiguous states do nothing early)
later scheduler remains = YES (`modal_app.py:11387-11401` untouched, safety path)
later scheduler becomes idempotent no-op = YES (`prep.unet_future is not None` → `already_prepared`)
new UNET threads/pools = 0
new H2D mechanism = NO

terminal cleanup start stamp = YES (`terminal_cleanup_start_wall_unix_ns`/`terminal_cleanup_start_mono_ns`)
terminal cleanup end stamp = YES (`terminal_cleanup_end_wall_unix_ns`/`terminal_cleanup_end_mono_ns`)

expected healthy wall saving = ≈70–110 ms (≈600 ms slow-first-request host; ≈220 ms bad-bandwidth host)
ready for integration = YES
