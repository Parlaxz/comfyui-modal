"""Dependency-free SageAttention runtime policy helpers.

This module is imported by both the deployment/configuration code and the
runtime.  Keep it limited to the standard library: importing it must not
initialize Modal, ComfyUI, Torch, CUDA, or model state.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .baseline_resolvers import production_baseline_value


SAGE_MODES = {"auto", "baked_cuda", "triton_fallback"}
SAGE_RESOLVED_MODES = {"baked_cuda", "triton_fallback"}

# The image is intentionally pinned to the known-good dispatcher.
SAGE_RUNTIME_BASELINE = "baked_cuda"
PRODUCTION_BASELINE_SAGE_MODE = SAGE_RUNTIME_BASELINE
PRODUCTION_BASELINE_PROBE = False


def normalize_sage_mode(value: str | None) -> str:
    """Normalize a Sage mode, using ``auto`` for missing/invalid input."""
    normalized = str(value or "").strip().lower()
    return normalized if normalized in SAGE_MODES else "auto"


def is_production_sage_mode(mode: str) -> bool:
    return normalize_sage_mode(mode) == SAGE_RUNTIME_BASELINE


def _optional_sage_mode(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized if normalized in SAGE_MODES else None


def resolve_sage_runtime_mode(
    file_value: str | None,
    env_value: str | None,
    baseline_value: str | None = None,
    golden_flag: bool = False,
) -> tuple[str, str, str, str]:
    """Resolve the configured Sage mode.

    The result is ``(resolved, reason, effective_input, resolution_source)``.
    Production's explicit baseline is checked before mutable runtime inputs,
    so a stale volume file or inherited environment cannot change production.
    Golden ignores the production baseline but honors its deploy environment;
    this keeps the profile's baked dispatcher from being replaced by a stale
    snapshot-time runtime decision.
    """
    file_mode = _optional_sage_mode(file_value)
    env_mode = _optional_sage_mode(env_value)
    baseline_mode = _optional_sage_mode(baseline_value)

    if golden_flag:
        golden_mode = env_mode or "auto"
        return (
            golden_mode,
            "golden-deploy-environment" if env_mode else "golden-default",
            golden_mode,
            "golden_env",
        )

    if baseline_mode in SAGE_RESOLVED_MODES:
        if file_mode is not None or env_mode is not None:
            return (
                baseline_mode,
                "production-baseline-overrides-runtime-file",
                baseline_mode,
                "baseline",
            )
        return baseline_mode, "production-baseline", baseline_mode, "baseline"

    if file_mode is not None:
        return file_mode, "runtime-file", file_mode, "file"
    if env_mode is not None:
        return env_mode, "runtime-environment", env_mode, "environment"
    return "auto", "default", "auto", "default"


def _optional_probe_value(value: str | bool | int | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def resolve_sage_probe_on_restore(
    file_value: str | bool | int | None,
    env_value: str | bool | int | None,
    baseline_value: str | bool | int | None = None,
    golden_flag: bool = False,
) -> tuple[bool, str, str, str]:
    """Resolve whether restore should run the Sage probe.

    Production baselines are authoritative over mutable file/environment
    values.  Golden ignores that production baseline so its explicitly
    configured runtime value can decide whether probing is appropriate.
    """
    file_probe = _optional_probe_value(file_value)
    env_probe = _optional_probe_value(env_value)
    baseline_probe = _optional_probe_value(baseline_value)

    if not golden_flag and baseline_probe is not None:
        if file_probe is not None or env_probe is not None:
            return (
                baseline_probe,
                "production-baseline-overrides-runtime-file",
                "1" if baseline_probe else "0",
                "baseline",
            )
        return (
            baseline_probe,
            "production-baseline",
            "1" if baseline_probe else "0",
            "baseline",
        )

    if file_probe is not None:
        return file_probe, "runtime-file", "1" if file_probe else "0", "file"
    if env_probe is not None:
        return env_probe, "runtime-environment", "1" if env_probe else "0", "environment"
    return False, "default", "0", "default"


def list_sageattention_extension_files(site_packages_root: str) -> list[Path]:
    """List compiled SageAttention extensions under a site-packages root."""
    root = Path(site_packages_root) / "sageattention"
    if not root.is_dir():
        return []

    # SageAttention 2.2.0 routes SM120 through the _qattn_sm89 family; an
    # _qattn_sm120 filename is not required.
    native_suffixes = {".so", ".pyd", ".dll", ".dylib"}
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and (path.suffix.lower() in native_suffixes or ".so." in path.name.lower())
    )


SAGE_RUNTIME_CACHE_SCHEMA_VERSION = 2
SAGE_RUNTIME_POLICY_VERSION = "ra5-phase-a-v1"
SAGEATTENTION_SOURCE_REPOSITORY = "https://github.com/thu-ml/SageAttention.git"
SAGEATTENTION_GIT_REF = "v2.2.0"
SAGEATTENTION_EXPECTED_NATIVE_FAMILY = "_qattn_sm89"
SAGEATTENTION_SOURCE_POLICY = (
    f"{SAGEATTENTION_SOURCE_REPOSITORY}@{SAGEATTENTION_GIT_REF}"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except (OSError, IOError):
        return ""
    return digest.hexdigest()


def sageattention_artifact_identity(site_packages_root: str) -> dict[str, Any]:
    """Describe an installed SageAttention package without importing it."""
    package_root = Path(site_packages_root) / "sageattention"
    files = list_sageattention_extension_files(site_packages_root)

    manifest: list[dict[str, Any]] = []
    for path in files:
        try:
            relative = path.relative_to(package_root).as_posix()
            size = path.stat().st_size
        except (OSError, ValueError):
            continue
        manifest.append({"path": relative, "size": size, "sha256": _sha256_file(path)})
    manifest.sort(key=lambda item: item["path"])

    site_root = Path(site_packages_root)
    metadata_files: list[dict[str, str]] = []
    for metadata_root in sorted(site_root.glob("sageattention*.dist-info")):
        for name in ("METADATA", "RECORD", "direct_url.json"):
            path = metadata_root / name
            if path.is_file():
                metadata_files.append(
                    {
                        "path": path.relative_to(site_root).as_posix(),
                        "sha256": _sha256_file(path),
                    }
                )

    source_files: list[dict[str, str]] = []
    if package_root.is_dir():
        for path in sorted(package_root.rglob("*.py")):
            if path.is_file():
                source_files.append(
                    {
                        "path": path.relative_to(package_root).as_posix(),
                        "sha256": _sha256_file(path),
                    }
                )

    def manifest_hash(value: Any) -> str:
        canonical = json.dumps(
            value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    return {
        "package_root": str(package_root),
        "extension_manifest": manifest,
        "extension_manifest_hash": manifest_hash(manifest),
        "native_kernel_families": sorted(
            {
                "_fused"
                if "_fused" in item["path"]
                else SAGEATTENTION_EXPECTED_NATIVE_FAMILY
                for item in manifest
                if "_fused" in item["path"]
                or SAGEATTENTION_EXPECTED_NATIVE_FAMILY in item["path"]
            }
        ),
        "source_manifest_hash": manifest_hash(source_files),
        "metadata_manifest_hash": manifest_hash(metadata_files),
    }


def _sage_identity_digest(identity: dict[str, Any]) -> str:
    comparable = {
        key: value
        for key, value in identity.items()
        if key not in {"identity_digest", "created_at", "mode", "reason"}
    }
    return hashlib.sha256(
        json.dumps(
            comparable,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def sage_runtime_identity_matches(cached: dict, current: dict) -> bool:
    """Return whether two complete Sage runtime identities are interchangeable."""
    if not isinstance(cached, dict) or not isinstance(current, dict):
        return False
    if (
        cached.get("schema_version") != SAGE_RUNTIME_CACHE_SCHEMA_VERSION
        or current.get("schema_version") != SAGE_RUNTIME_CACHE_SCHEMA_VERSION
    ):
        return False
    # Recompute rather than trusting a stored digest: a partially edited cache
    # must not match merely because its old digest field was retained.
    return _sage_identity_digest(cached) == _sage_identity_digest(current)


def sage_runtime_cache_usable(
    cached: dict, current: dict, *, strict: bool = False
) -> bool:
    """Apply identity and policy checks before reusing a runtime decision."""
    if not sage_runtime_identity_matches(cached, current):
        return False
    if cached.get("mode") not in {"baked_cuda", "triton_fallback", "disabled"}:
        return False
    # A negative result is never authoritative for the explicit Golden arm.
    return not strict or cached.get("mode") == "baked_cuda"


def build_sage_runtime_identity(
    *,
    site_packages_root: str = "",
    selected_symbol: str = "sageattn",
    kernel_family: str = "sage2++_public_dispatch",
    gpu_name: str = "",
    capability: tuple[int, int] | None = None,
    sage_version: str = "",
    torch_version: str = "",
    torch_cuda: str = "",
    driver_version: str = "",
    image_identity: str = "",
    deployment_identity: str = "",
) -> dict[str, Any]:
    """Build the cache identity without performing runtime imports or probes."""
    artifact = (
        sageattention_artifact_identity(site_packages_root)
        if site_packages_root
        else {
            "extension_manifest": [],
            "extension_manifest_hash": "",
            "native_kernel_families": [],
            "source_manifest_hash": "",
            "metadata_manifest_hash": "",
        }
    )
    identity: dict[str, Any] = {
        "schema_version": SAGE_RUNTIME_CACHE_SCHEMA_VERSION,
        "policy_version": SAGE_RUNTIME_POLICY_VERSION,
        "gpu_name": gpu_name or "unknown",
        "gpu_capability": list(capability) if capability is not None else [],
        "sage_version": sage_version,
        "sage_source_identity": artifact.get("source_manifest_hash", ""),
        "sage_build_identity": artifact.get("metadata_manifest_hash", ""),
        "sage_source_repository": SAGEATTENTION_SOURCE_REPOSITORY,
        "sage_source_ref": SAGEATTENTION_GIT_REF,
        "sage_source_policy": SAGEATTENTION_SOURCE_POLICY,
        "sage_expected_native_family": SAGEATTENTION_EXPECTED_NATIVE_FAMILY,
        "extension_manifest_hash": artifact.get("extension_manifest_hash", ""),
        "torch_version": torch_version,
        "torch_cuda": torch_cuda,
        "driver_version": driver_version,
        "image_identity": image_identity,
        "deployment_identity": deployment_identity,
        "selected_symbol": selected_symbol,
        "kernel_family": kernel_family,
    }
    identity["artifact_identity"] = artifact
    identity["identity_digest"] = _sage_identity_digest(identity)
    return identity


def select_public_sageattention_callable(
    module: Any,
) -> tuple[str | None, Callable | None, dict[str, Any]]:
    """Select SageAttention's public dispatcher, never private kernels."""
    candidate = getattr(module, "sageattn", None)
    if callable(candidate):
        return "sageattn", candidate, {"tensor_layout": "HND", "is_causal": False}
    return None, None, {}


def choose_sage_runtime_mode(
    enabled: bool,
    extension_files: list[Path],
    import_ok: bool,
    smoke_ok: bool,
) -> tuple[str, str]:
    """Choose the executable mode after the optional runtime checks."""
    if not enabled:
        return "disabled", "explicitly-disabled"
    if not extension_files:
        return "triton_fallback", "compiled-extensions-missing"
    if not import_ok:
        return "triton_fallback", "compiled-extensions-unusable"
    if not smoke_ok:
        return "triton_fallback", "smoke-test-failed"
    return "baked_cuda", "compiled-extensions-usable"


def sage_four_field_identity(
    *,
    configured: str,
    effective_input: str,
    resolution_source: str,
    resolved: str,
) -> dict[str, str]:
    """Return the four policy fields used in runtime provenance."""
    normalized_resolved = str(resolved or "").strip().lower()
    if normalized_resolved == "auto":
        normalized_resolved = "missing"
    return {
        "sage_runtime_mode_configured": normalize_sage_mode(configured),
        "sage_runtime_mode_effective_input": normalize_sage_mode(effective_input),
        "sage_runtime_mode_resolution_source": str(
            resolution_source or ""
        ).strip().lower(),
        "sage_runtime_mode_resolved": normalized_resolved,
    }
