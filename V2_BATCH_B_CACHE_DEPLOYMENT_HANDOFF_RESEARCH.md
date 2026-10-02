# V2 Batch B — Cache Deployment-Handoff Research

**Lane:** READ-ONLY research. No production source modified. No deploys. No Modal runs.
**Date:** 2026-08-14
**Scope:** ExactConditioningCache and PromptSignatureCache behavior across the authoritative baseline deployment (`b557b2401f293223` lineage) and the Batch-A fresh deployment (`25a4e5aceed3756c…`).
**Follow-up:** Resolves the custom-node-generation contradiction in §16 (original) — see §18–20.

---

## 1. Executive result

Both cache misses on the Batch-A fresh deployment are **cache-identity rotation**, not semantic invalidation:

- The **ExactConditioningCache** canonical key includes `deployment_hash` and `custom_node_generation` as required components. Between the authoritative deployment and the Batch-A deployment, `deployment_combined_hash` rotated `b557b2401f293223 → 25a4e5aceed3756c…` and `custom_nodes_generation` rotated `ff3a26d75ca51ece → 15e92eb38c68a51bb5015cf88f887af7`. Everything semantics-relevant (workflow hash, CLIP/model identity, schema, options) is unchanged or unproven-changed. The stored entries from the baseline remain on the same named Volume (persistence is deployment-agnostic), but no stored entry can match the new canonical key → `decision=miss_stored` → CLIP re-encode (5.241 s observed) + first-request cost.
- The **PromptSignatureCache** identity hash is `stable_hash({workflow_hash, source_workflow_hash, deployment_combined_hash, custom_node_generation, registry_proof_hash, schema_version})`. The two rotated fields (`deployment_combined_hash`, `custom_node_generation`) are both in that set → a new `identity_hash` → the persisted memo entries (keyed by old identity hash on the runtime-state volume) are unreachable → cold signature computation (~1.6 s observed).
- Root cause classification: **C (unrelated deployment identity changed) as primary driver; D (custom-node generation rotated without demonstrated relevant-semantic change) as contributing driver.** Causes A (semantic change), B (conditioning-relevant code change — no evidence), E (persistence failure — no), F (snapshot lacking volume contents — no) are ruled out by the traced code and artifacts.
- The broad `deployment_hash` is a **conservative hammer, not a correctness requirement**: it is `stable_hash` over *all* deployable source file hashes + runtime shape, so *any* source change anywhere (telemetry, harness, studio lanes) rotates it. Every correctness-critical axis already has a dedicated, narrower key component.
- Both deployments ran from the **same git commit** (`a6a755e`), with a dirty working tree. No commit separated them; the identity delta comes from working-tree content churn that was unrelated to conditioning semantics.
- **Follow-up conclusion (§18–20):** the original §16 recommendation kept `custom_node_generation` in both identities — which, per the key formulas and the observed rotation, would have **preserved both misses**. `custom_node_generation` is an MD5 over *every* syncable custom-node directory's `.py/.txt/.toml/.cfg` content — including `comfyui-modal`'s own repo — so any unrelated `.py` edit rotates it. `model_generation` is additionally a **minted UUID** (`comfyapp.py:1786`), a second false-invalidation source. The resolved design (§16v2, §19) removes all three rotating tokens and replaces node-code coverage with a **transitive-import-closure code hash** + the existing **requirements-context hash**, both baked at deploy/construction time; the counterfactual in §20 shows the proposed identities **HIT** the authoritative → Batch-A transition while remaining fail-closed for every correctness-required invalidator.

---

## 2. Conditioning-cache architecture

Module: `comfymodal_runtime\clip_conditioning_cache.py` (2678 lines). Consumers: `comfymodal_runtime\model_preload.py`, `comfymodal_runtime\modal_app.py`.

| Aspect | Fact | Source |
|---|---|---|
| Persistent storage | `/root/prompt_cache_vol/exact_conditioning` — flat, **deployment-hash-free path**; `entries/<key_hash>.header.json` + `entries/<key_hash>.data.bin` + `manifest.json` | `clip_conditioning_cache.py:58-83, 825-826, 1047-1051` |
| Volume | Named Modal Volume `comfymodal-prompt-encoding-cache`, mounted at `/root/prompt_cache_vol` at container start (`Volume.from_name(..., create_if_missing=True)`) | `modal_app.py:283-284, 3412-3420`; `comfyapp.py:6547` |
| Manifest | JSON: `{schema_version, format_version, next_seq, entries:[{key_hash, byte_length, last_access_seq, created_at}]}`; only `schema_version` gates read (mismatch → treated empty) | `clip_conditioning_cache.py:1012-1045, 2321-2326` |
| Payload | Explicit serialization (no pickle/torch.save): header JSON + raw little-endian bytes; bf16 stored as int16 view; per-tensor `{dtype, shape, offset, byte_length, checksum}` with sha256; header stamped with `key_hash`, `key_components`, `model_identity` block, `created_at` | `clip_conditioning_cache.py:7-27, 437-441, 497-587, 2572-2602` |
| In-memory | `_mem_manifest` + `_mem_payloads` keyed by digest; mtime/size staleness checks; invalidated on self-store/commit | `clip_conditioning_cache.py:908-914, 1138-1164, 1286-1290` |
| Prefetch | Plan-time `maybe_prefetch_conditioning` (daemon thread) → `prefetch_entries` → throttled volume reload; no deployment gate at load; correctness enforced at demand time | `model_preload.py:15830, 15948`; `clip_conditioning_cache.py:1082-1118, 1175-1401` |
| Demand validation | `_validate_entry_bytes`: `format`/`schema_version`/`format_version`/`key_hash` equality → **full canonical `key_components` equality** → `model_identity` block equality → byte length → deserialize with per-tensor checksums. Every mismatch = miss (fail closed) | `clip_conditioning_cache.py:1623-1690` |
| Lookup entry | `lookup_many` → `_lookup_entry_maybe_mem` → `_lookup_entry`; `miss_insufficient_identity` when required fields empty; `miss_stored` when key valid but no entry matches | `clip_conditioning_cache.py:1446-1621` |
| Versions | `SCHEMA_VERSION = 1`, `FORMAT_VERSION = 1`, `FORMAT_NAME = "comfymodal_exact_clip_conditioning"` | `clip_conditioning_cache.py:79-81` |
| Eviction | Deterministic LRU by `last_access_seq`, caps 64 entries / 512 MB; `_remove_unindexed_files` | `clip_conditioning_cache.py:84-85, 1053-1078, 2039-2071` |
| Restore interplay | GPU snapshot restore (`gpu_snapshot_shadow.py`) restores in-memory models; the prompt-cache Volume is a persistent named volume mounted per container — **not** copied per deployment and not part of the CPU/GPU snapshot. Old entries stay physically visible forever | `modal_app.py:3418-3420, 5208, 17272-17274` |

Key architectural fact: **cross-deployment isolation is enforced solely by key components, not by storage location.** The volume path contains no deployment identity. Therefore "old entries exist but are unreachable" is the expected post-deploy state when any key component rotates.

---

## 3. Conditioning cache key formula

`build_exact_key_components` (`clip_conditioning_cache.py:259-298`), digest at `:301-303`:

```python
components = {
    "schema_version": 1, "format_version": 1,
    "clip_identity": ...,          # CLIP loader filename (e.g. qwen_3_4b.safetensors)
    "clip_type": ...,              # e.g. lumina2
    "loader_class": ...,           # CLIPLoader / DualCLIPLoader
    "filenames": [...],            # loader filenames
    "weight_dtype": ..., "compute_dtype": ...,
    "torch_version": ..., "torch_num_threads": ...,
    "model_generation": ...,       # models-volume generation token
    "tokenizer_identity": ...,     # stable_hash of {class, options, name_or_path, vocab_size, model_max_length}
    "workflow_hash": ...,          # canonical sha256 of whole workflow JSON
    "deployment_hash": ...,        # ← REQUIRED; = _V2_DEPLOYMENT_COMBINED_HASH (see below)
    "custom_node_generation": ..., # ← REQUIRED; baked deploy-time generation token
    "production_options_hash": ...,# stable_hash of execution_options.to_dict()
    "entry": {"node_class", "role", "prompt_input", "text",
              "conditioning_inputs", "adapter_chain", "layer", "skip"},
}
digest = sha256(_canonical_json(components))   # sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False
```

Multi-entry (whole-plan) digest: `sha256(_canonical_json(sorted(per-entry digests)))` (`:326-328`). Demand-time eligibility = exact digest equality of the stored `key_components` vs. the current request's components (`_validate_entry_bytes`, `:1658-1690`). Any component difference → miss.

**Origin of `deployment_hash`** (`modal_app.py:17543-17551`, `contracts.py:1183-1190`, `deployment_spec.py:232-283`):

```python
_V2_DEPLOYMENT_COMBINED_HASH = stable_hash({
    "source_combined_hash": DeploymentIdentity.combined_hash,   # stable_hash({schema_version, runtime_hash,
                                                                 #   dependency_hash, custom_node_hash,
                                                                 #   file_hashes: sha256 of EVERY allowed source file})
    "runtime_shape": runtime_shape_config().identity_payload(),
})
```

So `deployment_hash` rotates whenever **any** deployable `.py/.js/.mjs` file changes (all of `comfymodal_runtime/` + custom-node paths, minus `.modalignore` exclusions), even if nothing conditioning-relevant changed.

**Origin of `custom_node_generation`** — see §18 (follow-up). Summary: MD5 over canonical JSON of per-node content hashes of `.py/.txt/.toml/.cfg` files across **all** syncable custom-node dirs **including `comfyui-modal` itself** (`comfyapp.py:3683-3749`). Baked at deploy time (`modal_app.py:8355`); runtime source `model_preload.py:15287-15291`. Rotates on any unrelated `.py` edit in any node directory.

---

## 4. Signature-cache architecture

Module: `comfymodal_runtime\prompt_signature_cache.py` (570 lines). Executor patch: `runtime_executor.py:3381-3432`; identity stash: `modal_app.py:13327-13333`; early load: `modal_app.py:16075-16079`.

| Aspect | Fact | Source |
|---|---|---|
| Storage | `/mnt/comfymodal_runtime_state/prompt_signature_memo.json` on the `comfymodal-runtime-config` Volume (`RUNTIME_STATE_PATH`, `modal_app.py:268, 3069`); file `{schema_version: 1, entries: {identity_hash: {nodes: {node_id: {class_type, is_changed, signature, inputs_hash}}, topo_lazy...}}}` | `prompt_signature_cache.py:36, 246-279, 310`; `modal_app.py:265` |
| Keying | `identity_hash` (see §5); per-node revalidation by `class_type` + `canonical_inputs_hash(inputs)` + `is_changed` equality; a memo hit applies only after **every** node verifies | `prompt_signature_cache.py:227-243, 498-570` |
| Enable gate | `COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE` default **True** (unset → enabled) | `runtime_executor.py:2411-2424` |
| Identity gate | `_memo_plan_from_state` requires stashed identity and `memo_identity(...)["complete"]` (all three strong components non-empty); else bypass with `missing_identity`/`incomplete_identity` | `runtime_executor.py:2427-2467` |
| Fail-safe | Any gate failure or per-node mismatch → original `add_keys` computation (correctness never weakened) | `runtime_executor.py:3418` |

---

## 5. Signature key formula

`memo_identity` (`prompt_signature_cache.py:76-109`):

```python
identity = {
    "workflow_hash": ...,            # plan.workflow_hash (canonical whole-workflow sha256)
    "source_workflow_hash": ...,     # plan.source_workflow_hash (defaults to workflow_hash)
    "deployment_combined_hash": ..., # plan.deployment_identity["deployment_combined_hash"] == _V2_DEPLOYMENT_COMBINED_HASH
    "custom_node_generation": ...,   # plan.deployment_identity["custom_nodes_generation"] (baked generation)
    "registry_proof_hash": stable_hash(registry_proof or {}),  # per-class {class_name, logical_module_path,
                                                               # qualname, module_file_sha256} over the workflow's class set
    "schema_version": 1,
}
identity_hash = stable_hash(identity)      # sha256 of canonical JSON
complete = bool(workflow_hash and deployment_combined_hash and custom_node_generation)
```

Sources: `workflow_hash`/`source_workflow_hash` — `modal_app.py:13328-13329`, `contracts.py:839-841`, `production_workflow.py:31-42`, `comfyapp.py:2683-2703`. `deployment_combined_hash` — `modal_app.py:13330, 17543-17551`. `custom_node_generation` — `modal_app.py:13331`, `canonical_execution.py:1157-1160` (baked manifest). `registry_proof` — `modal_app.py:13332`, `registry_proof.py:233-293` (LF-normalized module file sha256, path-independent logical paths; `complete` fails closed on any missing/mismatched class).

---

## 6. Identity delta — authoritative deployment → Batch-A deployment

Both deployments: same app `stable-modal-comfy-v2-restore-only-shadow`, same git commit `a6a755e` (no commit between; heavily dirty working tree), ComfyUI 0.24.0 (`f49bdb655707b979`, core_match=1), same model stack (`qwen_3_4b.safetensors` lumina2 CLIP / `z_image_turbo_bf16.safetensors` UNET / `ae.safetensors` VAE), same benchmark workflow (43 nodes, 3 loaders, 1 sampler — `V2_BATCH_A_INTEGRATED_ACCEPTANCE.md:231`).

| Field | Authoritative (baseline) | Batch-A | Changed? |
|---|---|---|---|
| deployment_combined_hash | `b557b2401f293223…` (`V2_10_COLD_RUNS_35S_COOLDOWN.md:3`, `v2_c2f_deploy_5.log:427`) | `25a4e5aceed3756cbe37b51af1f1af0041b98cea1f846006045e220ac4339386` (`.deployed_state.json:8`, acceptance :75) | **YES** |
| custom_nodes_generation | `ff3a26d75ca51ece` (`v2_c2f_deploy_5.log:427`, `V2_PRODUCTION_DEFAULTS_2026-08-13.md:13`) | `15e92eb38c68a51bb5015cf88f887af7` (`.deployed_state.json:6`, `.baked_custom_node_deps/custom_node_deps_baked.json:401`) | **YES** |
| workflow_hash | `2e43d4c0ba3b82c0` (`v2_c2f_10cold_35gap.log:228`, all 10 runs) | same workflow (acceptance :231) | NO |
| source_workflow_hash | not recorded locally | not recorded locally (defaults to workflow_hash) | UNKNOWN (likely NO) |
| registry_proof_hash | not recorded locally | not recorded locally | UNKNOWN (see §20: derivable EQUAL) |
| cache schema/format | conditioning 1/1; seed schema 2 | conditioning 1/1 (`.deployed_state.json:11`) | NO |
| model identity / CLIP identity | qwen_3_4b / lumina2 (v2_restore_plan.json) | same (acceptance) | NO |
| model_generation | not recorded | `d9da6b7226a1` (acceptance :162; "seeded" at construction :80) | UNKNOWN — **minted UUID, see §18** |
| requirements_context_hash | `b604c14479dc289b…` (228 files / 22 dirs) | identical (`.deploy_log`, `.last_custom_node_context_manifest.json`) | **NO** |
| cache volume | `comfymodal-prompt-encoding-cache` | same volume name (mount gated on cache flags) | NO |
| Modal image | lineage images; final not recorded | `im-pR3OcGwn4FsUEg96RFq5PG` (acceptance :76) | n/a (image id not in cache identity) |

Independent corroboration of systemic rotation: every deploy in the baseline lineage rotated `custom_nodes_generation` (`8f98568b2f0b64d6`, `9159548c202778c2`, `b636acdc5dfc7b79`, `c20de18bd2b4165d`, `b557b2401f293223` — `V2_CACHED_FIRST_NODE…:338`, deploy logs) — the generation is regenerated from the dirty tree on each deploy. The custom-node **requirements context hash** was identical in both deploy records (`b604c14479dc289b…` in both `.deploy_log` and `.last_custom_node_context_manifest.json`), i.e. the *requirements context did not change* while the *generation token* did — evidence the rotation is not driven by dependency changes.

---

## 7. Exact miss cause — conditioning

Mechanism chain (verified in code + artifacts):

1. Baseline deployment wrote entries under key components with `deployment_hash = b557b2401f293223…`, `custom_node_generation = ff3a26d75ca51ece` → exact hits on all 10 cold runs (`[v2.conditioning_exact_hit_breakdown] decision=exact_hit manifest_memory_hit=1 miss_count=0 payload_memory_hit=1`, `v2_c2f_10cold_35gap.log:303-304`).
2. Batch-A container computes demand-time components with `deployment_hash = 25a4e5aceed3756c…` and `custom_node_generation = 15e92eb38c68a51bb5015cf88f887af7` (`model_preload.py:15287-15296`).
3. `exact_key_digest(components)` differs from every stored entry's `key_hash`/`key_components`; `_validate_entry_bytes` full canonical-equality fails → `decision=miss_stored`, `identity_status=valid` (key complete but unmatched) → CLIP re-encode.
4. Observed: `decision=miss_stored` with `encode_calls=1`; Batch-A RUN 1 `CLIP encode (1 calls) 5.241s` (`V2_BATCH_A_INTEGRATED_ACCEPTANCE.md:245, 256-260`). Same mechanism lines in earlier lineage: `app_logs_agents34.txt:17`, `deploy3_full_search.log:566` (`miss_stored`, `identity_status=valid`, encode 3.4–7.1 s).
5. Not a persistence failure: the volume is the same named volume, the storage path is deployment-agnostic, and the mount happens at container start regardless of deploy (`modal_app.py:3418-3420`). Old entries remain on disk; they are simply unreachable under the new key. Cause E/F excluded.

**Miss driver: at least two key components rotated (`deployment_hash`, `custom_node_generation`) while every semantics-bearing component (workflow_hash, clip identity block, tokenizer identity, model identity, options hash, schema) was unchanged or unproven-changed. A third component (`model_generation`, a minted UUID) may also have rotated — see §18.**

---

## 8. Exact miss cause — signature

Mechanism chain:

1. Baseline runs stored memo entries keyed by `identity_hash` built from `deployment_combined_hash = b557b2401f293223…`, `custom_node_generation = ff3a26d75ca51ece` → `signature_cache_hit=True`, `signature_cache_source=volume`, `signature_reuse_ms=3.49` on all 10 runs (`v2_c2f_10cold_35gap.log:303`).
2. Batch-A request builds `memo_identity` with the rotated values → **new `identity_hash`** (`stable_hash` covers all six fields; rotation of two is sufficient to change it).
3. Memo file is keyed by `identity_hash`; the old entries are unreachable → cold signature computation (~1.6 s observed; acceptance :256-260, 268-269). Even though the memo *file* persisted on the runtime-state volume, the identity-level key rotation invalidates the whole entry set.
4. Not an identity-completeness failure: `complete=True` (workflow_hash present and unchanged); the miss is a genuine key-mismatch on rotated deployment-identity fields.

---

## 9. Correctness-required invalidators (v2 — after §18–20)

Must invalidate conditioning/signature reuse when any of these change. Component names refer to the final identities in §19.

| Axis | Conditioning (compat_conditioning_v2) | Signature (compat_signature_v2) |
|---|---|---|
| CLIP model/checkpoint | `clip_identity`, `clip_type`, `loader_class`, `filenames`, `weight_dtype` | `relevant_code_hash` (CLIP loader class module + closure), `workflow_hash` |
| Model weights/bytes | `model_content_identity` (content-derived; **replaces minted `model_generation`**) | — (weights do not affect signatures) |
| Tokenizer | `tokenizer_identity` (content hash of live tokenizer config) | `relevant_code_hash` (tokenizer-construction code in closure) |
| Node defining-module code | `relevant_code_hash` (closure includes defining modules) | `registry_proof_hash` (per-class single-module sha256) + `relevant_code_hash` |
| Helper/base modules (no node class) | `relevant_code_hash` (**transitive import closure**) | `relevant_code_hash` (same closure) |
| Prompt content | `workflow_hash`, `source_workflow_hash`, entry `node_class`/`role`/`text`/`conditioning_inputs`/`adapter_chain`/`layer`/`skip` | `workflow_hash`, `source_workflow_hash` |
| Conditioning parameters/options | `production_options_hash`, entry fields | (covered by `workflow_hash`) |
| dtype/layout | `compute_dtype`, `weight_dtype`, `torch_version`, `torch_num_threads` | (schema/format version) |
| Cache schema/format | `schema_version` (2), `format_version` (1) | `schema_version` (2) |
| Dependency/requirements state | `requirements_context_hash` | `requirements_context_hash` |
| Signature consumer code (executor interpretation, memo application) | n/a (cache's own machinery is versioned by schema) | `signature_consumer_hash` |
| Node registry / class resolution | `relevant_code_hash` (closure root = workflow class modules) | `registry_proof_hash` (fail-closed on missing class) |

## 10. Over-broad invalidators (v2 — resolved)

| Component | Why over-broad | Verdict |
|---|---|---|
| `deployment_hash` / `deployment_combined_hash` (conditioning + signature) | Covers **every** deployable source file (`.py/.js/.mjs`) + runtime shape; rotates on studio/browser/history `.js`, harness, tests, telemetry — nothing conditioning-related. Proven rotation between same-commit deploys. Every correctness axis has a dedicated component (§9). | **Remove** from both identities |
| `custom_node_generation` (conditioning + signature) | MD5 over **all** syncable custom-node dirs' `.py/.txt/.toml/.cfg` content **including `comfyui-modal`'s own repo** (`comfyapp.py:3683-3749`); rotates on any unrelated `.py` edit (harness tools, runtime instrumentation) while requirements context (`b604c144…`) stays identical; rotates on every deploy in the lineage. Proven false invalidator for this transition. | **Remove** from both identities |
| `model_generation` (conditioning key + models-reload guard) | **Minted UUID** (`comfyapp.py:1786`: `uuid.uuid4().hex`), written at construction when the record is missing (`:18635-18641`, `reason=initialize_generation_record`); **not content-derived**; can rotate with zero model-byte changes (fresh volume, record deletion, re-init). Batch-A "seeded" its record at construction (acceptance :80) — a probable third rotating component in this very miss (baseline value unrecorded). | **Remove**; replace with `model_content_identity` (§19) |
| `registry_proof_hash` used *alone* (signature) | Hashes exactly **one file per class** — the class's defining module (`registry_proof.py:53-78, 118-153`). Helper modules, deferred imports, data files, imported libraries: **blind** (proven, §18 Part 3). | Keep in signature identity but **not as sole node-code guard** — superseded by `relevant_code_hash` closure |

Latent gap found: the requirements-context hash (`b604c144…`) is **not currently part of `DeploymentIdentity.combined_hash`** — `dependency_hash` is passed as `""` in production calls (`deployment_spec.py:245-247`, `modal_app.py:3385`, host mirror `canonical_execution.py:1022-1025`). Dependency changes today are only caught by the over-broad generation/deployment hashes. The v2 identities close this gap by adding `requirements_context_hash` explicitly.

---

## 11. Cross-deployment compatibility model (v2)

Design goal: safely answer *"can conditioning/signature results generated by deployment X be reused by deployment Y?"*

Rules (unchanged in spirit):

- **MUST invalidate:** any change to a §9 axis — each via its dedicated component. Node code coverage requires **defining modules AND their transitive local import closure** (`relevant_code_hash`), because the per-class registry proof alone is helper-blind (§18 Part 3).
- **MAY NOT need to invalidate:** unrelated backend code (output handling, host telemetry, waterfall changes, loader scheduling), frontend `.js`/studio/browser/history lanes, docs, tests (pruned dirs), other custom-node directories not reachable from the workflow's class modules, and — once `model_generation` is replaced — model-volume *publish events* that do not change model bytes. All are excluded because no v2 component depends on them.
- **Fail closed:** any missing/incomplete component (empty `relevant_code_hash`, empty `requirements_context_hash`, empty `model_content_identity`, missing entry fields) → treat as unusable, recompute. Never reuse on partial identity.
- **Aliasing:** if `compat_conditioning_v2(X) == compat_conditioning_v2(Y)` then entries written under X's identity may be reused by Y. This holds across the authoritative → Batch-A transition (§20).

The final field sets are specified exactly in §19.

---

## 12. Candidate designs (v2 — evidence-based evaluation)

| # | Strategy | What changes invalidate it | What does NOT invalidate it | Helper modules covered? | Deterministic/stable | Construction cost | Request cost | Implementation complexity | Fail-closed? | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| A | Remove `custom_node_generation` entirely; rely on `registry_proof_hash` + dedicated fields | defining-module edits, workflow, tokenizer, model, options, schema | helper edits, data files, deps | **NO** (proof is single-file per class — proven) | Yes | None (proof exists) | ~20–35 small file reads/request (proof, uncached) | Low | No — helper changes fail open (stale reuse) | **REJECT** — helper-blind |
| B | Extend code identity to **transitive import closure** of the workflow's node modules (`relevant_code_hash`) | any change to defining modules or any local module they import (helpers, bases, package `__init__` chains) | other node dirs, `.js`, docs, tests, unrelated repo files not in closure | **YES** | Yes (content-only, LF-normalized; baked at deploy) | Deploy/construction-time bake (host walk + AST import resolution) | Near-zero (read baked value; no new request-path scan) | Medium-high (import graph resolution; relative/lazy imports; treat unresolvable → fail-closed) | **Yes** — incomplete closure ⇒ empty hash ⇒ miss | **ADOPT (core)** |
| C | Hash complete package/dir trees of only the packages providing workflow classes | any file in those packages (incl. unrelated studio/playground `.py` inside `comfyui-modal`) | packages not used by the workflow | Yes (dir-wide) | Yes | Deploy-time walk | Zero (baked) | Medium | Yes (dir-wide) | **REJECT** — still over-broad within used packages; `comfyui-modal` itself provides workflow-adjacent classes |
| D | Separate conditioning-relevant and signature-relevant curated code hashes | changes in curated file sets | anything not curated | **Partial** — only if curated correctly (fragile, omission risk) | Yes | High (manual curation + maintenance) | Zero | High (curation correctness is the risk) | Yes only if set complete — hard to guarantee | **REJECT** — fragile curation |
| E | `requirements_context_hash` + registry proof | dependency/requirements drift (incl. `-r/-c/-e` refs, wheels, local trees) | source helper edits within repos | **NO** (dependency files only) | Yes — hash already computed at deploy (`b604c144…`) | Zero (already computed; currently **not** in identity — latent gap) | Zero (baked) | Low | Yes for deps only | **ADOPT (complement to B)** |
| F | Keep `custom_node_generation`; accept no cross-deploy reuse | any `.py/.txt/.toml/.cfg` edit in any node dir incl. `comfyui-modal` itself | `.js`, tests, docs | Yes (over-broad) | Yes (content-derived, but MD5 + whole-tree scope) | Zero | Zero | None | Never wrong reuse — but every deploy misses on unrelated churn | **REJECT** — the observed failure mode |

**Recommended combination: B + E** — `relevant_code_hash` (transitive closure, baked at deploy/construction) + `requirements_context_hash` (already computed at deploy, now promoted into the identity). This is the narrowest identity that covers real semantic changes (defining modules, helpers, dependencies) without invalidating on unrelated project churn.

---

## 13. Expected first-request impact

- **Today (strategy F):** every fresh deployment pays ≈ **5.2 s CLIP re-encode + ≈1.6 s signature recompute** on the first request (Batch-A RUN 1 observed; encode loop walls of 3.4–7.1 s in other lineages). Additional container-side cost: manifest reload + potential re-store.
- **With v2 identities (B+E):** first request after an unrelated-churn deploy behaves like the authoritative baseline: `decision=exact_hit`, `lookup=34–95 ms`, `cached→first 0.5–1.1 ms`, `signature_cache_hit=True` — i.e. **≈5.2 s CLIP + ≈1.6 s signature saved on the first request after deploy**, at zero deploy-time cost (bake is a host-side hash walk, not a GPU run).
- **With warm-seed (strategy 4, optional):** same saving, moved to deploy time (one warm generation) and paid once per deploy.
- Distinction kept explicit per the brief: this is a **first-request-after-deploy improvement**, not a steady-state cold-request optimization. It does not change Batch-A RUN 1's total wall attribution (host variance remains the dominant factor there).

## 14. Steady-state impact

None for all strategies. Both caches are exact-hit in steady state (10/10 baseline; restore-to-restore reuse is already deployment-internal). The change only affects the transition window between deployments. No memory, latency, or eviction behavior changes.

---

## 15. Risks (v2)

1. **`registry_proof` byte-equality across the two deploys is still unrecorded** (never persisted locally). Equality is derivable (§20: same commit, same class set, defining modules = ComfyUI core, unchanged) but not byte-proven. **Gate:** record `registry_proof_hash`, `relevant_code_hash`, `requirements_context_hash`, `model_content_identity` in the deploy-identity artifact from the first v2 deploy onward.
2. **Plan-time vs demand-time tokenizer identity.** Plan-time `tokenizer_identity` is a structural approximation (`model_preload.py:15436-15455`) while demand-time uses the live tokenizer (`:15057-15072`); if they ever diverge, prefetch keys under a different key than lookup. Mitigation: prefetch under the demand-time context; keep `tokenizer_identity` in the compatibility identity.
3. **`model_generation` is a minted UUID — resolved by replacement.** It is not content-stable (`comfyapp.py:1786`) and may have contributed to this very miss. The v2 identity must ship with `model_content_identity` (content hash of model files at publish/construction, stored in the models record). Until implemented, **do not** rely on the current token as a stable model guard (it is used by the models-reload guard too — `runtime_bootstrap.py:1492-1537`; that guard's `skipped_generation_match` semantics need the same content identity).
4. **Stale-reuse window in aliasing designs (strategies 3/5/6).** Any alias must be byte-equality on the compatibility identity; a soft/approximate match must never alias. Fail closed on any missing field.
5. **`custom_node_generation` as "coarse backstop" — removed.** Its only unique value (helper coverage) is now provided deterministically by `relevant_code_hash`. Residual closure risk: dynamic/lazy imports (`importlib`-style, `getattr`-gated) and data files (M3) remain outside a static AST closure — mitigation: package `__init__` chains included, unresolvable imports ⇒ mark identity incomplete ⇒ miss (fail closed). Data-file semantics changes (rare) are explicitly out of scope for both caches and were never covered by any request-time component.
6. **Memo file growth / cross-app sharing.** Memo file on `comfymodal-runtime-config` volume is keyed by identity_hash only; unrelated app names sharing the volume would accumulate entries. Not a correctness issue (identity isolation), but a hygiene risk if volumes are ever shared.
7. **Closure bake determinism.** The bake must use content-only, LF-normalized per-file sha256 (existing primitives: `registry_proof._resolve_file_sha256`, `deployment_spec.compute_file_hashes`, `comfyapp._compute_deterministic_context_hash`) — no mtimes, no git state, no timestamps. Same commit + same tree ⇒ same hash, independent of host.
8. **Schema bump migration.** `SCHEMA_VERSION 1→2` orphans all v1 entries by design (manifest schema gate → empty cache → clean cold re-warm on first request). Expected and fail-closed; do not attempt in-place migration of v1 payloads.

---

## 16. Recommended implementation (v2 — contradiction resolved)

**Recommended: Strategies B + E (§12)** — narrow v2 identities per §19, baked at deploy/construction time, behind a versioned key schema. **`custom_node_generation` is removed from both identities; `deployment_hash`/`deployment_combined_hash` removed; minted `model_generation` replaced by content identity.**

### Conditioning (`compat_conditioning_v2`)
- **remove =** `deployment_hash`, `custom_node_generation`, minted `model_generation`
- **add =** `relevant_code_hash` (transitive closure), `requirements_context_hash`, `model_content_identity`
- **retain =** `schema_version` (bump), `format_version`, `clip_identity`, `clip_type`, `loader_class`, `filenames`, `weight_dtype`, `compute_dtype`, `torch_version`, `torch_num_threads`, `tokenizer_identity`, `workflow_hash`, `source_workflow_hash`, `production_options_hash`, entry `{node_class, role, prompt_input, text, conditioning_inputs, adapter_chain, layer, skip}`
- **schema bump =** `SCHEMA_VERSION` 1 → 2 (`FORMAT_VERSION` stays 1 — payload format unchanged); old v1 entries fail the manifest schema gate → clean cold start, re-warmed by the first request
- **failure behavior =** any empty/missing component ⇒ `miss` (fail closed); emit `key_component_delta=<which field rotated>` on every miss for auditability

### Signature (`compat_signature_v2`)
- **remove =** `deployment_combined_hash`, `custom_node_generation`
- **add =** `signature_consumer_hash`, `relevant_code_hash`, `requirements_context_hash`
- **retain =** `workflow_hash`, `source_workflow_hash`, `registry_proof_hash`, `schema_version` (bump)
- **schema bump =** `SCHEMA_VERSION` 1 → 2 (memo file `schema_version` gate)
- **failure behavior =** `complete` gate requires all strong components non-empty (else bypass memo — fail closed); per-node `class_type`/`inputs_hash`/`is_changed` revalidation unchanged; any per-node mismatch → original `add_keys` computation

### Cheapest relevant-code hash computation (no new request-path scans)
- **Deploy/construction-time bake on the host** (which holds the full tree): compute the transitive import closure of the workflow's node-class modules resolved within `{repo root, custom-node roots, ComfyUI core root}`; per-file LF-normalized sha256 via existing primitives (`registry_proof._resolve_file_sha256`, `deployment_spec.compute_file_hashes`); `relevant_code_hash = stable_hash(sorted[{logical_path, sha256}])`.
- Bake `{relevant_code_hash, requirements_context_hash (existing `b604c144…`-style value), model_content_identity, signature_consumer_hash}` into the deployment identity / baked manifest alongside `production_custom_node_generation` (which can then be dropped from runtime consumers).
- Request path: read baked values only. **No multi-file scan is introduced on the request path.** Construction-time bake cost: one extra host walk over already-walked source trees (sub-second to seconds, no GPU, no Modal run).
- `signature_consumer_hash = stable_hash([sha256(prompt_signature_cache.py), sha256(runtime_executor.py signature-application block), sha256(comfy_execution/caching.py), comfyui_commit])` — covers INPUT_TYPES/IS_CHANGED consumption and memo application without the whole-tree `file_hashes`.

Stop conditions and success criteria in §17; final identities in §19; counterfactual proof in §20.

## 17. Stop conditions (v2 — status: all evaluated)

| # | Condition | Status |
|---|---|---|
| 1 | Helper-module semantic changes must be coverable **without** the rotating whole-tree generation | **SATISFIED** — `relevant_code_hash` transitive closure (B) covers helpers deterministically; `custom_node_generation` is removed (§18 Part 2/3, §19) |
| 2 | Relevant-code identity must be deterministic | **SATISFIED** — content-only LF-normalized hashes, baked at deploy, no mtimes/git/timestamps (§15.7) |
| 3 | Proposed identity must **not** change across the actual same-semantics deploy transition | **SATISFIED** — §20: all v2 components equal across authoritative → Batch-A; proposed identities HIT |
| 4 | `model_generation` false invalidator: stable model-content identity must exist | **FOUND FALSE INVALIDATOR** (minted UUID, `comfyapp.py:1786`); replacement specified — `model_content_identity` (content hash at publish/construction). **Must ship with the change; otherwise NOT READY** |
| 5 | No heuristic/approximate matching | **SATISFIED** — all equality exact (byte-level canonical components) |

Implementation gates (unchanged in spirit):
- **Do not implement** unless (a) key component deltas are logged on miss, and (b) the four new hashes (`registry_proof_hash`, `relevant_code_hash`, `requirements_context_hash`, `model_content_identity`) are recorded in the deploy-identity artifact — otherwise the narrow key cannot be audited and §15.1 is unverifiable.
- **Do not alias across deployments** (strategies 3/5/6) before the v2 identity is in production and observed for ≥1 deploy with a logged component-delta audit.
- **Do not weaken** the signature memo gates: `complete` must remain required; per-node `class_type`/`inputs_hash`/`is_changed` revalidation must remain.
- **Stop** if any post-deploy run shows `identity_status=invalid` (a required field is empty in the deployed container) — that is a deployment-spec bug, not a cache design issue.
- **Stop** if a genuine conditioning-semantic change ever produces a cache *hit* — that indicates a missing dedicated component (e.g. closure gap) and the narrow-key design must be reverted to the conservative superset.

---

## 18. Custom-node generation contradiction resolution

### 18.1 Counterfactual — original §16 as written

Original §16 kept `custom_node_generation` in both identities. Actual values: baseline `ff3a26d75ca51ece`, Batch-A `15e92eb38c68a51bb5015cf88f887af7` — **rotated**.

- **Conditioning (original §16: remove `deployment_hash`, add `registry_proof_hash`, KEEP `custom_node_generation`):** `build_exact_key_components` still contains `custom_node_generation` (`clip_conditioning_cache.py:284`). The Batch-A value ≠ baseline value ⇒ canonical JSON differs ⇒ digest differs ⇒ `_validate_entry_bytes` fails ⇒ `decision=miss_stored` ⇒ CLIP re-encode. **Result: MISS preserved.** Changed component: `custom_node_generation`.
- **Signature (original §16: replace `deployment_combined_hash` with `signature_consumer_hash`, KEEP `custom_node_generation`):** `memo_identity` still contains `custom_node_generation` (`prompt_signature_cache.py:96`). It is a strong component of `identity` ⇒ `identity_hash` differs ⇒ memo entries keyed under the baseline `identity_hash` are unreachable ⇒ cold recompute. **Result: MISS preserved.** Changed component: `custom_node_generation`.

**Conclusion: the original recommendation retained the exact field the evidence identified as a rotating false invalidator — the recommendation was internally contradictory and is superseded by §16v2/§19.**

### 18.2 Derivation of `custom_node_generation` (proven from code)

Two functions in `comfyapp.py`:

1. `custom_node_source_fingerprint(source_root)` (`comfyapp.py:3683-3729`):
   - Walks **every syncable top-level dir** of the custom_nodes root (`_iter_syncable_custom_node_dirs`, `:6820-6837`; rejects hidden dirs, `.git/__pycache__/node_modules/.venv/...`, worktree clones, duplicate comfyui-modal copies) — **`comfyui-modal` itself is included** (canonical name passes the filter, `:6667-6668`).
   - Hashes only **`.py/.txt/.toml/.cfg`** (+ named `requirements.txt/pyproject.toml/setup.py/setup.cfg`); **`.js/.mjs/.json/.md/.ipynb` excluded** (frontend/browser JS and `.model_manifest.json` never enter).
   - Prunes generated dirs (`tests`, `examples`, `benchmarks`, `logs`, `scripts`, `.github`, `build`, `dist`, `.custom_node_requirements`, `.baked_custom_node_deps`, …; `:3662-3676`), suffixes `.log/.tmp/.trace/.jsonl/.whl`, prefixes `benchmark_`/`trace_` (`:3677-3680`).
   - Per node: `sha256` over `f"{rel_path}:".encode() + _canonical_dependency_bytes(file)` — **file content, LF-normalized** (`:3888-3893`); no mtimes, no git, no timestamps.
2. `custom_node_source_generation(source_root)` (`comfyapp.py:3732-3749`): `md5(json.dumps({name: {content_hash, is_dir, ...}}, sort_keys=True))`.

Persisted: baked manifest `production_custom_node_generation` (host, `:8154-8156`) and volume record `custom_nodes_generation.json` (in-container recompute `:8566-8574`; `generation=None → uuid4().hex` fallback only on compute exception `:1860`).

### 18.3 What it protects — coverage matrix

| Generation input class | In generation? | Already covered by (v2 identity)? |
|---|---|---|
| Node defining-module `.py` (workflow classes) | Yes | `registry_proof_hash` (single file/class) + `relevant_code_hash` (closure) |
| **Helper/base modules (no node class)** | Yes | **NO — only `relevant_code_hash` closure** (registry proof is blind to them, §18.4) |
| Requirements/dependency files in tree | Yes (files as `.txt/.toml/.cfg`) | `requirements_context_hash` (dedicated, already computed) |
| `comfyui-modal`'s own repo `.py` (runtime, harness, tools) | **Yes** | NO — irrelevant to conditioning/signature semantics; this is the false-invalidation driver |
| Other node dirs not used by the workflow | **Yes** | NO — irrelevant |
| Frontend `.js/.mjs`, `.json`, `.md`, `.ipynb` | **No** | n/a (also excluded from `deployment_hash`? No — `.js/.mjs` ARE in `deployment_hash` `file_hashes`) |
| tests/, logs/, benchmarks/ (pruned) | **No** | n/a |
| Model weights / tokenizer data | **No** | `model_content_identity` / `tokenizer_identity` |

**Why it rotates on same-commit dirty-tree deploys (proven):** any `.py` edit inside `comfyui-modal` itself or any node dir rotates the per-node `content_hash` ⇒ the MD5. Between deploy_5 and Batch-A the fingerprint-visible delta was the Batch-A lanes' files: `tools/batch_a_acceptance.py` (new — `tools/` is **not** pruned), `tools/benchmark_v2_direct.py` (M), `comfymodal_runtime/runtime_bootstrap.py` (models reload guard), `modal_app.py` (G1 stamps), `runtime_executor.py` + `v2_waterfall.py` (per-node timeline), `unet_backing.py` (telemetry) — none of which touch CLIP/conditioning semantics. Meanwhile the requirements context hash stayed byte-identical (`b604c144…`, 228 files / 22 dirs) and the workflow/node set was unchanged. Generation rotation on every lineage deploy (`8f98568b…`, `9159548c…`, `b636acdc…`, `c20de18b…`, `b557b240…`) confirms the pattern.

### 18.4 Registry-proof coverage gap (proven)

`registry_proof.py`:
- Class→module resolution: `sys.modules[cls.__module__].__file__` only (`:53-78`); no importlib/inspect/dir walk.
- `module_file_sha256`: hashes **exactly one file** — the class's defining module — LF-normalized (`:118-153`).
- **`helpers/bar.py` change while `nodes/foo.py` unchanged ⇒ `registry_proof_hash` UNCHANGED (proven — only `foo.py`'s content enters the digest).** Re-exported classes hash the *defining* module (`__init__.py` edits are blind); deferred (function-scope) imports are blind; data/config files are blind; modules imported *by* the node (comfy core internals, `comfymodal_runtime`, pip packages) are blind. Only classes *defined in* a file are covered when that file changes.

Realistic uncovered gaps for:
- **A. Conditioning tensor generation:** helper code in the CLIP-text-encode/tokenizer-construction path; adapter/LoRA helper modules; any non-defining-file code that changes conditioning outputs.
- **B. PromptSignatureCache:** `INPUT_TYPES` semantics / `IS_CHANGED` / topology-affecting code in helper or base modules (identity gate blind; partial mitigation only at memo-application via per-node `inputs_hash`/`is_changed` revalidation); signature-application code (`comfy_execution/caching.py`).

⇒ `registry_proof_hash` alone is insufficient; the closure hash (`relevant_code_hash`) is required (§19).

---

## 19. Final compatibility identities

### `compat_conditioning_v2` (exact key-component field set)

```python
{
    "schema_version": 2,                       # bumped from 1 (clean orphan of v1 entries)
    "format_version": 1,
    "clip_identity": ..., "clip_type": ..., "loader_class": ..., "filenames": [...],
    "weight_dtype": ..., "compute_dtype": ...,
    "torch_version": ..., "torch_num_threads": ...,
    "tokenizer_identity": ...,                 # content identity of live tokenizer
    "model_content_identity": ...,             # NEW: stable_hash(sorted[{model_path, sha256(bytes)}]) at publish/construction;
                                               #   replaces minted model_generation
    "workflow_hash": ..., "source_workflow_hash": ...,
    "relevant_code_hash": ...,                 # NEW: stable_hash(sorted[{logical_path, sha256(LF-normalized)}])
                                               #   over transitive import closure of workflow class modules
    "requirements_context_hash": ...,          # NEW: existing deterministic context hash (b604c144…-style)
    "production_options_hash": ...,
    "entry": {"node_class", "role", "prompt_input", "text",
              "conditioning_inputs", "adapter_chain", "layer", "skip"},
}
# REMOVED: deployment_hash, custom_node_generation, minted model_generation
```

### `compat_signature_v2` (exact memo-identity field set)

```python
identity = {
    "workflow_hash": ...,
    "source_workflow_hash": ...,
    "registry_proof_hash": ...,                # retained (per-class single-module sha256, fail-closed on missing class)
    "relevant_code_hash": ...,                 # NEW: closure hash (superset of registry proof — covers helpers/bases)
    "requirements_context_hash": ...,          # NEW: dependency/requirements state
    "signature_consumer_hash": ...,            # NEW: stable_hash([sha256(prompt_signature_cache.py),
                                               #   sha256(runtime_executor.py signature-application block),
                                               #   sha256(comfy_execution/caching.py), comfyui_commit])
    "schema_version": 2,
}
identity_hash = stable_hash(identity)
complete = bool(workflow_hash and relevant_code_hash and requirements_context_hash and signature_consumer_hash)
# REMOVED: deployment_combined_hash, custom_node_generation
# unchanged: per-node class_type/inputs_hash/is_changed revalidation at memo application
```

### New-hash definitions (computation sites)

| Hash | Computed where | Primitive | Determinism |
|---|---|---|---|
| `relevant_code_hash` | deploy/construction-time host bake (AST import resolution over the host tree; closure roots = workflow class modules, resolved within repo + custom-node + ComfyUI roots; package `__init__` chains included; unresolvable imports ⇒ mark incomplete ⇒ fail-closed) | `registry_proof._resolve_file_sha256` / `deployment_spec.compute_file_hashes` (LF-normalized content) | Yes — content only, sorted, canonical JSON |
| `requirements_context_hash` | already computed at deploy (`comfyapp.py:7129-7179`; value `b604c144…`) — promote into identity | `_compute_deterministic_context_hash` | Yes |
| `model_content_identity` | publish/construction-time over the models tree (hash each model file once per publish; store in models record replacing the UUID) | sha256 over file bytes, sorted by logical path | Yes |
| `signature_consumer_hash` | deploy-time bake over the three consumer modules + core commit | sha256, LF-normalized | Yes |

Request path reads baked values only — **no new request-path multi-file scan** (§16).

---

## 20. Counterfactual — authoritative deployment → Batch-A key result

| OLD COMPONENT (baseline value) | NEW COMPONENT (Batch-A value) | EQUAL? |
|---|---|---|
| workflow (workflow_hash `2e43d4c0ba3b82c0`) | same workflow (43 nodes, unchanged; acceptance :231) | **YES** |
| model bytes (qwen_3_4b / z_image_turbo_bf16 / ae.safetensors) | same files (model stack unchanged) | **YES** (content identity equal; minted token UNKNOWN — baseline unrecorded) |
| tokenizer (same ComfyUI commit `f49bdb655707b979`) | same | **YES** |
| registry / relevant code (same commit `a6a755e`, same class set; defining modules = ComfyUI core `nodes.py`, unchanged) | same; changed `.py` files (tools/, comfymodal_runtime/) are **not** in the workflow class-module import closure | **YES** (derivable; byte-proof requires the new bake records — §15.1) |
| options (unchanged) | unchanged | **YES** |
| schema (1) | 1 (pre-bump) | **YES** |
| requirements context (`b604c14479dc289b…`) | identical | **YES** |
| broad deployment hash (`b557b2401f293223…`) | `25a4e5aceed3756c…` | **NO — removed from v2 identity** |
| custom node generation (`ff3a26d75ca51ece`) | `15e92eb38c68a51bb5015cf88f887af7` | **NO — removed from v2 identity** |

Result matrix:

| Identity | Result |
|---|---|
| CURRENT conditioning key (deployment_hash + custom_node_generation + minted model_generation) | **MISS** (observed) |
| CURRENT signature identity (deployment_combined_hash + custom_node_generation) | **MISS** (observed) |
| PROPOSED `compat_conditioning_v2` | **HIT** — every retained/new component byte-equal across the transition; no component depends on the two rotated tokens |
| PROPOSED `compat_signature_v2` | **HIT** — workflow/source-workflow/registry-proof/closure/consumer/requirements/schema all equal; rotated tokens removed |

The proposed identities no longer miss on unrelated deployment churn. Semantic invalidation remains fail-closed: any genuine change to model bytes, tokenizer, workflow, options, node code (defining modules *or* helpers), dependencies, consumer code, or schema rotates exactly the corresponding v2 component and produces a miss (§9, §19).

---

## Completion output

```
report path = V2_BATCH_B_CACHE_DEPLOYMENT_HANDOFF_RESEARCH.md
source files changed = none
deploy count = 0
Modal runs = 0

keeping current custom_node_generation would preserve the observed miss = YES
  (counterfactual §18.1: original §16 kept it in both identities; it rotated
   ff3a26d75ca51ece → 15e92eb38c68a51bb5015cf88f887af7 ⇒ conditioning key
   digest differs ⇒ miss_stored; signature identity_hash differs ⇒ memo miss)
registry_proof covers helper modules = NO
  (proven: single defining-module file per class only; helpers/bar.py change
   with unchanged nodes/foo.py ⇒ registry_proof_hash unchanged)
narrow relevant-code replacement found = YES
replacement = relevant_code_hash (transitive import closure of workflow
  class modules, content-hashed LF-normalized, baked at deploy/construction)
  + requirements_context_hash (existing b604c144…-style, promoted into
  identity) + model_content_identity (content-derived model hash replacing
  the minted UUID)
model_generation content-stable = NO
  (uuid.uuid4().hex minted at construction, comfyapp.py:1786; can rotate
   with zero model-byte changes; Batch-A record "seeded" at construction)

proposed conditioning identity would hit authoritative -> Batch-A = YES
  (§20: all compat_conditioning_v2 components byte-equal; the two rotated
   tokens are removed from the identity)
proposed signature identity would hit authoritative -> Batch-A = YES
  (§20: workflow, registry proof, closure, consumer, requirements, schema
   all equal; rotated tokens removed)

conditioning semantic invalidation remains fail-closed = YES
signature semantic invalidation remains fail-closed = YES

final implementation strategy =
  conditioning: remove = deployment_hash, custom_node_generation, minted
    model_generation; add = relevant_code_hash, requirements_context_hash,
    model_content_identity; retain = schema_version (bump 1→2), format,
    clip identity block, tokenizer_identity, workflow/source_workflow,
    production_options_hash, entry fields; failure = any missing component
    ⇒ miss with key_component_delta logging
  signature: remove = deployment_combined_hash, custom_node_generation;
    add = signature_consumer_hash, relevant_code_hash,
    requirements_context_hash; retain = workflow/source_workflow,
    registry_proof_hash, schema (bump 1→2); failure = complete gate +
    per-node revalidation, any gap ⇒ bypass memo (fail closed)
  computation: deploy/construction-time host bake of all new hashes using
    existing primitives; request path reads baked values only (no new
    request-path multi-file scan)
implementation ready = YES
  (gates: §17 — component-delta logging, deploy-identity recording of the
   four hashes, content-derived model identity must ship with the change)
research ready to close = YES
```
