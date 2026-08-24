For structural code questions—symbols, callers/callees, architecture, cross-file impact, and dead-code analysis—prefer Codebase Memory graph discovery first, then verify exact source and coverage gaps with native tools. Native Read/Grep/Glob remain allowed for verification.

## Runtime env flags: deployment passthrough contract (READ BEFORE ADDING ANY FLAG)

Adding a new `COMFYMODAL_V2_*` runtime flag requires ALL THREE touchpoints. Missing any one produces the recurring silent failure: "works in local tests / v2ctl dry-run, silently defaults to off inside the Modal container" (hit by R44D, R44F, and R44I3 before the generic fix).

1. **Profile**: set the value in `config/v2/profiles/<profile>.toml` `[environment]`.
2. **Authority**: register a `_spec(...)` entry in `comfymodal_runtime/config_authority.py::GOLDEN_CONTROL_FLAGS` (runtime reconciliation compares resolved maps; unregistered flags are invisible to it).
3. **Container boundary**: `comfymodal_runtime/modal_app.py::_runtime_env()` builds the Modal class `env=`. Since R44I3 it GENERICALLY forwards every `COMFYMODAL_V2_*` / `COMFYMODAL_WARMUP_*` variable present in the deploy-time process environment (that environment is already sanitized by `tools/v2_control/environment.py::EnvironmentBuilder` — ambient host vars never leak in; only profile/`--set`/`--inherit` values arrive). Explicit per-key entries in `_runtime_env()` remain as documented defaults for absent keys and take precedence for their defaults only.

Verification duty for every new flag: after deploy, confirm the flag's EFFECT is visible in run telemetry (e.g. an adoption_mode / override marker field), not just its presence in dry-run output. A flag that changes no observable remote field must be treated as not deployed.
