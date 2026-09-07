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

from comfymodal_runtime.deployment_spec import (
    DEPLOYMENT_HASH_NAMESPACE,
    build_canonical_boundary_identity,
    build_v2_late_config,
)


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

    def canonical_identity(self):
        """Return the shared typed boundary identity for this control-plane config.

        Source, dependency, accelerator, deployment, and request identities
        remain independently addressable.  The legacy ``deploy_inputs`` and
        ``run_inputs`` projections remain available for persisted manifests.
        """
        config = self._config
        git = config.git
        target = config.target
        resources = config.resources
        effective_values = self.effective_flag_values()
        deploy_flags = {
            str(flag.name): effective_values[str(flag.name)]
            for flag in list(config.flags or ())
            if flag.change_requires in ("build", "deploy")
        }
        deploy_flags.update({
            str(flag.name): effective_values[str(flag.name)]
            for flag in list(config.unregistered or ())
        })
        source_hashes = {
            str(path): str(sha)
            for path, sha in sorted((git.dirty_hashes or {}).items())
        }
        return build_canonical_boundary_identity(
            foundation_inputs={
                "target": str(target.class_name),
                "python": "3.11",
            },
            dependency_inputs={
                "deploy_flags": deploy_flags,
                "profile": str(config.profile_name),
            },
            accelerator_inputs={
                "gpu": str(resources.gpu),
                "cpu": int(resources.cpu),
                "memory_mb": int(resources.memory_mb),
            },
            late_config_inputs=build_v2_late_config(
                resolved_values=effective_values,
                cpu_request=int(resources.cpu),
                memory_request=int(resources.memory_mb),
            ),
            source_inputs={
                "dirty_hashes": source_hashes,
                "git_head": str(git.head),
            },
            deployment_inputs=self.deploy_inputs(),
            request_inputs={
                "workload": {
                    "fresh_required": bool(config.workload.fresh_required),
                    "conditioning_cache": str(config.workload.conditioning_cache),
                    "expected_output_sha": str(config.workload.expected_output_sha),
                    "run_count": int(config.workload.run_count),
                    "gap_seconds": _fmt(config.workload.gap_seconds),
                    "nonce": str(config.workload.nonce),
                },
                "run_flags": {
                    str(flag.name): effective_values[str(flag.name)]
                    for flag in list(config.flags or ())
                    if flag.change_requires in ("run", "none")
                },
            },
        )

    # Explicit name used by the reserved env/schema field.
    def profile_config_fingerprint(self) -> str:
        return self.config_fingerprint()

    def profile_fingerprint(self) -> str:
        return self.config_fingerprint()

    def experiment_identity(
        self,
        *,
        invocation_id: str = "",
        request_id: str = "",
    ) -> dict[str, Any]:
        """Return the resolved identity carried by a Golden/RX invocation.

        The attention selector is included even when its resolved value is the
        accepted PyTorch default, so changing it cannot reuse a cohort or run
        fingerprint accidentally.
        """
        backend = "sage"
        for flag in list(getattr(self._config, "flags", ()) or ()) + list(
            getattr(self._config, "unregistered", ()) or ()
        ):
            if getattr(flag, "name", "") == "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND":
                backend = str(getattr(flag, "value", "sage") or "sage").strip().lower()
                break
        configured_sage = "auto"
        for flag in list(getattr(self._config, "flags", ()) or ()):
            if getattr(flag, "name", "") == "COMFYMODAL_SAGE_RUNTIME_MODE":
                configured_sage = str(getattr(flag, "value", "auto") or "auto").strip().lower()
                break
        qd2 = any(
            getattr(flag, "name", "") == "COMFYMODAL_V2_GOLDEN_CPU_QD2_PREFETCH"
            and str(getattr(flag, "value", "0") or "0").strip() == "1"
            for flag in list(getattr(self._config, "flags", ()) or ())
        )
        golden_profile = str(getattr(self._config, "profile_name", "") or "").lower().startswith("golden_p1")
        golden_mode = (
            "parallel"
            if str(getattr(self._config, "profile_name", "") or "").lower()
            == "golden_p1_parallel"
            else "serial"
        )
        return {
            "profile": str(getattr(self._config, "profile_name", "") or ""),
            "v2ctl_invocation_id": str(invocation_id or ""),
            "request_id": str(request_id or ""),
            "profile_config_fingerprint": self.profile_config_fingerprint(),
            "deploy_fingerprint": self.deploy_fingerprint(),
            "run_fingerprint": self.run_fingerprint(),
            "attention_backend": backend,
            "attention_backend_configured": backend,
            "attention_backend_resolved": backend,
            "golden_mode": golden_mode if golden_profile else "",
            "golden_arm": ("cpu_qd2_prefetch" if qd2 else "control") if golden_profile else "",
            "cpu_qd2_prefetch": qd2 if golden_profile else False,
            "configured_sage_runtime_mode": configured_sage,
            "resolved_sage_runtime_mode": "",
            "sage_runtime_mode_configured": configured_sage,
            "sage_runtime_mode_effective_input": configured_sage,
            "sage_runtime_mode_resolution_source": "auto_resolution" if configured_sage == "auto" else "explicit_profile",
            "sage_runtime_mode_resolved": "",
        }

    def deployment_hash_namespace(self) -> str:
        """Name the hash domain shared with the runtime image plan."""
        return DEPLOYMENT_HASH_NAMESPACE

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
        return self.canonical_identity().deployment

    def run_fingerprint(self) -> str:
        return self.canonical_identity().request

    def _sha256_hex(self, data: dict) -> str:
        return hashlib.sha256(self.canonical_json(data).encode("utf-8")).hexdigest()
