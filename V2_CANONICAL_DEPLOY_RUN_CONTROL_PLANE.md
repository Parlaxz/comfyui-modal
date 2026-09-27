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

# 23. Standing Instruction for All Future V2 Agents

Every future ComfyUI Modal V2 prompt that may deploy or run remotely must include this block or equivalent wording:

> **Canonical deploy/run tooling:** Before any Modal deploy or remote generation, read `docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md`. Use `python tools/v2ctl.py ...` as the only supported deploy/run interface. Do not invent ad-hoc Modal SDK deploys, direct BAT invocations, PowerShell `set && call` chains, custom flag forwarding, or experiment-specific launcher scripts. Do not edit a semantic flag whitelist to make a new experiment flag work. Register flag metadata when useful, but explicit safe flags must flow through `v2ctl`. Respect the v2ctl deploy lock and the current deploy owner. Use the one-cold-gate-first protocol; do not spend a confirmation run after a structurally invalid gate.

If `v2ctl` itself is broken, the agent must diagnose/fix `v2ctl` or stop and report the blocker. It must not silently bypass the control plane.

---

# 24. Non-Goals

This design does not require:

- replacing Modal;
- replacing the production runtime;
- moving all runtime options into request payloads;
- deleting every legacy runtime flag immediately;
- making every unknown flag typed before it can be tested;
- changing model-loading architecture.

The goal is one authoritative, reproducible control plane around the existing runtime.

---

# 25. Final Design Rule

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
