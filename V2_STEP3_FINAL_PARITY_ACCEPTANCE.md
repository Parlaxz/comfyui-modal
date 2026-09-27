# Step-3 Final Parity Acceptance — Deployment Identity FIXED, Workflow-Relevant Registry Proof BLOCKED

**Date:** 2026-08-12
**Repo:** `comfyui-modal` (HEAD `e5483d5a7a5414fc9baae84d16e02c13bf270520`, branch `TESTING2`, working tree — `commit hash: none`)
**Campaign status: STOPPED** — Deployment hash + dependency-proof axes are **fixed and verified end-to-end**; the workflow-relevant registry proof **mechanism works exactly as designed (fail-closed, precise diagnostics)** but the canonical identity scheme has a path-independence bug for custom-node classes, and core ComfyUI files diverge between host and image. Per protocol: no more deployments, no patch-and-retry, report the exact remaining mismatch.
**Paid generation calls: 0** (the single validation/discard request was NOT spent — a local pre-check through the same code paths the gate uses proved deterministic `workflow_registry_match=0`, so spending it would burn the budget with zero information). Deploys: 1. Snapshot constructions: 1.

---

# Executive result

The three remaining Step-3 axes were repaired as follows:

| Axis | Before | After this task |
|---|---|---|
| deployment_hash_match | 0 (host mirror ≠ baked) | **1 — FIXED**: plan reads the actual baked hash persisted at deploy time via container readback; host mirror is diagnostic-only |
| dependency_proof_match | 0 (derived from wrong hash) | **1 — FIXED**: verified equal (`3d517d8270a90e27` both sides) |
| registry_fingerprint_match | 0 (full-registry equality) | replaced by **workflow-registry-match** mechanism; full fingerprint diagnostic-only. **Mechanism verified working; 39/41 workflow classes mismatch due to (a) absolute-path module component in the identity scheme, (b) host↔image core-file divergence.** |

The trust gate continues to fail closed (legacy fallback) — it was never weakened. The workflow-relevant proof correctly caught a REAL divergence the old full-fingerprint could not even express.

# Deployment-hash root cause (confirmed)

- The image-baked `_V2_DEPLOYMENT_COMBINED_HASH` (modal_app.py:16153-16180) is computed at module import from the **image-copied tree** (`custom_root` = `parents[1]` of the image's `comfymodal_runtime`), which contains only the V2 modules — a different file set than the local repo root the host mirror hashed. No host-side computation can reproduce it.
- The old `.deployed_state.json` writer (`__init__._save_deploy_state`) stored the host-mirror value and was never invoked by the V2 deploy flow.

# Actual baked identity propagation (implemented + verified)

```
DEPLOY (deploy_and_run_v2_single.bat)
  → modal deploy -m comfymodal_runtime.modal_app            (image bakes _V2_DEPLOYMENT_COMBINED_HASH)
  → python tools\record_deployment_identity.py               (NEW, both bat branches)
       → Modal method get_deployment_identity_static         (NEW, modal_app.py ~14134, O(1), no GPU work)
            returns {deployment_combined_hash, custom_nodes_generation,
                     comfyui_version, registry_manifest}
       → writes .deployed_state.json  (repo root; .json ⇒ OUTSIDE the hashed surface —
         deployment_spec.py ALLOWED_SOURCE_EXTENSIONS = {.py,.js,.mjs} ⇒ NO self-reference; also git-ignored + image-ignored)
  → plan build reads .deployed_state.json (canonical_execution.py chain:
    request_metadata → env COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH → .deployed_state.json → FAIL-CLOSED)
```

Verified locally on the live deployment:

```
snapshot baked deployment hash  = e7832134b30585c2774749717034113f19a874092a2fc50f3fd46ec92841c71f
                                  (construction [v2.deployment_proof] dep_hash=e7832134b30585c2 + container readback)
locally persisted deployed hash = e7832134b30585c2774749717034113f19a874092a2fc50f3fd46ec92841c71f   (source=container_readback)
plan-carried deployment hash    = e7832134b30585c2774749717034113f19a874092a2fc50f3fd46ec92841c71f   (source=persisted — executed _collect_plan_deployment_identity)
all equal: YES
host mirror hash (diagnostic)   = 8058f942589127c2…
host mirror in trust decision: NO  (complete=False when persisted identity absent; mirror never grants eligibility)
deployment_combined_hash_source = persisted
```

The host mirror (`_compute_host_deployment_combined_hash`) remains available only as the `host_mirror_deployment_combined_hash` diagnostic field and no longer participates in `complete`/eligibility. Absent persisted identity ⇒ `deployment_combined_hash=""` ⇒ plan identity incomplete ⇒ legacy fallback (fail closed, mandated scenario 3/5 tested).

# Dependency-proof result (follows deployment hash — confirmed)

All non-hash inputs already aligned (generation `995727c9…`, `repair_mode=fail_fast`). With the baked hash now carried:

```
plan dependency_manifest_identity      = 3d517d8270a90e27…   (build_identity(combined_hash=e7832134…, overall=<baked manifest>, gen=995727c9…, fail_fast))
snapshot frozen dependency identity    = 3d517d8270a90e27…   (construction [v2.dep_manifest] identity=3d517d8270a90e27 combined_hash=e7832134b30585c2 cn_gen=995727c9f0d1a496 repair_mode=fail_fast)
match: YES
```

No separate workaround was needed — the axis follows deployment identity exactly.

# Full-registry problem

`compute_registry_fingerprint` (name=module.qualname over the full class set, root-filtered) could never agree host↔container: the host cannot load every pack (SeedVR2/fill-nodes/sam3/lora-manager…) and the host `comfyui_root` handling differed. It is retained **diagnostic-only** (`registry_fingerprint_match` still reported, never an eligibility blocker).

# validate_prompt dependency analysis (proved)

Traced the parent ComfyUI `execution.validate_prompt` (execution.py:1106-1225) → `validate_inputs` (824-1098) call graph:
- All `NODE_CLASS_MAPPINGS` reads are keyed by the prompt's own `class_type` (execution.py:850, 912, 1125).
- Linked-input recursion is closed under the workflow's own nodes (911-933); type matching is pure string logic (comfy_execution/validation.py) — no foreign registry lookups.
- Registry surface per node that validation reads: registry entry, `INPUT_TYPES()`, `VALIDATE_INPUTS` (V1) / `validate_inputs`+`define_schema` (V3), `RETURN_TYPES` (linked nodes), `OUTPUT_NODE`, `INPUT_IS_LIST` (+ V3 `GET_BASE_CLASS`/`VALIDATE_CLASS`/`PREPARE_CLASS_CLONE`/`ACCEPT_ALL_INPUTS`), plus file-system inputs those classes' own `INPUT_TYPES()` read.
- **Conclusion (proven with line refs): for workflow W, validation outcomes are fully determined by the registry definitions of exactly W's class set (+ the file system those classes read + the static ComfyUI code).** Full-registry equality is therefore over-broad; a workflow-relevant proof is sound.

# Workflow-relevant registry proof design (implemented)

- `comfymodal_runtime/registry_proof.py` (new, pure): `class_canonical_identity` = `stable_hash({name, module, qualname, file_sha256})` (module-file content hash, path-independent **in intent**); `build_workflow_registry_proof` (plan side, workflow class set incl. production classes); `build_registry_manifest` (snapshot side, all registered classes, per-module file-hash dedupe); `evaluate_workflow_registry_parity` (per-class presence + identity equality, bounded lists); `format_registry_parity_line`.
- Snapshot: proof freeze adds `registry_manifest` (2412 classes) — frozen at construction.
- Plan: `registry_proof` + `registry_proof_complete` carried in `deployment_identity`.
- Gate: `evaluate_plan_snapshot_parity` requires `registry_proof_complete AND workflow_registry_match`; `[v2.plan_proof.registry]` diagnostics printed at request time; full fingerprint retained as `registry_fingerprint_match` (diagnostic).
- Fail-closed cases (all implemented + tested): missing host class, missing snapshot class, identity mismatch, malformed proof, empty class set, unavailable manifest.

# Trust-equivalence argument

The mechanism is sound: per-class canonical identity with module-file content hashing detects implementation differences (including code that only lives inside `INPUT_TYPES`/`VALIDATE_INPUTS` bodies) while ignoring absolute mount paths. **The production run exposed a defect in the identity SCHEME, not in the gate logic:**

1. **Absolute-path module component (dominant).** ComfyUI's custom-node loader registers classes whose `__module__` is the node's absolute import path: host `C:\…\custom_nodes\ComfyUI-CacheDiT.nodes` vs container `/root/comfy/ComfyUI/custom_nodes/ComfyUI-CacheDiT.nodes`. Hashing `cls.__module__` therefore embeds absolute paths — exactly what the task prohibited ("Avoid absolute paths") — so every custom-node class mismatches **by construction** regardless of identical file content. (ComfyModalProductionOutput matches — module `comfyapp`, no path — proving image copies are byte-identical and the scheme is correct for path-free modules.)
2. **Core-file divergence.** CLIPLoader (`module=nodes`, plain) mismatches under ALL local candidates (raw / LF-normalized / BOM-stripped). The container's ComfyUI core files are not byte-identical to local 0.24.0 content despite equal version strings — a genuine host↔image divergence the proof correctly refuses to bless.

# Gate-2 preservation

`apply_repair_invalidation` (contracts.py:765-774), the missing-node walk, and the repair-invalidation ordering (modal_app.py ~11907-11926) are untouched and regression-tested. `evaluate_plan_validation_consumption` unchanged.

# Implementation

| File | Change |
|---|---|
| `comfymodal_runtime/registry_proof.py` | NEW — canonical identity, workflow proof, snapshot manifest, parity evaluator, diagnostics |
| `comfymodal_runtime/contracts.py` | `evaluate_plan_snapshot_parity`: workflow_registry_match authoritative; registry_fingerprint_match diagnostic-only |
| `canonical_execution.py` | fail-closed identity chain (no mirror trust), `deployment_combined_hash_source`, `registry_proof` build, memo key on proof, workflow wiring |
| `comfymodal_runtime/modal_app.py` | `get_deployment_identity_static` method; proof freeze adds registry_manifest; gate prints `[v2.plan_proof.registry]`; parity event fields |
| `tools/record_deployment_identity.py` | NEW — deploy-time container readback → `.deployed_state.json` (fail-closed) |
| `deploy_and_run_v2_single.bat` | identity-record step after V2 deploy in both branches |
| `tools/benchmark_v2_direct.py` | `comfyapp` module stub in `_ensure_full_node_registry` (identity resolution for AST-registered production classes) |
| `tests/test_step3_final_parity.py` | NEW — 23 tests (18 mandated scenarios + path stability + cross-file) |
| `tests/test_deployment_proof.py`, `tests/test_step3_fast_path.py` | fixtures updated to workflow-relevant semantics; diagnostic-only fingerprint tests added |

# Local tests

`python -m pytest` on `test_step3_final_parity.py test_deployment_proof.py test_plan_validation_proof.py test_step3_fast_path.py test_benchmark_v2_proof_collection.py test_custom_node_generation_parity.py test_waterfall_reconciliation.py` → **136 passed, 0 failed**.

# Fresh deployment

- Deploy: `deploy_and_run_v2_single.bat` (publish → V2 deploy 115.2 s → identity readback). `[v2.volume_publish] status=ok remote_status=ok nodes=38`.
- Deployment images: `im-R49uZOH11sC7d2ieMq2ZIU` / `im-QXCTGi2OthTes9eChPr61v` / `im-YGa27azXs0wmHuCRHgFrsc`.
- Provider/region: GCP (unpinned; region not captured in this window — prior deployments us-east1/us-east4).
- Readback: `[v2.deploy_identity] status=ok deployment_combined_hash=e7832134b30585c2 custom_nodes_generation=995727c9f0d1a496 comfyui_version=0.24.0 manifest_classes=2412`.
- `.deployed_state.json` written (source=container_readback).

# Snapshot proof (construction gates — PASS)

```
[v2.custom_node_startup] decision=snapshot_exact_skip callback_called=0 source=persisted_record generation=995727c9f0d1a496
[v2.custom_node_generation_parity] baked_generation=995727c9f0d1a496fb2de3af9d08c4b5 persisted_generation=995727c9f0d1a496fb2de3af9d08c4b5 … sync_performed=0 sync_reason=exact_match baked_matches_persisted=1 …
[v2.deployment_proof] schema=1 complete=True reason=ok dep_hash=e7832134b30585c2 baked_gen=995727c9f0d1a496 gen_ok=1 reg_fp=True dep_identity=True repair_mode=n/a
[v2.dep_manifest] startup build/persist done in 1179.9ms identity=3d517d8270a90e27 combined_hash=e7832134b30585c2 cn_gen=995727c9f0d1a496 repair_mode=fail_fast baked_ok=1 ident_ok=1
[v2.snapshot_model_eviction] restore_observed … cpu_snapshot_models_present=1 clip_present=1 unet_present=0 rss_after_restore_mib=11378.82
```

CLIP=1 VAE=1 UNET=0, retain_role=clip_vae, RSS ≈11.4 GiB, generation parity `baked_matches_persisted=1 proof_generation_match=1`, deployment proof `complete=1 valid=1 gen_ok=1`.

# Validation/discard result — NOT RUN (pre-check proved deterministic failure)

Before spending the single allowed generation, a local pre-check ran the SAME code paths the container gate uses: host `build_workflow_registry_proof` over the workflow's 41 classes (39 source + 2 production) vs the container's frozen `registry_manifest` (fetched via the readback `--manifest-out`):

```
precheck_classes=41 complete=True missing_host=[] unresolved_identity=[]
manifest_classes=2412
workflow_registry_match=False reason=identity_mismatch
counts: wf=41 host_proved=41 snapshot_proved=41
missing_snapshot(0)=[]
identity_mismatch(39): Any Switch (rgthree), Anything Everywhere, CLIPLoader, CLIPTextEncode,
  CacheDiT_Model_Optimizer, ClownsharKSampler_Beta, CombineHooks8, ConditioningZeroOut, CustomCombo,
  EmptyImage, EmptySD3LatentImage, Image Comparer (rgthree), ImageRotate, ImpactIfNone, ImpactSwitch,
  JoinStrings, LGNoiseInjectionLatent, LayerUtility: PurgeVRAM V2, ModelPatchLoader, ModelSamplingAuraFlow, … (39)
```

This outcome is deterministic in the container gate (identical code, identical inputs) ⇒ `plan_validation_consumed=0` was certain; the request was withheld per the protocol's intent (do not burn the generation; report the exact remaining mismatch). Legacy path, graph setup, and waterfall metrics were therefore not exercised.

# Step-3 parity matrix (expected at request time)

```
plan_validation_payload   payload_present=1 validated=1 workflow_hash_match=1 plan_deployment_complete=1
snapshot_proof            present=1 complete=1 valid=1
deployment_hash_match     1   (verified: e7832134… == e7832134…)
custom_nodes_generation_match 1   (verified: 995727c9… both sides)
dependency_proof_match    1   (verified: 3d517d8270a90e27 both sides)
workflow_registry_match   0   (39/41 identity mismatches — root cause below)
future_fast_path_eligible 0
[v2.plan_proof]           decision=legacy_validation_fallback (expected) consumed=0
```

# Root cause of the remaining mismatch (exact)

1. **Identity scheme path bug (dominant, provable by construction).** `class_canonical_identity` hashes `cls.__module__`; for classes registered by ComfyUI's path-based custom-node loader this value is an ABSOLUTE PATH — host `C:\Users\…\custom_nodes\ComfyUI-CacheDiT.nodes` vs container `/root/comfy/ComfyUI/custom_nodes/ComfyUI-CacheDiT.nodes` (verified live from the host registry). All 24+ custom-node classes mismatch regardless of identical file bytes. The task explicitly required path-independence; the module component must be derived path-independently (e.g., module file path RELATIVE to the known roots, or module basename).
2. **Host↔image core-file divergence.** CLIPLoader/CLIPTextEncode/EmptySD3LatentImage/… (module `nodes`, plain) do not reproduce the container composite under raw/LF/BOM-normalized candidates ⇒ the image's ComfyUI core files differ in content from local 0.24.0 despite equal version strings. The proof correctly refuses to bless a validation environment that differs from the snapshot. Repair requires aligning the host validation tree with the image (pin the image's ComfyUI commit to the local `f49bdb6`/0.24.0 or sync the local tree to the image content).

# Remaining blockers

1. Make `class_canonical_identity` path-independent (fix the module component) — resolves all custom-node mismatches; file content is already byte-identical (proven: `comfyapp` classes match; custom-node generation equal).
2. Align host ComfyUI core files with the image (or pin the image build) — required for core classes.
3. Then one fresh deployment + one validation/discard generation (next task's budget) to prove `consumed=1`.

# Whether A/B campaign may resume

**No.** Two deterministic, precisely-scoped repairs remain (path-independent module identity + core-tree alignment); both are gate-strengthening fixes, not weakenings, and require a fresh deploy.

---

# STEP 3 PRODUCTION NOT ACCEPTED
# A/B CAMPAIGN REMAINS BLOCKED
