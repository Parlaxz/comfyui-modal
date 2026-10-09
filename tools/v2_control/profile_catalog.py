"""Read-only catalog of config-owned Golden profiles.

This module deliberately has no Modal client and no deployment side effects.
The profile and fingerprint projections are built through the same v2ctl
resolution code used by the deploy control plane; deployment readiness is
authoritative only when an immutable deployment receipt matches the complete
resolved target and resource identity.
"""

from __future__ import annotations

import dataclasses
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .config import ConfigResolver, ResolvedConfig
from .deployment_receipt import DeploymentReceipt, latest_deployment_receipt
from .errors import FlagError, GateError, ProfileError
from .fingerprints import FingerprintEngine
from .profiles import Profiles, ResolvedProfile
from .registry import FlagRegistry

GOLDEN_METHODS = frozenset({
    "run_golden_serial_stream",
    "run_golden_parallel_stream",
})


class GoldenProfileError(ValueError):
    """A requested Golden profile cannot be trusted for execution."""


@dataclass(frozen=True)
class GoldenProfile:
    name: str
    owner: str | None
    target: dict[str, str]
    resources: dict[str, Any]
    config: ResolvedConfig
    receipt: DeploymentReceipt | None = None

    @property
    def deployed(self) -> bool:
        return self.receipt is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "owner": self.owner,
            "target": dict(self.target),
            "resources": dict(self.resources),
            "deployed": self.deployed,
        }


def _repo_root(repo_root: Path | None) -> Path:
    return Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]


def _resolver(root: Path) -> ConfigResolver:
    return ConfigResolver(
        root,
        Profiles(root / "config" / "v2" / "profiles"),
        FlagRegistry(root / "config" / "v2" / "flag_registry.toml"),
    )


def _target(config: ResolvedConfig) -> dict[str, str]:
    return {
        "app": str(config.target.app),
        "class": str(config.target.class_name),
        "method": str(config.target.method),
    }


def _resources(config: ResolvedConfig) -> dict[str, Any]:
    return {
        "gpu": str(config.resources.gpu),
        "cpu": int(config.resources.cpu),
        "memory_mb": int(config.resources.memory_mb),
    }


def _receipt_resources(receipt: DeploymentReceipt) -> dict[str, Any] | None:
    """Project resource identity from the receipt without guessing defaults."""
    config = receipt.effective_config
    raw: Any = config.get("resources") if isinstance(config, Mapping) else None
    if not isinstance(raw, Mapping):
        raw = receipt.deployment_identity.get("resources")
    if not isinstance(raw, Mapping):
        return None
    try:
        return {
            "gpu": str(raw["gpu"]),
            "cpu": int(raw["cpu"]),
            "memory_mb": int(raw["memory_mb"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _destination_record(root: Path) -> dict[str, str] | None:
    """Read the config-owned Modal destination, exactly as deploy freezes it.

    ``config/v2/modal_target.toml`` is the single destination authority.  It is
    part of the config fingerprint, so readiness can only be decided when the
    catalog resolves the same destination the deploy recorded.  An absent or
    unreadable destination is a fail-closed ``None``: readiness then cannot be
    proven rather than being assumed.
    """
    target = root / "config" / "v2" / "modal_target.toml"
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    modal = raw.get("modal")
    if not isinstance(modal, Mapping):
        return None
    workspace_id = str(modal.get("workspace_id", "") or "")
    if not workspace_id:
        return None
    return {
        "workspace_id": workspace_id,
        "workspace_label": str(modal.get("workspace_label", "") or ""),
        "environment": str(modal.get("environment", "") or ""),
        "source": "config/v2/modal_target.toml",
    }


def _with_destination(root: Path, config: ResolvedConfig) -> ResolvedConfig:
    """Return *config* with the config-owned destination frozen in."""
    destination = _destination_record(root)
    if destination is None or config.modal_destination is not None:
        return config
    return dataclasses.replace(config, modal_destination=destination)


def _matching_receipt(
    root: Path,
    profile: GoldenProfile,
) -> DeploymentReceipt | None:
    """Return a receipt only when target, resources, and config identity agree."""
    try:
        raw_destination = profile.config.modal_destination
        destination = raw_destination if isinstance(raw_destination, Mapping) else {}
        found = latest_deployment_receipt(
            root,
            profile=profile.name,
            target=profile.target,
            workspace_id=str(destination.get("workspace_id") or "") or None,
        )
    except (GateError, OSError, ValueError):
        # A corrupt authority is never replaced by an older receipt.
        return None
    if found is None:
        return None
    _path, receipt = found
    if receipt.target != profile.target:
        return None
    if _receipt_resources(receipt) != profile.resources:
        return None
    expected_fp = FingerprintEngine(
        _with_destination(root, profile.config)
    ).profile_config_fingerprint()
    if receipt.profile_config_fingerprint != expected_fp:
        return None
    return receipt


def _project(
    root: Path,
    resolved: ResolvedProfile,
    config: ResolvedConfig,
) -> GoldenProfile | None:
    method = str(config.target.method).strip()
    if method not in GOLDEN_METHODS:
        return None
    profile = GoldenProfile(
        name=config.profile_name,
        owner=resolved.owner,
        target=_target(config),
        resources=_resources(config),
        config=config,
    )
    return GoldenProfile(
        name=profile.name,
        owner=profile.owner,
        target=profile.target,
        resources=profile.resources,
        config=profile.config,
        receipt=_matching_receipt(root, profile),
    )


_CATALOG_CACHE: dict[str, tuple[tuple, list]] = {}


def _catalog_signature(root: Path) -> tuple:
    """Fingerprint every input the catalog depends on.

    The expensive part is per-profile receipt resolution, and the repository
    accumulates receipts indefinitely, so this is O(receipts) on every call.
    Detects the only two ways the answer can change: a receipt being written
    (directory mtime + file count move) and a profile being edited (its file
    mtime moves).
    """
    receipts = root / ".v2ctl" / "deployments"
    try:
        r_stat = receipts.stat()
        r_count = sum(1 for _ in receipts.glob("*.json"))
        sig_receipts = (r_stat.st_mtime_ns, r_count)
    except OSError:
        sig_receipts = (0, 0)
    profiles_dir = root / "config" / "v2" / "profiles"
    count = 0
    newest = 0
    try:
        for path in profiles_dir.glob("*.toml"):
            count += 1
            try:
                newest = max(newest, path.stat().st_mtime_ns)
            except OSError:
                pass
    except OSError:
        pass
    target = root / "config" / "v2" / "modal_target.toml"
    try:
        sig_target = (target.stat().st_mtime_ns, target.stat().st_size)
    except OSError:
        sig_target = (0, 0)
    return (sig_receipts, (count, newest), sig_target)


def invalidate_catalog_cache() -> None:
    """Drop the memoised Golden profile catalog."""
    _CATALOG_CACHE.clear()


def catalog_golden_profiles(repo_root: Path | None = None) -> list[GoldenProfile]:
    """Enumerate valid Golden profile files, failing closed per file.

    Invalid TOML, broken inheritance, invalid registry data, and invalid
    resolved configurations are omitted rather than projected as runnable
    profiles.  No profile name is synthesized and no network is contacted.

    Memoised against the receipt directory and the profile directory. This is
    called synchronously on the Golden run path, where a cold catalog scan
    measured 9.4-9.7s because every one of the 29 profiles re-read the whole
    receipts directory (412 files at the time of measurement). Deploy state must
    never be stale, so the cache key is a live fingerprint of both directories
    rather than a time-based expiry.
    """
    root = _repo_root(repo_root)
    key = str(root)
    signature = _catalog_signature(root)
    cached = _CATALOG_CACHE.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]

    profiles = Profiles(root / "config" / "v2" / "profiles")
    resolver = _resolver(root)
    result: list[GoldenProfile] = []
    for name in profiles.available():
        try:
            resolved = profiles.resolve(name)
            config = _with_destination(
                root,
                resolver.resolve(profile_name=name),
            )
            projected = _project(root, resolved, config)
        except (ProfileError, FlagError, OSError, ValueError, TypeError):
            projected = None
        if projected is not None:
            result.append(projected)
    _CATALOG_CACHE[key] = (signature, result)
    return result


def resolve_golden_profile(
    name: str,
    repo_root: Path | None = None,
) -> GoldenProfile:
    """Resolve one explicitly requested, receipt-checked Golden profile."""
    if not isinstance(name, str) or not name.strip() or any(
        token in name for token in ("/", "\\", "..")
    ):
        raise GoldenProfileError("unknown Golden profile")
    root = _repo_root(repo_root)
    profiles = Profiles(root / "config" / "v2" / "profiles")
    if name not in profiles.available():
        raise GoldenProfileError(f"unknown Golden profile: {name}")
    resolver = _resolver(root)
    try:
        resolved = profiles.resolve(name)
        config = _with_destination(
            root,
            resolver.resolve(profile_name=name),
        )
    except (ProfileError, FlagError, OSError, ValueError, TypeError) as exc:
        raise GoldenProfileError(f"Golden profile {name!r} is unreadable") from exc
    projected = _project(root, resolved, config)
    if projected is None:
        raise GoldenProfileError(
            f"Golden profile {name!r} has unsupported target method "
            f"{config.target.method!r}"
        )
    if projected.receipt is None:
        raise GoldenProfileError(
            f"Golden profile {name!r} has no matching deployment receipt"
        )
    return projected


# Short aliases keep the helper convenient for callers and focused tests.
list_golden_profiles = catalog_golden_profiles
get_golden_profile = resolve_golden_profile
