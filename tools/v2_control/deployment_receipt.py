"""Immutable host-side authority for a deployed Golden version.

Deployment manifests are an audit ledger.  A receipt is the smaller, bound
identity used by later requests: it is written once for a successful deploy
and is never amended by source-probe, run, gate, or confirm.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .errors import GateError

RECEIPT_SCHEMA_VERSION = 2
RECEIPT_PREFIX = "receipt_"

_RECEIPT_IDENTITY_ENV = frozenset({
    "COMFYMODAL_V2_APP_NAME",
    "COMFYMODAL_V2_CLASS_NAME",
    "COMFYMODAL_V2_GPU",
    "COMFYMODAL_V2_MEMORY_MB",
    "COMFYMODAL_V2_CPU_REQUEST",
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST",
    "COMFYMODAL_V2_BASELINE_CPU_REQUEST",
})
_RECEIPT_DIAGNOSTIC_ENV = frozenset({"COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS"})
_RECEIPT_HOST_ENV = frozenset({
    "PATH", "TEMP", "TMP", "COMSPEC", "SYSTEMROOT", "WINDIR", "PATHEXT",
    "USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH",
    "OS", "USERNAME", "COMPUTERNAME", "PYTHONHOME", "PYTHONIOENCODING",
    "PYTHONUTF8",
})
_RECEIPT_AUTH_ENV = frozenset({
    "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "MODAL_CLIENT_ID",
    "MODAL_CLIENT_SECRET", "MODAL_AUTH", "MODAL_ENVIRONMENT",
})
_RECEIPT_RESERVED_PREFIXES = ("MODAL_", "V2CTL_")
_RECEIPT_SECRET_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def validate_effective_environment(
    environment: Mapping[str, Any], *, allowed_names: set[str] | None = None
) -> None:
    """Reject host/auth/reserved data from a receipt environment projection."""
    if not isinstance(environment, Mapping):
        raise GateError("deployment receipt effective environment is malformed")
    for name, value in environment.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise GateError("deployment receipt effective environment is malformed")
        upper = name.upper()
        if value == "<redacted>":
            raise GateError("deployment receipt effective environment is redacted")
        if name in _RECEIPT_HOST_ENV or name in _RECEIPT_AUTH_ENV:
            raise GateError(f"deployment receipt contains protected host/auth key: {name}")
        if name.startswith(_RECEIPT_RESERVED_PREFIXES) or any(
            marker in upper for marker in _RECEIPT_SECRET_MARKERS
        ):
            raise GateError(f"deployment receipt contains protected key: {name}")
        if not (
            name in _RECEIPT_IDENTITY_ENV
            or name in _RECEIPT_DIAGNOSTIC_ENV
            or name.startswith("COMFYMODAL_V2_")
            or name == "COMFYMODAL_SAMPLING_DEEP_PROFILE"
            or name in (allowed_names or set())
        ):
            raise GateError(f"deployment receipt contains untrusted environment key: {name}")


@dataclass(frozen=True)
class DeploymentReceipt:
    profile: str
    target: dict[str, str]
    deploy_fingerprint: str
    effective_environment: dict[str, str]
    deployment_version: int
    created_at: str
    #: The one deployment identity. Compared against what the serving request
    #: reports; this is what makes a deployment claim checkable. Everything else
    #: on this record is either navigation metadata or a duplicate of it.
    deploy_id: str = ""
    modal_app: str = ""
    deployment_identity: dict[str, Any] = field(default_factory=dict)
    profile_config_fingerprint: str = ""
    manifest_path: str = ""
    effective_config: dict[str, Any] = field(default_factory=dict)
    receipt_path: str = ""
    modal_destination: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "profile": self.profile,
            "deploy_id": self.deploy_id,
            "target": dict(self.target),
            "deploy_fingerprint": self.deploy_fingerprint,
            "effective_environment": dict(self.effective_environment),
            "deployment_version": self.deployment_version,
            "created_at": self.created_at,
            "modal_app": self.modal_app,
            "deployment_identity": dict(self.deployment_identity),
            "profile_config_fingerprint": self.profile_config_fingerprint,
            "manifest_path": self.manifest_path,
            "effective_config": dict(self.effective_config),
            "receipt_path": self.receipt_path,
            "modal_destination": dict(self.modal_destination),
        }
        return data

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "DeploymentReceipt":
        if not isinstance(raw, Mapping):
            raise GateError("deployment receipt is not an object")
        if raw.get("schema_version") != RECEIPT_SCHEMA_VERSION:
            raise GateError("deployment receipt has unsupported schema")
        target = raw.get("target")
        environment = raw.get("effective_environment")
        if not isinstance(target, Mapping) or not isinstance(environment, Mapping):
            raise GateError("deployment receipt is malformed")

        def nested(name: str) -> dict[str, Any]:
            value = raw.get(name) or {}
            if not isinstance(value, Mapping):
                raise GateError(f"deployment receipt field {name} is malformed")
            return dict(value)

        if any(not isinstance(key, str) or not isinstance(value, str)
               for key, value in target.items()):
            raise GateError("deployment receipt target is malformed")
        if any(not isinstance(key, str) or not isinstance(value, str)
               for key, value in environment.items()):
            raise GateError("deployment receipt effective environment is malformed")
        result = cls(
            profile=str(raw.get("profile") or ""),
            deploy_id=str(raw.get("deploy_id") or ""),
            target=dict(target),
            deploy_fingerprint=str(raw.get("deploy_fingerprint") or ""),
            effective_environment=dict(environment),
            deployment_version=raw.get("deployment_version"),  # type: ignore[arg-type]
            created_at=str(raw.get("created_at") or ""),
            modal_app=str(raw.get("modal_app") or ""),
            deployment_identity=nested("deployment_identity"),
            profile_config_fingerprint=str(raw.get("profile_config_fingerprint") or ""),
            manifest_path=str(raw.get("manifest_path") or ""),
            effective_config=nested("effective_config"),
            receipt_path=str(raw.get("receipt_path") or ""),
            modal_destination=nested("modal_destination"),
        )
        result.validate()
        return result

    def _payload(self) -> dict[str, Any]:
        data = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "profile": self.profile,
            "deploy_id": self.deploy_id,
            "target": dict(self.target),
            "deploy_fingerprint": self.deploy_fingerprint,
            "effective_environment": dict(self.effective_environment),
            "deployment_version": self.deployment_version,
            "created_at": self.created_at,
            "modal_app": self.modal_app,
            "deployment_identity": dict(self.deployment_identity),
            "profile_config_fingerprint": self.profile_config_fingerprint,
            "manifest_path": self.manifest_path,
            "effective_config": dict(self.effective_config),
            "receipt_path": self.receipt_path,
            "modal_destination": dict(self.modal_destination),
        }
        return data

    def validate(self) -> None:
        if not self.profile or not self.created_at:
            raise GateError("deployment receipt is missing required identity")
        if not self.deploy_id:
            raise GateError(
                "deployment receipt has no deploy_id, so a run cannot be checked "
                "against the deployment it claims to be"
            )
        if len(self.deploy_id) != 64 or any(
            c not in "0123456789abcdef" for c in self.deploy_id
        ):
            raise GateError("deployment receipt deploy_id is malformed")
        if not all(self.target.get(name) for name in ("app", "class", "method")):
            raise GateError("deployment receipt target identity is incomplete")
        # Workspace binding still matters: deploying into the wrong Modal
        # workspace is a real operational failure. It is checked here, once,
        # rather than being re-proved through every record that mentions it.
        required_destination = {"workspace_id", "workspace_label", "environment", "source"}
        if (set(self.modal_destination) != required_destination or any(
            not isinstance(self.modal_destination.get(name), str)
            or not self.modal_destination.get(name, "").strip()
            for name in required_destination
        )):
            raise GateError("deployment receipt modal destination is missing or malformed")
        if self.modal_destination.get("source") != "config/v2/modal_target.toml":
            raise GateError("deployment receipt modal destination source is invalid")
        if any("token" in key.lower() or "secret" in key.lower() for key in self.modal_destination):
            raise GateError("deployment receipt modal destination contains credentials")
        if self.modal_app and self.modal_app != self.target["app"]:
            raise GateError("deployment receipt Modal app disagrees with target")
        if type(self.deployment_version) is not int or self.deployment_version < 0:
            raise GateError("deployment receipt deployment version is invalid")
        if any(value == "<redacted>" for value in self.effective_environment.values()):
            raise GateError("deployment receipt effective environment is redacted")
        deploy_flags = (
            self.effective_config.get("deploy_flags", {})
            if isinstance(self.effective_config, Mapping) else {}
        )
        validate_effective_environment(
            self.effective_environment,
            allowed_names={str(name) for name in deploy_flags}
            if isinstance(deploy_flags, Mapping) else None,
        )


    # The manifest, image identity, S4 generation and effective-config copies
    # that used to be cross-checked here are gone. Each one restated a fact
    # deploy_id already determines, or existed so this local file could prove
    # another local file. Which deployment served a request is established by
    # the deploy_id the serving request reports, compared at acceptance time.

def receipt_path(
    repo_root: Path, deploy_fingerprint: str, deployment_version: int | None = None
) -> Path:
    suffix = (
        f"{deployment_version}_{deploy_fingerprint}"
        if deployment_version is not None else deploy_fingerprint
    )
    return Path(repo_root) / ".v2ctl" / "deployments" / (
        f"{RECEIPT_PREFIX}{suffix}.json"
    )


def write_deployment_receipt(repo_root: Path, receipt: DeploymentReceipt) -> Path:
    """Persist one receipt, refusing to replace an existing receipt."""
    receipt.validate()
    path = receipt_path(repo_root, receipt.deploy_fingerprint, receipt.deployment_version)
    if receipt.receipt_path and Path(receipt.receipt_path) != path:
        raise GateError("deployment receipt path identity mismatch")
    serialized = receipt.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            existing = read_deployment_receipt(path)
        except GateError:
            raise GateError(f"deployment receipt already exists and is corrupt: {path}")
        raise GateError(f"deployment receipt is immutable and already exists: {path}")
        return path
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical(serialized) + "\n")
    except FileExistsError:
        raise GateError(f"deployment receipt was concurrently created: {path}")
    return path


def read_deployment_receipt(path: Path) -> DeploymentReceipt:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GateError(f"deployment receipt is missing or corrupt: {path}") from exc
    return DeploymentReceipt.from_dict(raw)


def latest_deployment_receipt(
    repo_root: Path,
    *,
    profile: str | None = None,
    target: Mapping[str, str] | None = None,
    workspace_id: str | None = None,
) -> tuple[Path, DeploymentReceipt] | None:
    directory = Path(repo_root) / ".v2ctl" / "deployments"
    if not directory.is_dir():
        return None
    matches: list[tuple[Path, DeploymentReceipt]] = []
    for path in sorted(directory.glob(f"{RECEIPT_PREFIX}*.json"), reverse=True):
        # Older receipts from another app may predate the immutable digest
        # field.  When the caller has already identified the profile/target,
        # filter those unrelated records before strict receipt parsing.  A
        # malformed record that matches the requested identity is still read
        # and fails closed below; this is only a compatibility boundary for
        # unrelated historical authorities.
        if profile is not None or target is not None:
            try:
                metadata = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise GateError(f"deployment receipt is missing or corrupt: {path}") from exc
            if not isinstance(metadata, Mapping):
                raise GateError(f"deployment receipt is malformed: {path}")
            if profile is not None and metadata.get("profile") != profile:
                continue
            metadata_target = metadata.get("target")
            if target is not None and (
                not isinstance(metadata_target, Mapping)
                or any(metadata_target.get(k) != str(v) for k, v in target.items())
            ):
                continue
            if workspace_id is not None:
                metadata_destination = metadata.get("modal_destination")
                if isinstance(metadata_destination, Mapping):
                    registered_workspace_id = metadata_destination.get("workspace_id")
                else:
                    # Legacy records are intentionally not usable as a
                    # canonical destination authority.
                    registered_workspace_id = None
                if registered_workspace_id != workspace_id:
                    continue
        try:
            receipt = read_deployment_receipt(path)
        except GateError:
            # Never silently fall back from a corrupt authority to an older
            # deployment.  Callers can report the concrete path.
            raise
        if profile is not None and receipt.profile != profile:
            continue
        if target is not None and any(receipt.target.get(k) != str(v) for k, v in target.items()):
            continue
        matches.append((path, receipt))
    if not matches:
        return None
    # Only receipts that survived the requested profile/destination filters can
    # make this lookup ambiguous; unrelated apps are not competing authorities.
    by_app_version: dict[tuple[str, int], list[tuple[Path, DeploymentReceipt]]] = {}
    for item in matches:
        key = (item[1].target.get("app", ""), item[1].deployment_version)
        by_app_version.setdefault(key, []).append(item)
    for (app, version), items in by_app_version.items():
        if len(items) > 1:
            raise GateError(
                "ambiguous deployment receipts: multiple receipts have the same "
                f"app/version ({app}/{version})"
            )
    versions = {}
    for item in matches:
        versions.setdefault(item[1].deployment_version, []).append(item)
    newest_version = max(versions)
    newest = versions[newest_version]
    if len(newest) != 1:
        raise GateError(
            "ambiguous deployment receipts: multiple receipts have the same "
            f"app/version ({newest_version})"
        )
    return newest[0]


def manifest_digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _integrity_digest(data: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(data).encode("utf-8")).hexdigest()






# require_source_probe_evidence removed: source-probe is debug tooling and
# no longer gates a run. See test_source_probe_is_debug_only.py.
