"""Deterministic local custom-node source-root resolution.

This is intentionally separate from the publication/filtering policy.  A
checkout under ``.slim/worktrees/<lane>`` has a staging root owned by that
checkout; its ``.slim/worktrees`` parent is never a source-root candidate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


CUSTOM_NODES_ENV = "COMFYMODAL_LOCAL_CUSTOM_NODES"
_WORKTREE_MARKERS = (".slim", "worktrees")
_UNSAFE_ROOTS = {"/", "/root", "/home", "/mnt", "/tmp", "/usr", "/opt"}


@dataclass(frozen=True)
class CustomNodesRootResolution:
    """The selected root and auditable reason for selecting it."""

    root: str
    method: str
    candidates: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "custom_nodes_root": self.root,
            "custom_nodes_root_resolution_method": self.method,
            "custom_nodes_root_candidates": list(self.candidates),
        }


def _normalise(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser().resolve()


def looks_like_custom_nodes_root(path: str | os.PathLike[str]) -> bool:
    """Return whether *path* contains a plausible custom-node set."""
    candidate = os.fspath(path)
    if not candidate or not os.path.isdir(candidate):
        return False
    if os.path.realpath(candidate).casefold() in {
        value.casefold() for value in _UNSAFE_ROOTS
    }:
        return False
    try:
        node_like = sum(
            1
            for name in os.listdir(candidate)
            if os.path.isdir(os.path.join(candidate, name))
            and not name.startswith(".")
            and (
                os.path.isfile(os.path.join(candidate, name, "__init__.py"))
                or os.path.isfile(os.path.join(candidate, name, "requirements.txt"))
            )
        )
    except OSError:
        return False
    return node_like >= 3


def _worktree_context(anchor: Path) -> tuple[Path, str, Path] | None:
    """Return ``(checkout, lane, canonical_custom_nodes)`` for a slim lane."""
    parts = tuple(part.casefold() for part in anchor.parts)
    if len(parts) < 3 or parts[-3:-1] != _WORKTREE_MARKERS:
        return None
    lane = anchor.name
    if not lane:
        return None
    checkout = anchor
    # <custom_nodes>/comfyui-modal/.slim/worktrees/<lane>
    repo_root = checkout.parents[2]
    canonical_root = repo_root.parent
    return checkout, lane, canonical_root


def resolve_custom_nodes_root_details(
    anchor: str | Path,
    *,
    explicit: str | Path | None = None,
    fallback_roots: tuple[str | Path, ...] = (),
) -> CustomNodesRootResolution:
    """Resolve a custom-node root without treating worktree metadata as data.

    Explicit configuration wins over every inferred candidate.  In an
    isolated slim checkout, the lane-local staged root wins over the
    canonical checkout root.  Other valid candidates are an error instead of
    being selected by incidental ordering.
    """
    anchor_path = _normalise(anchor)

    configured = explicit
    if configured is None:
        configured = os.environ.get(CUSTOM_NODES_ENV)
    if configured is not None:
        configured_text = os.fspath(configured).strip()
        if not configured_text:
            source = "explicit argument" if explicit is not None else CUSTOM_NODES_ENV
            raise RuntimeError(f"{source} custom-nodes root is empty")
        candidate = _normalise(configured_text)
        if not looks_like_custom_nodes_root(candidate):
            raise RuntimeError(
                f"{CUSTOM_NODES_ENV} does not look like a custom-nodes root "
                f"(need at least 3 node-like directories): {candidate}"
            )
        return CustomNodesRootResolution(
            str(candidate),
            "explicit_configured_root",
            (str(candidate),),
        )

    context = _worktree_context(anchor_path)
    if context is not None:
        checkout, lane, canonical_root = context
        staged = checkout / ".slim" / f"{lane}-custom-nodes"
        if looks_like_custom_nodes_root(staged):
            return CustomNodesRootResolution(
                str(staged),
                "worktree_staged_root",
                (str(staged), str(canonical_root)),
            )
        inferred = [(canonical_root, "canonical_root_from_worktree")]
    else:
        inferred = [(anchor_path.parent, "canonical_checkout_parent")]

    candidates: list[tuple[Path, str]] = inferred[:]
    candidates.extend(
        (_normalise(root), "configured_fallback_root") for root in fallback_roots
    )

    valid: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for candidate, method in candidates:
        key = os.path.normcase(os.path.realpath(candidate))
        if key in seen:
            continue
        seen.add(key)
        # In particular, never accept <repo>/.slim/worktrees itself if it was
        # supplied as a fallback or encountered through a legacy caller.
        if candidate.name.casefold() == "worktrees" and candidate.parent.name.casefold() == ".slim":
            continue
        if looks_like_custom_nodes_root(candidate):
            valid.append((candidate, method))

    if len(valid) > 1:
        raise RuntimeError(
            "ambiguous custom-nodes source root; valid candidates: "
            + ", ".join(str(path) for path, _ in valid)
            + f". Set {CUSTOM_NODES_ENV} explicitly."
        )
    if valid:
        candidate, method = valid[0]
        return CustomNodesRootResolution(
            str(candidate),
            method,
            tuple(str(path) for path, _ in valid),
        )

    raise RuntimeError(
        "could not resolve custom-nodes source root from anchor "
        f"{anchor_path}; set {CUSTOM_NODES_ENV} explicitly"
    )


def resolve_custom_nodes_root(
    anchor: str | Path,
    *,
    explicit: str | Path | None = None,
    fallback_roots: tuple[str | Path, ...] = (),
) -> str:
    """Compatibility wrapper returning only the selected root path."""
    return resolve_custom_nodes_root_details(
        anchor,
        explicit=explicit,
        fallback_roots=fallback_roots,
    ).root
