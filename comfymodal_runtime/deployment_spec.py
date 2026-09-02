"""Canonical deployment source manifest / DeploymentIdentity builder.

Excludes ``reference/``, ``*.ref``, ``*.v21610_backup``, ``before_v2_*``,
benchmark outputs, logs, screenshots, temporary JSON, local Studio outputs,
generated state, ``.git``, ``node_modules``, ``tests``, and ``docs`` unless
explicitly allowed.

Pure functions — suitable for unit tests without Modal or volume access.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from comfymodal_runtime.contracts import (
    DEPLOYMENT_HASH_NAMESPACE,
    DEPLOYMENT_IDENTITY_SCHEMA_VERSION,
    DeploymentIdentity,
)
from .publication_policy import (
    ALLOWED_SOURCE_EXTENSIONS,
    EXCLUDED_DIR_NAMES as EXCLUDED_DIRS,
    EXCLUDED_EXTENSIONS,
    EXCLUDED_FILENAMES,
    EXCLUDED_INFIXES,
    EXCLUDED_PREFIXES,
    GENERATED_JSON_PREFIXES,
    is_excluded_dir_name as _policy_excluded_dir_name,
    is_excluded_name,
    iter_syncable_custom_node_dirs,
    iter_source_files,
)
from .sage_policy import SAGE_RUNTIME_BASELINE


# This is the final, source/runtime-only environment boundary.  Keep the
# values here rather than importing comfyapp: v2ctl must be able to calculate
# the same identity without importing Modal or inheriting the shell.
_V2_STATIC_RUNTIME_ENV: dict[str, str] = {
    "TORCHINDUCTOR_CACHE_DIR": "/root/comfymodal_runtime_state/.inductor-cache",
    "TORCHINDUCTOR_FX_GRAPH_CACHE": "1",
    "TRITON_CACHE_DIR": "/tmp/triton_cache",
    "TORCHINDUCTOR_EMULATE_PRECISION_CASTS": "1",
    "TORCHINDUCTOR_COMPILE_THREADS": "1",
    "COMFYMODAL_ENABLE_TORCH_COMPILE": "0",
    "COMFYMODAL_ENABLE_GPU_SNAPSHOT": "0",
    "COMFYMODAL_WARMUP_TEXT": "warmup",
    "COMFYMODAL_SAGE_RUNTIME_MODE": SAGE_RUNTIME_BASELINE,
    "COMFYMODAL_SAGE_RUNTIME_PROBE_ON_RESTORE": "0",
    "COMFYMODAL_PRELOAD_MODE": "clip_only",
    "COMFYMODAL_DIRECT_WARMUP_LOAD_UNET": "0",
    "COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP": "1",
    "COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE": "1",
    "COMFYMODAL_EXACT_CLIP_PREFILL": "1",
    "COMFYMODAL_DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT": "1",
    "COMFYMODAL_SAFETENSORS_READ_MODE": "normal",
    "COMFYMODAL_RUNTIME": "1",
    "PROMPT_ASYNC_PRELOAD": "0",
    "PROMPT_PRELOAD_WORKERS": "2",
    "PROMPT_ASYNC_ACTUAL_LOAD": "1",
    "PROMPT_ASYNC_ACTUAL_LOAD_UNET": "1",
    "ACTUAL_LOAD_MODE": "unet_vae_only",
    "DISABLE_CACHEDIT_FOR_Z_IMAGE": "0",
    "DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE": "0",
    "COMFYMODAL_REQUIREMENTS_REPAIR_MODE": "fail_fast",
    "COMFYMODAL_PRELOAD_UNKNOWN_PROFILES": "0",
    "COMFYMODAL_PRELOAD_MAX_TOTAL_GB": "12",
    "COMFYMODAL_PRELOAD_MAX_FILE_GB": "10",
    "COMFYMODAL_PRELOAD_MIN_THROUGHPUT_GBPS": "0.5",
    "COMFYMODAL_PRELOAD_OUTLIER_ABORT_SECONDS": "10",
    "COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY": "0",
    "COMFYMODAL_EXPERIMENTAL_RESTORE_BACKGROUND_CODE": "0",
    "COMFYMODAL_RESTORE_BACKGROUND_UNET": "0",
}

_V2_EFFECTIVE_RUNTIME_DEFAULTS = {
    "COMFYMODAL_V2_PREFILL_LANES": "critical",
    "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "0",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "off",
}


def compute_v2_runtime_revision(runtime_root: str | Path | None = None) -> str:
    """Return the stable content revision for packaged runtime Python files."""
    root = (Path(__file__).resolve().parent if runtime_root is None else Path(runtime_root)).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"runtime package is not a directory: {root}")
    source_files = []
    for path in root.rglob("*.py"):
        resolved_path = path.resolve()
        if not resolved_path.is_relative_to(root):
            raise ValueError(f"runtime source escapes package: {path}")
        if not resolved_path.is_file():
            raise OSError(f"runtime source is not a file: {path}")
        source_files.append((path.relative_to(root).as_posix(), resolved_path))
    digest = hashlib.sha256()
    for relative_path, path in sorted(source_files, key=lambda item: item[0]):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def build_v2_late_config(
    *,
    environment: Mapping[str, Any] | None = None,
    resolved_values: Mapping[str, Any] | None = None,
    cpu_request: int | None = None,
    memory_request: int | None = None,
    runtime_root: str | Path | None = None,
    runtime_revision: str | None = None,
) -> dict[str, str]:
    """Build the flat environment applied by the canonical late image layer.

    Inputs are explicit snapshots.  In particular, this function never reads
    ``os.environ``; callers that intentionally want host values must pass a
    copied mapping.  ``resolved_values`` wins over ``environment`` and is the
    channel used by v2ctl's sanitized configuration.
    """
    ambient = dict(environment or {})
    resolved = dict(resolved_values or {})

    def value(name: str, default: str) -> str:
        raw = resolved.get(name, ambient.get(name, default))
        return str(raw)

    result = dict(_V2_STATIC_RUNTIME_ENV)
    for name, default in _V2_EFFECTIVE_RUNTIME_DEFAULTS.items():
        result[name] = value(name, default)
    result["COMFYMODAL_V2_RUNTIME_REVISION"] = (
        str(runtime_revision)
        if runtime_revision is not None
        else compute_v2_runtime_revision(runtime_root)
    )

    # Shape parsing is shared with the runtime, but receives only the explicit
    # resolved/environment snapshot.  Target resources override stale aliases
    # in a profile so the identity records the actual requested shape.
    from .runtime_shape import runtime_shape_config

    shape_inputs = dict(ambient)
    shape_inputs.update(resolved)
    shape = runtime_shape_config(
        cpu_request=cpu_request,
        memory_request=memory_request,
        environment=shape_inputs,
    )
    result.update(shape.environment())
    return result


def _stable_identity_hash(value: Any) -> str:
    """Hash one canonical, JSON-serializable identity component."""
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class CanonicalBoundaryIdentity:
    """Typed identities for the independently cacheable deployment boundaries.

    The fields are intentionally separate: changing source does not imply a
    dependency rebuild, and request-only values never become deployment
    identity.  ``deployment`` and ``request`` are derived summaries, not a
    replacement for the component identities.
    """

    schema_version: int = 2
    hash_namespace: str = DEPLOYMENT_HASH_NAMESPACE
    foundation: str = ""
    dependency: str = ""
    accelerator: str = ""
    source: str = ""
    late_config: str = ""
    deployment: str = ""
    request: str = ""
    # Persisted plans use this explicit proof to bind the compatibility
    # source record (including its manifest) to the canonical identity.  It
    # is optional for callers that provide source_inputs directly.
    source_manifest_hash: str = ""

    def for_boundary(self, boundary: str) -> str:
        if boundary not in {
            "foundation", "dependency", "accelerator", "source",
            "late_config", "deployment", "request",
        }:
            raise ValueError(f"unknown identity boundary: {boundary!r}")
        return str(getattr(self, boundary))

    @property
    def combined_hash(self) -> str:
        """Compatibility spelling used by existing runtime metadata callers."""
        return self.deployment

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "hash_namespace": self.hash_namespace,
            "foundation": self.foundation,
            "dependency": self.dependency,
            "accelerator": self.accelerator,
            "source": self.source,
            "late_config": self.late_config,
            "deployment": self.deployment,
            "request": self.request,
            "source_manifest_hash": self.source_manifest_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CanonicalBoundaryIdentity":
        if not isinstance(value, Mapping):
            raise ValueError("canonical identity must be an object")
        if value.get("schema_version") != cls.schema_version:
            raise ValueError(
                f"canonical identity schema mismatch: {value.get('schema_version')!r}"
            )
        if value.get("hash_namespace") != DEPLOYMENT_HASH_NAMESPACE:
            raise ValueError("canonical identity hash namespace is missing or unsupported")
        identity = cls(
            schema_version=int(value["schema_version"]),
            hash_namespace=str(value["hash_namespace"]),
            foundation=str(value.get("foundation", "")),
            dependency=str(value.get("dependency", "")),
            accelerator=str(value.get("accelerator", "")),
            source=str(value.get("source", "")),
            late_config=str(value.get("late_config", "")),
            deployment=str(value.get("deployment", "")),
            request=str(value.get("request", "")),
            source_manifest_hash=str(value.get("source_manifest_hash", "")),
        )
        validate_canonical_boundary_identity(identity)
        return identity


def validate_canonical_boundary_identity(identity: CanonicalBoundaryIdentity) -> None:
    """Reject incomplete identities before image/resource construction."""
    if not isinstance(identity, CanonicalBoundaryIdentity):
        raise ValueError("canonical identity has an unsupported type")
    if identity.schema_version != 2:
        raise ValueError(f"canonical identity schema mismatch: {identity.schema_version!r}")
    if identity.hash_namespace != DEPLOYMENT_HASH_NAMESPACE:
        raise ValueError("canonical identity hash namespace is missing or unsupported")
    missing = [
        name for name in (
            "foundation", "dependency", "accelerator", "source",
            "late_config", "deployment", "request",
        ) if not str(getattr(identity, name, "")).strip()
    ]
    if missing:
        raise ValueError(
            "canonical identity incomplete: missing " + ", ".join(missing)
        )


def _is_sha256_hex(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _source_manifest_payload(identity: DeploymentIdentity) -> dict[str, Any]:
    """Return the reproducible persisted-source proof payload.

    This deliberately contains only fields present in the persisted record;
    validation must not claim to recompute bytes that are not recorded there.
    """
    return {
        "schema_version": int(identity.schema_version),
        "runtime_hash": str(identity.runtime_hash),
        "dependency_hash": str(identity.dependency_hash),
        "custom_node_hash": str(identity.custom_node_hash),
        "source_bytes": int(identity.source_bytes),
        "file_hashes": dict(identity.file_hashes),
    }


def source_manifest_hash(identity: DeploymentIdentity) -> str:
    """Hash the complete persisted source record independently of deployment."""
    return _stable_identity_hash(_source_manifest_payload(identity))


def _validate_persisted_source_record(identity: DeploymentIdentity) -> None:
    """Validate relationships that the persisted source manifest can prove."""
    if (
        not isinstance(identity.schema_version, int)
        or isinstance(identity.schema_version, bool)
        or identity.schema_version != DEPLOYMENT_IDENTITY_SCHEMA_VERSION
    ):
        raise ValueError("source identity schema mismatch")
    if identity.hash_namespace != DEPLOYMENT_HASH_NAMESPACE:
        raise ValueError("source identity hash namespace is missing or unsupported")
    if (
        not isinstance(identity.source_bytes, int)
        or isinstance(identity.source_bytes, bool)
        or identity.source_bytes <= 0
    ):
        raise ValueError("source identity incomplete")
    if not _is_sha256_hex(identity.runtime_hash):
        raise ValueError("source identity runtime_hash is invalid")
    if not _is_sha256_hex(identity.dependency_hash):
        raise ValueError("source identity dependency_hash is invalid")
    if not _is_sha256_hex(identity.custom_node_hash):
        raise ValueError("source identity custom_node_hash is invalid")

    hashes = dict(identity.file_hashes)
    if not hashes:
        raise ValueError("source identity file_hashes are missing")
    for path, digest in hashes.items():
        if not isinstance(path, str) or not path or "\\" in path:
            raise ValueError("source identity file_hashes contain an invalid path")
        if not _is_sha256_hex(digest):
            raise ValueError("source identity file_hashes contain an invalid hash")

    runtime_hashes = {
        path: digest
        for path, digest in hashes.items()
        if not path.startswith("custom_node_root_")
    }
    custom_hashes = {
        path: digest
        for path, digest in hashes.items()
        if path.startswith("custom_node_root_")
    }
    if compute_aggregate_hash(runtime_hashes) != identity.runtime_hash:
        raise ValueError("source identity runtime_hash does not match file_hashes")
    if not custom_hashes or compute_aggregate_hash(custom_hashes) != identity.custom_node_hash:
        raise ValueError("source identity custom_node_hash does not match file_hashes")
    # Exact byte totals cannot be reconstructed from content digests.  This
    # lower bound is the only size relationship the persisted manifest proves.
    if identity.source_bytes < len(hashes):
        raise ValueError("source identity source_bytes is inconsistent with file_hashes")


def validate_persisted_identity_pair(
    source_identity: DeploymentIdentity,
    canonical_identity: CanonicalBoundaryIdentity,
) -> None:
    """Fail closed when a persisted source record disagrees with its plan.

    The canonical plan carries ``source_manifest_hash`` as the authoritative
    proof for fields whose source tree is unavailable at runtime.  No inverse
    hash formula or mutable global state is used here.
    """
    if not isinstance(source_identity, DeploymentIdentity):
        raise ValueError("source identity has an unsupported type")
    validate_canonical_boundary_identity(canonical_identity)
    _validate_persisted_source_record(source_identity)
    if source_identity.combined_hash != canonical_identity.deployment:
        raise ValueError("canonical source/deployment identity hash mismatch")
    expected = source_manifest_hash(source_identity)
    if canonical_identity.source_manifest_hash != expected:
        raise ValueError("canonical source manifest hash mismatch")


def deployment_identity_from_dict(value: Mapping[str, Any]) -> DeploymentIdentity:
    """Restore the source compatibility record persisted in image metadata."""
    if not isinstance(value, Mapping):
        raise ValueError("source identity must be an object")
    if value.get("schema_version") != DEPLOYMENT_IDENTITY_SCHEMA_VERSION:
        raise ValueError(
            f"source identity schema mismatch: {value.get('schema_version')!r}"
        )
    if value.get("hash_namespace") != DEPLOYMENT_HASH_NAMESPACE:
        raise ValueError("source identity hash namespace is missing or unsupported")
    file_hashes = value.get("file_hashes")
    if not isinstance(file_hashes, Mapping):
        raise ValueError("source identity file_hashes must be an object")
    raw_source_bytes = value.get("source_bytes", 0)
    if isinstance(raw_source_bytes, bool) or not isinstance(raw_source_bytes, int):
        raise ValueError("source identity source_bytes is invalid")
    identity = DeploymentIdentity(
        schema_version=int(value["schema_version"]),
        runtime_hash=str(value.get("runtime_hash", "")),
        dependency_hash=str(value.get("dependency_hash", "")),
        custom_node_hash=str(value.get("custom_node_hash", "")),
        source_bytes=raw_source_bytes,
        file_hashes=dict(file_hashes),
        deployment_hash=str(value.get("deployment_hash", "")),
        hash_namespace=str(value.get("hash_namespace", "")),
    )
    if not identity.deployment_hash:
        raise ValueError("source identity incomplete")
    _validate_persisted_source_record(identity)
    if "combined_hash" in value and value["combined_hash"] != identity.combined_hash:
        raise ValueError("source identity combined_hash mismatch")
    return identity


def build_canonical_boundary_identity(
    *,
    source_identity: "DeploymentIdentity | None" = None,
    source_inputs: Mapping[str, Any] | None = None,
    foundation_inputs: Mapping[str, Any] | None = None,
    dependency_inputs: Mapping[str, Any] | None = None,
    accelerator_inputs: Mapping[str, Any] | None = None,
    late_config_inputs: Mapping[str, Any] | None = None,
    deployment_inputs: Mapping[str, Any] | None = None,
    request_inputs: Mapping[str, Any] | None = None,
) -> CanonicalBoundaryIdentity:
    """Build all typed identity components from one publication policy.

    ``source_identity`` is the existing compatibility contract.  Its source
    hash remains useful to older callers while the boundary hashes make the
    dependency/source split explicit and cache-safe.
    """
    missing_inputs = [
        name for name, value in (
            ("foundation", foundation_inputs),
            ("dependency", dependency_inputs),
            ("accelerator", accelerator_inputs),
            ("late_config", late_config_inputs),
        ) if not value
    ]
    if source_identity is not None and (
        source_identity.source_bytes <= 0
        or not source_identity.runtime_hash
        or not source_identity.dependency_hash
        or not source_identity.custom_node_hash
    ):
        missing_inputs.append("source_identity")
    if source_identity is None and not source_inputs:
        missing_inputs.append("source")
    if missing_inputs:
        raise ValueError(
            "canonical identity inputs missing: " + ", ".join(missing_inputs)
        )

    foundation = _stable_identity_hash(dict(foundation_inputs or {}))
    dependency = _stable_identity_hash(dict(dependency_inputs or {}))
    accelerator = _stable_identity_hash(dict(accelerator_inputs or {}))
    late_config = _stable_identity_hash(dict(late_config_inputs or {}))
    source_manifest = ""
    if source_identity is not None:
        source_payload: Mapping[str, Any] = {
            "runtime_hash": source_identity.runtime_hash,
            "custom_node_hash": source_identity.custom_node_hash,
        }
        source_manifest = source_manifest_hash(source_identity)
    else:
        source_payload = dict(source_inputs or {})
    source = _stable_identity_hash(source_payload)
    deployment = _stable_identity_hash({
        "hash_namespace": DEPLOYMENT_HASH_NAMESPACE,
        "schema_version": 2,
        "foundation": foundation,
        "dependency": dependency,
        "accelerator": accelerator,
        "source": source,
        "late_config": late_config,
        "deployment_inputs": dict(deployment_inputs or {}),
    })
    request = _stable_identity_hash({
        "deployment": deployment,
        "request": dict(request_inputs or {}),
    })
    return CanonicalBoundaryIdentity(
        schema_version=2,
        hash_namespace=DEPLOYMENT_HASH_NAMESPACE,
        foundation=foundation,
        dependency=dependency,
        accelerator=accelerator,
        source=source,
        late_config=late_config,
        deployment=deployment,
        request=request,
        source_manifest_hash=source_manifest,
    )


def is_excluded_path(relative_path: str | Path) -> bool:
    """Apply the shared publication policy to a repository-relative path."""
    from .publication_policy import is_excluded_path as _is_excluded_path

    return _is_excluded_path(relative_path)


# ── Public pure predicates ───────────────────────────────────────────────


def _is_excluded_dir(name: str) -> bool:
    """Return ``True`` when *name* matches an excluded directory rule."""
    return _policy_excluded_dir_name(name)


# ── Source-file walking ──────────────────────────────────────────────────


def _iter_source_files(root: Path) -> Iterator[Path]:
    """Walk *root* depth-first, yielding allowed source file paths (absolute).

    Prunes excluded directories in-place (mutates ``dirnames`` so that
    ``os.walk`` does not descend into them).
    """
    yield from iter_source_files(root, extensions=ALLOWED_SOURCE_EXTENSIONS)


# ── Hashing helpers ──────────────────────────────────────────────────────


def _sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest of canonical source bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        data = f.read()
    if path.suffix.lower() in ALLOWED_SOURCE_EXTENSIONS:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    h.update(data)
    return h.hexdigest()


def compute_file_hashes(root: str | Path) -> dict[str, str]:
    """Return ``{relative_path: sha256_hex}`` for every allowed source file.

    Only files with extensions in ``ALLOWED_SOURCE_EXTENSIONS`` that pass
    the exclusion rules are included.
    """
    root_path = Path(root).resolve()
    result: dict[str, str] = {}
    for abspath in _iter_source_files(root_path):
        rel = str(abspath.relative_to(root_path)).replace("\\", "/")
        result[rel] = _sha256_file(abspath)
    return result


def compute_source_bytes(root: str | Path) -> int:
    """Return total byte count of all allowed source files under *root*."""
    root_path = Path(root).resolve()
    total = 0
    for abspath in _iter_source_files(root_path):
        try:
            total += abspath.stat().st_size
        except OSError:
            pass
    return total


def compute_aggregate_hash(file_hashes: dict[str, str]) -> str:
    """Compute a deterministic hash from ``{path: sha256_hex}``.

    Sorted by path so identical source trees always produce the same hash.
    """
    h = hashlib.sha256()
    for path in sorted(file_hashes):
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        h.update(file_hashes[path].encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _custom_node_file_hashes(
    custom_node_paths: Sequence[str | Path],
) -> dict[str, str]:
    custom_hashes: dict[str, str] = {}
    for root_index, cnp in enumerate(custom_node_paths):
        cnp_path = Path(cnp)
        if not cnp_path.is_dir():
            continue
        node_names = iter_syncable_custom_node_dirs(cnp_path)
        # A normal custom-node source root is a directory of node directories;
        # archive publication does not include unrelated files directly under
        # that root. A direct node path remains supported for existing callers.
        hash_roots = (
            [(name, cnp_path / name) for name in node_names]
            if node_names else [("", cnp_path)]
        )
        for node_name, hash_root in hash_roots:
            hashes = compute_file_hashes(hash_root)
            prefix = f"custom_node_root_{root_index}/"
            if node_name:
                prefix += f"{node_name}/"
            custom_hashes.update({
                f"{prefix}{relative}": digest
                for relative, digest in hashes.items()
            })
    return custom_hashes


def compute_custom_node_hash(custom_node_paths: Sequence[str | Path]) -> str:
    """Return the canonical S1 hash for one or more custom-node roots.

    Custom-node paths are namespaced before aggregation so equal relative
    paths from separate roots cannot overwrite one another.  This remains the
    narrower source/code identity used by deployment manifests.  Publication
    generation is intentionally separate and is owned by
    ``publication_policy.compute_publication_generation``.
    """
    custom_hashes = _custom_node_file_hashes(custom_node_paths)
    return compute_aggregate_hash(custom_hashes) if custom_hashes else ""


# ── Public builder ───────────────────────────────────────────────────────


def build_deployment_identity(
    runtime_root: str | Path,
    *,
    dependency_hash: str = "",
    custom_node_paths: Sequence[str | Path] | None = None,
) -> DeploymentIdentity:
    """Build a deterministic ``DeploymentIdentity``.

    Parameters
    ----------
    runtime_root : str or Path
        Path to the ``comfymodal_runtime/`` directory.  All allowed source
        files under this root are hashed for ``runtime_hash``.
    dependency_hash : str
        Pre-computed dependency hash (e.g. pinned ``requirements.txt``).
        Pass empty string when dependencies are unchanged.
    custom_node_paths : sequence of str or Path, optional
        One or more custom-node source directories.  Python/JS files found
        here contribute to ``custom_node_hash``.

    Returns
    -------
    DeploymentIdentity
        A frozen identity whose ``combined_hash`` changes when any source
        file changes, but is unaffected by excluded artifacts.
    """
    runtime_hashes = compute_file_hashes(runtime_root)
    runtime_bytes = compute_source_bytes(runtime_root)
    runtime_hash = compute_aggregate_hash(runtime_hashes)

    custom_hashes: dict[str, str] = {}
    custom_bytes = 0
    if custom_node_paths:
        custom_hashes = _custom_node_file_hashes(custom_node_paths)
        custom_bytes = sum(
            compute_source_bytes(Path(cnp))
            for cnp in custom_node_paths
            if Path(cnp).is_dir()
        )

    custom_node_hash = compute_aggregate_hash(custom_hashes) if custom_hashes else ""

    all_hashes = dict(runtime_hashes)
    all_hashes.update(custom_hashes)

    return DeploymentIdentity(
        schema_version=DEPLOYMENT_IDENTITY_SCHEMA_VERSION,
        runtime_hash=runtime_hash,
        dependency_hash=dependency_hash,
        custom_node_hash=custom_node_hash,
        source_bytes=runtime_bytes + custom_bytes,
        file_hashes=all_hashes,
    )
