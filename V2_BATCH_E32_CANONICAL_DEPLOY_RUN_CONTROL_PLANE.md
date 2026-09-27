# V2 Batch E32 — Canonical Deploy/Run Control Plane (v2ctl)

**Status:** LOCAL READY — `E32_V2CTL = READY_FOR_REMOTE_PARITY_GATE`  
**Remote activity:** `REMOTE_DEPLOYS = 0`, `REMOTE_REQUESTS = 0`, `SNAPSHOT_CREATIONS = 0`  
**Date:** 2026-08-19  
**Branch:** `TESTING2`

---

## 1. Starting Git State

- HEAD: `0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997` (e28: critical-path implementation)
- Branch: `TESTING2`
- Dirty at start: E29 (comfymodal_runtime/* critical-path ledger, gantt, modal_app), E30 (clip_qd_reader, clip_forward_forensics), E31 (clip_fp32_cast_once, runtime_bootstrap/executor, speculative_clip_hydration) modifications + their untracked reports/tests, plus `tools/benchmark_v2_direct.py` and taste files.
- **No E29/E30/E31 concurrent changes were overwritten.** `git status` at the end shows E32 added only: `config/`, `docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md`, `tools/v2_control/`, `tools/v2ctl.py`, `tests/test_v2ctl_*.py`, `tests/v2ctl_fakes.py`, and a 3-line `.gitignore` addition. No commits, no stash, no reset, no branch/worktree created.

---

## 2. Phase-0 Audit — Current Deploy/Run Call Graph (exact answers)

| Question | Answer |
|---|---|
| `CURRENT_CANONICAL_DEPLOY_PATH` | `deploy_and_run_v2_single.bat` (combined deploy+run; deploy-only exists only as `COMFYMODAL_DEPLOY_ONLY=1`, line 904; `snapshot_restore_only` mode exits after construction, line 1020) |
| `CURRENT_CANONICAL_RUN_PATH` | `run_v2_single.bat` → `tools/benchmark_v2_direct.py` (request harness) |
| `CURRENT_DEPLOY_ONLY_PATH` | **None standalone.** Only `deploy_and_run_v2_single.bat` + `COMFYMODAL_DEPLOY_ONLY=1` |
| `CURRENT_COMBINED_DEPLOY_RUN_PATH` | `deploy_and_run_v2_single.bat` |
| `FLAG_WHITELIST_LOCATION` | `comfymodal_runtime/modal_app.py:562` `_REQUEST_DIAGNOSTIC_ENV_ALLOWLIST` (request-carried env allowlist, ~26 keys) and `comfymodal_runtime/modal_app.py:2941` `_runtime_env()` (deploy-time class-`env=` allowlist) |
| `REQUEST_ENV_FORWARDING_LOCATION` | `tools/benchmark_v2_direct.py:134` `_EXPERIMENT_ORIGIN_OVERRIDES` → `modal_app.py:663` `_apply_request_variance_diagnostics` → `os.environ` (request scope) |
| `DEPLOY_ENV_FORWARDING_LOCATION` | `deploy_and_run_v2_single.bat` env pins + `modal_app.py:2941` `_runtime_env()` → Modal `cls(env=...)` (baked at deploy) |
| `RUNTIME_FILE_OVERRIDE_LOCATION` | `comfyapp.py:3432` `_resolve_runtime_flag` / `:3452` `_resolve_runtime_string` reading `<RUNTIME_CONFIG_DIR>/<NAME>.txt`; `RUNTIME_CONFIG_DIR = "/root/comfymodal_runtime_state"` (`comfyapp.py:1721`); `set_runtime_flag` `comfyapp.py:8686`, `clear_runtime_flag` `:8724`, `clear_runtime_flags` `:8743`; `benchmark_modal.py:36` `_call_set_runtime_flag` |

Call graph (current):

```text
deploy_and_run_v2_single.bat
 ├─ python tools/benchmark_v2_direct.py --verify-*  (pre-deploy profile gates)
 ├─ publish_custom_nodes_volume.py / record_deployment_identity.py
 ├─ modal deploy -m comfymodal_runtime.modal_app --name <APP>   (or concurrent V1+V2)
 └─ python tools/benchmark_v2_direct.py --run-count N [--conditioning-cache-nonce X]
run_v2_single.bat
 └─ python tools/benchmark_v2_direct.py [--verify-run-preflight] [--run-count N] [args]
```

Other scripts invoking Modal deploy: `deploy_and_benchmark_v2_shadow.bat`, `deploy_v2_full_trace_only.bat`, `run_transfer_ab.bat`, `deploy_and_run_backing_ab.py`, `deploy_and_run_provider_ab.py`, `deploy_and_run_region_ab.py`, plus per-batch one-off `.bat`/wrappers (the failure mode E32 eliminates).

---

## 3. Files Changed / Created

**New modules (`tools/v2_control/`):** `__init__.py`, `errors.py`, `registry.py`, `profiles.py`, `config.py`, `environment.py`, `fingerprints.py`, `backend.py`, `locking.py`, `runtime_overrides.py`, `validation.py`, `provenance.py`, `cli.py`.

**New entrypoint:** `tools/v2ctl.py` (thin; all logic in `v2_control`).

**New config:** `config/v2/flag_registry.toml` (98 registered flags — metadata, not admission), `config/v2/profiles/{production,e29-tracer,e30-clip-qd,e31-clip-fp32}.toml`.

**New tests (11 files, 310 tests):** `tests/test_v2ctl_{registry,profiles,config,environment,fingerprints,backend,locking,runtime_overrides,validation,provenance,cli}.py` + `tests/v2ctl_fakes.py`.

**Docs:** `docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md` (byte-identical mirror of the authoritative root design doc, SHA256 `0cf40d0b…`), `V2_BATCH_E32_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md` (this report).

**Modified:** `.gitignore` (added `.v2ctl/`). **No other existing file touched.**

---

## 4. Architecture

- `registry.py` — typed flag metadata (bool/int/float/string/enum/path/json, min/max, enum_values, regex, aliases, deprecated), lifecycle axes, `audit()` lint. **Metadata, not an admission whitelist.**
- `profiles.py` — TOML profiles, max one parent (`extends`), cycle detection, child-wins merge.
- `config.py` — resolution with exact precedence: defaults → parent → child → CLI options → `--inherit` → `--set`. Ambient shell env is **never** merged. `compute_git_state` hashes deploy-relevant dirty paths (`comfymodal_runtime`, `comfyapp.py`, `tools/benchmark_v2_direct.py`, `config/v2`). `check_run_safety(run_only=True)` refuses explicitly-changed deploy-required flags + explicit unregistered flags.
- `environment.py` — sanitized child env: required host vars + auth vars (present only) + resolved flags + backend extras; ambient `COMFYMODAL_*`/`V2_*` never leak; protected names refused on explicit channels; `display()/provenance_env()` redact secrets.
- `fingerprints.py` — deterministic deploy/run fingerprints (sha256 of canonical JSON).
- `backend.py` — wraps the known-good BATs via subprocess (win32: quoted BAT + `list2cmdline` args, explicit child env; posix: argv list), exit-code/stdout/stderr/timing capture, artifact discovery (`.comfymodal_experiments`, `.experiments`, `comfymodal-runtime`, `output`, `output/studio`, stdout `output_dir` lines).
- `locking.py` — `.v2ctl/deploy.lock` (owner/pid/host/target/profile/timestamp), atomic `O_EXCL` acquire, evidence-based staleness (pid liveness; foreign-host + age), explicit force only.
- `runtime_overrides.py` — local inventory of `.runtime_state/*.txt` flag files, `policy=forbid` default, explicit clear commands, remote lister seam (never invoked in this phase).
- `validation.py` — generic structural validators + plug-in seam (`ValidatorPlugin`); `GateRunner` runs exactly one cold run; `ConfirmRunner` refuses invalid/stale gates.
- `provenance.py` — effective-config provenance block, written as `<artifact>.v2ctl-provenance.json` siblings (never modifies E29/E30/E31 artifacts); deferred remote hook documented.
- `cli.py` / `v2ctl.py` — commands: `doctor`, `config`, `flags {list,explain,validate,audit}`, `deploy`, `run`, `deploy-run`, `gate`, `confirm --from <gate>`, `runtime-flags {list,clear,clear-all}`, `lock {status,acquire,release,force-release}`, `version`. Global flags hoisted so `v2ctl run --set X=1 --dry-run` works.

---

## 5. Flag Lifecycle Model

Every registered flag carries `consumed_at` (`build|module_import|restore|method_entry|request|harness`) and `change_requires` (`build|deploy|run|none|unknown`). Lifecycle assigned from the Phase-0 audit of the actual consumer, not the name:

- **request-carried** (in `_REQUEST_DIAGNOSTIC_ENV_ALLOWLIST`, modal_app.py:562): `consumed_at=request`, `change_requires=run` (e.g. `COMFYMODAL_V2_CLIP_FASTSAFE_THREADS`, `V2_VAE_EARLY_START_MS`, `V2_UNET_PRETOUCH`).
- **deploy-baked** (`_runtime_env` / BAT pins): `consumed_at=restore|module_import`, `change_requires=deploy` (e.g. `COMFYMODAL_V2_UNET_FASTSAFETENSORS`, `V2_SPECULATIVE_CLIP_HYDRATION`, `V2_CLIP_FP32_CAST_ONCE` per design-doc example).
- **harness**: `V2_BENCHMARK_*` → `change_requires=run`; `V2_E*_VALIDATION` selectors → `change_requires=deploy` (consumed by the deploy script).

Lifecycle catches deploy-vs-run mistakes: `v2ctl run --set COMFYMODAL_V2_UNET_FASTSAFETENSORS=1` → refused (`run-only configuration refuses changed deploy-required flags`); unregistered explicit flags → `change_requires=unknown`, accepted for deploy-capable commands, refused for run-only.

---

## 6. Semantic Whitelist Removal

The old semantic whitelist (`_REQUEST_DIAGNOSTIC_ENV_ALLOWLIST`, modal_app.py:562) is **bypassed by the v2ctl path**: v2ctl never consults it — explicit flags flow through profile/env resolution → sanitized child env → canonical backend. A brand-new flag (`v2ctl deploy-run --set COMFYMODAL_V2_BRAND_NEW_EXPERIMENT=1`) is accepted, syntax-checked, recorded as `UNREGISTERED`, and forwarded, with zero registry edits. The registry is metadata for validation/lifecycle/audit; the protected denylist replaces allowlist semantics for secrets/identity. The runtime allowlist itself remains in E29-owned `modal_app.py` untouched (deferred shared edit; request-level forwarding parity is a remote-gate item).

---

## 7. Protected-Variable Policy

Discovered from the repo (not invented): `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET` (loaded from `.modal_workspaces.json` by both BATs), `MODAL_*` auth namespace, `V2CTL_*` internal namespace, target identity (`COMFYMODAL_V2_APP_NAME`, `V2_DEPLOY_IDENT`, `COMFYMODAL_V2_GPU`, `MEMORY_MB`, `CPU_REQUEST`, `BASELINE_*`), harness internals (`COMFYMODAL_COMMAND_START_UNIX_MS`, `COMFYMODAL_DEPLOY_TIMEOUT_SECONDS`), and secret markers (`TOKEN/SECRET/PASSWORD/API_KEY/CREDENTIAL` + cloud-credential regex). Explicit overrides of protected names fail loudly; secret values never printed or persisted (redaction in `display()`/`provenance_env()`). Target/resource identity is set only by v2ctl's canonical identity channel (CLI `--app/--gpu/--memory-mb/--cpu` + profile `[target]`/`[resources]`).

---

## 8. Environment Sanitization

`EnvironmentBuilder.build()` = required host vars (`PATH`, `COMSPEC`, `SYSTEMROOT`, `TEMP`, …) → auth vars (present only) → resolved flags (+unregistered) → backend extras. Ambient `COMFYMODAL_*`/`V2_*` never enter the child env unless explicitly `--inherit`/`--set`. Proven by test: host with `COMFYMODAL_V2_UNET_FASTSAFETENSORS=1` + `V2_BENCHMARK_RUNS=99` → child env still `0`/`10`.

---

## 9. Backend Invocation

v2ctl never reinvents the deploy. `deploy` → `deploy_and_run_v2_single.bat` + `COMFYMODAL_DEPLOY_ONLY=1` (truthfully labeled `deploy_only_via_env`, since no standalone deploy-only path exists); `deploy-run` → the combined BAT; `run` → `run_v2_single.bat`. Windows: `subprocess.run(f'"{bat}" {list2cmdline(args)}', shell=True, env=child_env, cwd=repo_root)`; exit code, stdout/stderr, start/end ISO timestamps, elapsed, and artifact discovery all captured. `--dry-run` prints the exact command + redacted env and exits 0 without invoking or locking.

---

## 10. Fingerprints

- **Deploy inputs:** git HEAD, dirty flag, deploy-relevant dirty file hashes, target, resources, profile name, deploy-required flags + all unregistered flags, runtime-override policy.
- **Run inputs:** deploy fingerprint + workload (fresh_required, conditioning_cache, expected SHA, run_count, gap, nonce) + run-required flags + unregistered flags.
- Tests prove: a deploy-required change alters the deploy fingerprint; a run-only change (`V2_BENCHMARK_GAP_SECONDS`) does **not** alter it but alters the run fingerprint; unregistered changes alter both (unknown is not trusted); same config → identical fingerprints across instances.

---

## 11. Runtime-Override Safety

`runtime-flags list` scans the local `.runtime_state` mirror (`<NAME>.txt`); default policy `forbid`. `deploy-run`, `run`, `gate`, `confirm` fail **before** spend when local flag files exist, printing names/values/sources and never auto-deleting. `clear NAME` / `clear --all --confirm` are explicit mutations (traversal-guarded). Remote listing is a documented seam (`remote_lister`) with no helper wired and **no remote call in this phase**; unit-tested with a lister that asserts it is never invoked unless requested.

---

## 12. Deploy Lock

`.v2ctl/deploy.lock` with owner/pid/host/target/profile/timestamp; atomic `O_EXCL` acquire; deploy/deploy-run acquire automatically; conflicting owner → nonzero `LockHeldError`; stale detection is evidence-based (dead pid on same host, or foreign host + age > 6h) — a stale lock requires explicit `force`/`force-release`, never silent steal. Smoke-verified live: acquire → conflict refused → stale detection on dead pid → force-release (logged) → none.

---

## 13. Gate / Confirm

`gate`: exactly **one** backend run (`V2_BENCHMARK_RUNS=1 --run-count 1`), generic structural validation (backend ok, artifact present, identity/freshness/SHA as configured), manifest persisted under `.v2ctl/gates/` **even when invalid**, nonzero on invalid. `confirm --from <gate>`: refuses missing/invalid/`valid=false` manifests and **stale deploy fingerprints** (rechecks deploy inputs + git head, reports changed leaves), then runs exactly the requested number of runs with structural validation per run. Batch-specific validators plug in via `ValidatorPlugin` (E29/E30/E31 not hardcoded).

---

## 14. Provenance Schema

`.v2ctl` run/deploy manifests + `<artifact>.v2ctl-provenance.json` siblings: `{schema_version, profile, owner, deploy_fingerprint, run_fingerprint, git_head, target, resources, requested_environment (redacted), effective_environment (redacted), flag_sources, unregistered_flags, runtime_overrides, workload}`. Remote emission (compact `[v2ctl.config] deploy=… run=… profile=…` line) is documented as a deferred hook (`provenance.inject_provenance_hook_doc()`) — **not applied**, because it would touch E29/E30/E31-owned runtime files.

---

## 15. CLI Examples

```text
python tools/v2ctl.py doctor
python tools/v2ctl.py config --profile e29-tracer --json
python tools/v2ctl.py flags list | flags explain COMFYMODAL_V2_CLIP_FP32_CAST_ONCE
python tools/v2ctl.py flags validate COMFYMODAL_V2_UNET_FASTSAFETENSORS=1
python tools/v2ctl.py flags audit
python tools/v2ctl.py deploy --dry-run
python tools/v2ctl.py deploy-run --set COMFYMODAL_V2_BRAND_NEW_EXPERIMENT=1
python tools/v2ctl.py run --run-count 1          # run-only; refuses deploy-required changes
python tools/v2ctl.py gate
python tools/v2ctl.py confirm --from .v2ctl/gates/gate_<ts>_<fp>.json --runs 2
python tools/v2ctl.py runtime-flags list | clear <NAME> | clear --all --confirm
python tools/v2ctl.py lock status | acquire --owner E32 | release | force-release
```

---

## 16. Exact Tests / Results

```text
python -m pytest tests/test_v2ctl_registry.py tests/test_v2ctl_profiles.py \
  tests/test_v2ctl_config.py tests/test_v2ctl_environment.py \
  tests/test_v2ctl_fingerprints.py tests/test_v2ctl_backend.py \
  tests/test_v2ctl_locking.py tests/test_v2ctl_runtime_overrides.py \
  tests/test_v2ctl_validation.py tests/test_v2ctl_provenance.py \
  tests/test_v2ctl_cli.py -q
→ 310 passed in 21.73s   (pytest 9.1.1, Python 3.11.9, Windows)
```

Covers: profile inheritance; CLI precedence; no ambient leakage; explicit inherit/`--set`; registered bool/int/float/enum/regex/min-max validation; unknown deploy accepted; unknown unsafe run refused; protected refusal + redaction; deploy/run fingerprint semantics; subprocess argv/env and exit propagation (fake `.cmd` backend); artifact discovery; runtime-override forbid/clear; lock ownership/conflict/stale/force; gate exactly one run; invalid gate blocks confirm; stale fingerprint blocks confirm (with changed-leaf reporting); SHA/fresh enforcement; flag-audit warnings; CLI integration (`config`, `flags`, `doctor`, dry-runs, lock cycle, runtime-flags). Existing E29/E30/E31 harness tests were not modified or weakened; their files were not touched.

**Live smoke:** `doctor` (git/backend/registry/profiles/lock/manifest checks), `config --profile e29-tracer` (98 flags + lifecycle + fingerprints + unregistered), `flags audit` (96 consumed+registered, 129 consumed+unregistered warnings, 2 profile-set-no-consumer — advisory lint), `deploy --dry-run` / `deploy-run --dry-run --set COMFYMODAL_V2_CLIP_FAST_HYDRATION=1` (sanitized env, identity channel, fingerprints, command line), `lock` acquire/conflict/stale/force-release cycle. All local.

---

## 17. Deferred Shared Hooks

1. **Remote provenance line** — compact `[v2ctl.config]` emission inside the runtime (would touch E29-owned `modal_app.py`); exact snippet documented in `provenance.inject_provenance_hook_doc()`, applied at the remote-parity gate.
2. **Runtime-side allowlist parity** — the request-level runtime allowlist (`_REQUEST_DIAGNOSTIC_ENV_ALLOWLIST`) is left untouched; v2ctl-side forwarding works without it, and remote proof of effective values is part of the parity gate.
3. **BAT deprecation** — old BATs remain the wrapped backend; they become v2ctl wrappers or explicitly-legacy only after parity is proven (design §20 Phase 8). Not rewritten, so E29's in-flight deploy loop is unaffected.
4. **Registry growth** — 129 consumed-but-unregistered flags surfaced by `flags audit` are candidates for registration during the parity gate.

---

## 18. Remote Parity Plan (next, with explicit permission)

1. `v2ctl doctor` parity preflight → 2. `v2ctl deploy-run` (production profile) with lock acquisition → 3. `v2ctl gate` (exactly one cold run; structural validation) → 4. inspect gate manifest/artifacts → 5. `v2ctl confirm --from <gate> --runs N` → 6. register E29/E30/E31 flags confirmed effective; wire remote provenance line; then BAT deprecation.

## 19. Zero-Remote Proof

- All commands executed were local: `git`, `python -m pytest`, `python tools/v2ctl.py doctor|config|flags|deploy --dry-run|deploy-run --dry-run|run --dry-run|runtime-flags list|lock …`, `tasklist` (lock liveness), file reads/writes.
- No `modal` CLI or Modal SDK invocation, no `deploy_and_run_v2_single.bat`/`run_v2_single.bat` execution (dry-run builds the command line only), no `.runtime_state` mutation, no network calls. `MODAL_DEPLOYS = 0`, `MODAL_REQUESTS = 0`, `SNAPSHOT_CREATIONS = 0`.

---

## 20. Final Marker

```text
E32_V2CTL = READY_FOR_REMOTE_PARITY_GATE
REMOTE_DEPLOYS = 0
REMOTE_REQUESTS = 0
```

Remote parity is **not** claimed. Per the standing rule, any future deploy/run must read `docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md` and use `python tools/v2ctl.py …` — no ad-hoc Modal SDK deploys, no direct BAT invocations, no PowerShell set chains, no whitelist edits.
