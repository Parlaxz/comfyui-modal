# Step-3 Persistent-IPC Transport Acceptance — PRODUCTION ACCEPTED

**Date:** 2026-08-13
**Repo:** `comfyui-modal` (HEAD `e5483d5a7a5414fc9baae84d16e02c13bf270520`, branch `TESTING2`, working tree — `commit hash: none`)
**Campaign status: STEP 3 PRODUCTION ACCEPTED** — the single sanctioned validation/discard generation returned `decision=plan_validation_fast_path consumed=1` with every parity axis green and every legacy-path RPC bypassed. The A/B campaign may resume.

---

# Executive result

The final Step-3 blocker is resolved. The root cause was **not** the persistent-IPC transport: three independent local experiments (ExecutionPlan round-trip; real client → real owner server → intercepted forwarder; full production-flow replication) plus a 12-scenario regression suite proved the `registry_proof` survives the entire host chain byte-for-byte. The actual bug was one function gate: `ExecutionPlan.__post_init__` **freezes** `deployment_identity` (contracts `_freeze`), turning the nested `registry_proof` into a `MappingProxyType`, and `evaluate_workflow_registry_parity`'s strict `isinstance(..., dict)` checks rejected the frozen form with `plan_registry_proof_unavailable` — the exact 23:54 production symptom (workflow_class_count=0). One surgical fix (Mapping-based acceptance), one fresh deployment (the fix is deployed image code), and one validation/discard generation prove the fast path end-to-end.

# Existing good Step-3 state (all re-verified on the fresh deployment)

| Axis | Value | Match |
|---|---|---|
| deployment hash | `1bd881d798947977…` (baked == persisted == plan-carried) | 1 |
| dependency identity | `e996435d47bc4512…` (plan == snapshot) | 1 |
| custom-node generation | `fbecafb8ae72728ebc36d581b8356e39` (baked == persisted) | 1 |
| ComfyUI core | host == image == `f49bdb655707b979…` | `comfyui_core_match=1` |
| snapshot proof | `complete=True valid=True gen_ok=1` | 1 |

# Persistent-handle architecture (traced end-to-end)

```
benchmark_v2_direct._run_one
  → build_execution_plan (plan with deployment_identity.registry_proof)
  → execute_plan → _canonical_dict = plan.to_dict()                     (A/B checkpoints)
  → ModalTransport.run_plan_stream (plan_dict + origin-info mutations)  (C)
  → _persistent_client.run_plan_stream(key, workspace, plan_dict)       (persistent_hit)
      → local_handle_client._write_json: {"op":"run_plan_stream", "payload": dict(plan_dict), …}
      → 127.0.0.1 owner socket (newline-framed JSON; IPC_STREAM_LIMIT = 128 MiB)
      → local_handle_owner._handle_connection → json.loads → auth → op dispatch (D)
      → handle_run_plan_stream: payload = request["payload"]  →  _open_plan_stream  (E)
      → handle.run_plan_stream.remote_gen.aio(payload, request_id=…)   (Modal forward)
      → container run_plan_stream → _safe_payload → ExecutionPlan.from_dict (F/G)
      → _execute_v2_prompt_executor → evaluate_plan_snapshot_parity(plan.deployment_identity, snapshot_proof)
```

# Payload checkpoint trace

| Checkpoint | registry_proof | classes | complete |
|---|---|---|---|
| A after build_execution_plan | present | 31 (dispatch) / 41 (precheck set) | True |
| B plan.to_dict() | present | 31 | True |
| C after transport mutations | present | 31 | True (serialized 15 541 B total) |
| D owner JSON decode | present | 31 | True |
| E owner forwarder boundary | **present** | 31 | True |
| F container entry | present (frozen `MappingProxyType` — from `ExecutionPlan.__post_init__`) | tuple | True |
| G after from_dict | present (frozen) | 31 | True |
| **gate** | **rejected by `isinstance(plan_proof, dict)` → `plan_registry_proof_unavailable`** | 0 | — |

The "first checkpoint where registry_proof disappeared": **none** — it was present at every checkpoint including container receipt. The loss was a type-check rejection at the final gate, not transport.

# Exact field-loss boundary / root cause

- Function: `comfymodal_runtime/registry_proof.py::evaluate_workflow_registry_parity` (and `_proof_stats`) — strict `isinstance(plan_proof, dict)` / `isinstance(snapshot_manifest, dict)` / `isinstance(manifest_classes, dict)` / `isinstance(classes, list)`.
- Why only `registry_proof` appeared "missing": `ExecutionPlan.__post_init__` freezes `deployment_identity` via `contracts._freeze` → nested dicts become `MappingProxyType` (lists become tuples). All other identity fields are scalars (strings/bool) and survive freezing; only the nested proof/manifest dicts were frozen and rejected.
- Proven reproduction: `evaluate_workflow_registry_parity(_freeze(proof), _freeze(manifest))` → pre-fix `plan_registry_proof_unavailable` / 0/0/0; post-fix match=True with counts 3/3/3. Identical to the production 23:54 output (`workflow_class_count=0 … reason=plan_registry_proof_unavailable`).

# IPC size analysis

- Client request framing: `json.dumps(payload, default=str, ensure_ascii=False) + b"\n"`; owner `reader.readline()` with `limit=IPC_STREAM_LIMIT = 128 * 1024 * 1024` (local_handle_client.py:29).
- Measured payload: 15 541 serialized bytes for the full production-compiled plan incl. the 41-class proof — **~0.01% of the limit**; normal payload safely below limit: YES.
- Malformed (`b"not-json\n"`) → JSON decode failure → connection closed (explicit). Oversize (line > limit) → `LimitOverrunError` → connection closed (explicit, tested with a small-limit server). No silent stripping path exists in the framing.

# Direct Modal control path

`ModalTransport.run_plan_stream` V2 direct branch (`handle.run_plan_stream.remote_gen.aio(plan_dict, request_id=…)`) passes the identical `plan_dict` object through standard Modal serialization (cloudpickle-based; cannot selectively drop nested dict keys). Tested with a mocked `_v2_handle`: the direct path forwards `registry_proof` present + complete. Persistent and direct paths produce semantically equivalent forwarded payloads (test 10).

# Repair

`comfymodal_runtime/registry_proof.py` (deployed image code — redeploy required and performed):
- `_proof_stats`: accepts `classes` as list or tuple; `identities` as any `Mapping`.
- `evaluate_workflow_registry_parity`: accepts `Mapping` for `plan_proof` and `snapshot_manifest`; `manifest_classes` as any `Mapping`. Docstring documents the frozen-mapping contract.
- All fail-closed gates unchanged (missing host/snapshot class, identity mismatch, incomplete proof, empty class set → still ineligible). No Step-3 semantic changes. Transport code untouched (it was faithful).

# Regression tests

- `tests/test_step3_frozen_registry_parity.py` (9): frozen+frozen matches (THE root-cause regression — pre-fix `plan_registry_proof_unavailable`), mixed forms, tuple classes + mappingproxy identities, frozen missing-snapshot / identity-mismatch / incomplete / empty still fail closed, and the full `ExecutionPlan.from_dict` → gate round-trip (the exact production failure).
- `tests/test_persistent_handle_transport.py` (12): the 12 mandated scenarios over the REAL owner handler — persistent IPC preserves proof (41 classes), nested identity survives deep-equal, empty proof passes through, malformed fails explicitly, oversize fails explicitly, normal size << limit, future unknown fields survive (no shadow-schema reconstruction), direct path preserves proof, persistent≡direct, proof-less plan backward-compatible + fail-closed, future field survives transport + from_dict/to_dict.
- Full suite: 149 passed (9+12+23+15+21+12+27+8+22) + `test_waterfall_reconciliation.py` 23 passed — 0 failures.

# Redeploy required — YES (performed once)

The fix is in `registry_proof.py`, which is deployed image code. One fresh deployment/snapshot was performed (deploy 90.6 s — comfy-cli pin layers cached).

# Pre-generation transport proof / registry precheck

- Local full-flow replication: checkpoints A→E all `registry_proof present=True complete=True` (31-class dispatch proof; 41-class precheck set).
- Live precheck vs the fresh container manifest (2399 classes): **workflow classes 41 / host proved 41 / snapshot proved 41 / missing 0 / mismatches 0 / workflow_registry_match=1**.
- Stale persistent owner (PID 22844, spawned 11:30) killed + state cleared before the redeploy (fresh owner; the owner was exonerated as a pure passthrough, but the variable was removed).

# Validation/discard result (the single sanctioned generation)

Request `v2-benchmark-0-6378a8f18376` · role `validation_discard` · retained=0 · discard_reason=`first_post_snapshot_run` · provider/region GCP us-east1 (unpinned) · snapshot `im-8KexmbMytHCmXTxTMl6pl9|423ce11e7d2646c9b270e02955b04604`.

Container authoritative lines:

```
[v2.plan_proof.registry] workflow_class_count=31 host_proved_count=31 snapshot_proved_count=31
                         missing_host=0 missing_snapshot=0 identity_mismatch=0 workflow_registry_match=1 reason=
[v2.plan_proof] parity proof_present=1 proof_complete=1 proof_valid=1 dep_match=1 gen_match=1 wf_reg_match=1
                reg_full_match=0 dep_proof_match=1 eligible=1 reason=ok consumed=False
[v2.plan_proof] decision=plan_validation_fast_path consumed=1 workflow_hash_match=1 validation_hash_match=1
                plan_complete=1 snapshot_complete=1 snapshot_valid=1 dep_match=1 gen_match=1 wf_reg_match=1
                dependency_match=1 repair_changed=0 outputs_nonempty=1 eligible=1
certificate_read_outcome: cert_source=plan_validation cert_decision=plan_validation_fast_path hit=True preflight_skip=True consumed=True
```

(The first `[v2.plan_proof] … consumed=False cert_decision=legacy` line is the pre-gate instrumentation print whose `consumed=False` is a hardcoded placeholder; the authoritative decision line follows and shows consumed=1.)

- **Correct output: YES** — 1 output descriptor, 2 874 640 bytes, `sha256:895deda2…`.
- **plan_validation_consumed: 1** · **workflow_registry_match: 1** (31/31/31 in-container).

# Final Step-3 parity matrix

| Field | Value |
|---|---|
| plan_validation_payload present / validated / hash_match | 1 / 1 / 1 |
| snapshot_proof present / complete / valid | 1 / 1 / 1 |
| deployment_hash_match | 1 |
| custom_nodes_generation_match | 1 |
| dependency_proof_match | 1 |
| workflow_registry_match | 1 |
| registry_fingerprint_match | 0 (diagnostic-only, expected) |
| future_fast_path_eligible | 1 |
| repair_changed | 0 |
| **plan_validation_consumed** | **1** |

# RPC bypass counts

| Legacy step | Count | Evidence |
|---|---|---|
| certificate Volume RPC | **0** | `certificate_read_outcome` = fast-path emission only (hit=True, preflight_skip=True); `certificate_reload_start=0` |
| deployment-static preflight | **0** | `preflight_start=0`, `dependency_validation=0` |
| remote validate_prompt | **0** | no validate_prompt events; `validation_hash_match=1` from the carried proof |
| certificate writeback | **0** | `v2_certificate_write=0`, `_v2_schedule_cert_write` absent |

# Timing

- `certificate_ms / preflight_ms / validation_ms ≈ 0` (all bypassed; no legacy setup decomposition events fired).
- Graph setup: fast-path structural acceptance authoritative (`consumed=1`); `comfyui_path_setup_ms=0.12`; graph activity (execution) 4748.8 ms — the ~20–30 ms graph-setup target applies to the legacy decomposition which no longer runs on the fast path.

# Waterfall

- Final host-reconciled waterfall: `reconciliation_status=OK`, global residual **0.8795 ms** (tolerance OK).
- `TOTAL WALL` = 47 058.6 ms · `SCHEDULING` = 3 604.0 ms (informational; no % / no bar — unchanged) · `COMMAND→RESPONSE` = 50 662.6 ms.
- Remote artifact correctly labeled `REMOTE/PARTIAL WATERFALL (missing: missing_modal_restore_begin)`; host-side final authoritative.

# Remaining blockers

**None for Step-3.** All axes green; the legacy fallback remains available and unchanged for ineligible requests. The A/B framework, deployment-identity plumbing, generation parity, core pinning, Gate-2, and waterfall semantics are untouched.

# A/B campaign readiness

**READY.** Step-3 production acceptance is proven on a healthy fast path with zero legacy RPCs. The resumed A/B campaign can proceed from this deployment: validation/discard already accepted → baseline cohort → experiment arms (per the campaign protocol).

---

# STEP 3 PRODUCTION ACCEPTED
# A/B CAMPAIGN MAY RESUME
