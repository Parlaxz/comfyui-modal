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


# ``V2_E19_FINAL_COLD_LOADER`` is a harness selector, not a runtime flag.
# The deploy/run BAT applies these values after v2ctl has resolved the
# profile.  Keep this projection here so control-plane identities describe
# the configuration the container actually receives, while ``ResolvedConfig``
# remains the pre-selector input used by preflight and safety checks.
#
# These are deliberately limited to the flags whose post-selector values are
# part of the runtime snapshot identity.  Do not infer values from a profile
# name: the selector is the canonical activation signal.
_POST_SELECTOR_EFFECTIVE_FLAGS: dict[str, dict[str, str]] = {
    "V2_E19_FINAL_COLD_LOADER": {
        "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "1",
        "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
        "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "1",
        "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "1",
    },
}


def _fmt(value: Any) -> str:
    """Deterministic string form: floats via repr(), everything else str()."""
    if isinstance(value, float):
        return repr(value)
    return str(value)


class FingerprintEngine:
    """Computes deploy/run fingerprints for a resolved configuration."""

    def __init__(self, config: Any) -> None:
        self._config = config

    # -- input assembly ----------------------------------------------------

    def deploy_inputs(self) -> dict:
        """The exact ordered deploy input dict (for manifests / doctor)."""
        config = self._config
        git = config.git
        target = config.target
        resources = config.resources
        effective_values = self.effective_flag_values()
        dirty_hashes = {}
        for path, sha in sorted((git.dirty_hashes or {}).items()):
            dirty_hashes[path] = str(sha)
        deploy_flags = {}
        for flag in list(config.flags or ()):
            if flag.change_requires in ("build", "deploy"):
                deploy_flags[flag.name] = effective_values[flag.name]
        for flag in list(config.unregistered or ()):
            deploy_flags[flag.name] = effective_values[flag.name]
        return {
            "git_head": str(git.head),
            # ``dirty`` is the overall worktree state used by doctor/reporting;
            # deployment identity only includes changes that can be published.
            "git_dirty": bool(dirty_hashes),
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
        effective_values = self.effective_flag_values()
        run_flags = {}
        for flag in list(config.flags or ()):
            if flag.change_requires in ("run", "none"):
                run_flags[flag.name] = effective_values[flag.name]
        for flag in list(config.unregistered or ()):
            run_flags[flag.name] = effective_values[flag.name]
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

    def config_inputs(self) -> dict:
        """All resolved experiment-affecting configuration.

        Unlike deployment/run fingerprints this deliberately has no git or
        timestamp input: it identifies the selected profile and resolved
        configuration itself and is safe to persist in invocation metadata.
        """
        config = self._config
        effective_values = self.effective_flag_values()
        flags = {}
        for flag in list(getattr(config, "flags", ()) or ()):
            flags[str(flag.name)] = effective_values[str(flag.name)]
        for flag in list(getattr(config, "unregistered", ()) or ()):
            flags[str(flag.name)] = effective_values[str(flag.name)]
        return {
            "profile": str(getattr(config, "profile_name", "") or ""),
            "owner": str(getattr(config, "owner", "") or ""),
            "target": self.deploy_inputs()["target"],
            "resources": self.deploy_inputs()["resources"],
            "flags": flags,
            "workload": self.run_inputs()["workload"],
            "runtime_override_policy": str(
                getattr(config, "runtime_override_policy", "") or ""
            ),
        }

    def config_fingerprint(self) -> str:
        """Stable fingerprint of the resolved profile/configuration."""
        return self._sha256_hex(self.config_inputs())

    # Explicit name used by the reserved env/schema field.
    def profile_config_fingerprint(self) -> str:
        return self.config_fingerprint()

    def profile_fingerprint(self) -> str:
        return self.config_fingerprint()

    def effective_flag_values(self) -> dict[str, str]:
        """Return flag values after the canonical deploy-selector projection.

        The resolver intentionally exposes the values requested by the
        profile.  The launcher then applies selector-owned values before
        deployment.  Project only flags already present in the resolved
        configuration so this helper never invents a flag or a default for
        duck-typed/older configurations.
        """
        config = self._config
        values: dict[str, str] = {}
        flags = list(getattr(config, "flags", ()) or ())
        flags += list(getattr(config, "unregistered", ()) or ())
        for flag in flags:
            values[str(flag.name)] = _fmt(flag.value)

        for selector, effects in _POST_SELECTOR_EFFECTIVE_FLAGS.items():
            selector_value = values.get(selector, "").strip().lower()
            if selector_value not in {"1", "true", "yes", "on"}:
                continue
            for name, value in effects.items():
                if name in values:
                    values[name] = value
        return values

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
