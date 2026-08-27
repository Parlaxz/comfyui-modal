"""v2ctl command-line interface (Batch E32).

Thin CLI over the v2_control modules.  Local-only: every deploy/run/gate
command builds a sanitized child environment and invokes the canonical
backend (the known-good BATs) via subprocess.  No Modal SDK calls, no
network, no ambient experiment env leakage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

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

SCHEMA_VERSION = 1
VERSION = "0.1.0"

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
FULL_RUN_METHOD = "run_plan_stream"

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
        "COMFYMODAL_V2CTL_RUN_FINGERPRINT": fingerprints.run_fingerprint(),
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
    # The resolved Golden environment activates the BAT's dedicated harness;
    # do not forward the profile name as a benchmark positional selector.
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
        # The registry default is e28_single, whose BAT branch invokes the
        # ordinary run_plan_stream path.  Project the effective Golden mode
        # explicitly so the request reaches the serial-Golden branch.  An
        # explicit V2_BENCHMARK_MODE remains authoritative.
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
    Explicit mode selectors remain authoritative.  Non-Golden profiles keep
    the registry default and existing explicit-mode behavior.
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


def _require_full_run_mode(config: config_mod.ResolvedConfig, *, command: str) -> None:
    """HARD GUARD: gate/run must produce a full generation (run_plan_stream),
    never the snapshot-restore-only PROBE (which calls
    ``run_snapshot_restore_only_probe`` and produces no generation artifact).

    ``V2_BENCHMARK_MODE=snapshot_restore_only`` is a probe-only mode; using it
    through the gate/run path is a configuration error and is refused before
    any spend.
    """
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


def _app_version_number(app_name: str) -> int:
    """Highest ``v<N>`` version number from ``modal app history`` (0 if none).

    Returns 0 on any uncertainty — never raises.  The history table rows look
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
            return 0
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
        if r.returncode != 0:
            return 0
        highest = 0
        for line in r.stdout.splitlines():
            m = re.search(r"\bv(\d+)\b", line, re.IGNORECASE)
            if m:
                try:
                    highest = max(highest, int(m.group(1)))
                except ValueError:
                    continue
        return highest
    except Exception:
        return 0


# ── Manifests ──────────────────────────────────────────────────────────

def _deployment_manifest_dir(repo_root: Path) -> Path:
    return repo_root / ".v2ctl" / "deployments"


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


def write_deployment_manifest(repo_root: Path, config: config_mod.ResolvedConfig,
                              fingerprints: fp_mod.FingerprintEngine,
                              env: dict[str, str],
                              result: backend_mod.BackendResult | None) -> Path:
    d = _deployment_manifest_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    deploy_fp = fingerprints.deploy_fingerprint()
    manifest = {
        "schema_version": SCHEMA_VERSION,
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
        "profile_config_fingerprint": _profile_config_fingerprint(fingerprints),
        "deploy_inputs": fingerprints.deploy_inputs(),
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
    path = d / f"deploy_{time.strftime('%Y%m%d-%H%M%S')}_{deploy_fp[:8]}.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def latest_deployment_manifest(repo_root: Path) -> dict | None:
    d = _deployment_manifest_dir(repo_root)
    if not d.is_dir():
        return None
    files = sorted(d.glob("deploy_*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_run_manifest(repo_root: Path, config: config_mod.ResolvedConfig,
                       fingerprints: fp_mod.FingerprintEngine,
                       env: dict[str, str],
                       result: backend_mod.BackendResult,
                       provenance: prov_mod.Provenance | None) -> Path:
    d = _run_manifest_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    run_fp = fingerprints.run_fingerprint()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _utcnow_iso(),
        "profile": config.profile_name,
        "owner": config.owner,
        "deploy_fingerprint": fingerprints.deploy_fingerprint(),
        "run_fingerprint": run_fp,
        "v2ctl_invocation_id": result.v2ctl_invocation_id,
        "profile_config_fingerprint": fingerprints.profile_config_fingerprint(),
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


def cmd_doctor(args, repo_root: Path) -> int:
    problems: list[str] = []
    out: list[str] = ["[v2ctl.doctor]"]
    # git state
    git = config_mod.compute_git_state(repo_root)
    out.append(f"git.head={git.head}")
    out.append(f"git.branch={git.branch}")
    out.append(f"git.dirty={int(git.dirty)}")
    # python
    out.append(f"python={sys.version.split()[0]}")
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
    manifest = latest_deployment_manifest(repo_root)
    if manifest is None:
        out.append("deployment.manifest=none")
        problems.append("no deployment manifest found; run `v2ctl deploy-run` or `v2ctl deploy` first")
    else:
        try:
            _, _, _, config, fingerprints, _, _ = build_components(repo_root, args.profile)
            current = fingerprints.deploy_fingerprint()
            stored = manifest.get("deploy_fingerprint")
            match = stored == current
            out.append(f"deployment.fingerprint.stored={stored}")
            out.append(f"deployment.fingerprint.current={current}")
            out.append(f"deployment.fingerprint.match={int(match)}")
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
    try:
        _, _, _, config, fingerprints, _, _ = build_components(
            repo_root, args.profile,
            sets=args.set, inherits=args.inherit,
        )
        _refuse_protected_explicit(config)
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
    print(f"deploy_fingerprint={fingerprints.deploy_fingerprint()}")
    print(f"run_fingerprint={fingerprints.run_fingerprint()}")
    print(f"selector={_backend_selector(config) or '(none)'}")
    print(f"command={command}")
    print("[v2ctl.dry-run] child environment (redacted):")
    redacted = env_mod.EnvironmentBuilder().display(env)
    for k in sorted(redacted):
        print(f"  {k}={redacted[k]}")


def cmd_deploy(args, repo_root: Path) -> int:
    try:
        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = build_components(
            repo_root, args.profile, cli_options=_cli_target_options(args),
            sets=args.set, inherits=args.inherit,
        )
        invocation_id = _new_invocation_id()
        spec = backend_registry.deploy_only()
        env = env_builder.build(config, host_env=os.environ,
                                backend_extra={**spec.deploy_only_env,
                                               **_identity_env_for_command("deploy", config),
                                               **_canonical_metadata_env(config, fingerprints, invocation_id)})
        # Forward the canonical selector (e.g. E28_VALIDATION) as the BAT's
        # first positional arg: the deploy BAT reads %~1 to activate its
        # validation branch (env alone is not sufficient in all paths).
        selector = _backend_selector(config)
        extra_args = [selector] if selector else []
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
            print(f"[v2ctl.deploy] profile={config.profile_name} "
                  f"deploy_fingerprint={fingerprints.deploy_fingerprint()}")
            print(f"[v2ctl.deploy] command={command}")
            # ── Deploy-version-advance verification (E29 root-cause fix) ──
            # Capture the app's highest deployment version BEFORE the deploy
            # so a post-deploy comparison can prove a NEW version appeared
            # (a "version deployed recently" check falsely passes when a
            # deploy right after a prior one no-ops).
            _pre_version = _app_version_number(config.target.app) if config.target.app else 0
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
            manifest = write_deployment_manifest(repo_root, config, fingerprints, env, result)
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
            _post_version = _app_version_number(config.target.app) if config.target.app else 0
            if _post_version <= _pre_version:
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
            return 0
        finally:
            lock.release()
    except (V2CtlError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_deploy_run(args, repo_root: Path) -> int:
    try:
        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = build_components(
            repo_root, args.profile, cli_options=_cli_target_options(args),
            sets=args.set, inherits=args.inherit,
        )
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
            print(f"[v2ctl.deploy-run] profile={config.profile_name} "
                  f"deploy_fingerprint={fingerprints.deploy_fingerprint()}")
            print(f"[v2ctl.deploy-run] command={command}")
            result = backend_mod.BackendRunner(repo_root, env_builder).run(
                spec, config=config, extra_args=extra_args, extra_env=env, capture=True,
                invocation_id=invocation_id, strict_canonical_discovery=True)
            manifest = write_deployment_manifest(repo_root, config, fingerprints, env, result)
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
    try:
        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = build_components(
            repo_root, args.profile, cli_options=_cli_target_options(args),
            sets=args.set, inherits=args.inherit,
        )
        # Run-only: refuse unregistered and deploy-required explicit changes.
        resolver.check_run_safety(config, run_only=True)
        _require_no_deploy_in_flight(repo_root)
        manifest = latest_deployment_manifest(repo_root)
        if manifest is None:
            raise GateError("no deployment manifest; run `v2ctl deploy-run` (or `deploy`) first")
        stored = manifest.get("deploy_fingerprint")
        current = fingerprints.deploy_fingerprint()
        if stored != current:
            changes = diff_deploy_inputs(manifest.get("deploy_inputs", {}),
                                         fingerprints.deploy_inputs())
            raise GateError(
                "deployment fingerprint mismatch; deploy-required state changed since last "
                f"deploy. stored={stored} current={current}. Changed: "
                + ("; ".join(changes) if changes else "(unknown)"),
            )
        enforce_runtime_overrides(config,
                                  ro_mod.RuntimeOverrideInventory(local_dir=repo_root / ".runtime_state"),
                                  spend=True)
        # ── Full-run guard: run must generate (run_plan_stream), never the
        # snapshot-restore-only PROBE. ──
        _require_full_run_mode(config, command="v2ctl run")
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
        # Forward the canonical selector as the BAT's first positional arg so
        # the run BAT enters its validation mode (e.g. E28_VALIDATION) instead
        # of falling into the snapshot_restore_only probe branch.
        command = backend_mod.BackendRunner.build_command_line(spec, extra_args)
        if args.dry_run:
            _dry_run_report(config, fingerprints, env, command)
            return 0
        print(f"[v2ctl.run] profile={config.profile_name} "
              f"deploy_fingerprint={current} run_fingerprint={fingerprints.run_fingerprint()}")
        print(f"[v2ctl.run] command={command}")
        result = backend_mod.BackendRunner(repo_root, env_builder).run(
            spec, config=config, extra_args=extra_args, extra_env=env, capture=True,
            invocation_id=invocation_id, strict_canonical_discovery=True,
            allow_multiple_run_artifacts=run_count > 1)
        provenance = prov_mod.build_provenance(
            config, env, current, fingerprints.run_fingerprint(), [],
            invocation_id=invocation_id,
            profile_config_fingerprint=fingerprints.profile_config_fingerprint(),
            request_id=result.request_id or "",
        )
        run_manifest = write_run_manifest(repo_root, config, fingerprints, env, result, provenance)
        if result.artifacts.run_artifact is not None:
            try:
                prov_mod.write_provenance_sibling(result.artifacts.run_artifact, provenance)
            except OSError:
                pass
        print(f"[v2ctl.run] exit={result.exit_code} manifest={run_manifest}")
        if not result.ok():
            return result.exit_code if result.exit_code else 1
        return 0
    except (V2CtlError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_gate(args, repo_root: Path) -> int:
    try:
        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = build_components(
            repo_root, args.profile, cli_options=_cli_target_options(args),
            sets=args.set, inherits=args.inherit,
        )
        resolver.check_run_safety(config, run_only=True)
        _require_no_deploy_in_flight(repo_root)
        manifest = latest_deployment_manifest(repo_root)
        if manifest is None or manifest.get("deploy_fingerprint") != fingerprints.deploy_fingerprint():
            raise GateError("gate requires a deployment whose fingerprint matches the requested "
                            "configuration; run `v2ctl deploy-run` first")
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
                                  env_builder=env_builder)
        result = gate.run_gate(config, spec, invocation_id=invocation_id)
        print(f"[v2ctl.gate] valid={int(result.valid)} manifest={result.manifest_path}")
        for reason in result.reasons:
            print(f"  FAIL {reason}")
        if result.run is not None and result.run.artifacts.run_artifact is not None:
            provenance = prov_mod.build_provenance(
                config, env_builder.build(config, host_env=os.environ,
                                          backend_extra={"V2_BENCHMARK_RUNS": "1",
                                                         **_canonical_metadata_env(config, fingerprints, invocation_id)}),
                fingerprints.deploy_fingerprint(), fingerprints.run_fingerprint(), [],
                invocation_id=invocation_id,
                profile_config_fingerprint=fingerprints.profile_config_fingerprint(),
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
    try:
        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = build_components(
            repo_root, args.profile, cli_options=_cli_target_options(args),
            sets=args.set, inherits=args.inherit,
        )
        resolver.check_run_safety(config, run_only=True)
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
        # Confirm must enforce the same canonical ledger contract as gate;
        # otherwise an E37 gate could pass while confirmation silently drops
        # the first-durable ledger validator.
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
                                        validators=validator)
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
    try:
        from . import source_probe as sp

        workspace = sp._load_workspace(repo_root)
        # Reuse the profile's target identity (app/class/gpu) so the probe
        # addresses the SAME deployment the gate would.
        try:
            registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = (
                build_components(repo_root, args.profile,
                                 cli_options=_cli_target_options(args),
                                 sets=args.set, inherits=args.inherit)
            )
            app_name = config.target.app
            class_name = config.target.class_name
            gpu = config.resources.gpu
            deploy_fp = fingerprints.deploy_fingerprint()
        except Exception:
            app_name = ""
            class_name = ""
            gpu = "rtx-pro-6000"
            deploy_fp = ""
        import os as _os
        if app_name:
            _os.environ["COMFYMODAL_V2_APP_NAME"] = app_name
        if class_name:
            _os.environ["COMFYMODAL_V2_CLASS_NAME"] = class_name
        if gpu:
            _os.environ["COMFYMODAL_V2_GPU"] = str(gpu)

        exit_code, report = sp.run_source_probe(repo_root, workspace=workspace, gpu=str(gpu))
        print(f"[v2ctl.source-probe] profile={args.profile}")
        print(f"[v2ctl.source-probe] git_head={report['expected'].get('git_head', '')[:12]}")
        print(f"[v2ctl.source-probe] target app={app_name or '(profile unresolved)'} "
              f"class={class_name or '(profile unresolved)'} gpu={gpu or 'rtx-pro-6000'}")
        summary = report["remote_summary"]
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
            # Flip the deployment manifest's source_identity_status to
            # verified when it exists (truthful health semantics).
            try:
                import json as _json
                mdir = _deployment_manifest_dir(repo_root)
                files = sorted(mdir.glob("deploy_*.json")) if mdir.is_dir() else []
                for manifest_path in reversed(files):
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
        opts["target.app"] = args.app
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


_GLOBAL_HOIST_WITH_VALUE = ("--profile", "--owner")


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
        if arg in ("--dry-run", "--json"):
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
        return args.func(args, repo_root)
    except V2CtlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
