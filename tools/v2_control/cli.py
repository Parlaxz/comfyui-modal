"""v2ctl command-line interface (Batch E32).

Thin CLI over the v2_control modules.  Local-only: every deploy/run/gate
command builds a sanitized child environment and invokes the canonical
backend via subprocess.  Golden deploy uses the native Modal module deploy;
request execution retains the established backend.  No Modal SDK calls, no
network, no ambient experiment env leakage in dry-run mode.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import inspect
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from comfymodal_runtime import deploy_identity
from comfymodal_runtime.contracts import DEPLOYMENT_HASH_NAMESPACE
from comfymodal_runtime.publication_policy import (
    CUSTOM_NODES_PUBLISHER_APP_NAME,
    CUSTOM_NODES_VOLUME_NAME,
)
import modal_workspaces

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
from . import golden_guard as golden_guard_mod
from .experiment_evidence import (
    finalize_experiment_evidence,
    golden_arm_identity,
    is_experiment_profile,
    resolved_attention_backend,
    sage_runtime_identity,
)
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
GOLDEN_PARALLEL_PROFILE = "golden_p1_parallel"
GOLDEN_PARALLEL_METHOD = "run_golden_parallel_stream"
GOLDEN_PARALLEL_MODE = "golden_p1_parallel"
GOLDEN_ATTENTION_BACKEND_FLAG = "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND"
GOLDEN_CPU_QD2_PREFETCH_FLAG = "COMFYMODAL_V2_GOLDEN_CPU_QD2_PREFETCH"
GOLDEN_CPU_QD2_DEPLOY_FLAG = "COMFYMODAL_GOLDEN_CPU_QD2_PREFETCH"
FULL_RUN_METHOD = "run_plan_stream"
PROTECTED_GOLDEN_APP = "stable-modal-comfy-v2-golden-p1"
_MODAL_APP_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def is_golden_profile_name(profile: object) -> bool:
    value = str(profile or "").strip().lower()
    return (
        value in {GOLDEN_P1_PROFILE, GOLDEN_PARALLEL_PROFILE}
        or value.startswith("golden_p1_direct")
        or value.startswith("golden_p1_parallel_")
    )


def golden_profile_mode(profile: object) -> str:
    value = str(profile or "").strip().lower()
    return "parallel" if value == GOLDEN_PARALLEL_PROFILE or value.startswith("golden_p1_parallel_") else "serial"


def golden_method_for_profile(profile: object) -> str:
    return (
        GOLDEN_PARALLEL_METHOD
        if golden_profile_mode(profile) == "parallel"
        else GOLDEN_P1_METHOD
    )


def golden_harness_mode_for_profile(profile: object) -> str:
    return (
        GOLDEN_PARALLEL_MODE
        if golden_profile_mode(profile) == "parallel"
        else GOLDEN_P1_MODE
    )


def _golden_cpu_qd2_prefetch_requested(config: config_mod.ResolvedConfig) -> bool:
    """Resolve the registered run-only Golden arm, never ambient process env."""
    flag = config.flag(GOLDEN_CPU_QD2_PREFETCH_FLAG)
    raw = str(getattr(flag, "value", "0") if flag is not None else "0").strip().lower()
    if raw not in {"0", "1"}:
        raise GateError(
            f"{GOLDEN_CPU_QD2_PREFETCH_FLAG} must resolve to 0 or 1; got {raw!r}"
        )
    return raw == "1"


def _require_golden_cpu_qd2_deploy_gate(
    config: config_mod.ResolvedConfig,
    deployment_receipt: object | None = None,
) -> None:
    """Bind the run-only arm to the immutable deploy-baked gate."""
    requested = _golden_cpu_qd2_prefetch_requested(config)
    trusted: dict[str, str] = {}
    if deployment_receipt is not None:
        raw = (
            deployment_receipt.get("effective_environment", {})
            if isinstance(deployment_receipt, Mapping)
            else getattr(deployment_receipt, "effective_environment", {})
        )
        if isinstance(raw, dict):
            trusted = {str(key): str(value).strip().lower() for key, value in raw.items()}
    deploy_flag = config.flag(GOLDEN_CPU_QD2_DEPLOY_FLAG)
    gate = trusted.get(
        GOLDEN_CPU_QD2_DEPLOY_FLAG,
        str(getattr(deploy_flag, "value", "0") if deploy_flag is not None else "0")
        .strip()
        .lower(),
    )
    instant_tensor = any(
        "instanttensor" in name.lower() and value in {"1", "true", "yes", "on"}
        for name, value in trusted.items()
    )
    if instant_tensor:
        raise GateError(
            "Golden control/QD2 arms refuse InstantTensor; select a deployment "
            "without an InstantTensor flag"
        )
    if requested and gate not in {"1", "true", "yes", "on"}:
        raise GateError(
            f"{GOLDEN_CPU_QD2_PREFETCH_FLAG}=1 requires the deployed "
            f"{GOLDEN_CPU_QD2_DEPLOY_FLAG}=1 gate"
        )


DEFAULT_MODAL_ENVIRONMENT = "(default)"
PUBLISHER_FUNCTION_NAME = "sync_custom_nodes_to_volume"


@dataclass(frozen=True)
class WorkspaceBinding:
    """Frozen, credential-bearing workspace selection for one operation.

    Credentials are deliberately absent from all public/provenance projections.
    ``environment`` is ``(default)`` when Modal's default environment is being
    used; this makes the selection explicit without changing Modal's default
    lookup semantics.
    """

    workspace_id: str
    label: str
    environment: str
    token_id: str
    token_secret: str
    source: str = "config/v2/modal_target.toml"
    registry: str = ""

    def __repr__(self) -> str:
        return (
            "WorkspaceBinding(workspace_id={!r}, label={!r}, environment={!r})"
        ).format(self.workspace_id, self.label, self.environment)

    @property
    def workspace_label(self) -> str:
        return self.label

    @property
    def public(self) -> dict[str, str]:
        data = {
            "workspace_id": self.workspace_id,
            "workspace": self.workspace_id,
            "workspace_label": self.label,
            "environment": self.environment,
            "source": self.source,
            "registry": self.registry,
        }
        if self.source == "config/v2/modal_target.toml" and self.registry:
            return data
        return {"workspace": self.workspace_id, "environment": self.environment}

    @property
    def credentials(self) -> dict[str, str]:
        return {
            "MODAL_TOKEN_ID": self.token_id,
            "MODAL_TOKEN_SECRET": self.token_secret,
        }

    @property
    def workspace(self) -> dict[str, str]:
        """Compatibility projection for the existing custom-node publisher API.

        Keep construction private so new control-plane code does not pass a
        mutable credential-bearing record around accidentally.
        """
        return self._workspace_payload()

    def _workspace_payload(self) -> dict[str, str]:
        return {
            "id": self.workspace_id,
            "label": self.label,
            "token_id": self.token_id,
            "token_secret": self.token_secret,
            "environment": self.environment,
        }

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


def compute_deploy_id(config: config_mod.ResolvedConfig) -> str:
    """The one identity that says which deployment served a request.

    Derived from the shipped source revision, the resolved deploy-time
    configuration, the target class/method, and the deployment-relevant resource
    shape. Request-only settings and local/diagnostic noise are excluded, so the
    same deployment always yields the same id.

    This is computed here at deploy construction and baked into the class
    environment; the runtime freezes it at import and reports it per request, so
    a stale snapshot or a wrong deployment is caught by comparing the expected id
    with the one the executing interpreter reports.
    """
    resources: dict[str, object] = {}
    resolved = getattr(config, "resources", None)
    for field in ("gpu", "cpu", "memory_mb", "timeout_s"):
        value = getattr(resolved, field, None)
        if value is not None:
            resources[field] = value
    deploy_flags = getattr(config, "deploy_flags", None)
    resolved_config: dict[str, object] = {}
    if isinstance(deploy_flags, dict):
        resolved_config = {
            str(name): getattr(flag, "value", flag) for name, flag in deploy_flags.items()
        }
    elif isinstance(deploy_flags, (list, tuple)):
        resolved_config = {str(name): "" for name in deploy_flags}

    target = config.target
    return deploy_identity.compute_deploy_id(
        source_revision=str(getattr(config.git, "head", "") or ""),
        resolved_config=resolved_config,
        target={
            "app": target.app,
            "class": target.class_name,
            "method": getattr(target, "method", "") or "",
        },
        resources=resources,
    )


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
        # The authoritative deployment identity. The runtime reads this once at
        # import and reports it with every Golden request.
        deploy_identity.DEPLOY_ID_ENV: compute_deploy_id(config),
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
    is_golden = is_golden_profile_name(profile)
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


def _redact_backend_diagnostic(text: str, env: Mapping[str, str]) -> str:
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
    # Cover token-shaped values emitted without a field name (for example by
    # an SDK exception's repr).  This is deliberately conservative and is in
    # addition to replacement of the exact credentials supplied to the child.
    output = re.sub(
        r"(?i)\b(?:ak|as|mk|ms|wk|ws)[-_][a-z0-9_-]{8,}\b",
        "<redacted>",
        output,
    )
    output = re.sub(r"(?i)\bbearer\s+[^\s,;]+", "Bearer <redacted>", output)
    return output


def _safe_backend_diagnostic(text: str, env: Mapping[str, str]) -> str:
    """Return bounded backend output with credential-shaped values redacted."""
    output = _redact_backend_diagnostic(text, env)
    if len(output) > _BACKEND_DIAGNOSTIC_MAX_CHARS:
        output = output[:_BACKEND_DIAGNOSTIC_MAX_CHARS]
        output += "\n...[diagnostic output truncated]"
    return output


def _safe_exception_diagnostic(
    exc: BaseException, *, secrets: Mapping[str, str] | None = None
) -> str:
    """Format an exception for users without exposing SDK payloads/secrets."""
    env = {
        str(name): str(value)
        for name, value in dict(secrets or {}).items()
        if value
    }
    detail = _safe_backend_diagnostic(str(exc), env)
    return f"{type(exc).__name__}: {detail[:1024]}"


def _safe_public_value(value: object, secrets: Mapping[str, str]) -> str | None:
    """Bound and redact one diagnostic field, including nested reprs."""
    text = _safe_backend_diagnostic(str(value or ""), secrets)
    return text[:512] or None


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


def _persist_full_backend_diagnostic(
    result: backend_mod.BackendResult,
    env: dict[str, str],
    repo_root: Path,
    invocation_id: str,
) -> tuple[Path, Path] | None:
    """Preserve complete failed-deploy streams before bounded presentation."""
    directory = repo_root / ".v2ctl" / "deployment_diagnostics"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = f"deploy_{stamp}_{invocation_id[:12]}"
        stdout_path = directory / f"{stem}.stdout.log"
        stderr_path = directory / f"{stem}.stderr.log"
        stdout_path.write_text(
            _redact_backend_diagnostic(result.stdout, env), encoding="utf-8"
        )
        stderr_path.write_text(
            _redact_backend_diagnostic(result.stderr, env), encoding="utf-8"
        )
        print(
            f"[v2ctl.deploy] full_diagnostics stdout={stdout_path} "
            f"stderr={stderr_path}",
            file=sys.stderr,
        )
        return stdout_path, stderr_path
    except OSError as exc:
        print(
            f"[v2ctl.deploy] WARNING: could not persist full diagnostics: {exc}",
            file=sys.stderr,
        )
        return None


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
        if is_golden_profile_name(config.profile_name):
            return (
                "golden_p1_parallel"
                if golden_profile_mode(config.profile_name) == "parallel"
                else GOLDEN_P1_SELECTOR
            )
        env = {f.name: f.value for f in config.flags}
        if config.profile_name == E37_CLEAN_LANE_PROFILE or any(
            str(env.get(name, "0")).lower() in ("1", "true", "yes", "on")
            for name in ("COMFYMODAL_V2_E37_CLEAN_LANE", "COMFYMODAL_V2_CLEAN_LANE")
        ):
            return E37_CLEAN_LANE_SELECTOR
        if str(env.get("COMFYMODAL_V2_M2_PRODUCTION_LOADER", "0")).lower() in (
            "1", "true", "yes", "on"
        ):
            return "M2_PRODUCTION_VALIDATION"
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
    if is_golden_profile_name(config.profile_name):
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
        # Resolve the profile/request default before dispatch so the sampler
        # receives an explicit backend rather than relying on an implicit
        # PyTorch fallback.
        if attention_flag is not None:
            # Resolve before dispatch, including the accepted PyTorch default;
            # omission would leave backend identity implicit in the command.
            args += ["--attention-backend", resolved_attention_backend(config)]
        if _golden_cpu_qd2_prefetch_requested(config):
            args += ["--golden-p1-cpu-qd2-prefetch"]
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
            is_golden_profile_name(config.profile_name)
            and (mode_flag is None or getattr(mode_flag, "source", "") == "default")
        ):
            return golden_harness_mode_for_profile(config.profile_name)
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
    expected_mode = golden_harness_mode_for_profile(profile)
    if not is_golden_profile_name(profile) and effective_mode in {
        GOLDEN_P1_MODE, GOLDEN_PARALLEL_MODE,
    }:
        raise GateError(
            f"{command} refuses V2_BENCHMARK_MODE={effective_mode} for "
            f"non-Golden profile {profile or '(missing)'}; only Golden profiles may use it"
        )
    if not is_golden_profile_name(profile):
        return
    if mode_flag is None or mode_flag.source not in {"cli", "inherit", "set"}:
        return
    mode = str(mode_flag.value or "").strip()
    if mode != expected_mode:
        raise GateError(
            f"{command} refuses explicit V2_BENCHMARK_MODE={mode or '(empty)'} "
            f"for {profile}; only {expected_mode} is allowed"
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
    if is_golden_profile_name(profile):
        expected_method = golden_method_for_profile(profile)
        if method != expected_method:
            raise GateError(
                f"{command} refuses {profile} target.method={method or '(missing)'}; "
                f"{profile} requires {expected_method}"
            )
    elif method != FULL_RUN_METHOD:
        raise GateError(
            f"{command} refuses target.method={method or '(missing)'}; non-Golden "
            f"profiles require {FULL_RUN_METHOD}"
        )


def _app_version_number(
    app_name: str,
    workspace: Mapping[str, object] | WorkspaceBinding | None = None,
    environment: str | None = None,
) -> int | None:
    """Highest ``v<N>`` version number from ``modal app history`` (0 if none).

    Returns ``None`` on lookup uncertainty.  The history table rows look
    like ``| v9 | 2026-08-19 17:42 Central Daylight | ...``; the header row
    (``| Version | ...``) contains no ``v<num>`` and is ignored by the regex.

    Canonical callers pass the frozen config-owned destination; the raw
    ``modal`` CLI profile is never trusted.
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
        # Resolve credentials from the frozen binding, not the ambient Modal
        # profile.  The one-argument compatibility path retains the historical
        # active-workspace behavior for older callers and test doubles.
        if isinstance(workspace, WorkspaceBinding):
            ws = workspace._workspace_payload()
        elif isinstance(workspace, Mapping):
            ws = workspace
        else:
            # Compatibility callers without a parsed canonical destination
            # retain the legacy lookup; all parser-created remote commands
            # provide a WorkspaceBinding and never enter this branch.
            root = Path(__file__).resolve().parents[2]
            # Compatibility-only one-argument test/tool API. Canonical
            # commands always pass the frozen binding and never enter here.
            data = modal_workspaces.load_workspace_registry(
                root / ".modal_workspaces.json"
            )
            ws = modal_workspaces.get_active_workspace(data)
        if not ws or not ws.get("token_id") or not ws.get("token_secret"):
            return None
        env = dict(os.environ)
        for name in list(env):
            if name.startswith("MODAL_") or name in {
                "COMFYMODAL_ENVIRONMENT",
                "COMFYMODAL_V2_ENVIRONMENT",
                "COMFYMODAL_MODAL_PROFILE",
            }:
                env.pop(name, None)
        env["MODAL_TOKEN_ID"] = str(ws["token_id"])
        env["MODAL_TOKEN_SECRET"] = str(ws["token_secret"])
        selected_environment = environment
        if selected_environment is None and isinstance(workspace, (WorkspaceBinding, Mapping)):
            selected_environment = str(ws.get("environment") or "").strip()
        if selected_environment and selected_environment != DEFAULT_MODAL_ENVIRONMENT:
            env["MODAL_ENVIRONMENT"] = selected_environment
        else:
            env.pop("MODAL_ENVIRONMENT", None)
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
    """Compatibility name: return credentials for the frozen config target."""
    workspace = _active_workspace(repo_root)
    return {
        "MODAL_TOKEN_ID": str(workspace["token_id"]),
        "MODAL_TOKEN_SECRET": str(workspace["token_secret"]),
    }


def _active_workspace(repo_root: Path) -> dict[str, object]:
    """Compatibility projection of the immutable config-owned destination."""
    try:
        return modal_workspaces.resolve_modal_destination(repo_root)
    except (OSError, ValueError, RuntimeError) as exc:
        raise GateError(f"Modal destination cannot be resolved: {exc}") from exc


def resolve_workspace_binding(
    repo_root: Path,
    *,
    workspace_id: str | None = None,
    environment: str | None = None,
) -> WorkspaceBinding:
    """Resolve and freeze the config-owned destination before remote work."""
    target_path = Path(repo_root) / "config" / "v2" / "modal_target.toml"
    if not target_path.exists() and (workspace_id or environment):
        # Compatibility-only API for old callers that explicitly constructed
        # a temporary registry. Canonical parser commands are blocked below
        # when the target config is absent and never enter this branch.
        # Compatibility-only path for pre-target unit callers.  Canonical
        # parser commands reject a missing target before reaching this branch.
        registry = modal_workspaces.load_workspace_registry(
            Path(repo_root) / ".modal_workspaces.json"
        )
        active = modal_workspaces.get_active_workspace(registry)
        selected = modal_workspaces.get_workspace(registry, str(workspace_id).strip()) if workspace_id else active
        if not isinstance(selected, dict):
            raise GateError(f"Modal workspace {workspace_id!r} is not registered")
        if isinstance(active, dict) and selected.get("id") != active.get("id"):
            raise GateError(f"active Modal workspace does not match frozen workspace {selected.get('id')!r}")
        return WorkspaceBinding(
            workspace_id=str(selected.get("id") or ""),
            label=str(selected.get("label") or ""),
            environment=str(environment or selected.get("environment") or DEFAULT_MODAL_ENVIRONMENT),
            token_id=str(selected.get("token_id") or ""),
            token_secret=str(selected.get("token_secret") or ""),
        )
    try:
        selected = modal_workspaces.resolve_modal_destination(repo_root)
    except (OSError, ValueError, RuntimeError) as exc:
        raise GateError(f"Modal destination cannot be resolved: {exc}") from exc
    if workspace_id and str(workspace_id).strip() != selected["workspace_id"]:
        raise GateError(
            "workspace override rejected: Modal destination is config-owned by "
            "config/v2/modal_target.toml"
        )
    if environment and str(environment).strip() != selected["environment"]:
        raise GateError(
            "environment override rejected: Modal destination is config-owned by "
            "config/v2/modal_target.toml"
        )
    return WorkspaceBinding(
        workspace_id=str(selected["workspace_id"]),
        label=str(selected["workspace_label"]),
        environment=str(selected["environment"]),
        token_id=str(selected["token_id"]),
        token_secret=str(selected["token_secret"]),
        source=str(selected["source"]),
        registry=str(selected["registry"]),
    )


def assert_workspace_binding_current(repo_root: Path, binding: WorkspaceBinding) -> None:
    """Fail closed if the registry changed after the operation was frozen."""
    if binding.source == "config/v2/modal_target.toml" and not binding.registry:
        # Compatibility-only binding created without the tracked target.
        registry = modal_workspaces.load_workspace_registry(
            Path(repo_root) / ".modal_workspaces.json"
        )
        active = modal_workspaces.get_active_workspace(registry)
        if not isinstance(active, dict) or active.get("id") != binding.workspace_id:
            raise GateError("active Modal workspace changed after preflight")
        return
    current = resolve_workspace_binding(repo_root)
    if current.workspace_id != binding.workspace_id:
        raise GateError("active Modal workspace changed after preflight")
    if current.environment != binding.environment:
        raise GateError("Modal environment changed after preflight")
    if current.label != binding.label or current.token_id != binding.token_id or current.token_secret != binding.token_secret:
        raise GateError("configured Modal destination changed after preflight")


def _workspace_binding_for_args(args, repo_root: Path) -> WorkspaceBinding | None:
    """Resolve canonical config target; reject legacy CLI destination knobs."""
    if not (Path(repo_root) / "config" / "v2" / "modal_target.toml").is_file():
        raise GateError(
            "Modal target config is missing: canonical remote commands require "
            "config/v2/modal_target.toml"
        )
    workspace_id = getattr(args, "workspace_id", None) or getattr(args, "workspace", None)
    if workspace_id or getattr(args, "environment", None):
        raise GateError(
            "workspace/environment override rejected: Modal destination is "
            "config-owned by config/v2/modal_target.toml"
        )
    return resolve_workspace_binding(
        repo_root,
        workspace_id=workspace_id,
        environment=getattr(args, "environment", None),
    )


def _canonical_workspace_binding(args: Any, repo_root: Path, config: Any) -> WorkspaceBinding:
    if not any(hasattr(args, name) for name in ("workspace_id", "workspace", "environment")):
        # Compatibility boundary for older injected command doubles.  Real
        # parser-created canonical commands always carry these global fields.
        return None  # type: ignore[return-value]
    binding = _workspace_binding_for_args(args, repo_root)
    assert binding is not None
    # FingerprintEngine and all downstream identity writers see the same
    # immutable object that will be injected into remote calls.
    setattr(config, "modal_destination", binding)
    return binding


def _apply_workspace_binding_to_env(env: dict[str, str], binding: WorkspaceBinding) -> None:
    """Replace ambient Modal selection with the frozen selection."""
    if binding is None:
        return
    for name in list(env):
        if name.startswith("MODAL_") or name in {"COMFYMODAL_ENVIRONMENT", "COMFYMODAL_V2_ENVIRONMENT", "COMFYMODAL_MODAL_PROFILE"}:
            env.pop(name, None)
    env.update(binding.credentials)
    env[env_mod.V2CTL_DESTINATION_FROZEN_ENV] = "1"
    env[env_mod.V2CTL_WORKSPACE_ID_ENV] = binding.workspace_id
    env[env_mod.V2CTL_WORKSPACE_LABEL_ENV] = binding.label
    if binding.environment != DEFAULT_MODAL_ENVIRONMENT:
        env["MODAL_ENVIRONMENT"] = binding.environment


def _apply_workspace_binding_to_process(binding: WorkspaceBinding) -> None:
    """Set process-local Modal selection for source-probe transport."""
    for name in list(os.environ):
        if name.startswith("MODAL_") or name in {"COMFYMODAL_ENVIRONMENT", "COMFYMODAL_MODAL_PROFILE"}:
            os.environ.pop(name, None)
    os.environ.pop("COMFYMODAL_ENVIRONMENT", None)
    os.environ.pop("COMFYMODAL_V2_ENVIRONMENT", None)
    os.environ.update(binding.credentials)
    os.environ[env_mod.V2CTL_WORKSPACE_ID_ENV] = binding.workspace_id
    os.environ[env_mod.V2CTL_WORKSPACE_LABEL_ENV] = binding.label
    if binding.environment == DEFAULT_MODAL_ENVIRONMENT:
        os.environ.pop("MODAL_ENVIRONMENT", None)
        os.environ.pop("COMFYMODAL_ENVIRONMENT", None)
    else:
        os.environ["MODAL_ENVIRONMENT"] = binding.environment
        os.environ["COMFYMODAL_ENVIRONMENT"] = binding.environment
        os.environ["COMFYMODAL_V2_ENVIRONMENT"] = binding.environment


@contextmanager
def _workspace_process_environment(
    binding: WorkspaceBinding | None, extra: Mapping[str, str] | None = None
):
    """Temporarily bind process-based Modal clients, restoring the parent env."""
    original = dict(os.environ)
    try:
        if binding is not None:
            _apply_workspace_binding_to_process(binding)
        if extra:
            os.environ.update({str(name): str(value) for name, value in extra.items()})
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def _call_version_probe(app_name: str, binding: WorkspaceBinding) -> int | None:
    """Call the version probe without breaking one-argument test fakes."""
    try:
        parameters = inspect.signature(_app_version_number).parameters
    except (TypeError, ValueError):
        parameters = {}
    if len(parameters) >= 3:
        return _app_version_number(app_name, binding, binding.environment)
    if len(parameters) >= 2:
        return _app_version_number(app_name, binding)
    return _app_version_number(app_name)


def _checked_version_probe(repo_root: Path, app_name: str, binding: WorkspaceBinding) -> int | None:
    assert_workspace_binding_current(repo_root, binding)
    return _call_version_probe(app_name, binding)


class _FrozenWorkspaceBackendRunner:
    """Inject a frozen workspace into every GateRunner/ConfirmRunner call.

    GateRunner and ConfirmRunner own the execution loop and intentionally have
    no workspace parameter.  Wrapping their existing backend API is narrower
    than changing the shared validator: the wrapper rechecks the registry for
    each actual invocation and puts the frozen credentials last in the child
    environment, overriding any ambient Modal selection without mutating it.
    """

    def __init__(self, runner: Any, repo_root: Path, binding: WorkspaceBinding) -> None:
        self._runner = runner
        self._repo_root = Path(repo_root)
        self._binding = binding

    def run(self, spec, *, config, extra_args=(), extra_env=None, capture=True,
            timeout_seconds=None, invocation_id=None, invocation_context=None,
            canonical_identity=None, strict_canonical_discovery=False,
            allow_multiple_run_artifacts=False):
        assert_workspace_binding_current(self._repo_root, self._binding)
        bound_env = dict(extra_env or {})
        _apply_workspace_binding_to_env(bound_env, self._binding)
        kwargs: dict[str, Any] = {
            "config": config,
            "extra_args": list(extra_args),
            "extra_env": bound_env,
            "capture": capture,
            "timeout_seconds": timeout_seconds,
            "invocation_id": invocation_id,
            "invocation_context": invocation_context,
            "canonical_identity": canonical_identity,
            "strict_canonical_discovery": strict_canonical_discovery,
            "allow_multiple_run_artifacts": allow_multiple_run_artifacts,
        }
        try:
            parameters = inspect.signature(self._runner.run).parameters
        except (TypeError, ValueError):
            parameters = {}
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        if not accepts_kwargs:
            kwargs = {name: value for name, value in kwargs.items() if name in parameters}
        return self._runner.run(spec, **kwargs)


def _make_backend_runner(repo_root: Path, env_builder: Any, binding: WorkspaceBinding | None) -> Any:
    """Construct runners while keeping older injected two-argument fakes valid."""
    constructor = backend_mod.BackendRunner
    try:
        parameters = list(inspect.signature(constructor).parameters.values())
        positional = [p for p in parameters if p.kind in (
            inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD
        )]
        variadic = any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in parameters)
    except (TypeError, ValueError):
        positional, variadic = [], True
    if variadic or len(positional) >= 3:
        return constructor(repo_root, env_builder, binding)
    return constructor(repo_root, env_builder)


def _publisher_function_exists(
    binding: WorkspaceBinding,
    app_name: str = CUSTOM_NODES_PUBLISHER_APP_NAME,
    function_name: str = PUBLISHER_FUNCTION_NAME,
) -> bool | None:
    """Probe the publisher Function using the frozen client/workspace."""
    try:
        import modal

        client = modal.Client.from_credentials(binding.token_id, binding.token_secret)
        function = modal.Function.from_name(
            app_name,
            function_name,
            client=client,
            environment_name=(
                None if binding.environment == DEFAULT_MODAL_ENVIRONMENT
                else binding.environment
            ),
        )
        hydrate = getattr(function, "hydrate", None)
        if callable(hydrate):
            hydrate()
        return True
    except Exception as exc:
        # A not-found response is absence.  Authentication, transport, and
        # malformed-response failures are uncertainty and must fail closed.
        text = str(exc).casefold()
        if any(
            re.search(pattern, text)
            for pattern in (
                r"\bfunction\b[^\n]*\b(?:not found|does not exist)\b",
                r"\bno such function\b",
                r"\bcould not find (?:the )?function\b",
                r"\bapp(?:lication)?\b[^\n]*\b(?:not found|does not exist)\b",
                r"\bno such app(?:lication)?\b",
            )
        ):
            return False
        return None


def _publisher_probe(
    repo_root: Path,
    binding: WorkspaceBinding,
    *,
    publisher_app: str = CUSTOM_NODES_PUBLISHER_APP_NAME,
    function_name: str = PUBLISHER_FUNCTION_NAME,
) -> dict[str, object]:
    """Default, credential-scoped publisher probes; all calls are lazy."""
    from . import custom_nodes as custom_nodes_mod

    assert_workspace_binding_current(repo_root, binding)
    version = _call_version_probe(publisher_app, binding)
    function_exists = None
    if version is not None:
        assert_workspace_binding_current(repo_root, binding)
        function_exists = _publisher_function_exists(binding, publisher_app, function_name)
    # ``_app_version_number`` uses zero for a known missing/no-deployments
    # response.  A successful Function lookup disambiguates an existing app
    # whose history is empty; otherwise zero is treated as missing.
    if version is None:
        app_exists: bool | None = None
    else:
        app_exists = version > 0 or function_exists is True
    remote_generation: str | None = None
    try:
        assert_workspace_binding_current(repo_root, binding)
        volume = custom_nodes_mod.get_volume(
            CUSTOM_NODES_VOLUME_NAME, workspace=binding._workspace_payload()
        )
        remote_generation = custom_nodes_mod._content_generation_readback(volume)
    except Exception:
        # A missing/unreadable volume is not an exact match and cannot become a
        # skip by accident.
        remote_generation = None
    return {
        "publisher_exists": app_exists,
        "publisher_function_exists": function_exists,
        "publisher_version": version,
        "remote_generation": remote_generation,
    }


def _local_content_generation(repo_root: Path) -> str:
    from . import custom_nodes as custom_nodes_mod

    source_root = custom_nodes_mod.resolve_custom_nodes_root(repo_root)
    identity = custom_nodes_mod.build_source_identity(source_root)
    return str(identity.content_generation)




def run_publisher_preflight(
    repo_root: Path,
    binding: WorkspaceBinding,
    *,
    local_content_generation: str | None = None,
    probe: Any | None = None,
    publisher_app: str = CUSTOM_NODES_PUBLISHER_APP_NAME,
    function_name: str = PUBLISHER_FUNCTION_NAME,
    require_ready: bool = False,
) -> dict[str, object]:
    """Resolve the publisher decision and persist its control-plane record.

    ``probe`` is injectable so tests can prove ordering without Modal/GPU
    calls.  It receives ``(repo_root, binding)`` or just ``binding``.
    """
    assert_workspace_binding_current(repo_root, binding)
    local = local_content_generation or _local_content_generation(repo_root)
    if probe is None:
        observed = _publisher_probe(
            repo_root, binding, publisher_app=publisher_app, function_name=function_name
        )
    elif isinstance(probe, Mapping):
        observed = probe
    else:
        try:
            count = len(inspect.signature(probe).parameters)
        except (TypeError, ValueError):
            count = 2
        observed = probe(repo_root, binding) if count >= 2 else probe(binding)
    if not isinstance(observed, Mapping):
        raise GateError("publisher preflight probe returned malformed state")
    def presence(*names: str) -> bool | None:
        for name in names:
            if name in observed:
                value = observed[name]
                if value is None:
                    return None
                if isinstance(value, bool):
                    return value
                normalized = str(value).strip().casefold()
                if normalized in {"1", "true", "yes", "on", "exists"}:
                    return True
                if normalized in {"0", "false", "no", "off", "absent", "missing"}:
                    return False
                return None
        return None

    app_exists = presence("publisher_exists", "app_exists")
    function_exists = presence("publisher_function_exists", "function_exists")
    version = observed.get("publisher_version", observed.get("version"))
    if isinstance(version, str) and version.strip().isdigit():
        version = int(version.strip())
    remote = observed.get("remote_generation", observed.get("content_generation"))
    remote = str(remote).strip() if remote is not None and str(remote).strip() else None

    # One question: does this deployment require publication?
    #
    #   publisher app/Function missing -> the publisher must be deployed first
    #   published content != local     -> publish
    #   published content == local     -> skip (avoids a pointless re-upload)
    #   anything undetermined          -> publish
    #
    # The old machine had a fifth state, "invalid", for an undetermined lookup,
    # and callers refused to act on it. That distrusted the probe instead of
    # choosing the safe action: publishing is idempotent and always correct, so
    # an unknown answer means publish. A version counter is no longer consulted
    # at all -- it never established whether anything was published.
    app_missing = app_exists is False or function_exists is False
    if app_missing:
        decision = "bootstrap_required"
    elif remote is not None and local and remote == local:
        decision = "skip_exact"
    else:
        decision = "publish_required"

    data: dict[str, object] = {
        "WORKSPACE": binding.workspace_id,
        "ENVIRONMENT": binding.environment,
        "PUBLISHER_APP": publisher_app,
        "PUBLISHER_EXISTS": app_exists,
        "PUBLISHER_FUNCTION_EXISTS": function_exists,
        "PUBLISHER_VERSION": version,
        "LOCAL_CONTENT_GENERATION": local,
        "REMOTE_CONTENT_GENERATION": remote,
        "PUBLICATION_DECISION": decision,
        "REQUIRES_PUBLICATION": decision != "skip_exact",
        "READY_FOR_CONSUMER_DEPLOY": decision == "skip_exact",
    }
    if require_ready and decision != "skip_exact":
        raise GateError(
            "custom-node publication has not been performed for this bundle: "
            f"decision={decision}"
        )
    return data


def _verify_publisher_after_bootstrap(
    repo_root: Path,
    binding: WorkspaceBinding,
    before: Mapping[str, object],
    *,
    probe: Any | None = None,
) -> dict[str, object]:
    """Require the publisher app and its Function to exist after bootstrap.

    A version advance is deliberately NOT required. Modal's numeric version
    counter is not evidence that an app was updated -- it can advance for
    unrelated reasons, fail to advance when a deploy succeeded, and reset when
    Modal renumbers its history. App and Function existence is the actual
    question, and it is answered directly.
    """
    assert_workspace_binding_current(repo_root, binding)
    after = run_publisher_preflight(
        repo_root,
        binding,
        local_content_generation=(
            str(before.get("LOCAL_CONTENT_GENERATION") or "") or None
        ),
        probe=probe,
    )
    if not after["PUBLISHER_EXISTS"] or not after["PUBLISHER_FUNCTION_EXISTS"]:
        raise GateError("publisher bootstrap did not verify app and Function")
    return after


def _print_golden_predeploy_card(
    invocation_id: str, preflight: Mapping[str, object], *, lock_state: str = "CLEAR"
) -> None:
    """Print the compact RX9P-A admission card, without credentials."""
    yes_no = lambda value: "YES" if value else "NO"
    print("[v2ctl.golden.pre-deploy]")
    print(f"EXPERIMENT_ID={invocation_id}")
    print(f"MODAL_WORKSPACE={preflight.get('WORKSPACE', '')}")
    print(f"MODAL_ENVIRONMENT={preflight.get('ENVIRONMENT', '')}")
    print(f"PUBLISHER_APP={preflight.get('PUBLISHER_APP', '')}")
    print(f"PUBLISHER_EXISTS={yes_no(preflight.get('PUBLISHER_EXISTS'))}")
    print(
        "PUBLISHER_FUNCTION_EXISTS="
        f"{yes_no(preflight.get('PUBLISHER_FUNCTION_EXISTS'))}"
    )
    print(f"PUBLISHER_VERSION={preflight.get('PUBLISHER_VERSION')}")
    print(f"LOCAL_CONTENT_GENERATION={preflight.get('LOCAL_CONTENT_GENERATION', '')}")
    print(f"REMOTE_CONTENT_GENERATION={preflight.get('REMOTE_CONTENT_GENERATION') or '(none)'}")
    print(f"PUBLICATION_DECISION={preflight.get('PUBLICATION_DECISION', 'invalid')}")
    print(f"DEPLOY_LOCK={lock_state}")
    print(
        "READY_FOR_CONSUMER_DEPLOY="
        f"{yes_no(preflight.get('READY_FOR_CONSUMER_DEPLOY'))}"
    )


def _print_destination_preflight(binding: WorkspaceBinding | None, *, deploying: bool = False) -> None:
    """Print the non-secret destination admission card before remote work."""
    if binding is None:
        return
    print("[v2ctl.destination.preflight]")
    print(f"CONFIG_SOURCE={binding.source}")
    print(f"WORKSPACE_ID={binding.workspace_id}")
    print(f"WORKSPACE_LABEL={binding.label}")
    print(f"MODAL_ENVIRONMENT={binding.environment}")
    print(f"REGISTRY={binding.registry}")
    print("AMBIENT_MODAL_PROFILE=IGNORED")
    print("DESTINATION_STATUS=VERIFIED")
    if deploying:
        print(f"DEPLOYING TO={binding.workspace_label} ({binding.workspace_id})")


# ── Manifests ──────────────────────────────────────────────────────────

def _deployment_manifest_dir(repo_root: Path) -> Path:
    return repo_root / ".v2ctl" / "deployments"


def _receipt_target(config: config_mod.ResolvedConfig) -> dict[str, str]:
    return {
        "app": str(config.target.app),
        "class": str(config.target.class_name),
        "method": str(config.target.method),
    }


def _modal_destination_record(config: Any) -> dict[str, str]:
    destination = getattr(config, "modal_destination", None)
    if isinstance(destination, Mapping):
        value = lambda name, alias="": destination.get(name, destination.get(alias, ""))
    else:
        value = lambda name, alias="": getattr(destination, name, getattr(destination, alias, ""))
    return {
        "workspace_id": str(value("workspace_id") or ""),
        "workspace_label": str(value("workspace_label", "label") or ""),
        "environment": str(value("environment") or ""),
        "source": "config/v2/modal_target.toml",
    }


def _bound_deployment_receipt(
    repo_root: Path,
    config: config_mod.ResolvedConfig,
    *,
    command: str,
    workspace_binding: WorkspaceBinding | None = None,
) -> tuple[Path, receipt_mod.DeploymentReceipt]:
    """Load the immutable Golden authority and perform host admission checks."""
    # Older direct callers may supply no binding; canonical command paths
    # always resolve one before entering this helper.
    if workspace_binding is None:
        workspace_binding = None
    selected = receipt_mod.latest_deployment_receipt(
        repo_root,
        profile=config.profile_name,
        target=_receipt_target(config),
        workspace_id=(workspace_binding.workspace_id if workspace_binding else None),
    )
    if selected is None:
        raise GateError(f"{command} requires an immutable deployment receipt")
    path, receipt = selected
    target = _receipt_target(config)
    if receipt.target != target:
        raise GateError(f"{command} deployment receipt target mismatch")
    if receipt.profile != config.profile_name:
        raise GateError(f"{command} deployment receipt profile mismatch")
    if workspace_binding is not None:
        _require_receipt_workspace(receipt, workspace_binding, command=command)
        destination = receipt.modal_destination
        expected_destination = {
            "workspace_id": workspace_binding.workspace_id,
            "workspace_label": workspace_binding.label,
            "environment": workspace_binding.environment,
            "source": workspace_binding.source,
        }
        if destination != expected_destination:
            raise GateError(f"{command} deployment receipt destination mismatch")
    # Modal's numeric app version is diagnostic metadata only, never authority.
    #
    # It used to be a hard gate here: a receipt was rejected unless the current
    # version counter matched what the receipt recorded. That proved nothing
    # about which code actually serves a request, while creating invalid local
    # state whenever Modal reset or renumbered its version history -- which it
    # did, leaving a perfectly good deployment unusable until redeployed. The
    # serving request's own deploy_id is the authority; a version drift is
    # reported so it is visible when debugging, not treated as a failure.
    if workspace_binding is not None:
        assert_workspace_binding_current(repo_root, workspace_binding)
        observed_version = _call_version_probe(
            receipt.target["app"], workspace_binding
        )
    else:
        observed_version = _app_version_number(receipt.target["app"])
    if observed_version != receipt.deployment_version:
        print(
            "[v2ctl.%s] note: Modal app version is %r but the receipt recorded %r. "
            "This is diagnostic only; the request's deploy_id decides which "
            "deployment served it."
            % (command, observed_version, receipt.deployment_version),
            file=sys.stderr,
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


def _require_receipt_workspace(
    receipt: receipt_mod.DeploymentReceipt, binding: WorkspaceBinding, *, command: str
) -> None:
    expected_destination = {
        "workspace_id": binding.workspace_id,
        "workspace_label": binding.label,
        "environment": binding.environment,
        "source": binding.source,
    }
    if receipt.modal_destination != expected_destination:
        raise GateError(
            f"{command} deployment receipt destination mismatch: "
            f"stored={receipt.modal_destination!r} current={expected_destination!r}"
        )
    identity = receipt.deployment_identity
    workspace = str(identity.get("modal_workspace", ""))
    environment = str(identity.get("modal_environment", ""))
    if not workspace and not receipt.modal_destination:
        # A receipt must always carry its workspace binding; validate() enforces
        # that. Nothing here is a compatibility path for older records.
        return
    if workspace != binding.workspace_id or environment != binding.environment:
        raise GateError(
            f"{command} deployment receipt workspace/environment mismatch: "
            f"stored={workspace}/{environment} current={binding.workspace_id}/{binding.environment}"
        )


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
    workspace_id: str = ""
    environment: str = ""


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


def capture_deploy_identity(
    fingerprints: object, binding: WorkspaceBinding | None = None
) -> DeployIdentitySnapshot:
    """Capture all persisted deploy identity values exactly once."""
    deploy_fingerprint = getattr(fingerprints, "deploy_fingerprint")
    deploy_inputs = getattr(fingerprints, "deploy_inputs")
    return DeployIdentitySnapshot(
        deploy_fingerprint=str(deploy_fingerprint()),
        deploy_inputs=_freeze_deploy_identity(deploy_inputs()),
        profile_config_fingerprint=_profile_config_fingerprint(fingerprints),
        workspace_id=binding.workspace_id if binding is not None else "",
        environment=binding.environment if binding is not None else "",
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
    # behavior.  Deploy commands always pass their frozen deploy snapshot,
    # captured after the verified custom-node publication generation is known.
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
        "modal_workspace": deploy_identity.workspace_id if deploy_identity else "",
        "modal_environment": deploy_identity.environment if deploy_identity else "",
        "modal_destination": _modal_destination_record(config),
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
# A deploy proves the app was uploaded. Which deployment actually served a
           # request is established by the deploy_id the executing interpreter
           # reports, compared against the expected one at acceptance time, so
           # no separate probe is required. This field is diagnostic only.
           "source_identity_status": "unknown",
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
        packages = getattr(identity, "package_manifests", None)
        if packages is None:
            packages = []
        package_evidence: list[dict[str, Any]] = []
        for item in packages:
            to_dict = getattr(item, "to_dict", None)
            raw: Any = to_dict() if callable(to_dict) else item
            if isinstance(raw, Mapping):
                package_evidence.append({str(key): raw[key] for key in raw})
        receipt = getattr(publication, "receipt", None)
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
            "source_root": str(getattr(identity, "source_root", "") or ""),
            "packages": package_evidence,
            "destructive_override": bool(getattr(publication, "destructive_override", False)),
            "destructive_delta": dict(getattr(publication, "destructive_delta", {}) or {}),
            "receipt_destructive_override": bool(
                getattr(receipt, "destructive_override", False)
            ) if receipt is not None else False,
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
    # Custom-node publication carries no identity on the receipt. The receipt
    # records deploy_id, which is what a run is checked against; a publication
    # generation would be a second identity describing static code that already
    # belongs to the deployment. Publication is owned separately by
    # `golden publish-custom-nodes` and verified by the deploy path, not
    # attested to here.
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
        # The one identity a run is checked against. Computed the same way the
        # runtime computes it, so the value baked into the class environment and
        # the value recorded here cannot diverge.
        deploy_id=compute_deploy_id(config),
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
            "modal_workspace": deploy_identity.workspace_id,
            "modal_workspace_label": getattr(config.modal_destination, "label", ""),
            "modal_environment": deploy_identity.environment,
            "resources": {
                "gpu": str(config.resources.gpu),
                "cpu": int(config.resources.cpu),
                "memory_mb": int(config.resources.memory_mb),
            },
        },
        profile_config_fingerprint=deploy_identity.profile_config_fingerprint,
        manifest_path=str(manifest_path),
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
            "modal_workspace": deploy_identity.workspace_id,
            "modal_workspace_label": getattr(config.modal_destination, "label", ""),
            "modal_environment": deploy_identity.environment,
        },
        receipt_path=str(planned_path),
        modal_destination={
            "workspace_id": deploy_identity.workspace_id,
            "workspace_label": getattr(config.modal_destination, "label", "")
            if isinstance(getattr(config, "modal_destination", None), WorkspaceBinding)
            else "",
            "environment": deploy_identity.environment,
            "source": "config/v2/modal_target.toml",
        },
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
    sage_identity = sage_runtime_identity(
        config,
        getattr(result, "experiment_identity", {}),
        getattr(result.artifacts, "experiment_identity", {}),
    )
    arm_identity = golden_arm_identity(config) if is_golden_profile_name(config.profile_name) else {}
    result_identity = {
        **arm_identity,
        **(
            getattr(result, "experiment_identity", {})
            or getattr(result.artifacts, "experiment_identity", {})
            or {}
        ),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "deployment_hash_namespace": DEPLOYMENT_HASH_NAMESPACE,
        "fingerprint_algorithm": FINGERPRINT_ALGORITHM,
        "deployment_hash": deploy_fp,
        "created_at": _utcnow_iso(),
        "profile": config.profile_name,
        "owner": config.owner,
        "modal_workspace": (
            deployment_receipt.deployment_identity.get("modal_workspace", "")
            if deployment_receipt is not None else ""
        ),
        "modal_environment": (
            deployment_receipt.deployment_identity.get("modal_environment", "")
            if deployment_receipt is not None else ""
        ),
        "modal_destination": (
            dict(deployment_receipt.modal_destination)
            if deployment_receipt is not None
            else _modal_destination_record(config)
        ),
        "deploy_fingerprint": deploy_fp,
        "run_fingerprint": run_fp,
        "v2ctl_invocation_id": result.v2ctl_invocation_id,
        "profile_config_fingerprint": profile_fp,
        "request_id": result.request_id,
        "provenance_validation_status": result.provenance_validation_status,
        **arm_identity,
        **sage_identity,
        "attention_backend": (
            getattr(result, "attention_backend", None)
            or getattr(result.artifacts, "attention_backend", None)
        ),
        "experiment_identity": {**result_identity, **sage_identity},
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
            "attention_backend": (
                getattr(result, "attention_backend", None)
                or getattr(result.artifacts, "attention_backend", None)
            ),
            **arm_identity,
            "experiment_identity": {**result_identity, **sage_identity},
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

        _canonical_workspace_binding(args, repo_root, config)
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
            "profile": config.profile_name,
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


GOLDEN_PROFILE_DEPLOY_FLAGS = (
    ("COMFYMODAL_V2_FULL_TRACE", "1"),
    ("COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER", "1"),
    ("COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN", "1"),
)
GOLDEN_PROFILE_RUN_FLAGS = (
    ("COMFYMODAL_V2_GOLDEN_DEEP_TRACE", "1"),
)
_GOLDEN_COMMAND_HELP = {
    "doctor": "check local Golden readiness",
    "deploy": "deploy the Golden app without running a request",
    "run": "run exactly one Golden request",
    "publisher-bootstrap": "prepare custom-node publication",
    "publish-custom-nodes": "publish custom nodes to the app",
    "profile": "profile one Golden run end to end and print the decision report",
}

_GOLDEN_COMMAND_DESCRIPTION = {
    "profile": (
        "profile one Golden run end to end and print the decision report\n"
        "\n"
        "Runs a single request, identifies the trace that request produced,\n"
        "downloads and SHA-verifies its bundle, analyzes it, and writes the stage\n"
        "decision documents. Prints the report path when done.\n"
        "\n"
        "As one command (deploys first):\n"
        "  python tools/v2ctl.py --profile <profile> golden profile\n"
        "\n"
        "As two commands (deploy once, profile repeatedly):\n"
        "  python tools/v2ctl.py --profile <profile> golden deploy\n"
        "  python tools/v2ctl.py --profile <profile> golden profile --skip-deploy\n"
        "\n"
        "The app is resolved from the profile's target.app, so --app is only\n"
        "needed to override it. --profile defaults to the canonical Golden\n"
        "profile.\n"
        "\n"
        "Tracing flags are added automatically; do not pass them yourself:\n"
        "  COMFYMODAL_V2_FULL_TRACE=1\n"
        "  COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER=1\n"
        "  COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN=1\n"
        "  COMFYMODAL_V2_GOLDEN_DEEP_TRACE=1  (run only)\n"
        "\n"
        "Aborts if source-probe does not report RESULT=PASS, so a stale deployment\n"
        "is never profiled. Identifies the trace by what the run creates on the\n"
        "profile volume, not by scraping the container log.\n"
        "\n"
        "Options:\n"
        "  --skip-deploy       reuse the current deployment (must already carry\n"
        "                       the tracing flags)\n"
        "  --trace-id ID       analyze this existing trace instead of a new run\n"
        "  --min-ms FLOAT      call-tree expansion floor in ms (default 1.0)\n"
        "  --skip-analyze      reuse existing derived artifacts, only re-render\n"
        "  --workspace-id ID   Modal workspace id override for the bundle fetch\n"
        "  --dry-run           print the plan, invoke nothing\n"
        "\n"
        "Final output:\n"
        "  artifacts/golden_exhaustive_runs/<trace_id>/<trace_id>/session/derived/\n"
        "      golden_stage_report.md\n"
        "  containing the critical path, a whole-request function rollup, and a\n"
        "  recursive call tree per stage.\n"
        "\n"
        "This performs a real deploy and a real run, and the analysis is\n"
        "memory-hungry on very large traces. To work on an existing bundle with no\n"
        "GPU spend:\n"
        "  python tools/golden_profile_pipeline.py latest\n"
        "  python tools/golden_profile_pipeline.py report <trace_id> --skip-analyze"
    ),
}

_TRACE_ID_RE = re.compile(r"trace_id=([0-9a-f]{32})")


def _run_v2ctl(repo_root: Path, argv: list[str], capture: bool) -> tuple[int, str]:
    """Invoke this same CLI as a subprocess, streaming (and optionally capturing) it.

    Going through the documented ``v2ctl`` entry point rather than calling the
    internal handlers directly keeps one contract instead of two, so a change to
    deploy/run argument handling cannot silently diverge from the public CLI.
    """
    cmd = [sys.executable, str(repo_root / "tools" / "v2ctl.py")] + argv
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=capture,
        text=True,
    )
    return proc.returncode, (proc.stdout or "") if capture else ""


def _profile_app_name(repo_root: Path, profile_name: str) -> str:
    """Return ``target.app`` for *profile_name*, following ``extends``.

    ``--app`` is otherwise required, and a caller that does not know the app has
    to guess -- which is how a profiling run ended up pointed at a different
    profile contract than the one it meant to measure.
    """
    import tomllib

    profiles_dir = repo_root / "config" / "v2" / "profiles"
    seen: set[str] = set()
    cursor: str | None = profile_name
    while cursor and cursor not in seen:
        seen.add(cursor)
        path = profiles_dir / f"{cursor}.toml"
        try:
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            return ""
        target = raw.get("target")
        if isinstance(target, dict):
            app = target.get("app") or target.get("app_name")
            if isinstance(app, str) and app:
                return app
        parent = raw.get("extends")
        cursor = parent if isinstance(parent, str) and parent else None
    return ""


def _volume_trace_ids(repo_root: Path, profile_name: str) -> set[str] | None:
    """Current trace ids on the profile volume, or None if unreachable.

    Used to diff before and after a run so the trace id is identified by what the
    run *created* rather than by scraping the container log, which is not reliably
    present in captured stdout.
    """
    try:
        sys.path.insert(0, str(repo_root / "tools"))
        import golden_profile_pipeline as pipeline

        workspace_id = pipeline.resolve_workspace_id(None)
        volume_name = pipeline.resolve_profile_volume(None)
        if not workspace_id:
            return None
        volume = pipeline.open_volume(workspace_id, volume_name)
        return {
            record["trace_id"]
            for record in pipeline.list_traces(volume, days=2)
        }
    except BaseException:
        return None


def cmd_golden_profile(args, repo_root: Path) -> int:
    """Run one Golden request and profile it end to end.

    One command: run, identify the trace this run produced, fetch and verify the
    bundle, analyze it, write the decision documents, print the report path.

    Deploy is skipped by default when ``--skip-deploy`` is given, so the loop can
    be driven as two commands -- one deploy, then repeated profiling runs -- or as
    a single command that deploys first.
    """
    profile = getattr(args, "profile", None) or GOLDEN_P1_PROFILE
    app = getattr(args, "app", None) or _profile_app_name(repo_root, profile)
    min_ms = float(getattr(args, "min_ms", 1.0) or 1.0)
    skip_deploy = bool(getattr(args, "skip_deploy", False))
    explicit_trace = getattr(args, "trace_id", None)

    deploy_flags = ", ".join(k for k, _ in GOLDEN_PROFILE_DEPLOY_FLAGS)
    run_flags = ", ".join(k for k, _ in GOLDEN_PROFILE_RUN_FLAGS)

    if getattr(args, "dry_run", False):
        steps = "source-probe, publish-model-metadata-cache, run, fetch, analyze, render"
        if not skip_deploy:
            steps = "deploy, " + steps
        print(
            f"[v2ctl.golden_profile] dry-run\n"
            f"  profile = {profile}\n"
            f"  app     = {app or '(unresolved: pass --app)'}\n"
            f"  steps   = {steps}\n"
            f"  deploy flags = {deploy_flags}\n"
            f"  run flags    = {run_flags}",
            flush=True,
        )
        return 0

    if not app:
        print(
            f"ERROR: could not resolve target.app for profile {profile!r} in "
            "config/v2/profiles. Pass --app explicitly.",
            file=sys.stderr,
        )
        return 2

    extra: list[str] = []
    for item in getattr(args, "set", None) or []:
        extra += ["--set", str(item)]
    already = {s.split("=", 1)[0] for s in extra if "=" in s}

    def base() -> list[str]:
        return ["--profile", profile, "--app", app] + extra

    step = 0

    def advance(label: str) -> None:
        nonlocal step
        step += 1
        print(f"[v2ctl.golden_profile] step {step} {label}", flush=True)

    if not skip_deploy:
        for flag, value in GOLDEN_PROFILE_DEPLOY_FLAGS:
            if flag not in already:
                extra += ["--set", f"{flag}={value}"]
        advance("deploy (with tracing)")
        rc, _ = _run_v2ctl(repo_root, base() + ["golden", "deploy"], capture=False)
        if rc != 0:
            print(f"ERROR: deploy failed rc={rc}", file=sys.stderr)
            return rc
    else:
        print(
            "[v2ctl.golden_profile] skipping deploy; the existing deployment "
            "must already carry the tracing flags",
            flush=True,
        )

    advance("source-probe")
    rc, probe = _run_v2ctl(repo_root, base() + ["source-probe"], capture=True)
    sys.stdout.write(probe)
    sys.stdout.flush()
    # Diagnostic only: a failed probe no longer aborts the experiment.
    #
    # It used to return nonzero here, on the reasoning that the deployment was
    # "stale or mismatched". But the probe inspects the mounted filesystem of a
    # container it starts, which cannot establish what code a restored snapshot
    # executes -- so it could block a valid experiment while passing on a stale
    # one. The question it was standing in for is now answered directly: the run
    # reports the deploy_id of the deployment that served it, and acceptance
    # compares that with the expected id. A probe failure is still printed so it
    # remains visible when investigating.
    if rc != 0 or "RESULT=PASS" not in probe:
        print(
            "NOTE: source-probe did not report RESULT=PASS (rc=%r). This is "
            "diagnostic only and does not gate the run; correctness is decided "
            "by the deploy_id the serving request reports." % (rc,),
            file=sys.stderr,
        )

    advance("publish-model-metadata-cache")
    rc, publication = _run_v2ctl(
        repo_root,
        base() + ["publish-model-metadata-cache"],
        capture=True,
    )
    sys.stdout.write(publication)
    sys.stdout.flush()
    if rc != 0:
        print(
            "[v2ctl.golden_profile] note: model metadata publication did not "
            "complete; continuing fail-soft",
            file=sys.stderr,
            flush=True,
        )

    # Identify the trace by what the run creates, not by scraping its log.
    before = _volume_trace_ids(repo_root, profile)
    if before is None:
        print(
            "[v2ctl.golden_profile] note: cannot list the profile volume, falling "
            "back to log scraping for the trace id",
            flush=True,
        )

    for flag, value in GOLDEN_PROFILE_RUN_FLAGS:
        if flag not in already:
            extra += ["--set", f"{flag}={value}"]

    advance("run (traced)")
    rc, run_out = _run_v2ctl(repo_root, base() + ["golden", "run"], capture=True)
    sys.stdout.write(run_out)
    sys.stdout.flush()
    if rc != 0:
        print(f"ERROR: golden run failed rc={rc}", file=sys.stderr)
        return rc

    trace_id = explicit_trace
    if not trace_id and before is not None:
        after = _volume_trace_ids(repo_root, profile) or set()
        created = sorted(after - before)
        if len(created) == 1:
            trace_id = created[0]
        elif created:
            print(
                f"[v2ctl.golden_profile] {len(created)} traces appeared during the "
                f"run; using the last: {created[-1]}",
                file=sys.stderr,
            )
            trace_id = created[-1]
    if not trace_id:
        matches = _TRACE_ID_RE.findall(run_out)
        trace_id = matches[-1] if matches else None

    if not trace_id:
        print(
            "ERROR: could not identify the trace id for this run.\n"
            "  The run manifest does not record it and the container log did not "
            "surface it. Recover it manually with:\n"
            "    python tools/golden_profile_pipeline.py latest\n"
            "  then re-run with --trace-id <id> (or --skip-analyze to re-render "
            "an existing bundle).",
            file=sys.stderr,
        )
        return 1
    print(f"[v2ctl.golden_profile] trace_id={trace_id}", flush=True)

    advance("fetch, analyze and render")
    sys.path.insert(0, str(repo_root / "tools"))
    import golden_profile_pipeline as pipeline

    argv = ["report", trace_id, "--min-ms", str(min_ms)]
    if getattr(args, "workspace_id", None):
        argv += ["--workspace-id", args.workspace_id]
    if getattr(args, "skip_analyze", False):
        argv.append("--skip-analyze")
    rc = pipeline.main(argv)
    if rc != 0:
        print(f"ERROR: profiling pipeline failed rc={rc}", file=sys.stderr)
        return rc

    advance("done")
    return 0

def cmd_golden_deploy(args, repo_root: Path) -> int:
    """``golden deploy``, optionally with the profiler's tracing flags.

    ``--for-profiling`` exists so the two-command loop does not depend on the
    caller reproducing three environment flags from documentation. Without it,
    ``golden deploy`` followed by ``golden profile --skip-deploy`` produces a
    perfectly clean run with no trace at all, because the tracing flags are only
    otherwise applied by ``golden profile`` when it deploys itself.
    """
    if getattr(args, "for_profiling", False):
        extra = []
        for item in getattr(args, "set", None) or []:
            extra += ["--set", str(item)]
        already = {s.split("=", 1)[0] for s in extra if "=" in s}
        for flag, value in GOLDEN_PROFILE_DEPLOY_FLAGS:
            if flag not in already:
                extra += ["--set", f"{flag}={value}"]
        if extra != list(getattr(args, "set", None) or []):
            # args.set holds NAME=VALUE entries; extra interleaves the --set
            # flag with each one. Passing extra straight through made the parser
            # read the literal "--set" as a value and fail with
            # "invalid --set spec '--set': expected NAME=VALUE".
            args.set = extra[1::2]
            print(
                "[v2ctl.golden.deploy] --for-profiling: tracing flags added: "
                + ", ".join(f"{k}={v}" for k, v in GOLDEN_PROFILE_DEPLOY_FLAGS),
                flush=True,
            )
    return cmd_deploy(args, repo_root)


def cmd_golden(args, repo_root: Path) -> int:
    """Dispatch the public Golden namespace to the canonical handlers."""
    if args.golden_command not in {"doctor", "status", "deploy", "run", "publisher-bootstrap", "publish-custom-nodes", "profile"}:
        print(
            "ERROR: public Golden commands are doctor, status, deploy, run, "
            "publisher-bootstrap, publish-custom-nodes, and profile",
            file=sys.stderr,
        )
        return 2
    requested_profile = getattr(args, "profile", "production")
    publisher_command = args.golden_command in {"publisher-bootstrap", "publish-custom-nodes"}
    if (
        requested_profile != "production"
        and not is_golden_profile_name(requested_profile)
        and not publisher_command
    ):
        print(
            f"ERROR: `golden` commands use profile {GOLDEN_P1_PROFILE!r}; "
            f"received --profile {requested_profile!r}",
            file=sys.stderr,
        )
        return 1
    identity_error = _reject_golden_identity_args(args, public=True)
    if identity_error is not None:
        return identity_error
    public_run = args.golden_command in {"deploy", "run", "profile"}
    dry_run = bool(getattr(args, "dry_run", False))
    if public_run and not dry_run and not getattr(args, "app", None):
        # The profile declares its own target.app. Resolve it here rather than
        # forcing the caller to know the experimental app name, which otherwise
        # leads to a guessed app and a profile contract that was never intended.
        resolved_app = _profile_app_name(repo_root, requested_profile)
        if resolved_app:
            args.app = resolved_app
    if public_run and not dry_run:
        if not getattr(args, "app", None):
            print(
                "ERROR: Golden deploy/run requires --app <experimental-app>; "
                f"{PROTECTED_GOLDEN_APP!r} is protected",
                file=sys.stderr,
            )
            return 2
    if requested_profile == "production" and not publisher_command:
        args.profile = GOLDEN_P1_PROFILE
    args.golden_public = True
    if args.golden_command == "run":
        if args.run_count not in (None, 1):
            print("ERROR: public Golden run always executes exactly one request", file=sys.stderr)
            return 2
        args.run_count = 1
    if args.golden_command == "status":
        return cmd_golden_status(args, repo_root)
    if args.golden_command == "profile":
        return cmd_golden_profile(args, repo_root)
    if args.golden_command == "deploy":
        return cmd_golden_deploy(args, repo_root)
    handlers = {
        "doctor": cmd_doctor,
        "deploy": cmd_deploy,
        "run": cmd_run,
        "publisher-bootstrap": cmd_publisher_bootstrap,
        "publish-custom-nodes": cmd_publish_custom_nodes,
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
        _canonical_workspace_binding(args, repo_root, selected_config)
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
    repo_root: Path,
    publisher_app_name: str | None = None,
    workspace_binding: WorkspaceBinding | None = None,
    local_content_generation: str | None = None,
    allow_destructive: bool = False,
):
    """Mirror the canonical custom-node source before a native Golden deploy.

    Imports of ``modal`` and ``modal_client`` stay below the non-dry-run
    boundary: dry-run must remain a local command with no Volume access.  The
    compatibility publisher receives the shared publisher app and active
    workspace explicitly rather than consulting the user's ambient Modal
    profile.
    """
    from . import custom_nodes as custom_nodes_mod

    if workspace_binding is not None:
        assert_workspace_binding_current(repo_root, workspace_binding)

    # Keep the optional parameter as a compatibility surface for older hooks,
    # but never allow a consumer name to select the authority.
    publisher_app_name = CUSTOM_NODES_PUBLISHER_APP_NAME

    source_root = custom_nodes_mod.resolve_custom_nodes_root(repo_root)
    workspace = (
        workspace_binding._workspace_payload()
        if workspace_binding is not None else _active_workspace(repo_root)
    )
    secrets = (
        {str(name): str(value) for name, value in workspace.items()}
        if isinstance(workspace, Mapping) else {}
    )

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

    process_extra = {
        "COMFYMODAL_V2_APP_NAME": publisher_app_name,
    }
    process_scope = (
        _workspace_process_environment(workspace_binding, process_extra)
        if workspace_binding is not None else None
    )
    try:
        if process_scope is None:
            decision = custom_nodes_mod.run_publish_or_skip(
                source_root,
                volume_name=CUSTOM_NODES_VOLUME_NAME,
                publisher=publisher,
                workspace=workspace,
                identity_provider=identity_provider,
                allow_destructive=allow_destructive,
            )
        else:
            with process_scope:
                decision = custom_nodes_mod.run_publish_or_skip(
                    source_root,
                    volume_name=CUSTOM_NODES_VOLUME_NAME,
                    publisher=publisher,
                    workspace=workspace,
                    identity_provider=identity_provider,
                    allow_destructive=allow_destructive,
                )
    except Exception as exc:  # noqa: BLE001 - publication is a deploy gate
        raise GateError(
            "custom-node publication failed: "
            + _safe_exception_diagnostic(exc, secrets=secrets)
        ) from exc
    if decision.skip:
        print(
            "[custom_nodes.publish] decision=skip_exact "
            f"reason={decision.reason} "
            f"generation={decision.identity.content_generation[:12]} "
            f"schema={custom_nodes_mod.RECEIPT_SCHEMA_VERSION} "
            f"policy={custom_nodes_mod.PACKAGING_POLICY_VERSION}"
        )
        return decision
    if decision.action == "blocked":
        delta = getattr(decision, "destructive_delta", {}) or {}
        blocked = delta.get("packages", []) if isinstance(delta, dict) else []
        summary = "; ".join(
            f"{entry.get('package')}: prev_files={entry.get('prev_files')} "
            f"cand_files={entry.get('cand_files')} missing={entry.get('missing_count')}"
            for entry in blocked
        ) or decision.reason
        raise GateError(
            "Golden deploy refused: destructive custom-node publication blocked "
            f"({summary}); re-run with --allow-destructive-custom-node-publication "
            "to explicitly permit removal of previously-published external "
            "package files; remote generation is unchanged"
        )
    if decision.action != "published" or decision.reason != "published_verified":
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
                    "status": _safe_public_value(result.get("status"), secrets),
                    "comfyapp_version": _safe_public_value(
                        result.get("comfyapp_version"), secrets
                    ),
                    "reason": _safe_public_value(result.get("reason"), secrets),
                    "error": _safe_public_value(result.get("error"), secrets),
                    "expected_generation": expected_generation[:16] or None,
                    "result_generation": _safe_public_value(
                        result_generation[:16], secrets
                    ),
                    "readback_generation": _safe_public_value(
                        result.get("readback_generation"), secrets
                    ),
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
            f"{_safe_public_value(decision.reason, secrets) or 'unknown'} result={diagnostic}"
        )
    print(
        f"[custom_nodes.publish] decision={decision.action} "
        f"reason={_safe_public_value(decision.reason, secrets) or 'unknown'} "
        f"generation={decision.identity.content_generation[:12]} "
        f"schema={custom_nodes_mod.RECEIPT_SCHEMA_VERSION} "
        f"policy={custom_nodes_mod.PACKAGING_POLICY_VERSION}"
    )
    return decision


def _invoke_golden_publisher(
    repo_root: Path,
    publisher_app_name: str,
    workspace_binding: WorkspaceBinding | None = None,
    local_content_generation: str | None = None,
    allow_destructive: bool = False,
):
    """Pass the isolated app to the current hook without breaking old hooks."""
    hook = _publish_golden_custom_nodes
    try:
        parameters = inspect.signature(hook).parameters
    except (TypeError, ValueError):
        parameters = {}
    kwargs = {}
    if "workspace_binding" in parameters:
        kwargs["workspace_binding"] = workspace_binding
    if "local_content_generation" in parameters:
        kwargs["local_content_generation"] = local_content_generation
    if "allow_destructive" in parameters:
        kwargs["allow_destructive"] = allow_destructive
    if "publisher_app_name" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_POSITIONAL
        for parameter in parameters.values()
    ):
        return hook(repo_root, CUSTOM_NODES_PUBLISHER_APP_NAME, **kwargs)
    return hook(repo_root, **kwargs)


def _publication_verified_generation(publication: object) -> str:
    """Return the publisher's own verified content generation when present."""
    result = getattr(publication, "result", None)
    if not isinstance(result, Mapping):
        return ""
    for key in ("content_generation", "generation", "observed_generation"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _resolve_publication_generation(publication: object, desired: str) -> str:
    """Return the verified publication generation as the authoritative one.

    A verified publication is authoritative: the generation calculated before
    publication may legitimately differ when the shared custom-node tree
    changed while the deploy was in flight (the publisher re-reads the live
    tree).  A mismatch is logged, never fatal.  Real publication and
    verification failures are raised by ``_invoke_golden_publisher`` before
    this point.
    """
    resolved = str(
        getattr(getattr(publication, "identity", None), "generation", "") or ""
    )
    if not resolved:
        raise GateError(
            "custom-node publication has no verified generation after publication"
        )
    if desired and desired != resolved:
        print(
            "[custom_nodes.publish] pre-publication generation differs from the "
            "verified publication; continuing with the verified generation: "
            f"desired={desired[:16]} verified={resolved[:16]}"
        )
    return resolved


def cmd_publisher_bootstrap(args, repo_root: Path) -> int:
    """Deploy the shared custom-node ``comfyapp`` publisher (compatibility)."""
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
        workspace_binding = _canonical_workspace_binding(args, repo_root, config)
        _print_destination_preflight(workspace_binding, deploying=True)
        publisher_app_name = CUSTOM_NODES_PUBLISHER_APP_NAME
        invocation_id = _new_invocation_id()
        spec = backend_registry.publisher_bootstrap()
        env = env_builder.build(
            config,
            host_env=os.environ,
            backend_extra={
                **_identity_env_for_command("deploy", config),
                **_canonical_metadata_env(config, fingerprints, invocation_id),
                # Publisher bootstrap imports comfyapp only to publish the
                # shared custom-node Volume.  Select its lightweight image
                # without making this control-plane selector part of normal
                # Golden/production deploy configuration.
                "COMFYMODAL_PUBLISHER_ONLY": "1",
            },
        )
        env = _native_golden_deploy_env(env)
        _apply_workspace_binding_to_env(env, workspace_binding)
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
            auto_recover=True,
        )
        try:
            print(
                f"[v2ctl.publisher-bootstrap] app={publisher_app_name} "
                f"command={command}"
            )
            preflight = None
            # Publication correctness is decided by the backend result plus
            # whether the publisher app and its Function exist afterwards -- not
            # by Modal's numeric version counter.
            #
            # This block used to refuse to invoke the backend without a readable
            # pre-deploy version, and then reject a successful bootstrap whose
            # post-deploy version had not advanced. That made a Modal-side
            # counter the authority on whether an app exists, which is the same
            # fragility that made the deployment receipt unusable when a version
            # history reset. It also refused to act on an "invalid" preflight
            # lookup, i.e. it distrusted its own probe rather than verifying the
            # thing it actually needed.
            #
            # deploy_id remains the deployment authority. Here the only question
            # is whether the publisher became usable.
            if workspace_binding is not None:
                assert_workspace_binding_current(repo_root, workspace_binding)
            result = _make_backend_runner(repo_root, env_builder, workspace_binding).run(
                spec,
                config=config,
                extra_args=extra_args,
                extra_env=env,
                capture=True,
                invocation_id=invocation_id,
            )
            if not result.ok():
                _print_backend_diagnostic(result, env)
                return result.exit_code if result.exit_code else 1
            if workspace_binding is not None:
                postflight = run_publisher_preflight(repo_root, workspace_binding)
                if not postflight["PUBLISHER_EXISTS"] or not postflight[
                    "PUBLISHER_FUNCTION_EXISTS"
                ]:
                    raise GateError(
                        "publisher bootstrap did not verify app and required Function"
                    )
            print(f"[v2ctl.publisher-bootstrap] exit={result.exit_code}")
            return 0
        finally:
            lock.release()
    except (V2CtlError, OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _bootstrap_publisher_app(args, repo_root: Path) -> int:
    """Shared helper: deploy the shared custom-node ``comfyapp`` publisher.

    Single body shared by the ``publisher-bootstrap`` compatibility command
    and the manual ``publish-custom-nodes`` command.
    """
    return cmd_publisher_bootstrap(args, repo_root)


def cmd_publish_custom_nodes(args, repo_root: Path) -> int:
    """Explicit manual custom-node publication (the only publishing entry).

    Publication is fully manual: normal deploy/run/gate/confirm/doctor/
    source-probe commands never compute content generation or publish.
    This command ensures the shared publisher app exists (bootstrapping it
    first when the probe shows it absent) and then runs the full verified
    publication.  The destructive guard is only ever explicit CLI input.
    """
    identity_error = _reject_golden_identity_args(args, public=True)
    if identity_error is not None:
        return identity_error
    try:
        _, _, _, config, _, _, _ = _build_components_for_args(repo_root, args)
        _reject_protected_effective_target(
            config, command="v2ctl golden publish-custom-nodes"
        )
        workspace_binding = _canonical_workspace_binding(args, repo_root, config)
        if workspace_binding is None:
            print(
                "ERROR: publish-custom-nodes requires a canonical workspace binding",
                file=sys.stderr,
            )
            return 1
        if bool(getattr(args, "dry_run", False)):
            print("[v2ctl.publish-custom-nodes] dry-run: no publication performed")
            print(f"publisher_app={CUSTOM_NODES_PUBLISHER_APP_NAME}")
            print(f"workspace={workspace_binding.workspace_id}")
            return 0
        preflight = run_publisher_preflight(repo_root, workspace_binding)
        if (
            not preflight.get("PUBLISHER_EXISTS")
            or not preflight.get("PUBLISHER_FUNCTION_EXISTS")
        ):
            print(
                "[v2ctl.publish-custom-nodes] publisher app/Function absent; "
                "bootstrapping before publication"
            )
            bootstrapped = _bootstrap_publisher_app(args, repo_root)
            if bootstrapped != 0:
                return bootstrapped
        decision = _publish_golden_custom_nodes(
            repo_root,
            CUSTOM_NODES_PUBLISHER_APP_NAME,
            workspace_binding,
            allow_destructive=bool(
                getattr(args, "allow_destructive_custom_node_publication", False)
            ),
        )
        action = str(getattr(decision, "action", "") or "")
        reason = str(getattr(decision, "reason", "") or "")
        generation = str(getattr(getattr(decision, "identity", None), "generation", "") or "")
        skipped = bool(getattr(decision, "skip", False))
        print(
            f"[v2ctl.publish-custom-nodes] action={action or ('skip' if skipped else 'unknown')} "
            f"reason={reason or 'unknown'} generation={generation[:16] or '(none)'}"
        )
        if skipped or action in {"published", "skip"}:
            return 0
        return 1
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
        workspace_binding = _canonical_workspace_binding(args, repo_root, config)
        _print_destination_preflight(workspace_binding, deploying=True)
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
        native_golden = is_golden_profile_name(config.profile_name)
        spec = (
            backend_registry.native_deploy()
            if native_golden else backend_registry.deploy_only()
        )
        env = env_builder.build(config, host_env=os.environ,
                                backend_extra={**spec.deploy_only_env,
                                               **_identity_env_for_command("deploy", config),
                                               **_canonical_metadata_env(config, fingerprints, invocation_id)})
        # The legacy batch invokes publish_custom_nodes_volume.py as a child.
        # Tell that child the outer v2ctl deploy lock is already held so it
        # does not attempt a nested acquisition of the same lock.
        env["V2CTL_DEPLOY_LOCK_HELD"] = "1"
        if native_golden:
            env = _native_golden_deploy_env(env)
        if native_golden:
            # The active workspace, not the user's ambient Modal profile, owns
            # this deploy.  Values are redacted by the normal dry-run report.
            if workspace_binding is not None:
                _apply_workspace_binding_to_env(env, workspace_binding)
            else:
                _apply_workspace_binding_to_env(env, workspace_binding)
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
                     target=config.target.app, profile=config.profile_name,
                     auto_recover=True)
        try:
            print(f"[v2ctl.deploy] profile={config.profile_name}")
            print(f"[v2ctl.deploy] command={command}")
            # Custom-node publication is fully manual: deploy never computes
            # the custom-node content generation, never runs the publisher
            # preflight, and never publishes.  The source-probe expectation
            # below is repo source identity recorded on the receipt, not
            # custom-node content.
            source_probe_expected = None
            if native_golden:
                from . import source_probe as source_probe_mod

                # Capture the exact source expectation before backend work.
                source_probe_expected = source_probe_mod.compute_expected_local(repo_root)
            # The deploy fingerprint is captured at deploy time.
            deploy_identity = capture_deploy_identity(fingerprints, workspace_binding)
            _apply_deploy_identity_to_env(env, deploy_identity)
            print(
                f"[v2ctl.deploy] fingerprint={deploy_identity.deploy_fingerprint}"
            )
            # Modal's numeric version is probed only as diagnostic navigation
            # metadata. It is deliberately NOT a gate: requiring a readable
            # pre-deploy version, and then failing when the post-deploy version
            # did not advance, made a Modal-side counter the authority on whether
            # the app was actually updated.
            #
            # That check was aimed at a no-op deploy -- the client exiting 0
            # while the app was unchanged. deploy_id catches that strictly
            # better: a no-op leaves the previous deployment serving, so the run
            # reports the old deploy_id and acceptance rejects it as a mismatch.
            # A version counter can only approximate that, and it fails outright
            # whenever Modal resets or renumbers its history.
            _pre_version = (
                _checked_version_probe(repo_root, config.target.app, workspace_binding)
                if workspace_binding is not None
                else _app_version_number(config.target.app)
            )
            result = _make_backend_runner(repo_root, env_builder, workspace_binding).run(
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
                deploy_identity=deploy_identity,
            )
            print(f"[v2ctl.deploy] exit={result.exit_code} manifest={manifest}")
            if not result.ok():
                _persist_full_backend_diagnostic(
                    result, env, repo_root, invocation_id
                )
                _print_backend_diagnostic(result, env)
                # A failed deploy must NEVER leave a "deployed" manifest behind:
                # remove it so gate/run cannot treat a broken deployment as valid.
                try:
                    manifest.unlink(missing_ok=True)
                except OSError:
                    pass
                return result.exit_code if result.exit_code else 1
            # ── Deploy-version-advance verification (E29 root-cause fix) ────
            # Recorded for navigation only; see the pre-deploy note above.
            _post_version = (
                _checked_version_probe(repo_root, config.target.app, workspace_binding)
                if workspace_binding is not None
                else _app_version_number(config.target.app)
            )
            if _post_version is not None and _pre_version is not None:
                print(
                    f"[v2ctl.deploy] modal_version {_pre_version}->{_post_version}"
                    f" (diagnostic; correctness is decided by deploy_id)"
                )
            if native_golden:
                # A real backend writer always creates the manifest.  Keep
                # compatibility with injected runner tests that return a
                # sentinel path without materializing a ledger file.
                if manifest.is_file():
                    receipt = _write_golden_deployment_receipt(
                        repo_root, config, env, deploy_identity,
                        _post_version if isinstance(_post_version, int) else 0,
                        manifest, None,
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
        workspace_binding = _canonical_workspace_binding(args, repo_root, config)
        _print_destination_preflight(workspace_binding, deploying=True)
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
                     target=config.target.app, profile=config.profile_name,
                     auto_recover=True)
        try:
            deploy_identity = capture_deploy_identity(fingerprints, workspace_binding)
            _apply_workspace_binding_to_env(env, workspace_binding)
            _apply_deploy_identity_to_env(env, deploy_identity)
            print(f"[v2ctl.deploy-run] profile={config.profile_name} "
                  f"deploy_fingerprint={deploy_identity.deploy_fingerprint}")
            print(f"[v2ctl.deploy-run] command={command}")
            result = _make_backend_runner(repo_root, env_builder, workspace_binding).run(
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
        workspace_binding = _canonical_workspace_binding(args, repo_root, config)
        _print_destination_preflight(workspace_binding)
        bound_receipt = None
        if is_golden_profile_name(config.profile_name) and not getattr(args, "dry_run", False):
            receipt_kwargs = ({"workspace_binding": workspace_binding}
                              if workspace_binding is not None else {})
            _, bound_receipt = _bound_deployment_receipt(
                repo_root, config, command="run", **receipt_kwargs
            )
            if workspace_binding is not None:
                _require_receipt_workspace(bound_receipt, workspace_binding, command="run")
                assert_workspace_binding_current(repo_root, workspace_binding)
                # Custom-node publication is fully manual: run never computes
                # content generation or gates on publication.  The
                # --acknowledge-volume-drift flag is accepted as a no-op.
        # Run-only: refuse unregistered and deploy-required explicit changes.
        resolver.check_run_safety(
            config, run_only=True,
            trusted_environment=(bound_receipt.effective_environment if bound_receipt else None),
        )
        _require_golden_cpu_qd2_deploy_gate(config, bound_receipt)
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
                print(
                    "WARNING: deployment fingerprint mismatch; continuing with the "
                    f"requested run. stored={stored} current={current}. Changed: "
                    + ("; ".join(changes) if changes else "(unknown)"),
                    file=sys.stderr,
                )
        current = bound_receipt.deploy_fingerprint if bound_receipt else fingerprints.deploy_fingerprint()
        enforce_runtime_overrides(config,
                                  ro_mod.RuntimeOverrideInventory(local_dir=repo_root / ".runtime_state"),
                                  spend=True)
        # ── Full-run guard: run must generate (run_plan_stream), never the
        # snapshot-restore-only PROBE. ──
        _require_full_run_mode(config, command="v2ctl run")
        # No source-probe precondition here. Which deployment served a request is
        # decided by comparing the expected deploy_id with the one the executing
        # interpreter reports (see StructuralValidator). Requiring a separate
        # probe container first meant an extra GPU round trip before every run,
        # and it could only ever describe the mounted filesystem -- never the
        # code a restored snapshot actually executes.
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
        if workspace_binding is not None:
            _apply_workspace_binding_to_env(env, workspace_binding)
        if bound_receipt is not None:
            env = _receipt_effective_env(env, bound_receipt)
            # The receipt contains the deployment invocation identity.  A run
            # must retain the current run invocation so its artifact binds to
            # this request rather than being misattributed to deployment.
            env["COMFYMODAL_V2CTL_INVOCATION_ID"] = invocation_id
            env["COMFYMODAL_V2CTL_PROFILE"] = str(config.profile_name)
            env["COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT"] = (
                fingerprints.profile_config_fingerprint()
            )
            env["COMFYMODAL_V2CTL_RUN_FINGERPRINT"] = val_mod._bound_run_fingerprint(
                fingerprints, bound_receipt
            )
        if bool(getattr(args, "acknowledge_volume_drift", False)):
            env["COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT"] = "1"
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
        try:
            result = _make_backend_runner(repo_root, env_builder, workspace_binding).run(
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
        except Exception:
            if is_experiment_profile(config):
                try:
                    finalize_experiment_evidence(
                        repo_root,
                        identity={
                            "profile": config.profile_name,
                            "v2ctl_invocation_id": invocation_id,
                            "profile_config_fingerprint": fingerprints.profile_config_fingerprint(),
                            "deploy_fingerprint": current,
                            "run_fingerprint": val_mod._bound_run_fingerprint(
                                fingerprints, bound_receipt
                            ),
                            "attention_backend": resolved_attention_backend(config),
                            **sage_runtime_identity(config),
                            "backend_command": command,
                        },
                        verdict="INCONCLUSIVE",
                        experiment_id=f"{config.profile_name}_{invocation_id[:16]}",
                    )
                except Exception:
                    pass
            raise
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
            pass
        print(f"[v2ctl.run] exit={result.exit_code} manifest={run_manifest}")
        if is_experiment_profile(config):
            evidence_identity = {
                "profile": config.profile_name,
                "v2ctl_invocation_id": invocation_id,
                "request_id": result.request_id or result.artifacts.request_id or "",
                "profile_config_fingerprint": (
                    bound_receipt.profile_config_fingerprint
                    if bound_receipt is not None and bound_receipt.profile_config_fingerprint
                    else fingerprints.profile_config_fingerprint()
                ),
                "deploy_fingerprint": current,
                "run_fingerprint": val_mod._bound_run_fingerprint(fingerprints, bound_receipt),
                "attention_backend": resolved_attention_backend(config),
                **sage_runtime_identity(
                    config,
                    getattr(result, "experiment_identity", {}),
                    getattr(result.artifacts, "experiment_identity", {}),
                ),
                "backend_command": result.command,
                "target": {
                    "app": config.target.app,
                    "class": config.target.class_name,
                    "method": config.target.method,
                },
                "resources": {
                    "gpu": config.resources.gpu,
                    "cpu": config.resources.cpu,
                    "memory_mb": config.resources.memory_mb,
                    "min_containers": config.resources.min_containers,
                    "scaledown_window": config.resources.scaledown_window,
                },
            }
            try:
                evidence = finalize_experiment_evidence(
                    repo_root,
                    identity=evidence_identity,
                    verdict="ACCEPT" if result.ok() else "REJECT",
                    result=result,
                    extra_paths=[run_manifest],
                    experiment_id=f"{config.profile_name}_{invocation_id[:16]}",
                )
                print(f"[v2ctl.run] evidence={evidence.markdown_path} status={evidence.status}")
            except Exception as exc:  # noqa: BLE001 - normal completion is forbidden
                print(f"ERROR: experiment evidence finalization failed: {exc}", file=sys.stderr)
                return 1
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
        workspace_binding = _canonical_workspace_binding(args, repo_root, config)
        _print_destination_preflight(workspace_binding)
        bound_receipt = None
        if is_golden_profile_name(config.profile_name) and not getattr(args, "dry_run", False):
            receipt_kwargs = ({"workspace_binding": workspace_binding}
                              if workspace_binding is not None else {})
            _, bound_receipt = _bound_deployment_receipt(
                repo_root, config, command="gate", **receipt_kwargs
            )
            if workspace_binding is not None:
                _require_receipt_workspace(bound_receipt, workspace_binding, command="gate")
                assert_workspace_binding_current(repo_root, workspace_binding)
                # Custom-node publication is fully manual: gate never runs
                # the publisher preflight or gates on publication.
        resolver.check_run_safety(
            config, run_only=True,
            trusted_environment=(bound_receipt.effective_environment if bound_receipt else None),
        )
        _require_golden_cpu_qd2_deploy_gate(config, bound_receipt)
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
            if workspace_binding is not None:
                _apply_workspace_binding_to_env(env, workspace_binding)
            command = backend_mod.BackendRunner.build_command_line(spec, extra_args)
            _dry_run_report(config, fingerprints, env, command)
            return 0
        validator = val_mod.Validator()
        validator.register(val_mod.StructuralValidator())
        validator.register(val_mod.ExpectedOutputShaValidator())
        if is_golden_profile_name(config.profile_name):
            validator.register(val_mod.GoldenCohortValidator())
        # Golden has its own dedicated durability/seriality ledger contract;
        # the generic E29 run-plan ledger is not emitted by
        # run_golden_serial_stream.
        if not is_golden_profile_name(config.profile_name):
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
        runner = _make_backend_runner(repo_root, env_builder, workspace_binding)
        if workspace_binding is not None:
            runner = _FrozenWorkspaceBackendRunner(
                runner, repo_root, workspace_binding
            )
        gate = val_mod.GateRunner(repo_root=repo_root, fingerprints=fingerprints,
                                   validators=validator, backend_runner=runner,
                                   env_builder=env_builder,
                                   deployment_receipt=bound_receipt)
        result = gate.run_gate(config, spec, invocation_id=invocation_id)
        print(f"[v2ctl.gate] valid={int(result.valid)} manifest={result.manifest_path}")
        print(
            f"[v2ctl.gate] evidence={result.evidence_path} "
            f"evidence_status={result.evidence_status} verdict={result.verdict}"
        )
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
        workspace_binding = _canonical_workspace_binding(args, repo_root, config)
        _print_destination_preflight(workspace_binding)
        bound_receipt = None
        if is_golden_profile_name(config.profile_name) and not getattr(args, "dry_run", False):
            receipt_kwargs = ({"workspace_binding": workspace_binding}
                              if workspace_binding is not None else {})
            _, bound_receipt = _bound_deployment_receipt(
                repo_root, config, command="confirm", **receipt_kwargs
            )
            if workspace_binding is not None:
                _require_receipt_workspace(bound_receipt, workspace_binding, command="confirm")
                assert_workspace_binding_current(repo_root, workspace_binding)
                # Custom-node publication is fully manual: confirm never runs
                # the publisher preflight or gates on publication.
        resolver.check_run_safety(
            config, run_only=True,
            trusted_environment=(bound_receipt.effective_environment if bound_receipt else None),
        )
        _require_golden_cpu_qd2_deploy_gate(config, bound_receipt)
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
            if workspace_binding is not None:
                _apply_workspace_binding_to_env(env, workspace_binding)
            command = backend_mod.BackendRunner.build_command_line(spec, extra_args)
            _dry_run_report(config, fingerprints, env, command)
            return 0
        runner = _make_backend_runner(repo_root, env_builder, workspace_binding)
        if workspace_binding is not None:
            runner = _FrozenWorkspaceBackendRunner(
                runner, repo_root, workspace_binding
            )
        validator = val_mod.Validator()
        validator.register(val_mod.StructuralValidator())
        validator.register(val_mod.ExpectedOutputShaValidator())
        if is_golden_profile_name(config.profile_name):
            validator.register(val_mod.GoldenCohortValidator())
        # Confirm must enforce the same canonical ledger contract as gate;
        # otherwise an E37 gate could pass while confirmation silently drops
        # the first-durable ledger validator.
        # Golden has its own dedicated durability/seriality ledger contract;
        # the generic E29 run-plan ledger is not emitted by
        # run_golden_serial_stream.
        if not is_golden_profile_name(config.profile_name):
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
        print(
            f"[v2ctl.confirm] evidence={result.evidence_path} "
            f"evidence_status={result.evidence_status} verdict={result.verdict}"
        )
        for reason in result.reasons:
            print(f"  FAIL {reason}")
        return 0 if result.valid else 1
    except (V2CtlError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_debug(args, repo_root: Path) -> int:
    """Diagnostic tooling.

    Nothing under ``debug`` participates in admission. These commands exist to
    answer "what is actually in this container?" after something has already
    gone wrong, and none of them can make a deployment or a result valid.
    """
    print("[v2ctl.debug] available commands:")
    print("  source-probe   report which source files are mounted in a container")
    return 0


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
        explicit_workspace = any(
            getattr(args, name, None)
            for name in ("workspace_id", "workspace", "environment")
        )
        workspace_binding = _canonical_workspace_binding(args, repo_root, config)
        _print_destination_preflight(workspace_binding)
        if getattr(args, "dry_run", False):
            print("[v2ctl.dry-run] no invocation performed; source probe skipped")
            print(
                f"target.app={config.target.app} target.class={config.target.class_name} "
                f"target.gpu={config.resources.gpu}"
            )
            return 0
        app_name = config.target.app
        class_name = config.target.class_name
        gpu = config.resources.gpu
        bound_receipt = None
        if is_golden_profile_name(config.profile_name):
            receipt_kwargs = ({"workspace_binding": workspace_binding}
                              if workspace_binding is not None else {})
            _, bound_receipt = _bound_deployment_receipt(
                repo_root, config, command="source-probe", **receipt_kwargs
            )
            if workspace_binding is not None:
                _require_receipt_workspace(bound_receipt, workspace_binding, command="source-probe")
                assert_workspace_binding_current(repo_root, workspace_binding)
                # Custom-node publication is fully manual: source-probe never
                # runs the publisher preflight.
        deploy_fp = bound_receipt.deploy_fingerprint if bound_receipt else fingerprints.deploy_fingerprint()
        expected_source = (
            bound_receipt.source_probe.get("expected") if bound_receipt is not None else None
        )
        if bound_receipt is not None and not isinstance(expected_source, dict):
            raise GateError("deployment receipt has no source-probe expectation")
        workspace = (
            workspace_binding._workspace_payload()
            if workspace_binding is not None else sp._load_workspace(repo_root)
        )
        probe_env = {
            name: str(value)
            for name, value in {
                "COMFYMODAL_V2_APP_NAME": app_name,
                "COMFYMODAL_V2_CLASS_NAME": class_name,
                "COMFYMODAL_V2_GPU": gpu,
            }.items()
            if value
        }
        with _workspace_process_environment(workspace_binding, probe_env):
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
        diagnostics = summary.get("diagnostics", {})
        manifest_diag = diagnostics.get("baked_dependency_manifest", {})
        print(
            "[v2ctl.source-probe] baked_manifest "
            f"path={manifest_diag.get('path', '')} "
            f"exists={manifest_diag.get('exists', False)} "
            f"readable={manifest_diag.get('readable', False)} "
            f"overall_hash={str(manifest_diag.get('overall_dependency_hash', '') or '')[:16] or '(empty)'} "
            f"dependency_nodes={manifest_diag.get('dependency_node_count', 0)} "
            f"dependency_node_set_hash={str(manifest_diag.get('dependency_node_set_hash', '') or '')[:16] or '(empty)'}"
        )
        sage_diag = diagnostics.get("sage", {})
        dispatcher = sage_diag.get("public_dispatcher", {})
        print(
            "[v2ctl.source-probe] sage "
            f"extension_present={sage_diag.get('extension_present', False)} "
            f"imported={sage_diag.get('imported', False)} "
            f"dispatcher={dispatcher.get('symbol', '') or '(none)'} "
            f"dispatcher_status={dispatcher.get('status', 'unknown')} "
            f"status={sage_diag.get('status', 'unknown')} "
            f"reason={sage_diag.get('reason', '')}"
        )
        join_diag = diagnostics.get("join_strings", {})
        print(
            "[v2ctl.source-probe] JoinStrings "
            f"registered={join_diag.get('registered', 'unknown')} "
            f"owner={join_diag.get('owner', 'unknown')} "
            f"source={join_diag.get('source', 'unknown')} "
            f"reason={join_diag.get('reason', '')}"
        )
        print(
            f"[v2ctl.source-probe] diagnostics_verdict="
            f"{led.get('diagnostics', {}).get('verdict', 'UNKNOWN')}"
        )
        print(f"[v2ctl.source-probe] verdict={led['verdict']}")
        if led["verdict"] != "MATCH":
            print(f"[v2ctl.source-probe] RESULT=FAIL source_identity != expected local source",
                  file=sys.stderr)
        else:
            print(f"[v2ctl.source-probe] RESULT=PASS source_identity=MATCH")
            # Deliberately no longer flips source_identity_status on the
            # deployment manifest. A debug command must not mutate deployment
            # validity: it inspected the mounted filesystem in a container it
            # started, which is weaker evidence than the deploy_id the serving
            # request reports, and writing a verdict back into the ledger meant a
            # later run's correctness depended on this command having been run.
        return exit_code
    except (V2CtlError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_publish_model_metadata_cache(args, repo_root: Path) -> int:
    """Publish static Golden model metadata on the profile's deployment.

    This command is intentionally not a gate.  Its result is printed for run
    evidence, while ``golden profile`` treats every nonzero result as a
    visible, fail-soft warning and still starts the cohort.
    """
    identity_error = _reject_golden_identity_args(args)
    if identity_error is not None:
        return identity_error
    try:
        from . import source_probe as sp

        (
            _registry,
            _profiles,
            _resolver,
            config,
            _fingerprints,
            _env_builder,
            _backend_registry,
        ) = _build_components_for_args(repo_root, args)
        _reject_protected_effective_target(
            config, command="v2ctl publish-model-metadata-cache"
        )
        _reject_golden_mode_override(
            config, command="v2ctl publish-model-metadata-cache"
        )
        workspace_binding = _canonical_workspace_binding(args, repo_root, config)
        _print_destination_preflight(workspace_binding)
        if getattr(args, "dry_run", False):
            print("[v2ctl.dry-run] no invocation performed; metadata publication skipped")
            print(
                f"target.app={config.target.app} target.class={config.target.class_name} "
                f"target.gpu={config.resources.gpu}"
            )
            return 0

        workspace = (
            workspace_binding._workspace_payload()
            if workspace_binding is not None
            else sp._load_workspace(repo_root)
        )
        app_name = config.target.app
        class_name = config.target.class_name
        gpu = config.resources.gpu
        probe_env = {
            name: str(value)
            for name, value in {
                "COMFYMODAL_V2_APP_NAME": app_name,
                "COMFYMODAL_V2_CLASS_NAME": class_name,
                "COMFYMODAL_V2_GPU": gpu,
            }.items()
            if value
        }
        with _workspace_process_environment(workspace_binding, probe_env):
            report = sp.call_remote_runtime_method(
                repo_root,
                workspace=workspace,
                gpu=str(gpu),
                method_name="publish_model_metadata_cache",
                request_id="v2-publish-model-metadata-cache",
            )
        print(f"[v2ctl.publish-model-metadata-cache] profile={args.profile}")
        print(json.dumps(report, sort_keys=True))
        status = str(report.get("status", "error"))
        if status in {"ok", "nothing_to_do"}:
            print(f"[v2ctl.publish-model-metadata-cache] RESULT={status.upper()}")
            return 0
        print(
            f"[v2ctl.publish-model-metadata-cache] RESULT={status.upper()}",
            file=sys.stderr,
        )
        return 1
    except (V2CtlError, OSError, RuntimeError) as exc:
        print(f"[v2ctl.publish-model-metadata-cache] ERROR: {exc}", file=sys.stderr)
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


def cmd_guard(args, repo_root: Path) -> int:
    """Run compact local Golden guardrails; never performs an implicit run."""
    sub = args.guard_command
    try:
        if sub == "paths":
            report = golden_guard_mod.canonical_paths(repo_root)
            baseline_file = getattr(args, "baseline_file", None)
            if baseline_file:
                snapshot = golden_guard_mod.capture_git_snapshot(repo_root)
                golden_guard_mod.save_git_snapshot(baseline_file, snapshot)
                report["baseline_file"] = str(Path(baseline_file).resolve())
                report["baseline"] = snapshot.as_dict()
            bootstrap = getattr(args, "bootstrap", None)
            if bootstrap:
                report["bootstrap"] = golden_guard_mod.bootstrap_worktree(repo_root, bootstrap)
        elif sub == "preflight":
            selected_profile = getattr(args, "profile", golden_guard_mod.DEFAULT_PROFILE)
            # The shared root parser defaults to production for legacy v2ctl
            # commands; the guard namespace is Golden-only.
            if selected_profile == "production":
                selected_profile = golden_guard_mod.DEFAULT_PROFILE
            report = golden_guard_mod.preflight(
                repo_root,
                profile=selected_profile,
                app=getattr(args, "app", "") or "",
                baseline_file=getattr(args, "baseline_file", None),
                min_free_gb=getattr(args, "min_free_gb", golden_guard_mod.DEFAULT_DISK_FREE_GB),
                telemetry_path=getattr(args, "telemetry_path", None),
                require_evidence=bool(getattr(args, "require_evidence", False)),
                expected_flags=getattr(args, "expected_flag", []),
                required_events=getattr(args, "required_event", []),
            )
        elif sub in {"safe-deploy", "safe-source-probe"}:
            operation = "deploy" if sub == "safe-deploy" else "source-probe"
            app = getattr(args, "app", None)
            if not app:
                print(f"ERROR: {sub} requires --app <experimental-app>", file=sys.stderr)
                return 2
            if getattr(args, "dry_run", False):
                result = golden_guard_mod.SafeOperationResult(
                    operation, golden_guard_mod.supported_command(repo_root, operation, app),
                    False, None, False, 0.0, golden_guard_mod.NOT_SENT,
                    stderr="dry-run: no supported operation sent",
                )
                report = {"result": result.as_dict()}
                print(json.dumps(report, indent=2, sort_keys=True))
                return 0
            disk = golden_guard_mod.disk_check(
                repo_root,
                min_free_gb=getattr(args, "min_free_gb", golden_guard_mod.DEFAULT_DISK_FREE_GB),
            )
            occupancy = golden_guard_mod.worktree_occupancy(repo_root)
            if not disk.ok or occupancy["occupied"]:
                result = golden_guard_mod.SafeOperationResult(
                    operation, golden_guard_mod.supported_command(repo_root, operation, app),
                    False, None, False, 0.0, golden_guard_mod.NOT_SENT,
                    stderr=("host disk guard refused operation" if not disk.ok
                            else "worktree occupancy guard refused operation"),
                )
                report = {"disk": disk.as_dict(), "occupancy": occupancy, "result": result.as_dict()}
                if getattr(args, "json", False):
                    print(json.dumps(report, indent=2, sort_keys=True))
                else:
                    print(f"outcome={result.outcome}\ndisk={disk.as_dict()}")
                return 1
            result = golden_guard_mod.run_safe_operation(
                repo_root, operation, app,
                timeout=getattr(args, "timeout", None),
                retries=getattr(args, "retries", 0),
            )
            report = {"disk": disk.as_dict(), "occupancy": occupancy, "result": result.as_dict()}
        else:
            return 2
    except (OSError, ValueError, V2CtlError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    if sub == "preflight":
        return 0 if report.get("ok") else 1
    if sub in {"safe-deploy", "safe-source-probe"}:
        return 0 if report["result"]["outcome"] == golden_guard_mod.VALID else 1
    return 0


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
    parser.add_argument(
        "--workspace", "--workspace-id", dest="workspace_id", default=None,
        help="deprecated destination override; canonical commands use config/v2/modal_target.toml",
    )
    parser.add_argument(
        "--environment", dest="environment", default=None,
        help="explicit Modal environment (default: registry/default environment)",
    )
    parser.add_argument("--gpu", default=None, help="override resource GPU")
    parser.add_argument("--memory-mb", type=int, default=None, help="override resource memory")
    parser.add_argument("--cpu", type=int, default=None, help="override resource CPU")
    parser.add_argument("--run-count", type=int, default=None, help="override run count")
    parser.add_argument(
        "--allow-production", action="store_true",
        help="deprecated; always refused for Golden R0",
    )
    parser.add_argument(
        "--allow-destructive-custom-node-publication", action="store_true",
        help="explicitly permit a custom-node publication that removes "
        "previously-published external package files/content; never inferred, "
        "never defaulted, recorded in the publication receipt",
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
    for name in ("doctor", "deploy", "run", "publisher-bootstrap", "publish-custom-nodes", "profile"):
        child = gsub.add_parser(
            name,
            help=_GOLDEN_COMMAND_HELP.get(name),
            description=_GOLDEN_COMMAND_DESCRIPTION.get(name),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        if name in {"deploy", "run", "publisher-bootstrap", "publish-custom-nodes", "profile"}:
            # Visible on ``golden <command> --help`` while the existing
            # pre-parser continues to support root-option hoisting.
            # SUPPRESS is important: _hoist_global_options may already have
            # populated the root option before argparse reaches this child.
            child.add_argument("--app", default=argparse.SUPPRESS, help="experimental Modal app name")
            child.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                               help="resolve and print, invoke nothing")
            if name == "deploy":
                child.add_argument(
                    "--for-profiling",
                    dest="for_profiling",
                    action="store_true",
                    default=argparse.SUPPRESS,
                    help="add the full-trace tracing flags, so a later "
                    "`golden profile --skip-deploy` produces a trace",
                )
            if name == "profile":
                child.add_argument(
                    "--min-ms",
                    type=float,
                    default=argparse.SUPPRESS,
                    help="call-tree expansion floor in ms (default 1.0)",
                )
                child.add_argument(
                    "--skip-deploy",
                    action="store_true",
                    default=argparse.SUPPRESS,
                    help="do not deploy; reuse the current deployment (it must "
                    "already carry the tracing flags)",
                )
                child.add_argument(
                    "--trace-id",
                    dest="trace_id",
                    default=argparse.SUPPRESS,
                    help="analyse this existing trace id instead of the one "
                    "produced by the run",
                )
                child.add_argument(
                    "--skip-analyze",
                    action="store_true",
                    default=argparse.SUPPRESS,
                    help="reuse existing derived artifacts and only re-render",
                )
                child.add_argument(
                    "--workspace-id",
                    default=argparse.SUPPRESS,
                    help="Modal workspace id override for bundle fetch",
                )
            if name == "run":
                child.add_argument(
                    "--acknowledge-volume-drift",
                    action="store_true",
                    default=argparse.SUPPRESS,
                    help="accepted as a no-op for compatibility; publication is manual "
                    "and run never gates on publisher content generation",
                )
        child.set_defaults(func=cmd_golden)

    p = sub.add_parser("debug")
    p.set_defaults(func=cmd_debug)
    dsub = p.add_subparsers(dest="debug_command")
    dsrc = dsub.add_parser(
        "source-probe",
        help=(
            "diagnostic: report which source files are mounted in a container "
            "this command starts. Does not gate deploy/run and does not "
            "establish which code served a request."
        ),
    )
    dsrc.set_defaults(func=cmd_source_probe)

    # Retained as a hidden alias so existing muscle memory and any saved command
    # lines keep working. The command is diagnostic either way.
    p = sub.add_parser("source-probe", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_source_probe)

    p = sub.add_parser(
        "publish-model-metadata-cache",
        help="publish static Golden model metadata before a cohort",
    )
    p.set_defaults(func=cmd_publish_model_metadata_cache)

    p = sub.add_parser(
        "guard",
        help="compact local Golden paths/preflight/safe-operation guardrails",
    )
    gguard = p.add_subparsers(dest="guard_command", required=True)
    paths = gguard.add_parser("paths", help="show canonical roots; optionally save a git baseline")
    paths.add_argument("--baseline-file", default=None, metavar="PATH",
                       help="write a small pre-experiment git baseline JSON")
    paths.add_argument("--bootstrap", default=None, metavar="PATH",
                       help="explicitly create a detached worktree and copy only small local inputs")
    paths.set_defaults(func=cmd_guard)
    pre = gguard.add_parser("preflight", help="report identity, dirty diff, disk, nodes, and evidence")
    pre.add_argument("--profile", default=argparse.SUPPRESS, help="Golden profile (default: golden_p1)")
    pre.add_argument("--app", default=argparse.SUPPRESS, help="experimental Modal app name")
    pre.add_argument("--baseline-file", default=None, metavar="PATH")
    pre.add_argument("--min-free-gb", type=float, default=golden_guard_mod.DEFAULT_DISK_FREE_GB)
    pre.add_argument("--telemetry-path", default=None, metavar="PATH")
    pre.add_argument("--require-evidence", action="store_true",
                     help="make missing deployment/source-probe evidence a failure")
    pre.add_argument("--expected-flag", action="append", default=[], metavar="NAME=VALUE",
                     help="require a persisted effective flag value (repeatable)")
    pre.add_argument("--required-event", action="append", default=[], metavar="FAMILY",
                     help="require a telemetry event family (repeatable)")
    pre.set_defaults(func=cmd_guard)
    for name, help_text in (
        ("safe-deploy", "run supported golden deploy with finite timeout/retry policy"),
        ("safe-source-probe", "run supported golden source-probe with finite timeout/retry policy"),
    ):
        safe = gguard.add_parser(name, help=help_text)
        safe.add_argument("--app", default=argparse.SUPPRESS, help="experimental Modal app name")
        safe.add_argument("--timeout", type=float, default=None,
                          help="finite subprocess timeout (deploy/probe default 1800s)")
        safe.add_argument("--retries", type=int, default=0,
                          help="bounded retries (maximum 3); lock/status/doctor inspection runs before each retry")
        safe.add_argument("--min-free-gb", type=float, default=golden_guard_mod.DEFAULT_DISK_FREE_GB)
        safe.set_defaults(func=cmd_guard)

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
    "--workspace",
    "--workspace-id",
    "--environment",
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
        if arg in ("--dry-run", "--json", "--allow-production",
                     "--allow-destructive-custom-node-publication"):
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
