"""Shared builder for run_prompt_stream modal_options defaults.

Provides a single canonical source for ``production`` and ``actual_load``
option defaults that are forwarded to the remote ``comfyapp.run_prompt_stream``
call.  Every invocation path (normal queue, Studio direct, scheduler) uses
the same builder so defaults are consistent.
"""

from __future__ import annotations

import copy

from comfymodal_runtime.contracts import ExecutionOptions


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
    options = ExecutionOptions(
        production_enabled=True,
        production_output_node_ids=tuple(production_output_node_ids),
        compatibility_flags={
            "actual_load": {
                "enabled": bool(enable_actual_load),
                "mode": "unet_vae_only",
            }
        },
    )
    return options.to_legacy_dict()


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
    typed_existing = ExecutionOptions.from_legacy(modal_options, default_production=False)
    typed_builder = ExecutionOptions.from_legacy(builder_result, default_production=True)
    legacy_builder = typed_builder.to_legacy_dict()
    legacy_existing = typed_existing.to_legacy_dict()
    result: dict = dict(modal_options) if modal_options else {}

    # ── Production ──────────────────────────────────────────────────────
    builder_prod = {
        "enabled": typed_builder.production_enabled,
        "output_node_ids": list(typed_builder.production_output_node_ids),
    }
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
    builder_flags = typed_builder.compatibility_flags
    builder_al = builder_flags.get("actual_load", {}) if hasattr(builder_flags, "get") else {}
    if not builder_al:
        builder_al = legacy_builder.get("actual_load", builder_result.get("actual_load", {}))
    builder_al = dict(builder_al)
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

    if legacy_existing.get("actual_load") and "actual_load" not in result:
        result["actual_load"] = copy.deepcopy(legacy_existing["actual_load"])
    return result
