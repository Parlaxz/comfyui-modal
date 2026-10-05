"""Single declarative configuration schema, sourced from flag_registry.toml.

``config/v2/flag_registry.toml`` is the one authority for what a V2 setting is
called, what it defaults to, and whether it reaches the container. This module
is the only reader that turns that declaration into a runtime environment
projection, so adding a runtime-facing flag no longer requires editing a
handwritten passthrough list as well.

Why this exists
---------------
``modal_app._runtime_env()`` used to be a second, handwritten allowlist of ~180
``os.environ.get(...)`` entries. It and the registry disagreed: 26 shared flags
carried different defaults, 74 emitted keys were unregistered, and 54 registered
flags were never emitted. Whichever list won decided what a deployment actually
did, which is exactly the "two authorities" failure this removes.

The registry was migrated to describe what deployments really do, so generating
from it is behaviour-preserving. ``runtime_exposed = false`` marks a setting the
host owns; those are deliberately not sent to the container.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

#: Flag-shaped environment variables this projection is allowed to emit.
FLAG_PREFIXES = ("COMFYMODAL_", "V2_")


def registry_path() -> Path:
    """Absolute path to the single configuration authority."""
    return Path(__file__).resolve().parents[1] / "config" / "v2" / "flag_registry.toml"


def load_registry(path: Path | None = None) -> list[dict[str, object]]:
    """Parse flag_registry.toml into flag records, in declaration order."""
    target = path or registry_path()
    with open(target, "rb") as handle:
        document = tomllib.load(handle)
    return [dict(entry) for entry in document.get("flag", [])]


def _runtime_exposed(flag: dict[str, object]) -> bool:
    """Whether this flag is projected into the deployed runtime environment.

    Explicit ``runtime_exposed`` wins. Otherwise a flag is projected unless it
    declares ``change_requires = "none"``, which means nothing outside the host
    acts on it.
    """
    declared = flag.get("runtime_exposed")
    if isinstance(declared, bool):
        return declared
    return str(flag.get("change_requires", "")) != "none"


def runtime_env_fields(path: Path | None = None) -> dict[str, str]:
    """Map every runtime-exposed flag name to the default to inject.

    The default is what the container receives when the host environment does
    not set the variable, so it is part of the deployment's meaning and lives
    here rather than being duplicated in a forwarding list.
    """
    projected: dict[str, str] = {}
    for flag in load_registry(path):
        name = flag.get("name")
        if not isinstance(name, str) or not name.startswith(FLAG_PREFIXES):
            continue
        if not _runtime_exposed(flag):
            continue
        default = flag.get("default", "")
        projected[name] = "" if default is None else str(default)
    return projected


def project_runtime_env(
    environ: "os._Environ[str] | dict[str, str]",
    path: Path | None = None,
) -> dict[str, str]:
    """Project the host environment through the registry schema.

    For each runtime-exposed flag: the host value if set, otherwise the
    registry default. Host-only settings are omitted entirely.
    """
    return {
        name: environ.get(name, default)
        for name, default in runtime_env_fields(path).items()
    }


def is_runtime_exposed(name: str, path: Path | None = None) -> bool:
    """Whether a named flag reaches the container."""
    return name in runtime_env_fields(path)