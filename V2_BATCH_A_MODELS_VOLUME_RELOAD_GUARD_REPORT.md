# V2 — Batch A: Models-Volume Reload Guard (skip redundant `reload()` on restored generation requests)

Date: 2026-08-14
Owner lane: Batch A (runtime_bootstrap.py + comfyapp.py ownership; test file added)
Status: READY FOR INTEGRATION
No commit, no deploy, no Modal runs.

---

## 1. Existing unconditional path

The V2 restore lifecycle runs `ModalRuntimeEntrypoint.restore()` (`comfymodal_runtime/modal_app.py:9422`) →
`RuntimeBootstrap.restore(trace)` (`comfymodal_runtime/runtime_bootstrap.py:1589`). Step 4 of that method
previously invoked the reload callback unconditionally:

- `runtime_bootstrap.py` (pre-change, ~`:1787-1796`):
  ```python
  # ── 4. reload_models ──
  def _do_reload_models():
      ...
      if self.reload_models:
          self.reload_models()
  with variance_stage(trace, stage="models", phase="restore"):
      _do_reload_models()
  ```
- The callback is physically defined in `modal_app.py` (`_configure_runtime`, `:7541-7544`):
  ```python
  def reload_models() -> None:
      volume = getattr(module, "vol", None)
      if volume is not None:
          volume.reload()
  ```
  i.e. one Modal network Volume `reload()` RPC per restored request. Measured cost: median **97.0 ms**
  (range 68.7–388.2 ms, 10-run cohort, `V2_RESULT_HANDOFF_RESTORE_AND_SETUP_RESEARCH.md` §7).

The guard is implemented entirely in `runtime_bootstrap.py`; **no `modal_app.py` change is required**
(see §9).

## 2. Existing generation identity (reused, not invented)

The existing `models_generation.json` contract lives in `comfyapp.py` (legacy ComfyAPI module) and was
**already the intended comparison mechanism** (`_should_reload_models_volume`, `comfyapp.py:20415`,
unused by the V2 bootstrap path):

- Record file: `/root/custom_nodes_vol/.comfymodal_control/models_generation.json`
  (`MODELS_GENERATION_CONTROL_DIR`, `comfyapp.py:1732`) — stored on the **custom-nodes Volume**,
  mounted read-only at restore.
- Schema v1: `{"schema_version": 1, "generation": <uuid hex>, "updated_at_unix": ..., "reason": ...}`.
- Writers: `_write_models_generation_record` (`comfyapp.py:1778`) — deploy/construction-time only
  (single-use protocol: no writers between snapshot capture and request).
- Readers: `_read_models_generation_record` (`comfyapp.py:1749`) — returns `None` on missing file,
  parse error, wrong schema, or empty/non-string generation (fail-closed reader semantics);
  `_current_models_generation_id` (`:1802`).
- Legacy compare: `ComfyAPI.restore()` Phase 2/3/4 (`comfyapp.py:20540-20631`) compares the mounted
  record against `self._models_generation_seen` and reloads only on `generation_changed` /
  `generation_missing` / `mount_missing`.

This Batch A guard reuses exactly this record and the same comparison semantics (exact string match on
the `generation` field + mount-existence check). No second identity format was created.

## 3. Exact guard semantics

New in `runtime_bootstrap.py`:

1. **Construction-time baseline capture** — `RuntimeBootstrap.startup()` now calls
   `_capture_models_generation_baseline(trace)` (inserted after `sync_custom_nodes`, `:1302-1307`),
   which reads the mounted record via the injected reader (or the default
   `_default_models_generation_reader`, which resolves comfyapp's existing
   `_read_models_generation_record` through `sys.modules` — no import cost in the V2 runtime, no RPC)
   and freezes the value into the snapshot heap: `BootstrapState.snapshot_models_generation`
   (`:316-319`). Any read problem leaves the baseline empty.

2. **Restore-time decision** — step 4 now runs `_decide_models_reload()` (`:1489-1534`) before the
   callback. Decision table:

   | condition | decision | reload? |
   |---|---|---|
   | baseline captured AND mounted record == baseline AND mount dir exists | `skipped_generation_match` | **no** |
   | mounted record != baseline | `reloaded_generation_mismatch` | yes (existing call) |
   | no baseline (non-snapshot start / capture failed / reader absent) | `reloaded_generation_unknown` (reason `no_snapshot_baseline`) | yes (legacy path preserved) |
   | record missing (`None`) | `reloaded_generation_unknown` (reason `record_unavailable`) | yes |
   | record corrupt (empty/invalid generation) | `reloaded_generation_unknown` (reason `record_invalid`) | yes |
   | reader raised | `reloaded_generation_unknown` (reason `record_read_error`) | yes |
   | mount directory missing | `reloaded_generation_unknown` (reason `mount_missing`) | yes |
   | no reload callback configured (`reload_models is None`) | `reloaded_generation_unknown` (reason `unconditional`) | n/a — no-op exactly as before |

   The skip is a single comparison + one `os.path.isdir()`; the reload branches call the callback
   byte-identically to the previous unconditional path (same `variance_stage("models")` wrapper, same
   `reload_models_start/end` trace events).

3. Only the exact-match restored-container case changes behavior. Everything else preserves the
   existing unconditional reload (non-snapshot starts, reusable containers, mismatch, missing/corrupt
   metadata, tests, shadow configurations).

## 4. Fail-closed cases

All of the following reload exactly as before (enumerated in §3): missing marker, corrupt marker,
parse/schema error, mismatched generation, unknown generation (no baseline), mount missing, reader
exception, reader not injectable. `BootstrapState.snapshot_models_generation` defaults to `""`, so any
code path that never captured a baseline (including all existing tests and any future caller of
`restore()` without `startup()`) fails closed to the legacy reload. The guard itself never raises:
`_decide_models_reload` and `_capture_models_generation_baseline` swallow reader exceptions and record
them in the diagnostics reason.

## 5. No-RPC proof

The guard performs **zero** Modal/network operations:

- `_default_models_generation_reader` is a `sys.modules` lookup (comfyapp is already imported before
  bootstrap use in the V2 runtime) + a call to `comfyapp._read_models_generation_record`, which is
  `os.path.isfile` + `open` + `json.load` on the mounted custom-nodes Volume filesystem — a local
  read, no `vol.reload()`, no RPC.
- The skip branch calls no volume API at all; the only side effects are the decision print/trace event.
- Test `test_guard_performs_no_remote_io` asserts the reload callback is never invoked and the reader
  is called exactly once on the skip path.

There is no freshness RPC replacing the reload: freshness is judged by the same local record the
legacy restore already uses. (A network freshness check would defeat the optimization; none exists.)

## 6. Restored-container (snapshot) reasoning

Why an exact generation match is sufficient in the single-use snapshot architecture:

- **Single-use protocol** (`V2_RESULT_HANDOFF_RESTORE_AND_SETUP_RESEARCH.md` §9.1): nothing writes the
  models Volume between snapshot capture and request — deploy-time writes happen before construction.
  Every deploy-time write bumps the generation record atomically with the content
  (`_write_models_generation_record` commits with the publish lane).
- **Same token ⇒ same content**: identical `generation` values therefore imply the mounted models set
  is the one the snapshot was built against. This is precisely the existing legacy contract
  (`_should_reload_models_volume`); the guard reuses it verbatim instead of asserting
  "snapshot mounts are always current" (which the frozen-VRAM mount-lag case already proved false for
  the runtime-state volume).
- **Both mount semantics are sound**:
  - Restored mount reflects current committed state: record == baseline means no deploy wrote since
    construction → content matches the snapshot → reload is redundant.
  - Restored mount is a construction-era attach: the record equals the baseline by construction and the
    mounted content is construction-era → still consistent with the snapshot → reload is redundant.
  - Only a generation change (a real deploy write) forces the reload — the exact set of cases where
    content could differ.
- The baseline rides in the **memory snapshot heap** (`BootstrapState`), so it is the construction-time
  truth, not a request-time guess.

## 7. Diagnostics added (compact, existing style)

One line per lifecycle event, mirroring the `[v2.custom_node_restore]` / `[v2.sage_restore]` pattern:

- Startup (once per construction): `[v2.models_volume_baseline] source=… generation=<12> read_ms=…`
  + trace event `models_generation_baseline` (metadata: source, generation, read_ms,
  fail_closed_reload).
- Restore (once per request): `[v2.models_volume_restore] decision=… reason=… callback_called=0|1
  check_ms=…` + trace event `models_reload_decision` (same metadata).
- `restore_decomposition` (opt-gated, full artifacts) additionally carries `models_reload_check_ms`
  and `models_reload_decision`.
- **`reload_models_ms` accuracy on skip**: the wrapped callback timer (`_RESTORE_STAGE_TIMERS`,
  `modal_app.py:7529-7539`) is never touched on a skip, so the existing `_REQUIRED_RESTORE_STAGES`
  merge (`modal_app.py:10617-10627`) reports `reload_models_ms=0.0`, `reload_models_invoked=False`,
  `reload_models_reason="not_invoked"` — i.e. local-check-only, never a fabricated remote time. No
  modal_app.py edit needed; the field set already models the skipped case.

No high-volume logging: exactly one decision line + one trace event per restore, one baseline line per
construction.

## 8. Tests

New file `tests/test_models_volume_reload_guard.py` (unittest style, 13 tests, all passing):

1. `test_exact_generation_match_skips_reload` — match → no callback, reader called once
2. `test_generation_mismatch_reloads` — mismatch → reload, decision `reloaded_generation_mismatch`
3. `test_missing_record_reloads` — reader `None` → reload, `record_unavailable`
4. `test_corrupt_record_reloads` — empty generation → reload, `record_invalid`
5. `test_reader_exception_reloads` — reader raises → reload, `record_read_error`
6. `test_no_snapshot_baseline_reloads` — no capture → reload, `no_snapshot_baseline` (non-snapshot path unchanged)
7. `test_mount_missing_reloads` — match but mount dir absent → reload, `mount_missing`
8. `test_guard_performs_no_remote_io` — skip path: only the local reader runs, callback never called
9. `test_diagnostic_reason_accurate` — decision/reason/callback_called on the printed line
10. `test_bare_bootstrap_no_callbacks_unchanged` — no-callback bootstrap → no-op, `callback_called=0`
11. `test_capture_baseline_sets_state` / `test_capture_baseline_fail_closed` /
    `test_capture_baseline_exception_fail_closed` — startup baseline capture semantics

Verification run: `python run_tests.py tests.test_models_volume_reload_guard` → **13/13 OK**;
regression `python -m pytest tests/test_runtime_bootstrap.py -q` → **17/17 OK**. No Modal deploys or
runs were performed.

## 9. Integration patch outside ownership

**None required.** The guard is fully contained in `runtime_bootstrap.py`; the default reader resolves
the existing `comfyapp._read_models_generation_record` via `sys.modules` (comfyapp is imported before
bootstrap use in the V2 runtime). `modal_app.py` was not modified.

*Optional* hardening (only if the integration agent wants to remove even the lazy lookup):
in `modal_app.py` `_configure_runtime` (`:7832-7845`), add one keyword argument to the
`RuntimeBootstrap(...)` constructor call:

- Function name: `RuntimeBootstrap.__init__` parameter `read_models_generation_record`
- Old call: `..., read_current_custom_node_identity=read_current_custom_node_identity,`
- New call: `..., read_current_custom_node_identity=read_current_custom_node_identity, read_models_generation_record=module._read_models_generation_record,`
- Expected argument: `Callable[[], dict | None]` returning the parsed record dict (or `None`)
- Expected return: unused by the caller; consumed by `_decide_models_reload` / `_capture_models_generation_baseline`

## 10. Measured expected saving

- **Expected median saving: ~97 ms per restored request** (measured `reload_models` median from the
  10-run cohort; tail up to 388 ms when it engages on the skip path).
- Skip-path cost: one local file read + compare ≈ 0.002–0.05 ms (`check_ms`), i.e. the `models` stage
  drops from ~97 ms to <1 ms on the exact-match path.
- Worst case (record absent in a deployment that never seeds `models_generation.json`): every restore
  reloads as today — zero behavior change, zero regression; the guard engages only when the existing
  contract is present, which is the documented production state.

---

## Completion output

```
report path = V2_BATCH_A_MODELS_VOLUME_RELOAD_GUARD_REPORT.md
changed files = comfymodal_runtime/runtime_bootstrap.py (+184/-2), tests/test_models_volume_reload_guard.py (new)
commit = none
deploy count = 0
Modal runs = 0

existing generation identity reused = YES
exact match skips remote reload = YES
mismatch reloads = YES
unknown reloads = YES
guard performs remote I/O = NO
modal_app integration patch required = NO (optional hardening documented in §9)

expected median saving = ~97 ms
ready for integration = YES
```
