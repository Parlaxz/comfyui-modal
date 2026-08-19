"""v2ctl profile loading and resolution (Batch E32, Agent A).

Profiles are TOML files under ``config/v2/profiles``.  Inheritance is a
single-parent chain (``extends`` is a plain string naming at most one
parent).  Resolution order (design §6): built-in defaults → parent profile
→ selected profile.

Python 3.11 stdlib only (tomllib).  No network, no project runtime imports.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ProfileError

_DEFAULT_PROFILES_DIR = Path("config") / "v2" / "profiles"

# Built-in base defaults applied before any profile (design §6).
_BASE_DEFAULTS: dict[str, Any] = {
    "target": {
        "app": "stable-modal-comfy-v2-restore-only-shadow",
        "class": "ModalRuntimeEntrypointV2",
        "method": "run_plan_stream",
    },
    "resources": {
        "gpu": "rtx-pro-6000",
        "cpu": 12,
        "memory_mb": 32768,
        "min_containers": 0,
        "scaledown_window": 4,
    },
    "workload": {
        "fresh_required": True,
        "conditioning_cache": "forced_miss",
        "expected_output_sha": "",
        "run_count": 10,
        "gap_seconds": 35.0,
    },
    "environment": {},
    "runtime_overrides": {"policy": "forbid"},
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass
class Profile:
    """A single parsed profile file."""

    name: str
    path: Path
    raw: dict
    extends: str | None
    owner: str | None
    target: dict
    resources: dict
    workload: dict
    environment: dict[str, str]
    runtime_overrides: dict


@dataclass
class ResolvedProfile:
    """Effective merged profile for a profile chain."""

    name: str
    owner: str | None
    target: dict
    resources: dict
    workload: dict
    environment: dict[str, str]
    runtime_overrides: dict
    chain: list[str] = field(default_factory=list)


class Profiles:
    """Loads and resolves profiles from a directory of TOML files."""

    def __init__(self, profiles_dir: Path | None = None) -> None:
        if profiles_dir is None:
            profiles_dir = _repo_root() / _DEFAULT_PROFILES_DIR
        self.profiles_dir = Path(profiles_dir)

    # -- discovery --------------------------------------------------------

    def available(self) -> list[str]:
        """Sorted profile names (``*.toml`` files without the extension)."""
        if not self.profiles_dir.is_dir():
            return []
        return sorted(p.name[:-5] for p in self.profiles_dir.glob("*.toml"))

    # -- loading ----------------------------------------------------------

    def load(self, name: str) -> Profile:
        """Load one profile; raises ProfileError on missing/invalid files.

        Cycle and >1-parent detection happen here (and are re-verified while
        resolving, since parents are loaded through the same path).
        """
        if not isinstance(name, str) or not name:
            raise ProfileError(f"profile name must be a non-empty string, got {name!r}")
        path = self.profiles_dir / f"{name}.toml"
        try:
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        except FileNotFoundError as exc:
            raise ProfileError(f"profile {name!r} not found (looked at {path})") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ProfileError(f"profile {name!r} at {path} is not valid TOML: {exc}") from exc

        if raw.get("schema_version") != 1:
            raise ProfileError(
                f"profile {name!r}: unsupported schema_version {raw.get('schema_version')!r} "
                "(expected 1)"
            )
        raw_name = raw.get("name")
        if raw_name != name:
            raise ProfileError(
                f"profile {name!r}: internal 'name' field mismatch ({raw_name!r})"
            )

        extends = _optional_string(raw.get("extends"), name, "extends")
        owner = _optional_string(raw.get("owner"), name, "owner")

        # Detect cycles while walking the chain.  Each ancestor is loaded via
        # load(), so any cycle terminates here with ProfileError.
        seen = {name}
        cursor = extends
        while cursor is not None:
            if cursor in seen:
                chain = " -> ".join(list(seen) + [cursor])
                raise ProfileError(f"profile inheritance cycle detected: {chain}")
            seen.add(cursor)
            cursor = _extends_of(self.profiles_dir, cursor)

        environment = _string_map(raw.get("environment"), name, "environment")
        runtime_overrides = _string_map(
            raw.get("runtime_overrides"), name, "runtime_overrides"
        )

        return Profile(
            name=name,
            path=path,
            raw=dict(raw),
            extends=extends,
            owner=owner,
            target=_table(raw.get("target"), name, "target"),
            resources=_table(raw.get("resources"), name, "resources"),
            workload=_table(raw.get("workload"), name, "workload"),
            environment=environment,
            runtime_overrides=runtime_overrides,
        )

    # -- resolution -------------------------------------------------------

    def resolve(self, name: str) -> ResolvedProfile:
        """Merge the chain: base defaults → parent → child.

        Raises ProfileError on missing profiles, cycles, or a non-string
        ``extends`` (>1 parent is impossible by construction: ``extends``
        must be a plain string).
        """
        child = self.load(name)

        merged: dict[str, Any] = {
            "target": dict(_BASE_DEFAULTS["target"]),
            "resources": dict(_BASE_DEFAULTS["resources"]),
            "workload": dict(_BASE_DEFAULTS["workload"]),
            "environment": dict(_BASE_DEFAULTS["environment"]),
            "runtime_overrides": dict(_BASE_DEFAULTS["runtime_overrides"]),
        }
        chain: list[str] = []

        # Walk from the root ancestor down to the child, shallow-merging each
        # layer so the child wins for both dicts and scalar values.
        ordered: list[Profile] = []
        cursor: Profile | None = child
        while cursor is not None:
            ordered.append(cursor)
            cursor = (
                self.load(cursor.extends) if cursor.extends is not None else None
            )
        for profile in reversed(ordered):
            chain.append(profile.name)
            _merge_layer(merged, profile)

        return ResolvedProfile(
            name=child.name,
            owner=child.owner if child.owner is not None else _first_owner(ordered),
            target=merged["target"],
            resources=merged["resources"],
            workload=merged["workload"],
            environment=merged["environment"],
            runtime_overrides=merged["runtime_overrides"],
            chain=chain,
        )


# -- helpers ----------------------------------------------------------------


def _optional_string(raw: object, name: str, key: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ProfileError(
            f"profile {name!r}: '{key}' must be a plain string (got {type(raw).__name__})"
        )
    return raw


def _table(raw: object, name: str, key: str) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ProfileError(f"profile {name!r}: '{key}' must be a table")
    return dict(raw)


def _string_map(raw: object, name: str, key: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ProfileError(f"profile {name!r}: '{key}' must be a table")
    result: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ProfileError(
                f"profile {name!r}: '{key}' entries must be string keys with string values "
                f"(got {k!r}={v!r})"
            )
        result[k] = v
    return result


def _extends_of(profiles_dir: Path, name: str) -> str | None:
    """Read only the ``extends`` field of a profile (for cycle detection)."""
    path = profiles_dir / f"{name}.toml"
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ProfileError(f"profile {name!r} not found (looked at {path})") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"profile {name!r} at {path} is not valid TOML: {exc}") from exc
    extends = raw.get("extends")
    if extends is None:
        return None
    if not isinstance(extends, str):
        raise ProfileError(
            f"profile {name!r}: 'extends' must be a plain string naming at most one parent "
            f"(got {extends!r})"
        )
    return extends


def _merge_layer(merged: dict[str, Any], profile: Profile) -> None:
    """Shallow-merge one profile layer on top of ``merged`` (child wins)."""
    for key in ("target", "resources", "workload"):
        merged[key].update(profile.__dict__[key])
    merged["environment"].update(profile.environment)
    merged["runtime_overrides"].update(profile.runtime_overrides)


def _first_owner(ordered: list[Profile]) -> str | None:
    """Owner of the root ancestor (or the child if none set it)."""
    for profile in reversed(ordered):
        if profile.owner is not None:
            return profile.owner
    return None
