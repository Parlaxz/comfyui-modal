"""Provenance blocks for the v2ctl control plane (Batch E32).

Implements design section 13 ("Effective-Config Proof in Run Artifacts") of
V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md:

* every accepted run artifact carries a ``v2ctl`` provenance block;
* the block records what the caller requested, what v2ctl resolved, which
  deployment/run fingerprints were active, where each value came from, and
  the runtime override state;
* the remote runtime emits a compact fingerprint line such as
  ``[v2ctl.config] deploy=7f4d... run=1a03... profile=e29-tracer``;
* full environments are never dumped; requested/effective environments are
  redacted before persisting.

Provenance is written as a *sibling* file ``<artifact>.v2ctl-provenance.json``
so the artifact itself (and therefore the E29/E30/E31 files) is never
modified.

Python 3.11 stdlib only; no network calls.
"""

from __future__ import annotations

import json
import hashlib
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

LOG = logging.getLogger("v2ctl.provenance")

PROVENANCE_SCHEMA_VERSION = 1

# Secret-ish substrings used as a final redaction backstop (the primary
# redaction is done by the caller via EnvironmentBuilder.display).  A value
# is redacted when its NAME (key) or its value contains one of these markers,
# so secrets can never leak even if the caller's redaction missed them.
_SECRET_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "API_KEY",
    "CREDENTIAL",
    "AUTH",
    "FINGERPRINT",
)


def _redacted(key: str, value: str) -> str:
    haystack = f"{key} {value}".upper()
    return "<redacted>" if any(marker in haystack for marker in _SECRET_MARKERS) else value


@dataclass
class Provenance:
    """Effective-config proof block (design section 13)."""

    profile: str
    owner: str
    deploy_fingerprint: str
    run_fingerprint: str
    git_head: str
    target: dict = field(default_factory=dict)
    resources: dict = field(default_factory=dict)
    requested_environment: dict = field(default_factory=dict)  # redacted
    effective_environment: dict = field(default_factory=dict)  # redacted
    flag_sources: dict = field(default_factory=dict)
    unregistered_flags: list = field(default_factory=list)
    runtime_overrides: list = field(default_factory=list)
    workload: dict = field(default_factory=dict)
    v2ctl_invocation_id: str = ""
    profile_config_fingerprint: str = ""
    request_id: str = ""
    artifact_path: str = ""
    # Optional integrity metadata.  It is populated by
    # write_provenance_sibling after the artifact's final bytes exist; it is
    # intentionally not embedded in the artifact itself.
    artifact_sha256: str | None = None

    def to_dict(self) -> dict:
        return {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "profile": self.profile,
            "owner": self.owner,
            "deploy_fingerprint": self.deploy_fingerprint,
            "run_fingerprint": self.run_fingerprint,
            "git_head": self.git_head,
            "target": dict(self.target),
            "resources": dict(self.resources),
            "requested_environment": dict(self.requested_environment),
            "effective_environment": dict(self.effective_environment),
            "flag_sources": dict(self.flag_sources),
            "unregistered_flags": list(self.unregistered_flags),
            "runtime_overrides": [dict(o) for o in self.runtime_overrides],
            "workload": dict(self.workload),
            "v2ctl_invocation_id": self.v2ctl_invocation_id,
            "profile_config_fingerprint": self.profile_config_fingerprint,
            "request_id": self.request_id,
            "artifact_path": self.artifact_path,
            "artifact_sha256": self.artifact_sha256,
        }

    def to_json(self) -> str:
        """Compact, deterministically-sorted JSON."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def from_dict(data: dict) -> "Provenance":
        return Provenance(
            profile=str(data.get("profile", "")),
            owner=str(data.get("owner", "")),
            deploy_fingerprint=str(data.get("deploy_fingerprint", "")),
            run_fingerprint=str(data.get("run_fingerprint", "")),
            git_head=str(data.get("git_head", "")),
            target=dict(data.get("target") or {}),
            resources=dict(data.get("resources") or {}),
            requested_environment=dict(data.get("requested_environment") or {}),
            effective_environment=dict(data.get("effective_environment") or {}),
            flag_sources=dict(data.get("flag_sources") or {}),
            unregistered_flags=list(data.get("unregistered_flags") or []),
            runtime_overrides=list(data.get("runtime_overrides") or []),
            workload=dict(data.get("workload") or {}),
            v2ctl_invocation_id=str(data.get("v2ctl_invocation_id", "") or ""),
            profile_config_fingerprint=str(data.get("profile_config_fingerprint", "") or ""),
            request_id=str(data.get("request_id", "") or ""),
            artifact_path=str(data.get("artifact_path", "") or ""),
            artifact_sha256=(str(data["artifact_sha256"]) if data.get("artifact_sha256") else None),
        )

    def fingerprint_line(self) -> str:
        """Compact remote-emitted line:
        ``[v2ctl.config] deploy=XXXX run=YYYY profile=NAME`` (8-char
        prefixes)."""
        return (
            f"[v2ctl.config] deploy={self.deploy_fingerprint[:8]} "
            f"run={self.run_fingerprint[:8]} profile={self.profile}"
        )


# --------------------------------------------------------------------------
# construction / persistence
# --------------------------------------------------------------------------


def build_provenance(
    config: Any,  # ResolvedConfig
    env: dict,
    deploy_fp: str,
    run_fp: str,
    overrides: list[Any],  # list[RuntimeOverride]
    *,
    invocation_id: str = "",
    profile_config_fingerprint: str = "",
    request_id: str = "",
) -> Provenance:
    """Build a Provenance from a resolved config, a built environment (which
    the caller has already redacted via EnvironmentBuilder), fingerprints,
    and the runtime override inventory."""
    target = getattr(config, "target", None)
    resources = getattr(config, "resources", None)
    workload = getattr(config, "workload", None)
    git = getattr(config, "git", None)

    flag_sources: dict[str, str] = {}
    for flag in getattr(config, "flags", []) or []:
        name = getattr(flag, "name", None)
        if name is None:
            continue
        flag_sources[str(name)] = str(getattr(flag, "source", "unknown"))

    unregistered: list[str] = []
    for flag in getattr(config, "unregistered", []) or []:
        name = getattr(flag, "name", None)
        if name is not None:
            unregistered.append(str(name))

    # redaction backstop: never persist anything that smells like a secret,
    # even if the caller's redaction missed it (key OR value based)
    requested_env = {str(k): _redacted(str(k), str(v)) for k, v in (env or {}).items()}
    effective_env = {str(k): _redacted(str(k), str(v)) for k, v in (env or {}).items()}

    return Provenance(
        profile=str(getattr(config, "profile_name", "") or ""),
        owner=str(getattr(config, "owner", "") or ""),
        deploy_fingerprint=str(deploy_fp),
        run_fingerprint=str(run_fp),
        git_head=str(getattr(git, "head", "") if git is not None else ""),
        target=_as_dict(target),
        resources=_as_dict(resources),
        requested_environment=requested_env,
        effective_environment=effective_env,
        flag_sources=flag_sources,
        unregistered_flags=sorted(unregistered),
        runtime_overrides=[_override_dict(o) for o in (overrides or [])],
        workload=_as_dict(workload),
        v2ctl_invocation_id=str(invocation_id or ""),
        profile_config_fingerprint=str(profile_config_fingerprint or ""),
        request_id=str(request_id or ""),
    )


def write_provenance_sibling(artifact: Path, provenance: Provenance) -> Path:
    """Write ``<artifact>.v2ctl-provenance.json`` next to the artifact.

    The canonical path and optional integrity digest are finalized here, after
    the artifact bytes have been written.  This keeps ``artifact_sha256`` out
    of the artifact's own JSON and avoids an impossible embedded self-hash.
    NEVER modifies the artifact itself.  Returns the sibling path.
    """
    artifact = Path(artifact)
    sibling = artifact.with_name(artifact.name + ".v2ctl-provenance.json")
    sibling.parent.mkdir(parents=True, exist_ok=True)
    digest: str | None = None
    if artifact.is_file():
        hasher = hashlib.sha256()
        with artifact.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
    finalized = replace(
        provenance,
        artifact_path=str(artifact.resolve()),
        artifact_sha256=digest,
    )
    sibling.write_text(finalized.to_json() + "\n", encoding="utf-8")
    LOG.info("provenance sibling written: %s", sibling)
    return sibling


def read_provenance_sibling(artifact: Path) -> Provenance | None:
    """Read back the sibling provenance file; None when missing/corrupt."""
    artifact = Path(artifact)
    sibling = artifact.with_name(artifact.name + ".v2ctl-provenance.json")
    try:
        raw = sibling.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        LOG.warning("provenance sibling %s is corrupt", sibling)
        return None
    if not isinstance(data, dict):
        return None
    return Provenance.from_dict(data)


def inject_provenance_hook_doc() -> str:
    """Returns the exact deferred-hook snippet text (compact fingerprint-line
    emission in the remote runtime) WITHOUT applying it.

    This is the shared edit to be performed in a later batch: the remote
    runtime (comfymodal_runtime) will emit a one-line effective-config proof
    so run artifacts can be reconciled against the v2ctl provenance block.
    """
    return (
        "# v2ctl deferred provenance hook (NOT applied in E32; apply in the "
        "shared-edit batch)\n"
        "#\n"
        "# Emit a compact effective-config proof line on every accepted run so "
        "# that run artifacts can be reconciled against the provenance sibling\n"
        "# written by v2ctl (<artifact>.v2ctl-provenance.json).\n"
        "#\n"
        "# Where: comfymodal_runtime request handler, after environment "
        "resolution and\n"
        "#        before/around the first result materialization, guarded by "
        "the presence of\n"
        "#        COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT / "
        "COMFYMODAL_V2CTL_RUN_FINGERPRINT in the "
        "effective environment.\n"
        "#\n"
        "import os\n"
        "\n"
        "def _emit_v2ctl_provenance_line():\n"
        "    deploy_fp = os.environ.get('COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT', '')\n"
        "    run_fp = os.environ.get('COMFYMODAL_V2CTL_RUN_FINGERPRINT', '')\n"
        "    profile = os.environ.get('COMFYMODAL_V2CTL_PROFILE', '')\n"
        "    if not (deploy_fp and run_fp):\n"
        "        return  # not a v2ctl-controlled run; no proof line\n"
        "    line = '[v2ctl.config] deploy={} run={} profile={}'.format(\n"
        "        deploy_fp[:8], run_fp[:8], profile)\n"
        "    print(line, flush=True)\n"
        "\n"
        "# _emit_v2ctl_provenance_line()  # call at the accepted-run emission "
        "point\n"
        "#\n"
        "# Notes:\n"
        "# - prefixes are the first 8 hex chars of the sha256 fingerprints\n"
        "# - never dump the full environment or any secret values\n"
        "# - keep this line stable; validators (StructuralValidator) accept\n"
        "#   request_id/correlation_id and the v2ctl_config proof line from\n"
        "#   backend stdout"
    )


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _as_dict(obj: Any) -> dict:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return {str(k): v for k, v in obj.items() if not k.startswith("_")}
    return {
        str(key): getattr(obj, key)
        for key in (
            "app",
            "class_name",
            "method",
            "gpu",
            "cpu",
            "memory_mb",
            "min_containers",
            "scaledown_window",
            "fresh_required",
            "conditioning_cache",
            "expected_output_sha",
            "run_count",
            "gap_seconds",
            "nonce",
        )
        if hasattr(obj, key)
    }


def _override_dict(override: Any) -> dict:
    if isinstance(override, dict):
        return {str(k): v for k, v in override.items()}
    return {
        "name": str(getattr(override, "name", "")),
        "value": str(getattr(override, "value", "")),
        "source": str(getattr(override, "source", "")),
    }
