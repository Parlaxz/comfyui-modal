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
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .backend import detect_crash_loop
from .errors import GateError

LOG = logging.getLogger("v2ctl.validation")

_GATE_SCHEMA_VERSION = 1


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
            "telemetry": dict(self.telemetry),
            "output_sha": self.output_sha,
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


# --------------------------------------------------------------------------
# Built-in structural validators
# --------------------------------------------------------------------------


class StructuralValidator(ValidatorPlugin):
    """Generic structural checks from design section 18: backend success, a
    persisted run artifact exists, telemetry carries request/correlation ids,
    fresh/restored identity is present when fresh is required, output SHA
    matches when one is configured, and effective-config proof presence is
    checked only when the record carries it."""

    name = "structural"

    def validate(self, record: RunRecord, config: Any) -> list[str]:
        failures: list[str] = []

        # backend completed successfully
        if not record.backend_ok:
            failures.append("backend invocation did not complete successfully")

        # persisted run artifact present
        run_artifact = _artifact_run_path(record)
        if run_artifact is None or not Path(run_artifact).is_file():
            failures.append(f"persisted run artifact missing: {run_artifact}")

        # telemetry carries request/correlation identity when available
        # (an empty telemetry dict is itself a missing-identity failure)
        telemetry = record.telemetry or {}
        if "request_id" not in telemetry and "REQUEST_ID" not in telemetry:
            failures.append("telemetry missing request_id")
        if "correlation_id" not in telemetry and "CORRELATION_ID" not in telemetry:
            failures.append("telemetry missing correlation_id")

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

        # effective-config proof: checked only when the record carries it
        proof = telemetry.get("v2ctl_config") or telemetry.get("V2CTL_CONFIG")
        if proof is not None and not proof:
            failures.append("effective-config proof present but empty")

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
            return [
                f"output SHA mismatch: expected {expected}, observed {record.output_sha}"
            ]
        return []


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
        status = str(telemetry.get("canonical_ledger_status") or "")
        if status == "error":
            return [
                "canonical ledger finalization errored on the remote "
                "(canonical_ledger_status=error)"
            ]
        if status == "ok":
            endpoint_status = str(
                telemetry.get("canonical_ledger_endpoint_status") or ""
            )
            if endpoint_status != "ok":
                return [
                    f"canonical ledger endpoint_status={endpoint_status or '(missing)'}: "
                    "explicit authoritative endpoints (remote_python_resume -> "
                    "first_durable_result) are required"
                ]
            if telemetry.get("canonical_ledger_zero_gap") != "True":
                return ["canonical ledger serial zero-gap did not pass"]
            return []
        # status absent → canonical ledger missing from the artifact entirely.
        return [
            "canonical ledger missing from the run artifact "
            "(canonical_ledger_status absent): an E29 tracer run must attach "
            "canonical_ledger + canonical_ledger_status"
        ]


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
    target = getattr(config, "target", None)
    workload = _config_workload(config)
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
        telemetry=telemetry,
        output_sha=output_sha,
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
            return build(spec, extra_args)
        except Exception:  # noqa: BLE001 - best-effort, pure formatting
            pass
    name = getattr(spec, "name", "backend")
    return f"{name} {' '.join(extra_args)}".strip()


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
    ) -> None:
        self._repo_root = Path(repo_root)
        self._fingerprints = fingerprints
        self._validators = validators
        self._backend_runner = backend_runner
        self._env_builder = env_builder

    def run_gate(self, config: Any, backend_spec: Any) -> GateResult:
        deploy_fp = self._fingerprints.deploy_fingerprint()
        run_fp = self._fingerprints.run_fingerprint()
        # ── Full-run guard: gate must generate (run_plan_stream), never the
        # snapshot-restore-only PROBE. ──
        from .cli import _benchmark_mode

        if _benchmark_mode(config) == "snapshot_restore_only":
            raise GateError(
                "gate refuses V2_BENCHMARK_MODE=snapshot_restore_only: that "
                "mode runs the restore-only PROBE (run_snapshot_restore_only_probe), "
                "which never invokes run_plan_stream and produces no generation "
                "artifact. Configure a full-run mode (e.g. e28_single)."
            )
        # Forward the canonical selector (e.g. E28_VALIDATION) as the first
        # backend arg so the run BAT enters its validation mode instead of the
        # snapshot_restore_only probe branch.
        from .cli import _backend_selector

        selector = _backend_selector(config)
        extra_args = ([selector] if selector else []) + ["--run-count", "1"]
        try:
            result = self._backend_runner.run(
                backend_spec,
                config=config,
                extra_args=extra_args,
                extra_env={"V2_BENCHMARK_RUNS": "1"},
                capture=True,
                timeout_seconds=600.0,
            )
        except Exception as exc:  # noqa: BLE001 - backend spawn/timeout failure
            raise GateError(f"gate backend invocation failed before completing: {exc}") from exc

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
            )
            path = self._persist_manifest(config, run_fp, manifest)
            LOG.warning("gate manifest written (crash-loop, invalid): %s", path)
            return GateResult(valid=False, reasons=reasons, manifest_path=path, run=record)

        record = build_run_record_from_result(result, config, deploy_fp, run_fp)
        reasons = self._validators.run(record, config)
        valid = not reasons

        # persist manifest even when invalid, so confirm can refuse
        deploy_inputs = _safe_deploy_inputs(self._fingerprints)
        manifest = _build_manifest(record, config, valid, reasons, deploy_fp, run_fp, deploy_inputs)
        path = self._persist_manifest(config, run_fp, manifest)

        LOG.info("gate manifest written: %s (valid=%s)", path, valid)
        return GateResult(valid=valid, reasons=reasons, manifest_path=path, run=record)

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
    then runs exactly ``runs`` backend invocations and persists a combined
    confirmation manifest."""

    def __init__(
        self,
        *,
        repo_root: Path,
        fingerprints: Any,  # FingerprintEngine
        backend_runner: Any,
        env_builder: Any,
        validators: Validator,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._fingerprints = fingerprints
        self._backend_runner = backend_runner
        self._env_builder = env_builder
        self._validators = validators

    def confirm(
        self,
        gate_manifest: Path,
        config: Any,
        backend_spec: Any,
        runs: int = 1,
    ) -> GateResult:
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

        # deploy fingerprint must still match the current deployment
        snapshot = data.get("config_snapshot") or {}
        manifest_deploy_fp = snapshot.get("deploy_fingerprint")
        current_deploy_fp = self._fingerprints.deploy_fingerprint()
        if manifest_deploy_fp != current_deploy_fp:
            changed = _changed_deploy_inputs(snapshot, self._fingerprints)
            raise GateError(
                "deployment fingerprint changed since the gate manifest was written; "
                f"refusing to confirm. Changed deploy inputs: {', '.join(changed) or 'unknown'}"
            )

        # git head comparison (source drift)
        manifest_head = snapshot.get("git_head")
        current_head = self._current_git_head()
        if manifest_head and current_head and manifest_head != current_head:
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

        # exactly `runs` backend invocations
        run_fp = self._fingerprints.run_fingerprint()
        deploy_fp = self._fingerprints.deploy_fingerprint()
        all_reasons: list[str] = []
        records: list[RunRecord] = []
        for index in range(runs):
            try:
                result = self._backend_runner.run(
                    backend_spec,
                    config=config,
                    extra_args=["--run-count", str(runs)],
                    extra_env={"V2_BENCHMARK_RUNS": str(runs)},
                    capture=True,
                    timeout_seconds=600.0,
                )
            except Exception as exc:  # noqa: BLE001 - backend spawn/timeout
                raise GateError(f"confirm backend invocation {index + 1} failed before completing: {exc}") from exc
            record = build_run_record_from_result(result, config, deploy_fp, run_fp)
            records.append(record)
            all_reasons.extend(self._validators.run(record, config))

        valid = not all_reasons
        combined = records[-1] if records else None
        deploy_inputs = _safe_deploy_inputs(self._fingerprints)
        manifest = _build_manifest(combined, config, valid, all_reasons, deploy_fp, run_fp, deploy_inputs)
        manifest["confirm_runs"] = runs
        manifest["gate_manifest"] = str(path)
        manifest_path = self._persist_manifest(config, run_fp, manifest, kind="confirm")
        return GateResult(valid=valid, reasons=all_reasons, manifest_path=manifest_path, run=combined)

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
    }
    if deploy_inputs:
        snapshot["deploy_inputs"] = deploy_inputs
    return {
        "schema_version": _GATE_SCHEMA_VERSION,
        "gate_valid": valid,
        "reasons": list(reasons),
        "run": record.to_dict() if record is not None else {},
        "config_snapshot": snapshot,
        "created_at": _now_utc().isoformat(),
    }


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
