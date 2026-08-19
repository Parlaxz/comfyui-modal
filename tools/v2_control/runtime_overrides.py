"""Runtime-file override inventory for the v2ctl control plane (Batch E32).

Implements design section 10 ("Runtime-File Override Policy") of
V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md:

* persistent runtime flag files (``<RUNTIME_CONFIG_DIR>/<NAME>.txt``,
  mirrored locally under ``<repo_root>/.runtime_state``) are a separate state
  channel that must not silently contaminate a benchmark;
* default benchmark policy is FORBID;
* before a performance gate v2ctl lists relevant overrides and fails when
  any are present;
* clearing is always an explicit mutation (``clear NAME`` / ``clear --all
  --confirm``).

``remote_lister`` is an injected callable that is NEVER invoked by v2ctl
itself unless the caller explicitly asks for remote overrides
(``include_remote=True``).  In this phase gate/deploy-run must NOT call it.

Python 3.11 stdlib only; no network calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import RuntimeOverrideViolation

LOG = logging.getLogger("v2ctl.runtime_overrides")

DEFAULT_RUNTIME_OVERRIDE_POLICY = "forbid"

# Reject absolute paths, path separators and parent traversal outright.
_BAD_NAME_CHARS = ("/", "\\", "..")


def _default_local_dir() -> Path:
    """<repo_root>/.runtime_state -- two levels above tools/."""
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / ".runtime_state"


def _validate_override_name(name: str) -> str:
    """Traversal guard: names must be plain stems (no / \\ ..)."""
    if not isinstance(name, str) or not name:
        raise ValueError("runtime override name must be a non-empty string")
    if any(ch in name for ch in _BAD_NAME_CHARS):
        raise ValueError(f"invalid runtime override name {name!r}: path separators and '..' are not allowed")
    return name


@dataclass
class RuntimeOverride:
    """A single runtime flag file override.

    ``source`` is ``"local_staging"`` for the local mirror directory or
    ``"remote_volume"`` for the injected remote lister result.
    """

    name: str
    value: str
    source: str  # "local_staging" | "remote_volume"


class RuntimeOverrideInventory:
    def __init__(
        self,
        *,
        local_dir: Path | None = None,
        remote_lister: Callable[[], list[RuntimeOverride]] | None = None,
    ) -> None:
        self._local_dir = Path(local_dir) if local_dir is not None else _default_local_dir()
        self._remote_lister = remote_lister

    # -- listing ------------------------------------------------------------

    def list_local(self) -> list[RuntimeOverride]:
        """Scan ``*.txt`` files under the local mirror directory.  Sort by
        name for deterministic output."""
        overrides: list[RuntimeOverride] = []
        if not self._local_dir.is_dir():
            return overrides
        for path in sorted(self._local_dir.glob("*.txt")):
            try:
                value = path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError as exc:  # pragma: no cover - defensive
                LOG.warning("cannot read runtime override %s: %s", path, exc)
                continue
            overrides.append(RuntimeOverride(name=path.stem, value=value, source="local_staging"))
        return overrides

    def list_remote(self) -> list[RuntimeOverride]:
        """Remote overrides.  Returns [] when no remote_lister is injected;
        never calls anything remotely on its own."""
        if self._remote_lister is None:
            return []
        return list(self._remote_lister())

    # -- enforcement --------------------------------------------------------

    def enforce_policy(self, policy: str, *, include_remote: bool = False) -> list[RuntimeOverride]:
        """Raise RuntimeOverrideViolation when ``policy == "forbid"`` and any
        override is present (local always; remote only when include_remote
        AND a remote lister is configured).  Never auto-deletes.

        Returns the list of present overrides when the policy is not
        ``forbid`` (e.g. ``warn``) or when nothing is present.
        """
        present: list[RuntimeOverride] = list(self.list_local())
        if include_remote and self._remote_lister is not None:
            present.extend(self.list_remote())
        present = _dedupe(present)
        if policy == "forbid" and present:
            names = ", ".join(f"{o.name}={o.value} ({o.source})" for o in present)
            raise RuntimeOverrideViolation(
                f"runtime override policy is 'forbid' but override(s) are present: {names}",
                overrides=[o.__dict__ for o in present],
            )
        return present

    # -- clearing (always explicit) -----------------------------------------

    def clear_local(self, name: str) -> bool:
        """Remove ``<local_dir>/<name>.txt``; returns True when it existed.
        Never clears remote state.  Raises ValueError on traversal-style
        names."""
        safe = _validate_override_name(name)
        path = self._local_dir / f"{safe}.txt"
        try:
            path.unlink()
            LOG.info("cleared local runtime override %s", safe)
            return True
        except FileNotFoundError:
            return False

    def clear_local_all(self, confirm: bool) -> list[str]:
        """Remove every local override file; requires ``confirm=True``.
        Returns the removed names (deterministic, sorted)."""
        if not confirm:
            raise RuntimeOverrideViolation("clearing ALL local runtime overrides requires explicit confirmation")
        removed: list[str] = []
        for override in self.list_local():
            path = self._local_dir / f"{override.name}.txt"
            try:
                path.unlink()
            except OSError as exc:  # pragma: no cover - defensive
                LOG.warning("cannot remove %s: %s", path, exc)
                continue
            removed.append(override.name)
        LOG.warning("cleared ALL local runtime overrides: %s", ", ".join(removed) or "(none)")
        return removed

    # -- doctor -------------------------------------------------------------

    def describe(self) -> dict:
        """Doctor-oriented snapshot: policy (default forbid), local overrides,
        whether a remote lister is available, and remote overrides (only when
        a lister is configured and the caller asks -- remote_lister is never
        invoked here)."""
        return {
            "policy": DEFAULT_RUNTIME_OVERRIDE_POLICY,
            "local": [o.__dict__ for o in self.list_local()],
            "remote_available": self._remote_lister is not None,
            "remote": [],
        }


def _dedupe(overrides: list[RuntimeOverride]) -> list[RuntimeOverride]:
    """Last-wins dedupe by (name, source)."""
    result: dict[tuple[str, str], RuntimeOverride] = {}
    for override in overrides:
        result[(override.name, override.source)] = override
    return list(result.values())
