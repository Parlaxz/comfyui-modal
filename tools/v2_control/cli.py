"""v2ctl command-line interface (Batch E32).

Thin CLI over the v2_control modules.  Local-only: every deploy/run/gate
command builds a sanitized child environment and invokes the canonical
backend via subprocess.  Golden deploy uses the native Modal module deploy;
request execution retains the established backend.  No Modal SDK calls, no
network, no ambient experiment env leakage in dry-run mode.
"""

from __future__ import annotations

import argparse
import inspect
import importlib.util
import json
import os
import re
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from comfymodal_runtime.contracts import DEPLOYMENT_HASH_NAMESPACE
from comfymodal_runtime.publication_policy import (
    CUSTOM_NODES_PUBLISHER_APP_NAME,
    CUSTOM_NODES_VOLUME_NAME,
)

from . import environment as env_mod
from . import registry as registry_mod
from . import profiles as profiles_mod
from . import config as config_mod
from . import fingerprints as fp_mod
from . import backend as backend_mod
from . import locking as locking_mod
from . import runtime_overrides as ro_mod
from . import validation as val_mod
from . import provenance as prov_mod
from . import deployment_receipt as receipt_mod
from .errors import (
    BackendError,
    DeployCrashLoopError,
    FlagError,
    GateError,
    LockHeldError,
    LockStaleError,
    ProtectedVarError,
    ProfileError,
    RuntimeOverrideViolation,
    V2CtlError,
)

SCHEMA_VERSION = 2
VERSION = "0.2.0"
FINGERPRINT_ALGORITHM = "canonical-boundary-identity-v2"

# E31 QD4 cast-once is a distinct validation path.  The profile inherits the
# E29/E28 workload flags, so selector construction must key off the explicit
# profile name before looking at the inherited E28 selector.
E31_QD4_CAST_ONCE_PROFILE = "e31-clip-fp32-qd4-arm-b"
E31_VALIDATION_SELECTOR = "E31_VALIDATION"

# Golden P1 is a separate backend harness and remote method.  Keep its
# identity explicit so a profile cannot reach the Golden method accidentally
# through a generic full-run path.
GOLDEN_P1_PROFILE = "golden_p1"
GOLDEN_P1_SELECTOR = "golden_p1"
GOLDEN_P1_METHOD = "run_golden_serial_stream"
GOLDEN_P1_MODE = "golden_p1_serial"
GOLDEN_ATTENTION_BACKEND_FLAG = "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND"
FULL_RUN_METHOD = "run_plan_stream"
PROTECTED_GOLDEN_APP = "stable-modal-comfy-v2-golden-p1"
_MODAL_APP_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

# E37 deliberately inherits the E29/E28 workload shape, but its late CLIP
# policy is not compatible with the historical E28 selector.  Keep this path
# ahead of inherited selector flags so an E37 request can never be routed to
# the E28 BAT branch.
E37_LEGACY_PROFILES = frozenset({
    "e37-clip-qd4",
    "e37-clip-fastsafe",
})
E37_CLEAN_LANE_PROFILE = "e37-clean-lane-qd4"
E37_STRICT_PROOF_FLAG = "COMFYMODAL_V2_E37_STRICT_PROOF"
E37_VALIDATION_SELECTOR = "E37_VALIDATION"
E37_CLEAN_LANE_SELECTOR = "E37_CLEAN_LANE_VALIDATION"

# Static audit: which flag names does the runtime actually consume?  Derived
# from the Phase-0 audit of the deployed runtime source (modal_app request
# allowlist, comfyapp runtime-flag resolvers, harness selectors) plus a live
# source scan in `flags audit`.
CONSUMED_SOURCE_GLOBS = (
    "comfymodal_runtime/*.py",
    "comfyapp.py",
    "tools/benchmark_v2_direct.py",
)
_CONSUMED_TOKEN_RE = re.compile(r"\b(COMFYMODAL_V2_[A-Z0-9_]+|V2_[A-Z0-9_]+)\b")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _scan_consumed_names(repo_root: Path) -> set[str]:
    """Advisory lint: env-var tokens appearing in the runtime sources."""
    found: set[str] = set()
    for pattern in CONSUMED_SOURCE_GLOBS:
        for path in sorted(repo_root.glob(pattern)):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in _CONSUMED_TOKEN_RE.finditer(text):
                found.add(m.group(1))
    return found


# ── Bootstrap ──────────────────────────────────────────────────────────

def _parse_sets(specs: list[str]) -> list[tuple[str, str]]:
    return [config_mod.ConfigResolver.parse_set_spec(s) for s in specs]


def _identity_env(config: config_mod.ResolvedConfig) -> dict[str, str]:
    """Canonical target/resource identity env (protected; CLI/profile-driven).

    These names are in the protected policy because the target identity is
    controlled by dedicated CLI fields / profile ``[target]``/``[resources]``
    sections, never by ``--set``/``--inherit``.  v2ctl itself sets them on
    the child environment of deploy-capable commands.
    """
    return {
        "COMFYMODAL_V2_APP_NAME": config.target.app,
        "COMFYMODAL_V2_CLASS_NAME": config.target.class_name,
        "COMFYMODAL_V2_GPU": config.resources.gpu,
        "COMFYMODAL_V2_MEMORY_MB": str(config.resources.memory_mb),
        "COMFYMODAL_V2_CPU_REQUEST": str(config.resources.cpu),
        "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": str(config.resources.memory_mb),
        "COMFYMODAL_V2_BASELINE_CPU_REQUEST": str(config.resources.cpu),
    }


def _identity_env_for_command(command: str, config: config_mod.ResolvedConfig) -> dict[str, str]:
    # Run must target the exact app/class resolved by the selected profile;
    # otherwise run_v2_single.bat falls back to the production restore-only app.
    return _identity_env(config) if command in ("deploy", "deploy-run", "run") else {}


def _new_invocation_id() -> str:
    """Create exactly one collision-resistant ID for a canonical operation."""
    return uuid.uuid4().hex


def _canonical_metadata_env(
    config: config_mod.ResolvedConfig,
    fingerprints: fp_mod.FingerprintEngine,
    invocation_id: str,
) -> dict[str, str]:
    return {
        "COMFYMODAL_V2CTL_INVOCATION_ID": invocation_id,
        "COMFYMODAL_V2CTL_PROFILE": str(config.profile_name),
        "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": fingerprints.profile_config_fingerprint(),
        "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": fingerprints.deploy_fingerprint(),
        "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": fingerprints.deploy_fingerprint(),
        "COMFYMODAL_V2CTL_RUN_FINGERPRINT": fingerprints.run_fingerprint(),
        "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": DEPLOYMENT_HASH_NAMESPACE,
    }


def build_components(repo_root: Path, profile_name: str, cli_options: dict[str, str] | None = None,
                     sets: list[str] | None = None, inherits: list[str] | None = None,
                     inherit_from: dict[str, str] | None = None):
    registry = registry_mod.FlagRegistry(repo_root / "config" / "v2" / "flag_registry.toml")
    registry.load()
    profiles = profiles_mod.Profiles(repo_root / "config" / "v2" / "profiles")
    resolver = config_mod.ConfigResolver(repo_root, profiles, registry)
    config = resolver.resolve(
        profile_name=profile_name,
        cli_options=cli_options or {},
        sets=_parse_sets(sets or []),
        inherits=inherits or [],
        inherit_from=inherit_from or os.environ,
    )
    fingerprints = fp_mod.FingerprintEngine(config)
    env_builder = env_mod.EnvironmentBuilder()
    backend_registry = backend_mod.BackendRegistry(repo_root)
    return registry, profiles, resolver, config, fingerprints, env_builder, backend_registry


def _build_components_for_args(repo_root: Path, args):
    """Resolve one command's complete identity through the same path.

    In particular, public Golden commands must not let doctor/status use the
    profile target while deploy/run use a separately assembled app override.
    Keeping this in one helper makes the app, class, method, flags, and
    fingerprints identical for every command.
    """
    return build_components(
        repo_root,
        args.profile,
        cli_options=_cli_target_options(args),
        sets=getattr(args, "set", []),
        inherits=getattr(args, "inherit", []),
    )


def _normalize_app_name(value: object) -> str:
    normalized = str(value).strip().lower()
    if not _MODAL_APP_NAME_RE.fullmatch(normalized):
        raise ValueError(
            f"invalid Golden app name {value!r}; use lowercase letters, digits, "
            "and internal hyphens (1-63 characters)"
        )
    return normalized


def derive_publisher_app_name(experimental_app: object) -> str:
    """Compatibility spelling for the single shared publisher authority.

    The argument is intentionally ignored.  Custom-node ownership belongs to
    the shared Volume publisher, not to a consuming Golden app.
    """
    _ = experimental_app
    return CUSTOM_NODES_PUBLISHER_APP_NAME


def _reject_golden_identity_args(args, *, public: bool = False) -> int | None:
    """Reject protected Golden identity before any backend-side work.

    ``--allow-production`` used to be a bypass.  R0 is intentionally not a
    production workflow, so the option is accepted only to produce a clear
    refusal rather than silently changing the target.
    """
    profile = str(getattr(args, "profile", "") or "")
    is_golden = profile == GOLDEN_P1_PROFILE
    raw_app = getattr(args, "app", None)
    if raw_app:
        try:
            args.app = _normalize_app_name(raw_app)
        except ValueError as exc:
            if public or is_golden:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 2
    if getattr(args, "app", None) == PROTECTED_GOLDEN_APP:
        print(
            f"ERROR: {PROTECTED_GOLDEN_APP!r} is production-protected; "
            "Golden R0 requires a distinct experimental --app",
            file=sys.stderr,
        )
        return 2
    if getattr(args, "allow_production", False) and (public or is_golden):
        print(
            "ERROR: --allow-production is disabled for the isolated Golden R0 workflow",
            file=sys.stderr,
        )
        return 2
    return None


def _reject_protected_effective_target(
    config: config_mod.ResolvedConfig, *, command: str
) -> None:
    """Reject a protected app after profile/CLI target resolution.

    The raw ``--app`` check runs before dispatch.  This second check closes the
    equivalent path where a profile or another resolver supplies the protected
    target, before a command can inspect manifests, versions, or invoke a
    backend.
    """
    app = str(getattr(getattr(config, "target", None), "app", "") or "").strip().lower()
    if app == PROTECTED_GOLDEN_APP:
        raise GateError(
            f"{command} refuses production-protected app {PROTECTED_GOLDEN_APP!r}; "
            "Golden R0 requires a distinct experimental --app"
        )


def _reject_flat_golden_deploy_run(args) -> int | None:
    """Keep Golden deploy/run on its explicit public command path."""
    if getattr(args, "profile", None) != GOLDEN_P1_PROFILE:
        return None
    print(
        "ERROR: flat `v2ctl deploy-run --profile golden_p1` is not supported; "
        "use `v2ctl golden deploy --app <experimental>` followed by "
        "`v2ctl golden run --app <experimental>`",
        file=sys.stderr,
    )
    return 2


def _redact_env(env: dict[str, str]) -> dict[str, str]:
    return env_mod.EnvironmentBuilder().display(env)


_BACKEND_DIAGNOSTIC_MAX_CHARS = 8 * 1024
_BACKEND_DIAGNOSTIC_HEAD_CHARS = _BACKEND_DIAGNOSTIC_MAX_CHARS // 2
_BACKEND_DIAGNOSTIC_TAIL_CHARS = (
    _BACKEND_DIAGNOSTIC_MAX_CHARS - _BACKEND_DIAGNOSTIC_HEAD_CHARS
)
_DIAGNOSTIC_SECRET_RE = re.compile(
    r"(?i)((?:[a-z0-9_]*)(?:token|secret|password|api[_-]?key|credential)"
    r"(?:[a-z0-9_]*\s*[=:]\s*))"
    r"([^\s,;\"']+)"
)
_DIAGNOSTIC_QUOTED_SECRET_RE = re.compile(
    r"(?i)((?:[\"']?)[a-z0-9_]*(?:token|secret|password|api[_-]?key|credential)"
    r"[a-z0-9_]*[\"']?\s*[=:]\s*[\"'])"
    r"([^\"']+)([\"'])"
)


def _redact_backend_diagnostic(text: str, env: dict[str, str]) -> str:
    """Redact credential-shaped values from backend output."""
    output = text or ""
    # Replace values actually supplied to the backend first, including values
    # that do not use a ``NAME=value`` format in the backend's output.
    protected = env_mod.EnvironmentBuilder().display(env)
    for name, value in env.items():
        if not value or protected.get(name) != "<redacted>":
            continue
        output = output.replace(str(value), "<redacted>")
    # Also cover backend messages that print a credential without using the
    # exact value from the child environment (for example, a parsed config).
    output = _DIAGNOSTIC_QUOTED_SECRET_RE.sub(r"\1<redacted>\3", output)
    output = _DIAGNOSTIC_SECRET_RE.sub(r"\1<redacted>", output)
    return output


def _safe_backend_diagnostic(text: str, env: dict[str, str]) -> str:
    """Return bounded backend output with credential-shaped values redacted."""
    output = _redact_backend_diagnostic(text, env)
    if len(output) > _BACKEND_DIAGNOSTIC_MAX_CHARS:
        output = output[:_BACKEND_DIAGNOSTIC_MAX_CHARS]
        output += "\n...[diagnostic output truncated]"
    return output


def _backend_diagnostic_sections(text: str, env: dict[str, str]) -> tuple[str, str, bool]:
    """Return redacted, bounded head/tail sections for one backend stream."""
    output = _redact_backend_diagnostic(text, env)
    truncated = len(output) > _BACKEND_DIAGNOSTIC_MAX_CHARS
    if not truncated:
        return output, output, False
    return (
        output[:_BACKEND_DIAGNOSTIC_HEAD_CHARS],
        output[-_BACKEND_DIAGNOSTIC_TAIL_CHARS:],
        True,
    )


def _print_backend_diagnostic(result: backend_mod.BackendResult,
                              env: dict[str, str]) -> None:
    """Print failed backend streams with bounded, redacted head and tail sections."""
    print("[v2ctl.deploy] BEGIN backend diagnostics (stderr first; head and tail)",
          file=sys.stderr)
    for label, stream in (("stderr", result.stderr), ("stdout", result.stdout)):
        head, tail, truncated = _backend_diagnostic_sections(stream, env)
        print(f"--- backend {label} (head) ---", file=sys.stderr)
        print(head or "(no output)", file=sys.stderr)
        print(f"--- backend {label} (tail) ---", file=sys.stderr)
        print(tail or "(no output)", file=sys.stderr)
        if truncated:
            print("...[diagnostic output truncated; showing bounded head and tail]",
                  file=sys.stderr)
    print("[v2ctl.deploy] END backend diagnostics", file=sys.stderr)


def _backend_selector(config: config_mod.ResolvedConfig) -> str | None:
    """Derive the canonical backend selector argument from the resolved
    config environment.

    The deploy/run BATs enter their validation modes ONLY via the first
    positional selector argument (e.g. ``E28_VALIDATION``) or the
    corresponding env var.  Without it the run BAT falls back to the
    restore-only PROBE path (``run_snapshot_restore_only_probe``) which never
    invokes ``run_plan_stream`` and produces no generation artifact.  v2ctl
    therefore forwards the selector when the profile requests a validation
    mode.  Returns None when no selector applies (plain production run).
    """
    try:
        if config.profile_name == GOLDEN_P1_PROFILE:
            return GOLDEN_P1_SELECTOR
        env = {f.name: f.value for f in config.flags}
        if config.profile_name == E37_CLEAN_LANE_PROFILE or any(
            str(env.get(name, "0")).lower() in ("1", "true", "yes", "on")
            for name in ("COMFYMODAL_V2_E37_CLEAN_LANE", "COMFYMODAL_V2_CLEAN_LANE")
        ):
            return E37_CLEAN_LANE_SELECTOR
        if config.profile_name in E37_LEGACY_PROFILES:
            return E37_VALIDATION_SELECTOR
        if str(env.get(E37_STRICT_PROOF_FLAG, "0")).lower() in (
            "1", "true", "yes", "on"
        ):
            return E37_VALIDATION_SELECTOR
        if config.profile_name == E31_QD4_CAST_ONCE_PROFILE:
            return E31_VALIDATION_SELECTOR
        if str(env.get("V2_E31_VALIDATION", "0")) in ("1", "true", "yes", "on"):
            return E31_VALIDATION_SELECTOR
        if str(env.get("V2_E28_VALIDATION", "0")) in ("1", "true", "yes", "on"):
            return "E28_VALIDATION"
        if str(env.get("V2_E26_VALIDATION", "0")) in ("1", "true", "yes", "on"):
            return "E26_VALIDATION"
        if str(env.get("V2_E25_VALIDATION", "0")) in ("1", "true", "yes", "on"):
            return "E25_VALIDATION"
    except Exception:
        pass
    return None


def _validation_backend_args(config: config_mod.ResolvedConfig) -> tuple[list[str], dict[str, str]]:
    """Build the canonical single-run validation selector and its env.

    E25/E26/E28/E31 are activated by both a positional selector and a matching
    conditioning-cache nonce.  Keep this construction shared by gate,
    confirm, and dry-run reporting so a confirmation cannot silently fall
    back to the restore-only BAT path.
    """
    # The dedicated Golden harness is selected by the canonical positional
    # selector; keep the resolved environment and expected-output contract.
    if config.profile_name == GOLDEN_P1_PROFILE:
        expected_sha = str(config.workload.expected_output_sha or "").strip()
        args = [
            "--run-count",
            "1",
        ]
        # Keep duck-typed callers compatible when they construct a minimal
        # Golden config.  The real golden_p1 profile supplies the SHA and
        # therefore still forwards the strict expected-output contract.
        if expected_sha:
            args += ["--golden-p1-expected-output-sha", expected_sha]
        flag_lookup = getattr(config, "flag", None)
        attention_flag = (
            flag_lookup(GOLDEN_ATTENTION_BACKEND_FLAG)
            if callable(flag_lookup)
            else None
        )
        # Keep the historical request shape byte-compatible when the selector
        # is omitted: Golden's remote adapter already defaults to PyTorch.
        if (
            attention_flag is not None
            and getattr(attention_flag, "source", "default") != "default"
        ):
            args += ["--attention-backend", str(getattr(attention_flag, "value", ""))]
        # The registry default is e28_single, whose BAT branch invokes the
        # ordinary run_plan_stream path.  Project the effective Golden mode
        # explicitly so the request reaches the serial-Golden branch.  The
        # local Golden guard rejects explicit generic modes before this point.
        return args, {"V2_BENCHMARK_MODE": _benchmark_mode(config)}

    selector = _backend_selector(config)
    args = ([selector] if selector else []) + ["--run-count", "1"]
    selector_env: dict[str, str] = {}
    if selector:
        validation_name = selector.removesuffix("_VALIDATION")
        nonce_flag = None
        flag_lookup = getattr(config, "flag", None)
        if callable(flag_lookup):
            nonce_flag = flag_lookup(f"V2_{validation_name}_CONDITIONING_NONCE")
        nonce = str(getattr(nonce_flag, "value", "") or "").strip()
        if not nonce:
            nonce = str(getattr(getattr(config, "workload", None), "nonce", "") or "").strip()
        nonce = nonce or uuid.uuid4().hex
        args += ["--conditioning-cache-nonce", nonce]
        if selector in (E37_CLEAN_LANE_SELECTOR, E37_VALIDATION_SELECTOR):
            selector_env["V2_E37_CONDITIONING_NONCE"] = nonce
        else:
            selector_env[f"V2_{validation_name}_CONDITIONING_NONCE"] = nonce
        if selector == E37_CLEAN_LANE_SELECTOR:
            # CLEAN_LANE is a distinct deploy path.  It deliberately does not
            # project the historical E19 tuple; the BAT must preserve the
            # profile's off/none values and the clean verifier checks them.
            selector_env["COMFYMODAL_V2_E37_CLEAN_LANE"] = "1"
            selector_env["COMFYMODAL_V2_CLEAN_LANE"] = "1"
            selector_env["V2_E37_VALIDATION"] = "1"
            selector_env["V2_E28_VALIDATION"] = "0"
            selector_env["V2_E31_VALIDATION"] = "0"
            selector_env["V2_BENCHMARK_MODE"] = "e37_single"
            selector_env["V2_BENCHMARK_RUNS"] = "1"
        elif selector == E37_VALIDATION_SELECTOR:
            # E37 profiles inherit E29's E28 selector.  Explicitly project the
            # E37 request mode and disable historical selectors in the child
            # environment; the positional selector alone is not sufficient
            # for every BAT/parser path.
            selector_env["V2_E37_VALIDATION"] = "1"
            selector_env["V2_E28_VALIDATION"] = "0"
            selector_env["V2_E31_VALIDATION"] = "0"
            selector_env["V2_BENCHMARK_MODE"] = "e37_single"
            selector_env["V2_BENCHMARK_RUNS"] = "1"
        if selector == E31_VALIDATION_SELECTOR:
            # The E31 profile inherits E29's E28 selector.  Explicitly turn
            # that selector off in run-only children so E31 cannot silently
            # fall through the ordinary E28 path.
            selector_env["V2_E31_VALIDATION"] = "1"
            selector_env["V2_E28_VALIDATION"] = "0"
            selector_env["V2_BENCHMARK_MODE"] = "e31_single"
    return args, selector_env


def _benchmark_mode(config: config_mod.ResolvedConfig) -> str:
    """The effective ``V2_BENCHMARK_MODE`` from the resolved config.

    Golden P1 has a dedicated mode because the registry default
    (``e28_single``) routes to the ordinary ``run_plan_stream`` branch.
    The canonical Golden mode is projected for the inherited registry default;
    explicit generic selectors are rejected by the command guard.  Non-Golden
    profiles keep the registry default and existing explicit-mode behavior.
    """
    try:
        env = {f.name: f.value for f in config.flags}
        mode_flag = next(
            (flag for flag in config.flags if flag.name == "V2_BENCHMARK_MODE"),
            None,
        )
        mode = str(env.get("V2_BENCHMARK_MODE", "") or "e28_single").strip()
        if (
            config.profile_name == GOLDEN_P1_PROFILE
            and (mode_flag is None or getattr(mode_flag, "source", "") == "default")
        ):
            return GOLDEN_P1_MODE
        return mode or "e28_single"
    except Exception:
        return "e28_single"


def _native_golden_deploy_env(env: dict[str, str]) -> dict[str, str]:
    """Remove the legacy generic benchmark control plane from native deploys.

    ``V2_*`` controls belong to BAT/request compatibility paths.  Native
    Golden deployment only needs the ``COMFYMODAL_V2_*`` runtime configuration
    and v2ctl's canonical metadata; in particular it must not carry
    ``V2_BENCHMARK_MODE`` or any generic validation selector state.
    """
    return {name: value for name, value in env.items() if not name.startswith("V2_")}


def _reject_golden_mode_override(
    config: config_mod.ResolvedConfig, *, command: str
) -> None:
    """Keep explicit Golden mode selection on the dedicated harness only.

    The Golden profile's registry default is inherited from production for
    compatibility, so ``_benchmark_mode`` projects that default to the
    canonical Golden mode.  An explicit override is different: accepting a
    generic harness mode would let the BAT reach a generic branch before the
    Golden branch.  Refuse it while the resolved configuration is still local.
    """
    profile = str(getattr(config, "profile_name", "") or "")
    mode_flag = config.flag("V2_BENCHMARK_MODE")
    effective_mode = _benchmark_mode(config)
    if profile != GOLDEN_P1_PROFILE and effective_mode == GOLDEN_P1_MODE:
        raise GateError(
            f"{command} refuses V2_BENCHMARK_MODE={GOLDEN_P1_MODE} for "
            f"non-Golden profile {profile or '(missing)'}; only "
            f"{GOLDEN_P1_PROFILE} may use that mode"
        )
    if profile != GOLDEN_P1_PROFILE:
        return
    if mode_flag is None or mode_flag.source not in {"cli", "inherit", "set"}:
        return
    mode = str(mode_flag.value or "").strip()
    if mode != GOLDEN_P1_MODE:
        raise GateError(
            f"{command} refuses explicit V2_BENCHMARK_MODE={mode or '(empty)'} "
            f"for {GOLDEN_P1_PROFILE}; only {GOLDEN_P1_MODE} is allowed"
        )


def _require_full_run_mode(config: config_mod.ResolvedConfig, *, command: str) -> None:
    """HARD GUARD: gate/run must produce a full generation (run_plan_stream),
    never the snapshot-restore-only PROBE (which calls
    ``run_snapshot_restore_only_probe`` and produces no generation artifact).

    ``V2_BENCHMARK_MODE=snapshot_restore_only`` is a probe-only mode; using it
    through the gate/run path is a configuration error and is refused before
    any spend.
    """
    _reject_golden_mode_override(config, command=command)
    mode = _benchmark_mode(config)
    if mode == "snapshot_restore_only":
        raise GateError(
            f"{command} refuses V2_BENCHMARK_MODE=snapshot_restore_only: that "
            f"mode runs the restore-only PROBE (run_snapshot_restore_only_probe), "
            f"which never invokes run_plan_stream and produces no generation "
            f"artifact. Configure a full-run mode (e.g. e28_single) in the profile."
        )

    profile = str(getattr(config, "profile_name", "") or "")
    target = getattr(config, "target", None)
    method = str(getattr(target, "method", "") or "").strip()
    if profile == GOLDEN_P1_PROFILE:
        if method != GOLDEN_P1_METHOD:
            raise GateError(
                f"{command} refuses golden_p1 target.method={method or '(missing)'}; "
                f"golden_p1 requires {GOLDEN_P1_METHOD}"
            )
    elif method != FULL_RUN_METHOD:
        raise GateError(
            f"{command} refuses target.method={method or '(missing)'}; non-Golden "
            f"profiles require {FULL_RUN_METHOD}"
        )


def _app_version_number(app_name: str) -> int | None:
    """Highest ``v<N>`` version number from ``modal app history`` (0 if none).

    Returns ``None`` on lookup uncertainty.  The history table rows look
    like ``| v9 | 2026-08-19 17:42 Central Daylight | ...``; the header row
    (``| Version | ...``) contains no ``v<num>`` and is ignored by the regex.

    CRITICAL (workspace-safety): the invocation MUST use the ACTIVE
    workspace's credentials from ``.modal_workspaces.json`` — never the raw
    ``modal`` CLI, whose default profile may point at a DIFFERENT workspace
    (e.g. testing3 while the active workspace is testing6).  Checking the
    wrong workspace's version count silently makes a no-op deploy look valid
    (or vice versa).
    """
    import json
    import os
    import re
    import subprocess

    def explicitly_has_no_app_or_deployments(text: str) -> bool:
        lowered = text.casefold()
        return any(
            re.search(pattern, lowered)
            for pattern in (
                r"\bapp(?:lication)?\b[^\n]*\b(?:not found|does not exist)\b",
                r"\bno such app(?:lication)?\b",
                r"\bno app(?:lication)?\b[^\n]*\bfound\b",
                r"\bcould not find (?:the )?app(?:lication)?\b",
                r"\bno deployments? found\b",
            )
        )

    try:
        # Resolve the ACTIVE workspace credentials from .modal_workspaces.json.
        ws_file = Path(__file__).resolve().parents[2] / ".modal_workspaces.json"
        data = json.loads(ws_file.read_text(encoding="utf-8"))
        active_id = data.get("active_workspace_id")
        ws = next(
            (w for w in data.get("workspaces", []) if w.get("id") == active_id),
            None,
        )
        if not ws or not ws.get("token_id") or not ws.get("token_secret"):
            return None
        env = dict(os.environ)
        env["MODAL_TOKEN_ID"] = str(ws["token_id"])
        env["MODAL_TOKEN_SECRET"] = str(ws["token_secret"])
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        r = subprocess.run(
            ["modal", "app", "history", app_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=env,
        )
        output = f"{r.stdout or ''}\n{r.stderr or ''}"
        if r.returncode != 0:
            return 0 if explicitly_has_no_app_or_deployments(output) else None
        highest = 0
        for line in (r.stdout or "").splitlines():
            m = re.search(r"\bv(\d+)\b", line, re.IGNORECASE)
            if m:
                try:
                    highest = max(highest, int(m.group(1)))
                except ValueError:
                    continue
        if highest or explicitly_has_no_app_or_deployments(output):
            return highest
        return None
    except Exception:
        return None


def _active_workspace_credentials(repo_root: Path) -> dict[str, str]:
    """Return active workspace credentials for a native Modal child process."""
    workspace = _active_workspace(repo_root)
    return {
        "MODAL_TOKEN_ID": str(workspace["token_id"]),
        "MODAL_TOKEN_SECRET": str(workspace["token_secret"]),
    }


def _active_workspace(repo_root: Path) -> dict[str, object]:
    """Return the complete active workspace record without exposing secrets."""
    path = repo_root / ".modal_workspaces.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GateError(f"active Modal workspace file is unreadable: {path}") from exc
    if not isinstance(data, dict):
        raise GateError(f"active Modal workspace file is not an object: {path}")
    active_id = data.get("active_workspace_id")
    workspaces = data.get("workspaces", [])
    if not isinstance(workspaces, list):
        raise GateError("active Modal workspace file has malformed workspaces")
    workspace = next(
        (item for item in workspaces if isinstance(item, dict) and item.get("id") == active_id),
        None,
    )
    if not workspace or not workspace.get("token_id") or not workspace.get("token_secret"):
        raise GateError("active Modal workspace is missing credentials")
    return workspace


# ── Manifests ──────────────────────────────────────────────────────────

def _deployment_manifest_dir(repo_root: Path) -> Path:
    return repo_root / ".v2ctl" / "deployments"


def _receipt_target(config: config_mod.ResolvedConfig) -> dict[str, str]:
    return {
        "app": str(config.target.app),
        "class": str(config.target.class_name),
        "method": str(config.target.method),
    }


def _bound_deployment_receipt(
    repo_root: Path, config: config_mod.ResolvedConfig, *, command: str
) -> tuple[Path, receipt_mod.DeploymentReceipt]:
    """Load the immutable Golden authority and perform host admission checks."""
    selected = receipt_mod.latest_deployment_receipt(
        repo_root, profile=config.profile_name, target=_receipt_target(config)
    )
    if selected is None:
        raise GateError(f"{command} requires an immutable deployment receipt")
    path, receipt = selected
    target = _receipt_target(config)
    if receipt.target != target:
        raise GateError(f"{command} deployment receipt target mismatch")
    if receipt.profile != config.profile_name:
        raise GateError(f"{command} deployment receipt profile mismatch")
    # A different app version is a different remote deployment, even when the
    # local source happens to be unchanged.  Unknown lookup is fail-closed.
    current_version = _app_version_number(receipt.target["app"])
    if current_version is None or current_version != receipt.deployment_version:
        raise GateError(
            f"{command} deployment receipt version mismatch: stored="
            f"{receipt.deployment_version} current={current_version!r}"
        )
    try:
        current_fp = str(fp_mod.FingerprintEngine(config).deploy_fingerprint())
    except Exception as exc:  # noqa: BLE001 - receipt admission is fail-closed
        raise GateError(f"{command} could not resolve local deployment identity: {exc}") from exc
    if current_fp != receipt.deploy_fingerprint:
        print(
            f"[v2ctl.{command}] WARNING: local deploy identity drifted after deployment; "
            "binding the immutable remote receipt (source drift is warning-only)",
            file=sys.stderr,
        )
    return path, receipt


def _receipt_effective_env(
    env: dict[str, str], receipt: receipt_mod.DeploymentReceipt
) -> dict[str, str]:
    """Overlay only the receipt's narrow deployed configuration projection.

    Host/tool variables and request metadata stay owned by this invocation;
    receipt data is never a general child-environment restore mechanism.
    """
    receipt.validate()
    bound = dict(env)
    for name, value in receipt.effective_environment.items():
        bound[name] = str(value)
    bound["COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT"] = receipt.deploy_fingerprint
    bound["COMFYMODAL_V2CTL_DEPLOYMENT_HASH"] = receipt.deploy_fingerprint
    bound["COMFYMODAL_V2CTL_PROFILE"] = receipt.profile
    resources = receipt.deployment_identity.get("resources", {})
    if isinstance(resources, dict):
        for env_name, resource_name in (
            ("COMFYMODAL_V2_GPU", "gpu"),
            ("COMFYMODAL_V2_CPU_REQUEST", "cpu"),
            ("COMFYMODAL_V2_MEMORY_MB", "memory_mb"),
            ("COMFYMODAL_V2_BASELINE_CPU_REQUEST", "cpu"),
            ("COMFYMODAL_V2_BASELINE_MEMORY_REQUEST", "memory_mb"),
        ):
            if resource_name in resources:
                bound[env_name] = str(resources[resource_name])
    if receipt.profile_config_fingerprint:
        bound["COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT"] = receipt.profile_config_fingerprint
    return bound


def _run_manifest_dir(repo_root: Path) -> Path:
    return repo_root / ".v2ctl" / "runs"


def _profile_config_fingerprint(fingerprints: object) -> str:
    """Read the E32 config fingerprint without breaking older test doubles."""
    for name in ("profile_config_fingerprint", "config_fingerprint"):
        method = getattr(fingerprints, name, None)
        if callable(method):
            try:
                return str(method())
            except Exception:  # noqa: BLE001 - compatibility fallback
                continue
    return ""


@dataclass(frozen=True)
class DeployIdentitySnapshot:
    """The deploy identity captured before any publication/backend work."""

    deploy_fingerprint: str
    deploy_inputs: Mapping[str, Any]
    profile_config_fingerprint: str


def _freeze_deploy_identity(value: Any) -> Any:
    """Freeze nested deploy inputs so later config mutation cannot alter them."""
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze_deploy_identity(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_deploy_identity(item) for item in value)
    return value


def _thaw_deploy_identity(value: Any) -> Any:
    """Return JSON-compatible ordinary containers from a frozen snapshot."""
    if isinstance(value, Mapping):
        return {key: _thaw_deploy_identity(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_deploy_identity(item) for item in value]
    return value


def capture_deploy_identity(fingerprints: object) -> DeployIdentitySnapshot:
    """Capture all persisted deploy identity values exactly once."""
    deploy_fingerprint = getattr(fingerprints, "deploy_fingerprint")
    deploy_inputs = getattr(fingerprints, "deploy_inputs")
    return DeployIdentitySnapshot(
        deploy_fingerprint=str(deploy_fingerprint()),
        deploy_inputs=_freeze_deploy_identity(deploy_inputs()),
        profile_config_fingerprint=_profile_config_fingerprint(fingerprints),
    )


def _apply_deploy_identity_to_env(
    env: dict[str, str], identity: DeployIdentitySnapshot
) -> None:
    """Keep child deployment metadata aligned with the captured identity."""
    env["COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT"] = (
        identity.profile_config_fingerprint
    )
    env["COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT"] = identity.deploy_fingerprint
    env["COMFYMODAL_V2CTL_DEPLOYMENT_HASH"] = identity.deploy_fingerprint


def write_deployment_manifest(repo_root: Path, config: config_mod.ResolvedConfig,
                              fingerprints: fp_mod.FingerprintEngine,
                              env: dict[str, str],
                              result: backend_mod.BackendResult | None,
                              *, publication: object | None = None,
                              deploy_identity: DeployIdentitySnapshot | None = None) -> Path:
    d = _deployment_manifest_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    # Direct callers from older tests/tools retain the old convenience
    # behavior.  Deploy commands always pass their pre-publication snapshot.
    if deploy_identity is None:
        deploy_fp = getattr(fingerprints, "deploy_fingerprint")()
        deploy_inputs_method = getattr(fingerprints, "deploy_inputs", None)
        deploy_inputs = (
            deploy_inputs_method() if callable(deploy_inputs_method) else {}
        )
        profile_config_fp = _profile_config_fingerprint(fingerprints)
    else:
        deploy_fp = deploy_identity.deploy_fingerprint
        deploy_inputs = _thaw_deploy_identity(deploy_identity.deploy_inputs)
        profile_config_fp = deploy_identity.profile_config_fingerprint
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "deployment_hash_namespace": DEPLOYMENT_HASH_NAMESPACE,
        "fingerprint_algorithm": FINGERPRINT_ALGORITHM,
        "deployment_hash": deploy_fp,
        "created_at": _utcnow_iso(),
        "profile": config.profile_name,
        "owner": config.owner,
        "git": {"head": config.git.head, "branch": config.git.branch, "dirty": config.git.dirty},
        "target": {"app": config.target.app, "class": config.target.class_name, "method": config.target.method},
        "resources": {"gpu": config.resources.gpu, "cpu": config.resources.cpu,
                      "memory_mb": config.resources.memory_mb,
                      "min_containers": config.resources.min_containers,
                      "scaledown_window": config.resources.scaledown_window},
        "deploy_fingerprint": deploy_fp,
        "profile_config_fingerprint": profile_config_fp,
        "deploy_inputs": deploy_inputs,
        "effective_environment": _redact_env(env),
        "runtime_override_policy": config.runtime_override_policy,
        # ── Truthful deploy-health state (E29 gate lesson) ─────────────────
        # A Modal deploy exit 0 proves only that the app was uploaded and
        # accepted ("transport deployed").  It does NOT prove the remote
        # container lifecycle (restore) runs: crash-loop tracebacks appear
        # only in Modal's remote lifecycle logs, never in the local deploy
        # BAT stdout.  runtime_health_status is therefore ALWAYS "unverified"
        # at deploy time; the first v2ctl gate/run is the health-validation
        # boundary and updates it to "verified" only on a successful run.
        "deployment_transport_status": "deployed",
        "runtime_health_status": "unverified",
        # ── Source-identity health state (E29 source-identity stop-gate) ──
        # A deploy proves the app was uploaded but NOT that the bytes the
        # container imports equal the expected local source.  source_identity
        # is "unverified" at deploy time and flips to "verified" only after a
        # successful v2ctl source-probe (remote SHA-256 == expected local
        # SHA-256 for every required module).
        "source_identity_status": "unverified",
        "health_check_note": (
            "deploy exit 0 proves transport only; remote restore lifecycle "
            "health is unverified until the first gate/run invocation observes "
            "the container actually running (or a crash loop)"
        ),
    }
    if result is not None:
        manifest["v2ctl_invocation_id"] = result.v2ctl_invocation_id
        manifest["request_id"] = result.request_id
        manifest["provenance_validation_status"] = result.provenance_validation_status
        manifest["backend"] = {
            "command": result.command,
            "exit_code": result.exit_code,
            "started_at": result.started_at,
            "ended_at": result.ended_at,
            "elapsed_seconds": result.elapsed_seconds,
        }
        manifest["artifacts"] = {
            "output_dir": str(result.artifacts.output_dir) if result.artifacts.output_dir else None,
            "run_artifact": str(result.artifacts.run_artifact) if result.artifacts.run_artifact else None,
            "summary_artifact": str(result.artifacts.summary_artifact) if result.artifacts.summary_artifact else None,
            "campaign_manifest": str(result.artifacts.campaign_manifest) if result.artifacts.campaign_manifest else None,
            "console_capture": str(result.artifacts.console_capture) if result.artifacts.console_capture else None,
            "run_artifacts": [str(p) for p in result.artifacts.run_artifacts],
            "v2ctl_invocation_id": result.artifacts.v2ctl_invocation_id,
            "request_id": result.artifacts.request_id,
            "profile": result.artifacts.profile,
            "profile_config_fingerprint": result.artifacts.profile_config_fingerprint,
            "provenance_validation_status": result.artifacts.provenance_validation_status,
        }
    if publication is not None:
        identity = getattr(publication, "identity", None)
        manifest["custom_nodes_publication"] = {
            "action": str(getattr(publication, "action", "")),
            "reason": str(getattr(publication, "reason", "")),
            "generation": str(getattr(identity, "generation", "")),
            "identity_schema": getattr(identity, "identity_schema", None),
            "packaging_policy_version": getattr(
                identity, "packaging_policy_version", None
            ),
            "file_count": getattr(identity, "file_count", None),
            "total_bytes": getattr(identity, "total_bytes", None),
            "manifest_digest": getattr(identity, "manifest_digest", None),
        }
    path = d / f"deploy_{time.strftime('%Y%m%d-%H%M%S')}_{deploy_fp[:8]}.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_golden_deployment_receipt(
    repo_root: Path,
    config: config_mod.ResolvedConfig,
    env: dict[str, str],
    deploy_identity: DeployIdentitySnapshot,
    deployment_version: int,
    manifest_path: Path,
    publication: object | None,
    source_probe_expected: dict[str, Any] | None = None,
) -> Path:
    """Write the one-time receipt for a successful native Golden deploy."""
    from . import source_probe as source_probe_mod

    expected_source = source_probe_expected or source_probe_mod.compute_expected_local(repo_root)
    # Persist the deployment projection, not the child process environment.
    # In particular this excludes PATH/TEMP, Modal credentials, request-only
    # flags, invocation IDs, and arbitrary host variables.
    deployment_flag_values = {}
    effective_values = fp_mod.FingerprintEngine(config).effective_flag_values()
    for flag in list(getattr(config, "flags", ()) or ()) + list(
        getattr(config, "unregistered", ()) or ()
    ):
        if (
            getattr(flag, "change_requires", "") in {"build", "deploy"}
            or not getattr(flag, "registered", True)
        ):
            name = str(flag.name)
            if name in env:
                deployment_flag_values[name] = str(effective_values.get(name, env[name]))
    safe_env = {
        name: str(env[name])
        for name in (
            "COMFYMODAL_V2_APP_NAME", "COMFYMODAL_V2_CLASS_NAME",
            "COMFYMODAL_V2_GPU", "COMFYMODAL_V2_MEMORY_MB",
            "COMFYMODAL_V2_CPU_REQUEST", "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST",
            "COMFYMODAL_V2_BASELINE_CPU_REQUEST", "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS",
        )
        if name in env
    }
    safe_env.update(deployment_flag_values)
    identity = getattr(publication, "identity", None)
    generation = str(getattr(identity, "generation", "") or "")
    if not generation:
        raise GateError("Golden deploy has no verified full-content S4 publication identity")
    s4_identity = {
        "generation": generation,
        "identity_schema": getattr(identity, "identity_schema", None),
        "packaging_policy_version": getattr(identity, "packaging_policy_version", None),
        "file_count": getattr(identity, "file_count", None),
        "total_bytes": getattr(identity, "total_bytes", None),
        "manifest_digest": getattr(identity, "manifest_digest", None),
    }
    planned_path = receipt_mod.receipt_path(
        repo_root, deploy_identity.deploy_fingerprint, deployment_version
    )
    # The mutable ledger points at the immutable receipt before its digest is
    # captured, so the receipt's manifest digest covers the final ledger.
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["deployment_receipt"] = str(planned_path)
    manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    receipt = receipt_mod.DeploymentReceipt(
        profile=str(config.profile_name),
        target={
            "app": str(config.target.app),
            "class": str(config.target.class_name),
            "method": str(config.target.method),
        },
        deploy_fingerprint=deploy_identity.deploy_fingerprint,
        effective_environment=safe_env,
        deployment_version=deployment_version,
        created_at=receipt_mod.now_utc(),
        modal_app=str(config.target.app),
        deployment_identity={
            "app": str(config.target.app),
            "class": str(config.target.class_name),
            "method": str(config.target.method),
            "version": deployment_version,
            "deploy_fingerprint": deploy_identity.deploy_fingerprint,
            "resources": {
                "gpu": str(config.resources.gpu),
                "cpu": int(config.resources.cpu),
                "memory_mb": int(config.resources.memory_mb),
            },
        },
        deployed_source={
            "git_head": str(config.git.head),
            "dirty_hashes": dict(config.git.dirty_hashes or {}),
        },
        source_probe={"expected": expected_source},
        image_identity={
            # Deploy output does not provide a runtime image probe.  Keep this
            # explicit rather than inventing an image ID from local state.
            "status": "not_observed_at_deploy",
        },
        workflow_model_contract={
            "profile": str(config.profile_name),
            "expected_output_sha": str(config.workload.expected_output_sha),
            "conditioning_cache": str(config.workload.conditioning_cache),
        },
        s4_generation=generation,
        profile_config_fingerprint=deploy_identity.profile_config_fingerprint,
        manifest_path=str(manifest_path),
        manifest_digest=receipt_mod.manifest_digest(manifest_path),
        s4_identity=s4_identity,
        effective_config={
            "profile": str(config.profile_name),
            "target": {
                "app": str(config.target.app),
                "class": str(config.target.class_name),
                "method": str(config.target.method),
            },
            "resources": {
                "gpu": str(config.resources.gpu),
                "cpu": int(config.resources.cpu),
                "memory_mb": int(config.resources.memory_mb),
            },
            "deploy_flags": deployment_flag_values,
            "deploy_inputs": _thaw_deploy_identity(deploy_identity.deploy_inputs),
        },
        receipt_path=str(planned_path),
    )
    path = receipt_mod.write_deployment_receipt(repo_root, receipt)
    return path


def _validate_deployment_manifest(manifest: object) -> dict | None:
    """Return a trustworthy current deployment manifest, otherwise ``None``.

    Schema 2 has two spellings for the same deployment identity because the
    latter is the compatibility field used by the control plane.  Treat both
    as required and equal: accepting either one independently would allow a
    persisted manifest to claim a different deployment from the one v2ctl
    compares before a run.  Older schema-1 records remain stale and are not
    promoted to current state.
    """
    if not isinstance(manifest, dict):
        return None
    if manifest.get("schema_version") != SCHEMA_VERSION:
        return None
    if manifest.get("deployment_hash_namespace") != DEPLOYMENT_HASH_NAMESPACE:
        return None
    if manifest.get("fingerprint_algorithm") != FINGERPRINT_ALGORITHM:
        return None

    deployment_hash = manifest.get("deployment_hash")
    deploy_fingerprint = manifest.get("deploy_fingerprint")
    if not (
        isinstance(deployment_hash, str)
        and deployment_hash.strip()
        and isinstance(deploy_fingerprint, str)
        and deploy_fingerprint.strip()
        and deployment_hash == deploy_fingerprint
    ):
        return None
    return manifest


def _manifest_target_identity(value: object) -> tuple[str, str, str] | None:
    """Extract a complete target identity from either manifest spelling."""
    if not isinstance(value, Mapping):
        return None
    app = value.get("app")
    class_name = value.get("class", value.get("class_name"))
    method = value.get("method")
    if not all(isinstance(item, str) and item.strip() for item in (app, class_name, method)):
        return None
    return str(app), str(class_name), str(method)


def _deployment_manifest_target(manifest: Mapping[str, object]) -> tuple[str, str, str] | None:
    """Return a target only when all persisted target spellings agree.

    Deployment manifests written by different control-plane generations put
    the target at either ``target`` or ``deploy_inputs.target`` and use
    ``class`` versus ``class_name``.  A disagreement is not a usable target:
    target checks must fail closed rather than selecting whichever spelling is
    convenient.
    """
    identities: list[tuple[str, str, str]] = []
    top_level = _manifest_target_identity(manifest.get("target"))
    if manifest.get("target") is not None:
        if top_level is None:
            return None
        identities.append(top_level)
    deploy_inputs = manifest.get("deploy_inputs")
    if isinstance(deploy_inputs, Mapping) and "target" in deploy_inputs:
        deploy_target = _manifest_target_identity(deploy_inputs.get("target"))
        if deploy_target is None:
            return None
        identities.append(deploy_target)
    if not identities or any(identity != identities[0] for identity in identities[1:]):
        return None
    return identities[0]


def _requested_target_identity(target: object) -> tuple[str, str, str] | None:
    """Normalize a config target or target mapping for manifest selection."""
    if isinstance(target, Mapping):
        return _manifest_target_identity(target)
    app = getattr(target, "app", None)
    class_name = getattr(target, "class_name", getattr(target, "class", None))
    method = getattr(target, "method", None)
    return _manifest_target_identity(
        {"app": app, "class_name": class_name, "method": method}
    )


def _manifest_matches_request(
    manifest: Mapping[str, object], *, profile: str | None, target: object | None
) -> bool:
    if profile is not None and manifest.get("profile") != profile:
        return False
    if target is None:
        return True
    requested = _requested_target_identity(target)
    return requested is not None and _deployment_manifest_target(manifest) == requested


def _read_valid_deployment_manifest(path: Path) -> dict | None:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    validated = _validate_deployment_manifest(manifest)
    return validated


def latest_deployment_manifest_path(
    repo_root: Path, *, profile: str | None = None, target: object | None = None
) -> Path | None:
    """Return the newest valid manifest matching the optional request identity.

    With no filters this retains the historical global ``latest`` behavior.
    Filtered callers scan backwards through the ledger so an unrelated newer
    deployment cannot shadow the requested app/profile.
    """
    d = _deployment_manifest_dir(repo_root)
    if not d.is_dir():
        return None
    files = sorted(d.glob("deploy_*.json"))
    if not files:
        return None
    candidates = files[-1:] if profile is None and target is None else reversed(files)
    for path in candidates:
        manifest = _read_valid_deployment_manifest(path)
        if manifest is not None and _manifest_matches_request(
            manifest, profile=profile, target=target
        ):
            return path
    return None


def latest_deployment_manifest(
    repo_root: Path, *, profile: str | None = None, target: object | None = None
) -> dict | None:
    """Return the newest valid deployment manifest for an optional identity."""
    path = latest_deployment_manifest_path(repo_root, profile=profile, target=target)
    if path is None:
        return None
    return _read_valid_deployment_manifest(path)


def _golden_capture_guard_class(repo_root: Path):
    """Load the root-level guard when this CLI is launched as a script."""
    try:
        from deploy_warmup import GoldenCaptureGuard
        return GoldenCaptureGuard
    except ModuleNotFoundError:
        path = repo_root / "deploy_warmup.py"
        spec = importlib.util.spec_from_file_location("_v2ctl_deploy_warmup", path)
        if spec is None or spec.loader is None:
            raise V2CtlError(f"Golden capture guard module is unavailable: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.GoldenCaptureGuard


def write_run_manifest(repo_root: Path, config: config_mod.ResolvedConfig,
                       fingerprints: fp_mod.FingerprintEngine,
                       env: dict[str, str],
                       result: backend_mod.BackendResult,
                       provenance: prov_mod.Provenance | None,
                       deployment_receipt: receipt_mod.DeploymentReceipt | None = None) -> Path:
    d = _run_manifest_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    run_fp = val_mod._bound_run_fingerprint(fingerprints, deployment_receipt)
    deploy_fp = (
        deployment_receipt.deploy_fingerprint
        if deployment_receipt is not None else fingerprints.deploy_fingerprint()
    )
    profile_fp = (
        deployment_receipt.profile_config_fingerprint
        if deployment_receipt is not None and deployment_receipt.profile_config_fingerprint
        else fingerprints.profile_config_fingerprint()
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "deployment_hash_namespace": DEPLOYMENT_HASH_NAMESPACE,
        "fingerprint_algorithm": FINGERPRINT_ALGORITHM,
        "deployment_hash": deploy_fp,
        "created_at": _utcnow_iso(),
        "profile": config.profile_name,
        "owner": config.owner,
        "deploy_fingerprint": deploy_fp,
        "run_fingerprint": run_fp,
        "v2ctl_invocation_id": result.v2ctl_invocation_id,
        "profile_config_fingerprint": profile_fp,
        "request_id": result.request_id,
        "provenance_validation_status": result.provenance_validation_status,
        "workload": {
            "fresh_required": config.workload.fresh_required,
            "conditioning_cache": config.workload.conditioning_cache,
            "expected_output_sha": config.workload.expected_output_sha,
            "run_count": config.workload.run_count,
            "gap_seconds": config.workload.gap_seconds,
            "nonce": config.workload.nonce,
        },
        "effective_environment": _redact_env(env),
        "backend": {
            "command": result.command,
            "exit_code": result.exit_code,
            "started_at": result.started_at,
            "ended_at": result.ended_at,
            "elapsed_seconds": result.elapsed_seconds,
        },
        "artifacts": {
            "output_dir": str(result.artifacts.output_dir) if result.artifacts.output_dir else None,
            "run_artifact": str(result.artifacts.run_artifact) if result.artifacts.run_artifact else None,
            "summary_artifact": str(result.artifacts.summary_artifact) if result.artifacts.summary_artifact else None,
            "campaign_manifest": str(result.artifacts.campaign_manifest) if result.artifacts.campaign_manifest else None,
            "console_capture": str(result.artifacts.console_capture) if result.artifacts.console_capture else None,
            "run_artifacts": [str(p) for p in result.artifacts.run_artifacts],
            "v2ctl_invocation_id": result.artifacts.v2ctl_invocation_id,
            "request_id": result.artifacts.request_id,
            "profile": result.artifacts.profile,
            "profile_config_fingerprint": result.artifacts.profile_config_fingerprint,
            "provenance_validation_status": result.artifacts.provenance_validation_status,
        },
    }
    if deployment_receipt is not None:
        manifest.update({
            "deployment_receipt_path": deployment_receipt.receipt_path,
            "deployment_receipt_integrity_digest": deployment_receipt.to_dict()[
                "integrity_digest"
            ],
            "deployment_version": deployment_receipt.deployment_version,
            "receipt_profile": deployment_receipt.profile,
            "receipt_target": dict(deployment_receipt.target),
            "receipt_deploy_fingerprint": deployment_receipt.deploy_fingerprint,
            "receipt_source_probe_expected": deployment_receipt.source_probe.get("expected"),
            "receipt_manifest_path": deployment_receipt.manifest_path,
            "receipt_manifest_digest": deployment_receipt.manifest_digest,
            "source_probe_evidence_path": str(receipt_mod.source_probe_evidence_path(
                repo_root, deployment_receipt
            )),
        })
    if provenance is not None:
        manifest["provenance"] = provenance.to_dict()
    path = d / f"run_{time.strftime('%Y%m%d-%H%M%S')}_{run_fp[:8]}.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def diff_deploy_inputs(expected: dict, actual: dict) -> list[str]:
    """Leaf-path diff between two deploy_inputs dicts (sorted names)."""
    changed: list[str] = []

    def walk(a, b, prefix: str) -> None:
        keys = sorted(set(a) | set(b))
        for k in keys:
            leaf = f"{prefix}.{k}" if prefix else k
            av = a.get(k)
            bv = b.get(k)
            if isinstance(av, dict) and isinstance(bv, dict):
                walk(av, bv, leaf)
            elif av != bv:
                changed.append(f"{leaf}: {av!r} -> {bv!r}")

    walk(expected, actual, "")
    return changed


# ── Runtime-override gate ──────────────────────────────────────────────

def enforce_runtime_overrides(config: config_mod.ResolvedConfig,
                              inventory: ro_mod.RuntimeOverrideInventory,
                              *,
                              spend: bool) -> None:
    """Fail before benchmark spend when runtime flag files are present."""
    policy = config.runtime_override_policy or ro_mod.DEFAULT_RUNTIME_OVERRIDE_POLICY
    present = inventory.list_local()
    if policy == "forbid" and present:
        names = ", ".join(f"{o.name}={o.value} ({o.source})" for o in present)
        raise RuntimeOverrideViolation(
            f"runtime flag files present and policy={policy}; refusing before spend. "
            f"Files: {names}. Clear explicitly with "
            f"`python tools/v2ctl.py runtime-flags clear <NAME>`; never auto-deleted.",
            [{"name": o.name, "value": o.value, "source": o.source} for o in present],
        )
    if spend and policy == "forbid" and inventory.list_remote():
        # Remote listing requires a helper; in this phase no helper is wired,
        # so list_remote() returns [] and the local check above is the gate.
        pass


# ── Command implementations ────────────────────────────────────────────

def cmd_version(args, repo_root: Path) -> int:
    print(f"v2ctl {VERSION} (schema {SCHEMA_VERSION})")
    return 0


def cmd_golden_status(args, repo_root: Path) -> int:
    """Report local Golden readiness without invoking a backend.

    This is deliberately a local status view.  A matching deployment manifest
    proves only that the requested configuration was deployed; runtime and
    source identity remain unverified until their explicit checks run.
    """
    identity_error = _reject_golden_identity_args(args, public=True)
    if identity_error is not None:
        return identity_error
    try:
        _, _, _, config, fingerprints, _, _ = _build_components_for_args(
            repo_root, args
        )
        _reject_protected_effective_target(config, command="v2ctl golden status")
        _reject_golden_mode_override(config, command="v2ctl golden status")
        requested_target = {
            "app": config.target.app,
            "class": config.target.class_name,
            "method": config.target.method,
        }
        manifest = latest_deployment_manifest(
            repo_root, profile=config.profile_name, target=requested_target
        )
        manifest_path_obj = latest_deployment_manifest_path(
            repo_root, profile=config.profile_name, target=requested_target
        )
        manifest_path = str(manifest_path_obj) if manifest_path_obj else None

        current_fingerprint = fingerprints.deploy_fingerprint()
        stored_fingerprint = manifest.get("deploy_fingerprint") if manifest else None
        manifest_target_match = bool(
            manifest
            and _deployment_manifest_target(manifest)
            == _requested_target_identity(requested_target)
        )
        manifest_is_golden = bool(
            manifest
            and manifest.get("profile") == config.profile_name
            and manifest_target_match
        )
        fingerprint_match = bool(
            manifest_is_golden and stored_fingerprint == current_fingerprint
        )
        # An unrelated/latest production manifest is useful mismatch evidence,
        # never a source of Golden health state.
        matching_manifest = manifest if fingerprint_match else None
        deployed_state_path = repo_root / ".deployed_state.json"
        deployed_state: dict[str, object] | None = None
        deployed_state_error = ""
        if deployed_state_path.is_file():
            try:
                raw_state = json.loads(deployed_state_path.read_text(encoding="utf-8"))
                if isinstance(raw_state, dict):
                    deployed_state = raw_state
                else:
                    deployed_state_error = "deployed state is not an object"
            except (OSError, json.JSONDecodeError) as exc:
                deployed_state_error = f"{type(exc).__name__}: {exc}"
        deployed_target_match = bool(
            deployed_state
            and deployed_state.get("app_name") == config.target.app
            and deployed_state.get("class_name") == config.target.class_name
        )
        lock = locking_mod.DeployLock(repo_root / ".v2ctl" / "deploy.lock")
        lock_status = lock.status()
        lock_active = bool(lock_status is not None and not lock.is_stale(lock_status))
        GoldenCaptureGuard = _golden_capture_guard_class(repo_root)

        # The legacy state file may describe another app.  Once the selected
        # manifest matches the requested fingerprint, derive guard identity
        # from that manifest instead of allowing stale state to choose the
        # capture-guard namespace.
        guard_deployment_info = {}
        if matching_manifest is not None:
            guard_deployment_info = {
                "deployment_combined_hash": matching_manifest.get(
                    "deployment_hash", ""
                ),
                "deploy_fingerprint": matching_manifest.get(
                    "deploy_fingerprint", ""
                ),
            }
        guard_identity = GoldenCaptureGuard.deployment_identity(
            app_name=config.target.app,
            class_name=config.target.class_name,
            gpu=config.resources.gpu,
            deployment_info=guard_deployment_info,
            deploy_fingerprint=current_fingerprint,
        )
        guard = GoldenCaptureGuard(
            GoldenCaptureGuard.path_for_deployment(repo_root, guard_identity),
            deployment_identity=guard_identity,
        )
        guard_state = guard.snapshot()
        overrides = ro_mod.RuntimeOverrideInventory(
            local_dir=repo_root / ".runtime_state"
        ).list_local()

        out = {
            "schema_version": SCHEMA_VERSION,
            "profile": GOLDEN_P1_PROFILE,
            "target": {
                "app": config.target.app,
                "class": config.target.class_name,
                "method": config.target.method,
            },
            "deployment_manifest": manifest_path,
            "deployment_fingerprint_current": current_fingerprint,
            "deployment_fingerprint_stored": stored_fingerprint,
            "deployment_fingerprint_match": fingerprint_match,
            "deployment_target_match": manifest_target_match,
            "deployed_state_present": deployed_state is not None,
            "deployed_state_target_match": deployed_target_match,
            "deployed_state_app": (deployed_state or {}).get("app_name"),
            "deployed_state_class": (deployed_state or {}).get("class_name"),
            "deployed_state_combined_hash": (deployed_state or {}).get(
                "deployment_combined_hash"
            ),
            "deployed_state_error": deployed_state_error,
            "runtime_health_status": (matching_manifest or {}).get(
                "runtime_health_status", "unverified"
            ),
            "source_identity_status": (matching_manifest or {}).get(
                "source_identity_status", "unverified"
            ),
            "runtime_overrides_present": len(overrides),
            "deploy_lock_active": lock_active,
            "capture_guard": guard_state,
            "next_request_guarded": bool(guard_state.get("post_capture_guard_pending")),
            "remote_checks": "not_performed",
        }
        out["ready"] = bool(
            fingerprint_match
            and out["runtime_health_status"] == "verified"
            and out["source_identity_status"] == "verified"
            and not out["runtime_overrides_present"]
            and not lock_active
            # A pending post-capture guard makes the next request invalid;
            # readiness therefore remains false until that guard is consumed.
            and not out["next_request_guarded"]
        )
        if args.json:
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("[v2ctl.golden.status]")
            for key, value in out.items():
                print(f"{key}={value}")
        return 0 if out["ready"] else 1
    except (V2CtlError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_golden(args, repo_root: Path) -> int:
    """Dispatch the public Golden namespace to the canonical handlers."""
    if args.golden_command not in {"doctor", "status", "deploy", "run", "publisher-bootstrap"}:
        print(
            "ERROR: public Golden commands are doctor, status, deploy, run, "
            "and publisher-bootstrap",
            file=sys.stderr,
        )
        return 2
    requested_profile = getattr(args, "profile", "production")
    if requested_profile not in ("production", GOLDEN_P1_PROFILE):
        print(
            f"ERROR: `golden` commands use profile {GOLDEN_P1_PROFILE!r}; "
            f"received --profile {requested_profile!r}",
            file=sys.stderr,
        )
        return 1
    identity_error = _reject_golden_identity_args(args, public=True)
    if identity_error is not None:
        return identity_error
    public_run = args.golden_command in {"deploy", "run"}
    dry_run = bool(getattr(args, "dry_run", False))
    if public_run and not dry_run:
        if not getattr(args, "app", None):
            print(
                "ERROR: Golden deploy/run requires --app <experimental-app>; "
                f"{PROTECTED_GOLDEN_APP!r} is protected",
                file=sys.stderr,
            )
            return 2
    args.profile = GOLDEN_P1_PROFILE
    args.golden_public = True
    if args.golden_command == "run":
        if args.run_count not in (None, 1):
            print("ERROR: public Golden run always executes exactly one request", file=sys.stderr)
            return 2
        args.run_count = 1
    if args.golden_command == "status":
        return cmd_golden_status(args, repo_root)
    handlers = {
        "doctor": cmd_doctor,
        "deploy": cmd_deploy,
        "run": cmd_run,
        "publisher-bootstrap": cmd_publisher_bootstrap,
    }
    handler = handlers.get(args.golden_command)
    if handler is None:
        print(f"usage: v2ctl golden <command>", file=sys.stderr)
        return 2
    return handler(args, repo_root)


def cmd_doctor(args, repo_root: Path) -> int:
    identity_error = _reject_golden_identity_args(args)
    if identity_error is not None:
        return identity_error
    problems: list[str] = []
    out: list[str] = ["[v2ctl.doctor]"]
    selected_config = None
    selected_fingerprints = None
    # git state
    git = config_mod.compute_git_state(repo_root)
    out.append(f"git.head={git.head}")
    out.append(f"git.branch={git.branch}")
    out.append(f"git.dirty={int(git.dirty)}")
    # python
    out.append(f"python={sys.version.split()[0]}")
    try:
        _, _, _, selected_config, selected_fingerprints, _, _ = _build_components_for_args(
            repo_root, args
        )
        _reject_protected_effective_target(selected_config, command="v2ctl doctor")
        _reject_golden_mode_override(selected_config, command="v2ctl doctor")
        out.append(f"profile={selected_config.profile_name}")
        out.append(f"target.app={selected_config.target.app}")
        out.append(f"target.class={selected_config.target.class_name}")
        out.append(f"target.method={selected_config.target.method}")
    except GateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (V2CtlError, OSError) as exc:
        problems.append(f"config resolution failed: {exc}")
    # backend scripts
    backend_registry = backend_mod.BackendRegistry(repo_root)
    for spec in backend_registry.available():
        exists = spec.bat_path is not None and spec.bat_path.is_file()
        out.append(f"backend.{spec.name}.exists={int(exists)} kind={spec.kind}")
        if not exists:
            problems.append(f"backend {spec.name} missing: {spec.bat_path}")
    # registry/profile parse
    try:
        registry = registry_mod.FlagRegistry(repo_root / "config" / "v2" / "flag_registry.toml")
        registry.load()
        out.append(f"registry.flags={len(registry.registered_names())}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"registry parse failed: {exc}")
    try:
        profiles = profiles_mod.Profiles(repo_root / "config" / "v2" / "profiles")
        for name in profiles.available():
            profiles.resolve(name)
        out.append(f"profiles={','.join(profiles.available())}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"profile parse failed: {exc}")
    # runtime override policy
    inventory = ro_mod.RuntimeOverrideInventory(local_dir=repo_root / ".runtime_state")
    present = inventory.list_local()
    out.append(f"runtime_override_policy={ro_mod.DEFAULT_RUNTIME_OVERRIDE_POLICY}")
    out.append(f"runtime_overrides.present={len(present)}")
    for o in present:
        out.append(f"runtime_override.{o.name}={o.value} source={o.source}")
        problems.append(f"runtime flag file present: {o.name} (clear before gate/deploy-run)")
    # deploy lock
    lock = locking_mod.DeployLock(repo_root / ".v2ctl" / "deploy.lock")
    status = lock.status()
    if status is None:
        out.append("deploy.lock=none")
    else:
        out.append(f"deploy.lock.owner={status.get('owner')} pid={status.get('pid')} "
                   f"host={status.get('host')} target={status.get('target')} "
                   f"profile={status.get('profile')} stale={int(lock.is_stale(status))}")
        if lock.is_stale(status):
            problems.append(f"deploy lock is stale (owner {status.get('owner')}); "
                            "release with `lock force-release` after confirming ownership")
    # deployment fingerprint match
    manifest = None
    if selected_config is not None:
        requested_target = {
            "app": selected_config.target.app,
            "class": selected_config.target.class_name,
            "method": selected_config.target.method,
        }
        manifest = latest_deployment_manifest(
            repo_root,
            profile=selected_config.profile_name,
            target=requested_target,
        )
    if manifest is None:
        out.append("deployment.manifest=none")
        problems.append("no deployment manifest found; run `v2ctl deploy-run` or `v2ctl deploy` first")
    else:
        try:
            config = selected_config
            fingerprints = selected_fingerprints
            if config is None or fingerprints is None:
                raise GateError("selected profile could not be resolved")
            current = fingerprints.deploy_fingerprint()
            stored = manifest.get("deploy_fingerprint")
            requested_target = {
                "app": config.target.app,
                "class": config.target.class_name,
                "method": config.target.method,
            }
            target_match = (
                _deployment_manifest_target(manifest)
                == _requested_target_identity(requested_target)
            )
            match = stored == current and target_match
            out.append(f"deployment.fingerprint.stored={stored}")
            out.append(f"deployment.fingerprint.current={current}")
            out.append(f"deployment.fingerprint.match={int(match)}")
            out.append(f"deployment.target.match={int(target_match)}")
            if not match:
                problems.append("deployment fingerprint mismatch: deploy-required state changed since last deploy")
        except V2CtlError as exc:
            problems.append(f"config resolution failed: {exc}")
    for line in out:
        print(line)
    if problems:
        print("[v2ctl.doctor] PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("[v2ctl.doctor] OK")
    return 0


def _refuse_protected_explicit(config: config_mod.ResolvedConfig) -> None:
    """Protected names must never arrive through explicit override channels."""
    policy = env_mod.ProtectedPolicy.default()
    for flag in [*config.flags, *config.unregistered]:
        if flag.source in ("cli", "inherit", "set"):
            policy.check(flag.name)


def cmd_config(args, repo_root: Path) -> int:
    identity_error = _reject_golden_identity_args(args)
    if identity_error is not None:
        return identity_error
    try:
        _, _, _, config, fingerprints, _, _ = _build_components_for_args(repo_root, args)
        _reject_protected_effective_target(config, command="v2ctl config")
        _refuse_protected_explicit(config)
        _reject_golden_mode_override(config, command="v2ctl config")
    except V2CtlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    out = {
        "schema_version": SCHEMA_VERSION,
        "profile": config.profile_name,
        "owner": config.owner,
        "git": {"head": config.git.head, "branch": config.git.branch, "dirty": config.git.dirty},
        "target": {"app": config.target.app, "class": config.target.class_name, "method": config.target.method},
        "resources": {"gpu": config.resources.gpu, "cpu": config.resources.cpu,
                      "memory_mb": config.resources.memory_mb,
                      "min_containers": config.resources.min_containers,
                      "scaledown_window": config.resources.scaledown_window},
        "workload": {"fresh_required": config.workload.fresh_required,
                     "conditioning_cache": config.workload.conditioning_cache,
                     "expected_output_sha": config.workload.expected_output_sha,
                     "run_count": config.workload.run_count,
                     "gap_seconds": config.workload.gap_seconds,
                     "nonce": config.workload.nonce},
        "runtime_override_policy": config.runtime_override_policy,
        "deploy_fingerprint": fingerprints.deploy_fingerprint(),
        "run_fingerprint": fingerprints.run_fingerprint(),
        "profile_config_fingerprint": fingerprints.profile_config_fingerprint(),
        "flags": [
            {
                "name": f.name, "value": f.value, "source": f.source,
                "registered": f.registered, "consumed_at": f.consumed_at,
                "change_requires": f.change_requires, "type": f.type,
                "description": f.description,
            }
            for f in config.flags
        ],
        "unregistered": [
            {"name": f.name, "value": f.value, "source": f.source,
             "change_requires": f.change_requires}
            for f in config.unregistered
        ],
    }
    if args.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_flags(args, repo_root: Path) -> int:
    registry = registry_mod.FlagRegistry(repo_root / "config" / "v2" / "flag_registry.toml")
    registry.load()
    sub = args.flags_command
    if sub == "list":
        for f in registry.all_flags():
            print(f"{f.name}\ttype={f.type}\tconsumed_at={f.consumed_at}\t"
                  f"change_requires={f.change_requires}\towner={f.owner}")
        return 0
    if sub == "explain":
        name = args.name
        f = registry.get(name)
        if f is None:
            print(f"UNREGISTERED: {name}")
            print("  Metadata is not admission: explicit --set is accepted for deploy/deploy-run.")
            print("  Run-only use is refused until registered or proven request-time safe.")
            return 0
        print(f"name={f.name}")
        print(f"type={f.type}")
        print(f"default={f.default}")
        print(f"consumed_at={f.consumed_at}")
        print(f"change_requires={f.change_requires}")
        print(f"owner={f.owner}")
        print(f"description={f.description}")
        if f.enum_values:
            print(f"enum_values={','.join(f.enum_values)}")
        if f.min is not None or f.max is not None:
            print(f"range=[{f.min},{f.max}]")
        if f.regex:
            print(f"regex={f.regex}")
        if f.aliases:
            print(f"aliases={','.join(f.aliases)}")
        if f.deprecated:
            print("deprecated=true")
        return 0
    if sub == "validate":
        try:
            name, value = config_mod.ConfigResolver.parse_set_spec(args.name_value)
        except FlagError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        registry_mod.FlagRegistry.validate_name(name)
        f = registry.get(name)
        if f is None:
            print(f"UNREGISTERED: {name}={value} — syntax OK; accepted for deploy/deploy-run; "
                  "run-only refused.")
            return 0
        try:
            normalized = f.validate_value(value)
        except FlagError as exc:
            print(f"INVALID: {exc}", file=sys.stderr)
            return 1
        print(f"VALID: {name}={normalized} (type={f.type}, change_requires={f.change_requires})")
        return 0
    if sub == "audit":
        consumed = _scan_consumed_names(repo_root)
        profiles = profiles_mod.Profiles(repo_root / "config" / "v2" / "profiles")
        profile_set: set[str] = set()
        for name in profiles.available():
            profile_set |= set(profiles.resolve(name).environment)
        report = registry.audit(consumed, profile_set)
        print("[v2ctl.flags.audit] advisory lint only - not a runtime whitelist")
        print(f"consumed+registered ({len(report.consumed_registered)}):")
        for n in report.consumed_registered:
            print(f"  OK {n}")
        print(f"consumed+unregistered ({len(report.consumed_unregistered)}):")
        for n in report.consumed_unregistered:
            print(f"  WARN {n} (runtime reads it; registry has no metadata)")
        print(f"registered+no-consumer ({len(report.registered_no_consumer)}):")
        for n in report.registered_no_consumer:
            print(f"  WARN {n} (registered but no consumer found in sources)")
        print(f"profile-set+no-consumer ({len(report.profile_set_no_consumer)}):")
        for n in report.profile_set_no_consumer:
            print(f"  WARN {n} (profile sets it; no consumer found)")
        return 0
    print("usage: v2ctl flags list|explain NAME|validate NAME=VALUE|audit", file=sys.stderr)
    return 2


def _require_no_deploy_in_flight(repo_root: Path) -> None:
    lock = locking_mod.DeployLock(repo_root / ".v2ctl" / "deploy.lock")
    status = lock.status()
    if status is not None and not lock.is_stale(status):
        raise LockHeldError(
            f"deploy in flight by {status.get('owner')} (pid {status.get('pid')} "
            f"on {status.get('host')}, target {status.get('target')}, "
            f"profile {status.get('profile')}); run refused until released",
            owner=status.get("owner"), pid=status.get("pid"), host=status.get("host"),
            target=status.get("target"), profile=status.get("profile"),
            timestamp=status.get("timestamp"),
        )


def _dry_run_report(config: config_mod.ResolvedConfig, fingerprints: fp_mod.FingerprintEngine,
                    env: dict[str, str], command: str) -> None:
    print("[v2ctl.dry-run] no invocation performed; effective configuration:")
    print(f"profile={config.profile_name} owner={config.owner}")
    print(
        f"target.app={config.target.app} target.class={config.target.class_name} "
        f"target.method={config.target.method}"
    )
    print(f"deploy_fingerprint={fingerprints.deploy_fingerprint()}")
    print(f"run_fingerprint={fingerprints.run_fingerprint()}")
    print(f"selector={_backend_selector(config) or '(none)'}")
    print(f"command={command}")
    print("[v2ctl.dry-run] child environment (redacted):")
    redacted = env_mod.EnvironmentBuilder().display(env)
    for k in sorted(redacted):
        print(f"  {k}={redacted[k]}")


def _publish_golden_custom_nodes(
    repo_root: Path, publisher_app_name: str | None = None
):
    """Mirror the canonical custom-node source before a native Golden deploy.

    Imports of ``modal`` and ``modal_client`` stay below the non-dry-run
    boundary: dry-run must remain a local command with no Volume access.  The
    compatibility publisher receives the shared publisher app and active
    workspace explicitly rather than consulting the user's ambient Modal
    profile.
    """
    from . import custom_nodes as custom_nodes_mod

    # Keep the optional parameter as a compatibility surface for older hooks,
    # but never allow a consumer name to select the authority.
    publisher_app_name = CUSTOM_NODES_PUBLISHER_APP_NAME

    source_root = custom_nodes_mod.resolve_custom_nodes_root(repo_root)
    workspace = _active_workspace(repo_root)

    def identity_provider(_root: str | Path) -> dict[str, str]:
        from comfymodal_runtime.deployment_spec import build_deployment_identity

        identity = build_deployment_identity(
            repo_root / "comfymodal_runtime",
            custom_node_paths=[source_root],
        )
        return {"generation": identity.custom_node_hash}

    async def publisher(archive: bytes):
        # Import the legacy compatibility client only after receipt evaluation
        # has determined that publication is required.
        from modal_client import sync_custom_nodes

        return await sync_custom_nodes(
            archive, workspace=workspace, app_name=publisher_app_name
        )

    try:
        decision = custom_nodes_mod.run_publish_or_skip(
            source_root,
            volume_name=CUSTOM_NODES_VOLUME_NAME,
            publisher=publisher,
            workspace=workspace,
            identity_provider=identity_provider,
        )
    except Exception as exc:  # noqa: BLE001 - publication is a deploy gate
        raise GateError(f"custom-node publication failed: {type(exc).__name__}: {exc}") from exc
    if decision.skip:
        print(
            "[custom_nodes.publish] decision=skip_exact "
            f"reason={decision.reason} "
            f"generation={decision.identity.generation[:12]} "
            f"schema={custom_nodes_mod.RECEIPT_SCHEMA_VERSION} "
            f"policy={custom_nodes_mod.PACKAGING_POLICY_VERSION}"
        )
        return decision
    if decision.action not in {"published", "recovered"} or (
        decision.action == "published" and decision.reason != "published_verified"
    ):
        result = getattr(decision, "result", None)
        if isinstance(result, dict):
            identity = getattr(decision, "identity", None)
            expected_generation = str(getattr(identity, "generation", "") or "")
            result_generation = str(result.get("generation") or "")
            # The publisher result is intentionally bounded to scalar proof
            # values.  ``readback_generation`` is optional for older publisher
            # responses; null makes a host readback gap visible without
            # dumping the response (or any credentials it might contain).
            diagnostic = json.dumps(
                {
                    "status": result.get("status"),
                    "comfyapp_version": result.get("comfyapp_version"),
                    "reason": result.get("reason"),
                    "error": result.get("error"),
                    "expected_generation": expected_generation[:16] or None,
                    "result_generation": result_generation[:16] or None,
                    "readback_generation": str(
                        result.get("readback_generation") or ""
                    )[:16] or None,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        else:
            diagnostic = json.dumps(
                {
                    "expected_generation": str(
                        getattr(getattr(decision, "identity", None), "generation", "")
                        or ""
                    )[:16] or None,
                    "result_generation": None,
                    "readback_generation": None,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        raise GateError(
            "Golden deploy requires verified custom-node publication: "
            f"{decision.reason} result={diagnostic}"
        )
    print(
        f"[custom_nodes.publish] decision={decision.action} reason={decision.reason} "
        f"generation={decision.identity.generation[:12]} "
        f"schema={custom_nodes_mod.RECEIPT_SCHEMA_VERSION} "
        f"policy={custom_nodes_mod.PACKAGING_POLICY_VERSION}"
    )
    return decision


def _invoke_golden_publisher(
    repo_root: Path, publisher_app_name: str
):
    """Pass the isolated app to the current hook without breaking old hooks."""
    hook = _publish_golden_custom_nodes
    try:
        parameters = inspect.signature(hook).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "publisher_app_name" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_POSITIONAL
        for parameter in parameters.values()
    ):
        return hook(repo_root, CUSTOM_NODES_PUBLISHER_APP_NAME)
    return hook(repo_root)


def cmd_publisher_bootstrap(args, repo_root: Path) -> int:
    """Deploy the shared custom-node ``comfyapp`` publisher."""
    identity_error = _reject_golden_identity_args(args, public=True)
    if identity_error is not None:
        return identity_error
    dry_run = bool(getattr(args, "dry_run", False))
    # Bootstrap owns the shared publication resource, so its effective target
    # is stable and does not inherit a consumer's app identity.  Keep accepting
    # the old --app option at the parser boundary for compatibility.
    args.app = CUSTOM_NODES_PUBLISHER_APP_NAME

    try:
        (
            _registry,
            _profiles,
            _resolver,
            config,
            fingerprints,
            env_builder,
            backend_registry,
        ) = _build_components_for_args(repo_root, args)
        _reject_protected_effective_target(config, command="v2ctl golden publisher-bootstrap")
        publisher_app_name = CUSTOM_NODES_PUBLISHER_APP_NAME
        invocation_id = _new_invocation_id()
        spec = backend_registry.publisher_bootstrap()
        env = env_builder.build(
            config,
            host_env=os.environ,
            backend_extra={
                **_identity_env_for_command("deploy", config),
                **_canonical_metadata_env(config, fingerprints, invocation_id),
            },
        )
        env = _native_golden_deploy_env(env)
        if not dry_run:
            env.update(_active_workspace_credentials(repo_root))
        extra_args = ["--name", publisher_app_name]
        command = backend_mod.BackendRunner.build_command_line(spec, extra_args)
        if dry_run:
            _dry_run_report(config, fingerprints, env, command)
            print(f"publisher_app={publisher_app_name}")
            print("deployment_manifest=none")
            return 0

        lock = locking_mod.DeployLock(repo_root / ".v2ctl" / "deploy.lock")
        lock.acquire(
            owner=config.owner or args.owner or "v2ctl",
            target=publisher_app_name,
            profile=config.profile_name,
        )
        try:
            print(
                f"[v2ctl.publisher-bootstrap] app={publisher_app_name} "
                f"command={command}"
            )
            pre_version = _app_version_number(publisher_app_name)
            if pre_version is None:
                print(
                    "ERROR: unable to establish the publisher app's pre-deploy "
                    "version; refusing to invoke the backend",
                    file=sys.stderr,
                )
                return 1

            result = backend_mod.BackendRunner(repo_root, env_builder).run(
                spec,
                config=config,
                extra_args=extra_args,
                extra_env=env,
                capture=True,
                invocation_id=invocation_id,
            )
            post_version = _app_version_number(publisher_app_name)
            if post_version is None:
                print(
                    "ERROR: unable to establish the publisher app's post-deploy "
                    "version; refusing to treat this bootstrap as valid",
                    file=sys.stderr,
                )
                return 1
            if post_version <= pre_version:
                _print_backend_diagnostic(result, env)
                print(
                    "ERROR: publisher bootstrap reported success but the app's "
                    "deployment version did NOT advance; refusing to treat it "
                    "as valid",
                    file=sys.stderr,
                )
                return 1
            if not result.ok():
                _print_backend_diagnostic(result, env)
                return result.exit_code if result.exit_code else 1
            print(
                f"[v2ctl.publisher-bootstrap] exit={result.exit_code} "
                f"version={pre_version}->{post_version}"
            )
            return 0
        finally:
            lock.release()
    except (V2CtlError, OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_deploy(args, repo_root: Path) -> int:
    identity_error = _reject_golden_identity_args(args)
    if identity_error is not None:
        return identity_error
    try:
        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = _build_components_for_args(
            repo_root, args
        )
        _reject_protected_effective_target(config, command="v2ctl deploy")
        _reject_golden_mode_override(config, command="v2ctl deploy")
        unregistered_explicit = [
            flag for flag in config.unregistered if flag.source in {"cli", "inherit", "set"}
        ]
        if unregistered_explicit:
            print(
                "[v2ctl.deploy] WARNING: unregistered explicit flags are not "
                "admission metadata; they will be recorded but require exact "
                "receipt proof for later bound requests: "
                + ", ".join(flag.name for flag in unregistered_explicit),
                file=sys.stderr,
            )
        invocation_id = _new_invocation_id()
        native_golden = config.profile_name == GOLDEN_P1_PROFILE
        spec = (
            backend_registry.native_deploy()
            if native_golden else backend_registry.deploy_only()
        )
        publisher_app_name: str | None = (
            CUSTOM_NODES_PUBLISHER_APP_NAME if native_golden else None
        )
        env = env_builder.build(config, host_env=os.environ,
                                backend_extra={**spec.deploy_only_env,
                                               **_identity_env_for_command("deploy", config),
                                               **_canonical_metadata_env(config, fingerprints, invocation_id)})
        if native_golden:
            env = _native_golden_deploy_env(env)
        if native_golden and not args.dry_run:
            # The active workspace, not the user's ambient Modal profile, owns
            # this deploy.  Values are redacted by the normal dry-run report.
            env.update(_active_workspace_credentials(repo_root))
        # Historical deploy branches receive their selector as the first BAT
        # argument. Native Golden deploy has one explicit Modal app argument
        # and must not be routed through a harness selector.
        selector = _backend_selector(config)
        extra_args = (
            ["--name", config.target.app]
            if native_golden else ([selector] if selector else [])
        )
        command = backend_mod.BackendRunner.build_command_line(
            spec, extra_args)
        if args.dry_run:
            _dry_run_report(config, fingerprints, env, command)
            return 0
        # Deploy-only: warn (not fail) on runtime overrides; spend happens at run time.
        inventory = ro_mod.RuntimeOverrideInventory(local_dir=repo_root / ".runtime_state")
        present = inventory.list_local()
        if present and config.runtime_override_policy == "forbid":
            print(f"[v2ctl.deploy] WARNING: {len(present)} runtime flag file(s) present; "
                  "they will be enforced at gate/run time", file=sys.stderr)
        lock = locking_mod.DeployLock(repo_root / ".v2ctl" / "deploy.lock")
        lock.acquire(owner=config.owner or args.owner or "v2ctl",
                     target=config.target.app, profile=config.profile_name)
        try:
            deploy_identity = capture_deploy_identity(fingerprints)
            _apply_deploy_identity_to_env(env, deploy_identity)
            print(f"[v2ctl.deploy] profile={config.profile_name} "
                  f"deploy_fingerprint={deploy_identity.deploy_fingerprint}")
            print(f"[v2ctl.deploy] command={command}")
            publication = None
            source_probe_expected = None
            if native_golden:
                assert publisher_app_name is not None
                from . import source_probe as source_probe_mod

                # Capture the exact source expectation alongside the frozen
                # deploy identity, before publication or backend work starts.
                source_probe_expected = source_probe_mod.compute_expected_local(repo_root)
                # This is deliberately inside the deploy lock and before both
                # version capture and native Modal deployment.  A publication
                # failure exits through the lock's finally block and prevents
                # the backend from running.
                publication = _invoke_golden_publisher(repo_root, publisher_app_name)
            # ── Deploy-version-advance verification (E29 root-cause fix) ──
            # Capture the app's highest deployment version BEFORE the deploy
            # so a post-deploy comparison can prove a NEW version appeared
            # (a "version deployed recently" check falsely passes when a
            # deploy right after a prior one no-ops).
            # Every deploy, including public Golden deploys, must prove that
            # the target app received a new deployment version.  A successful
            # backend exit alone can also represent a no-op deploy.
            verify_version = True
            _pre_version = _app_version_number(config.target.app)
            if _pre_version is None:
                print(
                    "ERROR: unable to establish the app's pre-deploy version; "
                    "refusing to invoke the backend",
                    file=sys.stderr,
                )
                return 1
            result = backend_mod.BackendRunner(repo_root, env_builder).run(
                spec, config=config, extra_args=extra_args, extra_env=env, capture=True,
                invocation_id=invocation_id)
            # ── Crash-loop guard: a container that repeats the same traceback
            # must NEVER produce a "successful" deployment manifest.  Diagnose
            # the root cause locally and redeploy; never auto-retry. ──
            crash = backend_mod.detect_crash_loop(result.stdout or "")
            if crash is not None:
                raise DeployCrashLoopError(
                    f"deployed container is crash-looping: exception "
                    f"{crash['exception_type']!r} repeated {crash['count']}x "
                    f"in the deploy output. STOP: fix the root cause locally "
                    f"and redeploy; the deployment is NOT valid.",
                    exception_type=crash["exception_type"],
                    count=int(crash["count"]),
                )
            manifest = write_deployment_manifest(
                repo_root, config, fingerprints, env, result,
                publication=publication,
                deploy_identity=deploy_identity,
            )
            print(f"[v2ctl.deploy] exit={result.exit_code} manifest={manifest}")
            if not result.ok():
                _print_backend_diagnostic(result, env)
                # A failed deploy must NEVER leave a "deployed" manifest behind:
                # remove it so gate/run cannot treat a broken deployment as valid.
                try:
                    manifest.unlink(missing_ok=True)
                except OSError:
                    pass
                return result.exit_code if result.exit_code else 1
            # ── Deploy-version-advance verification (E29 root-cause fix) ────
            # A Modal client can exit 0 while the app was NOT actually updated
            # (Windows charmap crash, cached no-op).  Verify the app's
            # deployment version ADVANCED during this deploy; if it did not,
            # the deploy must be treated as a failure — never exit 0 on a
            # deploy that left the app unchanged.
            _post_version = _app_version_number(config.target.app)
            if _post_version is None:
                try:
                    manifest.unlink(missing_ok=True)
                except OSError:
                    pass
                print(
                    "ERROR: unable to establish the app's post-deploy version; "
                    "refusing to treat this deploy as valid.",
                    file=sys.stderr,
                )
                return 1
            if verify_version and _post_version <= _pre_version:
                try:
                    manifest.unlink(missing_ok=True)
                except OSError:
                    pass
                print(
                    "ERROR: deploy reported success but the app's deployment "
                    "version did NOT advance — the deployed code was NOT "
                    "updated. Refusing to treat this deploy as valid.",
                    file=sys.stderr,
                )
                return 1
            if native_golden:
                receipt = _write_golden_deployment_receipt(
                    repo_root, config, env, deploy_identity, _post_version,
                    manifest, publication,
                    source_probe_expected,
                )
                print(f"[v2ctl.deploy] deployment_receipt={receipt}")
            return 0
        finally:
            lock.release()
    except (V2CtlError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_deploy_run(args, repo_root: Path) -> int:
    identity_error = _reject_golden_identity_args(args)
    if identity_error is not None:
        return identity_error
    flat_golden_error = _reject_flat_golden_deploy_run(args)
    if flat_golden_error is not None:
        return flat_golden_error
    try:
        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = _build_components_for_args(
            repo_root, args
        )
        _reject_protected_effective_target(config, command="v2ctl deploy-run")
        _reject_golden_mode_override(config, command="v2ctl deploy-run")
        invocation_id = _new_invocation_id()
        spec = backend_registry.canonical()
        env = env_builder.build(config, host_env=os.environ,
                                backend_extra={**_identity_env_for_command("deploy-run", config),
                                               **_canonical_metadata_env(config, fingerprints, invocation_id)})
        # Forward the canonical selector as the BAT's first positional arg
        # (see cmd_deploy).
        selector = _backend_selector(config)
        extra_args = [selector] if selector else []
        command = backend_mod.BackendRunner.build_command_line(
            spec, extra_args)
        if args.dry_run:
            _dry_run_report(config, fingerprints, env, command)
            return 0
        enforce_runtime_overrides(config,
                                  ro_mod.RuntimeOverrideInventory(local_dir=repo_root / ".runtime_state"),
                                  spend=True)
        lock = locking_mod.DeployLock(repo_root / ".v2ctl" / "deploy.lock")
        lock.acquire(owner=config.owner or args.owner or "v2ctl",
                     target=config.target.app, profile=config.profile_name)
        try:
            deploy_identity = capture_deploy_identity(fingerprints)
            _apply_deploy_identity_to_env(env, deploy_identity)
            print(f"[v2ctl.deploy-run] profile={config.profile_name} "
                  f"deploy_fingerprint={deploy_identity.deploy_fingerprint}")
            print(f"[v2ctl.deploy-run] command={command}")
            result = backend_mod.BackendRunner(repo_root, env_builder).run(
                spec, config=config, extra_args=extra_args, extra_env=env, capture=True,
                invocation_id=invocation_id, strict_canonical_discovery=True)
            manifest = write_deployment_manifest(
                repo_root, config, fingerprints, env, result,
                deploy_identity=deploy_identity,
            )
            print(f"[v2ctl.deploy-run] exit={result.exit_code} manifest={manifest}")
            if not result.ok():
                # ── E40: crash-loop accounting ────────────────────────────
                _cl = getattr(result, "crash_loop", None)
                if _cl:
                    print(
                        f"ERROR: CRASH_LOOP detected: exception={_cl.get('exception_type')!r} "
                        f"count={_cl.get('count')}. The remote container is "
                        f"failing deterministically at startup; fix the reported "
                        f"error before redeploying (v2ctl will not auto-retry).",
                        file=sys.stderr,
                    )
                try:
                    manifest.unlink(missing_ok=True)
                except OSError:
                    pass
                return result.exit_code if result.exit_code else 1
            return 0
        finally:
            lock.release()
    except (V2CtlError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_run(args, repo_root: Path) -> int:
    identity_error = _reject_golden_identity_args(args)
    if identity_error is not None:
        return identity_error
    try:
        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = _build_components_for_args(
            repo_root, args
        )
        _reject_protected_effective_target(config, command="v2ctl run")
        _reject_golden_mode_override(config, command="v2ctl run")
        bound_receipt = None
        if config.profile_name == GOLDEN_P1_PROFILE and not getattr(args, "dry_run", False):
            _, bound_receipt = _bound_deployment_receipt(repo_root, config, command="run")
        # Run-only: refuse unregistered and deploy-required explicit changes.
        resolver.check_run_safety(
            config, run_only=True,
            trusted_environment=(bound_receipt.effective_environment if bound_receipt else None),
        )
        _require_no_deploy_in_flight(repo_root)
        requested_target = {
            "app": config.target.app,
            "class": config.target.class_name,
            "method": config.target.method,
        }
        manifest = latest_deployment_manifest(
            repo_root, profile=config.profile_name, target=requested_target
        )
        golden_dry_run = bool(
            getattr(args, "golden_public", False) and getattr(args, "dry_run", False)
        )
        if not golden_dry_run:
            if manifest is None and bound_receipt is None:
                raise GateError("no deployment manifest; run `v2ctl deploy-run` (or `deploy`) first")
            if manifest is not None and _deployment_manifest_target(manifest) != _requested_target_identity(
                requested_target
            ):
                raise GateError(
                    "deployment target mismatch; no matching deployment targets "
                    f"app={config.target.app} class={config.target.class_name} "
                    f"method={config.target.method}"
                )
            stored = manifest.get("deploy_fingerprint") if manifest is not None else None
            current = bound_receipt.deploy_fingerprint if bound_receipt else fingerprints.deploy_fingerprint()
            if bound_receipt is None and manifest is not None and stored != current:
                changes = diff_deploy_inputs(manifest.get("deploy_inputs", {}),
                                             fingerprints.deploy_inputs())
                raise GateError(
                    "deployment fingerprint mismatch; deploy-required state changed since last "
                    f"deploy. stored={stored} current={current}. Changed: "
                    + ("; ".join(changes) if changes else "(unknown)"),
                )
        current = bound_receipt.deploy_fingerprint if bound_receipt else fingerprints.deploy_fingerprint()
        enforce_runtime_overrides(config,
                                  ro_mod.RuntimeOverrideInventory(local_dir=repo_root / ".runtime_state"),
                                  spend=True)
        # ── Full-run guard: run must generate (run_plan_stream), never the
        # snapshot-restore-only PROBE. ──
        _require_full_run_mode(config, command="v2ctl run")
        if bound_receipt is not None:
            receipt_mod.require_source_probe_evidence(repo_root, bound_receipt)
        run_count = args.run_count or config.workload.run_count
        selector = _backend_selector(config)
        if selector:
            if run_count != 1:
                raise GateError(
                    f"{selector} requires exactly one cold run; got run_count={run_count}"
                )
            extra_args, selector_env = _validation_backend_args(config)
        else:
            extra_args = ["--run-count", str(run_count)]
            selector_env = {}
        invocation_id = _new_invocation_id()
        spec = backend_registry.run_only()
        env = env_builder.build(config, host_env=os.environ,
                                backend_extra={"V2_BENCHMARK_RUNS": str(run_count),
                                               **_identity_env_for_command("run", config),
                                               **selector_env,
                                               **_canonical_metadata_env(config, fingerprints, invocation_id)})
        if bound_receipt is not None:
            env = _receipt_effective_env(env, bound_receipt)
            env["COMFYMODAL_V2CTL_RUN_FINGERPRINT"] = val_mod._bound_run_fingerprint(
                fingerprints, bound_receipt
            )
        # Forward the canonical selector as the BAT's first positional arg so
        # the run BAT enters its validation mode (e.g. E28_VALIDATION) instead
        # of falling into the snapshot_restore_only probe branch.
        command = backend_mod.BackendRunner.build_command_line(spec, extra_args)
        if args.dry_run:
            _dry_run_report(config, fingerprints, env, command)
            return 0
        print(f"[v2ctl.run] profile={config.profile_name} "
              f"deploy_fingerprint={current} run_fingerprint="
              f"{val_mod._bound_run_fingerprint(fingerprints, bound_receipt)}")
        print(f"[v2ctl.run] command={command}")
        result = backend_mod.BackendRunner(repo_root, env_builder).run(
            spec, config=config, extra_args=extra_args, extra_env=env, capture=True,
            invocation_id=invocation_id, strict_canonical_discovery=True,
            allow_multiple_run_artifacts=run_count > 1,
            canonical_identity=(
                {
                    "profile": bound_receipt.profile,
                    "profile_config_fingerprint": (
                        bound_receipt.profile_config_fingerprint
                        or fingerprints.profile_config_fingerprint()
                    ),
                    "deploy_fingerprint": current,
                    "run_fingerprint": val_mod._bound_run_fingerprint(
                        fingerprints, bound_receipt
                    ),
                }
                if bound_receipt is not None else None
            ))
        provenance = prov_mod.build_provenance(
            config, env, current,
            val_mod._bound_run_fingerprint(fingerprints, bound_receipt), [],
            invocation_id=invocation_id,
            profile_config_fingerprint=(
                bound_receipt.profile_config_fingerprint
                if bound_receipt is not None and bound_receipt.profile_config_fingerprint
                else fingerprints.profile_config_fingerprint()
            ),
            request_id=result.request_id or "",
        )
        run_manifest = write_run_manifest(
            repo_root, config, fingerprints, env, result, provenance,
            deployment_receipt=bound_receipt,
        )
        if result.artifacts.run_artifact is not None:
            try:
                prov_mod.write_provenance_sibling(result.artifacts.run_artifact, provenance)
            except OSError:
                pass
        print(f"[v2ctl.run] exit={result.exit_code} manifest={run_manifest}")
        if not result.ok():
            return result.exit_code if result.exit_code else 1
        val_mod.mark_runtime_health_verified(
            repo_root,
            config,
            fingerprints,
            current,
            bound_receipt=bound_receipt,
        )
        return 0
    except (V2CtlError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_gate(args, repo_root: Path) -> int:
    identity_error = _reject_golden_identity_args(args)
    if identity_error is not None:
        return identity_error
    try:
        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = _build_components_for_args(
            repo_root, args
        )
        _reject_protected_effective_target(config, command="v2ctl gate")
        _reject_golden_mode_override(config, command="v2ctl gate")
        bound_receipt = None
        if config.profile_name == GOLDEN_P1_PROFILE and not getattr(args, "dry_run", False):
            _, bound_receipt = _bound_deployment_receipt(repo_root, config, command="gate")
        resolver.check_run_safety(
            config, run_only=True,
            trusted_environment=(bound_receipt.effective_environment if bound_receipt else None),
        )
        _require_no_deploy_in_flight(repo_root)
        requested_target = {
            "app": config.target.app,
            "class": config.target.class_name,
            "method": config.target.method,
        }
        manifest = latest_deployment_manifest(
            repo_root, profile=config.profile_name, target=requested_target
        )
        if manifest is None and bound_receipt is None:
            raise GateError("gate requires a deployment whose fingerprint matches the requested "
                            "configuration; run `v2ctl deploy-run` first")
        if bound_receipt is None and manifest is not None and manifest.get("deploy_fingerprint") != fingerprints.deploy_fingerprint():
            raise GateError("gate requires a deployment whose fingerprint matches the requested "
                            "configuration; run `v2ctl deploy-run` first")
        if manifest is not None and _deployment_manifest_target(manifest) != _requested_target_identity(
            requested_target
        ):
            raise GateError(
                "deployment target mismatch; no matching deployment targets "
                f"app={config.target.app} class={config.target.class_name} "
                f"method={config.target.method}"
            )
        enforce_runtime_overrides(config,
                                  ro_mod.RuntimeOverrideInventory(local_dir=repo_root / ".runtime_state"),
                                  spend=True)
        # ── Full-run guard: a gate must generate (run_plan_stream), never
        # the snapshot-restore-only PROBE. ──
        _require_full_run_mode(config, command="v2ctl gate")
        invocation_id = _new_invocation_id()
        spec = backend_registry.run_only()
        if args.dry_run:
            extra_args, selector_env = _validation_backend_args(config)
            env = env_builder.build(
                config, host_env=os.environ,
                backend_extra={"V2_BENCHMARK_RUNS": "1", **selector_env,
                               **_canonical_metadata_env(config, fingerprints, invocation_id)},
            )
            command = backend_mod.BackendRunner.build_command_line(spec, extra_args)
            _dry_run_report(config, fingerprints, env, command)
            return 0
        validator = val_mod.Validator()
        validator.register(val_mod.StructuralValidator())
        validator.register(val_mod.ExpectedOutputShaValidator())
        if config.profile_name == GOLDEN_P1_PROFILE:
            validator.register(val_mod.GoldenCohortValidator())
        # Golden has its own dedicated durability/seriality ledger contract;
        # the generic E29 run-plan ledger is not emitted by
        # run_golden_serial_stream.
        if config.profile_name != GOLDEN_P1_PROFILE:
            validator.register(val_mod.CanonicalLedgerValidator())
        e31_validator = val_mod.E31ForensicsValidator()
        if e31_validator.applies(config):
            validator.register(e31_validator)
        e37_validator = val_mod.E37StrictProofValidator()
        if e37_validator.applies(config):
            validator.register(e37_validator)
        clean_lane_validator = val_mod.E37CleanLaneProofValidator()
        if clean_lane_validator.applies(config):
            validator.register(clean_lane_validator)
        runner = backend_mod.BackendRunner(repo_root, env_builder)
        gate = val_mod.GateRunner(repo_root=repo_root, fingerprints=fingerprints,
                                   validators=validator, backend_runner=runner,
                                   env_builder=env_builder,
                                   deployment_receipt=bound_receipt)
        result = gate.run_gate(config, spec, invocation_id=invocation_id)
        print(f"[v2ctl.gate] valid={int(result.valid)} manifest={result.manifest_path}")
        for reason in result.reasons:
            print(f"  FAIL {reason}")
        if result.run is not None and result.run.artifacts.run_artifact is not None:
            provenance_env = env_builder.build(
                config, host_env=os.environ,
                backend_extra={"V2_BENCHMARK_RUNS": "1",
                               **_canonical_metadata_env(config, fingerprints, invocation_id)},
            )
            if bound_receipt is not None:
                provenance_env = _receipt_effective_env(provenance_env, bound_receipt)
            provenance = prov_mod.build_provenance(
                config, provenance_env,
                bound_receipt.deploy_fingerprint if bound_receipt is not None else fingerprints.deploy_fingerprint(),
                val_mod._bound_run_fingerprint(fingerprints, bound_receipt), [],
                invocation_id=invocation_id,
                profile_config_fingerprint=(
                    bound_receipt.profile_config_fingerprint
                    if bound_receipt is not None and bound_receipt.profile_config_fingerprint
                    else fingerprints.profile_config_fingerprint()
                ),
                request_id=result.run.request_id if result.run is not None else "",
            )
            try:
                prov_mod.write_provenance_sibling(result.run.artifacts.run_artifact, provenance)
            except OSError:
                pass
        return 0 if result.valid else 1
    except (V2CtlError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_confirm(args, repo_root: Path) -> int:
    identity_error = _reject_golden_identity_args(args)
    if identity_error is not None:
        return identity_error
    try:
        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = _build_components_for_args(
            repo_root, args
        )
        _reject_protected_effective_target(config, command="v2ctl confirm")
        _reject_golden_mode_override(config, command="v2ctl confirm")
        bound_receipt = None
        if config.profile_name == GOLDEN_P1_PROFILE and not getattr(args, "dry_run", False):
            _, bound_receipt = _bound_deployment_receipt(repo_root, config, command="confirm")
        resolver.check_run_safety(
            config, run_only=True,
            trusted_environment=(bound_receipt.effective_environment if bound_receipt else None),
        )
        _require_no_deploy_in_flight(repo_root)
        _require_full_run_mode(config, command="v2ctl confirm")
        enforce_runtime_overrides(config,
                                  ro_mod.RuntimeOverrideInventory(local_dir=repo_root / ".runtime_state"),
                                  spend=True)
        invocation_id = _new_invocation_id()
        spec = backend_registry.run_only()
        runs = args.runs or 1
        if args.dry_run:
            extra_args, selector_env = _validation_backend_args(config)
            env = env_builder.build(config, host_env=os.environ,
                                    backend_extra={"V2_BENCHMARK_RUNS": "1", **selector_env,
                                                   **_canonical_metadata_env(config, fingerprints, invocation_id)})
            command = backend_mod.BackendRunner.build_command_line(spec, extra_args)
            _dry_run_report(config, fingerprints, env, command)
            return 0
        runner = backend_mod.BackendRunner(repo_root, env_builder)
        validator = val_mod.Validator()
        validator.register(val_mod.StructuralValidator())
        validator.register(val_mod.ExpectedOutputShaValidator())
        if config.profile_name == GOLDEN_P1_PROFILE:
            validator.register(val_mod.GoldenCohortValidator())
        # Confirm must enforce the same canonical ledger contract as gate;
        # otherwise an E37 gate could pass while confirmation silently drops
        # the first-durable ledger validator.
        # Golden has its own dedicated durability/seriality ledger contract;
        # the generic E29 run-plan ledger is not emitted by
        # run_golden_serial_stream.
        if config.profile_name != GOLDEN_P1_PROFILE:
            validator.register(val_mod.CanonicalLedgerValidator())
        e31_validator = val_mod.E31ForensicsValidator()
        if e31_validator.applies(config):
            validator.register(e31_validator)
        e37_validator = val_mod.E37StrictProofValidator()
        if e37_validator.applies(config):
            validator.register(e37_validator)
        clean_lane_validator = val_mod.E37CleanLaneProofValidator()
        if clean_lane_validator.applies(config):
            validator.register(clean_lane_validator)
        confirm = val_mod.ConfirmRunner(repo_root=repo_root, fingerprints=fingerprints,
                                         backend_runner=runner, env_builder=env_builder,
                                         validators=validator,
                                         deployment_receipt=bound_receipt)
        result = confirm.confirm(Path(args.from_gate), config, spec, runs=runs,
                                 invocation_id=invocation_id)
        print(f"[v2ctl.confirm] valid={int(result.valid)} manifest={result.manifest_path}")
        for reason in result.reasons:
            print(f"  FAIL {reason}")
        return 0 if result.valid else 1
    except (V2CtlError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_source_probe(args, repo_root: Path) -> int:
    """v2ctl source-probe: prove the deployed bytes equal the local source.

    Invokes ONLY the no-generation ``source_identity_probe`` on the deployed
    GPU class (the same class/transport ``run_plan_stream`` uses) and
    classifies each required module MATCH / MISMATCH / MISSING /
    UNEXPECTED_PATH.  Exits nonzero on anything but a full MATCH.  Never
    runs a generation.
    """
    identity_error = _reject_golden_identity_args(args)
    if identity_error is not None:
        return identity_error
    try:
        from . import source_probe as sp

        # Reuse the profile's target identity (app/class/gpu) so the probe
        # addresses the SAME deployment the gate would.
        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = (
            _build_components_for_args(repo_root, args)
        )
        _reject_protected_effective_target(config, command="v2ctl source-probe")
        _reject_golden_mode_override(config, command="v2ctl source-probe")
        app_name = config.target.app
        class_name = config.target.class_name
        gpu = config.resources.gpu
        bound_receipt = None
        if config.profile_name == GOLDEN_P1_PROFILE:
            _, bound_receipt = _bound_deployment_receipt(
                repo_root, config, command="source-probe"
            )
        deploy_fp = bound_receipt.deploy_fingerprint if bound_receipt else fingerprints.deploy_fingerprint()
        expected_source = (
            bound_receipt.source_probe.get("expected") if bound_receipt is not None else None
        )
        if bound_receipt is not None and not isinstance(expected_source, dict):
            raise GateError("deployment receipt has no source-probe expectation")
        workspace = sp._load_workspace(repo_root)
        import os as _os
        if app_name:
            _os.environ["COMFYMODAL_V2_APP_NAME"] = app_name
        if class_name:
            _os.environ["COMFYMODAL_V2_CLASS_NAME"] = class_name
        if gpu:
            _os.environ["COMFYMODAL_V2_GPU"] = str(gpu)

        exit_code, report = sp.run_source_probe(
            repo_root, workspace=workspace, gpu=str(gpu), expected=expected_source
        )
        if bound_receipt is not None:
            receipt_mod.write_source_probe_evidence(repo_root, bound_receipt, report)
        print(f"[v2ctl.source-probe] profile={args.profile}")
        print(f"[v2ctl.source-probe] git_head={report['expected'].get('git_head', '')[:12]}")
        print(f"[v2ctl.source-probe] target app={app_name or '(profile unresolved)'} "
              f"class={class_name or '(profile unresolved)'} gpu={gpu or 'rtx-pro-6000'}")
        summary = report["remote_summary"]
        expected_remote_hash = str(
            (bound_receipt.deployment_identity.get("deployment_combined_hash", "")
             if bound_receipt is not None else "")
        )
        if expected_remote_hash and summary.get("deployment_combined_hash") != expected_remote_hash:
            raise GateError(
                "source-probe deployment identity mismatch against immutable receipt"
            )
        print(f"[v2ctl.source-probe] remote class={summary['class_name']} "
              f"image={summary['image_id']} container={summary['container_session_id']}")
        print(f"[v2ctl.source-probe] remote deployment_combined_hash="
              f"{summary['deployment_combined_hash'][:16] or '(empty)'}")
        print(f"[v2ctl.source-probe] remote cwd={summary['cwd']}")
        print(f"[v2ctl.source-probe] remote comfymodal_runtime __file__="
              f"{summary['comfymodal_runtime_file']}")
        for p in summary["comfymodal_runtime_path"]:
            print(f"[v2ctl.source-probe]   __path__: {p}")
        for c in report["classification"]["modules"]:
            print(f"[v2ctl.source-probe]   {c['module']}: {c['verdict']} "
                  f"remote_sha={c.get('remote_sha', '')[:16] or '(none)'} "
                  f"expected_sha={c.get('expected_sha', '')[:16] or '(none)'}"
                  + (f" path={c.get('remote_path')}" if c.get("remote_path") else ""))
        led = report["classification"]
        print(f"[v2ctl.source-probe] ledger flag={led['ledger_flag']} "
              f"enabled={led['ledger_enabled']} record_event={led['ledger_record_event']}")
        print(f"[v2ctl.source-probe] verdict={led['verdict']}")
        if led["verdict"] != "MATCH":
            print(f"[v2ctl.source-probe] RESULT=FAIL source_identity != expected local source",
                  file=sys.stderr)
        else:
            print(f"[v2ctl.source-probe] RESULT=PASS source_identity=MATCH")
            # A receipt seals the deployment manifest.  Bound source-probe
            # evidence is persisted separately, so do not amend that ledger.
            if bound_receipt is None:
                # Flip the deployment manifest's source_identity_status to
                # verified when it exists (truthful health semantics).
                try:
                    import json as _json
                    mdir = _deployment_manifest_dir(repo_root)
                    files = sorted(mdir.glob("deploy_*.json")) if mdir.is_dir() else []
                    for manifest_path in reversed(files):
                        try:
                            manifest = _json.loads(
                                manifest_path.read_text(encoding="utf-8")
                            )
                        except (OSError, _json.JSONDecodeError):
                            # An unrelated/corrupt record must not hide a valid
                            # current deployment record farther down the ledger.
                            continue
                        if not isinstance(manifest, dict):
                            continue
                        if manifest.get("deploy_fingerprint") == deploy_fp:
                            manifest["source_identity_status"] = "verified"
                            manifest_path.write_text(
                                json.dumps(manifest, indent=2, sort_keys=True),
                                encoding="utf-8",
                            )
                            print(f"[v2ctl.source-probe] manifest source_identity_status=verified")
                            break
                except Exception as _exc_manifest:
                    print(f"[v2ctl.source-probe] (manifest status update skipped: {_exc_manifest})")
        return exit_code
    except (V2CtlError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_runtime_flags(args, repo_root: Path) -> int:
    inventory = ro_mod.RuntimeOverrideInventory(local_dir=repo_root / ".runtime_state")
    sub = args.runtime_command
    if sub == "list":
        local = inventory.list_local()
        print(f"runtime_override_policy={ro_mod.DEFAULT_RUNTIME_OVERRIDE_POLICY}")
        print(f"local_override_count={len(local)}")
        for o in local:
            print(f"{o.name}={o.value} source={o.source}")
        print("remote listing: not available in this phase (helper deferred; no remote calls made)")
        return 0
    if sub == "clear":
        name = args.name
        try:
            removed = inventory.clear_local(name)
        except ro_mod.RuntimeOverrideViolation as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if removed:
            print(f"cleared {name}")
            return 0
        print(f"not present locally: {name}")
        return 1
    if sub == "clear-all":
        try:
            removed = inventory.clear_local_all(args.confirm)
        except ro_mod.RuntimeOverrideViolation as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"cleared {len(removed)}: {', '.join(removed) if removed else '(none)'}")
        return 0
    return 2


def cmd_lock(args, repo_root: Path) -> int:
    lock = locking_mod.DeployLock(repo_root / ".v2ctl" / "deploy.lock")
    sub = args.lock_command
    if sub == "status":
        status = lock.status()
        if status is None:
            print("deploy.lock=none")
            return 0
        stale = lock.is_stale(status)
        print(f"owner={status.get('owner')}")
        print(f"pid={status.get('pid')}")
        print(f"host={status.get('host')}")
        print(f"target={status.get('target')}")
        print(f"profile={status.get('profile')}")
        print(f"timestamp={status.get('timestamp')}")
        print(f"stale={int(stale)}")
        if stale:
            print("stale lock: release with `v2ctl lock force-release` after confirming ownership")
        return 0
    if sub == "acquire":
        try:
            lock.acquire(owner=args.owner or "v2ctl", target=args.target or "unknown",
                         profile=args.profile, force=args.force)
        except (LockHeldError, LockStaleError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"acquired: {lock.status()}")
        return 0
    if sub == "release":
        try:
            lock.release()
        except LockHeldError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print("released")
        return 0
    if sub == "force-release":
        lock.force_release(args.owner or "v2ctl")
        print("force-released")
        return 0
    return 2


def _cli_target_options(args) -> dict[str, str]:
    opts: dict[str, str] = {}
    if getattr(args, "app", None):
        # Modal app names are case-insensitive at the CLI boundary, but the
        # resolved identity and fingerprints must be stable everywhere.
        opts["target.app"] = str(args.app).strip().lower()
    if getattr(args, "gpu", None):
        opts["resources.gpu"] = args.gpu
    if getattr(args, "memory_mb", None):
        opts["resources.memory_mb"] = str(args.memory_mb)
    if getattr(args, "cpu", None):
        opts["resources.cpu"] = str(args.cpu)
    if getattr(args, "owner", None):
        opts["owner"] = args.owner
    return opts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="v2ctl",
        description="ComfyUI Modal V2 canonical deploy/run control plane (local-only).",
    )
    parser.add_argument("--profile", default="production", help="profile name (config/v2/profiles)")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                        help="explicit flag override (highest precedence; repeatable)")
    parser.add_argument("--inherit", action="append", default=[], metavar="NAME",
                        help="explicitly inherit one ambient env var (repeatable)")
    parser.add_argument("--owner", default=None, help="deploy owner label for the lock")
    parser.add_argument("--dry-run", action="store_true", help="resolve and print, invoke nothing")
    parser.add_argument("--json", action="store_true", help="machine-readable output where supported")
    parser.add_argument("--app", default=None, help="override target app (protected from --set)")
    parser.add_argument("--gpu", default=None, help="override resource GPU")
    parser.add_argument("--memory-mb", type=int, default=None, help="override resource memory")
    parser.add_argument("--cpu", type=int, default=None, help="override resource CPU")
    parser.add_argument("--run-count", type=int, default=None, help="override run count")
    parser.add_argument(
        "--allow-production", action="store_true",
        help="deprecated; always refused for Golden R0",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("version")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("doctor")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("config")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("flags")
    fsub = p.add_subparsers(dest="flags_command", required=True)
    fsub.add_parser("list").set_defaults(func=cmd_flags)
    pe = fsub.add_parser("explain")
    pe.add_argument("name")
    pe.set_defaults(func=cmd_flags)
    pv = fsub.add_parser("validate")
    pv.add_argument("name_value", metavar="NAME=VALUE")
    pv.set_defaults(func=cmd_flags)
    fsub.add_parser("audit").set_defaults(func=cmd_flags)

    p = sub.add_parser("deploy")
    p.set_defaults(func=cmd_deploy)

    p = sub.add_parser("deploy-run")
    p.set_defaults(func=cmd_deploy_run)

    p = sub.add_parser("run")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("gate")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("confirm")
    p.add_argument("--from", dest="from_gate", required=True, metavar="GATE_MANIFEST")
    p.add_argument("--runs", type=int, default=1)
    p.set_defaults(func=cmd_confirm)

    p = sub.add_parser("golden", help="public Golden operations")
    gsub = p.add_subparsers(dest="golden_command", required=True)
    gsub.add_parser("status", help="show local Golden readiness without backend calls").set_defaults(
        func=cmd_golden
    )
    for name in ("doctor", "deploy", "run", "publisher-bootstrap"):
        child = gsub.add_parser(name)
        if name in {"deploy", "run", "publisher-bootstrap"}:
            # Visible on ``golden <command> --help`` while the existing
            # pre-parser continues to support root-option hoisting.
            # SUPPRESS is important: _hoist_global_options may already have
            # populated the root option before argparse reaches this child.
            child.add_argument("--app", default=argparse.SUPPRESS, help="experimental Modal app name")
            child.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                               help="resolve and print, invoke nothing")
        child.set_defaults(func=cmd_golden)

    p = sub.add_parser("source-probe")
    p.set_defaults(func=cmd_source_probe)

    p = sub.add_parser("runtime-flags")
    rsub = p.add_subparsers(dest="runtime_command", required=True)
    rsub.add_parser("list").set_defaults(func=cmd_runtime_flags)
    rc = rsub.add_parser("clear")
    rc.add_argument("name")
    rc.set_defaults(func=cmd_runtime_flags)
    ra = rsub.add_parser("clear-all")
    ra.add_argument("--confirm", action="store_true", required=True)
    ra.set_defaults(func=cmd_runtime_flags)

    p = sub.add_parser("lock")
    lsub = p.add_subparsers(dest="lock_command", required=True)
    lsub.add_parser("status").set_defaults(func=cmd_lock)
    la = lsub.add_parser("acquire")
    la.add_argument("--force", action="store_true")
    la.add_argument("--target", default=None)
    la.set_defaults(func=cmd_lock)
    lsub.add_parser("release").set_defaults(func=cmd_lock)
    lf = lsub.add_parser("force-release")
    lf.set_defaults(func=cmd_lock)

    return parser


_GLOBAL_HOIST_WITH_VALUE = (
    "--profile",
    "--owner",
    "--app",
    "--gpu",
    "--memory-mb",
    "--cpu",
    "--run-count",
)


def _hoist_global_options(argv: list[str]) -> list[str]:
    """Move repeatable/global options before the subcommand.

    argparse rejects global options after a subcommand; agents naturally
    write ``v2ctl run --set X=1 --dry-run``.  This pre-pass hoists the
    repeatable and boolean global flags (and their values) to the front so
    both orderings work.
    """
    front: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--set", "--inherit") or arg in _GLOBAL_HOIST_WITH_VALUE:
            if i + 1 < len(argv):
                front.extend([arg, argv[i + 1]])
                i += 2
                continue
            rest.append(arg)
            i += 1
            continue
        if arg in ("--dry-run", "--json", "--allow-production"):
            front.append(arg)
            i += 1
            continue
        rest.append(arg)
        i += 1
    return front + rest


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(_hoist_global_options(argv))
    repo_root = Path(__file__).resolve().parents[2]
    try:
        # Apply the flat-command Golden identity guard before dispatch so even
        # commands that do not reach a backend cannot accept the protected app.
        if args.command != "golden":
            identity_error = _reject_golden_identity_args(args)
            if identity_error is not None:
                return identity_error
        return args.func(args, repo_root)
    except V2CtlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
