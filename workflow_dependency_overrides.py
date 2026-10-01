"""User-declared nonessential dependencies, keyed by workflow.

Auto-detection (a model no active node references) covers the mechanical case,
but a live node can still reference something the user does not want to fetch.
This store records those deliberate decisions so the resolver can honour them
without mutating a version: versions are immutable, and a version's captured
``model_stack`` must keep describing what the graph actually said.

Keys are resolver row keys (``"<role>|<filename>"``), so an override survives a
recapture that reorders or re-buckets the same file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from studio_store import StudioJsonStore, StudioStoreError


class DependencyOverrideStore:
    """Per-workflow set of dependency keys the user marked unnecessary.

    Rows are ``{"workflow_id": ..., "nonessential": ["<role>|<file>", ...]}``.
    Read and write both go through :class:`StudioJsonStore`, so writes are
    atomic and reads are cached on ``(mtime_ns, size)``.
    """

    FILENAME = ".studio_dependency_overrides.json"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = StudioJsonStore(self.root / self.FILENAME)

    def keys_for(self, workflow_id: str) -> set[str]:
        """Override keys recorded for *workflow_id* (empty when none/unreadable).

        An unreadable store must not invent overrides, so it degrades to "no
        overrides" rather than raising into resolution.
        """
        if not workflow_id:
            return set()
        try:
            rows = self.store.read()
        except (StudioStoreError, OSError):
            return set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("workflow_id") or "") != str(workflow_id):
                continue
            keys = row.get("nonessential")
            if not isinstance(keys, (list, tuple, set)):
                return set()
            return {str(k) for k in keys if isinstance(k, str) and k}
        return set()

    def set_keys(self, workflow_id: str, keys: set[str]) -> list[str]:
        """Replace *workflow_id*'s override set. Returns the stored keys.

        Passing an empty set removes the row, so a workflow that no longer
        overrides anything leaves no residue behind.
        """
        workflow_id = str(workflow_id or "")
        if not workflow_id:
            raise ValueError("workflow_id is required")
        wanted = sorted({str(k) for k in keys if isinstance(k, str) and k})

        def _mutate(rows: list[dict[str, Any]]) -> None:
            kept = [
                r
                for r in rows
                if not (isinstance(r, dict) and str(r.get("workflow_id") or "") == workflow_id)
            ]
            if wanted:
                kept.append({"workflow_id": workflow_id, "nonessential": wanted})
            rows[:] = kept

        self.store.update(_mutate)
        return wanted
