# R44A — Runtime-State Generation Determinism Repair

Batch: R44A · Lane: runtime-state generation identity · Worktree: `../comfyui-modal-r42`
Branch: `r42-golden-reconciliation` · Baseline HEAD: `0c59f46e3238f421378e8852ebc548da815b70af`
No deploy, no Modal execution, no commits.

---

## 1. Exact root cause

`runtime_generation.py::_content_derived_generation` hashes the construction manifest. The manifest entries produced by `build_runtime_state_manifest` were **raw-byte SHA-256** of the tracked runtime-state files:

- `prescan_custom_nodes.json`
- `gpu_capacity_frozen.json`

Both physical files embed **volatile construction observations**:

| File | Volatile field | Source |
|---|---|---|
| `gpu_capacity_frozen.json` | `"captured_at": time.time()` | `restore_memory_arm.maybe_freeze_snapshot_gpu_capacity` |
| `gpu_capacity_frozen.json` | `"gpu_name"` (provider/marketing string) | same, from `nvidia-smi --query-gpu=…,name` |
| `prescan_custom_nodes.json` | `"updated_at": time.time()` | `runtime_bootstrap._persist_custom_node_identity_record` |

So: same source/deployment → Construction A writes one byte sequence, Construction B another → manifest SHA differs → `_content_derived_generation` differs → a fresh instance restored from A compares against Volume state last written by B → generation mismatch **and** raw-hash manifest mismatch → fail-closed `reload_runtime_state` → `runtime_state_generation_reload` → RuntimeStatus DEGRADED.

Deterministic hashing over nondeterministic inputs. The R42 content-derived fix removed the random `uuid4`; it did not remove volatility of the hashed inputs. The volatile bytes also poisoned the restore-side exact-match proof (`verify_runtime_state_manifest`, raw sha comparison), so fixing only the token would NOT have been sufficient — both sides must compare semantic identity.

## 2. Generation-tracked files (complete)

`DEFAULT_RUNTIME_STATE_MANIFEST_FILES` (config default `BootstrapConfig.runtime_state_manifest_files`, no deployment override found):

1. `prescan_custom_nodes.json` — required at construction.
2. `gpu_capacity_frozen.json` — optional (absence legitimate when freeze arm off).

Deliberately NOT tracked (unchanged): `dependency_manifest/immutable_manifest.json` (container-local in V2, not on the `/mnt` mount); models/custom-nodes generation control records in `comfyapp.py` live on other volumes and are separate contracts.

## 3. Semantic vs volatile field classification

### `gpu_capacity_frozen.json`

| Field | Class | Rationale |
|---|---|---|
| `total_vram_mib` | **SEMANTIC** | Drives `comfy.model_management.total_vram` at restore → resource behavior. A real change MUST change generation. |
| `source` | SEMANTIC (stable constant `"nvidia-smi"`) | Provenance; kept in identity. |
| `gpu_name` | **DIAGNOSTIC/VOLATILE** | Provider-sensitive marketing string; never read by `apply_frozen_total_vram_or_none` (reads only `total_vram_mib`). Excluded from identity; kept in file for logs/forensics. A real SKU change still trips identity via `total_vram_mib`. |
| `captured_at` | **DIAGNOSTIC/VOLATILE** | Wall-clock capture time. MUST NOT alter the token. |

### `prescan_custom_nodes.json`

| Field | Class | Rationale |
|---|---|---|
| `schema_version` | SEMANTIC | Record contract version. |
| `custom_node_generation` | **SEMANTIC** | Core custom-node source identity. |
| `generation_source` | SEMANTIC | Identity derivation provenance. |
| `deployment_combined_hash` | SEMANTIC | Deployment fingerprint. |
| `updated_at` | **DIAGNOSTIC/VOLATILE** | Record write timestamp. |

**Exact prescan volatility:** `"updated_at": time.time()` written by `_persist_custom_node_identity_record` (runtime_bootstrap.py:1521). This is the sole writer of the file (modal_app.py:8792 only supplies the path). Historical same-deployment byte drift between constructions = differing `updated_at` floats (plus JSON serialization order variance across processes). No filesystem metadata, host observations, or traversal-order content exists in this payload — proven by reading every field of the sole writer.

No other volatile patterns (hostname/PID/session/container IDs/ephemeral paths/durations) exist in either tracked file — verified field-by-field against both writers.

## 4. Files changed

| File | Change |
|---|---|
| `comfymodal_runtime/runtime_generation.py` | Semantic-identity normalization (only production file touched) |
| `tests/test_r44a_generation_determinism.py` | NEW — 9 deterministic-proof tests |

**Functions changed (runtime_generation.py):**
- NEW `RUNTIME_STATE_VOLATILE_IDENTITY_KEYS` — per-file volatile top-level key map.
- NEW `_semantic_identity_bytes(rel, raw)` — canonical projection: parse UTF-8 JSON, drop listed top-level keys, re-serialize `sort_keys=True, separators=(",",":"), ensure_ascii=True`. Unknown rel or unparseable bytes → raw bytes returned unchanged (deterministic + fail-closed).
- NEW `_identity_sha256_file(rel, path)` — SHA-256 of the projection.
- `build_runtime_state_manifest` — manifest `sha256` now the semantic identity hash.
- `verify_runtime_state_manifest` — identical projection applied to on-mount files at restore.
- `_content_derived_generation` — algorithm UNCHANGED (still SHA-256[:32] over canonical manifest); determinism now comes from manifest content being semantic.

**NOT changed:** writers (`maybe_freeze_snapshot_gpu_capacity`, `_persist_custom_node_identity_record`), marker writer/reader structure, `finalize_runtime_state_generation`, `_decide_runtime_state_reload`, all reload callbacks/policy, any loader/CLIP/UNET/model-preload file, any restore scheduling/threading/preload/sizing code.

## 5. Normalization design

Chosen pattern: *keep volatile diagnostics in the physical JSON but explicitly exclude them from generation identity*, applied symmetrically at BOTH identity consumers:

```
construction:  build_runtime_state_manifest → semantic sha per file → _content_derived_generation → marker
restore:       verify_runtime_state_manifest → semantic sha of mount files → compare vs snapshot manifest
               _decide_runtime_state_reload  → marker.files == expected manifest (both semantic) → verify → skip/reload
```

Fail-closed fallbacks preserved:
- unparseable/tracked-but-non-JSON bytes → raw-byte hash (byte equality required, as before);
- missing required file / unreadable file → raise → empty baseline → reload;
- absent-optional stays `{"present": false}`; unexpected presence → `manifest_file_unexpected`.

Transition note: markers/manifests written by pre-R44A constructions carry raw-byte shas; first post-R44A construction legitimately produces a different token → exactly one transitional reload, then stable. Consistent with fail-closed policy.

## 6. Before/after example tokens

Equivalent-deployment payloads A/B differing ONLY in `captured_at`, `gpu_name`, `updated_at`, key order, whitespace:

```
BEFORE (raw-byte manifest hashing):
  construction A gen = 4e7e5f402576b792f130982081597438
  construction B gen = 55004a89ee98f162fd029bbcfb338c20   ← spurious divergence (the bug)

AFTER (semantic identity):
  construction A gen = 267c06ce780518fc75db583f713b23b6
  construction B gen = 267c06ce780518fc75db583f713b23b6   ← identical
```

## 7. Local deterministic proof (no paid remote work)

`tests/test_r44a_generation_determinism.py` — 9 tests, all passing:

1. `test_independent_constructions_same_generation` — full production path (`RuntimeBootstrap.finalize_runtime_state_generation`) twice on independent roots with volatile-only-different inputs → identical tokens + identical manifests; volatile fields verified still physically present on disk.
2. `test_semantic_capacity_change_changes_generation` — `total_vram_mib` 97887→81510 → different token.
3. `test_prescan_source_change_changes_generation` — `custom_node_generation` cnG→cnG2 → different token.
4. `test_volatile_only_drift_is_exact_match` — mount overwritten with B's volatile-differing bytes → `(True, "exact_match")`.
5. `test_real_mismatch_still_fail_closed` — capacity change → `manifest_hash_mismatch`; prescan removed → `manifest_file_missing`; gpu removed → `manifest_file_missing`; gpu present when expected-absent → `manifest_file_unexpected`; corrupted JSON → `manifest_hash_mismatch`.
6. `test_key_order_and_whitespace_only_no_identity_change`.
7. `test_unparseable_file_falls_back_to_raw_bytes` — deterministic, byte-sensitive.
8. `test_marker_payload_shape` — schema v2, generation == derived token, files == state manifest, `updated_at_unix` diagnostic-only.
9. `test_decide_reload_skips_across_constructions` — snapshot from A vs volume written by B → `_decide_runtime_state_reload` = `skipped_generation_match/exact_match`; real capacity change with self-consistent new marker → `reloaded_generation_mismatch`.

Regression: `tests/test_runtime_state_reload_guard.py` 32/32 PASS (fail-closed table intact). `tests/test_r42_golden_integration.py` PASS (incl. `_content_derived_generation` determinism tests).

Command: `python -m pytest tests/test_r44a_generation_determinism.py tests/test_runtime_state_reload_guard.py -q` → **41 passed**.

Pre-existing unrelated failures (NOT from this lane): 7 tests in `tests/test_modal_app_identity.py` fail with `RuntimeError: CacheDiT snapshot preimport FAILED … No module named 'cache_dit' / huggingface_hub 'cached_download'` — local Windows env lacks image-baked packages; failure occurs during modal_app startup preimport, before any generation code runs.

## 8. Reload-guard / fail-closed proof

- `_decide_runtime_state_reload`: ZERO edits (git diff of `runtime_bootstrap.py` contains no hunks from this lane; its dirty state is pre-existing R42A drift-diagnostic work by an earlier batch, preserved verbatim).
- All reload reasons (`reloaded_generation_mismatch`, `manifest_hash_mismatch`, `manifest_file_missing`, `manifest_file_unexpected`, `record_invalid`, `mount_missing`) exercised green in §7 items 5 and 9 plus the existing 32-test guard suite.
- Real changes that still flip the token: custom-node source/identity (`custom_node_generation`, `deployment_combined_hash`, `generation_source`, `schema_version`), correctness-relevant capacity (`total_vram_mib`), provenance (`source`), presence/absence of tracked files, byte changes to unknown/unparseable content.

## 9. Restore-performance statement

No change to restore scheduling, threading, preloading, model snapshot composition, GPU restore behavior, method entry timing, minimal restore, CPU/GPU sizing, `min_containers`, `scaledown_window`, single-use behavior, or model loading. The only runtime behavioral delta: same-semantic-deployment constructions now derive identical tokens/manifests → no false reload. Verification cost is unchanged (same O(file) reads, tiny JSON parse of <1 KB payloads).

## 10. Concurrent-file conflicts

None. Zero overlap with the R44 loader lane (`clip_fast_hydration*`, `speculative_clip_hydration*`, `unet_fastsafetensors*`, `model_preload.py`, `loader_selection.py`, `config_authority.py`). All pre-existing dirty files preserved; no reset/revert/clean/stash used; no whole-file replacement.

---

R44A_GENERATION_ROOT_CAUSE_COMPLETE = YES
R44A_VOLATILITY_REMOVED_FROM_IDENTITY = YES
R44A_PRESCAN_DETERMINISTIC = YES
R44A_REAL_MISMATCH_STILL_FAIL_CLOSED = YES
R44A_RESTORE_PERFORMANCE_PATH_CHANGED = NO
R44A_READY_FOR_INTEGRATION = YES
