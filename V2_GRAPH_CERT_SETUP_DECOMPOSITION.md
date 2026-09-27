# V2 Graph/Certificate Setup Decomposition — Snapshot-Restored Requests

Status: READ-ONLY / DESIGN-ONLY analysis, revision 2. No code modified, no deploy, no paid generations run.
Evidence base (all re-verified against the current checkout on 2026-08-11, concurrent edits possible):
- Code: `comfymodal_runtime/modal_app.py`, `comfyapp.py`, `canonical_execution.py`, `comfymodal_runtime/contracts.py`, `comfymodal_runtime/runtime_bootstrap.py`, `comfymodal_runtime/execution_seed.py`, `comfymodal_runtime/dependency_manifest.py`, parent ComfyUI `execution.py` + `comfy_execution/graph.py`.
- Measured artifact: `comfymodal-data\benchmarks\runs\v2_2026-08-12_03-04-09\run_0.json` — the exact run behind the cited 461/151/145/149 ms figures (values match to <1 ms).

---

# Corrected executive conclusion

**Original O1 is REJECTED.** The proposal to create/freeze a per-*workflow* validation certificate at snapshot creation is incompatible with the workflow-agnostic snapshot architecture (verified: `publish_restore_plan` is opt-in legacy, dead by default — `canonical_execution.py:1655-1699` skips with `flag_disabled`; `restore()` binds `self._restore_plan = None`, modal_app.py:8628; restore sets `source=startup_minimal, topology_available=0`, runtime_bootstrap.py:1819-1832). The snapshot must not know the future request workflow. Anything keyed by `workflow_hash` cannot be proven pre-freeze.

The corrected architecture splits the 460 ms window by **when proof first becomes knowable**:

- **Deployment-static proof** (knowable and provable *before freeze*, workflow-free): deployment combined hash, custom-nodes generation, dependency-manifest identity/health, registry/class state, repair mode. Verified: **every** current preflight/dependency check is deployment-static except two sub-millisecond workflow checks. The startup path **already builds and persists the manifest** (`source="snapshot_manifest"`, comfyapp.py:18361-18368) and freezes generation identity into `BootstrapState` (runtime_bootstrap.py:1259-1265) — the only missing pieces are freezing *that proof into snapshot memory* instead of re-reading Volume JSON per request, plus a registry fingerprint.
- **Workflow-static proof** (only knowable when `run_plan_stream(plan_payload)` arrives): the result of `execution.validate_prompt`. Verified: `validate_prompt`'s output is a **pure function of (workflow dict × node registry × model-folder listings × custom-node code)** — nothing request-specific, nothing keyed by `prompt_id` (parent `execution.py:1106`, third arg is a partial-execution filter, `extra_data` unused in validation). Its soundness is exactly what the cert identity already binds (`workflow_hash + deployment_hash + repair_mode + custom_nodes_generation`, modal_app.py:1364-1370). Therefore the validation result can ride **in `invocation_plan`** (computed host-side at plan build, where the same registry is live), trusted by the container under a re-derived binding: recomputed `prompt_sha256(plan.workflow) == plan.workflow_hash` **plus** plan-carried deployment identity == snapshot-frozen deployment proof. This is **stronger** than today's trust (today the container trusts `plan.workflow_hash` verbatim — no recompute anywhere in the v2 path).

**Verdicts:**
- **O1' (snapshot deployment proof):** feasible, workflow-free, removes the ~145 ms preflight Volume reads.
- **O2' (certificate Volume RPC removal):** the certificate abstraction is **unnecessary** in the corrected architecture — both of its jobs (carry validation result; gate preflight skip) are replaced. Remove it from the request path; do not re-cache it.
- **O3' (remote `validate_prompt` elimination):** safe under the exact trust condition below; ~149 ms container-side moves host-side once per workflow (cached, ~0 after).
- **O4' (writeback):** delete from the request path entirely; its only consumer (startup retention) never matches on the no-publish path anyway (`seed_missing`).
- **O5' (fallback):** unchanged semantics — deployment drift, stale proof, missing classes, repair, or malformed plan all degrade to today's full validation path or fail closed.

**Net:** graph_setup 460.5 ms → **~20-30 ms** on the fast path (verified sequential chain; span removals are additive in the leaf-sum model, see Expected savings for the host-side offset).

---

# Current call chain

Path for the measured run (v2, snapshot-restored): `run_plan_stream` (modal_app.py:14065) → `_run_in_process` (10011) → `_execute_v2_prompt_executor` (10996).

```
remote_method_entry (14604)
└─ _run_in_process
   ├─ runtime_configuration          (10022-10024)
   ├─ legacy_runtime_resolution      (10025-10027)
   ├─ graph_execution_start          (10034)  ← graph_setup span OPENS
   │  ├─ CPU-snapshot binding: derive_model_key / prefill key / restore spec (10114-10116, ~8.6 ms untimed gap)
   │  ├─ execution-prephase CLIP prefill scheduling (10489-10504)
   │  ├─ legacy_preload_check        (11017, 3.1 ms)  (no-op on no-publish path)
   │  ├─ input_materialization       (11021-11025)
   │  ├─ CERTIFICATE RESOLUTION      (11067-11397)
   │  │  ├─ identity build           (11148-11152, 0.03 ms)
   │  │  ├─ snapshot-memory gate     (11155-11218) → snapshot_cert_valid=False ⇒ snapshot_fallback
   │  │  ├─ process cache            (11226-11299) → miss
   │  │  └─ Volume read              (11301-11361, 150.7 ms): reload_async 147.8 + read 1.6 + parse 0.0
   │  ├─ dependency-preflight identity match (11399-11433)
   │  ├─ preflight                   (11437-11446 skip gate; 11447-11463 run, 145.1 ms) → _preflight_fn thread
   │  │                                → comfyapp _preflight_before_prompt_execution (10122): structure check 10137,
   │  │                                  combined hash 10163, baked manifest 10167, generation record 10173,
   │  │                                  manifest load 10180 (Volume JSON, never memoized), identity check 10185
   │  ├─ missing_node_repair         (11464-11483, 0.3 ms; always runs; Gate 2 11484-11532 invalidates cert on change)
   │  ├─ prompt validation           (11534-11578, 149.1 ms) → execution.validate_prompt (11555); skipped on cert hit
   │  │                                (skip sets valid=True/error={}, 11575-11578); cert write scheduled 11559-11574
   │  ├─ pregraph_setup              (11606-11709, 0.4 ms): production registry, executor.reset, seed hook
   │  ├─ execute_kwargs build        (11752-11757): {prompt, prompt_id, extra_data:{client_id}, execute_outputs}
   │  └─ prompt_executor_invoke_start (11989)  ← graph_setup span CLOSES
   └─ executor.execute_async         (12071-12076)
```

Post-request (after result path): `_write_v2_validation_certificate` (12788-12830) — `write_bytes` (1437) + awaited `commit.aio()` (1440-1448) — only when `_v2_schedule_cert_write and _v2_preflight_ran`.

Host side (outside the measured 460 ms): `build_execution_plan(..., validate=False)` (__init__.py:2448) → `ExecutionPlan.to_dict` → `modal_client.run_prompt_stream` → remote `ExecutionPlan.from_dict` (14360).

---

# Timing ownership

Source: `run_0.json` → `pre_sampler_stages`, `monotonic_ns` deltas. Sub-spans are **sequential inside the graph_setup window**; `reconciliation_status="ok"`, leaf-sum ≈ 460.5 ms = `graph_setup_ms`.

| Span | Start line | End line | Measured (ms) | Notes |
|---|---|---|---|---|
| graph_setup (parent) | 10034 | 11989 | **460.538** | = sum of children + ~13 ms gaps/residual |
| ├─ runtime_configuration | 10022 | 10024 | 0.049 | |
| ├─ legacy_runtime_resolution | 10025 | 10027 | 0.012 | |
| ├─ legacy_preload_check | 11017 | ~11040 | 3.085 | no-op on no-publish path |
| ├─ **certificate** | 11303 | 11361 | **150.744** | `cert_volume_reload_ms=147.79`, `cert_file_read_ms=1.627`, `cert_json_parse_validate_ms=0.0`, identity build 0.032 (outside span) |
| ├─ **preflight** | 11447 | 11463 | **145.078** | `legacy_preflight_ms=145.146`; `asyncio.to_thread` |
| ├─ missing_node_repair | 11464 | 11483 | 0.289 | always runs |
| ├─ **validation** | 11534 | 11578 | **149.071** | exactly `execution.validate_prompt` (11555) |
| ├─ pregraph_setup | 11606 | 11709 | 0.377 | `executor_reset` 0.064 nested |
| └─ residual_before_invoke | — | — | 1.843 | + un-emitted gaps ≈ 11 ms |
| restore (disjoint, before method) | comfyapp.py:20103 | 21862 | 1228.6 | `snapshot_restore_ms=1199.2`, `reload_runtime_state_ms=158.2` |
| pre_sampler_total | — | — | 7357.4 | dominated by CLIP encode 3087 ms + UNETLoader 3287 ms (loader/warmup — out of scope) |

**Overlap caveat:** the certificate/preflight/validation spans do not overlap each other, but the preflight and validation *wall intervals* contain concurrent background CLIP-prefill events (`execution_prefill_encode_start`, `clip_gpu_commit_*`, `clip_forward`) from other threads. Per the reconciliation model (`measured_children_ms=7315.688` vs `pre_sampler_total 7357.359`, `residual_ms=41.671`), those prefill events are accounted in their own spans, so removing a sequential span removes its wall time additively in the leaf-sum model (see Expected savings).

---

# Certificate invalidation root cause

(Unchanged from revision 1, now rendered moot by the corrected architecture.)

- Identity (`_compute_v2_cert_identity`, modal_app.py:1348-1378): SHA-256 of `cert_schema=2` + `workflow_hash` + `deployment_hash` + `repair_mode` + `custom_nodes_generation`. **No request-specific/stateful field.**
- `snapshot_cert_valid` defaults `False` (runtime_bootstrap.py:287), set `True` only by `set_snapshot_certificate` — via startup retention (modal_app.py:7465-7588) or post-request writeback (12770). On the no-publish path the startup retention reads `snapshot_seed.json` which has no workflow hash → `seed_missing` → status=fallback (7487-7488, 7571-7588) → `False` frozen into the CPU snapshot.
- Every restored container therefore logs `decision=snapshot_fallback reason=snapshot_cert_invalid` (11155-11218) and redundantly redoes Volume reload + preflight + `validate_prompt` + awaited writeback. The writeback only fixes in-container state; the frozen snapshot stays invalid.

In the corrected architecture the certificate mechanism is removed from the request path entirely, so the frozen flag and its root cause become irrelevant.

---

# Deployment-static vs workflow-static proof

For every current validation input/check: ownership, when it first becomes knowable, current cost.

| Check / input | Location (current) | First knowable | Workflow needed? | Cost today |
|---|---|---|---|---|
| Deployment combined hash | comfyapp.py:2026 `_CANONICAL_DEPLOYMENT_COMBINED_HASH` (in-memory constant, set by `_configure_runtime`; bootstrap constructor runtime_bootstrap.py:1153/1167) | **build/deploy** | No | 0 (µs) |
| Custom-nodes generation | `_read_custom_nodes_generation_record` (comfyapp.py:1540); frozen into `BootstrapState` by `observe_generations` (runtime_bootstrap.py:1259-1265) | **snapshot creation** | No | persisted read (Volume-backed file) per request |
| Baked manifest (image-local) | `load_baked_custom_node_dependency_manifest` (comfyapp.py:3922) | **build/deploy** | No | image-fs JSON open |
| Persistent dependency manifest | `_load_dependency_manifest` (2123-2149: `os.path.isfile`+`open`+`json.load` — **never memoized in memory**); `_check_dependency_manifest_identity` (2152) | **snapshot creation** (already built there: 18361-18368, `source="snapshot_manifest"`, commit=True) | No | **Volume JSON open per request (×2 call sites: 9975, 10180)** |
| Dependency validation + sentinels + fingerprint | `_run_dependency_validation_with_cache` (4315-4468); `_install_custom_node_requirements` (14739, runs at startup 18281-18300, fail-closed) | **snapshot creation** | No | ~0 on identity hit; ~900 ms full fingerprint miss |
| Requirements/repair mode | `_resolve_requirements_repair_mode` (env) | **build/deploy** | No | 0 |
| Registered node/class state | `nodes.init_extra_nodes()` (comfyapp.py:17978) + 2 manual classes (18009-18010), `_in_process_ready` (18018) | **snapshot creation** (post-import, pre-freeze) | No | — (no registry fingerprint exists today) |
| Custom-node sync | `_sync_custom_nodes_from_volume` (10665; memoized 10730) | **restore** (restore re-syncs: 20149; fast-path identity compare 1706-1795) | No | Volume reload per restore |
| Models generation baseline | `_read_models_generation_record` (restore: 20158) | **restore** | No | per restore |
| Prompt structure | `assert_valid_api_prompt_structure` (api_prompt_validator.py:41-135; called comfyapp.py:9947, 10137) | **request** (plan payload) | **Yes** | sub-ms O(nodes) pure Python |
| Class usage vs registry | `_enforce_workflow_node_classes_available_before_model_work` (15627) / `_find_missing_workflow_node_classes` (15587); v2 repair walk (11464) | **request** | **Yes** (registry itself deployment-static) | ~0.3 ms |
| `validate_prompt` result (outputs_to_execute, node_errors, all type/cycle/input invariants) | parent `execution.py:1106` (v2 call at 11555) | **request** (plan build host-side, or container) | **Yes** | 149.1 ms container-side |
| Input images / sampler inputs / preload timing | `_materialize_input_images` (11021-11025); preload wait | **request** | **Yes** (request-specific) | outside spans / 3.1 ms no-op |
| Workflow hash (`prompt_sha256` = canonical sorted-key JSON SHA-256 over the **entire workflow incl. inputs**, workflow_metadata.py:45-52 → production_workflow.py:31-42) | host: canonical_execution.py:920; container: **trusted verbatim, never recomputed** | **request** (host) | **Yes** | sub-ms to recompute |

**Key conclusions:**
- Everything in the ~145 ms preflight span except the sub-ms structure check is **deployment-static and provable pre-freeze**; the only reason it costs 145 ms per request is that `_load_dependency_manifest` + generation reads are Volume/file-backed and **never memoized in memory**, and v2 never sets `_preflight_already_ran` (comfyapp.py:22055-22066 is v1-only).
- restore() re-establishes deployment freshness **per restore** (cn sync 20149, generation 20158, `runtime_config_vol.reload` 20180) but never re-reads the manifest — the first request always pays the Volume reads.
- The container's registry is frozen by the CPU snapshot; `restore()` only mutates it if cn sync detects a changed generation (1773-1790) — that event is the natural "proof stale" trigger.

---

# What invocation_plan already proves

`ExecutionPlan` (contracts.py:615-676), built host-side per request (canonical_execution.py:879-984), deserialized container-side (modal_app.py:14360). Verified current fields:

| Field | Provenance | Proves |
|---|---|---|
| `workflow` (frozen Mapping) | deepcopy of compiled/source graph (897-918) | full graph content: class_types, inputs, connections, `_meta` |
| `workflow_hash` | `prompt_sha256(dispatch_workflow)` (920) | exact byte-identity of graph incl. all inputs (canonical sorted-key JSON SHA-256) |
| `source_workflow_hash` | report/source hash (968) | pre-compile identity |
| `production_report` | `compile_production_workflow` report (production_workflow.py:654-688) | compiled/source/topology/plan hashes, `output_node_ids`, bypass/rewritten node lists, selected output classes, cache_hit |
| `model_stack` | `extract_model_stack` (931) | model files referenced |
| `prompt_bundle` | `extract_safe_prompt_bundle` (933-937) | prompt scalars |
| `output_node_ids` | report or options (950) | requested output set |
| `input_images` | `_collect_input_images` (928-929) | input image refs |
| `execution_options` | `from_legacy` (945-949) | runtime options |
| `request_metadata` | (952-965) | prompt_id, client_id, selected_gpu, workspace_id |

**What it does NOT prove today:** validation results (`outputs_to_execute`, `node_errors`), `used_classes`, or deployment identity (no `deployment_hash`/`custom_nodes_generation` — that lives in `DeploymentIdentity` contracts.py:969-1000, `SnapshotExecutionSeed` contracts.py:894-895, and container module global `_V2_DEPLOYMENT_COMBINED_HASH`). The v2 path calls `build_execution_plan(..., validate=False)` (__init__.py:2448) — even the structure/class checks are skipped host-side.

---

# What validate_prompt uniquely proves

Real signature (parent repo): `async def validate_prompt(prompt_id, prompt, partial_execution_list)` — third arg is a partial-execution filter (modal passes `None`), `extra_data` unused in validation. Returns `(valid, error, outputs_to_execute, node_errors)`. `outputs_to_execute` is a **flat list of output-node ID strings** (execution.py:1180-1223) — the transitive closure is built at execution time by `ExecutionList.add_node` (comfy_execution/graph.py:138-166), so the plan's `output_node_ids` is not a substitute for it.

Invariants verified (execution.py:1106-1225, `validate_inputs` 824-1106):

| # | Invariant | Depends on | Covered elsewhere today? |
|---|---|---|---|
| a1 | every node has `class_type` | workflow | structure check (host, if validate=True) |
| a2 | `class_type ∈ NODE_CLASS_MAPPINGS` | registry | `_validate_class_types` / repair walk (0.3 ms, always runs) |
| a3 | OUTPUT_NODE collection | registry | not covered (a3+a4 only in validate_prompt) |
| a4 | non-empty outputs (`prompt_no_outputs`) | workflow+registry | not covered |
| b1 | `INPUT_TYPES()` callable per node | registry + **FS folder scans** (loader combos) | not covered |
| b2 | required inputs present | workflow | not covered (combo/dict shape only) |
| b3 | linked input is `[node_id, slot]` | workflow | not covered |
| b4 | return-type linkage across edges | workflow+registry | not covered |
| b5 | scalar coercion (**mutates workflow dict**, 966-981) | workflow | not covered — **run before hashing** |
| b6 | min/max bounds | workflow + INPUT_TYPES | not covered |
| b7 | combo membership (`value_not_in_list`) | workflow + **FS** | not covered |
| b8 | `VALIDATE_INPUTS` callback (arbitrary node code) | node code (FS/network possible) | not covered |
| c | cycle detection (DFS) | workflow | not covered |
| d | recursive closure walk (memoized) | workflow | not covered |
| e | `node_errors` dict | workflow | not covered |

**Dependency classification:** everything depends only on (workflow dict) × (registry) × (model-folder listings) × (custom-node code). Nothing is keyed by `prompt_id` or container state (no validation cache in the parent repo; `prompt_id` only feeds telemetry contextvars). **A different process with the same workflow, same registry, same model folders, and same custom-node code computes an identical result** — this is exactly the class of equivalence the cert identity already asserts (`workflow_hash` + `deployment_hash` + `custom_nodes_generation`).

**Why a cert hit is allowed to skip `validate_prompt` (the trace):** on any hit (snapshot-memory 11197-11201 / process cache 11276-11279 / Volume 11324-11327) the payload's `outputs_to_execute` + `node_errors` are loaded and the call is guarded `if not _v2_cert_preflight_skip` (11553-11557), with the skip branch setting `valid=True, error={}` (11575-11578); `execute_outputs` is injected via `execute_kwargs` (11752-11757) into `executor.execute_async` (12071-12076). `node_errors` is never passed to the executor — it only feeds the validity decision. Trust rests on identity equality: the cert file requires exact `identity` and per-component `identity_components` equality (1494-1508) plus `preflight_ok=True` and non-empty `outputs_to_execute` (1511-1520). **The cert is a memo of a pure function, keyed by its inputs.**

**Can the same trusted result come directly from invocation_plan?** Yes, if the container re-derives the same binding instead of reading a Volume memo:
1. **Workflow binding** — recompute `prompt_sha256(plan.workflow)` container-side (sub-ms for a ~13-node graph) and assert `== plan.workflow_hash`. Today the container trusts `workflow_hash` verbatim (verified: no recompute anywhere in the v2 path) — this assertion is *stronger* than current behavior and is what makes plan-carried validation sound (the executed graph is exactly the validated graph).
2. **Deployment binding** — plan carries deployment identity (deployment combined hash + custom-nodes generation as seen by host); container asserts equality with snapshot-frozen proof (O1'). Same trust level as cert identity components.
3. **Registry binding** — snapshot-frozen registry fingerprint (O1') + the always-running missing-node repair walk (11464, 0.3 ms) with Gate 2 invalidation (11484-11532) preserved.

**Residual gap (documented, not silent):** b1/b7/b8 are FS-dependent (loader combos list model folders; `VALIDATE_INPUTS` is arbitrary code). The cert today binds FS only *implicitly* (same-deploy containers share folders). Host-side validation assumes host model folders == deploy folders — same implicit level, now explicit: guard via plan `model_stack` (already carried) against the deployment's ensured models (ensure_models runs at restore). If a combo value exists container-side but not host-side, host validation still *accepts* it only if the value is in the host's list; a mismatch surfaces as a runtime hard failure (NodeNotFound/KeyError, per execution.py:69, graph.py:276) — never silent (empty `execute_outputs` would be the one silent case; the non-empty requirement from the cert path (1511-1520) is carried over as a hard precondition).

---

# Corrected optimization architecture

```text
SNAPSHOT CREATION (startup(), workflow-agnostic, pre-freeze)
  → deployment combined hash            (already in-memory constant)
  → custom-nodes generation             (already frozen by observe_generations)
  → dependency manifest build + identity (already runs, source="snapshot_manifest")
  → dependency validation fail-closed    (already runs for off/fail_fast)
  → registry fingerprint (NEW, post-init_extra_nodes)
  → repair mode                          (env)
  → FREEZE deployment proof dict into BootstrapState (snapshot memory)

REQUEST (restored container)
  → restore() re-establishes cn/generation freshness (existing fast path);
    if it re-synced ⇒ mark proof stale
  → run_plan_stream(plan_payload)        (only place workflow becomes known)
  → plan deserialize + schema validation (ExecutionPlan.from_dict)
  → recompute prompt_sha256(plan.workflow) == plan.workflow_hash   (NEW, sub-ms)
  → assert plan.deployment_identity == frozen proof                (in-memory, µs)
  → trust plan.validation payload (outputs_to_execute, node_errors)
  → structure check + missing-node repair + Gate 2 (unchanged, ~0.3-1 ms)
  → NO certificate Volume reload/read/write/commit
  → NO manifest/generation/baked Volume reads
  → executor.execute_async(execute_outputs=plan.validation.outputs_to_execute)
  → fallback: any proof/validation failure ⇒ today's full preflight+validate_prompt path

PROOFS
  deployment-static  → frozen in snapshot, verified per request in-memory
  workflow-static    → rides in invocation_plan, bound by hash + deployment identity
  request-specific   → input images, sampler inputs, preload timing (untouched)
```

Constraints honored: no workflow publication before generation; no second remote RPC (plan payload grows, transport unchanged); no snapshot-workflow coupling (proof is deployment-only); arbitrary post-restore workflows supported; `publish_restore_plan` stays dead.

---

# O1' Deployment proof

**Retained in the snapshot (frozen in `BootstrapState`, zero Volume access after restore):**

| Field | Computed at | Source today |
|---|---|---|
| `deployment_combined_hash` | build/deploy | comfyapp.py:2026 constant; bootstrap ctor 1153/1167 |
| `custom_nodes_generation` | snapshot creation | observe_generations freeze (runtime_bootstrap.py:1259-1265; `snapshot_custom_node_generation`) |
| `dependency_manifest_identity` | snapshot creation (new field) | result of `_build_and_persist_dependency_manifest` (18361-18368) — already computed at startup, currently only persisted to Volume |
| `dependency_validated` | snapshot creation | startup `_install_custom_node_requirements` fail-closed outcome (18281-18300) |
| `registry_fingerprint` | snapshot creation (new) | SHA-256 over sorted `(name, module, qualname)` of `NODE_CLASS_MAPPINGS`, computed after `nodes.init_extra_nodes()` (comfyapp.py:17978) + manual registrations (18009-18010) + `_in_process_ready` (18018); template: `_build_validation_certificate_identity` class encoding (2571-2603) |
| `repair_mode` | build/deploy | env resolution |

**Request-time consumption (all in-memory, µs):**
- Preflight span reduces to: structure check (sub-ms, workflow-dependent — keep) + registry walk (0.3 ms, already exists as repair) → **preflight ≈ 1-2 ms** instead of 145 ms.
- The manifest/generation/baked reads (9975, 10180, 10173) and identity checks are skipped entirely while proof is valid — no memoization hack needed; the proof replaces the reads.
- `restore()` already re-establishes freshness (cn sync fast path compares schema/generation/deployment-hash, 1706-1795): if it **re-syncs** (generation changed), set `proof.stale=True` → requests take the fallback path. If it fast-path-skips, proof remains valid. This gives deployment-drift invalidation without per-request Volume RPCs.

**Expected savings:** ~143 of the 145.1 ms preflight span.

**Risk:** low — startup already performs every one of these operations today (verified); the change is freezing their results into memory and gating request-time re-reads. The only new computation is the registry fingerprint (sub-ms, once per snapshot).

---

# O2' Certificate Volume RPC removal

**Can it be removed? Yes — entirely.** The certificate abstraction has exactly two jobs:

1. **Carry validation results** (outputs_to_execute, node_errors) across containers → replaced by plan-carried validation (O3').
2. **Gate preflight skip** (`preflight_certificate_skip`, 11437-11446) → replaced by snapshot deployment proof (O1').

With both replaced, the Volume cert read/write/commit, the process cache (11226-11299), the snapshot-memory cert gate (11155-11218), and identity construction (11148-11152) prove nothing additional: the plan is already bound to the graph by hash and to the deployment by identity — the Volume file adds a redundant third copy that costs 150.7 ms (147.8 ms of pure `reload_async`).

**Correctness guards for removal:**
- Plan-carried validation is trusted only when: (a) deployment proof valid (frozen + not stale), (b) `prompt_sha256(plan.workflow) == plan.workflow_hash`, (c) plan deployment identity == frozen proof, (d) `outputs_to_execute` non-empty (hard precondition, same as cert path 1511-1520).
- Failure of any guard → fallback path (full remote validate + preflight), never silent.
- Gate 2 / missing-node repair semantics unchanged (11484-11532).
- The cert subsystem code stays dormant behind `COMFYMODAL_V2_VALIDATION_CERT` (default flips to off) for rollback; no code deletion required in the first implementation step.

**Expected savings:** the full 150.7 ms certificate span (including the ~1.6 ms file read and the ~0.03 ms identity build).

---

# O3' validate_prompt elimination/narrowing

**Exact safe condition to skip remote `validate_prompt`:**

```text
skip_remote_validate := (
    snapshot_deployment_proof.valid
    AND plan.validation.validated == True
    AND plan.validation.validated_workflow_hash == plan.workflow_hash
    AND recompute(prompt_sha256(plan.workflow)) == plan.workflow_hash     # container-side, sub-ms
    AND plan.deployment_identity == snapshot_deployment_proof.identity    # hash + generation
    AND len(plan.validation.outputs_to_execute) > 0
    AND NOT missing_node_repair_changed(workflow)                          # Gate 2, always evaluated
)
```

**Missing proofs to add (smallest set):**
1. `invocation_plan.validation` — new ExecutionPlan field: `{validated: bool, outputs_to_execute: list[str], node_errors: dict, validated_workflow_hash: str, validation_schema: int}` (contracts.py:615-676).
2. `invocation_plan.deployment_identity` — new field: `{deployment_combined_hash: str, custom_nodes_generation: str}` as observed host-side (host already has both: canonical_execution.py:1381 reads `COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH`; generation is deploy-managed).
3. Container-side hash recompute + assert (does not exist today — the container trusts `plan.workflow_hash` verbatim; this is a *strengthening*).
4. Non-empty outputs precondition (mirrors cert path).

**Host-side computation:** call `execution.validate_prompt(prompt_id, dispatch_workflow, None)` inside `build_execution_plan` **before** `prompt_sha256` (b5 coercion mutates the workflow dict — validation-then-hash ordering is mandatory to keep `plan.workflow`/`workflow_hash` consistent). The `execution` module is importable in the local ComfyUI process (`_validate_class_types` already imports `nodes`; async-shim pattern exists at __init__.py:2641-2649). `ComfyModalProductionOutput` (the production output class) is this repo's own class, so validating the production-compiled `dispatch_workflow` host-side is valid. Cost: ≈149 ms once per workflow_hash, then host-side memoization (in-memory LRU keyed by `workflow_hash` — the workflow-static cache the current architecture lacks) → ~0 for repeated identical requests.

**Expected savings:** 149.1 ms container-side; +149 ms host-side once per workflow (amortized to ~0). Validation strength is unchanged (same function, same registry, same graph) — nothing is weakened; the trust boundary (deployment identity) is the same one the cert already used.

---

# O4' Certificate writeback

**Remove it from the request path entirely.** Verified current behavior: post-execution `_write_v2_validation_certificate` (12788-12830) with awaited `commit.aio()` (1440-1448), gated `_v2_schedule_cert_write and _v2_preflight_ran`.

- Its only consumer is the startup retention read (7465-7588), which on the no-publish path finds no seed workflow hash → `seed_missing` → the cert is **never consumed by anything** in the workflow-agnostic architecture. It exists purely to serve a mechanism (snapshot workflow cert) that the corrected design abolishes.
- Cross-container reuse is moot: containers are single-use; the plan-carried validation (O3') replaces cross-container validation reuse.
- Keep the code dormant behind `COMFYMODAL_V2_VALIDATION_CERT=0` for rollback; no deferred/debounced variant is justified — there is no consumer to serve. (This also removes the awaited Volume commit from the request tail, an untimed tens-of-ms-class latency plus Volume IO contention.)

---

# Failure and invalidation model

Every abnormal case must still fail correctly. Mapping with the corrected architecture:

| Failure | Detection | Behavior |
|---|---|---|
| Deployment mismatch (request targets a different deploy) | `plan.deployment_identity.deployment_combined_hash != frozen proof` | fallback: full remote preflight + validate_prompt (today's path); if mismatch persists after validation, fail closed |
| Custom-nodes generation mismatch | (a) restore fast-path compare (1706-1795) → re-sync → `proof.stale=True`; (b) plan generation vs frozen | stale proof ⇒ fallback path (which includes today's cn-sync/manifest checks); never trust plan validation on stale proof |
| Missing classes | missing-node repair walk (11464, always runs) | existing repair semantics (dev-mode pip install only); Gate 2 (11484-11532) invalidates plan validation when availability changed ⇒ remote validate re-runs |
| Dependency failure | frozen `dependency_validated=False` (startup would have raised, 18293-18300) or proof stale | fail closed before execution |
| Repair changing the graph | Gate 2 (`missing_before` behind skip) | plan validation discarded ⇒ remote validate re-runs (unchanged semantics) |
| Malformed/tampered invocation plan | `ExecutionPlan.from_dict` schema validation (14360) + container-side `prompt_sha256(plan.workflow) != plan.workflow_hash` | reject/fail the request before any trust decision |
| Workflow identity mismatch | hash assert mismatch (above) | same — reject or fallback, never execute with unverified binding |
| Empty/absent validation payload | `plan.validation.validated` false or `outputs_to_execute` empty | fallback to remote validate; **never execute with empty `execute_outputs`** (parent executor would emit `execution_success` with zero work, execution.py:793-805) |
| Invalid graph slipping past plan validation | runtime hard failure (NodeNotFound/KeyError, execution.py:69 / graph.py:276) | request errors loudly — same backstop as a cert miss today |

Honest boundary: the container executes client-supplied workflows; the hash assert enforces *consistency between the executed graph and the validated result* (integrity of binding), not client intent — identical threat model to today, where the client supplies the workflow and the cert merely memoizes validation.

---

# Expected savings

Baseline (measured): certificate ≈150.7 ms, preflight ≈145.1 ms, validation ≈149.1 ms, mechanical ≈15 ms, graph_setup ≈460.5 ms.

Corrected fast-path call chain (verified sequential; span removals are additive in the leaf-sum model — `reconciliation_status="ok"`; background prefill events are accounted in their own spans and are unchanged in total):

```
deserialize plan + schema          ~5-10 ms   (already in the 8.6 ms gap today)
runtime_configuration              0.05 ms
legacy_runtime_resolution          0.01 ms
preload check (no-op)              3.1 ms
hash recompute + assert            ~1-5 ms    (NEW; sub-ms for 13-node graph + overhead)
deployment proof asserts           <0.1 ms    (NEW; in-memory)
structure check                    ~1 ms
missing-node repair + Gate 2       0.3 ms
pregraph_setup / executor reset    0.4 ms
residual/gaps                     ~11 ms
─────────────────────────────────────────────
graph_setup (fast path)           ~20-30 ms
```

| Span | Baseline | Fast path | Delta |
|---|---|---|---|
| certificate | 150.7 | 0 | −150.7 (pure synchronous Volume RPC; fully removed, additive) |
| preflight | 145.1 | ~1-2 | −143 (Volume JSON reads replaced by frozen proof; wall span removed, interleaved prefill events unchanged in total) |
| validation | 149.1 | 0 | −149.1 container-side; **offset host-side by ≈+149 ms on the first submission per workflow_hash, ~0 thereafter (host cache)** |
| mechanical | ~15 | ~15 | 0 |
| **graph_setup** | **460.5** | **~20-30** | **−430-440** |

End-to-end accounting (honest, not blindly additive): first identical workflow after deploy ≈ −290 ms net (container −440, host +150 once); every subsequent identical request ≈ −440 ms. Savings are additive within the container because the spans form a strictly sequential chain and the reconciliation model attributes background prefill separately.

---

# Exact implementation plan

Smallest change set for a later implementation agent (in dependency order, each independently shippable):

**Step 1 — Plan-carried validation payload (local-only, no runtime behavior change):**
- `comfymodal_runtime/contracts.py:615-676`: add `validation: Mapping` (schema: `{validated, outputs_to_execute: list[str], node_errors: dict, validated_workflow_hash, validation_schema}`) and `deployment_identity: Mapping` (`{deployment_combined_hash, custom_nodes_generation}`) to `ExecutionPlan`.
- `canonical_execution.py` `build_execution_plan` (879-984): when enabled (v2 path), run `await/run(execution.validate_prompt(prompt_id, dispatch_workflow, None))` via the async shim pattern (__init__.py:2641-2649) **before** `prompt_sha256` (coercion mutation ordering); store result + host-observed deployment identity in the new fields; keep `validate=False` default semantics untouched.
- `__init__.py:2448`: wire the v2 path to collect the payload.
- No container change yet; plan payload is inert.

**Step 2 — Snapshot deployment proof (O1'):**
- `comfymodal_runtime/runtime_bootstrap.py`: extend `BootstrapState` (286-307) with `snapshot_deployment_proof` (dict: deployment_combined_hash, custom_nodes_generation, dependency_manifest_identity, dependency_validated, registry_fingerprint, repair_mode, source, stale=False).
- Compute registry fingerprint after `nodes.init_extra_nodes()` (comfyapp.py:17978) + manual classes (18009-18010), i.e. at `_in_process_ready` (18018) — SHA-256 over sorted `(name, module, qualname)` (template: 2571-2603).
- Freeze manifest identity from `_build_and_persist_dependency_manifest` result (18361-18368); freeze dependency-validated from startup policy outcome (18281-18300).
- `restore()` (runtime_bootstrap.py:1530-1883, cn fast path 1706-1795): set `stale=True` when re-sync actually ran.

**Step 3 — Container trust gate + cert removal (O2'/O3'/O4'):**
- `comfymodal_runtime/modal_app.py` `_execute_v2_prompt_executor` (10996): replace the cert block (11067-11397) with the fast-path gate from the O3' section; add container-side `prompt_sha256` recompute + assert; skip preflight Volume path (keep structure check + repair + Gate 2); fallback branch calls the existing preflight + `validate_prompt` (11534-11578) unchanged.
- Remove request-path cert Volume read/write/commit (11301-11361, 12788-12830) behind `COMFYMODAL_V2_VALIDATION_CERT` (default off, code dormant for rollback); delete process cache (11226-11299) and snapshot-memory cert gate from the active path.
- `v2_waterfall.py` (677-685): unchanged (spans still emitted; certificate span measures ~0).

**Tests:** extend `tests/` (test_comfyapp_volume_lifecycle.py, test_dependency_manifest_wiring.py, test_dependency_manifest_lifecycle.py) with the verification-plan cases below.

Do not touch: Active Profile, CLIP↔UNET overlap, conditioning cache, output persistence, sampling, loader/snapshot architecture, `publish_restore_plan` legacy code.

---

# Verification plan

Prefer unit/local verification; at most one paid correctness run after implementation.

1. **Unit (local, no Modal):**
   - Plan round-trip: build plan with Step-1 payload → `to_dict`/`from_dict` preserves `validation` + `deployment_identity` byte-exactly.
   - Hash-equality: container-side `_canonical_workflow_hash(plan.workflow)` == `plan.workflow_hash` for (a) a raw workflow, (b) a production-compiled `dispatch_workflow`, (c) workflow with coercion-mutated inputs (validated-then-hashed ordering).
   - Proof logic: frozen-proof-valid/stale transitions; plan-deployment-identity compare; non-empty outputs precondition.
   - Fallback: stale proof or identity mismatch ⇒ existing preflight + `validate_prompt` run (existing test coverage re-verified); Gate 2 still invalidates plan validation when repair changes availability (11484-11532 semantics).
   - Malformed plan: hash-assert mismatch ⇒ reject; empty `outputs_to_execute` ⇒ never reach `execute_async` (guard against the silent zero-work executor path, execution.py:793-805).
2. **One paid correctness run (after implementation):**
   - Same benchmark workflow (`benchmark_modal_e2e.py` / `benchmark_modal.py`): assert `graph_setup_ms ≈ 20-30`, `certificate_ms ≈ 0`, `preflight_ms ≈ 1-2`, `validation_ms ≈ 0`, `reconciliation_status="ok"`, and **output images identical to the pre-change baseline** (image diff, not just exit code).
   - Adversarial case: a workflow with a missing node class and a tampered hash → still fails cleanly (no silent success, no wrong outputs).
   - Confirm no `[v2.cert]` Volume RPCs on the fast path in container logs.

---

# Recommended next action

**Step 1 — plan-carried validation proof — is now IMPLEMENTED and verified** (see the Step-1 sections below). The next single step is **Step 2 — snapshot deployment proof (O1')**: freeze `{deployment_combined_hash, custom_nodes_generation, dependency_manifest_identity, dependency_validated, registry_fingerprint, repair_mode}` into `BootstrapState` at snapshot creation, mark `stale` at restore when the cn fast-path re-syncs, per the O1' section. It is workflow-agnostic, needs no Modal run to unit-test (proof transitions + fingerprint helper), and unlocks Step 3 (container trust gate + cert removal).

---

# Step 1 implementation

Status: **IMPLEMENTED** (working tree, branch `TESTING2`). Behaviorally inert: the payload is carried and instrumented only — nothing consumes it; no container-side decision changed. No commits made by this task (a concurrent agent's commit `eea1b3c` absorbed `canonical_execution.py` into HEAD; working tree == HEAD for that file).

---

# New ExecutionPlan fields

| Field | Type | Keys | Notes |
|---|---|---|---|
| `ExecutionPlan.validation` | frozen `Mapping[str, Any]` | `schema_version: int` (= `VALIDATION_PROOF_SCHEMA_VERSION` = 1), `validated: bool`, `outputs_to_execute: list[str]` (sorted, deterministic), `node_errors: dict`, `validated_workflow_hash: str` (== `plan.workflow_hash`), `source: str` (`"host_validate_prompt"`) | absent → `{}` (backward compatible) |
| `ExecutionPlan.deployment_identity` | frozen `Mapping[str, Any]` | `schema_version: int`, `deployment_combined_hash: str`, `custom_nodes_generation: str`, `registry_fingerprint: str`, `complete: bool` (all three non-empty) | `""` = unknown → `complete=False` → future gate ineligible; never fabricated |

- `VALIDATION_PROOF_SCHEMA_VERSION = 1` (contracts.py:618); fields frozen in `__post_init__` (672-673), round-tripped in `from_dict` (699-700) / `to_dict` (716-717).
- Shared helper `compute_registry_fingerprint(class_mappings=None)` (contracts.py:621-647): deterministic SHA-256 over sorted `(name, module.qualname)` of `NODE_CLASS_MAPPINGS`; `""` when the registry is unavailable/empty — ineligible, never fabricated.

---

# Validation provenance

- Host-side `_collect_plan_validation_proof` (canonical_execution.py:879-920) invokes the parent-ComfyUI authoritative `execution.validate_prompt(prompt_id, dispatch_workflow, None)` — the exact validation the container would run — **fail-closed** (`RuntimeError` on invalid or raising).
- **Ordering (critical):** validation runs after dispatch-workflow finalization (production compile/report reuse) and **before** `prompt_sha256` (canonical_execution.py:988-997), because `validate_prompt` coerces scalar inputs **in place** (parent execution.py:966-981). The hash therefore covers the exact dict object frozen into `plan.workflow`, so the container's `prompt_sha256(_thaw(plan.workflow))` reproduces `plan.workflow_hash`.
- Enabled only at the v2 dispatch call site (`__init__.py:2449`, `collect_validation_proof=True`); default `False` — all other callers (v2_experiment_invoker, playground, tests) unchanged.
- Async: in a running-loop context (v2 dispatch runs on the ComfyUI event loop) the coroutine is driven on a fresh-loop worker thread — `run_coroutine_threadsafe(...).result()` from inside that loop deadlocks (verified experimentally); no-loop context uses `asyncio.run`.
- Travels only inside `plan_payload`: no Volume write, no second RPC, `publish_restore_plan` untouched and default-off (verified: `publish_restore_plan_enabled()` False with env unset).

---

# Canonical workflow hash binding

- Single shared canonical representation confirmed: `prompt_sha256` (workflow_metadata.py:45-52) → `production_workflow._canonical_workflow_hash` (production_workflow.py:31-42) — canonical sorted-key JSON (`sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False`) + SHA-256 over the **entire workflow incl. inputs**. Host and container hash identically; nothing else hashes the workflow on the plan path (`stable_hash` is for identity dicts; the comfyapp MD5 `_compute_workflow_struct_hash` is trace-only and intentionally different).
- Step 1 adds the binding: `validation.validated_workflow_hash == plan.workflow_hash`, plus container-side instrumentation recompute `prompt_sha256(_thaw(plan.workflow))` with a `match` flag (modal_app.py:11068-11073) — proving today that the future gate's `recompute_hash(plan.workflow) == plan.workflow_hash` equality holds, without gating on it.
- Implementation note: `json.dumps` cannot serialize frozen `MappingProxyType` — recompute must hash `_thaw(plan.workflow)` (plain dict), which is the exact to_dict/from_dict round-trip representation (unit-tested).

---

# Deployment/registry bindings

- **`_CANONICAL_DEPLOYMENT_COMBINED_HASH` (comfyapp.py:2022-2059) — VERIFIED POPULATED in production.** `modal_app._configure_runtime()` (modal_app.py:7047-7056, called at startup 7394; production path is never bootstrap-injected) assigns `_V2_DEPLOYMENT_COMBINED_HASH`, which is never literally `""` (the `stable_hash` wrap at modal_app.py:15722-15725). Absent only in standalone imports / bootstrap-injected test paths, where the legacy fallback can return `""`.
- **Caveat:** if `build_modal_resources()` raised at import (`source_identity=None`), the wrap degrades to a hash over `runtime_shape` only — non-empty but semantically weak. Confirm `_MODAL_RESOURCES["source_identity"]` is non-None in the deployed image before Step 3.
- Host-side capture at plan build (`_collect_plan_deployment_identity`, canonical_execution.py:923-943): `deployment_combined_hash` from `request_metadata["deployment_combined_hash"]` or env `COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH`; `custom_nodes_generation` from `request_metadata["custom_node_generation"]` — **nothing populates these today, so `complete=False`** → future fast path correctly ineligible until Step 2 populates them.
- `registry_fingerprint` is the host's view of `NODE_CLASS_MAPPINGS`; if the host registry includes local-only nodes, the future gate fails safe (never trusts mismatched registries).
- Container-side already knows its deployment identity (`_V2_DEPLOYMENT_COMBINED_HASH` + frozen generation) — Step 2 freezes the comparable snapshot-side proof.

---

# Residual remote-only checks

- **b7 combo membership (`value_not_in_list`) and b8 `VALIDATE_INPUTS` callbacks** depend on model-folder listings and arbitrary node code (parent execution.py:1025-1088). Host-side validation can reject a workflow that would be valid container-side if folders differ (and vice versa — runtime hard failure backstop, never silent).
- Step 1 does **not** weaken these: the container's remote `execution.validate_prompt` path remains fully authoritative and unchanged; the payload is never trusted remotely.
- The empty-`execute_outputs` silent-success hazard (parent execution.py:793-805) remains handled by the current container path; the Step-3 gate must carry over the non-empty precondition.

---

# Changed files

| File | Change | Lines (current) |
|---|---|---|
| `comfymodal_runtime/contracts.py` | constant, fingerprint helper, two fields, freeze, from_dict, to_dict | 618, 621-647, 662-663, 672-673, 699-700, 716-717 |
| `canonical_execution.py` | `_collect_plan_validation_proof`, `_collect_plan_deployment_identity`, `collect_validation_proof` param, validation-before-hash, plan wiring + host print | 879-920, 923-943, 961, 988-997, 1045-1066 |
| `__init__.py` | `collect_validation_proof=True` at the v2 call site (only edit) | 2449 |
| `comfymodal_runtime/modal_app.py` | instrumentation block only: `[v2.plan_proof]` print + `trace.emit("plan_validation_payload", consumed=False)` | 11060-11090 |
| `tests/test_plan_validation_proof.py` | NEW — 12 unittest tests | 1-330 |

---

# Local verification

- `python run_tests.py tests.test_plan_validation_proof` → **Ran 12 tests / OK** (round-trip intact, determinism, workflow-change changes hash binding, validation-output change changes serialized identity, container recompute == plan hash, missing deployment identity → `complete=False`, full identity → `complete=True`, fingerprint determinism, backward compat `{}` defaults, `publish_restore_plan` default off).
- `python run_tests.py tests.test_runtime_contracts tests.test_canonical_execution` → **Ran 63 tests / OK**.
- `python -m pytest tests/test_env_flags.py -q` → **1378 passed**.
- `test_local_submission_critical_path` (9 C8 runtime-shape errors) and `test_production_workflow` (8 comfyapp env-default failures): **pre-existing** — reproduced identically with these changes stashed; not attributable to Step 1.
- No paid runs; no commits.

---

# Runtime behavior unchanged

- Container certificate lookup, preflight, the `execution.validate_prompt` call site, certificate writeback, Gate 2, and missing-node repair: **untouched** (verified by diff review).
- Payload never consumed (`consumed=False`, `cert_decision=legacy`); the `[v2.plan_proof]` line and `plan_validation_payload` trace event are diagnostics only.
- Host-side delta only: v2 plan build now runs the authoritative `validate_prompt` (fail-closed for invalid workflows — invalid requests still fail, now earlier and locally) and emits one `[v2.plan_proof]` line.
- Old plans without the new fields still deserialize (`validation == {}`, `deployment_identity == {}`).

---

# Step 2 prerequisites

1. Freeze the snapshot-side deployment proof in `BootstrapState` (deployment_combined_hash, custom_nodes_generation, dependency_manifest_identity, dependency_validated, registry_fingerprint computed after `nodes.init_extra_nodes()`/manual classes, repair_mode); set `stale=True` at restore when the cn fast path re-syncs.
2. Populate the host-side binding: ship `deployment_combined_hash` + `custom_nodes_generation` at the v2 call site (request_metadata) or via env so `complete` can become `True`; verify deploy tooling supplies `COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH` / non-None `source_identity`.
3. Step-3 container gate (O2'/O3'/O4'): recompute-hash assert (already instrumented), deployment-identity compare vs frozen proof, non-empty `outputs_to_execute` precondition, Gate 2 preserved, cert/preflight skip under guard, writeback removal behind env flag.
4. Verify registry-fingerprint parity host↔container for the production deploy (host may carry local-only nodes).

---

# Step 2 implementation

Status: **IMPLEMENTED** (working tree, branch `TESTING2`). Behaviorally inert: the snapshot proof is frozen and instrumented only — nothing consumes it; `plan_validation_consumed=False`; certificate/preflight/`validate_prompt`/writeback/Gate 2/repair decisions are unchanged. No commits made by this task (concurrent dirty work prevents a safe commit). No paid runs.

What landed:
1. Canonical `custom_nodes_generation` provenance from the deploy-generated baked manifest (identical value host-side and container-side).
2. Root-filtered canonical registry fingerprint (excludes host-local-only nodes; path-independent; deterministic).
3. Deployment-static proof frozen into `BootstrapState.snapshot_validation_proof` at snapshot creation (after manifest persist, before CPU snapshot capture), with restore-time staleness marking.
4. Host-side validation memoization (local-only, identity-keyed).
5. Plan↔snapshot parity matrix instrumentation (exact-match diagnostics, `consumed=False`).
6. 20 new unit tests + full relevant-suite regression run.

---

# Deployment identity provenance

- Container: `_V2_DEPLOYMENT_COMBINED_HASH` (modal_app.py:15771-15779) = `stable_hash({source_combined_hash, runtime_shape})`; `source_identity` is built unconditionally by `build_deployment_identity` (deployment_spec.py:232-283 — never raises on missing paths, hashes whatever exists) at modal_app.py:3226; only the exception fallback (15752-15765) yields `source_identity=None`. The stable_hash wrap means the value is **never literally `""`** — on the exception path it degrades to a runtime-shape-only hash (semantically weak, fail-safe for parity).
- **`source_identity` non-None: CODE-verified for the normal path; NOT live-verified** (Step 2 forbids paid runs). Manual check: on a real snapshot, confirm `[v2.deployment_proof] dep_hash=<non-empty>` and `[v2.generation_identity]` show the real source identity.
- Host-side at plan build: `deployment_combined_hash` from `request_metadata["deployment_combined_hash"]` or env `COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH` (canonical_execution.py:1381) — **still not populated by any deploy tooling today**, so `plan.deployment_identity.deployment_combined_hash` will be `""` → `plan_identity_incomplete` → future fast path correctly ineligible until Step-3 wiring ships it (never fabricated).
- Snapshot freeze uses `_V2_DEPLOYMENT_COMBINED_HASH` with fallback to `state.deployment_combined_hash` (frozen by `freeze_custom_node_identity`, runtime_bootstrap.py:490).

---

# custom_nodes_generation provenance

**Canonical source (single, deploy-generated, immutable, both sides):** `production_custom_node_generation` in the **baked custom-node dependency manifest**.

- Deploy-time: computed at comfyapp.py:7796-7798 via `custom_node_source_generation(_LOCAL_CUSTOM_NODES)` — MD5 over sorted JSON of `{schema_version:2, nodes:[{name, content_hash}]}`, where `content_hash` is per-dir SHA-256[:16] over tracked files (.py/.txt/.toml/.cfg + requirements/pyproject/setup), excluding generated dirs/files (comfyapp.py:3395-3461).
- Host artifact: repo-local `.baked_custom_node_deps/custom_node_deps_baked.json` — **verified present on disk**. Read by `_read_baked_custom_node_manifest()` / `_read_baked_custom_node_generation()` (canonical_execution.py:889-912); fallback `request_metadata["custom_node_generation"]` if absent.
- Container artifact: `/opt/comfymodal/custom_node_deps_baked.json` (comfyapp.py:2915), read at snapshot freeze; the frozen value is additionally cross-checked against `state.custom_node_generation` (observed from the volume tree at startup) via `generation_matches_observed` — mismatch ⇒ proof incomplete (fail-safe, never fabricated).
- Not used: the host's `_build_custom_node_fingerprint` (__init__.py:1128, SHA-256 over requirements.txt only) and `deploy_warmup.deployment_generation` (timestamped token) — different algorithms; documented so no future change conflates them.
- Note: a concurrent agent's comfyapp.py change (volume re-fingerprinting removal, ~86 s/boot) makes the persisted generation record the trusted content-derived value; the baked-vs-observed cross-check above keeps the proof honest under that model.

---

# Canonical registry fingerprint

Surface (contracts.py `compute_registry_fingerprint(class_mappings=None, *, roots=None)`, 621-643+):
- **Inputs:** classes of `NODE_CLASS_MAPPINGS` whose module (resolved via `sys.modules`) has a `__file__` under **any** deployment root; modules that cannot be resolved are included conservatively; sorted by class name; entries `name=module.qualname`; SHA-256 over the joined lines.
- **Excluded:** classes whose module file is outside the roots (host-local-only dev nodes) — so local development nodes do not corrupt production parity.
- **Path-independent:** absolute paths are used only for the include/exclude decision, never hashed — identical content ⇒ identical fingerprint across host and container with different mount points.
- **Deterministic ordering**, no timestamps/addresses/process-local IDs. `""` when the registry is unavailable/empty → ineligible, never fabricated.
- **Roots:** host = `[comfyui_root (plan param), custom_nodes_dir (parent of repo root), repo root]`; container = `[bootstrap comfyui_root (fallback "/root/comfy/ComfyUI"), CUSTOM_NODES_PATH, repo root]`.
- A mismatch makes the future fast path **ineligible** — it never fails an otherwise-valid generation.

---

# Frozen BootstrapState proof

- Field: `BootstrapState.snapshot_validation_proof` (runtime_bootstrap.py:332-334); setters `freeze_validation_proof` / `mark_validation_proof_stale` (554-566).
- Freeze point: `modal_app.py` startup, after `bootstrap.startup()` returns (node classes imported) and after the dependency-manifest persist block, before the CPU snapshot build (freeze block ~7624-7717). Non-fatal on failure (`[v2.deployment_proof] status=failed` — startup must never break).
- Payload (schema `DEPLOYMENT_PROOF_SCHEMA_VERSION = 1`):
```text
schema_version: 1
deployment_combined_hash
custom_nodes_generation          (baked manifest value)
generation_matches_observed      (baked == state.custom_node_generation, both non-empty)
registry_fingerprint             (root-filtered)
dependency_manifest_identity     (the exact identity the manifest writer persisted; state set at modal_app.py:4521)
repair_mode
complete: bool                   (dep_hash AND baked_gen AND gen_ok AND reg_fp AND dep_identity)
valid: bool                      (= complete at freeze; stale flips it)
invalid_reason: str
source: "snapshot_startup"
```
- `dependency_manifest_identity` provenance: `_persist_v2_dependency_manifest` writes the manifest via the shared legacy writer and copies `manifest["identity"]` into `state.dependency_manifest_identity` (modal_app.py:4517-4522) — the same value the request-time preflight would re-derive, frozen.
- Persistence: `BootstrapState` is memory-only by design (never serialized; survives the Modal CPU snapshot as the in-memory object graph) — the proof rides the same mechanism as `snapshot_certificate`/`snapshot_execution_seed`.

---

# Restore validity/staleness rules

- `restore()` custom-node fast path (runtime_bootstrap.py:1716-1794): the mismatch/fallback branches (`missing_current_token`, `schema_mismatch`, `generation_mismatch`, `deployment_hash_mismatch`, `untrusted_source`) and the post-sync re-freeze block call `mark_validation_proof_stale(f"custom_node_{reason}")` → `valid=False`, `invalid_reason` set.
- The exact-skip branch (`decision=snapshot_exact_skip`) never marks stale — the frozen proof stays valid.
- Never silently refreshes a mismatching proof into validity; a re-synced container simply has a stale proof (fail-safe ineligible).

---

# Deployment-static preflight proof

- The frozen proof carries the manifest identity + repair mode + `generation_matches_observed` — exactly the inputs the ~145 ms request-time preflight re-derives from Volume JSON reads (manifest load, generation record, baked manifest). Step 3 can later skip those reads against the frozen proof; nothing is skipped in Step 2.
- Kept OUTSIDE the frozen proof (workflow-specific, still per-request): prompt structure check (sub-ms) and missing-node class walk/repair (0.3 ms) — per the O1' design.

---

# Host validation memoization

- Previously: none existed (verified) — `execution.validate_prompt` ran on every `build_execution_plan(collect_validation_proof=True)`.
- Now: `_PLAN_VALIDATION_MEMO` (canonical_execution.py:934-947, max 64 entries, simple clear-on-overflow eviction), keyed by `(prompt_sha256(raw dispatch workflow), deployment_combined_hash, custom_nodes_generation, registry_fingerprint, VALIDATION_PROOF_SCHEMA_VERSION)`; hit → payload copied (never shared mutable state); `validated_workflow_hash` reset to `dispatch_hash` after compute on both hit and miss so `plan.workflow_hash == validated_workflow_hash` always holds; exceptions never cached; fail-closed unchanged. `memo=hit|miss` in the `[v2.plan_proof]` print.
- Documented nuance: the key uses the raw (pre-coercion) workflow hash — coercion-affected workflows (rare string/int literals) simply miss and revalidate correctly; identical submissions hit.

---

# Plan ↔ snapshot parity matrix

`evaluate_plan_snapshot_parity(plan.deployment_identity, snapshot_proof)` (contracts.py) returns, per exact-match rule (both sides non-empty AND equal):

```text
plan_validation_schema, plan_deployment_complete,
snapshot_proof_present, snapshot_proof_complete, snapshot_proof_valid,
deployment_hash_match, custom_nodes_generation_match,
registry_fingerprint_match, dependency_proof_match,
future_fast_path_eligible, future_fast_path_ineligible_reason
```

- Instrumented in `modal_app.py` immediately after the Step-1 block (~11172+): `[v2.plan_proof] parity ...` print + `trace.emit("plan_snapshot_parity", metadata=...)`; `consumed=False` retained.
- Eligibility requires: plan `complete` AND proof `complete` AND proof `valid` AND all four matches. Workflow-hash binding remains independently recomputed (Step-1 instrumentation `match=`).

---

# Changed files

| File | Changes (Step 2) |
|---|---|
| `comfymodal_runtime/contracts.py` | `DEPLOYMENT_PROOF_SCHEMA_VERSION`, `compute_registry_fingerprint` roots filter, `evaluate_plan_snapshot_parity` |
| `comfymodal_runtime/runtime_bootstrap.py` | `snapshot_validation_proof` field, `freeze_validation_proof`/`mark_validation_proof_stale`, restore() stale marking |
| `comfymodal_runtime/modal_app.py` | startup proof freeze block (~7624-7717), parity instrumentation (~11172+) |
| `canonical_execution.py` | baked-manifest readers, `_host_requirements_repair_mode`, memoization, `_collect_plan_deployment_identity` (baked generation + roots fingerprint + `dependency_manifest_identity`), build wiring (identity computed up-front, `memo=` print) |
| `tests/test_deployment_proof.py` | NEW — 20 unit tests |

Untouched (concurrent agents' files preserved): `comfyapp.py` (another agent's volume re-fingerprint removal), `__init__.py`, `modal_transport.py`, `model_preload.py`, `clip_conditioning_cache.py`, `modal_client.py`, `tools/*`.

---

# Local verification

- `python run_tests.py tests.test_deployment_proof` → **20 tests OK** (freeze/complete/incomplete/stale; generation provenance both sides; fingerprint determinism, root exclusion, change-sensitivity; full parity matrix incl. mismatch reasons; memo hit/miss; identity-change miss).
- `python run_tests.py tests.test_plan_validation_proof tests.test_runtime_contracts tests.test_canonical_execution` → **75 tests OK** (Step-1 guarantees intact).
- `python -m pytest tests/test_env_flags.py -q` → **1378 passed**; `python run_tests.py tests.test_module_bootstrap` → **1 OK**.
- Syntax: OK (utf-8-sig; note `runtime_bootstrap.py` carries a pre-existing BOM in HEAD — not introduced here).
- No paid runs; no commits.

---

# Runtime behavior unchanged

- `plan_validation_consumed=False` throughout; certificate lookup, dependency preflight, `execution.validate_prompt`, certificate writeback, Gate 2, missing-node repair, and graph execution are **untouched** (diff-verified).
- The only runtime deltas: (a) startup freezes + logs `[v2.deployment_proof]`; (b) restore marks the proof stale on custom-node drift; (c) one extended diagnostics print + `plan_snapshot_parity` trace event; (d) host-side validation is memoized and the plan carries `dependency_manifest_identity` (identity values only — no decision changes).

---

# Step 3 eligibility

Remaining blockers before the Step-3 container gate (cert removal / preflight skip / validate skip under the eligibility matrix):

1. **Live verification (manual, one paid correctness run after Step 3 lands):** `source_identity` non-None in the deployed image; `[v2.deployment_proof] gen_ok=1` (baked == observed volume generation); container registry-parity (`reg_match=1`) — confirm the container comfyui_root fallback (`/root/comfy/ComfyUI`) matches the real image layout.
2. **Host-side `deployment_combined_hash` population:** nothing ships it at the v2 call site today → `plan.deployment_identity.complete=False` → ineligible by design; Step-3 wiring must read deploy-provided env/metadata (no new RPC).
3. **`dependency_manifest_identity` parity** depends on repair-mode env agreement (`COMFYMODAL_REQUIREMENTS_REPAIR_MODE`, mirrored host-side default `fail_fast`) and baked-manifest freshness — confirmed by the parity line on the first real run.
4. **Step-3 gate itself** (recompute-hash assert already instrumented; eligibility-gated cert/preflight/validate skip; non-empty `outputs_to_execute` precondition; writeback removal behind env flag) is the next task — not implemented here.
5. **Concurrent churn** in `modal_app.py`/`comfyapp.py`/`__init__.py` — coordinate before touching those regions again.

> **Step 2 is now IMPLEMENTED and verified** (see the Step-2 sections below). The next single step is Step 3 (container trust gate + cert removal).

---

# Step 2 implementation

Status: **IMPLEMENTED** (working tree, branch `TESTING2`). Behaviorally inert: proof frozen, restored, marked stale on drift, and logged — never consumed (`plan_validation_consumed=False`); certificate/preflight/`validate_prompt`/writeback/Gate 2/repair untouched. No commits made by this task (concurrent uncommitted work in `modal_app.py`/`__init__.py`/`comfyapp.py` would be captured by a commit).

---

# Deployment identity provenance

- Container: `_V2_DEPLOYMENT_COMBINED_HASH` (modal_app.py:15771-15779) = `stable_hash({source_combined_hash: source_identity.combined_hash, runtime_shape})`; never literally `""` (the wrap). `source_identity` is `None` **only** on the exception fallback of `build_modal_resources()` (15752-15765); `build_deployment_identity` (deployment_spec.py:232-283) never raises on missing paths. Production path (`_bootstrap_injected=False`) always runs `_configure_runtime` (7047-7056) which assigns `_CANONICAL_DEPLOYMENT_COMBINED_HASH` at startup.
- **Code-verified normally non-None; NOT live-verified** (no paid runs allowed in Step 2) — a degraded runtime-shape-only wrap is possible if `build_modal_resources()` raised at import. Manual check: `[v2.deployment_proof] dep_hash=...` on a real snapshot.
- Host plan side: `deployment_combined_hash` from `request_metadata["deployment_combined_hash"]` or env `COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH` — **nothing populates these today** → plan identity `complete=False` → future fast path ineligible until deploy tooling supplies it (Step-3 prerequisite).

---

# custom_nodes_generation provenance

**Canonical source (both sides, deploy-generated immutable artifact):** `production_custom_node_generation` inside the **baked custom-node dependency manifest**:
- Host: repo-local `.baked_custom_node_deps/custom_node_deps_baked.json` — **verified present on disk**; read by `_read_baked_custom_node_generation()` (canonical_execution.py:891-914); fallback `request_metadata["custom_node_generation"]`.
- Container: image-local `/opt/comfymodal/custom_node_deps_baked.json` (comfyapp.py:2915), read at snapshot freeze via `load_baked_custom_node_dependency_manifest()`.
- Value computed at deploy with the exact container algorithm `custom_node_source_generation` (comfyapp.py:3444-3461): MD5 over sorted JSON `{schema_version:2, nodes:[{name, content_hash}]}`; `content_hash` = per-dir SHA-256[:16] over tracked files (3395-3441).
- Snapshot freeze records the baked value plus `generation_matches_observed` vs `state.custom_node_generation` (from `observe_generations`, runtime_bootstrap.py:1259-1265); mismatch → proof incomplete (fail-safe).
- Parity holds by construction when the deploy tree == volume tree — the invariant the existing `snapshot_exact_skip` path already detects/logs (modal_app.py:7152-7160).

---

# Canonical registry fingerprint

Surface (deterministic, path-independent, both sides identical algorithm):
- Entries: `f"{class_name}={module}.{qualname}"` over `NODE_CLASS_MAPPINGS`, **sorted by class name**.
- Inclusion filter: class included only when its module (via `sys.modules`) has `__file__` under **any deployment root** — `[comfyui_root, custom_nodes_dir, repo_root]` (host: `comfyui_root` param + parent-of-repo-root + repo root; container: bootstrap-config comfyui root (fallback `/root/comfy/ComfyUI`), `CUSTOM_NODES_PATH`, repo root). Unresolvable modules are included conservatively. **File paths never enter the hash input.**
- SHA-256 over the joined entries; `""` when the registry is unavailable/empty or enumeration fails → ineligible, never fabricated.
- Host-only/local-dev nodes outside the roots are excluded → host↔snapshot parity is achievable; any genuine registry difference (or root misconfiguration) makes the future fast path **ineligible, never fails a valid generation**.
- `compute_registry_fingerprint(class_mappings=None, *, roots=None)` (contracts.py:621-682); `roots=None` keeps the Step-1 full-registry behavior (backward compatible).

---

# Frozen BootstrapState proof

- Field: `BootstrapState.snapshot_validation_proof: dict` (runtime_bootstrap.py:332-334); setters `freeze_validation_proof(proof)` / `mark_validation_proof_stale(reason)` (554-566, modeled on `set_snapshot_certificate`/`invalidate_snapshot_certificate`).
- Payload (frozen at startup, modal_app.py:7624-7717, after `bootstrap.startup` 7470 and manifest persist 7622-7642, before the CPU snapshot build 7654):
```text
{schema_version: 1, deployment_combined_hash, custom_nodes_generation (baked),
 generation_matches_observed, registry_fingerprint, dependency_manifest_identity,
 repair_mode, complete, valid, invalid_reason, source: "snapshot_startup"}
```
- `complete`/`valid` = all of: deployment hash, baked generation, generation-match, registry fingerprint, dependency identity non-empty; `invalid_reason` lists the first missing component (e.g. `deployment_hash_unavailable`, `baked_generation_unavailable`, `generation_mismatch`, `registry_fingerprint_unavailable`, `dependency_identity_unavailable`). Never fabricated.
- `dependency_manifest_identity` is the exact identity the startup manifest writer persisted (set at modal_app.py:4521 from `_manifest["identity"]`, built by `_build_and_persist_dependency_manifest` from combined hash + baked fingerprint + generation + repair mode — shared builder `dependency_manifest.build_identity`, dependency_manifest.py:35-59).
- Freeze is non-fatal (`[v2.deployment_proof] status=failed` on exception — never breaks startup).
- `BootstrapState` is memory-only by design (survives the Modal CPU snapshot in the object graph; no serialization added — verified no `to_dict`/persist exists).

---

# Restore validity/staleness rules

- restore() custom-node fast path (runtime_bootstrap.py:1716-1794): any fallback decision — `missing_current_token`, `schema_mismatch`, `generation_mismatch`, `deployment_hash_mismatch`, `untrusted_source` — calls `mark_validation_proof_stale(f"custom_node_{reason}")` (valid→False, invalid_reason set); the resync block re-marks after re-freeze.
- The exact-skip branch (`_skipped_cn_sync=True`, 1740) **never** marks stale — the frozen proof remains valid.
- A mismatching proof is never silently refreshed into validity; only a future snapshot creation re-freezes a valid proof.

---

# Deployment-static preflight proof

- The proof's `dependency_manifest_identity` + `repair_mode` are exactly the inputs the ~145 ms request-time preflight re-derives via Volume reads (comfyapp.py:10167-10185: baked manifest, generation record, persistent manifest load + identity check). Step 3's gate can skip those Volume-backed checks by comparing `plan.deployment_identity.dependency_manifest_identity` vs the frozen proof value instead.
- The two workflow-specific/sub-ms checks (structure validation `assert_valid_api_prompt_structure`; class-usage walk / missing-node repair) stay **outside** the frozen proof and outside any future skip.
- Nothing is skipped in Step 2; the preflight path is untouched.

---

# Host validation memoization

- **Implemented** (none existed — verified): `_PLAN_VALIDATION_MEMO` (canonical_execution.py:934-946), max 64 entries, clear-on-overflow (documented simple eviction).
- Key = `(prompt_sha256(dispatch_workflow), deployment_combined_hash, custom_nodes_generation, registry_fingerprint, VALIDATION_PROOF_SCHEMA_VERSION)` — the exact validation identity from the design.
- Hit → payload copied (never mutated); miss → `_collect_plan_validation_proof` runs and the payload is stored; `validated_workflow_hash` is always reset to `dispatch_hash` after computation, so `plan.workflow_hash == validated_workflow_hash` holds on both hit and miss.
- Exceptions are never cached; fail-closed validation unchanged. Documented coercion nuance: the key uses the raw pre-coercion hash, so coercion-affected workflows miss (correct, rare).
- Evidence: unit tests prove identical builds call `execution.validate_prompt` exactly once and identity changes re-validate; `[v2.plan_proof] ... memo=hit|miss` is logged.

---

# Plan ↔ snapshot parity matrix

`evaluate_plan_snapshot_parity(plan_identity, snapshot_proof)` (contracts.py:684-741) — pure, decision-free:

| Field | Semantics |
|---|---|
| `plan_validation_schema` / `plan_deployment_complete` | plan-carried identity state |
| `snapshot_proof_present/complete/valid` | frozen proof state |
| `deployment_hash_match` | both non-empty and equal |
| `custom_nodes_generation_match` | both non-empty and equal |
| `registry_fingerprint_match` | both non-empty and equal |
| `dependency_proof_match` | both non-empty and equal |
| `future_fast_path_eligible` | complete plan ∧ complete valid proof ∧ schema ok ∧ all four matches |
| `future_fast_path_ineligible_reason` | comma list of failing components |

Container emits `[v2.plan_proof] parity proof_present=... dep_match=... gen_match=... reg_match=... dep_proof_match=... eligible=... reason=... consumed=False` + `trace.emit("plan_snapshot_parity", ...)` right after the Step-1 block (modal_app.py:11172-11194). Workflow hash binding stays independently recomputed as in Step 1 (`prompt_sha256(_thaw(plan.workflow)) == plan.workflow_hash`).

---

# Changed files

| File | Change |
|---|---|
| `comfymodal_runtime/contracts.py` | `DEPLOYMENT_PROOF_SCHEMA_VERSION`, `compute_registry_fingerprint(roots=...)` filter, `evaluate_plan_snapshot_parity` |
| `comfymodal_runtime/runtime_bootstrap.py` | `snapshot_validation_proof` field, `freeze_validation_proof`/`mark_validation_proof_stale`, restore() stale marking |
| `comfymodal_runtime/modal_app.py` | startup proof freeze + `[v2.deployment_proof]` log; request-time parity instrumentation + `plan_snapshot_parity` trace |
| `canonical_execution.py` | baked-manifest readers, `_host_requirements_repair_mode` mirror, host `dependency_manifest_identity` derivation, `_PLAN_VALIDATION_MEMO` memoization, roots-filtered fingerprint, `memo=` diagnostics |
| `tests/test_deployment_proof.py` | NEW — 20 tests (freeze/mark, provenance parity, fingerprint determinism/exclusion/sensitivity, parity matrix eligibility + each mismatch, memo hit/miss, identity change revalidation) |

Untouched: certificate decision block, preflight, `validate_prompt` call site, writeback, Gate 2, repair, Active Profile, CLIP/UNET, conditioning cache, output persistence, `model_preload.py`, `modal_transport.py`, `tools/*`, `comfyapp.py` (concurrent agent's work — volume re-fingerprint removal — preserved untouched).

---

# Local verification

- `python run_tests.py tests.test_deployment_proof` → **20 tests OK**.
- `python run_tests.py tests.test_plan_validation_proof tests.test_runtime_contracts tests.test_canonical_execution` → **75 tests OK**.
- `python run_tests.py tests.test_module_bootstrap` → 1 test OK; `python -m pytest tests/test_env_flags.py -q` → **1378 passed**.
- Syntax: all 5 edited files parse (utf-8-sig; `runtime_bootstrap.py` has a pre-existing BOM, unchanged from HEAD).
- No paid runs; no commits; no new Modal/Volume/network calls in the host-side paths (pure file I/O + in-memory).

---

# Runtime behavior unchanged

- Container certificate lookup, preflight, `execution.validate_prompt` call site, writeback, Gate 2, missing-node repair, graph execution: **untouched** (verified by diff review).
- `plan_validation_consumed=False`; the parity matrix is diagnostics only.
- Host-side deltas: plan identity now carries the baked generation + dependency identity + roots-filtered fingerprint; host validation is memoized (no decision change); one extra `[v2.plan_proof]` field and the `[v2.deployment_proof]` startup line.
- Workflow acceptance/rejection semantics unchanged (fail-closed host validation identical).

---

# Step 3 eligibility

**Remaining blockers before the container trust gate can be enabled:**

1. **Plan-side deployment hash is empty in practice**: nothing populates `COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH` env or `request_metadata["deployment_combined_hash"]` at plan build → `plan_deployment_complete=False` → ineligible. Deploy tooling must supply it (or the host-side call site must pass it).
2. **Live source_identity verification**: code-verified normally non-None, but a degraded runtime-shape-only wrap is possible if `build_modal_resources()` raised at import — confirm `[v2.deployment_proof] dep_hash=...` and `[v2.generation_identity]` on a real snapshot (one paid correctness run, deferred to Step 3).
3. **gen_ok / reg_fp parity needs one real run**: `[v2.deployment_proof] gen_ok=1 reg_fp=1` at snapshot and request-time `parity gen_match=1 reg_match=1` confirm the host↔snapshot equivalence that unit tests can only approximate.
4. **dependency_manifest_identity host↔container parity**: host derivation uses `dependency_manifest.build_identity` with baked components + `COMFYMODAL_REQUIREMENTS_REPAIR_MODE` (default `fail_fast` mirrored); must match the container's manifest-writer identity when envs agree — first real-run parity line confirms; a mismatch fails safe (ineligible).
5. **Step 3 gate itself** (recompute-hash assert already instrumented; deployment-identity compare; non-empty `outputs_to_execute` precondition; Gate 2 preserved; cert/preflight skip under guard; writeback removal behind env flag) is the next task and is not implemented here.

> **Step 3 is now IMPLEMENTED and locally verified** (sections below). The single paid acceptance run was consumed but did **not** exercise the fast path (served by a pre-Step-3 snapshot from a concurrent deploy race; the benchmark harness does not enable `collect_validation_proof`) — two concrete blockers documented in "Paid acceptance run". Hard-stop honored: no second paid run.

---

# Step 3 implementation

Status: **IMPLEMENTED** (working tree, branch `TESTING2`). The plan-carried validation proof is now *consumed* under an exact Step-2 parity gate: eligible requests skip certificate lookup/Volume RPC, deployment-static preflight, remote `execution.validate_prompt`, and certificate writeback; everything else takes the unchanged legacy path. Certificate subsystem code remains (Step-4 cleanup deferred). No commits (concurrent dirty work). Local verification green; the single paid acceptance run consumed without fast-path demonstration (see below).

---

# Plan deployment-hash provenance

Host-side source chain for `plan.deployment_identity.deployment_combined_hash` (canonical_execution.py:1064-1070), in order:
1. `request_metadata["deployment_combined_hash"]`
2. env `COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH`
3. persisted `.deployed_state.json` key `deployment_combined_hash` (new; written by `_save_deploy_state`, __init__.py:1157-1174)
4. `_compute_host_deployment_combined_hash()` (canonical_execution.py:936-967) — once-per-process memoized mirror of the container's `_V2_DEPLOYMENT_COMBINED_HASH = stable_hash({"source_combined_hash": build_deployment_identity(runtime_root, custom_node_paths).combined_hash, "runtime_shape": runtime_shape_config().identity_payload()})`, computed from pure stdlib modules (`deployment_spec`, `runtime_shape`, `contracts.stable_hash`); `""` on failure (never fabricated).

No Modal RPC, no Volume read, no network, no per-request repo scan (the heavy identity computation runs at most once per process; steady state is a local file/constant read). If the exact value cannot be produced the plan stays `complete=False` → ineligible (fail-safe, trust model unweakened).

---

# Final trust gate

Pure helper `evaluate_plan_validation_consumption(parity, plan_validation, workflow_hash_match, validation_hash_match, structure_ok, outputs_nonempty)` (contracts.py:723-763) — consumes only when ALL hold:

```text
snapshot proof present AND complete AND valid          (via parity)
plan deployment identity complete                       (via parity)
deployment_hash_match AND custom_nodes_generation_match
registry_fingerprint_match AND dependency_proof_match   (via parity)
supported validation schema (== VALIDATION_PROOF_SCHEMA_VERSION)
plan.validation.validated == True
validation_hash_match   (validated_workflow_hash == plan.workflow_hash)
workflow_hash_match     (container recompute prompt_sha256(_thaw(plan.workflow)) == plan.workflow_hash — NEVER trusts the shipped hash alone)
structure_ok            (assert_valid_api_prompt_structure passed)
outputs_nonempty        (outputs_to_execute non-empty)
```

Ineligibility reasons are enumerated per component (e.g. `workflow_hash_mismatch`, `empty_outputs`, `snapshot_proof_invalid_or_unsupported`). No empty/partial identity component is ever accepted as a match.

---

# Repair/Gate-2 ordering

Decision computed *before* the certificate block (modal_app.py:11187-11216), applied at the skip-flag level (11278-11296), and the certificate block is bypassed via `if _V2_VALIDATION_CERT_ENABLED and not _pp_eligible:` (11339). **The proof is NOT trusted past repair**: missing-node repair still runs unconditionally; existing Oracle Gate 2 (11615-11687) — now via `apply_repair_invalidation(consumed, "repair_changed")` (11714-11717) — flips `_plan_proof_consumed=False`, clears `outputs_to_execute`/`node_errors`, sets `_v2_preflight_ran=True`, and re-runs the full legacy preflight+validate path. Ordering guarantee: any class-availability change after the gate forces the legacy path; the proof is consumed only on the exact-match branch.

---

# Fast path

Eligible request active path: structure validation → workflow-hash recompute (instrumented Step-1) → in-memory proof comparisons (Step-2 parity + Step-3 gate) → missing-node walk / Gate 2 → pregraph setup → executor invocation. `execute_outputs` = `plan.validation["outputs_to_execute"]` (authoritative only after the gate succeeds); `node_errors` carried for diagnostics only. Absent: certificate Volume reload, certificate file read, certificate JSON validation, process-certificate-cache gating, persistent-manifest Volume read, generation-record request-time read, remote `execution.validate_prompt`, certificate writeback, certificate Volume commit.

---

# Legacy fallback path

Any of: missing plan validation, unsupported schema, workflow/validation hash mismatch, empty outputs, incomplete plan identity, incomplete/stale snapshot proof, deployment/generation/registry/dependency mismatch, repair/class-availability change, malformed proof → today's full path unchanged: certificate behavior as supported → full dependency preflight → `execution.validate_prompt` → existing validity/error handling → normal executor. Proof mismatch never becomes a generation failure; malformed/tampered workflows that already require fail-closed rejection keep failing closed (structure failure + hash mismatch both land on legacy, which rejects).

---

# Certificate bypass

On the eligible path the certificate subsystem (snapshot-memory gate, process cache, Volume read) is skipped by construction (condition `and not _pp_eligible`); a `certificate_read_outcome` event with `cert_source=plan_validation, cert_decision=plan_validation_fast_path` is emitted for diagnostics. Fallback: entire certificate code path functional, untouched.

---

# Preflight bypass

Only the portion proven by `snapshot_validation_proof` is skipped: baked dependency state, persisted dependency manifest, custom-node generation identity, deployment-static dependency checks. The two workflow/request-specific checks — prompt/API structure validation (runs in the gate) and class availability / missing-node repair + Gate 2 (always runs) — are never skipped. Skip never broadened beyond what Step 2 proves.

---

# Remote validate_prompt bypass

`execution.validate_prompt` is not invoked on the eligible path (the existing `if not _v2_cert_preflight_skip:` guard, set by the plan-proof apply-block); `valid=True, error={}` and `_diag_prompt_validation_ms=0.0` on the skip branch. Fallback: remote validation identical to today.

---

# Certificate writeback bypass

Writeback gate now `should_write_validation_cert(_v2_schedule_cert_write, _v2_preflight_ran)` (contracts.py:777-779; modal_app.py:13047). On the fast path `_v2_schedule_cert_write` is never set and `_v2_preflight_ran` stays False → no write, no commit. Fallback (incl. Gate-2 degradation, which sets `_v2_preflight_ran=True`) writes exactly as today.

---

# Instrumentation

- Gate decision: `[v2.plan_proof] decision=plan_validation_fast_path consumed=1` (full matrix: workflow_hash_match, validation_hash_match, plan_complete, snapshot_complete, snapshot_valid, dep_match, gen_match, reg_match, dependency_match, repair_changed=0, outputs_nonempty, eligible=1) or `decision=legacy_validation_fallback consumed=0 reason=<first cause>` (modal_app.py:11820-11845); `trace.emit("plan_proof_decision", ...)`.
- Timing spans preserved: on the consumed path `_cert_ms = _preflight_ms = _validation_ms = 0.0` (modal_app.py:12514-12516) so diagnostics show zero, not "absent"; `graph_setup_ms` continues to be measured.

---

# Local verification

- `tests/test_step3_fast_path.py` (NEW, 27 tests): exact parity → eligible; workflow-hash recompute; tampered hash → cannot consume; unsupported schema / not-validated / empty-outputs / deployment / generation / registry / dependency / stale-proof / incomplete-plan fallbacks; repair invalidation helper; Gate-2 preservation (via `apply_repair_invalidation` + `should_write_validation_cert` semantics); eligible path never schedules writeback; memo hit/miss; identity-change memo miss; no new network/Modal/Volume in plan construction; hash provenance chain (env → persisted → memoized-once).
- Combined: `test_step3_fast_path` + `test_deployment_proof` + `test_plan_validation_proof` + `test_runtime_contracts` + `test_canonical_execution` + `test_module_bootstrap` → **123 tests OK**; `test_env_flags` → **1378 passed**; syntax OK.
- Pre-existing (unchanged): `test_local_submission_critical_path` (9 C8 runtime-shape) + `test_production_workflow` (8 comfyapp env-default) failures — same signature as the Step-1 stash-verified baseline.

---

# Paid acceptance run

One run consumed (hard stop): `comfymodal-data\benchmarks\runs\v2_2026-08-12_05-54-14\` (run_0.json, summary.json). Config deployed: RTX PRO 6000 / CPU 12 / RAM 32768 MiB, cloud/region unpinned; `COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS=0` (verified: no 2500 arm exists anywhere in the current tree; default is 0).

**Provider/region observed:** `CLOUD_PROVIDER_GCP`, `us-east1`.

**Verdict: the fast path was NOT exercised by this run — two root causes, both concrete:**

1. **Stale snapshot race**: the run was served by a 43-minute-old snapshot (`snapshot_callback_age_at_restore_ms=2,596,887`; `image_id=im-q2GwFPLjr49HZMY6OgaWgH`, not the deployed `im-mFjm2cB2JTZRTFme8BVm6A`). A concurrent agent deployed the same shadow app between my deploy and my benchmark; Modal restored their older snapshot. Evidence: `plan_snapshot_parity` and `plan_validation_payload` events exist (Step-1/2 instrumentation) but **no `plan_proof_decision` event** — the serving container ran pre-Step-3 code.
2. **Harness wiring gap**: `tools/benchmark_v2_direct.py:999-1010` and `:2275-2282` call `build_execution_plan(..., validate=False)` **without `collect_validation_proof=True`**, so even a fresh Step-3 container would receive a plan with `plan.validation == {}` (`plan_validation_payload` shows `schema=0, payload_present=false`) → gate ineligible by design (fail-safe, correct, but the harness as-is cannot ever hit the fast path).

**Plan↔snapshot parity matrix (from the run, all as observed):**

```text
plan_validation_schema=1 plan_deployment_complete=false
snapshot_proof_present=true snapshot_proof_complete=false snapshot_proof_valid=false
deployment_hash_match=false custom_nodes_generation_match=false
registry_fingerprint_match=false dependency_proof_match=false
future_fast_path_eligible=false
reason=plan_identity_incomplete,snapshot_proof_incomplete,snapshot_proof_invalid_or_unsupported,
       deployment_hash_mismatch,custom_nodes_generation_mismatch,registry_fingerprint_mismatch,
       dependency_proof_mismatch
```

**What the run DID prove (legacy path + instrumentation on a real snapshot-restored container):**
- Legacy fallback executed correctly end-to-end: certificate Volume reload RPC **count=1** (`certificate_reload_start/end`, `cert_volume_reload_ms=103.7`, hit=false), dependency preflight **count=1** (`preflight_start/end`, `legacy_preflight_ms=22.3`), remote `validate_prompt` **count=1** (`prompt_validation_start/end`, `prompt_validation_ms=146.3`, `valid=true`, `output_count=2`, `node_error_count=0`).
- Workflow-hash recompute binding works in production: `plan_validation_payload` shows `workflow_hash == recomputed_hash` (`dabf819d...`), `hash_match=true`.
- Correctness: request succeeded; **1 image produced** (`production_v2-bench_107_b_0.png`, output node 107); one normal graph execution (Any Switch (rgthree) → CLIPTextEncode → ClownsharKSampler_Beta); no silent zero-output execution.
- `graph_setup_ms=296.0` on this legacy-path run (cert 104.3 + preflight 22.2 + validation 147.3 + mechanical ~22 — the preflight was short because the dependency-identity fast path hit on the old snapshot); `pre_sampler_total_ms=2757.8`, `reconciliation_status=ok`.
- Certificate writeback: **0 write events observable in the trace** (writeback is print+commit, not a trace event; legacy gate would have scheduled it on this run — not directly countable from artifacts).
- `plan_validation_consumed=0` (no Step-3 code on the serving container).

**Step-3 fast-path acceptance: NOT demonstrated.** The structural criterion (cert 150ms + preflight 145ms + validate 149ms absent on the eligible path) remains unproven in production; the mechanism is unit-verified (27 tests) but the one allowed paid run could not reach it. `source_identity` live health: **not verified** — the serving snapshot's proof was frozen (present=true) but incomplete, consistent with a concurrent mid-flight deploy; my deployed image's `[v2.deployment_proof]` startup line was never observed.

---

# Graph-setup timing

| Metric | Baseline (03-04-09) | Step-3 fast path (target) | Paid run (05-54-14, legacy) |
|---|---|---|---|
| certificate_ms | 150.7 | 0 | 104.3 |
| preflight_ms | 145.1 | 0 | 22.2 |
| validation_ms | 149.1 | 0 | 147.3 |
| graph_setup_ms | 460.5 | ~20-30 | 296.0 |
| restore_total_ms | 1228.6 | n/a | 790.2 |
| command→response wall | n/a | n/a | 82,175.7 |

The paid run's 296 ms is a **legacy-path** number on a different (concurrent) snapshot — not a Step-3 measurement. Fast-path graph_setup (~20-30 ms target) remains to be measured on a fresh Step-3 deployment with a proof-collecting harness.

---

# Correctness proof

- Executed workflow identical to submission; `outputs_to_execute` consumed only from `plan.validation` after the full gate; prompt rejection semantics unchanged (structure + hash mismatches land on legacy which rejects as today); missing-node repair + Gate 2 semantics preserved (unit-verified via `apply_repair_invalidation`; legacy path re-run on any repair change); arbitrary post-snapshot workflows supported (gate is workflow-agnostic); workflow-agnostic snapshot intact; `publish_restore_plan` untouched (default off); no new pre-submit Modal call; no new Volume read before submission; no warm-container requirement.
- Local evidence: 27 Step-3 tests + 123 combined + 1378 env-flags green; production evidence (above) confirms legacy correctness on a real snapshot.

---

# Remaining Step-4 cleanup

- Certificate subsystem code remains fully functional (fallback + rollback). Safe to delete **only after** a fresh-deploy acceptance run demonstrates: `future_fast_path_eligible=1`, `plan_validation_consumed=1`, certificate RPC count 0, preflight 0, remote validate 0, writeback 0, graph_setup ≈20-30 ms, output parity.
- Required before that run (two fixes, both local): (a) wire `collect_validation_proof=True` into `tools/benchmark_v2_direct.py`'s two `build_execution_plan` call sites; (b) coordinate the deploy so the benchmark targets a snapshot built from the Step-3 code (avoid the shadow-app deploy race — e.g., a dedicated acceptance app name or immediate-run-after-deploy with snapshot confirmation).
- Then: env-flag-gated removal of the cert block, process cache, writeback, and startup retention (dormant behind `COMFYMODAL_V2_VALIDATION_CERT=0`), keeping the legacy fallback reachable until the fast path has production evidence.

---

# Step 3 acceptance retry

Status: **PARTIAL — mechanism fixed and locally proven; paid acceptance NOT yet executed (deploy blocked by concurrent-editor churn; no paid request submitted).**

## Benchmark proof-collection fix

Both `build_execution_plan(...)` call sites in `tools/benchmark_v2_direct.py` (default single-run path and acceptance path) now pass `collect_validation_proof=True` **and** `comfyui_root=_COMFYUI_ROOT_DIR`, mirroring the production v2 dispatch (__init__.py:2437-2449). Verified: `tests/test_benchmark_v2_proof_collection.py` (7 tests: AST call-site checks, plan-carries-validation-payload behavior, registry-root filtering, `utils` pre-lock ordering, PromptServer-mirror ordering).

## Registry parity fixes (two independent harness-environment blockers, both resolved)

1. **`utils` shadowing** — `ComfyUI-CacheDiT\utils.py` (a plain module) shadows the real ComfyUI `utils/` package when CacheDiT's dir is on `sys.path` during node loading, breaking `utils.install_util` consumers (Impact Pack, RES4LYF). Fixed by pre-locking `import utils`/`import utils.install_util` into `sys.modules` before `init_extra_nodes` (registry 704 → 1179 classes).
2. **`PromptServer.instance` missing** — Impact Pack (`impact_server.py:60`) and RES4LYF (`res4lyf.py:37`) decorate `@PromptServer.instance.routes.post(...)` at import; the standalone harness never constructed a PromptServer (the real server does at main.py:470 before init_extra_nodes at :476). Fixed by mirroring `start_comfyui()`: populate the shared `comfy.cli_args.args` singleton (network-free `front_end_root` = local `web` dir) and construct `server.PromptServer(asyncio.get_running_loop())` before `init_extra_nodes` (registry 1179 → **2401 classes**).

Decisive local gate — plan build from the real benchmark workflow under the embedded interpreter (Python 3.13.12, `python_embeded`) with the full effective manifest:

```text
[v2.plan_proof] schema=1 payload=yes validated=True outputs=10 wf_hash=14f815f1916e075a dep_complete=True memo=miss
PLAN_VALIDATION schema=1 validated=True
OUTPUTS=('1049','1066','1067','107','1137','1281','199','202','9','935:931')
VH_MATCH=True (validated_workflow_hash == plan.workflow_hash)
DEP complete=True  dep_hash_len=64 gen_len=32 reg_len=64
DEP_IDENTITY=ffc4a94599b52849…
```

The two previous acceptance failures (`missing_node_type: PairConditioningSetProperties`, then `ImpactIfNone`) are eliminated; host-side authoritative validation now succeeds for the benchmark workflow.

## Fresh-deployment isolation

Dedicated app name `stable-modal-comfy-v2-step3-accept` (no shared shadow app). Deploy path: `V2_BENCHMARK_MODE=snapshot_restore_only` + `COMFYMODAL_V2_ENV_PROFILE=inherit` via `deploy_and_run_v2_single.bat` (construction-only, no probes), then `run_v2_single.bat` for the exactly-6 no-op restore probes, then one harness request.

## Deployment/image identity

- **Testing2/3 workspace (pre-move)**: one successful deploy of the dedicated app; 6/6 cold restore probes VALID on the fresh snapshot; serving image `im-k7KyKJq2Y8hA0HkdYemEcq` consistent across all probes. Snapshot gate (probe `invariant`): `unet_present=0, clip_present=1, vae_present=1, cpu_snapshot_models_present=1, container_retained=1, eviction_retained_role=clip_vae, rss≈13.3 GiB` — PASSED.
- **Testing4 workspace (current)**: the redeploy is **blocked by concurrent-editor churn** — Modal's "file modified during build process" guard aborted 5 deploy attempts, each on a different file the concurrent agents were editing during the ~2 min build window (`.cache/v2_restore_cache.json`, `comfymodal_runtime/v2_waterfall.py`, `tests/test_optimization_diagnostics.py`, `comfymodal_runtime/modal_app.py`). A 10-minute full-tree stability poll found no 200 s quiet window (continuous churn). Last attempted deploy image: `im-WD4VhBVhRTt3Lz2nEg0gwZ` (build completed; deploy aborted by the guard).

Per the task's stop conditions ("current concurrent edits make the checkout incoherent"; "the deployment cannot be isolated from concurrent app/snapshot replacement"), **no paid acceptance request was submitted** — zero paid cost incurred for Step-3 acceptance. The mechanism is not weakened.

## Source-identity live verification

**NOT completed** — deferred to the first successful fresh deployment on the current workspace (needs `[v2.deployment_proof] dep_hash=…` from a real snapshot; code-verified non-degraded on the normal path only).

## Snapshot proof / Plan validation proof / Full parity matrix / Fast-path decision / bypass proofs

**Not yet measurable in production** — the parity matrix, `plan_proof_decision`, and the certificate/preflight/validate/writeback counts require the one paid request on the fresh deployment. Locally proven equivalents:
- Plan validation proof: built and verified (above).
- Parity evaluator + consumption gate + all fallback reasons: 27 Step-3 unit tests + 59 combined + 7 harness tests green.
- Host-side registry surface now matches the container class surface (2401 classes, roots-filtered fingerprint computed with the same algorithm).

## Graph-setup timing / Application timing / Correctness

Not yet measurable (no paid request). Previous legacy-path reference: `graph_setup_ms=296.0` (testing2 stale-snapshot run, pre-fix). Fast-path target ≈20-30 ms pending the acceptance run.

## Step-4 readiness

**NO** — certificate subsystem must remain; production fast-path evidence does not exist yet.

---

# Step 3 acceptance retry — completion output (blocked state)

- Exact report path: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\V2_GRAPH_CERT_SETUP_DECOMPOSITION.md`
- Changed files (this retry): `tools/benchmark_v2_direct.py` (collect_validation_proof + comfyui_root at both call sites; `_COMFYUI_ROOT_DIR` sys.path insert; `_ensure_full_node_registry` with `utils` pre-lock + PromptServer mirror), `tests/test_benchmark_v2_proof_collection.py` (7 tests).
- Commit hash: `none` (concurrent dirty work prevents a safe commit).
- Exact benchmark harness change: `collect_validation_proof=True, comfyui_root=_COMFYUI_ROOT_DIR` at both `build_execution_plan` call sites + full server-mirror registry init (`utils` pre-lock + `PromptServer` + `init_extra_nodes`) before plan build.
- Exact deployment command: `modal deploy -m comfymodal_runtime.modal_app --name stable-modal-comfy-v2-step3-accept` (via deploy_and_run_v2_single.bat, snapshot_restore_only/inherit, construction-only).
- Acceptance app name: `stable-modal-comfy-v2-step3-accept`
- Deployed image ID (last attempt, testing4): `im-WD4VhBVhRTt3Lz2nEg0gwZ` (build OK, deploy aborted by churn guard); previous workspace serving image: `im-k7KyKJq2Y8hA0HkdYemEcq`
- Image identity matched: **NO for current workspace** (deploy blocked); matched on the pre-move workspace (all 6 probes served the deployed image).
- Exact effective V2 manifest: full list from the "Required effective environment" section (inherit profile, CPU_MODEL_SNAPSHOT=1, VAE_SNAPSHOT=1, SNAPSHOT_EXCLUDE_UNET=1, EVICT_RETAIN_ROLE=clip_vae, NATIVE_FAST_DISK_UNET=1, CLIP_CONDITIONING_CACHE=1, UNET_H2D_DELAY=0, UNET_ACTIVATION_MODE=late, VAE_ACTIVATION_MODE=sampling_end, PUBLISH_RESTORE_PLAN=0, SINGLE_USE=1, MINIMAL_GPU_TEARDOWN=1, RELEASE_GPU=1, CPU=12, MEM=32768, GPU=rtx-pro-6000, TBASE/O0/v1, cloud/region unpinned) — all applied to the deploy attempts.
- Snapshot CLIP/VAE/UNET presence (pre-move workspace, 6 probes): clip=1 vae=1 unet=0, retain=clip_vae, cpu_snapshot_models_present=1
- Snapshot RSS: ≈13.3 GiB (VMRSS 13,283-13,303 MiB)
- Actual provider/region (pre-move probes): GCP us-east1/us-central1 + AWS ap-northeast-1 (unpinned)
- source_identity healthy: **NOT live-verified** (deploy blocked on current workspace)
- Deployment proof complete/valid: **NOT live-verified** (same reason)
- Full plan↔snapshot parity matrix: **not measurable** (no paid request); locally the plan side is complete=True with all identity fields populated.
- workflow hash match / validation hash match: locally True (recomputed == plan hash; validated_workflow_hash == plan hash)
- future_fast_path_eligible: **not measurable** (no paid request)
- plan_validation_consumed: **not measurable** (no paid request)
- certificate RPC count / preflight count / remote validate_prompt count / writeback count: **not measurable** (no paid request)
- Old graph_setup baseline: 460.5 ms (03-04-09); 296.0 ms legacy (05-54-14 pre-fix run)
- New graph_setup: **not measurable** (no paid request)
- Measured Step-3 application-wall saving: **none measurable** (no paid request)
- Application wall including restore / command→response wall: not measured for Step-3
- Correct image produced: **N/A** (no request submitted)
- Step 3 production acceptance: **FAIL (blocked)** — mechanism locally proven; production evidence pending a churn-free deploy window
- Step 4 cleanup safe: **NO**

---

# Step 3 acceptance retry — final paid run (testing4, fresh deployment)

One paid request executed (run `v2_2026-08-12_16-55-32`, app `stable-modal-comfy-v2-step3-accept`, testing4). Hard-stop honored after this single valid run — no second request.

## Deployment/image identity

- Deployed app: `stable-modal-comfy-v2-step3-accept` (testing4, `V2_BENCHMARK_MODE=snapshot_restore_only`, `ENV_PROFILE=inherit`, full required manifest incl. `COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS=0`; cloud/region unpinned).
- Deployed/serving image: **`im-TVgb0ceq36ktk2S9z1o35Q`** — identical across all 6 restore probes AND the acceptance request (7 cold restores). **Image identity MATCHED** (fresh-image gate passed; no stale-shadow race).

## Snapshot gate (probe `invariant`, 6/6 VALID cold restores)

```text
unet_present=0 clip_present=1 vae_present=1 cpu_snapshot_models_present=1
container_retained=1 eviction_retained_role=clip_vae snapshot_exclude_unet_gate=1
RSS ≈ 12.99-13.0 GiB
```
PASSED. Provider/region observed (unpinned): GCP us-central1 / us-east4 / us-west1 / us-south1.

## Plan validation proof (host-side, this run)

```text
plan_validation_payload: schema=1 payload_present=true validated=true
outputs_count=2 outputs_ids=107,935:931
workflow_hash=2e43d4c0…  recomputed_hash=2e43d4c0…  hash_match=true
deployment_complete=true
```
**Both harness blockers conclusively fixed in production**: the plan now carries the authoritative validation payload, the container-side recomputed hash matches, and `plan_deployment_complete=true`.

## Full plan↔snapshot parity matrix (measured, this run)

```text
plan_validation_schema=1       plan_deployment_complete=true
snapshot_proof_present=true    snapshot_proof_complete=false  snapshot_proof_valid=false
deployment_hash_match=false    custom_nodes_generation_match=true
registry_fingerprint_match=false  dependency_proof_match=false
future_fast_path_eligible=false
reason=snapshot_proof_incomplete,snapshot_proof_invalid_or_unsupported,
       deployment_hash_mismatch,registry_fingerprint_mismatch,dependency_proof_mismatch
```

## Fast-path decision

```text
plan_proof_decision: consumed=false decision=legacy_validation_fallback
reason=snapshot_proof_incomplete,snapshot_proof_invalid_or_unsupported,
       deployment_hash_mismatch,registry_fingerprint_mismatch,dependency_proof_mismatch
```
**The gate correctly declined** — it did not consume the proof under mismatched identity (fail-safe, no weakening). The legacy path executed.

## Critical-path counts (this run)

```text
certificate Volume RPC count = 1   (certificate_reload_start/end; legacy path)
dependency preflight count     = 1   (preflight_start/end; legacy path)
remote execution.validate_prompt count = 1  (prompt_validation_start/end; legacy path)
certificate writeback          = legacy-scheduled (preflight_ran=true + valid ⇒ legacy gate)
fast-path writeback            = 0
plan_validation_consumed       = 0
```

## Graph-setup timing (this run — legacy path, single-use cold container)

```text
graph_setup_ms    = 3559.1   (cert 1110.3 + preflight 406.3 + validation 1908.2 + mechanical)
certificate_ms    = 1110.3   (cold Volume reload on fresh single-use container)
preflight_ms      = 406.3
validation_ms     = 1908.2
pre_sampler_total = 7829.7
```
Baseline for comparison: graph_setup 460.5 ms (03-04-09). This run's numbers are **legacy-path** values on a cold single-use container — they do NOT represent the fast path (which was correctly not taken). The ~20-30 ms fast-path target remains unmeasured in production.

## Application timing (this run)

```text
command_to_response_ms = 45368.5    wall_ms = 25297.4
restore_total_ms       = 1656.6
sampler_ms             = 3744.8     vae_decode_ms = 427.3
```
Sampling boundary (authoritative): `[v2.sampler_boundary]`-equivalent spans used by the harness waterfall (Sampling 5.230 s, VAE 0.427 s + load, Output encode 0.591 s, Remote handoff 1.851 s).

## Correctness (this run)

- **1 valid image produced**: `production_v2-bench_107_b_0.png` (output node 107) — non-empty execution, one normal graph execution (43+ nodes incl. ImpactSwitch, UNETLoader, ClownsharKSampler_Beta), no silent zero-output. **Correct image produced: YES.**
- Workflow hash binding: recomputed == plan hash (`hash_match=true`). No repair mutation (Gate 2 not triggered on legacy run). Sampling/VAE/output behavior within expected ranges for the legacy path; UNET remained absent from the CPU snapshot (gate above); native fast-disk UNET path active per manifest; conditioning-cache and output-delivery semantics unchanged (Agents 3/4 untouched).

## Why the gate declined (root-cause for the remaining parity gaps)

1. **snapshot_proof_incomplete/invalid** — the frozen `BootstrapState.snapshot_validation_proof` at snapshot creation is incomplete (`[v2.deployment_proof] complete=0`). Since `custom_nodes_generation_match=true`, the baked-generation component was fine; one of `registry_fingerprint` / `dependency_manifest_identity` / `generation_matches_observed` / deployment-hash was missing or mismatched at freeze time on the container. This is the unresolved **Step-2 live-parity question** (needs the `[v2.deployment_proof]` startup line on a clean snapshot).
2. **deployment_hash_match=false** — the host computes `deployment_combined_hash` from the **current local tree** at plan-build; the image was built minutes earlier from a tree that concurrent agents kept editing (benchmark_v2_direct.py 11:37, tests 11:39 local; continuous churn observed). Host hash ≠ frozen hash ⇒ correctly ineligible. This is the documented concurrent-edit hazard of the exact-match parity gate, not a mechanism fault.
3. **registry_fingerprint_match=false** — host registry (2403 classes incl. production outputs) vs container's frozen registry: the container imports from its volume-synced custom-node tree, which can differ from the local tree (pack versions/presence). Surface mismatch ⇒ correctly ineligible.
4. **dependency_proof_match=false** — follows from the above component drift.

## Step-4 readiness

**NO.** The mechanism is locally proven and the harness blockers are fixed (plan proof + complete identity verified in production), but the fast path was **not consumed** in production: the exact-match parity gate requires (a) a snapshot whose frozen proof is complete, (b) a host tree byte-identical to the deployed image at request time, and (c) host↔container registry-surface equality. None of the guards were weakened; the legacy fallback produced a correct image. Step-4 certificate cleanup remains unsafe until a run records `future_fast_path_eligible=1, plan_validation_consumed=1` with certificate/preflight/validate counts all zero.

## Completion output (final)

- exact report path: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\V2_GRAPH_CERT_SETUP_DECOMPOSITION.md`
- changed files (this retry): `tools/benchmark_v2_direct.py` (collect_validation_proof + comfyui_root at both call sites; `_COMFYUI_ROOT_DIR` sys.path insert; `_ensure_full_node_registry` with pinned `utils` pre-lock + PromptServer mirror + production-output class registration), `tests/test_benchmark_v2_proof_collection.py` (8 tests), `.modal_workspaces.json` (active workspace switched to testing4 `ws_f1a4990a74fd`)
- commit hash: `none` (concurrent dirty work prevents a safe commit)
- exact benchmark harness change: `collect_validation_proof=True, comfyui_root=_COMFYUI_ROOT_DIR` at both `build_execution_plan` call sites + server-mirror registry init (pinned `utils` pre-lock → `PromptServer` → `init_extra_nodes` → production-output registration) before plan build
- exact deployment command: `modal deploy -m comfymodal_runtime.modal_app --name stable-modal-comfy-v2-step3-accept` (via deploy_and_run_v2_single.bat, snapshot_restore_only/inherit, construction-only)
- acceptance app name: `stable-modal-comfy-v2-step3-accept`
- deployed image ID: `im-TVgb0ceq36ktk2S9z1o35Q`
- restored/serving image ID: `im-TVgb0ceq36ktk2S9z1o35Q`
- image identity matched: **YES**
- exact effective V2 manifest: full required list applied (inherit; CPU_MODEL_SNAPSHOT=1; VAE_SNAPSHOT=1; SNAPSHOT_EXCLUDE_UNET=1; EVICT_MODELS_BEFORE_SNAPSHOT=1; EVICT_RETAIN_ROLE=clip_vae; EVICT_RESTORE_IDLE_SECONDS=0; NATIVE_FAST_DISK_UNET=1; CLIP_CONDITIONING_CACHE=1; EXECUTION_UNET_H2D_DELAY_MS=0; UNET_ACTIVATION_MODE=late; VAE_ACTIVATION_MODE=sampling_end; PUBLISH_RESTORE_PLAN=0; SINGLE_USE_CONTAINERS=1; MINIMAL_GPU_TEARDOWN=1; RELEASE_GPU_AFTER_REQUEST=1; CPU_REQUEST=12; MEMORY_MB/MEMORY_REQUEST=32768; GPU=rtx-pro-6000; THREAD_POLICY=TBASE; SNAPSHOT_MODEL_ORDER=O0; VAE_POLICY=v1; CLOUD/REGION unpinned)
- snapshot CLIP/VAE/UNET presence: clip=1 vae=1 unet=0
- snapshot RSS: ≈13.0 GiB
- actual provider/region: CLOUD_PROVIDER_GCP / us-central1, us-east4, us-west1, us-south1 (unpinned)
- source_identity healthy: **NOT verified** (frozen proof incomplete on the serving snapshot — needs `[v2.deployment_proof]` startup-line inspection on a clean snapshot; code-verified non-degraded path only)
- deployment proof complete/valid: **false/false** (measured)
- full plan↔snapshot parity matrix: see matrix above (measured)
- workflow hash match: **1** (recomputed == plan hash)
- validation hash match: **1** (validated_workflow_hash == plan hash)
- future_fast_path_eligible: **0**
- plan_validation_consumed: **0**
- certificate RPC count: **1** (legacy)
- preflight execution count: **1** (legacy)
- remote validate_prompt count: **1** (legacy)
- certificate writeback count: **0 fast-path** (legacy-scheduled on this run)
- old graph_setup baseline: 460.5 ms (03-04-09)
- new graph_setup: **not measured on fast path** (3559.1 ms legacy-path this run)
- measured Step-3 application-wall saving: **none measurable** (fast path not consumed)
- application wall including restore: 45.4 s command→response (this run, legacy)
- command→response wall: 45.4 s
- correct image produced: **YES** (production_v2-bench_107_b_0.png)
- Step 3 production acceptance: **FAIL (gate declined — fail-safe; mechanism + harness verified, production parity not yet demonstrated)**
- Step 4 cleanup safe: **NO**
