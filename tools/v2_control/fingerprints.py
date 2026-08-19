"""Deterministic deploy/run fingerprints for the v2ctl control plane (E32).

``FingerprintEngine`` computes two stable sha256 fingerprints over the
canonical JSON of the deploy-relevant and run-relevant configuration:

* deploy fingerprint — git head/dirty state, target, resources, profile,
  deploy-required flags, runtime-override policy;
* run fingerprint — deploy fingerprint + workload identity + run-time flags.

Unregistered (unknown) flags are included in BOTH fingerprints: an unknown
flag may be deploy-capable, so "unknown is not trusted" means a changed
unregistered flag alters the deploy fingerprint too.

Deterministic: values are strings, floats are formatted via ``repr()``,
canonical JSON uses ``sort_keys`` with compact separators and
``ensure_ascii=False``.  No timestamps, no randomness.

Python 3.11 stdlib only.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _fmt(value: Any) -> str:
    """Deterministic string form: floats via repr(), everything else str()."""
    if isinstance(value, float):
        return repr(value)
    return str(value)


class FingerprintEngine:
    """Computes deploy/run fingerprints for a resolved configuration."""

    def __init__(self, config: "ResolvedConfig") -> None:
        self._config = config

    # -- input assembly ----------------------------------------------------

    def deploy_inputs(self) -> dict:
        """The exact ordered deploy input dict (for manifests / doctor)."""
        config = self._config
        git = config.git
        target = config.target
        resources = config.resources
        dirty_hashes = {}
        for path, sha in sorted((git.dirty_hashes or {}).items()):
            dirty_hashes[path] = str(sha)
        deploy_flags = {}
        for flag in list(config.flags or ()):
            if flag.change_requires in ("build", "deploy"):
                deploy_flags[flag.name] = _fmt(flag.value)
        for flag in list(config.unregistered or ()):
            deploy_flags[flag.name] = _fmt(flag.value)
        return {
            "git_head": str(git.head),
            "git_dirty": bool(git.dirty),
            "dirty_hashes": dirty_hashes,
            "target": {
                "app": str(target.app),
                "class_name": str(target.class_name),
                "method": str(target.method),
            },
            "resources": {
                "gpu": str(resources.gpu),
                "cpu": int(resources.cpu),
                "memory_mb": int(resources.memory_mb),
                "min_containers": int(resources.min_containers),
                "scaledown_window": int(resources.scaledown_window),
            },
            "profile": str(config.profile_name),
            "deploy_flags": deploy_flags,
            "runtime_override_policy": str(config.runtime_override_policy),
        }

    def run_inputs(self) -> dict:
        """The exact ordered run input dict (for manifests / doctor)."""
        config = self._config
        workload = config.workload
        run_flags = {}
        for flag in list(config.flags or ()):
            if flag.change_requires in ("run", "none"):
                run_flags[flag.name] = _fmt(flag.value)
        for flag in list(config.unregistered or ()):
            run_flags[flag.name] = _fmt(flag.value)
        return {
            "deploy_fingerprint": self.deploy_fingerprint(),
            "workload": {
                "fresh_required": bool(workload.fresh_required),
                "conditioning_cache": str(workload.conditioning_cache),
                "expected_output_sha": str(workload.expected_output_sha),
                "run_count": int(workload.run_count),
                "gap_seconds": _fmt(workload.gap_seconds),
                "nonce": str(workload.nonce),
            },
            "run_flags": run_flags,
        }

    # -- fingerprints ------------------------------------------------------

    @staticmethod
    def canonical_json(data: dict) -> str:
        """Deterministic compact canonical JSON."""
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def deploy_fingerprint(self) -> str:
        return self._sha256_hex(self.deploy_inputs())

    def run_fingerprint(self) -> str:
        return self._sha256_hex(self.run_inputs())

    def _sha256_hex(self, data: dict) -> str:
        return hashlib.sha256(self.canonical_json(data).encode("utf-8")).hexdigest()
