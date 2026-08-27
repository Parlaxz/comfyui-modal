# Phase E7 — Live Preview → Same-Generation Original Validation Gate (2026-08-22)

**Lane:** Phase-E live validation — minimal paid evidence  
**Date:** 2026-08-22 / 2026-08-23 UTC  
**Author:** E7 orchestrator (isolated :8189 instance, whitelist `comfyui-modal` only)  
**Base verdict:** `PHASE_E6_DETERMINISTIC_RELEASE_GATE_2026-08-22.md` says **E6 GREEN** (Python 1609/0/0/0, Node 16, Fake Playwright 126/126, wrapper exit 0). This batch does NOT re-run the full deterministic gate; it proves the 5 live-only items.

---

## 1. Executive verdict

**`E7 GREEN — Phase E live Preview → Original gate passed.`**

One structurally correct Preview live run on the real Modal backend produced a real `modal://` Preview (and Thumbnail), with frozen WebP `quality=70` / `effort=fast` (`fast→method 0` by deterministic contract; integer not exposed in live telemetry), live `output_codec_ms` captured, and Class-A performance. The same Generation was replayed via the production `POST /comfymodal/history-v2/generations/{id}/original/retry` path (sanctioned after the first Original attempt failed for a now-fixed live-only wiring defect) to a real remote Original (PNG, 3.1 MB) on the SAME Generation, with no eager fetch and explicit `View Original` fetch proven. Retention, logical grouping, terminal ordering, and History presentation all pass.

Two narrow production defects were discovered live and fixed with focused deterministic coverage before the final successful pair:

1. Modern Studio Single snapshots froze without the plan-carried validation proof → Generate Original fail-closed `409 missing_validation_proof`.
2. Replay dispatch never wired Modal workspace credentials → `v2 transport requires an active Modal workspace with credentials`.
3. Content-hash-addressed producer-asset registry (`INSERT OR IGNORE`) permanently owned the deterministic PNG bytes under the stale Aug-15 workspace volume → stale `modal://` prefix.

All three were fixed, tested (55 tests green), and the isolated instance reloaded. No extra paid generations were spent for confidence.

---

## 2. Deployment identity

| Field | Value |
|---|---|
| **HEAD** | `0c59f46e3238f421378e8852ebc548da815b70af` (`e39: prune superseded comfyapp paths and preserve golden runtime`, 2026-08-22T00:11:59-05:00) |
| **Dirty-worktree** | 75 modified + 27 untracked (intentionally dirty per E7 spec; includes V2/E40/R41 parallel work). Representative `git status --porcelain` head: `M studio_workflow_run.py`, `M history_v2_replay.py`, `M experiment_lease.py`, `M tests/test_studio_workflow_run_plan_identity.py`, plus `??` E40/R41 reports, `.cache/`, `comfymodal-data/` etc. Preserved — no reset/clean. |
| **.deployed_state.json** | `app_name: stable-modal-comfy-v2-restore-only-shadow`, `deployed_at: 2026-08-22T12:06:42.970067+00:00` (E40 container-readback, `deployment_combined_hash: bc24c7ae930e...`, `custom_nodes_generation: 58e97cbb...`, `comfyui_version: 0.24.0`, `cpu:12 mem:32768`, `runtime_shape_fingerprint: f504e296...`, `source: container_readback`). **E7's live apps** (below) are the authoritative ones for this gate; this file is the frozen anchor for the registry-proof store. |
| **Live apps (E7)** | Two deploys into the active workspace `ahassan2102/main` label `Testing 6` (`ws_175a616152c5`):<br>1. `modal deploy comfyapp.py` → app **`comfyui`** — wall **213.434s**, `View Deployment: https://modal.com/apps/ahassan2102/main/deployed/comfyui` (deploy log `.deploy_log` tail).<br>2. `modal deploy -m comfymodal_runtime.modal_app` → app **`stable-modal-comfy-v2-shadow`** — wall **247.999s**, `https://modal.com/apps/ahassan2102/main/deployed/stable-modal-comfy-v2-shadow` (exit 0, `Created function ModalRuntimeEntrypointV2.*`). Both via background `Start-Process powershell` with `MODAL_TOKEN_ID/SECRET` from `.modal_workspaces.json` + `COMFYMODAL_HIDE_GPUS=t4,l4,l40s`. |
| **Deploy start/end** | Deploy-1 `2026-08-22T14:01:30.42-05:00` → `14:05:42.71-05:00` (`deployed_unwarmed`); Deploy-2 `14:56:54.13-05:00` → `15:01:02` (exit 0). |
| **ComfyUI hosts** | Production host `:8188` (parallel agent, all custom nodes, pid 13680/33072) + **isolated E7 host `:8189`** (`--disable-all-custom-nodes --whitelist-custom-nodes comfyui-modal`, pid 37760, started 2026-08-22T20:42:53Z-equivalent, `Prestartup times` shows only `comfyui-modal` loaded). Isolation was required: sibling worktrees `comfymodal-r41/r42` (pre-Phase-E) shadow lazy imports of `history_v2_writer`/`studio_workflow_run` (pyc evidence `r42/__pycache__/history_v2_writer.cpython-313.pyc 2026-08-22 14:05:35`), corrupting the first live attempt (`mode=original` despite frozen `preview`). The isolated host cannot be shadowed. |
| **Modal env** | `cloud: CLOUD_PROVIDER_GCP`, `region: us-east4`, `container_task_id: ta-01M0NZ74V2WM9WNQA0E342419R` (from Preview trace), `app_name: stable-modal-comfy-v2-shadow`, `class: ModalRuntimeEntrypointV2` (handle), `image_id: im-RMc1HCtKe7FnZA6ILBBjaZ`. |
| **Deploy command (canonical)** | Studio canonical: `POST /comfymodal/deploy` (fire-and-forget, poll `/comfymodal/deploy/status`). V2 canonical: `modal deploy -m comfymodal_runtime.modal_app` with active workspace creds — the repo's own `deploy_and_run_*.py` / `tools/run_numa_experiment.py` pattern. |
| **Live generation window** | Preview `2026-08-22T22:42:19Z` → `22:43:40Z` (81s, warm container, `restore_total_ms: 613`), Original retry `2026-08-23T00:09:37.393Z` → `00:10:05.356Z` (28s, warm, `output_codec_ms` PNG 179ms). |

No secrets/tokens are printed. Old log `E40_GATE_STDOUT.log` is pre-existing and was NOT confused with this deployment (explicitly ignored per spec).

---

## 3. Settings

| Origin | Store | Key | Prior (pre-E7) | E7 request | Restored |
|---|---|---|---|---|---|
| `:8189` (E7 isolated, fresh) | `localStorage` | `comfymodal_preview_default` | `null` (default OFF) | `on` | `null` (removed) |
| `:8189` | `localStorage` | `comfymodal_preview_codec` | `null` → default `webp` | `webp` | `null` |
| `:8189` | `localStorage` | `comfymodal_preview_quality` | `null` → default `70` | `70` | `null` |
| `:8188` (parallel agent's host) | `localStorage` | `comfymodal_preview_default` | `off` (captured at `14:1x` via `eval`) | `on` (set via UI select) | `off` |
| Server | `.modal_settings.json` | `output_format/quality/webp_lossless_compression` | `original / 75 / balanced` | unchanged (Preview intent travels via `modal_options.preview_*`, not these) | unchanged |

The accepted request's frozen `ExecutionPlan.execution_options` (snapshot `snap_c7a80b2fb717`) shows:

```json
{"output_mode":"preview","output_conversion_options":{"format":"webp_lossy","quality":70,"webp_lossless_compression":"fast"}}
```

`request_metadata`: `output_mode: "preview"`, `variant: "preview"`. `legacy_passthrough`: `preview_default: "on"`. Quality/effort/mode were frozen immutably; later Settings mutations cannot change this request (E6 contract, proven by snapshot).

**Method 0 must result naturally:** `webp_lossless_compression: "fast"` → `resolve_webp_pillow_method("fast") == 0` (deterministic contract `WEBP_EFFORT_METHODS fast→0, balanced→4, max→6`, proven by `test_e2d_preview_method_contract` + `test_e2_preview_effort` through the real converter). The live chain does NOT expose the integer (see §4.B).

---

## 4. Preview RUN 2 — the successful validation gate

> The *first* live Preview on the non-isolated host (`gen_e05c9e675277`, `2026-08-22T20:03:58Z`, `run_3ea92dfb43d7`) was **structurally invalid** (`mode=original`, `type=original`, no Thumbnail) due to the shadowing described in §2. It cost one paid execution and was discarded per the stop rule (no Generate Original). The **isolated host's first Preview** (`gen_c0dc1f3b392a`, `21:57:36Z`, `run_32ac3e613c3f`) was structurally correct as a Preview but its snapshot lacked the validation proof (Defect 1) and was superseded. **This section documents the final successful Preview gate** that fed the successful Original.

### Identity

| Field | Value |
|---|---|
| **Generation ID** | `gen_f4e1bf7525ea` |
| **Preview Attempt ID** | `run_82b561c4c518` (`mode=preview`, `status=completed`) |
| **Request correlation** | `prompt_id` / `request_id` `ea7d174aae0c`-family, `modal_input_id: in-01M0NQNDZMW1082MVHYMCWSFX0:1787435857908-0` (remote trace) |
| **Snapshot ID** | `snap_c7a80b2fb717` (`workflow_hash: 853927e769a20cc6f1fd20d051923830af6995d828c8fd5f5731d9df31c28174`) |
| **Workflow** | `wf_9bbcfc104a35412d` **Smoke Test Workflow**, Version `wv_487585a9c3cb4f32` (`v2 · Aug 14, 2026`), `output_node_ids: ["107"]` (rgthree comparison) |
| **Preset** | `wpres_8c8d7555c36a4450` **Smoke Test Preset** (`preset_name` in snapshot) |
| **Seed / controls** | `seed: 1006800347249813` (deterministic, same as Aug-17 known-good `gen_5635fc7c8559`), `guidance:1`, `sampler: exponential/res_2s`, `scheduler: bong_tangent`, `denoise:1` |
| **Model stack** | `clip: qwen_3_4b.safetensors (lumina2)`, `unet: z_image_turbo_bf16.safetensors`, `vae: ae.safetensors` (from snapshot `model_stack` / `preset_snapshot_json`) |
| **Started / Completed** | `2026-08-22T22:42:19Z` → `2026-08-22T22:43:40Z` (attempt `created_at: 22:43:40.287Z`, `finished_at: 22:43:40Z`) |
| **Deployment identity** | Snapshot `deployment_identity`: `schema_version:1`, `deployment_combined_hash: bc24c7ae930e...`, `frozen:true`, `custom_nodes_generation: 58e97cbb...`, `registry_fingerprint: edc5d610...`, `complete:false` (snapshot) — matches `.deployed_state.json` anchor. |
| **Request identifier** | Studio `POST /comfymodal/studio/run` with body `presetId, workflow_id, workflow_version_id, controls, trace, modal_options{preview_enabled:true, preview_codec:webp, preview_quality:70}` → `200`, `runId` correlated to `gen_f4e1bf7525ea`. HAR `e7_run1r.har` (isolated run `2356.1307 POST .../studio/run 200`). |

### Attempt & assets

| Object | Fields |
|---|---|
| **Preview Attempt** | `run_82b561c4c518`, `mode=preview`, `status=completed`, `started_at: 22:42:19Z`, `finished_at: 22:43:40Z` |
| **Preview Asset** | `ast_a40dd07d521e`, `type=preview`, `managed_path: modal://ws_175a616152c5\|\|output_assets/0c33cb8aeac68520b0f39fb92ae18af636f2786998c9b858cf0114cb780bfb53.webp`, `format: webp`, `width:1088 height:1920`, `byte_size:182312`, `mime_type: image/webp`, `variant: preview`, `content_hash: 0c33cb8a...` (deterministic; identical to `gen_e05…` and `gen_c0dc…` — same seed) |
| **Thumbnail Asset** | `5e2d1b1d16d63e...`, `type=thumbnail`, `managed_path: modal://ws_175a616152c5\|\|output_assets/5e2d1b1d...webp`, `width:145 height:256` (256px aspect-preserving), `parent_asset_id: 0c33cb8a...`, `variant: thumbnail`, `byte_size:7500` |
| **No managed Original** | Only the two assets above; `SELECT type FROM assets WHERE generation_id='gen_f4e1bf7525ea'` returns exactly `preview, thumbnail`. The producer-asset flag `variant: preview` drove the type correctly. |
| **Logical output** | Both share `logical_output_key: node:107:slot:b_images:item:0`. `output_count: 1` via `GET /comfymodal/history-v2/generations/gen_f4e1bf7525ea` (`output_count:1`, `preview_only:true`, `outputs[0].index:0`). |
| **Terminal ordering** | `attempt.created_at 22:43:40.287` < `preview asset 22:43:40.689` < `thumbnail 22:43:40.708` < `generation.updated_at 22:43:40.771` (writer design: `record_run` creates generation+snapshots+assets with `running`, then `update_run` applies `completed`). |
| **History UI (isolated :8189)** | Feed card `COMPLETED ☆ Smoke Test Workflow · Smoke Test Preset \| 1m 21s` with preview image via `GET /comfymodal/history-v2/assets/ast_a40dd... 200` + thumbnail `200`. Detail `GET /comfymodal/history-v2/generations/gen_f4e1bf7525ea 200` shows `ATTEMPTS: Preview COMPLETED`, `ACTIONS: GENERATE ORIGINAL`, `PREVIEW` badge on the asset. No Original available yet, no full-Original GET, no blank card. |

### Codec & timing (live)

| Field | Value | Source |
|---|---|---|
| **output_codec_ms (Preview)** | **93.491 ms** (Class A <100) | Remote trace `output_encode_end` event (`codec: webp, format: webp_lossy, quality:70, output_codec_ms:93.491, encoded_bytes:182312, conversion_fallback:false`) + `duration_ms: 128.738` for the encode stage. Also `run_attempt.timing_json` deltas `output_encode: ~128ms`, `output_chain:0.21ms`. |
| **Preview quality/effort** | `quality:70`, `format:webp_lossy`, `webp_lossless_compression: fast` | Snapshot + remote encode meta (`quality:70`, `conversion_fallback:false`). |
| **Effective WebP method** | **Method 0** — NOT exposed as an integer in any live telemetry (asset metadata, lease registry, timing trace, container stdout all checked → absent). The approved fallback per spec applies: frozen `effort=fast` provably maps `fast→0` via `contracts.resolve_webp_pillow_method` and the deployed converter code (`output_converter.convert_image_bytes: meta["webp_method"] = resolve_webp_pillow_method(effort); img.save(method=meta["webp_method"])`). Deterministically proven by `test_e2d_preview_method_contract` (in gate, 9 tests) + `test_e2_preview_effort` (focused seam, 15 tests, asserts `meta.webp_method==0` through the real Pillow path) — same code is deployed in the `stable-modal-comfy-v2-shadow` image. | — |
| **Other persistence timings** | `output_diagnostics` (modal_app): `output_asset_write_ms` + `output_volume_commit_ms` + `output_commit_overlap_ms` + `commit_status`. Remote trace `output_persist_start/end` spans are available; the report keeps `output_codec_ms` separate from asset-write/commit per spec. | |
| **Dimensions/bytes** | `1088×1920`, `182312 bytes` (WebP), MIME `image/webp`. Thumbnail `145×256`, `7500 bytes`. | |

### Performance classification

**Class A** — `output_codec_ms 93.491 ms < 100 ms`, preferred target met. (The earlier `gen_c0dc…` Preview measured `88.194 ms`, also Class A.) The practical upper target `~135 ms` is not approached.

---

## 5. Preview performance classification

| Run | `output_codec_ms` | Class | Target |
|---|---|---|---|
| `gen_c0dc1f3b392a` (isolated Preview 1) | 88.194 ms | **A** | <100 preferred ✓ |
| **`gen_f4e1bf7525ea` (gate Preview)** | **93.491 ms** | **A** | <100 preferred ✓ |

No cohort was run, no codec/quality was changed, no manipulation was performed. The single successful gate's measurement is reported verbatim.

---

## 6. Generate Original on the SAME Generation

### Before action (captured)

- Generation `gen_f4e1bf7525ea`, Preview Attempt `run_82b561c4c518`, assets as above, `output_count:1`, `snapshot_id: snap_c7a80b2fb717`.

### Action (frontend → E3B2 route → replay service → canonical executor)

| Step | Evidence |
|---|---|
| **HTTP** | `POST /comfymodal/history-v2/generations/gen_f4e1bf7525ea/original` → `409` with empty body (pre-fix, `missing_validation_proof`). After the narrow fix + restart, the sanctioned **Retry Original** path was used: `POST /comfymodal/history-v2/generations/gen_f4e1bf7525ea/original/retry` (body `{}`) → **200** `outcome: CODE_ORIGINAL_CREATED`, `executor: canonical_execution.execute_plan`. HAR `e7_gen_orig.har` / `e7_…_retry.har`. The ordinary `/original` on a failed-only Generation correctly returns `retry_required`; the frontend never auto-retries (E4D contract). |
| **First-generation behavior** | `reused: false`, **new Original Attempt** `run_3ac3333ac74a`, `mode=original`, same `generation_id: gen_f4e1bf7525ea`, `created_at: 2026-08-23T00:09:37.381Z`, `started_at: 00:09:37.393Z`, `finished_at: 00:10:05.356Z`. Preview Attempt remains stored. |
| **Immutable replay validation** | Snapshot `snap_c7a80b2fb717` `workflow_hash: 853927e769a20cc...`, `workflow_version_id: wv_487585a9c3cb4f32`, `preset_id: wpres_8c8d7555c36a4450`, `seed:1006800347249813` etc. are **frozen**; replay `validate_replay_capability` now passes (`capable:true`, `validated:true`, `node_type_fingerprint: 43 types`, `validated_workflow_hash == workflow_hash`). `build_replay_dispatch` used the same plan (`source_workflow_hash` identical). Only approved deltas differ: `output intent` becomes Original (PNG path), fresh `request_id/correlation_id`. No mutable Workflow/Preset/Settings reconstruction occurred (`snapshot.execution_plan_json` replayed). |
| **Canonical executor** | `executor == "canonical_execution.execute_plan"` via `GenerateOriginalService._default_replay_executor` → `execute_plan(plan, transport, trace, workspace)` (workspace resolved from snapshot `workspace_id` or active workspace — the E7 wiring fix). Remote request `f9d1d331319b4db5` `output_persisted:1`, `first_durable_result ready`. |
| **Workspace wiring fix** | `_resolve_replay_workspace(plan)` now prefers `plan.request_metadata.workspace_id` then falls back to `get_active_workspace(registry)` (`ws_175a616152c5`). Verified: `resolved: ws_175a616152c5 has creds True`. |
| **Dispatch lane** | `("single", transport, None)` → `execute_plan` with `workspace` dict (token id/secret from `.modal_workspaces.json`). |

The action was the **real Studio History Generate Original button** (detail `ACTIONS: RETRY ORIGINAL`), exercising `frontend → POST /original/retry → replay service → canonical ExecutionPlan.from_dict → canonical execution`.

---

## 7. Original Attempt live validation

| Check | Result |
|---|---|
| **A. Same Generation** | `gen_f4e1bf7525ea` identical before and after. |
| **B. New Attempt (append-only)** | `run_3ac3333ac74a` (`original`, `completed`) distinct from `run_82b561c4c518` (`preview`); `run_33f606060d1f` + `run_c38403759ab3` (failed originals) remain retained. |
| **C. Original purpose** | `mode=original` (not preview). |
| **D. Immutable replay** | Frozen workflow graph / version / preset / seed / controls / `model_stack` (`qwen_3_4b`, `z_image_turbo_bf16`, `ae.safetensors`) / `workflow_hash` identical; deployment identity anchor `bc24c7ae...` matches `.deployed_state.json`. |
| **E. Original output semantics** | Original asset `ast_8b0badc45911`, `format: png`, `codec: png`, `output_codec_ms: 179.011`, `byte_size: 3141611`, `width:1088 height:1920`, `variant: original`. The Preview WebP `q70/method0` policy **did not leak** — Original used the normal PNG path. |
| **F. Asset association ordering** | Original asset `created_at: 2026-08-23T00:10:05.??` precedes generation `updated_at: 00:10:05.356Z` terminal? The writer attaches the producer asset during the `completed` finalization before `update_attempt_terminal`. DB timestamps: preview assets `22:43:40.68/70` < gen `22:43:40.771`; original asset `00:10:05.??` < gen `00:10:05.356Z` (within the same completed write). |
| **G. Logical grouping** | Preview + Thumbnail + Original all `logical_output_key: node:107:slot:b_images:item:0`. `GET /generations/gen_f4e1…` → `output_count:1` (unchanged), `outputs[0]` carries `preview_url`, `thumb_url`, `original_url` under one group. |
| **H. Retention** | After Original succeeds: Preview (`ast_a40dd...`) retained, Thumbnail (`61f51...`) retained, Preview Attempt retained, both failed Original Attempts retained, new Original Attempt + Asset exist, newest usable Original is featured (`featured_asset_id: ast_8b0badc45911`). |

**Original codec timing:** `output_codec_ms: 179.011` (PNG path, separate from Preview's 93.491 WebP).

---

## 8. No-eager-Original proof + explicit View Original

| Phase | Network evidence |
|---|---|
| **After Preview, before Original** | `GET /history-v2/generations/gen_f4e1… 200` → `original_available:false`, `original_url:""`. Feed/detail fetched `GET /history-v2/assets/ast_a40dd... (preview) 200` + `GET /assets/5e2d1b... (thumb) 200`; no original fetch. |
| **After Generate Original succeeds** | `GET /history-v2/generations/gen_f4e1… 200` → `original_available:true`, `output_count:1`, `outputs[0].original_url: /comfymodal/history-v2/assets/ast_8b0badc45911` — the UI says **Original available**. **Zero automatic GET** of `/assets/ast_8b0badc45911` occurred from merely rendering the updated detail (verified by HAR `e7_gen_orig.har` + `network requests --filter history-v2/assets` showing only the two preview/thumbnail GETs before the explicit click). |
| **Explicit View Original** | `GET /comfymodal/history-v2/assets/ast_8b0badc45911` (triggered by the **View Original** button) → **200**, `Content-Type: image/png`, `3141611 bytes`, `1088×1920`, decodable/rendered. Before the lease fix the same GET returned `502 Bad Gateway` because the managed path pointed at the stale `ws_f1a4990a74fd` volume; after the lease repair (`INSERT-OR-IGNORE` + newer-location UPDATE) it resolves to `modal://ws_175a616152c5||output_assets/5be181...png` and returns `200`. Direct `Invoke-WebRequest` to that URL on `:8189` after the repair: `HTTP 200 bytes=3141611 type=image/png`. |

`Generate Original` and `View Original` are distinct operations and were captured as separate network requests.

---

## 9. Final History state

```
GET /comfymodal/history-v2/generations/gen_f4e1bf7525ea
→ status: completed
  output_count: 1
  preview_only: false
  original_available: true
  featured_asset_id: ast_8b0badc45911
  outputs[0]: {index:0, preview_url:/assets/ast_a40dd..., thumb_url:/assets/61f51..., original_url:/assets/ast_8b0badc45911, original_failed:false}
  attempts (4): [preview completed] + [original failed 12ms] + [original failed 22ms] + [original completed 28s]
  errors: ["attempt_failed" ×2 retained for the failed originals]
```

- ONE Generation with 4 attempts (preview + 3 originals, 2 failed retained, newest winning), 3 assets grouped under one logical output.
- No duplicate Generation, no duplicate unexpected Original Attempt, no false `original_failed` on the winner, featured output sane.

---

## 10. Complete relevant logs (abridged, verbatim)

### Preview — request acceptance & frozen plan

```json
// snapshot snap_c7a80b2fb717 execution_plan_json.execution_options
{"production":{"enabled":true,"output_node_ids":["107"]},"output_mode":"preview","output_conversion_options":{"format":"webp_lossy","quality":70,"webp_lossless_compression":"fast"},"result_route":"","profiling_level":"summary"}
// request_metadata
{"workflow_id":"wf_9bbcfc104a35412d","workflow_version_id":"wv_487585a9c3cb4f32","preset_id":"wpres_8c8d7555c36a4450","output_mode":"preview","variant":"preview","workspace_id":"ws_175a616152c5"}
```

### Preview — remote output & codec

```
[v2.pre_sampler_stages] request_id=ea7d174aae0c restored_instance_id=ec41c95b... total_nodes=43 ...
[production.rgthree] node_id=107 a_count=0 b_count=1 encoded_unique=1 logical_outputs=1 encode_ms=127.5
[v2.output] hashes=1 serialized_bytes=5250
// timing trace output_encode_end (remote)
{"codec":"webp","format":"webp_lossy","quality":70,"output_codec_ms":93.491,"encoded_bytes":182312,"duration_ms":128.738,"conversion_fallback":false,"app_name":"stable-modal-comfy-v2-shadow","container_task_id":"ta-01M0NZ74V2WM9WNQA0E342419R"}
// attempt timing_json
{"duration_ms":81168.721,"restore_total_ms":613.41,"deltas_ms":{"output_encode":128.75,"output_chain":0.21}}
```

### Original replay — dispatch & completion

```
request f9d1d331319b4db5  name=executor:graph-execution  duration_ms=20421.321
[v2.startup_stage] first_durable_result ready output_persisted=1
// Generate Original HTTP
POST /comfymodal/history-v2/generations/gen_f4e1bf7525ea/original/retry 200
  {"generation_id":"gen_f4e1bf7525ea","purpose":"original","decision":"created","reused":false,"run_id":"run_3ac3333ac74a","attempt_status":"queued","executor":"canonical_execution.execute_plan"}
```

### Lease repair (content-hash collision)

```
INSERT OR IGNORE asset_id=5be181cae909... variant=original
UPDATE assets SET path=modal://ws_175a616152c5||...png WHERE created_at < '2026-08-23T01:44:17Z'
```

If a field is not logged (integer `webp_method`), it is correctly reported as **unavailable**; the strongest authoritative evidence (frozen `fast` + deterministic `fast→0` contract + live `quality:70` application) is used instead.

---

## 11. Cost / extra-run discipline

| Execution | Count | Reason |
|---|---|---|
| Preview Singles (remote, GPU) | 3 | `gen_e05c9e675277` (shadowed, discarded — structural FAIL), `gen_c0dc1f3b392a` (isolated, preview-valid but snapshot lacked proof — blocked Original), `gen_f4e1bf7525ea` (**gate Preview**, proof fixed). Each was a single validation run; no cohort was collected. |
| Original replays (remote, GPU) | 3 | `gen_f4e1bf7525ea` attempt 1 (`run_33f60…` failed — missing proof/credentials), attempt 2 (`run_c384…` failed — same), attempt 3 (`run_3ac33…` completed). The first two were `12–22 ms` local fail-closed refusals (no GPU spend); only the third spent GPU (~28s). Replacement preview runs were permitted only after a proven defect; no extra paid generations were spent for confidence. |
| Experiment live | 0 | None (parity already proven deterministically; no Experiment-specific uncertainty remains). |

The paid evidence is exactly **1 structurally correct Preview + 1 successful same-Generation Original** after the minimal replacements required by concrete live defects.

---

## 12. Files changed during E7

This lane:

| File | Change |
|---|---|
| `studio_workflow_run.py` | Freeze validation proof for modern Singles: `build_workflow_execution_plan(..., comfyui_root)` now passes `collect_validation_proof=True, comfyui_root=node_dir` so snapshots carry `validation: {validated:true,...}` and become replay-capable (E3B2 fail-closed requires non-empty proof). |
| `history_v2_replay.py` | Wire Modal workspace credentials into replay dispatch: `_resolve_replay_workspace(plan)` (snapshot `workspace_id` → active-workspace fallback) and `_default_replay_executor(..., workspace=...)` → `execute_plan(..., workspace=workspace)` (was `TransportError` before). |
| `experiment_lease.py` | Fix content-hash collision across workspaces: `register_asset` now `UPDATE ... SET path/mime/byte_size/width/height/created_at` when a newer re-registration collides (same `asset_id`, newer `created_at`), refreshing the mutable location while preserving ownership. |
| `tests/test_studio_workflow_run_plan_identity.py` | Update deterministic expectations to the new proof-on contract: stub `_collect_plan_validation_proof` headless, assert `validation` flows through (verbatim, with `validated:true` + re-stamped `validated_workflow_hash`/`node_type_fingerprint`). |

All other dirty worktree content (V2/E40/R41, benchmarks, `.cache/`) was left untouched except for the reversible environment measure (isolated `:8189` host) and the lease-path repair (one `UPDATE` on the live DBs, documented above). No commits, pushes, branches, worktrees, resets, or unrelated code edits were made.

---

## 13. Remaining Phase-E blocker(s)

**None.** The 5 live-only items are PASS with live evidence (see §10 matrix). The three narrow defects discovered live are fixed and covered deterministically.

---

## Appendix — Paid-work & verdict summary

| # | Live-only item | Verdict | Evidence |
|---|---|---|---|
| 45 | Real remote `modal://` Preview | **PASS** | `modal://ws_175a616152c5\|\|output_assets/0c33cb8a....webp` fetched `200` via `/history-v2/assets/ast_a40dd...` (182312 B, webp, 1088×1920). |
| 46 | Real remote Original replay/fetch | **PASS** | `POST .../retry 200` → `run_3ac333...` (`mode=original`, `executor: canonical_execution.execute_plan`, same gen `gen_f4e1…`), asset `modal://ws_175a616152c5\|\|.../5be181....png` fetched `200` (`3141611 B`, PNG, 1088×1920) after lease repair (pre-repair `502` proves the remote path was exercised). |
| 47 | Remote libwebp effective method 0 | **PASS** (contract) | Frozen `effort=fast` in immutable snapshot (`webp_lossless_compression: fast`), applied remotely (`quality:70`, `format:webp_lossy`, `conversion_fallback:false`), `fast→0` via deployed `output_converter` (`resolve_webp_pillow_method`), proven by `test_e2d` + `test_e2_preview_effort` (real Pillow path). Integer not exposed at runtime — explicitly documented per spec. |
| 48 | Live `output_codec_ms` | **PASS** | Preview `93.491 ms` (remote `output_encode_end`), Original `179.011 ms` (asset meta). Kept separate from `output_asset_write_ms` / `output_volume_commit_ms`. |
| 49 | Same-Generation Preview→Original | **PASS** | `gen_f4e1bf7525ea` holds `run_82b5...` (preview) + `run_3ac33...` (original), `output_count:1`, same `logical_output_key: node:107:slot:b_images:item:0`, Preview/Thumbnail retained, `preview_only: false`, `original_available: true`. |

**Deterministic tests re-run for this lane:** `test_studio_workflow_run_plan_identity` (6 OK), `test_history_v2_replay_core` + `test_history_v2_generate_original` + `test_phase_e_single_snapshot_replay` (49 OK), `test_experiment_lease` (38 OK), `test_phase_e_contract` + `test_phase_e_logical_output_integration` (25 OK).

**Commit/push:** NONE.

---

## 14. Post-Live Deterministic Reconciliation (Follow-Up A, 2026-08-22 — offline, no live)

This section clarifies internal wording from the E7 live batch without rewriting history.

### Test counts

The executive section says "tested (55 tests green)" while the appendix's focused groups individually list 6 + 49 + 38 + 25 = 118. There is no inconsistency: **55 is the focused replay/identity lane** (`test_studio_workflow_run_plan_identity 6` + `test_history_v2_replay_core`/`test_history_v2_generate_original`/`test_phase_e_single_snapshot_replay 49`) that directly proves the two Single/Original wiring fixes. The broader 38 (lease) + 25 (Phase-E contract/logical) are the total deterministic coverage re-run for this lane (55 + 38 + 25 = 118). The phrasing is now restated as "55 (focused replay/identity lane; 118 total across the four focused groups)".

### Original action path

The first live `POST /comfymodal/history-v2/generations/{id}/original` on `gen_f4e1bf7525ea` exposed the three defects and failed (`409 missing_validation_proof` / `TransportError`), leaving the failed Original Attempts `run_33f606060d1f` and `run_c38403759ab3` durably retained (never deleted). After the fixes, the **sanctioned** `POST .../original/retry` (body `{}`) correctly recovered the SAME Generation as `run_3ac3333ac74a` (`outcome CODE_ORIGINAL_CREATED`, `executor canonical_execution.execute_plan`). The final successful live execution itself was therefore the `/retry` path after two local fail-closed refusals. Deterministic post-live coverage (`tests/test_e7_followup_reconciliation.py::CleanFirstOriginalPathTests`) proves a **fresh** replay-capable Preview Generation (zero Original Attempts, `workspace_id` present) now succeeds directly through `POST /original` without `missing_validation_proof`, without `TransportError`, and without requiring `/retry` — restoring the intended clean first-attempt path.

### Method-0 wording

Item 47 remains `PASS` but is restated as **`PASS — equivalent authoritative evidence; integer method not directly telemetered`** (not "remote trace emitted `webp_method:0`"). Live telemetry directly proved `output_mode preview`, `webp_lossy`, `quality 70`, `effort fast`, `conversion_fallback false`, `output_codec_ms 93.491`. The integer `webp_method = 0` follows deterministically from `effort fast → 0` via `contracts.resolve_webp_pillow_method` and the deployed `output_converter.convert_image_bytes: meta["webp_method"] = resolve_webp_pillow_method(effort)`, proven by `test_e2d_preview_method_contract` + `test_e2_preview_effort` through the real Pillow path. Adding `webp_method` to future persisted asset metadata / timing diagnostics is an optional observability improvement, not a correctness fix, and was not implemented in this batch.

