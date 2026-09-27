"""Shared builder for run_prompt_stream modal_options defaults.

Provides a single canonical source for ``production`` and ``actual_load``
option defaults that are forwarded to the remote ``comfyapp.run_prompt_stream``
call.  Every invocation path (normal queue, Studio direct, scheduler) uses
the same builder so defaults are consistent.
"""

from __future__ import annotations

import copy


def build_run_prompt_options(
    *,
    production_output_node_ids: list[str],
    enable_actual_load: bool = True,
) -> dict:
    """Build canonical production and actual_load option defaults.

    Parameters
    ----------
    production_output_node_ids:
        Node IDs to designate as production output nodes.  Copied
        defensively, sorted, deduplicated, and string-cast.
    enable_actual_load:
        Whether ``actual_load`` is enabled by default (default ``True``).

    Returns
    -------
    dict
        ``{"production": {"enabled": True, "output_node_ids": [...]},
            "actual_load": {"enabled": True, "mode": "unet_vae_only"}}``
    """
    seen: set[str] = set()
    normalized_ids: list[str] = []
    for raw_id in production_output_node_ids:
        sid = str(raw_id).strip()
        if sid and sid not in seen:
            seen.add(sid)
            normalized_ids.append(sid)
    # Sort numerically when all IDs are numeric, falling back to string sort
    # (mirrors production_workflow._normalize_ids behavior).
    def _sort_key(s: str):
        try:
            return (0, int(s))
        except ValueError:
            return (1, s)
    normalized_ids.sort(key=_sort_key)

    return {
        "production": {
            "enabled": True,
            "output_node_ids": normalized_ids,
        },
        "actual_load": {
            "enabled": bool(enable_actual_load),
            "mode": "unet_vae_only",
        },
    }


def ensure_run_prompt_options(
    modal_options: dict | None,
    builder_result: dict,
) -> dict:
    """Merge builder defaults into *modal_options*, preserving caller keys.

    *modal_options* may be ``None`` or an existing dict with arbitrary
    top-level keys (``runtime``, ``comfymodal_scheduler_test``, ``output_format``,
    workspace flags, etc.) that must be retained.

    *builder_result* is the dict returned by ``build_run_prompt_options()``.

    Rules
    -----
    - All top-level keys from *modal_options* are retained.
    - ``production`` is set from *builder_result* when absent.
    - ``actual_load`` is set from *builder_result* when absent.
    - An explicit ``production.enabled=False`` or ``actual_load.enabled=False``
      in *modal_options* is preserved as an intentional opt-out.
    - When ``production`` or ``actual_load`` already exist and are not
      opt-outs, builder defaults are merged underneath (caller sub-keys win).
    """
    result: dict = dict(modal_options) if modal_options else {}

    # ── Production ──────────────────────────────────────────────────────
    builder_prod = builder_result.get("production", {})
    if "production" not in result:
        result["production"] = copy.deepcopy(builder_prod)
    elif result["production"].get("enabled") is False:
        # Explicit opt-out — preserve as-is, do not touch.
        pass
    else:
        merged_prod = copy.deepcopy(builder_prod)
        existing_prod = result["production"]
        for k, v in existing_prod.items():
            if v is not None:
                merged_prod[k] = v
        result["production"] = merged_prod

    # ── Actual load ─────────────────────────────────────────────────────
    builder_al = builder_result.get("actual_load", {})
    if "actual_load" not in result:
        result["actual_load"] = copy.deepcopy(builder_al)
    elif result["actual_load"].get("enabled") is False:
        # Explicit opt-out — preserve as-is.
        pass
    else:
        merged_al = copy.deepcopy(builder_al)
        existing_al = result["actual_load"]
        for k, v in existing_al.items():
            if v is not None:
                merged_al[k] = v
        result["actual_load"] = merged_al

    return result
