"""Gate/confirm validation protocol for the v2ctl control plane (Batch E32).

Implements design sections 17 ("Canonical Cold Validation Protocol") and 18
("Generic Validation Contract") of V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md:

* one cold gate run first; inspect/validate it; only then spend a
  confirmation run (1-5 valid runs total, biased toward fewer);
* a structurally invalid gate exits nonzero;
* confirm only runs after a valid gate manifest and rechecks that
  source/config/deployment have not changed (deploy fingerprint, git head,
  target);
* validators plug in through a seam rather than hardcoding E29/E30/E31 into
  core v2ctl.

The backend is invoked through an injectable ``backend_runner`` (duck-typed
against tools/v2_control/backend.py's BackendRunner: ``run(spec, *, config,
extra_args, extra_env, ...) -> BackendResult`` with ``.exit_code``,
``.stdout``, ``.stderr``, ``.artifacts``).  Tests substitute a fake backend
runner; the gate never performs more than one invocation and confirm never
more than ``runs``.

Python 3.11 stdlib only; no network calls; no real BAT execution here.
"""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import inspect
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


def _is_golden_profile(config: Any) -> bool:
    profile = str(getattr(config, "profile_name", "") or "").strip().lower()
    return profile in {"golden_p1", "golden_p1_parallel"} or profile.startswith("golden_p1_direct")


def _golden_contract(config: Any) -> tuple[str, str, str, bool]:
    """Return mode, method, evidence mode, and seriality requirement."""
    profile = str(getattr(config, "profile_name", "") or "").strip().lower()
    target = getattr(config, "target", None)
    method = str(getattr(target, "method", "") or "").strip()
    parallel = profile == "golden_p1_parallel" or method == "run_golden_parallel_stream"
    if parallel:
        return (
            "golden_p1_parallel",
            "run_golden_parallel_stream",
            "parallel",
            False,
        )
    return ("golden_p1_serial", "run_golden_serial_stream", "serial", True)

from .backend import detect_crash_loop
from .errors import GateError
from .experiment_evidence import (
    configured_sage_runtime_mode,
    finalize_experiment_evidence,
    golden_arm_identity,
    is_experiment_profile,
    resolved_attention_backend,
    resolved_sage_runtime_mode,
)

try:  # Keep direct-script/package imports usable in both test and CLI paths.
    from tools.golden_observability import WORKFLOW_CONTRACT_MARKERS, workflow_contract_failures
except ImportError:  # pragma: no cover - direct tools-script fallback
    try:
        from golden_observability import WORKFLOW_CONTRACT_MARKERS, workflow_contract_failures
    except ImportError:  # pragma: no cover - package-relative fallback
        from ..golden_observability import WORKFLOW_CONTRACT_MARKERS, workflow_contract_failures

try:  # Canonical runtime selector; validation remains usable without runtime deps.
    from comfymodal_runtime.output_durability import (
        ConfigurationError as _RuntimeOutputDurabilityConfigurationError,
        resolve_output_durability as _runtime_resolve_output_durability,
    )
except Exception:  # pragma: no cover - stdlib-only/control-plane fallback
    _RuntimeOutputDurabilityConfigurationError = None
    _runtime_resolve_output_durability = None

LOG = logging.getLogger("v2ctl.validation")

_GATE_SCHEMA_VERSION = 1


def _receipt_value(receipt: Any, name: str, default: Any = "") -> Any:
    if receipt is None:
        return default
    if isinstance(receipt, dict):
        return receipt.get(name, default)
    return getattr(receipt, name, default)


def _bind_receipt_environment(extra_env: dict[str, str], receipt: Any) -> dict[str, str]:
    if receipt is None:
        return extra_env
    validator = getattr(receipt, "validate", None)
    if callable(validator):
        validator()
    values = _receipt_value(receipt, "effective_environment", {})
    if not isinstance(values, dict):
        raise GateError("deployment receipt effective environment is malformed")
    from .deployment_receipt import validate_effective_environment

    effective_config = _receipt_value(receipt, "effective_config", {})
    deploy_flags = (
        effective_config.get("deploy_flags", {})
        if isinstance(effective_config, dict) else {}
    )
    validate_effective_environment(
        values,
        allowed_names={str(name) for name in deploy_flags}
        if isinstance(deploy_flags, dict) else None,
    )
    bound = dict(extra_env)
    bound.update({str(k): str(v) for k, v in values.items() if v != "<redacted>"})
    target = _receipt_value(receipt, "target", {})
    if isinstance(target, dict):
        for name, key in (("COMFYMODAL_V2_APP_NAME", "app"),
                          ("COMFYMODAL_V2_CLASS_NAME", "class")):
            if target.get(key):
                bound[name] = str(target[key])
    resources = _receipt_value(receipt, "deployment_identity", {})
    resources = resources.get("resources", {}) if isinstance(resources, dict) else {}
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
    deploy_fp = str(_receipt_value(receipt, "deploy_fingerprint", ""))
    if not deploy_fp:
        raise GateError("deployment receipt has no deployment fingerprint")
    bound["COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT"] = deploy_fp
    bound["COMFYMODAL_V2CTL_DEPLOYMENT_HASH"] = deploy_fp
    profile = str(_receipt_value(receipt, "profile", ""))
    if profile:
        bound["COMFYMODAL_V2CTL_PROFILE"] = profile
    profile_fp = str(_receipt_value(receipt, "profile_config_fingerprint", ""))
    if profile_fp:
        bound["COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT"] = profile_fp
    return bound


def _bound_run_fingerprint(fingerprints: Any, receipt: Any) -> str:
    """Keep request identity deterministic while replacing only deploy state."""
    if receipt is None:
        return str(fingerprints.run_fingerprint())
    deploy_fp = str(_receipt_value(receipt, "deploy_fingerprint", ""))
    try:
        inputs = dict(fingerprints.run_inputs())
        inputs["deploy_fingerprint"] = deploy_fp
        return hashlib.sha256(
            json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
    except Exception:  # noqa: BLE001 - older test doubles expose only run_fingerprint
        return str(fingerprints.run_fingerprint())


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


@dataclass
class RunRecord:
    """What one backend invocation produced, reduced to validation-relevant
    fields."""

    run_fingerprint: str
    deploy_fingerprint: str
    profile: str
    target_app: str
    target_class: str
    fresh_required: bool
    expected_output_sha: str
    artifacts: Any  # ArtifactSet (duck-typed: .output_dir/.run_artifact/...)
    backend_ok: bool
    telemetry: dict = field(default_factory=dict)
    output_sha: str | None = None
    v2ctl_invocation_id: str = ""
    request_id: str = ""
    profile_config_fingerprint: str = ""
    provenance_validation_status: str = ""
    #: deploy_id the deployment being claimed was expected to report.
    expected_deploy_id: str = ""
    #: deploy_id the serving interpreter actually reported for this request.
    deploy_id: str = ""
    backend_exit_code: int | None = None
    attention_backend: str = ""
    golden_arm: str = ""
    cpu_qd2_prefetch: bool = False
    experiment_identity: dict[str, Any] = field(default_factory=dict)
    backend_command: str = ""

    def to_dict(self) -> dict:
        return {
            "run_fingerprint": self.run_fingerprint,
            "deploy_fingerprint": self.deploy_fingerprint,
            "profile": self.profile,
            "target_app": self.target_app,
            "target_class": self.target_class,
            "fresh_required": self.fresh_required,
            "expected_output_sha": self.expected_output_sha,
            "artifacts": _artifacts_to_dict(self.artifacts),
            "backend_ok": self.backend_ok,
            "backend_exit_code": self.backend_exit_code,
            "telemetry": dict(self.telemetry),
            "output_sha": self.output_sha,
            "v2ctl_invocation_id": self.v2ctl_invocation_id,
            "request_id": self.request_id,
            "profile_config_fingerprint": self.profile_config_fingerprint,
            "provenance_validation_status": self.provenance_validation_status,
            "attention_backend": self.attention_backend,
            "golden_arm": self.golden_arm,
            "cpu_qd2_prefetch": self.cpu_qd2_prefetch,
            "experiment_identity": dict(self.experiment_identity),
            "backend_command": self.backend_command,
        }


def _artifacts_to_dict(artifacts: Any) -> dict:
    """Serialize an ArtifactSet-like object; Path values become strings."""
    if artifacts is None:
        return {}
    try:
        items = artifacts.__dict__
    except AttributeError:
        return {}
    result: dict = {}
    for key, value in items.items():
        if isinstance(value, Path):
            result[key] = str(value)
        elif isinstance(value, list):
            result[key] = [str(v) if isinstance(v, Path) else v for v in value]
        else:
            result[key] = value
    return result


@dataclass
class GateResult:
    """Outcome of a gate run or a confirmation phase."""

    valid: bool
    reasons: list[str]
    manifest_path: Path | None = None
    run: RunRecord | None = None
    evidence_path: Path | None = None
    evidence_status: str = "not_run"
    verdict: str = "INCONCLUSIVE"


def _experiment_identity(
    record: RunRecord | None,
    config: Any,
    deploy_fp: str,
    run_fp: str,
    result: Any | None = None,
) -> dict[str, Any]:
    from .experiment_evidence import sage_runtime_identity as _sage_id
    identity = dict(record.experiment_identity if record is not None else {})
    # RX9P-H: include full Sage 4-field and attention provenance in frozen identity.
    sage_id = _sage_id(config, identity)
    attention_configured = resolved_attention_backend(config)
    attention_resolved = attention_configured  # control-plane expectation; runtime must prove same
    identity.update({
        "profile": str(getattr(config, "profile_name", "") or ""),
        "deploy_fingerprint": deploy_fp,
        "run_fingerprint": run_fp,
        "configured_sage_runtime_mode": configured_sage_runtime_mode(config),
        "resolved_sage_runtime_mode": resolved_sage_runtime_mode(identity),
        "sage_runtime_mode_configured": sage_id.get("sage_runtime_mode_configured", ""),
        "sage_runtime_mode_effective_input": sage_id.get("sage_runtime_mode_effective_input", ""),
        "sage_runtime_mode_resolution_source": sage_id.get("sage_runtime_mode_resolution_source", ""),
        "sage_runtime_mode_resolved": sage_id.get("sage_runtime_mode_resolved", ""),
        "attention_backend": str(
            (record.attention_backend if record is not None else "")
            or resolved_attention_backend(config)
        ),
        "attention_backend_configured": attention_configured,
        "attention_backend_resolved": attention_resolved,
        **(golden_arm_identity(config) if _is_golden_profile(config) else {}),
    })
    if record is not None:
        identity.setdefault("v2ctl_invocation_id", record.v2ctl_invocation_id)
        identity.setdefault("request_id", record.request_id)
        identity.setdefault("profile_config_fingerprint", record.profile_config_fingerprint)
    if result is not None:
        identity["backend_command"] = str(getattr(result, "command", "") or "")
        identity["backend_exit_code"] = getattr(result, "exit_code", None)
    elif record is not None and record.backend_command:
        identity["backend_command"] = record.backend_command
    target = getattr(config, "target", None)
    resources = getattr(config, "resources", None)
    identity["target"] = {
        "app": str(getattr(target, "app", "") or ""),
        "class": str(getattr(target, "class_name", "") or ""),
        "method": str(getattr(target, "method", "") or ""),
    }
    identity["resources"] = {
        name: getattr(resources, name, "")
        for name in ("gpu", "cpu", "memory_mb", "min_containers", "scaledown_window")
    }
    return identity


def _finalize_evidence(
    repo_root: Path,
    *,
    record: RunRecord | None,
    config: Any,
    deploy_fp: str,
    run_fp: str,
    result: Any | None,
    verdict: str,
    gate_manifest: Path | None = None,
    confirmation_manifest: Path | None = None,
    records: list[RunRecord] | None = None,
    invocation_id: str = "",
) -> tuple[Path | None, str, str, str | None]:
    """Finalize evidence and convert any finalizer failure to INCONCLUSIVE."""
    if not is_experiment_profile(config):
        return None, "not_applicable", verdict, None
    try:
        identity = _experiment_identity(record, config, deploy_fp, run_fp, result)
        if invocation_id:
            identity["v2ctl_invocation_id"] = invocation_id
        evidence = finalize_experiment_evidence(
            repo_root,
            identity=identity,
            verdict=verdict,
            result=result,
            records=records or ([record] if record is not None else []),
            gate_manifest=gate_manifest,
            confirmation_manifest=confirmation_manifest,
        )
        return evidence.markdown_path, evidence.status, evidence.verdict, None
    except Exception as exc:  # noqa: BLE001 - evidence failure is an explicit verdict
        return None, "FAILED", "INCONCLUSIVE", f"experiment evidence finalization failed: {exc}"


def _invalidate_evidence_manifest(path: Path | None, reason: str) -> None:
    """Prevent a control manifest from remaining valid after evidence failure."""
    if path is None:
        return
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            return
        manifest["gate_valid"] = False
        reasons = manifest.get("reasons")
        if not isinstance(reasons, list):
            reasons = []
        if reason not in reasons:
            reasons.append(reason)
        manifest["reasons"] = reasons
        manifest["evidence_status"] = "FAILED"
        manifest["verdict"] = "INCONCLUSIVE"
        path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError):
        # The finalizer already reports the primary failure.  Do not mask it
        # with a best-effort control-manifest repair error.
        return


def mark_runtime_health_verified(
    repo_root: Path,
    config: Any,
    fingerprints: Any,
    captured_deploy_fingerprint: str,
    *,
    bound_receipt: Any | None = None,
) -> Path | None:
    """Mark the exact deployment proved by a successful validated run.

    Runtime health is deliberately independent from source identity.  Only the
    newest deployment manifest is eligible, and it must match all three target
    identity fields and the deployment fingerprint captured before execution.
    For non-receipt paths, the fingerprint is checked again immediately before
    writing so an old successful result cannot promote a deployment created
    during the run.  Receipt-bound paths validate the matching manifest and
    return its path without mutating the sealed ledger.
    """
    deployments = Path(repo_root) / ".v2ctl" / "deployments"
    if not deployments.is_dir():
        return None
    manifests = sorted(deployments.glob("deploy_*.json"))
    if not manifests:
        return None
    path = manifests[-1]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict):
        return None

    target = getattr(config, "target", None)
    expected_target = {
        "app": str(getattr(target, "app", "") or ""),
        "class": str(getattr(target, "class_name", "") or ""),
        "method": str(getattr(target, "method", "") or ""),
    }
    if manifest.get("target") != expected_target:
        return None
    if manifest.get("deploy_fingerprint") != captured_deploy_fingerprint:
        return None

    try:
        current_deploy_fingerprint = str(fingerprints.deploy_fingerprint())
    except (AttributeError, TypeError, ValueError):
        return None
    if bound_receipt is None and current_deploy_fingerprint != captured_deploy_fingerprint:
        return None

    # A bound Golden receipt seals this deployment manifest.  Health evidence
    # belongs to the run/gate artifacts, not to the immutable ledger.
    if bound_receipt is not None:
        return path

    manifest["runtime_health_status"] = "verified"
    try:
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        return None
    return path


# --------------------------------------------------------------------------
# Validator seam
# --------------------------------------------------------------------------


class ValidatorPlugin(Protocol):
    """A pluggable validator.  ``validate`` returns a list of failure
    strings (empty == pass)."""

    name: str

    def validate(self, record: RunRecord, config: Any) -> list[str]:  # ResolvedConfig
        ...


class Validator:
    def __init__(self) -> None:
        self._plugins: list[ValidatorPlugin] = []

    def register(self, plugin: ValidatorPlugin) -> None:
        self._plugins.append(plugin)

    def run(self, record: RunRecord, config: Any) -> list[str]:  # ResolvedConfig
        failures: list[str] = []
        for plugin in self._plugins:
            for failure in plugin.validate(record, config):
                failures.append(f"[{plugin.name}] {failure}")
        return failures


def _artifact_run_path(record: RunRecord) -> Path | None:
    artifacts = record.artifacts
    if artifacts is None:
        return None
    run_artifact = getattr(artifacts, "run_artifact", None)
    return run_artifact if run_artifact is not None else None


# E40 Lane E: single acceptance authority extensions
def _runtime_contract_data(record: RunRecord) -> dict[str, Any]:
    """Return runtime contract fields from telemetry and the persisted record."""
    data: dict[str, Any] = {}
    telemetry = record.telemetry if isinstance(record.telemetry, dict) else {}
    contract_keys = (
        "runtime_status",
        "loader_selection",
        "resolved_config",
        "resolved_config_fingerprint",
        "config_snapshot",
        "provenance",
        "deploy_inputs",
    )
    for key in contract_keys:
        if key in telemetry:
            data[key] = telemetry[key]
        candidate = getattr(record, key, None)
        if candidate is not None:
            data[key] = candidate
    artifact_data = _artifact_data(record)
    sources = [artifact_data, artifact_data.get("result"), artifact_data.get("telemetry")]
    result = artifact_data.get("result")
    if isinstance(result, dict):
        sources.append(result.get("telemetry"))
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in contract_keys:
            if key in source:
                data[key] = source[key]
    return data


# E40 Lane E: single acceptance authority extensions
def _runtime_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() in {
        "1", "true", "yes", "on",
    }


# E40 Lane E: single acceptance authority extensions
def _runtime_status_failures(runtime_status: Any) -> list[str]:
    if not isinstance(runtime_status, dict):
        return ["runtime_status_not_nominal:(missing)", "runtime_status_reasons_invalid"]
    status = runtime_status.get("status")
    failures: list[str] = []
    if status != "NOMINAL":
        failures.append(f"runtime_status_not_nominal:{status or '(missing)'}")
    reasons = runtime_status.get("reasons")
    if isinstance(reasons, list):
        failures.extend(str(reason) for reason in reasons)
    else:
        failures.append("runtime_status_reasons_invalid")
    return failures


# E40 Lane E: single acceptance authority extensions
def _loader_selection_failures(loader_selection: Any) -> list[str]:
    if loader_selection is None:
        return ["loader_selection_invalid"]
    if not isinstance(loader_selection, dict):
        return ["loader_selection_invalid"]
    failures: list[str] = []
    for role in ("clip", "unet", "vae"):
        if role not in loader_selection:
            continue
        selection = loader_selection[role]
        if not isinstance(selection, dict):
            failures.append(f"loader_selection_invalid_{role}")
            continue
        requested = str(selection.get("requested", ""))
        effective = str(selection.get("effective", ""))
        observed = str(selection.get("observed", ""))
        fallback_loader = str(selection.get("fallback_loader", ""))
        if _runtime_bool(selection.get("fallback_attempted")):
            failures.append(f"loader_fallback_{role}:{requested}->{fallback_loader}")
        if observed != effective:
            failures.append(f"loader_observed_mismatch_{role}")
        if requested != effective:
            failures.append(f"loader_effective_mismatch_{role}")
    return failures


# E40 Lane E: single acceptance authority extensions
def _fingerprint_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("resolved_config_fingerprint", "fingerprint"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for key in ("resolved_config", "config_snapshot", "provenance", "deploy_inputs"):
            nested = _fingerprint_from_value(value.get(key))
            if nested:
                return nested
    for key in ("resolved_config_fingerprint", "fingerprint"):
        candidate = getattr(value, key, None)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


# E40 Lane E: single acceptance authority extensions
def _runtime_fingerprint_failures(record: RunRecord, config: Any, data: dict[str, Any]) -> list[str]:
    resolved_config = data.get("resolved_config")
    if not isinstance(resolved_config, dict):
        return []
    observed = _fingerprint_from_value(resolved_config)
    if not observed:
        return []

    comparable: list[Any] = []
    for source in (data, record.telemetry, getattr(record, "artifacts", None), config):
        if isinstance(source, dict):
            comparable.extend(
                source.get(key)
                for key in (
                    "resolved_config_fingerprint",
                    "config_snapshot",
                    "provenance",
                    "deploy_inputs",
                )
                if key in source
            )
        else:
            for key in (
                "resolved_config_fingerprint",
                "config_snapshot",
                "provenance",
                "deploy_inputs",
                "resolved_config",
            ):
                candidate = getattr(source, key, None)
                if candidate is not None:
                    comparable.append(candidate)
    for candidate in comparable:
        expected = _fingerprint_from_value(candidate)
        if expected and expected != observed:
            return ["resolved_config_fingerprint_mismatch"]
    return []


# E40 Lane E: single acceptance authority extensions
def _validate_runtime_contract(record: RunRecord, config: Any) -> list[str]:
    data = _runtime_contract_data(record)
    failures: list[str] = []
    if "runtime_status" in data:
        failures.extend(_runtime_status_failures(data["runtime_status"]))
    if "loader_selection" in data:
        failures.extend(_loader_selection_failures(data["loader_selection"]))
    failures.extend(_runtime_fingerprint_failures(record, config, data))
    return failures


# --------------------------------------------------------------------------
# Built-in structural validators
# --------------------------------------------------------------------------


class StructuralValidator(ValidatorPlugin):
    """Generic structural checks from design section 18: backend success, a
    persisted run artifact exists, telemetry carries request/correlation ids,
    fresh/restored identity is present when fresh is required, output SHA
    matches when one is configured, and effective provenance is required for
    every canonical record.  Missing proof or identity fails closed."""

    name = "structural"

    def validate(self, record: RunRecord, config: Any) -> list[str]:
        # Golden has a deliberately separate persisted schema (cohort
        # manifest + attempt artifact), so the generic run-plan proof fields
        # such as ``fresh`` and ``v2ctl_config`` are not applicable.  Route it
        # through the equally fail-closed Golden contract instead of allowing
        # a generic external run projection to stand in for the cohort.
        if (
            _is_golden_profile(config)
            and getattr(getattr(record, "artifacts", None), "campaign_manifest", None) is not None
        ):
            return GoldenCohortValidator().validate(record, config)
        failures: list[str] = []

        # persisted run artifact present
        run_artifact = _artifact_run_path(record)
        if not record.backend_ok:
            if run_artifact is None or not Path(run_artifact).is_file():
                failures.append(
                    "backend invocation failed without producing a persisted run artifact"
                    f" (exit code {record.backend_exit_code if record.backend_exit_code is not None else 'unknown'})"
                )
            else:
                failures.append("backend invocation did not complete successfully")
        if run_artifact is None or not Path(run_artifact).is_file():
            failures.append(f"persisted run artifact missing: {run_artifact}")

        # telemetry carries request/correlation identity when available
        # (an empty telemetry dict is itself a missing-identity failure)
        telemetry = record.telemetry or {}
        if "request_id" not in telemetry and "REQUEST_ID" not in telemetry:
            failures.append("telemetry missing request_id")
        if "correlation_id" not in telemetry and "CORRELATION_ID" not in telemetry:
            failures.append("telemetry missing correlation_id")

        # Canonical validation is fail-closed: a persisted artifact is not
        # enough without the identity that bound it to this v2ctl operation.
        artifacts = record.artifacts
        invocation_id = str(
            record.v2ctl_invocation_id
            or getattr(artifacts, "v2ctl_invocation_id", "")
            or ""
        ).strip()
        profile_config_fingerprint = str(
            record.profile_config_fingerprint
            or getattr(artifacts, "profile_config_fingerprint", "")
            or ""
        ).strip()
        provenance_status = str(
            record.provenance_validation_status
            or getattr(artifacts, "provenance_validation_status", "")
            or ""
        ).strip()
        request_id = str(
            record.request_id
            or getattr(artifacts, "request_id", "")
            or telemetry.get("request_id")
            or telemetry.get("REQUEST_ID")
            or ""
        ).strip()
        if not invocation_id:
            failures.append("effective provenance missing v2ctl_invocation_id")
        if not request_id:
            failures.append("effective provenance missing request_id")
        if not profile_config_fingerprint:
            failures.append("effective provenance missing profile_config_fingerprint")
        # provenance_validation_status is deliberately NOT an acceptance gate.
        #
        # It recorded whether a *provenance sibling document* had itself been
        # cross-validated, i.e. one local file vouching for another. That is a
        # proof of a proof, and its absence says nothing about whether the
        # output was correct. The facts it was guarding -- which deployment ran,
        # which request produced this, whether the SHA matched -- are now
        # checked directly: deploy_id above, and output SHA below.
        if provenance_status and provenance_status != "validated":
            failures.append(
                "effective provenance was not canonically validated: "
                f"{provenance_status}"
            )

        # fresh identity line when fresh required: a REUSED (restored)
        # container must FAIL a fresh-required gate, never satisfy it.
        if record.fresh_required:
            fresh = str(telemetry.get("fresh") or "").lower() in ("1", "true", "yes", "on")
            restored = str(telemetry.get("restored") or "").lower() in ("1", "true", "yes", "on")
            if restored:
                failures.append(
                    "fresh_required but container was REUSED (restored=True): "
                    "a reused container cannot prove a fresh cold generation"
                )
            elif not fresh:
                failures.append("fresh_required but telemetry shows neither fresh nor restored identity")

        # output SHA match when expected
        if record.expected_output_sha:
            if not record.output_sha:
                failures.append("expected_output_sha configured but no output SHA observed")
            elif record.output_sha != record.expected_output_sha:
                failures.append(
                    f"output SHA mismatch: expected {record.expected_output_sha}, observed {record.output_sha}"
                )

        # Same-request deploy_id is the authoritative deployment check.
        #
        # This replaces the previous "effective-config proof" requirement, which
        # demanded a `v2ctl_config` telemetry string containing deploy=/run=/
        # profile= tokens. That string was a proof of other proofs: it restated
        # a deploy fingerprint, a run fingerprint and a profile name, so the two
        # could disagree and nothing compared them against what actually served
        # the request.
        #
        # deploy_id is computed once from the deployment-relevant inputs, baked
        # into the class environment, frozen by the runtime at import and
        # reported by the serving request. Comparing the expected id with the
        # id the executing interpreter reported answers the question directly:
        # did the deployment I intended actually serve this request? A stale
        # snapshot reports its own older id and is rejected.
        expected_deploy_id = str(
            getattr(record, "expected_deploy_id", "") or ""
        ).strip()
        served_deploy_id = str(
            getattr(record, "deploy_id", "")
            or telemetry.get("deploy_id")
            or telemetry.get("DEPLOY_ID")
            or ""
        ).strip()
        if not served_deploy_id:
            failures.append(
                "the serving deployment reported no deploy_id, so it cannot be "
                "shown to be the deployment that was requested"
            )
        elif not expected_deploy_id:
            failures.append(
                "no expected deploy_id was supplied, so the serving deployment "
                "cannot be checked against the deployment that was requested"
            )
        elif served_deploy_id != expected_deploy_id:
            failures.append(
                "deploy_id mismatch: expected %s but the deployment that served "
                "this request reports %s (stale snapshot or wrong deployment)"
                % (expected_deploy_id, served_deploy_id)
            )

        # E40 Lane E: single acceptance authority extensions
        failures.extend(_validate_runtime_contract(record, config))
        return failures


class ExpectedOutputShaValidator(ValidatorPlugin):
    """Compares the observed output SHA against
    ``config.workload.expected_output_sha`` when the latter is set."""

    name = "output_sha"

    def validate(self, record: RunRecord, config: Any) -> list[str]:
        expected = _config_workload(config).get("expected_output_sha")
        if not expected:
            return []
        if record.output_sha is None:
            return ["output SHA unavailable: backend produced no output_sha line"]
        if record.output_sha != expected:
            if _is_golden_profile(config):
                LOG.warning(
                    "Golden output SHA mismatch is warning-only: expected=%s observed=%s",
                    expected,
                    record.output_sha,
                )
                return []
            return [
                f"output SHA mismatch: expected {expected}, observed {record.output_sha}"
            ]
        return []


_OUTPUT_DURABILITY_SELECTOR_KEYS = (
    "output_durability_mode",
    "request_output_durability_mode",
    "output_durability",
    "request_output_durability",
    "durability_mode",
)
_OUTPUT_DURABILITY_CONFIG_FLAGS = (
    "COMFYMODAL_OUTPUT_DURABILITY",
    "COMFYMODAL_V2_OUTPUT_DURABILITY_MODE",
    "COMFYMODAL_V2_REQUEST_OUTPUT_DURABILITY_MODE",
    "COMFYMODAL_V2_OUTPUT_DURABILITY",
    "COMFYMODAL_V2_REQUEST_OUTPUT_DURABILITY",
)
_OUTPUT_DURABILITY_CONFIGURATION_ERROR = (
    "configuration error: COMFYMODAL_OUTPUT_DURABILITY must be off or strict"
)


def _normalize_output_durability_mode(value: Any) -> str:
    """Apply the runtime selector contract to one explicit value.

    ``off`` and an absent/empty value mean off; ``strict`` means strict.  Any
    other non-empty value is a configuration error.  In particular, invalid
    input is not converted to ``off``: doing that would allow a malformed
    explicit request to pass the validator as if it had never been made.
    """
    normalized = str(value or "").strip().lower()
    if not normalized or normalized == "off":
        return "off"
    if normalized == "strict":
        return "strict"
    error_type = _RuntimeOutputDurabilityConfigurationError or ValueError
    raise error_type(_OUTPUT_DURABILITY_CONFIGURATION_ERROR)


def _selector_from_source(source: Any) -> tuple[bool, Any]:
    """Find an explicit selector only on known result/telemetry containers."""
    if isinstance(source, dict):
        for key in (*_OUTPUT_DURABILITY_SELECTOR_KEYS, *_OUTPUT_DURABILITY_CONFIG_FLAGS):
            if key in source:
                return True, source[key]
        for key in (
            "result", "data", "golden_telemetry", "telemetry", "metadata",
            "request", "workload", "options",
        ):
            nested = source.get(key)
            found, value = _selector_from_source(nested)
            if found:
                return True, value
    return False, None


def _resolve_output_durability_mode(*sources: Any, config: Any = None) -> str:
    """Resolve request-output durability with result evidence taking priority.

    Missing selectors are ``off``.  An invalid explicit selector raises the
    same configuration error as the runtime resolver.  Config is consulted
    only when the authoritative result surfaces do not carry a selector.
    """
    observed_modes: list[str] = []
    environment_mode: str | None = None
    environment_value = os.environ.get("COMFYMODAL_OUTPUT_DURABILITY")
    if environment_value is not None:
        # Validate the actual process selector even when result/config
        # evidence is present.  Runtime would reject an invalid selector
        # before producing that evidence.
        environment_mode = _normalize_output_durability_mode(environment_value)
    for source in sources:
        found, value = _selector_from_source(source)
        if found:
            observed_modes.append(_normalize_output_durability_mode(value))
    # Validate every explicit resolved-config selector even when a result
    # surface is present.  The runtime cannot execute with an invalid config
    # and the validator must not hide that error behind result precedence.
    if config is not None:
        for name in _OUTPUT_DURABILITY_CONFIG_FLAGS:
            try:
                flag = config.flag(name)
            except Exception:  # noqa: BLE001 - duck-typed validation config
                flag = None
            if flag is not None:
                _normalize_output_durability_mode(getattr(flag, "value", flag))
        for flag in getattr(config, "flags", ()) or ():
            if getattr(flag, "name", "") in _OUTPUT_DURABILITY_CONFIG_FLAGS:
                _normalize_output_durability_mode(getattr(flag, "value", flag))
        for name in _OUTPUT_DURABILITY_SELECTOR_KEYS:
            value = getattr(config, name, None)
            if value is not None:
                _normalize_output_durability_mode(value)
        workload = getattr(config, "workload", None)
        if isinstance(workload, dict):
            found, value = _selector_from_source(workload)
            if found:
                _normalize_output_durability_mode(value)
    if observed_modes:
        # Conflicting evidence fails closed.  Invalid values have already
        # raised above, rather than being hidden by an explicit off surface.
        return "strict" if all(mode == "strict" for mode in observed_modes) else "off"
    if config is not None:
        for name in _OUTPUT_DURABILITY_CONFIG_FLAGS:
            try:
                flag = config.flag(name)
            except Exception:  # noqa: BLE001 - duck-typed validation config
                flag = None
            if flag is not None:
                return _normalize_output_durability_mode(getattr(flag, "value", flag))
        for flag in getattr(config, "flags", ()) or ():
            if getattr(flag, "name", "") in _OUTPUT_DURABILITY_CONFIG_FLAGS:
                return _normalize_output_durability_mode(getattr(flag, "value", flag))
        for name in _OUTPUT_DURABILITY_SELECTOR_KEYS:
            value = getattr(config, name, None)
            if value is not None:
                return _normalize_output_durability_mode(value)
        workload = getattr(config, "workload", None)
        if isinstance(workload, dict):
            found, value = _selector_from_source(workload)
            if found:
                return _normalize_output_durability_mode(value)
    if environment_mode is not None:
        return environment_mode
    if _runtime_resolve_output_durability is not None:
        try:
            return str(_runtime_resolve_output_durability().mode)
        except Exception as exc:  # noqa: BLE001 - preserve runtime config semantics
            raw = os.environ.get("COMFYMODAL_OUTPUT_DURABILITY")
            error_type = _RuntimeOutputDurabilityConfigurationError or ValueError
            if raw not in (None, ""):
                raise error_type(_OUTPUT_DURABILITY_CONFIGURATION_ERROR) from exc
            raise
    return "off"


def _output_durability_selector_present(*sources: Any, config: Any = None) -> bool:
    for source in sources:
        if _selector_from_source(source)[0]:
            return True
    # An environment selector is explicit even when it selects ``off`` (or
    # contains an invalid value).  It must prevent selector-less historical
    # evidence from being upgraded to strict.
    if os.environ.get("COMFYMODAL_OUTPUT_DURABILITY") is not None:
        return True
    if config is not None:
        for name in _OUTPUT_DURABILITY_CONFIG_FLAGS:
            try:
                if config.flag(name) is not None:
                    return True
            except Exception:  # noqa: BLE001 - duck-typed validation config
                pass
        if any(
            getattr(flag, "name", "") in _OUTPUT_DURABILITY_CONFIG_FLAGS
            for flag in (getattr(config, "flags", ()) or ())
        ):
            return True
        if any(getattr(config, name, None) is not None for name in _OUTPUT_DURABILITY_SELECTOR_KEYS):
            return True
        workload = getattr(config, "workload", None)
        if isinstance(workload, dict) and _selector_from_source(workload)[0]:
            return True
    return False


# Public spelling for callers that want to share the exact parser without
# importing any runtime/model-loading code.
resolve_output_durability_mode = _resolve_output_durability_mode


def _output_proof_truthy(value: Any) -> bool:
    if isinstance(value, dict):
        for key in ("ok", "valid", "verified", "ready", "complete", "success"):
            if key in value:
                return _output_proof_truthy(value[key])
        if any(value.get(key) for key in ("asset_id", "output_sha", "content_sha256", "sha256")):
            return True
        status = str(value.get("status", "")).strip().lower()
        return status in {"ready", "complete", "completed", "ok", "success", "valid"}
    if isinstance(value, str):
        return value.strip().lower() in {
            "1", "true", "yes", "on", "ok", "ready", "complete", "completed", "success", "valid",
        }
    return value is True


def _result_ready_proof(*sources: Any) -> Any:
    keys = (
        "result_ready", "result_ready_proof", "result_ready_marked",
        "first_result_ready", "first_result_ready_marked",
    )
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key in source:
                return source[key]
        for key in ("result", "data", "golden_telemetry", "telemetry", "metadata"):
            value = _result_ready_proof(source.get(key))
            if value is not None:
                return value
    return None


def _durability_context_is_distinct_publication(context: tuple[str, ...]) -> bool:
    """Keep unrelated S4/publication commits out of the output gate.

    The control plane can carry several ledgers in one artifact.  A commit in
    an explicitly named S4/publication container is not generated-output
    durability evidence; an ``output_*`` container remains authoritative even
    when it also mentions publication.
    """
    joined = "_".join(context)
    publication_index = next(
        (index for index, token in enumerate(context)
         if "publication" in token or "published" in token or token == "s4"),
        None,
    )
    if publication_index is None:
        return False
    publication = any(token in joined for token in ("publication", "published"))
    s4 = "s4" in joined
    # Only the path leading into the named publication branch determines
    # whether it is distinct.  ``s4_publication.fsync`` is still distinct;
    # ``output_publication.fsync`` is generated-output persistence.
    parent = "_".join(context[:publication_index])
    generated_output = any(
        token in parent
        for token in ("output", "asset", "durable", "sidecar", "fsync")
    )
    return (publication or s4) and not generated_output


def _durability_key_kind(key: Any) -> str | None:
    normalized = str(key).strip().lower().replace("-", "_")
    if normalized in {"true_durable", "true_durable_marked", "result_durable"}:
        return "true_durable"
    if normalized in {"pending_durability", "pendingdurability", "durability_invoked",
                      "output_durability_invoked"}:
        return "pending_durability"
    if normalized in {"asset_write", "asset_write_done", "output_asset_write",
                      "output_asset_write_ms", "file_written", "output_file_written"}:
        return "asset_write"
    if normalized in {"fsync", "output_fsync", "asset_fsync", "output_fsync_ms"}:
        return "fsync"
    if "sidecar" in normalized:
        return "sidecar"
    if normalized in {"commit", "volume_commit", "volume_commit_start",
                      "volume_commit_complete", "output_commit"}:
        return "commit"
    if normalized in {"reopen", "reopen_verified", "durable_reopen",
                      "durable_reopen_verified"}:
        return "reopen"
    if normalized in {"true_first_durable_result", "first_durable_result"}:
        return "true_first"
    if normalized == "output_durability":
        return "pending_durability"
    if "asset_write" in normalized or normalized.endswith("file_written"):
        return "asset_write"
    if "fsync" in normalized:
        return "fsync"
    if "sidecar" in normalized:
        return "sidecar"
    if "pending_durability" in normalized or "durable_commit" in normalized:
        return "pending_durability" if "pending" in normalized else "commit"
    if "durable_reopen" in normalized:
        return "reopen"
    if "true_first_durable_result" in normalized:
        return "true_first"
    return None


def _durability_claim_value(value: Any, kind: str) -> bool:
    """Whether a field is positive persistence evidence (rather than absent)."""
    if kind in {"commit", "reopen", "true_first"} and value not in (None, False, "", 0):
        return True
    if isinstance(value, dict):
        # A structured operation record is evidence unless it explicitly says
        # that the operation was skipped/false.
        for key in ("ok", "success", "completed", "performed", "invoked", "enabled"):
            if key in value:
                return _output_proof_truthy(value[key])
        status = str(value.get("status", "")).strip().lower()
        if status in {"skipped", "not_run", "disabled", "false", "off"}:
            return False
        return True
    return _output_proof_truthy(value) or (
        kind in {"asset_write", "fsync", "sidecar", "pending_durability"}
        and value not in (None, False, "", 0, 0.0)
    )


def _golden_durability_claimed(*sources: Any) -> bool:
    """Detect generated-output persistence work without treating absent evidence as 0ms."""
    def visit(value: Any, context: tuple[str, ...] = ()) -> bool:
        if isinstance(value, dict):
            name = str(value.get("name", "")).strip().lower().replace("-", "_")
            if name and not _durability_context_is_distinct_publication(context + (name,)):
                name_kind = _durability_key_kind(name)
                if name_kind is not None:
                    return True
                if any(token in name for token in (
                    "durable_commit", "durable_reopen", "output_persist",
                    "asset_write", "output_fsync", "sidecar",
                )):
                    return True
            for key, child in value.items():
                normalized = str(key).strip().lower().replace("-", "_")
                child_context = context + (normalized,)
                if _durability_context_is_distinct_publication(child_context):
                    continue
                if normalized not in _OUTPUT_DURABILITY_SELECTOR_KEYS:
                    kind = _durability_key_kind(normalized)
                    if kind is not None and _durability_claim_value(child, kind):
                        return True
                if visit(child, child_context):
                    return True
        elif isinstance(value, list):
            return any(visit(item, context) for item in value)
        return False

    for source in sources:
        if visit(source):
            return True
    return False


def _historical_pre_selector_strict(*sources: Any) -> bool:
    """Recognize only the old, explicitly durable ledger shape.

    Before RA7B there was no selector.  Such artifacts remain readable only
    when their canonical ledger contains the old strict endpoint and positive
    durability evidence; an arbitrary selector-less result is not upgraded to
    strict merely because it lacks a field.
    """
    for source in sources:
        if not isinstance(source, dict):
            continue
        ledger = source.get("canonical_ledger")
        if isinstance(ledger, dict) and str(ledger.get("endpoint_status", "")).lower() == "ok":
            serial = ledger.get("serial_ledger")
            if isinstance(serial, dict) or _golden_durability_claimed(source):
                return True
        if (
            (source.get("true_durable") is True or source.get("true_durable_marked") is True)
            and source.get("reopen_verified") is True
            and _golden_durability_claimed(source)
        ):
            return True
    return False


def _canonical_evidence_timestamp(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    for key in ("mono_ns", "monotonic_ns", "wall_ns", "wall_unix_ns",
                "end_wall_ns", "entry_wall_ns", "timestamp", "time"):
        raw = value.get(key)
        if isinstance(raw, bool) or raw is None:
            continue
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str) and raw.strip():
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _canonical_event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event)
    metadata = event.get("metadata")
    if isinstance(metadata, dict):
        payload.update(metadata)
    fields = event.get("fields")
    if isinstance(fields, dict):
        payload.update(fields)
    return payload


def _named_proof_value(source: Any, key: str) -> Any:
    """Read a proof field from the known artifact/telemetry containers."""
    if not isinstance(source, dict):
        return None
    if key in source:
        return source[key]
    for nested_key in (
        "result", "data", "golden_telemetry", "telemetry", "metadata",
        "canonical_ledger",
    ):
        value = _named_proof_value(source.get(nested_key), key)
        if value is not None:
            return value
    return None


def _canonical_commit_reopen_order(ledger: dict[str, Any]) -> bool | None:
    """Return ordering from authoritative ledger events, or ``None`` absent."""
    events = ledger.get("events")
    if not isinstance(events, list):
        return None
    commits: list[float] = []
    reopens: list[float] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        name = str(event.get("name", "")).strip().lower().replace("-", "_")
        payload = _canonical_event_payload(event)
        stamp = _canonical_evidence_timestamp(event) or _canonical_evidence_timestamp(payload)
        if stamp is None:
            continue
        if "commit" in name and "result" not in name:
            commits.append(stamp)
        if "reopen" in name:
            reopens.append(stamp)
    if not commits or not reopens:
        return None
    return min(commits) <= min(reopens)


class GoldenCohortValidator(ValidatorPlugin):
    """Validate the dedicated Golden cohort/attempt artifact contract.

    ``run_golden_serial_stream`` does not emit the generic run-plan artifact.
    The harness has already performed the detailed event validation; v2ctl
    verifies that its immutable result is present, internally consistent,
    hash-intact, and matches the current profile before accepting it.  A
    configured output SHA mismatch is accepted only when the attempt records
    the actual, well-formed SHA together with explicit expected/observed
    warning evidence.
    """

    name = "golden_cohort"

    @staticmethod
    def _load(path: Any) -> dict[str, Any] | None:
        if path is None:
            return None
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError, TypeError):
            return None
        return value if isinstance(value, dict) else None

    def validate(self, record: RunRecord, config: Any) -> list[str]:
        if not _is_golden_profile(config):
            return []

        failures: list[str] = []
        artifacts = record.artifacts
        manifest_path = getattr(artifacts, "campaign_manifest", None)
        attempt_path = getattr(artifacts, "run_artifact", None)
        summary_path = getattr(artifacts, "summary_artifact", None)
        manifest = self._load(manifest_path)
        attempt = self._load(attempt_path)
        summary = self._load(summary_path)
        if manifest is None or manifest_path is None or not Path(manifest_path).is_file():
            failures.append("Golden cohort manifest missing or unreadable")
            return failures
        if attempt is None or attempt_path is None or not Path(attempt_path).is_file():
            failures.append("Golden attempt artifact missing or unreadable")
            return failures
        if summary is None or summary_path is None or not Path(summary_path).is_file():
            failures.append("Golden summary artifact missing or unreadable")
        if not record.backend_ok:
            failures.append(
                "Golden backend invocation did not complete successfully"
                f" (exit code {record.backend_exit_code if record.backend_exit_code is not None else 'unknown'})"
            )

        # New Golden writers may carry an explicit workflow contract.  It is
        # mandatory once present, but old P2 artifacts remain readable because
        # they have no contract metadata at all.
        contract_sources = [manifest, attempt]
        metadata_keys = ("workflow_contract", "workflow_identity", "provenance", "workflow",
                         "identity", "golden_telemetry", "metadata")
        for artifact in (manifest, attempt):
            for key in metadata_keys:
                nested = artifact.get(key)
                if isinstance(nested, dict):
                    contract_sources.append(nested)
                    for child_key in metadata_keys:
                        child = nested.get(child_key)
                        if isinstance(child, dict):
                            contract_sources.append(child)
        contract_markers = WORKFLOW_CONTRACT_MARKERS
        for contract in contract_sources:
            if any(key in contract for key in contract_markers):
                failures.extend(workflow_contract_failures(contract))
                break
        if Path(manifest_path).resolve().parent != Path(attempt_path).resolve().parent:
            failures.append("Golden manifest and attempt artifacts are from different cohorts")
        if summary_path is not None and Path(summary_path).resolve().parent != Path(attempt_path).resolve().parent:
            failures.append("Golden summary and attempt artifacts are from different cohorts")

        # The v2ctl invocation is the root of the binding chain.  Do not let a
        # valid-looking neighboring cohort satisfy this request.
        expected_invocation = str(record.v2ctl_invocation_id or "").strip()
        nested_manifest = manifest.get("v2ctl")
        observed_invocation = str(
            manifest.get("v2ctl_invocation_id")
            or (nested_manifest.get("invocation_id", "")
                if isinstance(nested_manifest, dict) else "")
        ).strip()
        if not observed_invocation:
            failures.append("Golden manifest invocation ID is missing")
        elif expected_invocation and observed_invocation != expected_invocation:
            failures.append("Golden manifest invocation ID does not match v2ctl binding")
        for label, data in (("summary", summary), ("attempt", attempt)):
            if not isinstance(data, dict):
                continue
            observed = str(data.get("v2ctl_invocation_id") or "").strip()
            if not observed:
                failures.append(f"Golden {label} invocation ID is missing")
            elif expected_invocation and observed != expected_invocation:
                failures.append(f"Golden {label} invocation ID does not match v2ctl binding")

        target = getattr(config, "target", None)
        resources = getattr(config, "resources", None)
        expected_target = {
            "app_name": str(getattr(target, "app", "") or ""),
            "class_name": str(getattr(target, "class_name", "") or ""),
            "gpu": str(getattr(resources, "gpu", "") or ""),
        }
        observed_target = manifest.get("target")
        expected_mode, expected_method, expected_golden_mode, require_seriality = _golden_contract(config)
        if manifest.get("mode") != expected_mode:
            failures.append(f"Golden cohort mode is not {expected_mode}")
        if manifest.get("method") != expected_method:
            failures.append(f"Golden cohort method is not {expected_method}")
        if expected_golden_mode == "parallel" and manifest.get("golden_mode") != "parallel":
            failures.append("Golden cohort golden_mode is not parallel")
        if not isinstance(observed_target, dict) or any(
            observed_target.get(key) != value for key, value in expected_target.items()
        ):
            failures.append("Golden cohort target identity does not match config")

        expected_sha = str(getattr(getattr(config, "workload", None), "expected_output_sha", "") or "").strip()
        if not expected_sha:
            failures.append("Golden expected output SHA is missing")
        if manifest.get("expected_output_sha") != expected_sha:
            failures.append("Golden cohort expected output SHA does not match config")
        workflow = manifest.get("workflow")
        if not isinstance(workflow, dict) or not all(
            isinstance(workflow.get(key), str) and workflow[key].strip()
            for key in ("workflow_hash", "prompt_sha256")
        ):
            failures.append("Golden cohort workflow hash proof is missing")

        counts = {
            "run_count_requested": 1,
            "attempt_count": 1,
            "valid_count": 1,
            "invalid_count": 0,
            "dnf_count": 0,
        }
        for key, expected in counts.items():
            if manifest.get(key) != expected:
                failures.append(f"Golden cohort {key}={manifest.get(key)!r}; expected {expected}")

        attempts = manifest.get("attempts")
        manifest_attempt = attempts[0] if isinstance(attempts, list) and len(attempts) == 1 else None
        request_id = str(attempt.get("request_id") or "").strip()
        if not request_id or not isinstance(manifest_attempt, dict) or str(
            manifest_attempt.get("request_id") or ""
        ).strip() != request_id:
            failures.append("Golden cohort attempt request identity is inconsistent")
        if not record.request_id:
            failures.append("effective provenance missing request_id")
        elif record.request_id != request_id:
            failures.append("Golden attempt request ID does not match v2ctl binding")
        if attempt.get("mode") != expected_mode or attempt.get("method") != expected_method:
            failures.append("Golden attempt method/mode proof is missing")
        if expected_golden_mode == "parallel" and attempt.get("golden_mode") != "parallel":
            failures.append("Golden attempt golden_mode proof is missing")
        if attempt.get("valid") is not True or attempt.get("dnf") is not False:
            failures.append("Golden attempt did not validate")
        if attempt.get("failures") != []:
            failures.append("Golden attempt contains validation failures")
        validation = attempt.get("validation")
        observed_shas = validation.get("observed_output_shas") if isinstance(validation, dict) else None
        observed_sha = None
        if not isinstance(observed_shas, list) or len(observed_shas) != 1:
            failures.append("Golden attempt output SHA proof is missing or ambiguous")
        elif not isinstance(observed_shas[0], str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", observed_shas[0].strip()
        ):
            failures.append("Golden attempt output SHA proof is malformed")
        else:
            observed_sha = observed_shas[0].strip()
            if observed_sha.lower() != expected_sha.lower():
                warning = validation.get("output_sha_warning") if isinstance(validation, dict) else None
                warning_expected = warning.get("expected") if isinstance(warning, dict) else None
                warning_observed = warning.get("observed") if isinstance(warning, dict) else None
                warning_ok = (
                    isinstance(warning_expected, str)
                    and isinstance(warning_observed, str)
                    and warning_expected.strip().lower() == expected_sha.lower()
                    and warning_observed.strip().lower() == observed_sha.lower()
                )
                if not warning_ok:
                    failures.append(
                        "Golden attempt output SHA mismatch lacks explicit warning evidence"
                    )
            elif isinstance(validation, dict) and validation.get("output_sha_warning"):
                failures.append("Golden attempt output SHA warning contradicts matching SHA")
        if record.output_sha is not None:
            if not isinstance(record.output_sha, str) or not re.fullmatch(
                r"[0-9a-fA-F]{64}", record.output_sha.strip()
            ):
                failures.append("Golden record output SHA is malformed")
            elif observed_sha is not None and record.output_sha.strip().lower() != observed_sha.lower():
                failures.append("Golden record output SHA disagrees with attempt proof")
        telemetry = attempt.get("golden_telemetry")
        selector_present = _output_durability_selector_present(
            attempt, telemetry, manifest, config=config
        )
        try:
            output_durability_mode = _resolve_output_durability_mode(
                attempt, telemetry, manifest, config=config
            )
        except ValueError as exc:
            failures.append(str(exc))
            output_durability_mode = "off"
        if not selector_present and _historical_pre_selector_strict(attempt, telemetry, manifest):
            # Compatibility is limited to genuinely old strict artifacts.  A
            # selector-less modern artifact remains off, rather than gaining a
            # durable endpoint from missing metadata.
            output_durability_mode = "strict"
        if output_durability_mode == "off":
            # Request-output durability is deliberately opt-in.  The result
            # endpoint is still required, but a result-ready artifact must not
            # be promoted to a durable result by this validator.
            result_ready = _result_ready_proof(attempt, telemetry)
            if not _output_proof_truthy(result_ready):
                failures.append("Golden result-ready proof is missing or false")
            integrity_values = [
                source[key]
                for source in (attempt, telemetry if isinstance(telemetry, dict) else {})
                for key in ("output_integrity", "output_identity")
                if key in source
            ]
            if integrity_values and not all(_output_proof_truthy(value) for value in integrity_values):
                failures.append("Golden output integrity proof is false")
            if _golden_durability_claimed(attempt, telemetry):
                failures.append(
                    "Golden output durability evidence is contradictory in off mode"
                )
        if not isinstance(telemetry, dict) or not str(telemetry.get("schema", "")).startswith("golden_"):
            failures.append("Golden telemetry proof is missing")
        if isinstance(telemetry, dict):
            if output_durability_mode == "strict":
                if telemetry.get("true_durable_marked") is not True:
                    failures.append("Golden durable-result proof is missing")
                if telemetry.get("reopen_verified") is not True:
                    failures.append("Golden durable reopen proof is missing")
        if require_seriality:
            seriality = attempt.get("seriality") or (telemetry or {}).get("seriality")
            if not isinstance(seriality, dict) or seriality.get("ok") is not True or seriality.get("count") != 0:
                failures.append("Golden strict-seriality proof is missing or failed")

        # The Golden writer hashes all immutable sibling artifacts.  Verify
        # those hashes here so a valid flag in a modified attempt cannot pass.
        hashes = manifest.get("artifact_file_hashes")
        if not isinstance(hashes, dict) or not hashes:
            failures.append("Golden cohort artifact hashes are missing")
        else:
            parent = Path(manifest_path).resolve().parent
            for relative, expected in hashes.items():
                candidate = (parent / str(relative)).resolve()
                try:
                    candidate.relative_to(parent)
                except ValueError:
                    failures.append(f"Golden artifact hash path escapes cohort: {relative}")
                    continue
                if not candidate.is_file():
                    failures.append(f"Golden artifact hash file missing: {relative}")
                    continue
                observed = hashlib.sha256(candidate.read_bytes()).hexdigest()
                if str(expected).lower() != observed:
                    failures.append(f"Golden artifact hash mismatch: {relative}")

        if not str(record.v2ctl_invocation_id or "").strip():
            failures.append("effective provenance missing v2ctl_invocation_id")
        if not str(record.profile_config_fingerprint or "").strip():
            failures.append("effective provenance missing profile_config_fingerprint")
        if record.provenance_validation_status != "validated":
            failures.append("effective provenance was not canonically validated")

        # Backend selection is resolved before dispatch and must be observable
        # in the persisted cohort.  Selector-less historical fixtures remain
        # readable, but identity-bound modern cohorts fail closed.
        expected_backend = str(record.attention_backend or "").strip().lower()
        if not expected_backend:
            try:
                expected_backend = resolved_attention_backend(config)
            except ValueError as exc:
                failures.append(str(exc))
                expected_backend = ""
        observed_backends: set[str] = set()
        if record.attention_backend:
            # The control-plane command/env is the resolved pre-dispatch
            # authority when an older Golden writer does not repeat the
            # selector in its cohort JSON.  Any contradictory cohort value is
            # still rejected below.
            observed_backends.add(record.attention_backend.strip().lower())
        for data in (manifest, summary, attempt):
            if not isinstance(data, dict):
                continue
            for key in ("attention_backend", "resolved_attention_backend"):
                if data.get(key) not in (None, ""):
                    observed_backends.add(str(data[key]).strip().lower())
            telemetry = data.get("golden_telemetry")
            if isinstance(telemetry, dict) and telemetry.get("attention_backend") not in (None, ""):
                observed_backends.add(str(telemetry["attention_backend"]).strip().lower())
        if len(observed_backends) > 1:
            failures.append("Golden cohort contains mixed attention backends")
        elif observed_backends and expected_backend and observed_backends != {expected_backend}:
            failures.append("Golden attention backend does not match resolved experiment identity")
        elif expected_invocation and not observed_backends:
            failures.append("Golden attention backend evidence is missing")

        expected_arm = str(record.golden_arm or "control").strip().lower()
        observed_arms: set[str] = set()
        if record.golden_arm:
            observed_arms.add(expected_arm)

        def collect_arm(value: Any) -> None:
            if isinstance(value, dict):
                if value.get("golden_arm") not in (None, ""):
                    observed_arms.add(str(value["golden_arm"]).strip().lower())
                if "cpu_qd2_prefetch" in value:
                    raw_qd2 = value["cpu_qd2_prefetch"]
                    observed_arms.add(
                        "cpu_qd2_prefetch"
                        if raw_qd2 is True
                        or str(raw_qd2).strip().lower() in {"1", "true", "yes", "on"}
                        else "control"
                    )
                for child in value.values():
                    collect_arm(child)
            elif isinstance(value, list):
                for child in value:
                    collect_arm(child)

        for data in (manifest, summary, attempt):
            collect_arm(data)
        if len(observed_arms) > 1:
            failures.append("Golden cohort contains mixed request arms")
        elif observed_arms and observed_arms != {expected_arm}:
            failures.append("Golden request arm does not match resolved experiment identity")

        def contains_instant_tensor(value: Any) -> bool:
            if isinstance(value, dict):
                return any(
                    (str(key).lower() == "instant_tensor" or "instanttensor" in str(key).lower())
                    and child is True
                    or contains_instant_tensor(child)
                    for key, child in value.items()
                )
            if isinstance(value, list):
                return any(contains_instant_tensor(child) for child in value)
            return False

        if any(contains_instant_tensor(data) for data in (manifest, summary, attempt)):
            failures.append("Golden control/QD2 arm cannot mix InstantTensor")
        return failures


class CanonicalLedgerValidator(ValidatorPlugin):
    """E29 tracer-gate validator: the canonical ledger is the authoritative
    ground-truth payload and lives in ``data["canonical_ledger"]`` (with
    ``canonical_ledger_status``) — NOT in ordinary RuntimeTrace events.

    Fails a run whose canonical ledger is missing, errored, or does not have
    the explicit authoritative endpoints + a zero-gap serial ledger.  This
    makes it impossible for a run with a missing/broken ledger to be
    classified as a valid E29 tracer run."""

    name = "canonical_ledger"

    def validate(self, record: RunRecord, config: Any) -> list[str]:
        # The profile must enable the E29 ledger for this validator to apply.
        flag = "COMFYMODAL_V2_CRITICAL_PATH_LEDGER"
        try:
            fl = config.flag(flag)
        except Exception:
            fl = None
        if fl is None or str(getattr(fl, "value", fl or "")).strip().lower() not in (
            "1", "true", "yes", "on",
        ):
            # Ledger not enabled for this run → nothing to validate here
            # (a non-tracer profile must not fail on a missing ledger).
            return []

        telemetry = record.telemetry or {}
        artifact = _artifact_data(record)
        selector_present = _output_durability_selector_present(
            telemetry, artifact, config=config
        )
        failures: list[str] = []
        try:
            output_durability_mode = _resolve_output_durability_mode(
                telemetry, artifact, config=config
            )
        except ValueError as exc:
            return [str(exc)]
        historical = (
            not selector_present
            and isinstance(artifact.get("canonical_ledger"), dict)
            and _historical_pre_selector_strict(artifact, telemetry)
        )
        if historical:
            # Compatibility is intentionally limited to the recognized
            # pre-selector canonical ledger shape.
            output_durability_mode = "strict"
        if output_durability_mode == "off" and _golden_durability_claimed(telemetry, artifact):
            return ["canonical ledger contains output durability evidence in off mode"]
        status = str(
            telemetry.get("canonical_ledger_status")
            or artifact.get("canonical_ledger_status")
            or ""
        )
        if status == "error":
            return [
                "canonical ledger finalization errored on the remote "
                "(canonical_ledger_status=error)"
            ]
        if status == "ok":
            ledger = artifact.get("canonical_ledger")
            ledger = ledger if isinstance(ledger, dict) else {}
            ledger_endpoint = ledger.get("endpoint")
            if isinstance(ledger_endpoint, dict):
                ledger_endpoint = ledger_endpoint.get("status") or ledger_endpoint.get("name")
            endpoint_status = str(
                ledger.get("endpoint_status")
                or ledger_endpoint
                or telemetry.get("canonical_ledger_endpoint_status")
                or ""
            ).strip().lower().replace("-", "_")
            if output_durability_mode == "strict":
                # Current strict runs must name the durable endpoint.  The
                # historical ``ok`` endpoint is accepted only above.
                accepted_endpoint_statuses = {
                    "true_durable", "true_durable_result", "first_durable_result",
                }
                if historical:
                    accepted_endpoint_statuses.add("ok")
            else:
                accepted_endpoint_statuses = {"result_ready", "first_result_ready"}
            if endpoint_status not in accepted_endpoint_statuses:
                failures.append(
                    f"canonical ledger endpoint_status={endpoint_status or '(missing)'}: "
                    "explicit authoritative endpoints (remote_python_resume -> "
                    f"{'first_durable_result' if output_durability_mode == 'strict' else 'result_ready'}"
                    ") are required"
                )
            serial_zero_gap = telemetry.get("canonical_ledger_zero_gap")
            if serial_zero_gap is None:
                serial_zero_gap = ledger.get("serial_ledger", {}).get("zero_gap") \
                    if isinstance(ledger.get("serial_ledger"), dict) else None
            if not _runtime_bool(serial_zero_gap):
                failures.append("canonical ledger serial zero-gap did not pass")
            if output_durability_mode == "off":
                ready = _result_ready_proof(telemetry, artifact)
                if not _output_proof_truthy(ready):
                    failures.append("canonical ledger result-ready proof missing")
            elif not historical:
                durable_marked = any(
                    _runtime_bool(_named_proof_value(source, key))
                    for source in (telemetry, artifact)
                    for key in ("true_durable", "true_durable_marked")
                )
                if not durable_marked:
                    failures.append("canonical ledger true_durable/true_durable_marked proof missing")
                reopen_verified = any(
                    _runtime_bool(_named_proof_value(source, "reopen_verified"))
                    for source in (telemetry, artifact)
                )
                if not reopen_verified:
                    failures.append("canonical ledger reopen_verified proof missing")
                ordering = _canonical_commit_reopen_order(ledger)
                if ordering is not True:
                    failures.append(
                        "canonical ledger commit-before-reopen ordering proof missing or invalid"
                    )
            return failures
        # status absent → canonical ledger missing from the artifact entirely.
        return [
            "canonical ledger missing from the run artifact "
            "(canonical_ledger_status absent): an E29 tracer run must attach "
            "canonical_ledger + canonical_ledger_status"
        ]


def _flag_enabled(config: Any, name: str) -> bool:
    """Read one resolved flag without making validation depend on Config types."""
    try:
        flag = config.flag(name)
    except Exception:  # noqa: BLE001 - validation is deliberately duck-typed
        flag = None
    if flag is not None:
        value = getattr(flag, "value", flag)
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    for flag in getattr(config, "flags", ()) or ():
        if getattr(flag, "name", "") == name:
            return str(getattr(flag, "value", "")).strip().lower() in (
                "1", "true", "yes", "on",
            )
    return False


def _artifact_data(record: RunRecord) -> dict[str, Any]:
    """Load the persisted run artifact, returning an empty mapping on error."""
    path = _artifact_run_path(record)
    if path is None:
        return {}
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _e31_trace_events(data: dict[str, Any], telemetry: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ordinary trace events carrying E31 proof and cache observations.

    E31's *timing* evidence is authoritative only on the canonical ledger.  Its
    residency/bind and cache facts are emitted on the ordinary trace, so this
    helper intentionally reads only the known trace containers rather than
    recursively accepting arbitrary nested dictionaries.
    """
    events: list[dict[str, Any]] = []
    sources: list[Any] = [data, telemetry]
    for root in (data, telemetry):
        for source in (root.get("result"), root.get("full_trace"), root.get("trace")):
            if isinstance(source, dict):
                sources.append(source)
                nested_trace = source.get("trace")
                if isinstance(nested_trace, dict):
                    sources.append(nested_trace)
    for source in sources:
        if not isinstance(source, dict):
            continue
        candidate = source.get("events")
        if isinstance(candidate, list):
            events.extend(item for item in candidate if isinstance(item, dict))
        # A few artifact writers persist these named proof records directly.
        for name, value in (
            ("clip_fh_cast_once_bind_proof", source.get("cast_once_bind_proof")),
            ("clip_fh_cast_once_forward_check", source.get("e31_forward_evidence")),
        ):
            if isinstance(value, dict):
                events.append({"name": name, "metadata": value})
    return events


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Flatten one trace event's metadata while preserving its scalar fields."""
    payload: dict[str, Any] = {}
    metadata = event.get("metadata")
    if isinstance(metadata, dict):
        payload.update(metadata)
    for key, value in event.items():
        if key not in {"name", "metadata", "phase", "wall_unix_ns", "monotonic_ns"}:
            payload.setdefault(key, value)
    return payload


def _named_e31_event(events: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for event in reversed(events):
        if str(event.get("name", "")) == name:
            return _event_payload(event)
    return None


def _nested_mapping(value: Any, *keys: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    for key in keys:
        nested = value.get(key)
        if isinstance(nested, dict):
            return nested
    return {}


def _number(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on", "ok", "pass")


class E31ForensicsValidator(ValidatorPlugin):
    """Fail-closed evidence gate for profiles with E31 forensics enabled.

    The canonical ledger is the only accepted source for forward GPU timing
    and real cast accounting.  In particular, the hydration result's
    ``conversion_count`` is intentionally never used: it describes the bind
    transform and cannot prove a real forward-time BF16->FP32 conversion.
    """

    name = "e31_forensics"

    def applies(self, config: Any) -> bool:
        return _flag_enabled(config, "COMFYMODAL_V2_E31_FORENSICS")

    def validate(self, record: RunRecord, config: Any) -> list[str]:
        if not self.applies(config):
            return []

        failures: list[str] = []
        data = _artifact_data(record)
        telemetry = record.telemetry or {}
        ledger = data.get("canonical_ledger")
        if not isinstance(ledger, dict):
            candidate = telemetry.get("canonical_ledger")
            ledger = candidate if isinstance(candidate, dict) else None
        status = data.get("canonical_ledger_status", telemetry.get("canonical_ledger_status"))
        if not isinstance(ledger, dict) or str(status or "").lower() != "ok":
            return [
                "authoritative E31 canonical ledger evidence missing "
                "(canonical_ledger_status=ok and canonical_ledger required)"
            ]

        canonical_events = ledger.get("events")
        if not isinstance(canonical_events, list):
            canonical_events = []
        canonical_names = {
            str(item.get("name", ""))
            for item in canonical_events
            if isinstance(item, dict)
        }
        required_canonical = {
            "clip_gpu_event_start",
            "clip_gpu_event_end",
            "clip_forward_cast_summary",
        }
        missing = sorted(required_canonical - canonical_names)
        if missing:
            failures.append(
                "authoritative E31 canonical ledger missing event evidence: "
                + ", ".join(missing)
            )
            return failures

        gpu_stamps = {
            str(item.get("name")): _number(item.get("mono_ns"))
            for item in canonical_events
            if isinstance(item, dict)
            and item.get("name") in {"clip_gpu_event_start", "clip_gpu_event_end"}
        }
        gpu_start = gpu_stamps.get("clip_gpu_event_start")
        gpu_end = gpu_stamps.get("clip_gpu_event_end")
        if gpu_start is None or gpu_end is None or gpu_start >= gpu_end:
            failures.append("authoritative E31 GPU event evidence has invalid boundaries")

        summary_event = next(
            (item for item in reversed(canonical_events)
             if isinstance(item, dict) and item.get("name") == "clip_forward_cast_summary"),
            None,
        )
        summary = _event_payload(summary_event or {})

        expected = str(_config_workload(config).get("expected_output_sha", "") or "").strip()
        if not expected:
            failures.append("E31 requires an expected output SHA")
        elif not record.output_sha:
            failures.append("E31 expected output SHA configured but no output SHA observed")
        elif record.output_sha != expected:
            failures.append(
                f"E31 output SHA mismatch: expected {expected}, observed {record.output_sha}"
            )

        workload = _config_workload(config)
        if str(workload.get("conditioning_cache", "") or "").strip().lower() != "forced_miss":
            failures.append("E31 requires conditioning_cache=forced_miss")

        events = _e31_trace_events(data, telemetry)
        lookup = _named_e31_event(events, "clip_conditioning_cache_lookup") or {}
        miss_count = _number(lookup.get("miss_count"))
        miss_decision = False
        for event in events:
            if event.get("name") != "clip_conditioning_cache_decision":
                continue
            payload = _event_payload(event)
            decision = str(payload.get("decision", "")).strip().lower()
            if decision in {"miss", "miss_stored", "miss_not_stored"}:
                miss_decision = True
                break
        if not ((miss_count is not None and miss_count > 0) or miss_decision):
            failures.append("E31 conditioning-cache miss evidence missing")

        real_count = _number(summary.get("real_conversions"))
        real_bytes = _number(summary.get("real_conversion_bytes"))
        source_dtypes = summary.get("source_dtypes")
        dest_dtypes = summary.get("dest_dtypes")
        bf16_count = _number(source_dtypes.get("torch.bfloat16")) if isinstance(source_dtypes, dict) else None
        fp32_count = _number(dest_dtypes.get("torch.float32")) if isinstance(dest_dtypes, dict) else None
        cast_once_on = _flag_enabled(config, "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE")

        if not cast_once_on:
            if real_count is None or real_count <= 0 or real_bytes is None or real_bytes <= 0:
                failures.append(
                    "E31 OFF requires canonical real BF16->FP32 conversion count and bytes "
                    "(hydration conversion_count is not accepted)"
                )
            if bf16_count is None or bf16_count <= 0 or fp32_count is None or fp32_count <= 0:
                failures.append("E31 OFF canonical cast summary lacks BF16 source/FP32 destination proof")
            return failures

        if real_count != 0 or real_bytes != 0:
            failures.append(
                "E31 ON requires zero canonical real conversions and zero real conversion bytes"
            )

        bind = _named_e31_event(events, "clip_fh_cast_once_bind_proof")
        applied = _named_e31_event(events, "clip_fh_cast_once_applied")
        forward = _named_e31_event(events, "clip_fh_cast_once_forward_check")
        if not bind or not _truth(bind.get("ok")):
            failures.append("E31 ON cast-once bind/residency proof missing or not valid")
        applied_params = _number((applied or {}).get("fp32_params"))
        if not applied or not (
            (applied_params is not None and applied_params > 0)
            or _truth((applied or {}).get("cast_once_applied"))
        ):
            failures.append("E31 ON cast-once applied proof missing")

        proof = bind or {}
        count_by_dtype = proof.get("count_by_dtype")
        device_counts = proof.get("device_counts")
        fp32_resident = (
            isinstance(count_by_dtype, dict)
            and (_number(count_by_dtype.get("torch.float32")) or 0) > 0
        )
        cuda_resident = (
            isinstance(device_counts, dict)
            and any((str(key).startswith("cuda") and (_number(value) or 0) > 0)
                    for key, value in device_counts.items())
        )
        if not fp32_resident:
            failures.append("E31 ON residency proof does not establish FP32 residency")
        if not cuda_resident:
            failures.append("E31 ON residency proof does not establish CUDA residency")

        generation = _number(proof.get("generation"))
        applied_generation = _number((applied or {}).get("generation"))
        if generation is None or generation <= 0 or applied_generation != generation:
            failures.append("E31 ON generation/bind proof is missing or inconsistent")

        if not forward:
            failures.append("E31 ON real-forward proof missing")
        else:
            if not _truth(forward.get("forward_observed")) or not _truth(
                forward.get("forward_actually_observed")
            ):
                failures.append("E31 ON real-forward observation missing")
            stability = _nested_mapping(forward, "post_forward_stability", "stability")
            if not (_truth(forward.get("storage_stable")) and
                    _truth(stability.get("storage_stable", forward.get("storage_stable")))):
                failures.append("E31 ON storage-stable residency proof missing")
            bind_generation = _number(forward.get("bind_generation"))
            post_generation = _number(forward.get("post_forward_generation"))
            if bind_generation != generation or post_generation != generation:
                failures.append("E31 ON forward generation does not match bind generation")

        return failures


# Descriptive compatibility alias for callers that name the seam by contract.
E31EvidenceValidator = E31ForensicsValidator


class E37StrictProofValidator(ValidatorPlugin):
    """Fail-closed control-plane proof gate for the E37 profiles.

    E37 deliberately keeps E31 diagnostics and FP32 cast-once disabled.  Its
    acceptance proof is instead the plan-validation fast path, a real
    conditioning-cache miss, the canonical first-durable ledger, and the
    source/v2ctl identity carried by the persisted artifact.
    """

    name = "e37_strict_proof"
    expected_output_sha = (
        "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"
    )

    def applies(self, config: Any) -> bool:
        return _flag_enabled(config, "COMFYMODAL_V2_E37_STRICT_PROOF") or str(
            getattr(config, "profile_name", "") or ""
        ).startswith("e37-")

    def validate(self, record: RunRecord, config: Any) -> list[str]:
        if not self.applies(config):
            return []

        failures: list[str] = []
        data = _artifact_data(record)
        events = _e31_trace_events(data, record.telemetry or {})

        workload = _config_workload(config)
        configured_sha = str(workload.get("expected_output_sha", "") or "").strip()
        if configured_sha != self.expected_output_sha:
            failures.append(
                "E37 requires the canonical expected output SHA "
                f"{self.expected_output_sha}, configured {configured_sha or '(missing)'}"
            )
        if record.output_sha != self.expected_output_sha:
            failures.append(
                "E37 exact output SHA mismatch: expected "
                f"{self.expected_output_sha}, observed {record.output_sha or '(missing)'}"
            )
        if str(workload.get("conditioning_cache", "") or "").strip().lower() != "forced_miss":
            failures.append("E37 requires conditioning_cache=forced_miss")

        # Batch-C proves consumed=True, but E37 additionally requires the
        # decision reason to be explicitly present and empty.  Absence is not
        # equivalent to an empty reason.
        proof_events = [
            _event_payload(event)
            for event in events
            if event.get("name") == "plan_proof_decision"
        ]
        proof = proof_events[-1] if proof_events else None
        if not isinstance(proof, dict):
            failures.append("E37 consumed plan proof missing")
        else:
            if not _truth(proof.get("consumed")):
                failures.append("E37 consumed plan proof must have consumed=True")
            if proof.get("decision") != "plan_validation_fast_path":
                failures.append("E37 plan proof decision is not plan_validation_fast_path")
            if "reason" not in proof or proof.get("reason") != "":
                failures.append("E37 plan proof reason must be explicitly empty")

        lookup = _named_e31_event(events, "clip_conditioning_cache_lookup") or {}
        miss_count = _number(lookup.get("miss_count"))
        miss_observed = miss_count is not None and miss_count > 0
        if lookup.get("hit") is False or str(lookup.get("hit", "")).strip().lower() in {
            "0", "false", "no", "off",
        }:
            miss_observed = True
        for event in events:
            if event.get("name") != "clip_conditioning_cache_decision":
                continue
            decision = str(_event_payload(event).get("decision", "")).strip().lower()
            if decision in {"miss", "miss_stored", "miss_not_stored"}:
                miss_observed = True
                break
        if not miss_observed:
            failures.append("E37 actual conditioning-cache miss evidence missing")

        # The canonical ledger is authoritative.  Require both its explicit
        # endpoint/zero-gap contract and the durable boundary event itself.
        ledger = data.get("canonical_ledger")
        if not isinstance(ledger, dict):
            candidate = (data.get("result") or {}).get("canonical_ledger")
            ledger = candidate if isinstance(candidate, dict) else None
        status = data.get("canonical_ledger_status")
        if status is None and isinstance(data.get("result"), dict):
            status = data["result"].get("canonical_ledger_status")
        if not isinstance(ledger, dict) or str(status or "").lower() != "ok":
            failures.append("E37 canonical first-durable ledger missing or not OK")
        else:
            if ledger.get("endpoint_status") != "ok":
                failures.append("E37 canonical ledger endpoint_status must be ok")
            serial = ledger.get("serial_ledger")
            if not isinstance(serial, dict) or serial.get("zero_gap") is not True:
                failures.append("E37 canonical first-durable ledger zero-gap proof missing")
            canonical_events = ledger.get("events")
            if not isinstance(canonical_events, list):
                canonical_events = []
            durable = [
                event for event in canonical_events
                if isinstance(event, dict) and event.get("name") == "first_durable_result"
            ]
            if not durable:
                failures.append("E37 canonical first-durable result event missing")
            end_ns = ledger.get("end_mono_ns")
            if end_ns is not None:
                durable_ns = durable[-1].get("mono_ns") if durable else None
                if durable_ns is None:
                    durable_ns = durable[-1].get("monotonic_ns") if durable else None
                if durable_ns is None or int(durable_ns) != int(end_ns):
                    failures.append("E37 first-durable event does not match ledger end boundary")

        # Source identity is distinct from v2ctl provenance.  Require the
        # runtime's DeploymentIdentity projection as well as StructuralValidator
        # below's invocation/profile/request provenance checks.
        result_value = data.get("result")
        result: dict[str, Any] = result_value if isinstance(result_value, dict) else {}
        ledger_identity = ledger.get("identity") if isinstance(ledger, dict) else None
        source_candidates = (
            data.get("source_identity"),
            data.get("identity"),
            result.get("source_identity"),
            result.get("identity"),
            ledger_identity,
        )
        source = next((item for item in source_candidates if isinstance(item, dict)), None)
        source_markers = (
            "combined_hash", "deployment_combined_hash", "runtime_hash",
            "dependency_hash", "custom_node_hash", "file_hashes",
        )
        # The runtime persists the canonical deployment identity in the
        # artifact's effective environment.  Accept that explicit deployment
        # hash as source proof, but do not treat profile/request IDs or an
        # arbitrary environment fingerprint as provenance.
        effective_env = data.get("effective_env")
        effective_env_hash = (
            effective_env.get("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH")
            if isinstance(effective_env, dict)
            else None
        )
        has_effective_env_hash = (
            isinstance(effective_env_hash, str) and bool(effective_env_hash.strip())
        )
        has_source_identity = source is not None and any(
            source.get(key) for key in source_markers
        )
        if not has_source_identity and not has_effective_env_hash:
            failures.append("E37 source identity proof missing")

        return failures


# Descriptive alias for callers/tests that use the E37 evidence name.
E37EvidenceValidator = E37StrictProofValidator


class E37CleanLaneProofValidator(ValidatorPlugin):
    """Fail-closed proof gate for the diagnostic E37 CLEAN_LANE profile."""

    name = "e37_clean_lane_proof"

    def applies(self, config: Any) -> bool:
        profile = str(getattr(config, "profile_name", "") or "")
        return profile == "e37-clean-lane-qd4" or _flag_enabled(
            config, "COMFYMODAL_V2_E37_CLEAN_LANE"
        ) or _flag_enabled(config, "COMFYMODAL_V2_CLEAN_LANE")

    def validate(self, record: RunRecord, config: Any) -> list[str]:
        if not self.applies(config):
            return []
        failures: list[str] = []
        events = _e31_trace_events(_artifact_data(record), record.telemetry or {})
        event_value = _named_e31_event(events, "clean_lane_proof")
        if not isinstance(event_value, dict):
            failures.append("CLEAN_LANE_PROOF missing")
            return failures
        event: dict[str, Any] = event_value
        qd: dict[str, Any] = dict(event["qd"]) if isinstance(event.get("qd"), dict) else {}
        ordering: dict[str, Any] = dict(event["ordering"]) if isinstance(event.get("ordering"), dict) else {}
        quiescence: dict[str, Any] = dict(event["quiescence"]) if isinstance(event.get("quiescence"), dict) else {}
        intervals: dict[str, Any] = dict(event["phase_intervals"]) if isinstance(event.get("phase_intervals"), dict) else {}
        volume: list[Any] = list(event["volume_reads"]) if isinstance(event.get("volume_reads"), list) else []
        forbidden_attempts = event.get("forbidden_activity_attempts")
        if event.get("mode") != "E37_CLEAN_LANE" or event.get("proof_version") != 1:
            failures.append("CLEAN_LANE_PROOF mode/version missing")
        if (
            qd.get("configured_qd") != 4
            or qd.get("actual_inflight") != 4
            or qd.get("actual_worker_count") != 4
        ):
            failures.append("CLEAN_LANE actual QD must be 4")
        if qd.get("fallback") is True or qd.get("mode") != "QD4":
            failures.append("CLEAN_LANE QD proof shows FASTSAFE fallback")
        if qd.get("source_errors"):
            failures.append("CLEAN_LANE source errors present")
        if qd.get("stats_status") != "ok":
            failures.append("CLEAN_LANE QD stats are not OK")
        if not qd.get("reconciliation_240_240"):
            failures.append("CLEAN_LANE 240/240 source reconciliation missing")
        if qd.get("h2d_host_issue_ms") is None or qd.get("h2d_cuda_event_ms") is None:
            failures.append("CLEAN_LANE paired H2D host/CUDA timing missing")
        if not volume or any(
            not isinstance(item, dict)
            or not item.get("path")
            or not item.get("identity")
            or item.get("owner") != "clip_qd_reader"
            or item.get("size_bytes") is None
            or item.get("start_ns") is None
            or item.get("end_ns") is None
            or item.get("concurrency") != 4
            for item in volume
        ):
            failures.append("CLEAN_LANE Volume read identity/interval proof missing")
        if event.get("gpu_operation_overlap") or event.get("forbidden_overlap"):
            failures.append("CLEAN_LANE forbidden GPU overlap observed")
        if not isinstance(forbidden_attempts, list):
            failures.append("CLEAN_LANE forbidden-activity attempt evidence missing")
        required_order = (
            "restore_return_ns", "plan_identity_complete_ns", "qd_start_ns",
            "qd_ready_ns", "bind_ns", "forward_start_ns", "forward_end_ns",
        )
        if any(not isinstance(ordering.get(key), int) for key in required_order):
            failures.append("CLEAN_LANE lifecycle ordering proof incomplete")
        else:
            values = [ordering[key] for key in required_order]
            if values != sorted(values) or ordering["restore_return_ns"] >= ordering["plan_identity_complete_ns"]:
                failures.append("CLEAN_LANE lifecycle ordering is false")
        if not intervals or any(
            not isinstance(item, dict)
            or not isinstance(item.get("start_ns"), int)
            or not isinstance(item.get("end_ns"), int)
            or item["end_ns"] < item["start_ns"]
            for item in intervals.values()
        ):
            failures.append("CLEAN_LANE phase intervals missing")
        required_quiescence = (
            "source_reads_complete", "submitted_blocks_reconciled", "futures_joined",
            "no_qd_worker_runnable", "pinned_ownership_safe",
            "h2d_events_complete", "device_ready_published",
        )
        if any(quiescence.get(key) is not True for key in required_quiescence):
            failures.append("CLEAN_LANE quiescence proof missing or false")
        if not isinstance(event.get("thread_state"), dict):
            failures.append("CLEAN_LANE CPU/native thread state proof missing")
        return failures


def _config_workload(config: Any) -> dict:
    workload = getattr(config, "workload", None)
    if workload is None:
        return {}
    if isinstance(workload, dict):
        return workload
    return {
        key: getattr(workload, key)
        for key in ("fresh_required", "conditioning_cache", "expected_output_sha", "run_count", "gap_seconds", "nonce")
        if hasattr(workload, key)
    }


# --------------------------------------------------------------------------
# stdout parsing helpers
# --------------------------------------------------------------------------


def parse_telemetry(stdout: str) -> dict:
    """Best-effort parse of ``key=value`` lines from backend stdout into a
    telemetry dict.  Last occurrence wins; malformed lines are skipped.
    Tolerates a leading log prefix such as ``12:34:56 request_id=abc`` by
    taking the final whitespace token of the key side as the key."""
    telemetry: dict[str, str] = {}
    if not stdout:
        return telemetry
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or "=" not in stripped:
            continue
        proof_match = re.search(
            r"\[v2ctl\.config\]\s+deploy=([^\s]+)\s+run=([^\s]+)\s+profile=([^\s]+)",
            stripped,
        )
        if proof_match:
            telemetry["v2ctl_config"] = (
                f"deploy={proof_match.group(1)} "
                f"run={proof_match.group(2)} profile={proof_match.group(3)}"
            )
        key_part, _, value = stripped.partition("=")
        key = key_part.strip().split()[-1] if key_part.strip() else ""
        value = value.strip()
        if not key or not _is_identifier_key(key):
            continue
        telemetry[key] = value
    return telemetry


def _is_identifier_key(key: str) -> bool:
    if not key:
        return False
    first = key[0]
    return first.isalpha() or first == "_" or first == "[" or first == "."


def extract_output_sha(stdout: str) -> str | None:
    """output_sha from lines containing 'output_sha' or 'OUTPUT_SHA' (tolerant
    of ``KEY = "value"`` spacing and trailing commas)."""
    if not stdout:
        return None
    pattern = re.compile(r"(?:output_sha|OUTPUT_SHA)\s*[=:]\s*\"?([^\"\s,]+)")
    for line in stdout.splitlines():
        if "output_sha" not in line and "OUTPUT_SHA" not in line:
            continue
        match = pattern.search(line)
        if match:
            return match.group(1).strip()
    return None


def build_run_record_from_result(
    result: Any,
    config: Any,
    deploy_fingerprint: str,
    run_fingerprint: str,
) -> RunRecord:
    """Reduce a BackendResult-like object into a RunRecord (best-effort)."""
    artifacts = getattr(result, "artifacts", None)
    stdout = getattr(result, "stdout", "") or ""
    telemetry = parse_telemetry(stdout)
    output_sha = extract_output_sha(stdout)
    if output_sha is None:
        output_sha = telemetry.get("output_sha") or telemetry.get("OUTPUT_SHA")
    # ── Artifact enrichment (E29 gate fix) ────────────────────────────────
    # The backend stdout often lacks the authoritative identity/SHA fields
    # (Windows BAT capture loses interleaved lines).  The PERSISTED run
    # artifact is authoritative: enrich telemetry/output_sha from it when the
    # stdout is incomplete.
    run_artifact = None
    if artifacts is not None:
        run_artifact = getattr(artifacts, "run_artifact", None)
    if run_artifact is not None and Path(run_artifact).is_file():
        try:
            data = json.loads(Path(run_artifact).read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            nested_golden = data.get("golden_telemetry")
            if isinstance(nested_golden, dict):
                for key in ("fresh", "restored", "v2ctl_config"):
                    if key not in telemetry and nested_golden.get(key) is not None:
                        telemetry[key] = nested_golden[key]
            if "request_id" not in telemetry and isinstance(data.get("request_id"), str):
                telemetry["request_id"] = data["request_id"]
            if "correlation_id" not in telemetry:
                cid = data.get("correlation_id") or data.get("request_id") or data.get("prompt_id")
                if cid:
                    telemetry["correlation_id"] = str(cid)
            # fresh/restored identity: the AUTHORITATIVE cold proof is the
            # container's own request/restore counts (restore_count==1 and
            # request_count==1 == exactly one request on a freshly restored
            # container).  NOTE: the container's reported class_name is a
            # legacy naming artifact (ModalRuntimeEntrypoint vs the deployed
            # ModalRuntimeEntrypointV2 target) and is NOT a stale-container
            # signal — do NOT use class-name mismatch as staleness proof.
            if not (telemetry.get("fresh") or telemetry.get("restored")):
                snap = data.get("snapshot_identity") or {}
                src = data.get("source_identity") or {}
                if isinstance(snap, dict) and snap.get("restored_instance_id"):
                    restored_id = snap["restored_instance_id"]
                    telemetry["restored_instance_id"] = str(restored_id)
                if isinstance(src, dict):
                    for k in ("fresh", "restored", "cold", "warm"):
                        if src.get(k) is not None:
                            telemetry[k] = str(src[k])
                    rc = src.get("restore_count")
                    qc = src.get("request_count")
                    if rc is not None and qc is not None:
                        if int(rc) == 1 and int(qc) == 1:
                            telemetry["fresh"] = "True"
                        else:
                            telemetry["restored"] = "True"
            # ── E29: canonical ledger presence (authoritative) ────────────
            # The E29 canonical ledger lives in data["canonical_ledger"]
            # (with canonical_ledger_status), NOT in ordinary trace events.
            # Surface its status into telemetry so the CanonicalLedgerValidator
            # can reject a run whose ledger is missing or errored.
            if "canonical_ledger_status" in data:
                telemetry["canonical_ledger_status"] = str(data["canonical_ledger_status"])
            if isinstance(data.get("canonical_ledger"), dict):
                telemetry["canonical_ledger"] = "present"
                telemetry["canonical_ledger_endpoint_status"] = str(
                    data["canonical_ledger"].get("endpoint_status") or ""
                )
                serial = data["canonical_ledger"].get("serial_ledger")
                if isinstance(serial, dict):
                    telemetry["canonical_ledger_zero_gap"] = str(
                        serial.get("zero_gap", False)
                    )
            if output_sha is None and isinstance(data.get("output_sha"), str):
                output_sha = data["output_sha"]
            if output_sha is None:
                # The output descriptor array carries the authoritative asset
                # hash (asset_id = the exact output SHA).
                desc = data.get("output_descriptor")
                if isinstance(desc, list):
                    for item in desc:
                        if isinstance(item, dict) and isinstance(item.get("asset_id"), str):
                            output_sha = item["asset_id"]
                            break
                elif isinstance(desc, dict) and isinstance(desc.get("asset_id"), str):
                    output_sha = desc["asset_id"]
            if output_sha is None:
                # Golden attempts keep output identity in the harness
                # validation projection rather than the generic descriptor
                # fields.  This is still persisted evidence, not stdout or a
                # value inferred from the configured expectation.
                golden_validation = data.get("validation")
                golden_shas = (
                    golden_validation.get("observed_output_shas")
                    if isinstance(golden_validation, dict)
                    else None
                )
                if isinstance(golden_shas, list) and len(golden_shas) == 1:
                    candidate = golden_shas[0]
                    if isinstance(candidate, str) and candidate.strip():
                        output_sha = candidate.strip()
            if "attention_backend" in data:
                telemetry["attention_backend"] = str(data["attention_backend"])
            if "resolved_attention_backend" in data:
                telemetry["resolved_attention_backend"] = str(data["resolved_attention_backend"])
            golden_telemetry = data.get("golden_telemetry")
            if isinstance(golden_telemetry, dict) and golden_telemetry.get("attention_backend"):
                telemetry["attention_backend"] = str(golden_telemetry["attention_backend"])
    target = getattr(config, "target", None)
    workload = _config_workload(config)
    try:
        attention_backend = resolved_attention_backend(config)
    except ValueError:
        attention_backend = ""
    artifact_identity = getattr(artifacts, "experiment_identity", {}) or {}
    experiment_identity = {
        "profile": getattr(config, "profile_name", "") or "",
        "v2ctl_invocation_id": str(getattr(artifacts, "v2ctl_invocation_id", "") or ""),
        "request_id": str(getattr(artifacts, "request_id", "") or telemetry.get("request_id", "") or ""),
        "profile_config_fingerprint": str(
            getattr(artifacts, "profile_config_fingerprint", "") or ""
        ),
        "deploy_fingerprint": deploy_fingerprint,
        "run_fingerprint": run_fingerprint,
        "attention_backend": str(telemetry.get("attention_backend") or attention_backend),
    }
    if isinstance(artifact_identity, dict):
        experiment_identity.update(artifact_identity)
    arm_identity = golden_arm_identity(config) if _is_golden_profile(config) else {}
    if isinstance(artifact_identity, dict):
        arm_identity.update({
            key: artifact_identity[key]
            for key in ("golden_arm", "cpu_qd2_prefetch")
            if key in artifact_identity
        })
    return RunRecord(
        run_fingerprint=run_fingerprint,
        deploy_fingerprint=deploy_fingerprint,
        profile=getattr(config, "profile_name", "") or "",
        target_app=getattr(target, "app", "") if target is not None else "",
        target_class=getattr(target, "class_name", "") if target is not None else "",
        fresh_required=bool(workload.get("fresh_required", False)),
        expected_output_sha=str(workload.get("expected_output_sha", "") or ""),
        artifacts=artifacts,
        backend_ok=bool(getattr(result, "exit_code", 1) == 0),
        backend_exit_code=getattr(result, "exit_code", None),
        telemetry=telemetry,
        output_sha=output_sha,
        v2ctl_invocation_id=str(getattr(artifacts, "v2ctl_invocation_id", "") or ""),
        request_id=str(getattr(artifacts, "request_id", "") or telemetry.get("request_id", "") or ""),
        profile_config_fingerprint=str(
            getattr(artifacts, "profile_config_fingerprint", "") or ""
        ),
provenance_validation_status=str(
              getattr(artifacts, "provenance_validation_status", "") or ""
          ),
          # The one deployment identity: what was expected, and what the
          # serving interpreter actually reported for this request.
          expected_deploy_id=str(
              getattr(artifacts, "expected_deploy_id", "") or ""
          ),
          deploy_id=str(
              getattr(artifacts, "deploy_id", "")
              or telemetry.get("deploy_id")
              or telemetry.get("DEPLOY_ID")
              or ""
          ),
        attention_backend=str(telemetry.get("attention_backend") or attention_backend),
        golden_arm=str(arm_identity.get("golden_arm", "") or ""),
        cpu_qd2_prefetch=bool(arm_identity.get("cpu_qd2_prefetch", False)),
        experiment_identity=experiment_identity,
        backend_command=str(getattr(result, "command", "") or ""),
    )


# --------------------------------------------------------------------------
# GateRunner / ConfirmRunner
# --------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _format_run_command(spec: Any, extra_args: list[str]) -> str:
    build = getattr(spec, "build_command_line", None)
    if callable(build):
        try:
            return str(build(spec, extra_args))
        except Exception:  # noqa: BLE001 - best-effort, pure formatting
            pass
    name = getattr(spec, "name", "backend")
    return f"{name} {' '.join(extra_args)}".strip()


def _profile_config_fingerprint(fingerprints: Any) -> str:
    try:
        method = getattr(fingerprints, "profile_config_fingerprint", None)
        if callable(method):
            return str(method())
        method = getattr(fingerprints, "config_fingerprint", None)
        if callable(method):
            return str(method())
    except Exception:  # noqa: BLE001 - compatibility fakes
        pass
    return ""


def _profile_config_fingerprint_from_config(config: Any) -> str:
    try:
        from .fingerprints import FingerprintEngine
        return FingerprintEngine(config).profile_config_fingerprint()
    except Exception:  # noqa: BLE001 - duck-typed validation config
        return ""


def _canonical_extra_env(
    config: Any,
    deploy_fp: str,
    run_fp: str,
    profile_config_fp: str,
    invocation_id: str,
    extras: dict[str, str],
) -> dict[str, str]:
    result = dict(extras)
    # Gate/confirm use the same resolved target/resource identity channel as
    # cmd_run.  Do not leave these names to the BAT defaults: that is how a
    # run-only Golden request can silently land on the restore-only app.
    from .cli import _identity_env

    result.update({
        name: str(value) for name, value in _identity_env(config).items()
    })
    result.update({
        "COMFYMODAL_V2CTL_INVOCATION_ID": invocation_id,
        "COMFYMODAL_V2CTL_PROFILE": str(getattr(config, "profile_name", "") or ""),
        "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": profile_config_fp,
        "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": deploy_fp,
        "COMFYMODAL_V2CTL_RUN_FINGERPRINT": run_fp,
    })
    return result


_CANONICAL_IDENTITY_ENV = (
    "COMFYMODAL_V2_APP_NAME",
    "COMFYMODAL_V2_CLASS_NAME",
    "COMFYMODAL_V2_GPU",
    "COMFYMODAL_V2_MEMORY_MB",
    "COMFYMODAL_V2_CPU_REQUEST",
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST",
    "COMFYMODAL_V2_BASELINE_CPU_REQUEST",
)


def _receipt_identity_environment(receipt: Any) -> dict[str, str] | None:
    if receipt is None:
        return None
    result: dict[str, str] = {}
    values = _receipt_value(receipt, "effective_environment", {})
    if isinstance(values, dict):
        result.update({str(k): str(v) for k, v in values.items()})
    target = _receipt_value(receipt, "target", {})
    if isinstance(target, dict):
        if target.get("app"):
            result["COMFYMODAL_V2_APP_NAME"] = str(target["app"])
        if target.get("class"):
            result["COMFYMODAL_V2_CLASS_NAME"] = str(target["class"])
    deployment = _receipt_value(receipt, "deployment_identity", {})
    resources = deployment.get("resources", {}) if isinstance(deployment, dict) else {}
    if isinstance(resources, dict):
        for env_name, resource_name in (
            ("COMFYMODAL_V2_GPU", "gpu"),
            ("COMFYMODAL_V2_CPU_REQUEST", "cpu"),
            ("COMFYMODAL_V2_MEMORY_MB", "memory_mb"),
            ("COMFYMODAL_V2_BASELINE_CPU_REQUEST", "cpu"),
            ("COMFYMODAL_V2_BASELINE_MEMORY_REQUEST", "memory_mb"),
        ):
            if resource_name in resources:
                result[env_name] = str(resources[resource_name])
    return result


def _assert_canonical_backend_identity(
    config: Any,
    extra_env: dict[str, str],
    identity_source: dict[str, str] | None = None,
) -> None:
    """Refuse Golden backend calls unless the complete identity is explicit.

    The BAT fallback is intentionally retained for non-Golden profiles.  For
    Golden, however, an omitted or contradictory identity is unsafe: the
    backend must not get a chance to select its restore-only default.
    """
    if not _is_golden_profile(config):
        return

    target = getattr(config, "target", None)
    if isinstance(target, dict):
        target_value = target.get
    else:
        target_value = lambda name, default="": getattr(target, name, default)
    resolved_app = str(target_value("app", "") or "").strip()
    expected_target = {
        # The profile supplies the canonical app by default, but an explicit
        # resolved app is valid for experimental Golden deployments.  The
        # identity environment checks below still bind the backend to it.
        "app": resolved_app or "stable-modal-comfy-v2-golden-p1",
        "class_name": "ModalRuntimeEntrypointV2",
        "method": "run_golden_serial_stream",
    }
    failures = [
        f"golden_p1 target.{name} must be {expected!r}; got {target_value(name, '')!r}"
        for name, expected in expected_target.items()
        if str(target_value(name, "") or "") != expected
    ]

    try:
        from .cli import _identity_env

        expected_env = {
            name: str(value) for name, value in _identity_env(config).items()
        }
    except Exception as exc:  # noqa: BLE001 - fail closed for duck-typed callers
        raise GateError(f"golden_p1 canonical identity could not be resolved: {exc}") from exc
    for name in _CANONICAL_IDENTITY_ENV:
        expected = str((identity_source or {}).get(name, expected_env.get(name, ""))).strip()
        observed = str(extra_env.get(name, "") or "").strip()
        if not expected or expected.lower() in {"none", "null"}:
            failures.append(f"golden_p1 canonical identity {name} is missing from config")
        elif observed != expected:
            failures.append(
                f"golden_p1 canonical identity {name} mismatch: "
                f"expected {expected!r}, got {observed or '(missing)'!r}"
            )

    if failures:
        raise GateError(
            "refusing golden_p1 backend invocation: " + "; ".join(failures)
        )


def _run_backend(
    runner: Any,
    spec: Any,
    *,
    config: Any,
    extra_args: list[str],
    extra_env: dict[str, str],
    timeout_seconds: float,
    invocation_id: str,
    strict_canonical: bool,
    allow_multiple_run_artifacts: bool = False,
    canonical_identity: dict[str, str] | None = None,
) -> Any:
    """Call real BackendRunner plus older duck-typed test runners safely."""
    kwargs: dict[str, Any] = {
        "config": config,
        "extra_args": extra_args,
        "extra_env": extra_env,
        "capture": True,
        "timeout_seconds": timeout_seconds,
    }
    try:
        parameters = inspect.signature(runner.run).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "invocation_id" in parameters:
        kwargs["invocation_id"] = invocation_id
    elif "invocation_context" in parameters:
        kwargs["invocation_context"] = invocation_id
    if "strict_canonical_discovery" in parameters:
        kwargs["strict_canonical_discovery"] = strict_canonical
    if "allow_multiple_run_artifacts" in parameters:
        kwargs["allow_multiple_run_artifacts"] = allow_multiple_run_artifacts
    if canonical_identity is not None and "canonical_identity" in parameters:
        kwargs["canonical_identity"] = canonical_identity
    return runner.run(spec, **kwargs)


class GateRunner:
    """Runs EXACTLY ONE cold validation gate invocation and persists a gate
    manifest even when the gate is invalid (so confirm can refuse)."""

    def __init__(
        self,
        *,
        repo_root: Path,
        fingerprints: Any,  # FingerprintEngine
        validators: Validator,
        backend_runner: Any,
        env_builder: Any,
        deployment_receipt: Any | None = None,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._fingerprints = fingerprints
        self._validators = validators
        self._backend_runner = backend_runner
        self._env_builder = env_builder
        self._deployment_receipt = deployment_receipt

    def run_gate(
        self,
        config: Any,
        backend_spec: Any,
        invocation_id: str | None = None,
        invocation_context: str | None = None,
    ) -> GateResult:
        invocation_id = str(invocation_id or invocation_context or uuid.uuid4().hex)
        deploy_fp = str(_receipt_value(
            self._deployment_receipt, "deploy_fingerprint", ""
        ) or self._fingerprints.deploy_fingerprint())
        run_fp = _bound_run_fingerprint(self._fingerprints, self._deployment_receipt)
        profile_config_fp = str(_receipt_value(
            self._deployment_receipt, "profile_config_fingerprint", ""
        ) or _profile_config_fingerprint(self._fingerprints))
        # Keep the full-run mode and target-method policy centralized in the
        # CLI guard so direct GateRunner callers cannot bypass Golden routing.
        from .cli import _require_full_run_mode

        _require_full_run_mode(config, command="v2ctl gate")
        # No source-probe precondition. Deployment correctness is decided by the
        # same-request deploy_id comparison in StructuralValidator, which is
        # strictly stronger than a probe of the mounted filesystem.
        # Keep selector, run count, nonce, and selector env in one canonical
        # construction shared with confirm and CLI dry-run reporting.
        from .cli import _validation_backend_args

        extra_args, selector_env = _validation_backend_args(config)
        extra_env = _canonical_extra_env(
            config, deploy_fp, run_fp, profile_config_fp, invocation_id,
            {"V2_BENCHMARK_RUNS": "1", **selector_env},
        )
        extra_env = _bind_receipt_environment(extra_env, self._deployment_receipt)
        _assert_canonical_backend_identity(
            config, extra_env,
            _receipt_identity_environment(self._deployment_receipt),
        )
        canonical_identity = {
            "profile": str(_receipt_value(self._deployment_receipt, "profile", "")
                            or getattr(config, "profile_name", "") or ""),
            "profile_config_fingerprint": profile_config_fp,
            "deploy_fingerprint": deploy_fp,
            "run_fingerprint": run_fp,
        }
        try:
            result = _run_backend(
                self._backend_runner, backend_spec, config=config,
                extra_args=extra_args,
                extra_env=extra_env,
                timeout_seconds=600.0, invocation_id=invocation_id,
                strict_canonical=True,
                canonical_identity=canonical_identity,
            )
        except Exception as exc:  # noqa: BLE001 - backend spawn/timeout failure
            detail = str(exc)
            if "no canonical run artifact" in detail.lower():
                detail = f"no persisted run artifact was discovered; {detail}"
            _finalize_evidence(
                self._repo_root, record=None, config=config, deploy_fp=deploy_fp,
                run_fp=run_fp, result=None, verdict="INCONCLUSIVE",
                invocation_id=invocation_id,
            )
            raise GateError(f"gate backend invocation failed before completing: {detail}") from exc

        # ── Crash-loop guard: a container that repeats the same traceback in
        # the gate output is crash-looping; the run is NOT a valid measurement
        # and must never be treated as a structurally valid gate. ──
        crash = detect_crash_loop(result.stdout or "")
        if crash is not None:
            reasons = [
                f"deployed container crash-looping: exception "
                f"{crash['exception_type']!r} repeated {crash['count']}x "
                f"in gate output (measurement invalid; diagnose root cause "
                f"locally, fix, redeploy, then re-run gate)"
            ]
            record = build_run_record_from_result(result, config, deploy_fp, run_fp)
            manifest = _build_manifest(
                record, config, valid=False, reasons=reasons,
                deploy_fp=deploy_fp, run_fp=run_fp,
                deploy_inputs=_safe_deploy_inputs(self._fingerprints),
                deployment_receipt=self._deployment_receipt,
            )
            path = self._persist_manifest(config, run_fp, manifest)
            LOG.warning("gate manifest written (crash-loop, invalid): %s", path)
            evidence_path, evidence_status, evidence_verdict, evidence_reason = _finalize_evidence(
                self._repo_root, record=record, config=config, deploy_fp=deploy_fp,
                run_fp=run_fp, result=result, verdict="REJECT", gate_manifest=path,
            )
            if evidence_reason:
                reasons.append(evidence_reason)
            return GateResult(
                valid=False, reasons=reasons, manifest_path=path, run=record,
                evidence_path=evidence_path, evidence_status=evidence_status,
                verdict=evidence_verdict,
            )

        record = build_run_record_from_result(result, config, deploy_fp, run_fp)
        reasons = self._validators.run(record, config)
        valid = not reasons

        # persist manifest even when invalid, so confirm can refuse
        deploy_inputs = _safe_deploy_inputs(self._fingerprints)
        manifest = _build_manifest(
            record, config, valid, reasons, deploy_fp, run_fp, deploy_inputs,
            deployment_receipt=self._deployment_receipt,
        )
        path = self._persist_manifest(config, run_fp, manifest)
        if valid:
            mark_runtime_health_verified(
                self._repo_root,
                config,
                self._fingerprints,
                deploy_fp,
                bound_receipt=self._deployment_receipt,
            )

        evidence_path, evidence_status, evidence_verdict, evidence_reason = _finalize_evidence(
            self._repo_root, record=record, config=config, deploy_fp=deploy_fp,
            run_fp=run_fp, result=result,
            verdict="ACCEPT" if valid else "REJECT", gate_manifest=path,
        )
        if evidence_reason:
            reasons.append(evidence_reason)
            valid = False
            _invalidate_evidence_manifest(path, evidence_reason)

        LOG.info("gate manifest written: %s (valid=%s)", path, valid)
        return GateResult(
            valid=valid, reasons=reasons, manifest_path=path, run=record,
            evidence_path=evidence_path, evidence_status=evidence_status,
            verdict="INCONCLUSIVE" if evidence_reason else evidence_verdict,
        )

    def latest_gate(self) -> Path | None:
        gates_dir = self._repo_root / ".v2ctl" / "gates"
        if not gates_dir.is_dir():
            return None
        candidates = sorted(gates_dir.glob("gate_*.json"), key=lambda p: p.name, reverse=True)
        return candidates[0] if candidates else None

    # -- helpers ------------------------------------------------------------

    def _persist_manifest(self, config: Any, run_fp: str, manifest: dict) -> Path:
        gates_dir = self._repo_root / ".v2ctl" / "gates"
        gates_dir.mkdir(parents=True, exist_ok=True)
        stamp = _now_utc().strftime("%Y%m%d-%H%M%S")
        filename = f"gate_{stamp}_{run_fp[:8]}.json"
        path = gates_dir / filename
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


class ConfirmRunner:
    """Confirmation protocol: refuses a missing/invalid/stale gate manifest,
    then runs exactly ``runs`` separate single-run backend invocations and
    persists a combined confirmation manifest."""

    def __init__(
        self,
        *,
        repo_root: Path,
        fingerprints: Any,  # FingerprintEngine
        backend_runner: Any,
        env_builder: Any,
        validators: Validator,
        deployment_receipt: Any | None = None,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._fingerprints = fingerprints
        self._backend_runner = backend_runner
        self._env_builder = env_builder
        self._validators = validators
        self._deployment_receipt = deployment_receipt

    def confirm(
        self,
        gate_manifest: Path,
        config: Any,
        backend_spec: Any,
        runs: int = 1,
        invocation_id: str | None = None,
        invocation_context: str | None = None,
    ) -> GateResult:
        invocation_id = str(invocation_id or invocation_context or uuid.uuid4().hex)
        # Confirm is a full-generation protocol just like gate.  Keep the same
        # centralized method/mode guard here so direct callers cannot spend on
        # the restore-only probe or an arbitrary target method.
        from .cli import _require_full_run_mode

        _require_full_run_mode(config, command="v2ctl confirm")
        # No source-probe precondition. Deployment correctness is decided by the
        # same-request deploy_id comparison in StructuralValidator, which is
        # strictly stronger than a probe of the mounted filesystem.
        path = Path(gate_manifest)
        if not path.is_file():
            raise GateError(f"gate manifest not found: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise GateError(f"gate manifest is invalid/corrupt: {path}: {exc}") from exc
        if not isinstance(data, dict) or data.get("schema_version") != _GATE_SCHEMA_VERSION:
            raise GateError(f"gate manifest has unsupported schema: {path}")
        if data.get("gate_valid") is not True:
            reasons = data.get("reasons") or []
            raise GateError(
                f"gate manifest {path} is invalid (gate_valid=False); confirm refuses to run: {reasons}"
            )

        if self._deployment_receipt is not None:
            receipt = self._deployment_receipt
            receipt_data = receipt.to_dict() if hasattr(receipt, "to_dict") else {}
            expected_path = str(getattr(receipt, "receipt_path", "") or "")
            if not expected_path or data.get("deployment_receipt_path") != expected_path:
                raise GateError("gate manifest is not bound to the deployment receipt path")
            if data.get("deployment_receipt_integrity_digest") != receipt_data.get(
                "integrity_digest"
            ):
                raise GateError("gate manifest deployment receipt integrity mismatch")
            if data.get("deployment_version") != receipt.deployment_version:
                raise GateError("gate manifest deployment version mismatch")
            if data.get("receipt_profile") != receipt.profile:
                raise GateError("gate manifest deployment receipt profile mismatch")
            if data.get("receipt_target") != receipt.target:
                raise GateError("gate manifest deployment receipt target mismatch")
            if data.get("receipt_deploy_fingerprint") != receipt.deploy_fingerprint:
                raise GateError("gate manifest deployment receipt fingerprint mismatch")
            if data.get("receipt_source_probe_expected") != receipt.source_probe.get("expected"):
                raise GateError("gate manifest source-probe expectation mismatch")
            if data.get("receipt_manifest_path") != receipt.manifest_path:
                raise GateError("gate manifest deployment manifest path mismatch")
            if data.get("receipt_manifest_digest") != receipt.manifest_digest:
                raise GateError("gate manifest deployment manifest digest mismatch")
            from .deployment_receipt import source_probe_evidence_path

            if data.get("source_probe_evidence_path") != str(
                source_probe_evidence_path(Path(receipt.receipt_path).parents[2], receipt)
            ):
                raise GateError("gate manifest source-probe evidence path mismatch")

        # deploy fingerprint must still match the current deployment
        snapshot = data.get("config_snapshot") or {}
        manifest_deploy_fp = snapshot.get("deploy_fingerprint")
        current_deploy_fp = str(_receipt_value(
            self._deployment_receipt, "deploy_fingerprint", ""
        ) or self._fingerprints.deploy_fingerprint())
        if manifest_deploy_fp != current_deploy_fp:
            changed = _changed_deploy_inputs(snapshot, self._fingerprints)
            raise GateError(
                "deployment fingerprint changed since the gate manifest was written; "
                f"refusing to confirm. Changed deploy inputs: {', '.join(changed) or 'unknown'}"
            )
        if self._deployment_receipt is not None:
            if snapshot.get("profile") != self._deployment_receipt.profile:
                raise GateError("gate manifest profile is not receipt-bound")
            if snapshot.get("run_fingerprint") != _bound_run_fingerprint(
                self._fingerprints, self._deployment_receipt
            ):
                raise GateError("gate manifest run identity is not receipt-bound")
            if snapshot.get("profile_config_fingerprint") != self._deployment_receipt.profile_config_fingerprint:
                raise GateError("gate manifest profile configuration is not receipt-bound")
            run_identity = data.get("run")
            expected_run = _bound_run_fingerprint(
                self._fingerprints, self._deployment_receipt
            )
            if not isinstance(run_identity, dict) or run_identity.get(
                "deploy_fingerprint"
            ) != self._deployment_receipt.deploy_fingerprint or run_identity.get(
                "run_fingerprint"
            ) != expected_run:
                raise GateError("gate manifest run record is not receipt-bound")
            if data.get("profile_config_fingerprint") != self._deployment_receipt.profile_config_fingerprint:
                raise GateError("gate manifest top-level profile configuration mismatch")
            if snapshot.get("target") != {
                "app": self._deployment_receipt.target.get("app", ""),
                "class_name": self._deployment_receipt.target.get("class", ""),
                "method": self._deployment_receipt.target.get("method", ""),
            }:
                raise GateError("gate manifest target is not receipt-bound")

        # A receipt binds the immutable remote version.  Local source drift is
        # informational after that bind; without a receipt retain the legacy
        # fail-closed gate-manifest contract.
        manifest_head = snapshot.get("git_head")
        current_head = self._current_git_head()
        if self._deployment_receipt is None and manifest_head and current_head and manifest_head != current_head:
            raise GateError(
                f"git HEAD changed since the gate manifest: {manifest_head} -> {current_head}; refusing to confirm"
            )

        # target must be unchanged
        manifest_target = snapshot.get("target")
        current_target = _target_dict(config)
        if manifest_target and current_target and manifest_target != current_target:
            changed = sorted(set(manifest_target.keys()) | set(current_target.keys()))
            raise GateError(
                f"deploy target changed since the gate manifest; refusing to confirm. Changed inputs: {', '.join(changed)}"
            )

        if runs < 1:
            raise GateError("confirm runs must be >= 1")

        # Each confirmation is deliberately a separate single-run backend
        # invocation.  In particular, never pass `runs` as --run-count or
        # enable multi-artifact discovery for the confirmation loop.
        run_fp = _bound_run_fingerprint(self._fingerprints, self._deployment_receipt)
        deploy_fp = current_deploy_fp
        profile_config_fp = str(_receipt_value(
            self._deployment_receipt, "profile_config_fingerprint", ""
        ) or _profile_config_fingerprint(self._fingerprints))
        from .cli import _validation_backend_args

        extra_args, selector_env = _validation_backend_args(config)
        all_reasons: list[str] = []
        records: list[RunRecord] = []
        for index in range(runs):
            # A strict canonical discovery binds one persisted artifact to one
            # backend invocation.  Separate IDs keep separate confirmations
            # from becoming an ambiguous multi-run invocation.
            run_invocation_id = invocation_id if runs == 1 else uuid.uuid4().hex
            extra_env = _canonical_extra_env(
                config, deploy_fp, run_fp, profile_config_fp, run_invocation_id,
                {"V2_BENCHMARK_RUNS": "1", **selector_env},
            )
            extra_env = _bind_receipt_environment(extra_env, self._deployment_receipt)
            _assert_canonical_backend_identity(
                config, extra_env,
                _receipt_identity_environment(self._deployment_receipt),
            )
            canonical_identity = {
                "profile": str(_receipt_value(self._deployment_receipt, "profile", "")
                                or getattr(config, "profile_name", "") or ""),
                "profile_config_fingerprint": profile_config_fp,
                "deploy_fingerprint": deploy_fp,
                "run_fingerprint": run_fp,
            }
            try:
                result = _run_backend(
                    self._backend_runner, backend_spec, config=config,
                    extra_args=extra_args,
                    extra_env=extra_env,
                    timeout_seconds=600.0, invocation_id=run_invocation_id,
                    strict_canonical=True,
                    allow_multiple_run_artifacts=False,
                    canonical_identity=canonical_identity,
                )
            except Exception as exc:  # noqa: BLE001 - backend spawn/timeout
                detail = str(exc)
                if "no canonical run artifact" in detail.lower():
                    detail = f"no persisted run artifact was discovered; {detail}"
                _finalize_evidence(
                    self._repo_root, record=records[-1] if records else None,
                    config=config, deploy_fp=deploy_fp, run_fp=run_fp,
                    result=None, verdict="INCONCLUSIVE", gate_manifest=path,
                    records=records, invocation_id=run_invocation_id,
                )
                raise GateError(
                    f"confirm backend invocation {index + 1} failed before completing: {detail}"
                ) from exc
            record = build_run_record_from_result(result, config, deploy_fp, run_fp)
            records.append(record)
            all_reasons.extend(self._validators.run(record, config))

        valid = not all_reasons
        combined = records[-1] if records else None
        deploy_inputs = _safe_deploy_inputs(self._fingerprints)
        manifest = _build_manifest(
            combined, config, valid, all_reasons, deploy_fp, run_fp, deploy_inputs,
            deployment_receipt=self._deployment_receipt,
        )
        manifest["confirm_runs"] = runs
        manifest["gate_manifest"] = str(path)
        manifest_path = self._persist_manifest(config, run_fp, manifest, kind="confirm")
        evidence_path, evidence_status, evidence_verdict, evidence_reason = _finalize_evidence(
            self._repo_root, record=combined, config=config, deploy_fp=deploy_fp,
            run_fp=run_fp, result=None,
            verdict="ACCEPT" if valid else "REJECT",
            gate_manifest=path, confirmation_manifest=manifest_path, records=records,
        )
        if evidence_reason:
            all_reasons.append(evidence_reason)
            valid = False
            _invalidate_evidence_manifest(manifest_path, evidence_reason)
        return GateResult(
            valid=valid, reasons=all_reasons, manifest_path=manifest_path, run=combined,
            evidence_path=evidence_path, evidence_status=evidence_status,
            verdict="INCONCLUSIVE" if evidence_reason else evidence_verdict,
        )

    # -- helpers ------------------------------------------------------------

    def _current_git_head(self) -> str | None:
        import subprocess

        try:
            proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(self._repo_root),
                timeout=15,
            )
        except Exception:  # noqa: BLE001 - git absent/unavailable
            return None
        if proc.returncode != 0:
            return None
        head = (proc.stdout or "").strip()
        return head or None

    def _persist_manifest(self, config: Any, run_fp: str, manifest: dict, kind: str) -> Path:
        confirm_dir = self._repo_root / ".v2ctl" / "confirmations"
        confirm_dir.mkdir(parents=True, exist_ok=True)
        stamp = _now_utc().strftime("%Y%m%d-%H%M%S")
        filename = f"confirm_{stamp}_{run_fp[:8]}.json"
        path = confirm_dir / filename
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


# --------------------------------------------------------------------------
# manifest construction
# --------------------------------------------------------------------------


def _target_dict(config: Any) -> dict:
    target = getattr(config, "target", None)
    if target is None:
        return {}
    if isinstance(target, dict):
        return {str(k): v for k, v in target.items() if not k.startswith("_")}
    return {
        "app": getattr(target, "app", ""),
        "class_name": getattr(target, "class_name", ""),
        "method": getattr(target, "method", ""),
    }


def _resources_dict(config: Any) -> dict:
    resources = getattr(config, "resources", None)
    if resources is None:
        return {}
    if isinstance(resources, dict):
        return {str(k): v for k, v in resources.items() if not k.startswith("_")}
    return {
        "gpu": getattr(resources, "gpu", ""),
        "cpu": getattr(resources, "cpu", ""),
        "memory_mb": getattr(resources, "memory_mb", ""),
        "min_containers": getattr(resources, "min_containers", ""),
        "scaledown_window": getattr(resources, "scaledown_window", ""),
    }


def _build_manifest(
    record: RunRecord | None,
    config: Any,
    valid: bool,
    reasons: list[str],
    deploy_fp: str,
    run_fp: str,
    deploy_inputs: dict | None = None,
    deployment_receipt: Any | None = None,
) -> dict:
    git_head = getattr(config, "git", None)
    if git_head is not None:
        head = getattr(git_head, "head", "")
    else:
        head = ""
    snapshot = {
        "profile": getattr(config, "profile_name", "") or "",
        "git_head": head,
        "target": _target_dict(config),
        "resources": _resources_dict(config),
        "deploy_fingerprint": deploy_fp,
        "run_fingerprint": run_fp,
        "profile_config_fingerprint": _profile_config_fingerprint_from_config(config),
    }
    if deploy_inputs:
        snapshot["deploy_inputs"] = deploy_inputs
    if deployment_receipt is not None:
        effective_config = getattr(deployment_receipt, "effective_config", {})
        deployment_identity = getattr(deployment_receipt, "deployment_identity", {})
        snapshot["profile"] = deployment_receipt.profile
        snapshot["git_head"] = str(
            getattr(deployment_receipt, "deployed_source", {}).get("git_head", "")
        )
        snapshot["target"] = {
            "app": deployment_receipt.target.get("app", ""),
            "class_name": deployment_receipt.target.get("class", ""),
            "method": deployment_receipt.target.get("method", ""),
        }
        receipt_resources = (
            deployment_identity.get("resources", {})
            if isinstance(deployment_identity, dict) else {}
        )
        if isinstance(effective_config, dict) and isinstance(
            effective_config.get("resources"), dict
        ):
            receipt_resources = effective_config["resources"]
        snapshot["resources"] = dict(receipt_resources)
        if isinstance(effective_config, dict) and isinstance(
            effective_config.get("deploy_inputs"), dict
        ):
            snapshot["deploy_inputs"] = effective_config["deploy_inputs"]
        snapshot["profile_config_fingerprint"] = deployment_receipt.profile_config_fingerprint
    manifest = {
        "schema_version": _GATE_SCHEMA_VERSION,
        "gate_valid": valid,
        "reasons": list(reasons),
        "run": record.to_dict() if record is not None else {},
        "config_snapshot": snapshot,
        "created_at": _now_utc().isoformat(),
    }
    if record is not None:
        manifest["attention_backend"] = record.attention_backend
        manifest["experiment_identity"] = dict(record.experiment_identity)
    if deployment_receipt is not None:
        receipt_data = (
            deployment_receipt.to_dict()
            if hasattr(deployment_receipt, "to_dict") else deployment_receipt
        )
        manifest["deployment_receipt_path"] = str(
            receipt_data.get("receipt_path", "") if isinstance(receipt_data, dict) else ""
        )
        manifest["deployment_receipt_integrity_digest"] = str(
            receipt_data.get("integrity_digest", "") if isinstance(receipt_data, dict) else ""
        )
        manifest["deployment_version"] = getattr(deployment_receipt, "deployment_version", None)
        manifest["receipt_deploy_fingerprint"] = deploy_fp
        manifest["receipt_profile"] = deployment_receipt.profile
        manifest["receipt_target"] = dict(deployment_receipt.target)
        manifest["receipt_source_probe_expected"] = deployment_receipt.source_probe.get("expected")
        manifest["receipt_manifest_path"] = deployment_receipt.manifest_path
        manifest["receipt_manifest_digest"] = deployment_receipt.manifest_digest
        from .deployment_receipt import source_probe_evidence_path

        manifest["source_probe_evidence_path"] = str(
            source_probe_evidence_path(
                Path(deployment_receipt.receipt_path).parents[2], deployment_receipt
            )
            if deployment_receipt.receipt_path else ""
        )
    if record is not None:
        manifest.update({
            "v2ctl_invocation_id": record.v2ctl_invocation_id,
            "request_id": record.request_id,
            "profile": record.profile,
            "profile_config_fingerprint": record.profile_config_fingerprint,
            "provenance_validation_status": record.provenance_validation_status,
            "selected_run_path": str(getattr(record.artifacts, "run_artifact", "") or ""),
            "selected_summary_path": str(getattr(record.artifacts, "summary_artifact", "") or ""),
            "run_artifacts": [str(p) for p in (getattr(record.artifacts, "run_artifacts", []) or [])],
        })
    if deployment_receipt is not None:
        # Artifact metadata can be produced by a drifted local runtime.  The
        # top-level admission identity remains the immutable receipt identity.
        manifest["profile"] = deployment_receipt.profile
        manifest["profile_config_fingerprint"] = deployment_receipt.profile_config_fingerprint
    return manifest


def _safe_deploy_inputs(fingerprints: Any) -> dict:
    try:
        inputs = fingerprints.deploy_inputs()
    except Exception:  # noqa: BLE001 - best-effort
        return {}
    if not isinstance(inputs, dict):
        return {}
    return {str(key): value for key, value in inputs.items()}


def _changed_deploy_inputs(snapshot: dict, fingerprints: Any) -> list[str]:
    """Diff the manifest's config snapshot against the current deploy inputs.
    Returns names of changed deploy-relevant inputs (human-readable dotted
    names, e.g. ``deploy_flags.COFMYMODAL_V2_UNET_FASTSAFETENSORS``).

    Nested dicts (deploy_flags, target, resources, dirty_hashes) are
    expanded so the report names the exact leaf that changed, not just the
    container key."""
    changed: list[str] = []
    try:
        current_inputs = fingerprints.deploy_inputs()
    except Exception:  # noqa: BLE001 - best-effort
        return changed
    manifest_inputs = snapshot.get("deploy_inputs")
    if not isinstance(manifest_inputs, dict):
        # fall back to comparing the snapshot fields we captured
        for key in ("profile", "git_head", "target", "resources"):
            manifest_value = snapshot.get(key)
            current_value = _snapshot_current_value(fingerprints, key)
            if manifest_value != current_value:
                changed.append(key)
        return changed
    _diff_mapping("", manifest_inputs, current_inputs, changed)
    return sorted(changed)


def _diff_mapping(prefix: str, old: dict, new: dict, out: list[str]) -> None:
    for key in sorted(set(old) | set(new)):
        dotted = f"{prefix}.{key}" if prefix else str(key)
        old_value = old.get(key)
        new_value = new.get(key)
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            _diff_mapping(dotted, old_value, new_value, out)
        elif old_value != new_value:
            out.append(dotted)


def _snapshot_current_value(fingerprints: Any, key: str) -> Any:
    try:
        inputs = fingerprints.deploy_inputs()
    except Exception:  # noqa: BLE001
        return None
    return inputs.get(key)
