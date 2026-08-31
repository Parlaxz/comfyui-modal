# V2 Canonical Deploy/Run Control Plane Design

**Status:** Design specification  
**Project:** ComfyUI Modal V2 performance / validation tooling  
**Primary goal:** Make every deploy, run, experiment flag, cold gate, and artifact reproducible through one canonical interface so agents stop inventing one-off deployment methodology.

---

# 1. Executive Summary

The current V2 deployment/benchmark surface has grown organically across batch files, Python harnesses, environment variables, runtime flag files, diagnostic forwarding logic, and experiment-specific scripts. That has created recurring failure modes:

- agents deploy through different commands;
- flags are set in a shell but never reach the deployed runtime;
- request-time overrides are attempted for values that were consumed at import/deploy time;
- hidden runtime-volume flag files override environment values;
- new diagnostic flags must be manually added to a forwarding allowlist/whitelist;
- deployment identity, effective flags, workload, resource shape, and run artifact are not represented by one authoritative configuration;
- agents run confirmation requests after a structurally invalid first cold run;
- concurrent agents can race for the deploy target.

Replace this with one canonical control plane:

```text
python tools/v2ctl.py ...
```

`v2ctl` becomes the only supported developer/agent interface for V2 performance deploys and runs.

The existing `.bat` files may remain as compatibility backends initially, but agents must not call them directly once `v2ctl` is accepted.

---

# 2. Core Principles

## 2.1 One control plane

There must be one parser, one configuration resolver, one flag lifecycle model, one deployment path, one run path, one provenance record, and one cold-validation protocol.

No experiment should require a custom BAT file, custom PowerShell environment setup, or ad-hoc Modal SDK script.

## 2.2 Remove the semantic flag whitelist

A semantic whitelist of accepted experiment flag names is the wrong abstraction.

A new flag must **not** require edits in several forwarding locations before it can reach the runtime.

Instead:

- explicitly supplied environment variables are accepted when their names are syntactically valid;
- protected variables are rejected;
- registered variables receive typed validation and lifecycle checking;
- unregistered variables are still accepted for deploy-capable commands, but are loudly marked `UNREGISTERED`;
- run-only commands refuse unregistered overrides when the tool cannot prove they are request-time safe;
- every supplied variable is recorded in provenance;
- the remote runtime exposes enough provenance to prove which values actually became effective.

The registry is **metadata**, not an admission whitelist.

## 2.3 No ambient-shell surprises

The parent shell must not silently become experimental configuration.

`v2ctl` constructs a sanitized child environment. Only required host/tool variables, canonical project variables, profile values, explicit `--set` values, and explicit `--inherit NAME` values enter the child configuration.

## 2.4 Unknown is allowed; unknown is not trusted

Example:

```text
python tools/v2ctl.py deploy-run --set COMFYMODAL_V2_NEW_EXPERIMENT=1
```

This must not fail merely because the flag is new. It should say:

```text
UNREGISTERED FLAG:
  COMFYMODAL_V2_NEW_EXPERIMENT=1

Accepted for deploy-run.
Lifecycle/type cannot be proven.
Run-only use will be refused until registered or explicitly scoped.
```

## 2.5 Raw provenance beats launcher intent

It is not enough that a shell said `COMFYMODAL_V2_X=1`.

Every accepted run artifact must prove:

- what the caller requested;
- what `v2ctl` resolved;
- what deployment fingerprint was active;
- what the runtime observed as effective;
- where each value came from.

---

# 3. Proposed Repository Layout

```text
tools/
  v2ctl.py
  v2_control/
    __init__.py
    cli.py
    config.py
    registry.py
    profiles.py
    environment.py
    deploy.py
    run.py
    validation.py
    provenance.py
    locking.py
    runtime_overrides.py
    subprocess_backend.py

config/
  v2/
    flag_registry.toml
    profiles/
      production.toml
      diagnostics.toml
      e29-tracer.toml
      e30-clip-qd-arm-a.toml
      e30-clip-qd-arm-b.toml
      e31-clip-fp32-qd4-arm-a.toml
      e31-clip-fp32-qd4-arm-b.toml
      e31-clip-fp32-fastsafe-arm-a.toml
      e31-clip-fp32-fastsafe-arm-b.toml

docs/
  V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md
```

The exact package split may be simplified, but the responsibilities should remain separate.

---

# 4. Canonical CLI

Minimum supported commands:

```text
python tools/v2ctl.py doctor
python tools/v2ctl.py config
python tools/v2ctl.py flags
python tools/v2ctl.py deploy
python tools/v2ctl.py run
python tools/v2ctl.py deploy-run
python tools/v2ctl.py gate
python tools/v2ctl.py confirm
python tools/v2ctl.py source-probe
python tools/v2ctl.py runtime-flags
python tools/v2ctl.py lock
```

## 4.1 `doctor`

Checks, without deploying:

- repository root and git state;
- Python/tool availability;
- canonical backend scripts exist;
- profile/registry parse;
- protected variables are not overridden;
- runtime flag policy;
- current deploy lock;
- whether requested flag changes require deploy;
- whether the last deployment fingerprint matches requested configuration.

## 4.2 `config`

Prints the complete resolved configuration and exits. It must show target, resources, workload, each resolved flag, its source, registry status, lifecycle, runtime override policy, deploy fingerprint, and run fingerprint.

## 4.3 `flags`

Examples:

```text
python tools/v2ctl.py flags list
python tools/v2ctl.py flags explain COMFYMODAL_V2_CLIP_FP32_CAST_ONCE
python tools/v2ctl.py flags validate COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=1
python tools/v2ctl.py flags audit
```

`flags audit` statically reports:

- consumed + registered;
- consumed + unregistered;
- registered + no consumer found;
- profile-set + no consumer found.

It is advisory lint, not a runtime whitelist.

## 4.4 `deploy`

Deploys the resolved configuration only when a true deploy-only backend exists. It acquires the deploy lock, runs preflight, prints effective configuration, writes a deployment manifest, invokes only the canonical backend, and records the deployment fingerprint.

If the current backend actually combines deploy+run, `v2ctl` must label that truthfully until a real deploy-only path exists.

## 4.5 `run`

Runs against an already compatible deployment.

Before run:

```text
requested deploy fingerprint == active deployment fingerprint
```

must be true.

If not, refuse and list which deploy-required values changed.

## 4.6 `deploy-run`

Canonical combined workflow:

```text
resolve
→ preflight
→ acquire lock
→ deploy
→ verify deployment identity
→ run
→ persist artifacts
→ release lock
```

## 4.7 `gate`

Runs exactly **one** cold validation gate. It must never automatically run a second sample.

Generic checks:

- expected app/class/method;
- expected GPU/resource shape;
- fresh/restored identity as requested;
- requested deployment and run fingerprints;
- required flags effective;
- output SHA if configured;
- persisted artifact completeness.

A structurally invalid gate exits nonzero.

## 4.8 `confirm`

Only runs after a valid gate manifest and rechecks that source/config/deployment have not changed.

This encodes the project rule: **one cold run first; inspect/validate it; only then spend a confirmation run.**

## 4.9 `source-probe` (E29 source-identity stop-gate)

Proves, WITHOUT any generation, that the bytes the deployed GPU class actually imports equal the expected local source. This is the authoritative answer to "is the remote running my code?" — image IDs, app versions, and trace contents are NOT proof.

```text
python tools/v2ctl.py source-probe --profile e29-tracer --owner E29
```

- Invokes the deployed class's no-generation `source_identity_probe` method (registered via `_modal.method()` in `_build_decorated_v2_class` — a method wrapped only in `_METHODS_TO_WRAP` but NOT `_modal.method()`-decorated is never exposed by Modal and returns `NotFoundError`).
- Compares remote SHA-256 against expected local SHA-256 for: `modal_app.py`, `critical_path_ledger.py`, `runtime_bootstrap.py`, `runtime_executor.py`, `gantt_telemetry.py`.
- Classifies each module `MATCH` / `MISMATCH` / `MISSING` / `UNEXPECTED_PATH`; exits nonzero unless ALL match.
- Reports the ledger enable state (`COMFYMODAL_V2_CRITICAL_PATH_LEDGER`, `_ENABLED`, `record_event` presence) from inside the container.
- On PASS, flips the matching deployment manifest's `source_identity_status` from `unverified` → `verified` (deploy-health semantics: `deployment_transport_status` / `runtime_health_status` / `source_identity_status` are distinct; a deployment is fully validated only after the source probe succeeds AND a gate observes the container running).

The ONLY v2ctl command that makes a direct Modal SDK call. It uses the ACTIVE workspace credentials from `.modal_workspaces.json` (never the raw `modal` CLI profile) — see the workspace pitfall below.

---

# 5. Configuration Model

Use TOML so Python can parse it without a new dependency.

```toml
schema_version = 1
name = "e29-tracer"
extends = "production"
owner = "E29"

[target]
app = "stable-modal-comfy-v2-restore-only-shadow"
class = "ModalRuntimeEntrypointV2"
method = "run_plan_stream"

[resources]
gpu = "RTX-PRO-6000"
cpu = 12
memory_mb = 28672
min_containers = 0
scaledown_window = 4

[workload]
fresh_required = true
conditioning_cache = "forced_miss"
expected_output_sha = "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"

[environment]
COMFYMODAL_V2_E29_CRITICAL_PATH = "1"
COMFYMODAL_V2_GANTT_TELEMETRY = "1"
COMFYMODAL_V2_CLIP_QD_IO = "0"
COMFYMODAL_V2_CLIP_FP32_CAST_ONCE = "0"

[runtime_overrides]
policy = "forbid"
```

---

# 6. Configuration Precedence

Use exactly:

```text
built-in v2ctl defaults
    ↓
base profile (`extends`, max one parent)
    ↓
selected profile
    ↓
explicit CLI options
    ↓
explicit `--set NAME=VALUE`
```

Ambient shell environment is **not** an experiment layer.

Runtime-volume flag files are a separate state channel and do not silently participate.

---

# 7. Flag Registry: Metadata, Not Whitelist

Example:

```toml
[[flag]]
name = "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"
type = "bool"
default = "0"
consumed_at = "module_import"
change_requires = "deploy"
owner = "clip"
description = "Persist compute-ready FP32 CLIP weights."
```

## 7.1 Two lifecycle axes

Each flag records:

### `consumed_at`

Where the code reads/uses it:

```text
build
module_import
restore
method_entry
request
harness
```

### `change_requires`

What action is required for a changed value to take effect:

```text
build
deploy
run
none
unknown
```

A flag may be consumed during restore while still requiring deployment to change because its environment value was captured by the deployed runtime.

## 7.2 Types

Support:

```text
bool
int
float
string
enum
path
json
```

with optional min/max, enum values, regex, aliases, and deprecation metadata.

## 7.3 Unregistered flags

An explicit unregistered flag:

- is not rejected solely for being unknown;
- is syntax checked;
- is checked against protected names;
- is recorded;
- receives `change_requires=unknown`;
- may be used by `deploy` / `deploy-run`;
- may not be used by `run` unless its lifecycle is registered or explicitly proven safe.

---

# 8. Protected Variables Instead of Whitelist

Use a small protected/deny policy for:

- credentials/secrets;
- Modal/cloud authentication;
- internal v2ctl provenance/fingerprint variables;
- app/class/method identity controlled by dedicated CLI fields;
- dangerous host/runtime internals.

Protected override must fail loudly and secret values must never be printed or persisted.

---

# 9. Environment Sanitization

`v2ctl` builds the child process environment from a controlled baseline.

Host variables needed for PATH/tool discovery, Python, Modal authentication, and OS operation may be inherited internally.

Experimental `COMFYMODAL_*` / `V2_*` variables from the caller shell are not silently inherited. Use:

```text
--inherit NAME
```

or:

```text
--set NAME=value
```

---

# 10. Runtime-File Override Policy

Persistent runtime flag files are useful for legacy/admin operations but dangerous for reproducible benchmarks.

Default benchmark policy:

```text
runtime_overrides = FORBID
```

Before a performance gate, `v2ctl` should list current relevant overrides and fail if any are present.

Commands:

```text
python tools/v2ctl.py runtime-flags list
python tools/v2ctl.py runtime-flags clear NAME
python tools/v2ctl.py runtime-flags clear --all --confirm
```

Clearing is always an explicit mutation.

---

# 11. Deployment Fingerprint

Every deployment gets a deterministic fingerprint over deploy-relevant state, including:

```text
git HEAD
relevant dirty source hashes
target app/class/method
resource shape
deployment-required flags
build-required flags
profile identity
existing runtime/dependency identity inputs
```

Do not hash irrelevant logs/artifacts.

Persist local deployment manifests under:

```text
.v2ctl/deployments/
```

Sensitive values are redacted or omitted.

---

# 12. Run Fingerprint

Separate deployment identity from request/workload identity.

Run fingerprint includes:

```text
deployment fingerprint
workload identity
request-time flags
conditioning-cache policy
expected SHA
benchmark options
validation mode
```

---

# 13. Effective-Config Proof in Run Artifacts

Each run artifact should contain a `v2ctl` provenance block with:

```text
schema_version
profile
owner
deploy_fingerprint
run_fingerprint
git_head
target
resources
requested_environment
effective_environment
flag_sources
unregistered_flags
runtime_overrides
workload
```

Remote code should emit a compact line such as:

```text
[v2ctl.config] deploy=7f4d... run=1a03... profile=e29-tracer
```

Do not dump full environment or secrets.

---

# 14. Backend Strategy

The first implementation should **not** rewrite deployment semantics unnecessarily.

1. Audit the current real behavior of `deploy_and_run_v2_single.bat`, `run_v2_single.bat`, `tools/benchmark_v2_direct.py`, and helpers.
2. Designate the existing known-good path as the backend.
3. Have `v2ctl` invoke it through `subprocess` / `cmd.exe` with a sanitized explicit environment.
4. Capture stdout/stderr and discover persisted artifacts.
5. Migrate wrapper internals only after parity is proven.

The control plane must not replace a known-good deploy with an improvised Modal SDK deployment.

---

# 15. Windows Invocation

`v2ctl` owns Windows quoting and child environment setup.

Agents should never need to write:

```powershell
cmd.exe /d /v:on /c "set X=1 && call ..."
```

Use `subprocess.run(..., env=resolved_env)` internally.

---

# 16. Deploy Ownership Lock

Concurrent agents require an explicit deploy lock:

```text
.v2ctl/deploy.lock
```

Store owner, pid, host, target, profile, and timestamp.

Rules:

- deploy commands acquire automatically;
- conflicting deploy owner exits nonzero;
- stale lock detection requires evidence;
- force-unlock is explicit and logged;
- release is visible.

This formalizes statements like "E29 owns deploy".

---

# 17. Canonical Cold Validation Protocol

1. Deploy if required.
2. Run exactly one cold gate.
3. If invalid, stop/fix/redeploy.
4. Only after a valid gate, run confirmation.
5. Use 1–5 valid runs total only when justified, biased toward fewer.

The tooling should make doing the wrong thing harder than doing the right thing.

---

# 18. Generic Validation Contract

Every run should validate:

- target;
- deployment fingerprint;
- profile;
- resource shape;
- fresh requirement;
- output SHA when known;
- persisted artifact exists;
- effective-config proof exists;
- no conflicting runtime override;
- successful completion.

Batch-specific validators may add conditions such as real CLIP miss/encode, exact-hit behavior, QD observed max-outstanding, zero-gap trace reconciliation, FP32 applied, and so on.

Use a validator plug-in seam rather than hardcoding E29/E30/E31 into core `v2ctl`.

## 18.1 Generated-output durability is an explicit policy

Golden and other V2 guidance must use
`docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for generated request output.
`COMFYMODAL_OUTPUT_DURABILITY` accepts `off|strict`; missing/`off` resolves to
`off`, while an invalid explicit value is a configuration error:
`configuration error: COMFYMODAL_OUTPUT_DURABILITY must be off or strict`.
Generated-output durability is off by default.

The default result contract is:

```text
encode -> observed SHA/bytes -> FIRST_RESULT_READY -> return
```

Only an explicit strict opt-in requires:

```text
write/fsync -> Volume.commit -> reopen/hash proof
-> TRUE_FIRST_DURABLE_RESULT -> return
```

The validator must match evidence to the selected mode and must not require
`true_durable` for an output-off result or accept a strict result before its
commit/reopen/hash proof. Strict failure cannot silently downgrade. This policy
does not make S4/source publication durability optional; that publication
contract remains mandatory.

---

# 19. Artifact Discovery

Never depend exclusively on redirected console logs.

The tool must discover and record the authoritative persisted run directory and store references to:

```text
run artifact
summary artifact
campaign manifest
console capture
```

If console capture is empty, persisted artifacts remain authoritative.

## 19.1 Invocation-bound provenance (E32)

Every canonical `v2ctl deploy-run`, `run`, `gate`, and `confirm` operation is
bound to one collision-resistant invocation ID, generated once before its
backend child process (and shared by every confirmation sample).  The ID is
propagated through the reserved internal environment channel
`COMFYMODAL_V2CTL_INVOCATION_ID`.  The same channel carries
`COMFYMODAL_V2CTL_PROFILE`,
`COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT`,
`COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT`, and
`COMFYMODAL_V2CTL_RUN_FINGERPRINT`.  v2ctl injects these values after caller
extras; protected-environment rules still reject user attempts to set them.

The primary run artifact must persist the top-level fields
`v2ctl_invocation_id`, `profile` (or `profile_name`),
`profile_config_fingerprint`, `deploy_fingerprint`, `run_fingerprint`,
`request_id`, `output_sha` when available, and `generated_at_utc`.  A `v2ctl`
block is accepted for compatibility with older writers, but new canonical
writers use the top-level invocation field.  Result metadata also records the
selected run/summary paths, any `run_artifacts` list, request ID, profile, and
`provenance_validation_status`.

Canonical discovery scans known roots and their immediate child directories,
parses only plausible JSON, and requires an exact persisted invocation ID.
It validates profile and profile/config fingerprint, reconciles request IDs
from stdout and artifacts, and fails closed on zero matches, missing identity
in an otherwise plausible run, wrong profile/fingerprint, ambiguous duplicate
matches, or conflicting request IDs.  Malformed JSON is ignored safely and
reported by the resulting zero-match failure when no valid artifact remains.
Newest-mtime selection cannot prove invocation ownership and is never used by
canonical calls.  Legacy mtime discovery is available only through an
explicit legacy/noncanonical option and its result is labeled
`provenance_validation_status=legacy_mtime`; it must not contaminate canonical
gate/run/confirm validation.

---

# 20. Migration Plan

## Phase 1 — Audit

Map current known-good deploy/run call graph and locate selective env forwarding / whitelist behavior.

## Phase 2 — Config/registry/profiles

Implement TOML profiles, metadata registry, resolver, protected names, environment sanitization, `config`, `flags`, and `doctor`.

## Phase 3 — Backend wrapper

Implement `deploy`, `run`, and `deploy-run` by invoking the current canonical backend.

## Phase 4 — Fingerprints/provenance

Implement deploy/run fingerprints and effective-config provenance.

## Phase 5 — Remove forwarding whitelist

Delete/bypass the old semantic experiment flag whitelist. Keep type validation, lifecycle validation, protected denylist, and provenance.

## Phase 6 — Runtime override control

Implement runtime override inventory and default-forbid benchmark policy.

## Phase 7 — Gate/confirm

Encode the one-cold-run-first validation convention.

## Phase 8 — BAT deprecation

After parity is proven, old BATs either become compatibility wrappers around `v2ctl` or are explicitly legacy internal backends that agents are forbidden to call directly.

---

# 21. Required Tests

At minimum test:

- profile parsing/inheritance;
- CLI precedence;
- no ambient experiment env leakage;
- explicit inherit and `--set`;
- registered bool/int/float/enum validation;
- unknown deploy accepted;
- unknown unsafe run refused;
- protected/secret override refusal and redaction;
- deploy fingerprint stability/change semantics;
- run fingerprint semantics;
- backend argv/env and exit propagation;
- artifact discovery;
- runtime override forbid/clear behavior;
- deploy lock ownership/conflict/stale handling;
- gate exactly one run;
- invalid gate blocks confirm;
- stale fingerprint blocks confirm;
- expected SHA/fresh enforcement;
- flag audit warnings.

---

# 22. Success Criteria

The control plane is not complete until:

1. A brand-new experiment flag can be deployed without editing a whitelist.
2. The tool tells the agent whether a changed flag requires build, deploy, or run.
3. `run` refuses a changed deploy-required flag.
4. Effective configuration is printed before spend.
5. Effective configuration is persisted with the run.
6. Remote provenance proves deployment/run fingerprints.
7. Hidden runtime-volume overrides cannot silently contaminate a benchmark.
8. A cold validation gate runs exactly once.
9. Confirmation cannot run against an invalid/stale gate.
10. Concurrent deploy owners cannot collide.
11. Existing known-good deploy/run behavior remains available through the canonical backend.
12. No agent needs manual PowerShell `set` commands.
13. The old semantic flag whitelist is removed.
14. Old BATs are wrappers around `v2ctl` or explicitly legacy/forbidden for agents.
15. Documentation contains exact examples for production, diagnostics, new flags, run-only errors, runtime overrides, cold gate, and confirmation.

---

# 22b. Known Pitfall — `snapshot_restore_only` vs Full Generation (MUST READ)

**Symptom (observed E29 Remote Gate 1):** a `v2ctl gate`/`run` reported
`backend_ok=true` but was structurally invalid: no output SHA, no persisted
run artifact, and Modal showed `run_snapshot_restore_only_probe` invocations
instead of `run_plan_stream`.  The run BAT silently fell into the
restore-only **probe** branch, which never generates an image.

**Root cause chain:**

1. `V2_BENCHMARK_MODE` had a registry default of `snapshot_restore_only`.
2. `v2ctl`'s `EnvironmentBuilder` writes every resolved flag (including
   registry **defaults**) into the child env of the deploy/run BATs.
3. The run BAT (`run_v2_single.bat`) enters the probe branch when
   `V2_BENCHMARK_MODE == snapshot_restore_only` (it invokes
   `benchmark_v2_direct.py --snapshot-restore-only`, which calls the
   `run_snapshot_restore_only_probe` remote method — a no-generation probe).
4. Unless the profile explicitly overrode the mode, every v2ctl run/gate
   silently produced a probe instead of a generation.

**Why deploy exit 0 does not help:** the deploy BAT's exit 0 proves only
that Modal accepted the upload ("transport deployed").  Container
crash-loops and probe-vs-generation behavior are remote lifecycle facts
invisible to the local deploy stdout.

**The fix (in place):**

- `V2_BENCHMARK_MODE` registry default changed to `e28_single` (one full
  `run_plan_stream` generation) — `snapshot_restore_only` is an explicit
  opt-in ONLY.
- v2ctl `run`/`gate` now HARD-REFUSE `V2_BENCHMARK_MODE=snapshot_restore_only`
  (`_require_full_run_mode` / `GateRunner` guard) — a probe mode through the
  gate/run path is a configuration error, refused before any spend.
- v2ctl `run`/`gate` forward the canonical selector (e.g. `E28_VALIDATION`)
  as the BAT's first positional arg so the run BAT enters the full-run
  validation branch.
- Deployment manifests state truthfully:
  `deployment_transport_status=deployed`, `runtime_health_status=unverified`
  (the first gate/run is the health-validation boundary).

**Agent rule:** if you intend a generation, verify from the resolved config
that `V2_BENCHMARK_MODE` is a full-run mode (`e28_single`/`e26_single`/
`e25_single`), that `V2_E28_VALIDATION=1` (or the matching selector) is set,
and that Modal shows `run_plan_stream` — NOT `run_snapshot_restore_only_probe`.
Never "fix" a structurally invalid gate by rerunning the same config.

## 22c. Known Pitfall — "Stale container" diagnostics (CORRECTED after E29)

**Symptom (early E29 gate iterations):** a gate run reports a correct
profile/SHA but the artifact's `source_identity.class_name` is
`ModalRuntimeEntrypoint` while the deployment targets
`ModalRuntimeEntrypointV2`, and the container trace has NONE of the current
instrumentation events.  This was initially attributed to warm containers
serving old code.

**CORRECTION (proven during E29):** `class_name=ModalRuntimeEntrypoint` is
a LEGACY NAMING ARTIFACT — the deployed class is dynamically built as
`ModalRuntimeEntrypointV2` from the base `ModalRuntimeEntrypoint`, and the
container reports the base name.  A class-name mismatch is NOT a stale-
container signal.  The actual root causes of the missing E29 events were the
use-before-assignment bug and the missing `_modal.method()` registration
(see §24.5/§24.4), NOT stale containers.  Warm-container reuse is real
(Modal keeps containers alive across redeploys; `restore_count` increments),
but it is not diagnosed by the class name.

**Detection (authoritative):** `python tools/v2ctl.py source-probe
--profile <p>` — byte-compare the deployed modules' SHA-256 against the
expected local source (MATCH/MISMATCH/MISSING/UNEXPECTED_PATH).  That is
the ONLY proof of which code the container runs.  Image IDs and class names
are NOT proof (Modal's `add_local_python_source` without `copy=True` mounts
local bytes at container start; the same image ID can serve different
Python sources, and vice versa).

**The reliable fix:** run cold-gate validation with
`COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1` so every request starts a fresh
container with the current baked code.  This remains the dependable fresh-
cold boundary under Modal warm reuse.

**Agent rule:** before trusting a "fresh" gate, confirm (a) the source-
probe MATCHes the current tree, (b) the current instrumentation events are
present in the artifact's `canonical_ledger` (NOT `trace.events`), and
(c) the container was started for this request (`restore_count==1` with
single-use containers).  A warm container is RESTORED and can never satisfy
a fresh-required gate.

---

# 23. Standing Instruction for All Future V2 Agents

Every future ComfyUI Modal V2 prompt that may deploy or run remotely must include this block or equivalent wording:

> **Canonical deploy/run tooling:** Before any Modal deploy or remote generation, read `docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md`. Use `python tools/v2ctl.py ...` as the only supported deploy/run interface. Do not invent ad-hoc Modal SDK deploys, direct BAT invocations, PowerShell `set && call` chains, custom flag forwarding, or experiment-specific launcher scripts. Do not edit a semantic flag whitelist to make a new experiment flag work. Register flag metadata when useful, but explicit safe flags must flow through `v2ctl`. Respect the v2ctl deploy lock and the current deploy owner. Use the one-cold-gate-first protocol; do not spend a confirmation run after a structurally invalid gate.

If `v2ctl` itself is broken, the agent must diagnose/fix `v2ctl` or stop and report the blocker. It must not silently bypass the control plane.

---

# 24. Operational Playbook — Pitfalls That Cost Days (E29 batch, all proven)

## 24.1 Deploy/run recipe that works (E29 verified)

```text
# 1. Check the deploy lock and resolve config
python tools/v2ctl.py lock status
python tools/v2ctl.py config --profile e29-tracer

# 2. Deploy (acquires the lock; verifies the app version ADVANCED)
python tools/v2ctl.py deploy --profile e29-tracer --owner E29

# 3. Prove the deployed bytes equal the local source (no generation)
python tools/v2ctl.py source-probe --profile e29-tracer --owner E29
#   → verdict=MATCH + manifest source_identity_status=verified

# 4. One cold gate (one paid generation)
python tools/v2ctl.py gate --profile e29-tracer --owner E29
#   → valid=1 requires: fresh container, exact output SHA,
#     canonical_ledger_status=ok, endpoint_status=ok, zero_gap=True
```

The canonical ledger (E29) lives in the run artifact under
`canonical_ledger` (with `canonical_ledger_status`), NOT in ordinary
`trace.events`. Validate against `data["canonical_ledger"]`:
`events`, `spans`, `serial_ledger`, `reconciliation`, `endpoint_status`.

## 24.2 Workspace mismatch — the raw `modal` CLI is NOT the active workspace

The `modal` CLI profile (`modal profile list`) can point at a DIFFERENT
workspace than the one `.modal_workspaces.json` marks active (observed:
profile `default` → testing3, active workspace → testing6). Consequences:

- `modal app history <app>` reads the WRONG workspace's versions (v9 vs v33+).
- A direct `modal deploy` deploys to the WRONG workspace.

**Rule:** never use the raw `modal` CLI for version checks or deploys.
v2ctl resolves credentials from `.modal_workspaces.json`
(`active_workspace_id`) — `_app_version_number`, `_load_workspace`, and the
BAT's workspace-loading all use those credentials. `MODAL_TOKEN_ID` /
`MODAL_TOKEN_SECRET` from the active workspace must be in the child env.

## 24.3 Deploy exit 0 ≠ app updated — verify the version ADVANCED

A Modal deploy can exit 0 while the app version does NOT advance (Windows
`charmap` codec crash printing the 🔨/🎉 emoji, or a cached no-op). v2ctl
refuses such deploys: it captures the app's highest version number BEFORE
the deploy (`_app_version_number`, workspace-aware) and requires a strictly
greater number AFTER. Never trust "App deployed" + exit 0 alone.

Windows environment requirement (taste/lessons): `chcp 65001` +
`PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8` for every modal/child process, or
the CLI's Unicode error panel crashes with `charmap` and produces an EMPTY
or misleading deploy log. The deploy/run BATs set these at the top.

## 24.4 A method must be `_modal.method()`-registered to exist remotely

Adding a new remote method to `ModalRuntimeEntrypoint` requires BOTH:

1. the method definition on the class, AND
2. `setattr(cls, "<name>", _modal.method()(cls.<name>))` in
   `_build_decorated_v2_class`, AND
3. `"<name>"` in `_METHODS_TO_WRAP` AND `_NON_WORKFLOW_METHODS`.

A method only in `_METHODS_TO_WRAP` is wrapped but NEVER exposed by Modal —
the deployed class returns
`NotFoundError: Class has no method <name>`. This cost a full deploy cycle.

## 24.5 Instrumentation must never silently fail (E29 ledger lesson)

The E29 canonical ledger was missing from every remote run for days because
the finalization block referenced `_span_durable_result` before assignment
(use-before-assignment → `UnboundLocalError`) inside a broad
`except Exception: pass`. Rules for lifecycle instrumentation:

- initialize every span holder to `None` at the TOP of the function;
- open `request:executor-run` at PLAN RECEIPT, close it at the selected result
  endpoint (`FIRST_RESULT_READY` by default; `TRUE_FIRST_DURABLE_RESULT` only
  for explicit strict output durability);
- NEVER swallow finalization exceptions on a tracer run: attach
  `canonical_ledger_status="ok"|"error"` + `canonical_ledger_error`
  to the result so a broken tracer FAILS the gate, not silently vanishes;
- the serial ledger MUST use explicit authoritative endpoints
  (`remote_python_resume_mono_ns` → the selected result endpoint; the
  compatibility storage key is `first_durable_result_mono_ns`), never min/max
  of existing events — a truncated ledger must not tile its own truncated
  interval and claim zero-gap (`endpoint_status="missing"` fails).

## 24.6 Host plan validation can fail on the LOCAL node registry

`build_execution_plan` runs `execution.validate_prompt` HOST-side
(fail-closed). The host node registry can be broken/incomplete while the
deployed container is fine — observed causes:

- a third-party custom node (`ComfyUI-CacheDiT/utils.py` or the rgthree
  emoji print without UTF-8) breaks `server.py`'s `utils.install_util`
  import → `PromptServer`-importing packs (Impact Pack, rgthree) fail to
  load → `missing_node_type` for `PairConditioningSetProperties` /
  `Any Switch (rgthree)`.

Fix (implemented): when live host validation fails, `build_execution_plan`
falls back to the D1 registry-proof store's DEPLOYED validation proof,
matched by `node_type_fingerprint` (sorted `class_type` list — the per-run
conditioning nonce changes literal text only, not node structure). The
store must be primed (`python tools/benchmark_v2_direct.py
--prime-registry-proof`, run by the deploy BAT) with UTF-8 so the full
registry (incl. rgthree) loads and stores a validated proof WITH the
fingerprint. The fallback is fail-closed: it only uses a stored proof whose
anchor matches the current `.deployed_state.json` and whose fingerprint
matches the workflow.

## 24.7 The ledger must be copied into the SAMPLE artifact

The remote attaches `canonical_ledger` to the result; `run_0.json` carries
it. But the gate validates `run_001_sample.json`, written by
`experiment_result_store.build_run_record`. If the record builder drops
unknown keys, the ledger vanishes from the validated artifact. The record
builder now carries `canonical_ledger` + `canonical_ledger_status` +
`canonical_ledger_error`; the artifact writer in `benchmark_v2_direct.py`
surfaces status/error too. When adding new remote payload keys, ALWAYS
check both the artifact writer AND the sample-record builder.

## 24.8 `class_name` is a legacy naming artifact, NOT a stale signal

The deployed class is dynamically built as `ModalRuntimeEntrypointV2`
(`type("ModalRuntimeEntrypointV2", (ModalRuntimeEntrypoint,), ...)`) but the
container may report `class_name=ModalRuntimeEntrypoint` (the base).
A class-name mismatch is NOT proof of a stale container. Use the
source-probe (byte hashes) + image/container identity for staleness, never
the class name.

## 24.9 Canonical ledger events do not live in `trace.events`

`critical_path_ledger.record_event()` writes into the ledger's OWN stores
(`_EVENTS` / `_RESTORE_EVENTS`), NOT the ordinary `RuntimeTrace`. "The
remote trace lacks `modal_restore_entry`, therefore the source is old" is an
INVALID inference. The E29 validation target is `data["canonical_ledger"]`.
Keep E30/E31 normal trace-event ingestion separate from E29 ledger storage
unless an explicit bridge joins them.

## 24.10 The `source-probe` manifest flip

`source-probe` PASS flips the deployment manifest
(`.v2ctl/deployments/deploy_*.json`) `source_identity_status` to
`verified`. The manifest is a JSON file (read/write via the path, not the
parsed dict — `latest_deployment_manifest()` returns a dict).

## 24.11 E27 source-only QD parity gate (prepared, blocked)

```
E27_PARITY_GATE_READY = BLOCKED
```

The exact intended parity target is the repaired production QD reader's
source-only entry point, `comfymodal_runtime.clip_qd_reader.read_file_qd`,
with these fixed inputs:

```text
profile:     config/v2/profiles/e30-clip-qd-arm-b.toml
owner:       E27
model_name:  qwen_3_4b.safetensors
folder:      text_encoders
path:        /root/models/text_encoders/qwen_3_4b.safetensors
qd:          4
block_mib:   32
generation:  none
H2D:         excluded (use read_file_qd, not read_file_qd_gpu)
```

`e30-clip-qd-arm-b` is the current selectable canonical arm and pins
`COMFYMODAL_V2_CLIP_QD_READER=1`, `COMFYMODAL_V2_CLIP_QD_QD=4`,
`COMFYMODAL_V2_CLIP_QD_BLOCK_MIB=32`, and the production
`restore_earliest` launch policy. The logical model name must be resolved by
the remote `folder_paths` resolver and the resolved path must be reported as
the real safetensors path above; a basename-only or synthetic-file result is
not E27 parity evidence.

There is currently **no safe canonical source-only remote command** to execute
for this target. `v2ctl source-probe` only hashes imported source and
`v2ctl gate` is a full generation gate; neither invokes `read_file_qd`.
The existing remote `run_clip_qd_probe` invokes the older
`unet_qd_probe.run_unet_qd_probe_battery`, not the repaired production QD
engine, and the direct probe launcher is not a canonical v2ctl backend.
Therefore no executable command is claimed here and no Modal/direct probe is
to be run. The missing mechanism is a v2ctl-owned, invocation-bound
source-only remote method/backend that accepts this profile/path/QD contract,
calls `read_file_qd`, persists its JSON metrics, and has a source-only parity
validator. Until that mechanism exists, E27 parity remains BLOCKED.

Prepared command: **NONE — blocked before invocation**. The profile and
source/path contract above are the exact handoff for the missing backend; do
not substitute `v2ctl gate`, `run_clip_qd_probe`, or a direct Modal launcher.

---

# 26. Non-Goals

This design does not require:

- replacing Modal;
- replacing the production runtime;
- moving all runtime options into request payloads;
- deleting every legacy runtime flag immediately;
- making every unknown flag typed before it can be tested;
- changing model-loading architecture.

The goal is one authoritative, reproducible control plane around the existing runtime.

---

# 27. Final Design Rule

Move from:

```text
Which script did this agent use, which flags happened to get forwarded,
and was this value baked or request-time?
```

to:

```text
This run used profile X, deploy fingerprint Y, run fingerprint Z,
effective flags A/B/C, no runtime overrides, one valid cold gate,
and artifact R proves it.
```

That is the standard every future optimization batch should build on.
