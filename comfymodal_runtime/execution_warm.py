"""Advisory cache-warming helpers for the cached->first-node hot path.

Background warmers that pre-populate the two cold ComfyUI caches the
``TopologicalSort`` walk pays on the FIRST request of a container after a
memoized prompt-signature fast path skips the normal ``add_keys`` warm-up:

* ``warm_registered_folders``  → warms ``folder_paths.filename_list_cache``
  (the cold Modal-volume ``recursive_search`` each loader ``INPUT_TYPES()``
  triggers for ``*_name`` inputs).
* ``warm_classes_input_types`` → warms ``nodes.NODE_CLASS_MAPPINGS[ct].INPUT_TYPES()``
  for every distinct class type in the incoming prompt.

Both are advisory-only: if a warm is incomplete or fails, the request simply
pays the original cost later (no correctness impact — identical results, just
not pre-warmed).  **Never raise.**  Every failure is swallowed per-entry and
the functions always return a ``(count, elapsed_ms)`` tuple.

Both functions are safe to run in a daemon thread (the modal_app integration
lanes launch them exactly that way) and both are importable when ComfyUI is
absent (the test environment): the lazy ``folder_paths`` / ``nodes`` imports
are guarded, and on import failure they return ``(0, 0.0)``.
"""

from __future__ import annotations

import time
from typing import Any


def warm_registered_folders() -> tuple[int, float]:
    """Warm ``folder_paths.get_filename_list`` for every registered folder.

    Iterates the exact folders ComfyUI knows about at call time
    (``folder_paths.folder_names_and_paths`` keys) and calls
    ``get_filename_list`` once per folder — the same call the topo walk's
    ``INPUT_TYPES()`` triggers through a loader's ``*_name`` input.  Each
    call is individually guarded; a failure in one folder never stops the
    others.  Returns ``(folder_count, elapsed_ms)`` — ``(0, 0.0)`` when
    ComfyUI's ``folder_paths`` cannot be imported.
    """
    try:
        import folder_paths
    except Exception:
        return 0, 0.0
    _folder_names: tuple[str, ...] = ()
    try:
        _folder_names = tuple(folder_paths.folder_names_and_paths.keys())
    except Exception:
        _folder_names = ()
    _count = 0
    _t0 = time.perf_counter()
    for _folder_name in _folder_names:
        try:
            folder_paths.get_filename_list(_folder_name)
            _count += 1
        except Exception:
            # Advisory only: a failed folder leaves the request to pay the
            # original cold lookup cost — never raises, never aborts.
            continue
    _elapsed_ms = round((time.perf_counter() - _t0) * 1000.0, 3)
    return _count, _elapsed_ms


def warm_classes_input_types(prompt: dict[str, Any]) -> tuple[int, float]:
    """Warm ``NODE_CLASS_MAPPINGS[ct].INPUT_TYPES()`` for the prompt's classes.

    Computes the distinct ``class_type`` values present in *prompt*
    (``{node_id: {"class_type": ...}}``), resolves each through
    ``nodes.NODE_CLASS_MAPPINGS``, and calls ``INPUT_TYPES()`` once per class —
    the exact call ``TopologicalSort.get_input_info`` repeats per link during
    the topo walk.  Per-class failures are swallowed.  Returns
    ``(class_count, elapsed_ms)`` — ``(0, 0.0)`` when ComfyUI's ``nodes``
    module cannot be imported.
    """
    try:
        import nodes
    except Exception:
        return 0, 0.0
    _class_types: list[str] = []
    try:
        for _node in prompt.values():
            if isinstance(_node, dict):
                _ct = _node.get("class_type")
                if isinstance(_ct, str) and _ct and _ct not in _class_types:
                    _class_types.append(_ct)
    except Exception:
        _class_types = []
    _count = 0
    _t0 = time.perf_counter()
    # Routed through the same helper the runner uses, so a class whose schema
    # was captured before the snapshot is served from memory here too instead
    # of paying its caller-detection cost again at request time.
    from comfymodal_runtime.golden_serial import golden_input_types

    for _ct in _class_types:
        try:
            _class_def = nodes.NODE_CLASS_MAPPINGS.get(_ct)
            if _class_def is not None:
                golden_input_types(_class_def)
                _count += 1
        except Exception:
            # Advisory only: an un-mappable or raising class leaves the topo
            # walk to do its own lookup later — never raises, never aborts.
            continue
    _elapsed_ms = round((time.perf_counter() - _t0) * 1000.0, 3)
    return _count, _elapsed_ms
