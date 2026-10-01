"""Custom-node registry: discovered ComfyUI custom nodes + their node classes.

Scans ``<comfyui_root>/custom_nodes`` for installed custom-node directories
(repo URL + installed commit via git) and attributes each class in
``nodes.NODE_CLASS_MAPPINGS`` to either its containing custom node or the
ComfyUI core (when the class module lives inside ComfyUI itself).

Discovery never raises: git/subprocess failures yield empty strings and a
missing ``nodes`` module yields an empty core set.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from studio_store import StudioJsonStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CustomNodeRecord:
    """One installed custom-node directory."""

    name: str
    install_path: str
    repo_url: str = ""
    installed_commit: str = ""
    classes: list[str] = field(default_factory=list)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "install_path": self.install_path,
            "repo_url": self.repo_url,
            "installed_commit": self.installed_commit,
            "classes": list(self.classes),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CustomNodeRecord":
        return cls(
            name=str(data.get("name", "")),
            install_path=str(data.get("install_path", "")),
            repo_url=str(data.get("repo_url", "")),
            installed_commit=str(data.get("installed_commit", "")),
            classes=[c for c in (data.get("classes") or []) if isinstance(c, str)],
            updated_at=str(data.get("updated_at", "")),
        )


class CustomNodeRegistryStore:
    """Persistent JSON store of custom-node records (thread-safe, atomic)."""

    FILENAME = ".studio_custom_nodes.json"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = StudioJsonStore(self.root / self.FILENAME)

    def list_records(self) -> list[dict[str, Any]]:
        return self.store.read()

    def get_record(self, name: str) -> Optional[dict[str, Any]]:
        for record in self.store.read():
            if record.get("name") == name:
                return record
        return None

    def replace_records(self, records: list[Any]) -> None:
        data = [r.to_dict() if isinstance(r, CustomNodeRecord) else dict(r) for r in records]

        def _mutate(rows: list[dict]) -> None:
            rows[:] = data

        self.store.update(_mutate)

    def record_by_class(self, class_type: str) -> Optional[dict[str, Any]]:
        for record in self.store.read():
            if class_type in (record.get("classes") or []):
                return record
        return None


class CustomNodeDiscovery:
    """Discovers custom-node directories and core node classes."""

    def __init__(self, root: Optional[str | Path] = None) -> None:
        self._store = CustomNodeRegistryStore(root) if root is not None else None

    @staticmethod
    def _git(path: Path, args: list[str]) -> str:
        try:
            proc = subprocess.run(
                ["git", "-C", str(path), *args],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0:
                return (proc.stdout or "").strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def _import_nodes():
        try:
            import nodes  # type: ignore[import-not-found]

            return nodes
        except Exception:
            return None

    def discover(
        self,
        comfyui_root: str | Path,
        nodes_module: Any = None,
    ) -> tuple[list[CustomNodeRecord], set[str]]:
        """Return ``(records, core_classes)`` for *comfyui_root*.

        *records* — one ``CustomNodeRecord`` per custom-node directory with
        an ``__init__.py`` (or any ``.py``), excluding the plugin itself and
        dot/underscore directories.
        *core_classes* — ``NODE_CLASS_MAPPINGS`` classes whose module file
        lives inside ComfyUI itself (not under ``custom_nodes``).
        """
        comfyui_root = Path(comfyui_root)
        custom_nodes_dir = comfyui_root / "custom_nodes"
        records: list[CustomNodeRecord] = []
        by_path: dict[Path, CustomNodeRecord] = {}

        if custom_nodes_dir.is_dir():
            try:
                entries = sorted(custom_nodes_dir.iterdir())
            except Exception:
                entries = []
            for entry in entries:
                try:
                    if not entry.is_dir():
                        continue
                    name = entry.name
                    if not name or name.startswith(".") or name.startswith("_"):
                        continue
                    if "comfyui-modal" in name.lower():
                        continue
                    has_python = any(p.suffix == ".py" for p in entry.iterdir())
                    if not has_python:
                        continue
                    record = CustomNodeRecord(
                        name=name,
                        install_path=str(entry),
                        repo_url=self._git(entry, ["remote", "get-url", "origin"]),
                        installed_commit=self._git(entry, ["rev-parse", "HEAD"]),
                        updated_at=_now_iso(),
                    )
                    records.append(record)
                    by_path[entry.resolve()] = record
                except Exception:
                    continue

        core_classes: set[str] = set()
        try:
            nodes = nodes_module if nodes_module is not None else self._import_nodes()
            mappings = getattr(nodes, "NODE_CLASS_MAPPINGS", None)
            if mappings:
                resolved_custom_dir = custom_nodes_dir.resolve()
                resolved_comfy_root = comfyui_root.resolve()
                for class_type, cls in mappings.items():
                    module = sys.modules.get(getattr(cls, "__module__", ""))
                    file = getattr(module, "__file__", "") if module is not None else ""
                    if not file:
                        continue
                    fpath = Path(file).resolve()
                    if fpath.is_relative_to(resolved_custom_dir):
                        for candidate in (fpath.parent, *fpath.parents):
                            record = by_path.get(candidate)
                            if record is not None:
                                record.classes.append(str(class_type))
                                break
                    elif fpath.is_relative_to(resolved_comfy_root):
                        core_classes.add(str(class_type))
        except Exception:
            pass

        return records, core_classes

    def refresh(
        self, comfyui_root: str | Path, nodes_module: Any = None
    ) -> tuple[list[dict[str, Any]], set[str]]:
        """Discover and persist records; return ``(records, core_classes)``."""
        records, core = self.discover(comfyui_root, nodes_module=nodes_module)
        if self._store is not None:
            self._store.replace_records(records)
        return [r.to_dict() for r in records], core
