# V2 Custom-Node Generation Parity Fix

**Date:** 2026-08-12
**Repo:** `comfyui-modal` custom node (HEAD `e5483d5a7a5414fc9baae84d16e02c13bf270520`, branch `TESTING2`)
**Campaign status: A/B CAMPAIGN MAY RESUME** — root cause proven, repair implemented, 54 local tests green, one validation deployment + snapshot construction performed, `[v2.deployment_proof] complete=True gen_ok=1 generation_matches_observed=1` frozen in the new snapshot. No generation requests, no A/B requests, no Step-3 generation acceptance run.

---

# Executive root cause

The V2 deployment-proof failure (`complete=0 reason=generation_mismatch`) was **not** a stale-record, stale-volume, or proof-timing problem. It was an **algorithm/provenance mismatch** between the two content-derived generation computations:

1. **IMAGE-BAKED** = `custom_node_source_generation(local tree)` at image build.
2. **PERSISTED (volume)** = `custom_node_source_generation(extracted volume tree)` after the deploy-time archive sync.

The archive builder (`_build_custom_nodes_archive`, `__init__.py:3121-3156`) excludes directories via `_CUSTOM_NODE_SYNC_EXCLUDE_DIRS` (`__init__.py:909-916`) — including `.comfymodal_experiments`, `.custom_node_requirements`, `.baked_custom_node_deps`, `benchmark_runs`, `benchmark_logs`, `optimization_logs`, `output`, `test-results`, `playwright-report`, `.playwright-mcp`, `.experiments`, `.run_history`, `.presets`, `.preset_blobs` — while the fingerprint walk (`custom_node_source_fingerprint`, `comfyapp.py:3624-3670`) pruned only the smaller `_CUSTOM_NODE_GENERATED_DIRS` set (`comfyapp.py:3611-3617`). Therefore **archive→extract→fingerprint(volume tree) ≠ fingerprint(local tree) by construction**, even with a perfectly fresh publish of the frozen tree. Baked could never equal persisted.

**Proven locally (not inferred):** building the real archive from the real tree, extracting it, and fingerprinting the extracted tree with the real `comfyapp` produced `421b50bd711e8d4868333f8cb776a454` — an **exact match to the live Volume record** fetched via `modal volume get` — while the local tree fingerprinted `ec22f6de14b680fb439c55d93ac0d364`. After the fix, archive→extract == local == `7d24383509e83867375e31b39d95fb39` (MATCH=True).

---

# Existing generation values

| Source | Value (pre-fix) | Meaning |
|---|---|---|
| Volume record (fetched) | `667f5c299d7f4b2e54ffaf7c0e06f25e` | written `2026-08-12 11:03:18` local, `reason=post_sync_custom_nodes_to_volume` — content hash of the volume tree as synced at 11:03 |
| Image bake (observed in old constructions) | `f397bcd530dc6e10…` | content hash of the local tree at the earlier image build |
| Local tree (frozen, old algorithm) | `ec22f6de14b680fb439c55d93ac0d364` | recomputed with the real `comfyapp` on the frozen tree |
| Volume record after publish test | `421b50bd711e8d4868333f8cb776a454` | recomputed from the real archive→extract (== local reproduction) |
| Local tree (after unified-algorithm fix) | `7d24383509e83867375e31b39d95fb39` | archive→extract MATCH=True |
| Final tree (after last wiring edit) | `62441578b512bd7c913b55976012b2c6` | manifest regenerated to match; next deployment bakes this |

---

# Baked-generation provenance

- Constant: `BAKED_CUSTOM_NODE_DEPS_MANIFEST_PATH = "/opt/comfymodal/custom_node_deps_baked.json"` (`comfyapp.py:3144`); local mirror `.baked_custom_node_deps/custom_node_deps_baked.json` (`comfyapp.py:8005-8007`).
- Algorithm: `custom_node_source_generation(source_root)` (`comfyapp.py:3673-3690`) = MD5 of `json.dumps(fingerprint minus "source_root", sort_keys=True)`; fingerprint (`comfyapp.py:3624-3670`) = per syncable node dir a single sha256 over `"{rel}:".encode() + canonical_bytes(file)` for tracked files (`.py/.txt/.toml/.cfg` + `requirements.txt/pyproject.toml/setup.py/setup.cfg`), pruned dirs = `_CUSTOM_NODE_GENERATED_DIRS`, excluded file suffixes `.log/.tmp/.trace/.jsonl/.whl`, prefixes `benchmark_/trace_`. CRLF normalized (`_canonical_dependency_bytes`, `comfyapp.py:3824-3834`). mtimes never participate; paths never participate (source_root stripped); untracked/dirty files DO participate; git not consulted; requirements files participate; generated experiment/report files participate **only if** inside tracked ext/name rules and not pruned (`.md`/`.json`/`.log` never do).
- Written at image build (`comfyapp.py:8024-8028`) via `_maybe_write_baked_manifest` (`8009-8022`), mounted into the image (`8075-8079` `add_local_file`). Read back by `load_baked_custom_node_dependency_manifest` (`4151-4166`).

# Persisted-generation provenance

- Record path: `/root/custom_nodes_vol/.comfymodal_control/custom_nodes_generation.json` (`comfyapp.py:1698-1702`, `MODELS_GENERATION_CONTROL_DIR` = `/root/custom_nodes_vol/.comfymodal_control`).
- Readers: `_read_custom_nodes_generation_record` (`1769-1793`), `_resolve_custom_nodes_generation(api, authoritative_only=True)` (`1859-1895`) → returns `api._custom_nodes_generation_seen` (source=`instance`) or the record (source=`persisted_record`); the `authoritative_only` parameter is dead — it never re-hashes content.
- Writers: `sync_custom_nodes_to_volume` (V1 remote, `8373-8469`) — extracts tar.gz into `.staging`, deletes volume content except `.comfymodal_control`, moves staging → root, then computes `custom_node_source_generation(CUSTOM_NODES_PATH)` from the **extracted** tree (`8437-8439`), writes the record (`8442-8445`), commits (`8460`). In-container writers only write when the record is **missing** (`_sync_custom_nodes_from_volume` `11055-11068`; startup `18551-18572`).
- The stored value is **content-derived** (a real hash of the extracted volume tree), not a deployment token — but it describes the **volume tree as extracted from the archive**, which differs from the local tree by the archive's larger exclusion set. That is the parity break.

# Actual-tree generation

- After `fallback_full_sync`, the runtime tree `/root/comfy/ComfyUI/custom_nodes` is rebuilt as **symlinks into the volume** (`sync_custom_nodes_into_comfy`, `comfyapp.py:3725-3812`, direction VOLUME→container, one-way; stale symlinks unlinked, blocking image-baked real dirs renamed to `.comfymodal_stale_custom_nodes`; the volume is never modified by the sync). The actual content is therefore the volume tree.
- The proof's observed value (`state.custom_node_generation`, set at `runtime_bootstrap.py:1308`) comes from the **instance token / persisted record** — it is never verified against a fresh content hash of the actual post-sync tree.

# fallback_full_sync direction and lifecycle

- Startup callback `sync_custom_nodes` (`modal_app.py:7187-7274`, wired `7355-7368`): baked vs `_resolve_custom_nodes_generation(authoritative_only=True)`; equal → `snapshot_exact_skip` (no sync); unequal → `fallback_full_sync` → `api._sync_custom_nodes_from_volume()`.
- `_sync_custom_nodes_from_volume` (`comfyapp.py:10894-11072`): reload volume → `sync_custom_nodes_into_comfy(CUSTOM_NODES_PATH, "/root/comfy/ComfyUI/custom_nodes", include_state=True)` — **VOLUME → container**, symlinks only, stale destination cleaned, **nothing on the volume deleted**, record rewritten **only when missing**.
- Ordering (snapshot construction): sync (`runtime_bootstrap.py:1269-1270`) → generation observation (`1305-1315`) → dependency-manifest persistence (`modal_app.py:7676-7689`) → **proof freeze** (`7691-7778`) → CPU snapshot capture (`7784+`). The proof freezes AFTER the sync, but compares baked vs the (unchanged) persisted token — hence `complete=0` even when a full sync succeeded.

# Authority model

**Model A — deployed image/source authoritative, Volume as a synchronized mirror.** The design intent is explicit at `modal_app.py:7188-7191`: "The image already contains the production custom nodes. Avoid copying the volume over them when the persisted generation is an exact match for the image-baked source." The volume is a mirror that must match the deployment; `snapshot_exact_skip` is the healthy path. The V2 deploy flow simply never refreshed the mirror (no `sync_custom_nodes_to_volume` call), and the fingerprint/archive exclusion sets disagreed — so the mirror could never match even when refreshed.

# A/B/C identity matrix

| | Value (pre-fix) | Value (post-fix) |
|---|---|---|
| A — baked (image, from local tree) | `ec22f6de…` | `7d243835…` (== local) |
| B — persisted (volume record) | `421b50bd…` (post-publish) | `7d243835…` (post-publish) |
| C — actual (volume tree content) | `421b50bd…` | `7d243835…` |

Pre-fix: **C == B, C != A** (the volume genuinely held different content than the image — the archive had dropped dirs the fingerprint counted). The proof correctly failed closed. Post-fix: **A == B == C**.

# Exact root cause

**Algorithm mismatch between the volume-sync archive filter (`__init__._CUSTOM_NODE_SYNC_EXCLUDE_DIRS`) and the fingerprint walk filter (`comfyapp._CUSTOM_NODE_GENERATED_DIRS`)** — the archive excluded directories that the fingerprint still hashed, so the extracted volume tree never fingerprinted like the local tree, making `generation_matches_observed=0` reproducible on every construction regardless of tree freeze, publish timing, or volume staleness. Compounded by the V2 deploy flow never refreshing the volume mirror at deploy time. Classification: **algorithm mismatch** (Repair D) + **missing deploy-time publication** (Repair C). Not a stale record, not proof timing, not the trust gate.

# Correctness requirements

- Baked and persisted must be produced by **one canonical content-derived algorithm** over the same effective file set.
- The volume mirror must be refreshed from the deployed source **at deploy time**, before snapshot construction.
- The proof must freeze only after the final runtime tree is established, and must not accept any value without content equality.
- Stale-record repair is allowed only when the **post-sync ACTUAL tree hash equals baked** (never bless different code).
- Restore/request paths must stay O(1) — no per-request full-tree hashing.

# Repair implemented

1. **Unified exclusion sets** — `comfyapp.py::_CUSTOM_NODE_GENERATED_DIRS` is now a superset of `__init__._CUSTOM_NODE_SYNC_EXCLUDE_DIRS` (comment documents the invariant). Archive→extract now preserves the fingerprint (verified: MATCH=True on the real tree).
2. **Deploy-time volume publication** — NEW `tools/publish_custom_nodes_volume.py`: builds the exact archive (mirrors `__init__._build_custom_nodes_archive` with the actual constants) and pushes it through the existing V1 remote `sync_custom_nodes_to_volume` (the same in-container algorithm that computes the record) before `modal deploy`.
3. **Bat wiring** — `deploy_and_run_v2_single.bat`: publish step before the V2 deploy in the V1-exists branch; in the V1-missing branch publish after V1 verify, then re-deploy V2 (fresh volume visible to construction).
4. **Construction-time reconciliation + parity diagnostics** — NEW `comfymodal_runtime/custom_node_parity.py` (pure: `build_parity_report`, `should_update_persisted_record`, `format_parity_line`); `modal_app.py::sync_custom_nodes` now, when `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1`: hashes the tree pre/post sync, repairs the persisted record **only when post-sync actual == baked** (writes record + commits + hydrates the token), emits `[v2.custom_node_generation_parity]` in both sync paths; exact-skip path stays O(1).
5. **Env passthrough** — `_runtime_env` now forwards `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION` so the construction container actually receives the marker (previously silently dropped — the parity event would never have fired remotely).

# Proof freeze ordering

Unchanged ordering (sync → observe → manifest persist → freeze → capture), but the freeze now observes the **reconciled** generation: with deploy-time publication, baked == persisted from the start (`snapshot_exact_skip`, callback_called=0); the construction-time reconciliation is the safety net for a stale record, activating only when the post-sync actual tree hash equals baked. The proof semantics are at least as strong as before (content equality on both sides; nothing is accepted without it).

# New diagnostics

`[v2.custom_node_generation_parity]` startup event (construction-gated; on restore/requests it is not emitted and no hashing occurs):
`baked_generation persisted_generation pre_sync_actual_generation post_sync_actual_generation persisted_source sync_performed sync_direction sync_reason baked_matches_persisted baked_matches_pre_sync_actual baked_matches_post_sync_actual persisted_matches_post_sync_actual final_authoritative_generation final_authority_source proof_freeze_generation proof_generation_match` (bools as 1/0, None as `-`).

# Local tests

`tests/test_custom_node_generation_parity.py` (NEW, 22 tests): the 16 mandated scenarios + format/record/authority extras + two root-cause regression tests:
- `test_generated_dirs_is_superset_of_archive_excludes` — pins the unified-exclusion invariant;
- `test_real_tree_archive_round_trip_matches` — builds the real archive from the real `custom_nodes` root, extracts, and asserts the fingerprint is preserved (the decisive proof).
**Result: 54 passed** (22 parity + `tests/test_deployment_proof.py` + `tests/test_plan_validation_proof.py` 32) — no Step-3 regressions.

# Validation deployment

One deployment + snapshot construction performed (PHASE-B restore-only/inherit architecture, all B arms OFF, `COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1`):

- Publish step: `[v2.volume_publish] status=ok remote_status=ok nodes=38` (runs before deploy).
- Deploy: `App deployed in 99.884s` — new images `im-spkR1aTc8cCNKpQ2uWZ9jj`, `im-eWz1p0SpxjKBcHwAor1j89` (+ construction image).
- 6 restore-only probes: **6/6 VALID** (0 invalid/DNF); placement GCP `us-east1` (×4) and `us-central1` (×2), unpinned.
- Snapshot construction container:
  - `[v2.custom_node_startup] decision=snapshot_exact_skip callback_called=0 source=persisted_record generation=7d24383509e83867`
  - `[v2.snapshot_model_eviction] restore_observed: cpu_snapshot_models_present=1 clip_present=1 unet_present=0 retained_role=clip_vae rss_after_restore_mib=11408.69` (≈11.4 GiB — 11–13 GiB class)
  - `[v2.restore_only_probe] ... unet_present=0 clip_present=1 vae_present=1 container_retained=1` (every probe)

# Snapshot proof result

```
[v2.deployment_proof] schema=1 complete=True reason=ok
  dep_hash=4fcf1492ee7a0d39 baked_gen=7d24383509e83867 gen_ok=1
  reg_fp=True dep_identity=True repair_mode=n/a
```

- `generation_matches_observed = 1` (gen_ok=1)
- `deployment_combined_hash` non-empty (`4fcf1492ee7a0d39`)
- `custom_nodes_generation` non-empty (`7d24383509e83867375e31b3…`)
- `registry_fingerprint` non-empty (reg_fp=True)
- `dependency_manifest_identity` non-empty (dep_identity=True)
- Architecture gates: CLIP=1, VAE=1, UNET=0, retain_role=clip_vae, RSS ≈11.4 GiB — all PASS.

Note: the parity event itself is gated on `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION` reaching the container; that passthrough was missing during this validation deploy (the proof passed via the deploy-time publication + unified algorithm, `snapshot_exact_skip`). The passthrough is now wired (`_runtime_env`), so the next construction will emit `[v2.custom_node_generation_parity]` as well.

# Remaining risks

- The final tree generation is now `62441578b512bd7c913b55976012b2c6` (the last wiring edit to `modal_app.py` participates in the fingerprint; manifest regenerated to match). The A/B campaign deployment must be built from this exact final tree; the deploy-time publish will keep baked == persisted for whatever value it produces.
- The V1-missing deploy branch re-deploys V2 after publishing — untested on a truly first-time workspace (not exercised here; V1 was already deployed).
- Volume publish archive ~493 MB / ~14,300 members; the V1 remote sync timeout (1800s) was adequate here.
- Registry fingerprint and dependency identity were already True pre-fix and remain so; they were not part of the mismatch.

# Whether A/B campaign may resume

**YES — A/B CAMPAIGN MAY RESUME.** The blocking `generation_mismatch` is fixed and the new snapshot freezes `complete=1 valid=1 generation_matches_observed=1`. The campaign agent should deploy once from this exact final tree (freeze record: `V2_AB_CAMPAIGN_FREEZE_REPAIR_DEPLOY.md`), then proceed with validation/discard → Step-3 acceptance → retained cohorts per the campaign protocol.
