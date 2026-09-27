# Step-3 Last Two Blockers — Both Content Blockers FIXED; Plan-Transport Gap Remains

**Date:** 2026-08-12
**Repo:** `comfyui-modal` (HEAD `e5483d5a7a5414fc9baae84d16e02c13bf270520`, branch `TESTING2`, working tree — `commit hash: none`)
**Campaign status: STOPPED** — The two deterministic content blockers (path-dependent class identity; host↔image ComfyUI core divergence) are **fixed and verified live**. The single allowed validation/discard generation ran; it produced correct output with axes 1–2 green, but Step-3 still did not consume the fast path because the plan's `registry_proof` **arrived empty in the container** (`plan_registry_proof_unavailable`) — a plan-transport gap in the persistent local-handle IPC path, not an identity mismatch. Per protocol: no second request, no second deployment, no patch-and-retry; exact mismatch reported.
**Paid generation calls: 1** (the single sanctioned validation/discard). Deploys: 1. Snapshot constructions: 1.

---

# Executive result

| Blocker | Status |
|---|---|
| Path-dependent class identity (absolute `__module__` for path-loaded nodes) | **FIXED** — path-independent logical module identity; verified live: 41/41 identities match the container manifest, 0 mismatches |
| Host↔image ComfyUI core divergence (comfy-cli nightly master vs local v0.24.0 tag) | **FIXED** — image pinned to `f49bdb6…`; verified live: `comfyui_core_match=1` |
| Step-3 production acceptance | **NOT YET** — new plan-transport gap: `registry_proof` dropped in the persistent-IPC handle path (exact diagnosis below) |

# Path-dependent identity root cause

`class_canonical_identity` hashed `cls.__module__`, which for ComfyUI path-loaded custom nodes is an absolute path: host `C:\…\custom_nodes\ComfyUI-CacheDiT.nodes` vs container `/root/comfy/ComfyUI/custom_nodes/ComfyUI-CacheDiT.nodes`. Identical source mismatched purely by root (24+ classes by construction).

# Canonical logical module identity (implemented)

```
class_canonical_identity(cls, roots) = stable_hash({
    "class_name": cls.__name__,
    "logical_module_path": shortest os.path.relpath(abspath(module_file), root) across roots
                           [comfyui_root, repo_root]  (abspath, NOT realpath; "/"-normalized),
    "qualname": cls.__qualname__,
    "module_file_sha256": sha256(LF-normalized module file bytes),   # EOL-insensitive (Python
})                                                                    # compile behavior identical
```
- Absolute paths NEVER participate (verified: `test_drive_letter_not_in_identity`, `test_path_separator_normalization`).
- Root sets symmetric: host `canonical_execution._collect_plan_deployment_identity` → `[comfyui_root, repo_root]`; container `modal_app._registry_manifest_roots()` → `[repo_root, comfyui_root, comfyapp-file dir]` (comfyapp-dir covers the image's `/root/comfyapp.py` placement). `custom_nodes_dir` deliberately excluded (asymmetric shortest-path).
- Unknown/unresolvable root → identity `""` → `registry_proof_complete=0` → legacy fallback (never guessed; test 7).
- File content hash stays authoritative; LF normalization is behaviorally exact (Python normalizes newlines at compile time) and consistent with the custom-node generation fingerprint convention.

# Path-stability proof

- Tests (tests/test_step3_path_identity.py, 10 scenarios): Windows vs Linux roots equal; different absolute roots equal; changed bytes differ; qualname differ; logical module differ; core `nodes.py` under different roots equal; unknown root → incomplete; separator normalization; drive-letter never in identity; symlink-vs-direct equal (abspath semantics).
- Live verification: local precheck vs the fresh container manifest — **41/41 identities match, 0 mismatches** (previously 39/41).

# Host ComfyUI core provenance (verified)

| Item | Value |
|---|---|
| version | 0.24.0 (`comfyui_version.py`) |
| exact commit | `f49bdb655707b97952dcef40e12e5af1f08d2007` — upstream `v0.24.0` tag (lightweight tag == HEAD, detached; remote `Comfy-Org/ComfyUI`; clean tree; upstream author/PR history) |
| `nodes.py` SHA-256 | raw CRLF `1c32bce5…`; committed/LF-normalized `0812066ec17e89826835a95b081f3ae89f9f585bb05472fa8dc86c3e14fdc446` |
| `execution.py` SHA-256 | raw CRLF `07c73707…`; committed/LF-normalized `fb4d90801bba2828b161a7d14ff1cb51426124cbe1698da1d8cd94f7afe1e0ea` |
| working-tree drift | none (pure CRLF↔LF transform of committed blobs; `git diff HEAD` empty; autocrlf=true) |

# Image ComfyUI core provenance (root cause identified)

| Item | Value |
|---|---|
| reported version | 0.24.0 |
| installation | `comfy --skip-prompt install --nvidia`, comfy-cli **1.3.7** (comfyapp.py:7780) |
| comfy-cli default | **`version="nightly"`** → plain `git clone` of master, **no tag checkout** (verified in comfy-cli 1.3.7 source) |
| consequence | image core = unpinned master snapshot frozen in a cached layer; the `0.24.0` string spanned **7 master commits** (2026-06-03 16:42Z → 06-04 18:07Z), only the first (`f49bdb6…`) is the true tag → core content differed from the local checkout despite equal version strings (confirmed: container `nodes.py` composite unmatched by raw/LF/BOM candidates and by committed-tag content) |
| post-install core edits | none (no build step touches `nodes.py`/`execution.py`/`comfy_extras`) |

# Exact core divergence

Version strings equal; **content differs because the image ran a non-tag master snapshot**. This is a real correctness mismatch (the host validated against v0.24.0 while the container executed newer code) and was correctly refused by the proof.

# Authoritative core source decision

**Current local ComfyUI checkout (`f49bdb6`, upstream v0.24.0 tag) → deployment image.** The local checkout is a pristine upstream tag; the image's master snapshot was an artifact of comfy-cli's nightly default.

# Core alignment implementation

- `comfyapp.py:7746-7752` — `_COMFYUI_PINNED_COMMIT = "f49bdb655707b97952dcef40e12e5af1f08d2007"` (constant near `SAGEATTENTION_GIT_REF`; layer-hash-sensitive).
- `comfyapp.py:7791-7798` — new build step immediately after the comfy-cli install (before the torch reinstall):
  `git -C /root/comfy/ComfyUI fetch --depth=1 origin <sha> && git -C /root/comfy/ComfyUI checkout --force <sha> && git -C /root/comfy/ComfyUI log -1 --format='pinned=%H'`
- Diagnostics: `get_deployment_identity_static` now returns `comfyui_commit` + `core_module_sha256s` (LF); `tools/record_deployment_identity.py` prints `host_comfyui_identity=` / `deployed_comfyui_identity=` / `comfyui_core_match=` and persists them in `.deployed_state.json` (diagnostic only — not a gate).
- Live result after rebuild (715 s): `host_comfyui_identity=f49bdb655707b979 deployed_comfyui_identity=f49bdb655707b979 comfyui_core_match=1`.

# Workflow registry precheck (local, against live container manifest)

```
workflow_class_count = 41
host_proved_count    = 41
snapshot_proved_count= 41
missing_host         = []
missing_snapshot     = []
identity_mismatch    = []
workflow_registry_match = 1
```

Both blockers eliminated at the content level — the mechanism now proves exact per-class identity for all 41 workflow classes.

# Local verification

`tests/test_step3_path_identity.py` (15) + `tests/test_step3_final_parity.py` (23) + `test_deployment_proof.py` (21) + `test_plan_validation_proof.py` (12) + `test_step3_fast_path.py` (27) + `test_benchmark_v2_proof_collection.py` (8) + `test_custom_node_generation_parity.py` (22) + `test_waterfall_reconciliation.py` (23) → **151 passed, 0 failed**. Compile OK.

# Fresh deployment

- `[v2.volume_publish] status=ok remote_status=ok nodes=38`; V2 deploy 715.2 s (image layers rebuilt due to the pin); deployment images `im-EvBhElwF0GXOjCU2yJ4oCf`, `im-BOzg1EfbT4WkWkUbFPkLQx`, `im-musGnZXTxXb34j90Umauyz`, `im-VM4orZCCjAHgLM24hmxLKP`, `im-UK69NUe3ZltFFO6wiPc5jE`, `im-IvGuT4XBQRtkTpFfZdURVf`.
- Construction container (readback): snapshot identity `im-lWGANbjndWCr0HKiiOMNZa|003ce20e6e4f42e2836bbf08fbf1aa0c`; provider GCP (unpinned); validation request ran on **AWS eu-central-1** (placement not pinned).
- Readback: `[v2.deploy_identity] status=ok deployment_combined_hash=2f1dc2b7f5c0d42c custom_nodes_generation=e54f0670730bad2c comfyui_version=0.24.0 manifest_classes=2399` + core match=1.

# Snapshot gates — PASS

```
[v2.custom_node_generation_parity] baked_generation=e54f0670730bad2c6c8ed5bfab7e39c3 persisted_generation=…sync_performed=0 sync_reason=exact_match baked_matches_persisted=1 … proof_generation_match=1
[v2.dep_manifest] startup build/persist done in 1080.0ms identity=d30a658261c5f3a8 combined_hash=2f1dc2b7f5c0d42c cn_gen=e54f0670730bad2c repair_mode=fail_fast baked_ok=1 ident_ok=1
[v2.deployment_proof] schema=1 complete=True reason=ok dep_hash=2f1dc2b7f5c0d42c baked_gen=e54f0670730bad2c gen_ok=1 reg_fp=True dep_identity=True repair_mode=n/a
snapshot: clip_present=1 unet_present=0 retain_role=clip_vae rss_after_restore_mib=11318.84 (≈11.0 GiB)
```

Deployment identity: baked == persisted == plan-carried (`2f1dc2b7f5c0d42c…`, source=persisted). Dependency proof: `d30a658261c5f3a8` both sides → match. Generation: `e54f0670730bad2c` both sides → match.

# Registry manifest readback

`tools/record_deployment_identity.py --manifest-out` → 2399-class manifest (schema 1); local precheck above consumed it.

# Validation/discard result — RUN, consumed=0 (plan-transport gap)

The single sanctioned request ran (`run_role=validation_discard retained=0 discard_reason=first_post_snapshot_run`; request `v2-benchmark-0-2321be2e79d4`; AWS eu-central-1):

```
[v2.plan_proof] parity proof_present=1 proof_complete=1 proof_valid=1 dep_match=1 gen_match=1
                wf_reg_match=0 reg_full_match=0 dep_proof_match=1 eligible=0 reason=workflow_registry_mismatch consumed=False
[v2.plan_proof.registry] workflow_class_count=0 host_proved_count=0 snapshot_proved_count=0
                         missing_host=0 missing_snapshot=0 identity_mismatch=0
                         workflow_registry_match=0 reason=plan_registry_proof_unavailable
[v2.plan_proof] decision=legacy_validation_fallback consumed=0 reason=workflow_registry_mismatch
```

- **Correct output: YES** — 1 output descriptor, 2,874,640 bytes, `sha256:895deda2…`.
- **Step-3 matrix**: `payload_present=1 validated=1 hash_match=1`; `snapshot_proof present/complete/valid=1`; `deployment_hash_match=1`; `custom_nodes_generation_match=1`; `dependency_proof_match=1`; `registry_fingerprint_match=0` (diagnostic-only, expected); **`workflow_registry_match=0`**; `future_fast_path_eligible=0`.
- **RPC bypass counts**: NOT achieved — legacy path executed (certificate read + preflight + remote validate_prompt + cert writeback; `cert_decision=legacy`). Fast-path `certificate_ms/preflight_ms/validation_ms ≈ 0` not applicable.
- **Graph setup**: legacy-path value only (fast-path graph_setup not exercised).
- **Waterfall**: final host-reconciled `reconciliation_status=OK`, residual **1.248 ms**; `TOTAL WALL 46 475.08 ms`; `Scheduling 72 573.11 ms` (informational, no %/bar — unchanged); `COMMAND→RESPONSE 119 048.19 ms`.

# Exact remaining mismatch (plan-transport gap)

The container received `plan.deployment_identity` with **all pre-existing fields intact** (`complete=True`, `deployment_combined_hash`, `custom_nodes_generation`, `dependency_manifest_identity` — all matched) but **`registry_proof` empty**, yielding `plan_registry_proof_unavailable`. Proven faithful (local experiment through the real code): `build_execution_plan` → `plan.to_dict()` → `ExecutionPlan.from_dict` → JSON round-trip **all preserve `registry_proof`** (39–41 identities, complete=True). The container entry wrapper (`run_plan_stream` → `_run_plan_stream_impl` → `_safe_payload` → `from_dict`) is also faithful.

The run used the **persistent local-handle IPC path** (`[v2.local_handle] decision=persistent_hit`; `COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE=1`): `local_handle_client.run_plan_stream` ships `{"op":"run_plan_stream", "payload": dict(payload), …}` via `_write_json` to the local owner over `127.0.0.1` with `IPC_STREAM_LIMIT`. The **owner-side forwarding of the op** (how the payload reaches the Modal method) is the single unverified link and the only place consistent with "old fields survive, new key dropped" — a schema/allowlist or size-limit filter in the owner's forwarding that predates the `registry_proof` key. The direct Modal path (`remote_gen.aio(plan_dict, …)`) uses standard Modal serialization and is the obvious candidate to confirm the fix.

# Remaining blockers

1. **Plan-transport of `registry_proof` via the persistent-IPC handle path** (exact diagnosis above). Repair candidates for the next task (not executed here — frozen tree, hard-stop): (a) make the persistent owner forward the plan payload wholesale (or add `registry_proof` to any field allowlist); (b) verify/raise `IPC_STREAM_LIMIT` for payload size; (c) candidate workaround: `COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE=0` → direct Modal serialization. Then re-run the registry precheck and one validation/discard generation.
2. Nothing else — deployment identity, dependency proof, generation parity, path-independent identity, and core parity are all verified green.

# A/B campaign readiness

**Not yet** — one transport fix + one fresh validation/discard generation remain. All content-level parity is proven; the gate continues to fail closed correctly.

---

# STEP 3 PRODUCTION NOT ACCEPTED
# A/B CAMPAIGN REMAINS BLOCKED
