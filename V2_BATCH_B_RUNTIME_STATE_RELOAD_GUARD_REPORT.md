# V2 — Batch B: Runtime-State Volume Reload Guard (skip redundant `reload_runtime_state` on restored generation requests)

Date: 2026-08-14 (rev 2 — content-based freshness proof)
Owner lane: Batch B1 (comfymodal_runtime/runtime_bootstrap.py + runtime_generation.py + dedicated tests)
Status: READY FOR INTEGRATION (one documented modal_app.py call-site patch required)
No commit, no deploy, no Modal runs.

---

## 1. Current reload path

`RuntimeBootstrap.restore()` step 3 invokes the `reload_runtime_state` callback unconditionally
(`comfymodal_runtime/runtime_bootstrap.py`, `_do_reload_runtime_state`). The callback is a
closure injected from `comfymodal_runtime/modal_app.py:7719-7724` (inside `_configure_runtime`):

```python
def reload_runtime_state() -> None:
    volume = getattr(module, "runtime_config_vol", None)
    if volume is not None:
        volume.reload()
    global _RUNTIME_STATE_VOLUME_RELOADED_MONO
    _RUNTIME_STATE_VOLUME_RELOADED_MONO = time.monotonic()
```

i.e. one Modal network `Volume.reload()` RPC per restored request on the
`comfymodal-runtime-config` Volume (`RUNTIME_STATE_VOLUME_NAME`, modal_app.py:265), mounted at
`/mnt/comfymodal_runtime_state` (`RUNTIME_STATE_PATH`, modal_app.py:268; V1 legacy mount
`/root/comfymodal_runtime_state`). Measured cost: median **81.9 ms** (range 71.5–263.8 ms,
10-run cohort, `V2_RESULT_HANDOFF_RESTORE_AND_SETUP_RESEARCH.md` §7). The callback is
timer-wrapped (`_wrap_restore_stage`, modal_app.py:7952) so `reload_runtime_state_ms` is
accounted in `restore_breakdown`. The same callback is also invoked at construction startup
(runtime_bootstrap.py startup step); that call is untouched by this guard.

## 2. Runtime-state writers

Complete inventory (files/line refs verified against the **current** checkout; concurrent
Batch-B drift re-checked — no new runtime-state writers were added):

**Construction-time (snap=True startup, before snapshot capture):**
| File | Writer | Mechanism | On /mnt mount? |
|---|---|---|---|
| `prescan_custom_nodes.json` | `runtime_bootstrap.py` `_persist_custom_node_identity_record` (called from startup) | plain local FS, temp + `os.replace` | **YES** |
| `dependency_manifest/immutable_manifest.json` | `modal_app.py:8329` → legacy `comfyapp.py:2335-2393` | plain FS under `/root/comfymodal_runtime_state/` + `commit()` | **NO — container-local `/root`, snapshot-carried** (V2 mounts the volume only at `/mnt`; the commit flushes the `/mnt` mount) |
| `gpu_capacity_frozen.json` | `modal_app.py:8993-8996` → `restore_memory_arm.py:95-162` (flag-gated) | plain local FS, temp + `fsync` + `os.replace`; **no volume commit after it** | **YES** |

Snapshot capture occurs when the `startup()` enter-hook returns (modal_app.py:17260-17264), i.e.
after all of the above. `v2_cert_*.json` is only **read** at construction (cert-snapshot
retention, modal_app.py:8245); `snapshot_seed.json`/`restore_state.json` are written only on the
opt-in publisher path (see §4). Snapshot-manifest capture and allocator hygiene
(`COMFYMODAL_V2_SNAPSHOT_MANIFEST` / `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE`) are
memory/print-only — no volume writes.

**Request/execution-time (restored container):** `v2_cert_<identity>.json`
(`_write_v2_validation_certificate`, modal_app.py:1494-1567, with `commit.aio()`),
`prescan_custom_nodes.json` rewrite (restore path, only after a full custom-node sync),
`output_assets/*`, `prompt_signature_memo.json` (request-time), plus
`snapshot_seed.json`/`restore_state.json` **only when `COMFYMODAL_V2_PUBLISH_RESTORE_PLAN=1`**
(publisher path). Post-run/host-side writers (V1 `comfyapp.py` certs, profiles, flags) exist but
are outside the restored-container critical path.

## 3. Mount-lag evidence

`V2_FINAL_OBSERVABILITY_AND_RESTORE_COMPLETION.md:49` and the frozen-VRAM investigation
(`V2_RESULT_HANDOFF_RESTORE_AND_SETUP_RESEARCH.md` §9.2): a construction-time write
(`gpu_capacity_frozen.json`, written by plain local FS at modal_app.py:8993-8996 **after** the
last volume commit) was **not visible to the restored mount until `Volume.reload()`**. The
restored mount therefore cannot be assumed to reflect construction-time writes — an
unconditional skip of `reload_runtime_state` is UNSAFE.

## 4. Existing identity/generation mechanisms

| Mechanism | Covers | Construction-written? | Readable locally at restore without reload? | Reusable here? |
|---|---|---|---|---|
| `models_generation.json` + `_should_reload_models_volume` (comfyapp.py:1749-1810, Batch A guard) | **models** Volume (`comfyui-models`) | yes | yes | no — different Volume |
| `prescan_custom_nodes.json` (runtime_bootstrap.py) | custom-node identity record | yes (on the runtime-state mount) | yes | partially — reused as a manifest member, not as the sole identity |
| `dependency_manifest/immutable_manifest.json` | dependency identity | yes, but **NOT on the /mnt mount in V2** (container-local `/root`, snapshot-carried) | from `/root`, not the volume mount | no — cannot participate in a mount-content proof |
| `snapshot_seed.json` / `restore_state.json` `_generation` stamps (runtime_state.py `CommitCoordinator`) | logical write generation of the seed/restore-plan payloads | only on opt-in publisher path | yes | no — request-time, flag-gated |
| `_RUNTIME_STATE_VOLUME_RELOADED_MONO` (modal_app.py:1785) | in-session monotonic "remote reload happened" stamp | n/a | n/a | no — must NOT be reused as freshness proof (see §8) |

**No existing construction-time generation identity existed for the runtime-state Volume
itself** — the Batch B1 marker (`runtime_config_generation.json`) was created for this, now
extended with a content manifest (rev 2).

## 5. New guard design (rev 2 — content-based)

New module `comfymodal_runtime/runtime_generation.py`:

- `RUNTIME_STATE_GENERATION_FILENAME = "runtime_config_generation.json"`
- `RUNTIME_STATE_GENERATION_SCHEMA_VERSION = 2` (v1 markers are deliberately rejected: a
  generation-only marker cannot prove content → fail closed to reload)
- `DEFAULT_RUNTIME_STATE_MANIFEST_FILES = ("prescan_custom_nodes.json", "gpu_capacity_frozen.json")`
  — correctness-relevant construction files relative to the volume root (audit-derived;
  `dependency_manifest/immutable_manifest.json` excluded — it is not on the /mnt mount in V2,
  see §2, so it cannot be proven from the mount).
- `DEFAULT_RUNTIME_STATE_MANIFEST_REQUIRED = ("prescan_custom_nodes.json",)` — must be present
  at construction (fail closed otherwise). `gpu_capacity_frozen.json` is optional: its absence
  at construction (frozen-VRAM arm off) is a legitimate state, recorded as `present=false`.
- `build_runtime_state_manifest(root_dir, relative_files, *, required)` — local read/hash of
  the correctness-relevant files; returns `{rel: {"present": bool, "sha256": str}}`; raises
  (fail closed) on a missing required file or an unreadable file.
- `write_runtime_state_generation_marker(root_dir, *, generation, reason, files_manifest)` —
  atomic local-FS write (temp + `fsync` + `os.replace`, the same pattern as the other
  construction writers) of the schema-v2 payload:
  ```json
  {
    "schema_version": 2,
    "generation": "<uuid hex>",
    "files": {
      "prescan_custom_nodes.json": {"present": true, "sha256": "..."},
      "gpu_capacity_frozen.json": {"present": false}
    }
  }
  ```
  No volatile timestamps enter the comparison (``updated_at_unix`` is informational only).
- `read_runtime_state_generation_marker(root_dir)` — fail-closed local reader; returns the
  parsed dict for any well-formed marker (caller rejects non-v2), `None` on
  missing/unreadable/non-dict/empty-generation.
- `verify_runtime_state_manifest(root_dir, expected_manifest)` — local-only verifier;
  `(True, "exact_match")` or `(False, reason)` with reason ∈
  {`manifest_file_missing`, `manifest_hash_mismatch`, `manifest_file_unexpected`,
  `manifest_read_error:<exc-type>`}.

`RuntimeBootstrap` additions (all in runtime_bootstrap.py):

- `BootstrapConfig.runtime_state_generation_path` (default `""`, auto-derived from the
  `prescan_record_path` directory — both live on the volume root — so **no modal_app.py config
  change is needed**), plus `runtime_state_manifest_files` / `runtime_state_manifest_required`.
- `BootstrapState.snapshot_runtime_state_generation` (default `""` → fail closed),
  `runtime_state_generation_marker_written`, and
  `snapshot_runtime_state_manifest` (default `{}` → fail closed).
- Constructor injectables `write_runtime_state_generation_marker` /
  `read_runtime_state_generation_marker` / `build_runtime_state_manifest` /
  `verify_runtime_state_manifest` (default to the module functions) for testability.
- `finalize_runtime_state_generation(*, trace=None, reason="construction") -> str` —
  construction-time manifest build + marker write + baseline freeze (see §6).
- `_decide_runtime_state_reload() -> dict` — restore-time local decision (see §7).
- Restore step 3 rewritten to consume the decision; skip branch calls nothing.

## 6. Construction-time marker semantics (rev 2)

`finalize_runtime_state_generation` is called **once, at the very end of snapshot construction
— after every correctness-relevant runtime-state write and before snapshot capture** (semantic
boundary, §13). It:

1. **builds the content manifest** by locally reading/hashing the correctness-relevant
   construction files (`prescan_custom_nodes.json` required; `gpu_capacity_frozen.json`
   recorded `present=false` when absent — the correct construction state with the frozen-VRAM
   arm off);
2. **writes the marker atomically** (`runtime_config_generation.json`, schema v2: generation +
   files manifest) through the same plain local-FS writer as the other construction files (no
   Volume API, no RPC);
3. **freezes the exact generation + manifest** into
   `BootstrapState.snapshot_runtime_state_generation` / `snapshot_runtime_state_manifest`
   (survives the memory snapshot).

**Fail closed:** if a required file cannot be read/hash-verified (missing required file,
unreadable file, builder/writer exception, unresolvable path), NO usable baseline is claimed —
generation AND manifest stay empty and no marker is written. Restore then reloads as before.
`finalize_runtime_state_generation` never raises; startup is never blocked.

**Why content, not write order:** the previous proof ("marker written last ⇒ marker visibility
implies all earlier writes visible") is retained only as a *secondary* property. The primary
proof is now the exact generation + exact local construction-state manifest — even if a
restored mount showed a marker while an earlier file lagged (or a file changed), the content
check fails and the reload runs. Conversely, the generation token still rejects a stale marker
whose files happen to be present and byte-identical.

## 7. Restore-time decision (rev 2)

`_decide_runtime_state_reload()` reads the marker from the restored mount using **local
filesystem access only** and applies the skip predicate:

**skip ⟺ generation_match AND content_manifest_match**, where:

- **generation_match** — marker `generation` == `BootstrapState.snapshot_runtime_state_generation`,
  marker is schema v2, and marker `files` == the frozen baseline manifest (marker-vs-baseline
  consistency);
- **content_manifest_match** — every manifest entry verified against the restored mount:
  expected-present files exist with matching sha256; expected-absent files remain absent
  (via `verify_runtime_state_manifest`).

Decision table:

| Condition | decision | reason | reload? |
|---|---|---|---|
| generation + manifest both match (local verify OK) | `skipped_generation_match` | `exact_match` | **no** |
| marker generation != baseline | `reloaded_generation_mismatch` | `generation_mismatch` | yes |
| marker schema != v2 (incl. legacy v1) | `reloaded_generation_unknown` | `record_invalid` | yes |
| marker readable but empty generation | `reloaded_generation_unknown` | `record_invalid` | yes |
| marker files not a dict / empty | `reloaded_generation_unknown` | `manifest_invalid` | yes |
| marker files != frozen baseline manifest | `reloaded_generation_unknown` | `manifest_mismatch` | yes |
| expected-present file missing | `reloaded_generation_unknown` | `manifest_file_missing` | yes |
| expected-present file hash mismatch | `reloaded_generation_unknown` | `manifest_hash_mismatch` | yes |
| expected-absent file present | `reloaded_generation_unknown` | `manifest_file_unexpected` | yes |
| verifier raised / file unreadable | `reloaded_generation_error` | `manifest_read_error:<Type>` | yes |
| marker missing | `reloaded_generation_unknown` | `record_unavailable` | yes |
| marker corrupt / parse error | `reloaded_generation_unknown` | `record_unavailable` | yes |
| marker reader raised | `reloaded_generation_error` | `record_read_error` | yes |
| generation baseline missing | `reloaded_generation_unknown` | `no_snapshot_baseline` | yes |
| generation baseline present but manifest baseline empty | `reloaded_generation_unknown` | `manifest_no_baseline` | yes |
| volume root dir missing | `reloaded_generation_unknown` | `mount_missing` | yes |
| no reload callback configured | `legacy_path` | `unconditional` | n/a — byte-identical no-op |

The skip is a single local marker read + compare + tiny file hashes (+ one `os.path.isdir`);
the reload branches call the callback byte-identically to the previous unconditional path (same
`variance_stage("runtime_state")` wrapper, same `reload_runtime_state_start/end` trace events).

## 8. 900 s cert reload interaction (unchanged by rev 2)

Traced end-to-end:

- `_RUNTIME_STATE_VOLUME_RELOADED_MONO` is **set only** inside the `reload_runtime_state`
  closure (modal_app.py:7723-7724) — i.e. a stamp meaning "a remote Volume reload actually
  executed in this session".
- It is **read only** by `_read_v2_validation_certificate_for_snapshot` (modal_app.py:1833-1835),
  which skips its own redundant Volume reload when the stamp is < 900 s old (saves ~10 s at
  snapshot startup). That helper is **startup-only**: its sole call site is modal_app.py:8245
  (cert-snapshot retention during construction); it is never called from `restore()`.
- The 900 s policy therefore gates **certificate retention at construction startup**, not any
  restore-time consumer.

Consequences of the guard (rev 1 and rev 2 identical here):

1. **Skip path does not invoke the reload callback** → `_RUNTIME_STATE_VOLUME_RELOADED_MONO`
   is never falsely populated. The 900 s dedup keeps its exact meaning ("remote reload
   happened") and remains correct at every construction.
2. **Construction-time startup reload is untouched** (runtime_bootstrap.py startup still runs
   unconditionally) → the cert-retention dedup at construction behaves exactly as today.
3. In a restored container the marker's in-heap value is whatever construction left; no
   restore-time consumer reads it, so a restore-time skip cannot change any 900 s behavior.
4. If a future consumer ever treats "generation+manifest proven locally" as reload freshness,
   that must be a deliberate new semantic — the guard deliberately exposes
   `runtime_state_reload_invoked=0` on skip so downstream code can distinguish
   "freshness proven locally" from "remote reload executed".

Generation/manifest freshness (local proof) and remote-reload execution (callback invocation)
are therefore kept as distinct facts in the instrumentation.

## 9. Fail-closed cases

All of the following reload exactly as before: missing marker, corrupt marker, parse error,
non-v2/legacy v1 marker, empty generation, marker files missing/invalid, marker files !=
baseline manifest, any manifest file missing (expected-present), hash mismatch, unexpected
present file (expected-absent), verifier exception / unreadable file, unknown generation
(no baseline), empty manifest baseline, mount dir missing, reader exception, unresolvable
marker path. `BootstrapState.snapshot_runtime_state_generation` defaults to `""` and
`snapshot_runtime_state_manifest` defaults to `{}`, so any path that never captured a baseline
(all existing tests, any caller of `restore()` without the construction finalize) fails closed
to the legacy reload. The guard never raises: `_decide_runtime_state_reload`,
`finalize_runtime_state_generation` and the local verifier swallow their own exceptions and
record them in the diagnostic reason. A bootstrap without a `reload_runtime_state` callback
behaves byte-identically to the legacy no-op (`legacy_path`).

## 10. No-RPC proof

- The marker writer/reader/manifest builder/verifier are pure `os`/`json`/`hashlib` local
  filesystem operations on the mounted volume — no `Volume.*` API, no Modal client, no network.
- The skip branch calls no volume API and no callback; its only side effects are one local
  marker read, ≤2 tiny local file hashes, one `os.path.isdir()`, one print line and one trace
  event.
- Test `test_guard_performs_no_remote_io` asserts on the skip path: the reload callback is
  never invoked, the local reader runs exactly once, the local verifier runs exactly once.
- There is no freshness RPC replacing the reload (a network check would defeat the
  optimization). Freshness is judged by the construction-written marker + the exact content
  manifest — no remote operation participates in the decision.

## 11. Instrumentation

One compact line + one trace event per restore, mirroring the Batch A models pattern:

- Restore: `[v2.runtime_state_volume_restore] decision=… reason=… callback_called=0|1 runtime_state_reload_invoked=0|1 check_ms=…`
  + trace event `runtime_state_reload_decision` (same metadata).
- Construction (once per build): `[v2.runtime_state_generation_baseline] source=… generation=… files=<count> write_ms=…`
  + trace event `runtime_state_generation_baseline` (source, generation, files, write_ms,
  fail_closed_reload).
- `opt_restore_decomposition` (opt-gated) additionally carries `runtime_state_reload_check_ms`,
  `runtime_state_reload_decision`, `runtime_state_reload_invoked`.

Exposed fields: `runtime_state_reload_decision` ∈ {`skipped_generation_match`,
`reloaded_generation_mismatch`, `reloaded_generation_unknown`, `reloaded_generation_error`,
`legacy_path`}, `runtime_state_reload_check_ms`, `runtime_state_reload_invoked`.

**`reload_runtime_state_ms` accuracy on skip:** the timer wrapper (modal_app.py:7702-7712)
accumulates only when the wrapped callback runs; on a skip it is never touched, so the
`_REQUIRED_RESTORE_STAGES` merge (modal_app.py:10810-10820) reports
`reload_runtime_state_ms=0.0`, `reload_runtime_state_invoked=False`,
`reload_runtime_state_reason="not_invoked"` — local-check-only, no fake timing. No modal_app.py
edit is required for this.

## 12. Tests

New file `tests/test_runtime_state_reload_guard.py` (unittest style, **32 tests**, all
passing). All Batch B1 rev-1 scenarios preserved (adjusted to schema-v2 semantics) plus the
rev-2 content-manifest scenarios:

1. `test_generation_and_manifest_match_skips_reload` — generation match + all file hashes match → skip
2. `test_match_but_expected_file_missing_reloads` — generation match + `gpu_capacity_frozen.json` missing → reload (`manifest_file_missing`)
3. `test_match_but_expected_file_content_changed_reloads` — generation match + content mismatch → reload (`manifest_hash_mismatch`)
4. `test_match_but_marker_manifest_mismatch_reloads` — generation match + marker manifest ≠ baseline manifest → reload (`manifest_mismatch`)
5. `test_expected_absent_file_present_reloads` — expected-absent file unexpectedly present → reload (`manifest_file_unexpected`)
6. `test_stale_generation_identical_files_reloads` — stale generation + identical file contents → reload (`generation_mismatch`)
7. `test_corrupt_content_manifest_reloads` — marker `files` not a dict → reload (`manifest_invalid`)
8. `test_file_read_exception_reloads` — verifier raises → reload (`manifest_read_error:RuntimeError`)
9. `test_old_v1_marker_reloads_fail_closed` — legacy schema-v1 marker → reload (`record_invalid`); plus `test_marker_without_files_manifest_reloads`
10. `test_guard_performs_no_remote_io` — skip path: only the local reader + verifier run, callback never called
11. `test_skip_never_invokes_reload_callback` — skip ⇒ zero callback invocations (⇒ 900 s stamp never falsely populated); `test_reload_path_invokes_callback_exactly_once`
12. `test_check_cost_reported_honestly` (check_ms reported, < 100 ms CI-safe bound) + `test_local_check_microbenchmark` (measured ≈ **0.36 ms** median per check, 50 checks)

Plus preserved rev-1 coverage: generation mismatch, missing/corrupt/invalid-schema/empty-gen/
reader-exception markers, no baseline, `manifest_no_baseline`, mount missing, legacy no-callback
paths, finalize baseline capture (incl. `present=false` for absent gpu file), finalize
fail-closed (required file missing / writer exception / path unavailable), full
finalize→restore skip roundtrip, diagnostic reason accuracy.

Verification run: `python -m pytest tests/test_runtime_state_reload_guard.py -q` → **32/32 OK**.
Regression: `python -m pytest tests/test_runtime_bootstrap.py tests/test_models_volume_reload_guard.py -q`
→ **30/30 OK** (Batch A guard unaffected). No Modal deploys or runs were performed.

## 13. modal_app integration patch (REQUIRED — one call site)

The marker must be written **after the final correctness-relevant runtime-state write** and
**before snapshot capture**.

- **Semantic insertion point (authoritative):** in `ModalRuntimeEntrypoint.startup()`, after
  `maybe_freeze_snapshot_gpu_capacity()` (the last correctness-relevant runtime-state write:
  `gpu_capacity_frozen.json`) and before the enter-hook returns (snapshot capture). The
  integration agent must verify no later runtime-state writer exists in the current checkout
  before placing the call.
- **Current location (secondary info, verified on this checkout):** immediately after the
  freeze block at `comfymodal_runtime/modal_app.py:8993-8996` (the gated allocator-hygiene
  block at :8998-9016 is memory-only; startup returns at :9038-9045; nothing writes the
  runtime-state volume after :8996). Re-verify if modal_app.py drifts.
- **Call:**
  ```python
  # ── Batch B: runtime-state generation marker + content manifest ──
  # (final construction write; fail-closed baseline; non-fatal)
  try:
      self.bootstrap.finalize_runtime_state_generation(trace=trace)
  except Exception:
      pass
  ```
- **Arguments:** `trace=trace` (optional; `RuntimeTrace | None`).
- **Expected return:** `str` — the captured generation (ignored by the caller; diagnostics
  printed/emitted inside). The content manifest is frozen into `BootstrapState` internally.
- **Ordering:** after `maybe_freeze_snapshot_gpu_capacity()`, before any later startup work and
  before the enter-hook returns (snapshot capture). Write-order ("marker last") remains a
  useful secondary property; the primary proof is the content manifest (§16).
- No other modal_app.py change is required: the marker path derives from
  `BootstrapConfig.prescan_record_path`'s directory (already `{RUNTIME_STATE_PATH}/...`), and
  the skip-side `reload_runtime_state_ms=0.0 / _invoked=False / _reason="not_invoked"`
  reporting needs no change (§11).

Without this patch the guard is inert (no baseline captured → every restore reloads as today),
which is safe but gains nothing.

## 14. Expected saving

- **Expected median saving: ~82 ms per restored request** (measured `reload_runtime_state`
  median, 10-run cohort; tail up to 263.8 ms when the reload engages on the skip path).
  Combined with the Batch A models guard: ~179 ms median.
- Skip-path cost: one local marker read + compare + ≤2 tiny file hashes + one `os.path.isdir()`.
  Measured **≈ 0.36 ms** median per check (50-check microbenchmark in `test_local_check_microbenchmark`)
  — the `runtime_state` restore stage drops from ~82 ms to <1 ms on the exact-match path.
  Files involved are 0.1–0.4 KB each; hashing is µs-scale. `dependency_manifest/immutable_manifest.json`
  is deliberately NOT hashed (not on the /mnt mount in V2; see §2) — no large-file hash cost is
  introduced. No >10 ms request-path verifier exists.
- Worst case (deployments without the integration patch, or marker absent): every restore
  reloads as today — zero behavior change, zero regression.

## 15. Decision

**READY.** A safe local construction-time generation identity exists and now carries a content
manifest: skip requires exact generation match AND exact local construction-state manifest
match (expected-present files exist with matching sha256; expected-absent files remain absent).
Any missing/unexpected/hash-mismatched/unreadable/unknown state reloads exactly as before; the
guard performs no remote I/O; the 900 s cert-reload dedup semantics are preserved (skip never
stamps the monotonic reload marker); `reload_runtime_state_ms` stays truthful on skip (0.0 /
`not_invoked`). One documented modal_app.py integration call is required to activate the marker
write at construction (semantic boundary: after the final correctness-relevant write, before
snapshot capture; current location modal_app.py:8996, §13); the later integration agent owns
modal_app.py and applies it.

## 16. Content-based freshness proof (rev 2)

The rev-1 proof relied on write-order monotonicity: "the marker is written last, therefore
marker visibility on the restored mount proves all earlier construction files are visible."
Rev 2 keeps that as a **secondary** property only.

**Primary proof = exact generation + exact local construction-state manifest:**

- At construction, `finalize_runtime_state_generation` locally reads and sha256-hashes the
  correctness-relevant construction files on the runtime-state Volume mount
  (`prescan_custom_nodes.json` required; `gpu_capacity_frozen.json` optional, recorded
  `present=false` when absent), stores the manifest inside the schema-v2 marker, and freezes
  both generation and manifest into `BootstrapState` (snapshot heap).
- At restore, the skip predicate is `generation_match AND content_manifest_match`, evaluated
  purely locally: the marker must be schema v2, its generation must equal the baseline, its
  files manifest must equal the frozen baseline, and every expected-present file must exist
  with matching sha256 while every expected-absent file stays absent.
- Consequences:
  - A missing earlier file with a matching marker **reloads** (`manifest_file_missing`).
  - A changed earlier file with a matching marker **reloads** (`manifest_hash_mismatch`).
  - A stale generation with matching files **reloads** (`generation_mismatch`).
  - An unexpectedly present file (construction said absent) **reloads**
    (`manifest_file_unexpected`).
- Correctness never depends on cross-file write-order visibility being honored by the Modal
  mount; it depends only on the mount's content matching the construction-time manifest for
  the enumerated correctness-relevant files.

---

## Completion output

```
report path = V2_BATCH_B_RUNTIME_STATE_RELOAD_GUARD_REPORT.md
changed files = comfymodal_runtime/runtime_bootstrap.py, comfymodal_runtime/runtime_generation.py, tests/test_runtime_state_reload_guard.py, V2_BATCH_B_RUNTIME_STATE_RELOAD_GUARD_REPORT.md
commit = none
deploy count = 0
Modal runs = 0

generation marker retained = YES
content manifest added = YES
correctness-relevant construction files enumerated = YES (prescan_custom_nodes.json, gpu_capacity_frozen.json; dependency manifest excluded — not on the /mnt mount in V2)

skip requires generation match = YES
skip requires content manifest match = YES
write-order monotonicity required for correctness = NO (secondary property only)

missing earlier file with matching marker reloads = YES (manifest_file_missing)
changed earlier file with matching marker reloads = YES (manifest_hash_mismatch)
stale generation with matching files reloads = YES (generation_mismatch)

guard remote I/O = NO
900s semantics preserved = YES

local check expected cost = ~0.36 ms median (microbenchmarked; CI bound < 100 ms) vs ~82 ms remote reload
modal_app integration semantic boundary = after final correctness-relevant runtime-state write (gpu_capacity_frozen.json), before snapshot capture; current location: after modal_app.py:8996 (re-verify if drifted)

runtime-state guard status = READY
ready for integration = YES
```
