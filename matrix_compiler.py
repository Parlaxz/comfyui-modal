"""Pure matrix compiler for the testing suite.

Compile an experiment spec into an ordered list of cells plus checkpoints
and a duplicate report. No I/O. Same input → same output (deterministic).

Cheap-axis nesting (outer → inner, from parent plan §6):
  Workflow → Checkpoint (model triple) → LoRA selection → Prompt → Image
  → Sampler → Scheduler → Steps → Guidance → Denoise
  → LoRA model strengths → LoRA clip strengths → Resolution → Seed

Seed is innermost. Strength axes iterate the cartesian product per LoRA.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Iterable


# ── Public types ─────────────────────────────────────────────────────────

class CompilationError(ValueError):
    pass


# Sentinel value meaning "use the workflow's existing value".
# Used in axis_values for axes not specified in the experiment spec.
# Must be JSON-serializable (string); survives json.dumps/json.loads round-trip.
WORKFLOW_OWNED = "__COMFYMODAL_WORKFLOW_OWNED__"


def is_workflow_owned(value) -> bool:
    """Return True if value is the WORKFLOW_OWNED sentinel.

    Checks both identity (is) for internal usage and equality (==) for
    values that may have survived a JSON serialization round-trip.
    """
    return value is WORKFLOW_OWNED or value == WORKFLOW_OWNED


def resolve_axis_value(axis_values: dict, key: str, fallback=None):
    """Return the resolved value for an axis, or fallback if workflow-owned.

    Never returns the WORKFLOW_OWNED sentinel to callers that expect
    an int/float/str. Instead returns *fallback* (default None) which
    signals "use the workflow's existing value."
    """
    val = axis_values.get(key, WORKFLOW_OWNED)
    if is_workflow_owned(val):
        return fallback
    return val


# Cheap-axis ordering (outer → inner). All cheap axes are listed; missing
# axes contribute a single value (None) so nesting still works.
_CHEAP_AXIS_ORDER = (
    "sampler",
    "scheduler",
    "steps",
    "guidance",
    "denoise",
    "lora_model_strengths",  # special: derived from the active LoRA
    "lora_clip_strengths",   # special: derived from the active LoRA
    "resolution",            # (width, height) — kept together as a tuple
    "seed",
)

# ── Extra axis handling ─────────────────────────────────────────────────

def _build_axis_values(*, sampler, scheduler, steps, steps_val,
                       guidance, guidance_val, denoise, denoise_val,
                       model_str, clip_str, width, width_val,
                       height, height_val, seed, seed_val,
                       extra) -> dict:
    """Build axis_values dict including any extra non-special axes."""
    result = {
        "sampler": sampler if (sampler is not None and not is_workflow_owned(sampler)) else WORKFLOW_OWNED,
        "scheduler": scheduler if (scheduler is not None and not is_workflow_owned(scheduler)) else WORKFLOW_OWNED,
        "steps": steps_val if (steps is not None and not is_workflow_owned(steps)) else WORKFLOW_OWNED,
        "guidance": guidance_val if (guidance is not None and not is_workflow_owned(guidance)) else WORKFLOW_OWNED,
        "denoise": denoise_val if (denoise is not None and not is_workflow_owned(denoise)) else WORKFLOW_OWNED,
        "lora_model_strengths": model_str,
        "lora_clip_strengths": clip_str,
        "resolution": (width_val, height_val) if (width is not None and not is_workflow_owned(width)) else WORKFLOW_OWNED,
        "seed": seed_val if (seed is not None and not is_workflow_owned(seed)) else WORKFLOW_OWNED,
    }
    if extra:
        for _ek, _ev in extra.items():
            if is_workflow_owned(_ev):
                result[_ek] = WORKFLOW_OWNED
            else:
                result[_ek] = _ev
    return result


# ── Public API ──────────────────────────────────────────────────────────

def compile_experiment(spec: dict) -> dict:
    """Compile a spec into an ordered list of cells + checkpoints + duplicate report.

    Returns a dict with keys:
        - experiment_id
        - revision
        - checkpoints: list of {id, profile_id, loader_target_group_id, triple, lora_selection_ids, cell_count}
        - cells: list of {cell_key, sequence, checkpoint_id, profile_id,
                          loader_target_group_id, triple, lora_selection_id,
                          lora_signature, prompt_id, image_id, axis_values}
        - duplicate_count: int (number of cells with a duplicate canonical key)
        - warnings: list[str]
    """
    if not isinstance(spec, dict):
        raise CompilationError("spec must be a dict")
    exp_id = spec.get("experiment_id", "")
    if not exp_id:
        raise CompilationError("experiment_id is required")
    revision = int(spec.get("revision", 1))

    workflows = spec.get("workflows", [])
    if not isinstance(workflows, list):
        raise CompilationError("workflows must be a list")
    if not workflows:
        raise CompilationError("at least one workflow is required")

    prompts_cfg = spec.get("prompts", {}) or {}
    prompts = [p for p in prompts_cfg.get("items", [])
               if isinstance(p, dict) and p.get("enabled", True)]
    shared_negative = prompts_cfg.get("shared_negative")
    images_cfg = spec.get("images", {}) or {}
    image_items = [i for i in images_cfg.get("items", [])
                   if isinstance(i, dict) and i.get("enabled", True)]
    image_mode = images_cfg.get("mode", "cartesian")
    if image_mode not in ("cartesian", "paired", "none"):
        raise CompilationError(f"invalid image mode: {image_mode!r}")

    lora_selections = [l for l in (spec.get("loras", {}) or {}).get("selections", [])
                       if isinstance(l, dict) and l.get("enabled", True)]

    shared_axes = (spec.get("axes", {}) or {}).get("shared", {}) or {}
    per_workflow_axes = (spec.get("axes", {}) or {}).get("per_workflow", {}) or {}

    # Axes that are handled internally by the compiler (not expanded generically).
    _COMPILER_INTERNAL_AXES = frozenset({
        "sampler", "scheduler", "steps", "guidance", "denoise",
        "lora_model_strengths", "lora_clip_strengths", "resolution", "seed",
        # Studio-special axes handled at the adapter level
        "prompt", "negative_prompt",
    })

    warnings: list[str] = []
    checkpoints_out: list[dict] = []
    cells_out: list[dict] = []
    sequence = 0
    seen_keys: dict[str, int] = {}  # cell_key -> first sequence
    duplicate_count = 0

    for wf in workflows:
        profile_id = wf.get("profile_id", "")
        pw_axes = per_workflow_axes.get(profile_id, {}) or {}

        # ── Resolve per-stack or flat mode ─────────────────────────────
        raw_stacks = wf.get("stacks")
        if isinstance(raw_stacks, list) and raw_stacks:
            # New per-stack path: each stack is an independent checkpoint
            # unit with its own main_triple, subprofile_triples, and
            # per-stack lora_selections.
            stack_configs = []
            for stack in raw_stacks:
                if not isinstance(stack, dict):
                    continue
                stack_lora = [l for l in (stack.get("lora_selections") or [])
                              if isinstance(l, dict) and l.get("enabled", True)]
                stack_configs.append({
                    "group_id": stack.get("loader_target_group_id", "g_default"),
                    "main_triple": stack.get("main_triple") or {},
                    "subprofiles": [s for s in (stack.get("subprofile_triples") or [])
                                    if isinstance(s, dict) and s.get("enabled", True)],
                    "selected_ids": stack.get("selected_triple_ids") or ["main"],
                    "lora_selections": stack_lora,
                })
        else:
            # Flat (legacy) mode — a single implicit stack from the
            # workflow-level fields.
            stack_configs = [{
                "group_id": wf.get("loader_target_group_id", "g_default"),
                "main_triple": wf.get("main_triple") or {},
                "subprofiles": [s for s in (wf.get("subprofile_triples") or [])
                                if isinstance(s, dict) and s.get("enabled", True)],
                "selected_ids": wf.get("selected_triple_ids") or ["main"],
                "lora_selections": lora_selections,
            }]

        for sc in stack_configs:
            group_id = sc["group_id"]
            main_triple = sc["main_triple"]
            subprofiles = sc["subprofiles"]
            selected_ids = sc["selected_ids"]
            stack_lora_selections = sc["lora_selections"]

            if not isinstance(main_triple, dict):
                raise CompilationError("main_triple must be a dict")

            triples: list[tuple[str, dict]] = []
            if "main" in selected_ids:
                triples.append(("main", {
                    "id": "main",
                    "unet": main_triple.get("unet", ""),
                    "clip": main_triple.get("clip", ""),
                    "vae": main_triple.get("vae", ""),
                }))
            for sub in subprofiles:
                sid = sub.get("id", "")
                if sid in selected_ids:
                    triples.append((sid, {
                        "id": sid,
                        "unet": sub.get("unet", ""),
                        "clip": sub.get("clip", ""),
                        "vae": sub.get("vae", ""),
                    }))

            for triple_id, triple in triples:
                ck_id = f"ck_{len(checkpoints_out) + 1:03d}"
                ck_cell_count = 0
                # Build per-checkpoint axis resolution
                axis_values_per_axis: dict[str, list] = {}
                extra_axis_names: list[str] = []
                extra_axis_value_lists: list[list] = []
                # Collect extra (non-internal) axes from shared and per-workflow.
                # Per-workflow values override shared for identical names,
                # matching standard-axis override semantics.
                _extra_axis_map: dict[str, list] = {}
                for _src_axes in (shared_axes, pw_axes):
                    for _name in _src_axes:
                        if _name in _COMPILER_INTERNAL_AXES:
                            continue
                        _extra_axis_map[_name] = _axis_values(_src_axes.get(_name))
                extra_axis_names = list(_extra_axis_map.keys())
                extra_axis_value_lists = list(_extra_axis_map.values())
                for axis_name in _CHEAP_AXIS_ORDER:
                    if axis_name == "lora_model_strengths" or axis_name == "lora_clip_strengths":
                        # handled inside LoRA loop
                        continue
                    if axis_name == "resolution":
                        # resolution is special: width × height
                        res = _resolve_resolution(shared_axes, pw_axes)
                        axis_values_per_axis[axis_name] = res
                        continue
                    # Shared first, then per-workflow override
                    if axis_name in pw_axes:
                        axis_values_per_axis[axis_name] = _axis_values(pw_axes[axis_name])
                    elif axis_name in shared_axes:
                        axis_values_per_axis[axis_name] = _axis_values(shared_axes[axis_name])
                    else:
                        axis_values_per_axis[axis_name] = [WORKFLOW_OWNED]

                for lora_sel in stack_lora_selections:
                    lora_id = lora_sel.get("id", "")
                    # Build LoRA signature for cell key
                    lora_signature = _lora_signature(lora_sel)
                    lora_strength_combos = _lora_strength_combos(lora_sel)

                    # Build prompt/image pairs
                    pairs = _build_prompt_image_pairs(prompts, image_items, image_mode, warnings, shared_negative=shared_negative)

                    for prompt_id, image_id, image_hash, prompt_text, negative in pairs:
                        for combo in lora_strength_combos:
                            model_str, clip_str = combo
                            # Walk cheap axes in fixed order
                            for sampler in axis_values_per_axis["sampler"]:
                                for scheduler in axis_values_per_axis["scheduler"]:
                                    for steps in axis_values_per_axis["steps"]:
                                        for guidance in axis_values_per_axis["guidance"]:
                                            for denoise in axis_values_per_axis["denoise"]:
                                                for _res_item in axis_values_per_axis["resolution"]:
                                                    if is_workflow_owned(_res_item):
                                                        width = WORKFLOW_OWNED
                                                        height = WORKFLOW_OWNED
                                                    else:
                                                        width, height = _res_item
                                                    for seed in axis_values_per_axis["seed"]:
                                                        if extra_axis_names and extra_axis_value_lists:
                                                            for _extra_combo in itertools.product(*extra_axis_value_lists):
                                                                _extra_av = dict(zip(extra_axis_names, _extra_combo))
                                                                sequence += 1
                                                                cell = _build_cell(
                                                                    spec=spec,
                                                                    sequence=sequence,
                                                                    ck_id=ck_id,
                                                                    profile_id=profile_id,
                                                                    group_id=group_id,
                                                                    triple_id=triple_id,
                                                                    triple=triple,
                                                                    lora_id=lora_id,
                                                                    lora_signature=lora_signature,
                                                                    model_str=model_str,
                                                                    clip_str=clip_str,
                                                                    prompt_id=prompt_id,
                                                                    prompt_text=prompt_text,
                                                                    negative=negative,
                                                                    image_id=image_id,
                                                                    image_hash=image_hash,
                                                                    sampler=sampler,
                                                                    scheduler=scheduler,
                                                                    steps=steps,
                                                                    guidance=guidance,
                                                                    denoise=denoise,
                                                                    width=width,
                                                                    height=height,
                                                                    seed=seed,
                                                                    extra_axis_values=_extra_av,
                                                                )
                                                                if cell["cell_key"] in seen_keys:
                                                                    duplicate_count += 1
                                                                else:
                                                                    seen_keys[cell["cell_key"]] = sequence
                                                                cells_out.append(cell)
                                                                ck_cell_count += 1
                                                        else:
                                                            sequence += 1
                                                            cell = _build_cell(
                                                                spec=spec,
                                                                sequence=sequence,
                                                                ck_id=ck_id,
                                                                profile_id=profile_id,
                                                                group_id=group_id,
                                                                triple_id=triple_id,
                                                                triple=triple,
                                                                lora_id=lora_id,
                                                                lora_signature=lora_signature,
                                                                model_str=model_str,
                                                                clip_str=clip_str,
                                                                prompt_id=prompt_id,
                                                                prompt_text=prompt_text,
                                                                negative=negative,
                                                                image_id=image_id,
                                                                image_hash=image_hash,
                                                                sampler=sampler,
                                                                scheduler=scheduler,
                                                                steps=steps,
                                                                guidance=guidance,
                                                                denoise=denoise,
                                                                width=width,
                                                                height=height,
                                                                seed=seed,
                                                                extra_axis_values={},
                                                            )
                                                            if cell["cell_key"] in seen_keys:
                                                                duplicate_count += 1
                                                            else:
                                                                seen_keys[cell["cell_key"]] = sequence
                                                            cells_out.append(cell)
                                                            ck_cell_count += 1

                checkpoints_out.append({
                    "id": ck_id,
                    "profile_id": profile_id,
                    "loader_target_group_id": group_id,
                    "triple": triple,
                    "lora_selection_ids": [l.get("id", "") for l in stack_lora_selections],
                    "cell_count": ck_cell_count,
                })

    return {
        "experiment_id": exp_id,
        "revision": revision,
        "checkpoints": checkpoints_out,
        "cells": cells_out,
        "duplicate_count": duplicate_count,
        "warnings": warnings,
    }


# ── Helpers ─────────────────────────────────────────────────────────────

def _axis_values(spec: dict | None) -> list:
    if not isinstance(spec, dict):
        return [None]
    mode = spec.get("mode", "list")
    if mode == "list":
        return list(spec.get("values", [None]))
    # numeric range → expand
    if mode == "range":
        start = spec.get("start", 0)
        end = spec.get("end", 0)
        step = spec.get("step", 1)
        if step == 0:
            return [start]
        if step > 0:
            seq = []
            v = start
            while v <= end + 1e-9:
                seq.append(v)
                v += step
            return seq
        else:
            seq = []
            v = start
            while v >= end - 1e-9:
                seq.append(v)
                v += step
            return seq
    return [None]


def _resolve_resolution(shared: dict, per_workflow: dict) -> list:
    # Per-workflow wins. If neither, return [WORKFLOW_OWNED] so the
    # downstream injector preserves the workflow's existing resolution.
    res = per_workflow.get("resolution") or shared.get("resolution")
    if isinstance(res, dict):
        w = res.get("width", 1024)
        h = res.get("height", 1024)
        # respect shared-across-workflows flag
        if "values" in res and isinstance(res["values"], list):
            return [tuple(v) for v in res["values"]]
        return [(int(w), int(h))]
    return [WORKFLOW_OWNED]


def _lora_signature(sel: dict) -> tuple:
    """Return the LoRA signature for cell-key hashing.

    Empty for "No LoRA". Each entry is a (file, model_strength, clip_strength)
    tuple using the FIRST strength value (or 0.0 if not set).
    """
    out = []
    for entry in sel.get("loras", []):
        if not entry.get("enabled", True):
            continue
        f = entry.get("file", "")
        ms = entry.get("model_strength", [0.0]) or [0.0]
        cs = entry.get("clip_strength", [0.0]) or [0.0]
        out.append((f, float(ms[0]) if ms else 0.0, float(cs[0]) if cs else 0.0))
    return tuple(out)


def _lora_strength_combos(sel: dict) -> list:
    """Return a list of (model_strength_list, clip_strength_list) tuples — the
    full Cartesian product across all LoRAs in the selection. Each LoRA's own
    (model_strength × clip_strength) combos are computed first, then the
    Cartesian product across LoRAs produces every combination.

    For "No LoRA" (no entries), returns [("", "")].

    Raises ValueError if an enabled LoRA has empty model_strength.
    """
    entries = [e for e in sel.get("loras", []) if e.get("enabled", True)]
    if not entries:
        return [("", "")]
    # For each LoRA, compute its own model_strength × clip_strength combos
    # using a simple cartesian product.
    per_lora_combos: list[list[tuple[float, float]]] = []
    for e in entries:
        mlist = [float(v) for v in (e.get("model_strength", []) or [])]
        clist = [float(v) for v in (e.get("clip_strength", []) or [])]
        if not mlist and not clist:
            raise CompilationError(
                f"LoRA {e.get('file', '')!r} is enabled but has both "
                f"empty model_strength and clip_strength lists. "
                f"Provide at least one strength value or disable the LoRA."
            )
        elif not mlist:
            raise CompilationError(
                f"LoRA {e.get('file', '')!r} is enabled but has empty "
                f"model_strength list"
            )
        elif not clist:
            raise CompilationError(
                f"LoRA {e.get('file', '')!r} is enabled but has empty "
                f"clip_strength list. Provide at least one clip_strength value."
            )
        combos = [(m, c) for m in mlist for c in clist]
        per_lora_combos.append(combos)

    # Full Cartesian product across all LoRAs (Issue A).
    result: list = []
    for combo in itertools.product(*per_lora_combos):
        ms = [c[0] for c in combo]
        cs = [c[1] for c in combo]
        result.append((ms, cs))
    return result


def _build_prompt_image_pairs(prompts: list, images: list, mode: str, warnings: list,
                               shared_negative: str | None = None) -> list:
    """Return a list of (prompt_id, image_id, image_hash, prompt_text, negative)
    tuples per the prompt/image mode.

    Negative resolution order (per item):
        1. Per-item ``negative`` when explicitly present (including empty string).
        2. ``shared_negative`` from the prompts config.
        3. ``None`` (which becomes WORKFLOW_OWNED in the cell builder).
    """

    def _resolve_negative(p: dict) -> str | None:
        neg = p.get("negative")
        if neg is not None:
            return neg  # non-None string (including empty "")
        if shared_negative is not None:
            return shared_negative
        return None

    if not prompts and not images:
        # t2i with no prompts/images: one logical no-op
        return [("", "", "", "", None)]
    if not images:
        return [
            (p.get("id", ""), "", "",
             p.get("text", ""), _resolve_negative(p))
            for p in prompts
        ]
    if mode == "paired":
        n = min(len(prompts), len(images))
        if len(prompts) != len(images):
            warnings.append(
                f"Paired prompt/image lists are uneven "
                f"({len(prompts)} prompts, {len(images)} images); skipping extras"
            )
        out = []
        for i in range(n):
            p = prompts[i]
            im = images[i]
            out.append((p.get("id", ""), im.get("id", ""),
                        im.get("content_hash", ""),
                        p.get("text", ""), _resolve_negative(p)))
        return out
    # cartesian (default)
    out = []
    for p in prompts:
        for im in images:
            out.append((p.get("id", ""), im.get("id", ""),
                        im.get("content_hash", ""),
                        p.get("text", ""), _resolve_negative(p)))
    return out


def _build_cell(*, spec, sequence, ck_id, profile_id, group_id, triple_id,
                triple, lora_id, lora_signature, model_str, clip_str,
                prompt_id, prompt_text, negative, image_id, image_hash,
                sampler, scheduler, steps, guidance, denoise, width, height,
                seed, extra_axis_values=None) -> dict:
    from experiment_models import canonical_hash

    # Coerce WORKFLOW_OWNED / None axes to safe defaults for the cell key.
    # The axis_values dict keeps the WORKFLOW_OWNED sentinel so the
    # downstream injector knows to preserve the workflow's value.
    steps_val = 0 if (steps is None or is_workflow_owned(steps)) else int(steps)
    guidance_val = 0.0 if (guidance is None or is_workflow_owned(guidance)) else float(guidance)
    denoise_val = 1.0 if (denoise is None or is_workflow_owned(denoise)) else float(denoise)
    width_val = 0 if (width is None or is_workflow_owned(width)) else int(width)
    height_val = 0 if (height is None or is_workflow_owned(height)) else int(height)
    seed_val = 0 if (seed is None or is_workflow_owned(seed)) else int(seed)

    # Distinguish missing negative (None → WORKFLOW_OWNED) from explicit
    # empty string ("" → keep "") so the injector preserves the workflow's
    # existing negative prompt when the spec omits the field entirely.
    if negative is None:
        neg_prompt = WORKFLOW_OWNED
    else:
        neg_prompt = negative  # may be ""

    # Resolve lora_signature into a tuple-of-tuples with concrete strengths
    # (the inner strength combo overrides the first-strength default).
    if lora_signature and model_str and clip_str:
        new_sig_list = []
        for idx, (f, _m, _c) in enumerate(lora_signature):
            m = model_str[idx] if isinstance(model_str, list) and idx < len(model_str) else (model_str if isinstance(model_str, (int, float)) else 0.0)
            c = clip_str[idx] if isinstance(clip_str, list) and idx < len(clip_str) else (clip_str if isinstance(clip_str, (int, float)) else 0.0)
            new_sig_list.append((f, float(m), float(c)))
        effective_signature = tuple(new_sig_list)
    else:
        effective_signature = lora_signature or ()

    # Build cell key hash from a plain dict (not a CellKey dataclass).
    # All axes use sentinel defaults (0, 0.0, "", etc.) when workflow-owned
    # so that two cells with the same workflow-owned values hash identically.
    extra = extra_axis_values or {}
    key_dict = {
        "experiment_id": spec.get("experiment_id", ""),
        "profile_id": profile_id,
        "loader_target_group_id": group_id,
        "unet": triple.get("unet", ""),
        "clip": triple.get("clip", ""),
        "vae": triple.get("vae", ""),
        "lora_signature": [[f, float(m), float(c)] for (f, m, c) in effective_signature],
        "prompt_text": prompt_text,
        "negative_prompt_text": "" if neg_prompt is None or is_workflow_owned(neg_prompt) else neg_prompt,
        "input_image_hash": image_hash,
        "seed": seed_val,
        "steps": steps_val,
        "guidance": guidance_val,
        "sampler": str(sampler) if (sampler is not None and not is_workflow_owned(sampler)) else "",
        "scheduler": str(scheduler) if (scheduler is not None and not is_workflow_owned(scheduler)) else "",
        "denoise": denoise_val,
        "width": width_val,
        "height": height_val,
    }
    # Include extra (non-special) axis values in the hash for determinism
    for _ek in sorted(extra.keys()):
        _ev = extra[_ek]
        if is_workflow_owned(_ev):
            key_dict[_ek] = ""
        elif isinstance(_ev, (int, float)):
            key_dict[_ek] = _ev
        else:
            key_dict[_ek] = str(_ev)
    cell_key = canonical_hash(key_dict)
    # Compute normalised dimensions (stable metadata for results grouping).
    if width is not None and not is_workflow_owned(width):
        nd_width = width_val
    else:
        nd_width = None
    if height is not None and not is_workflow_owned(height):
        nd_height = height_val
    else:
        nd_height = None

    return {
        "cell_key": cell_key,
        "sequence": sequence,
        "checkpoint_id": ck_id,
        "profile_id": profile_id,
        "loader_target_group_id": group_id,
        "triple_id": triple_id,
        "triple": triple,
        "lora_selection_id": lora_id,
        "lora_signature": [list(s) for s in effective_signature],
        "prompt": prompt_text,
        "negative_prompt": neg_prompt,
        "input_image_hash": image_hash,
        "prompt_id": prompt_id,
        "image_id": image_id,
        "image_hash": image_hash,
        "normalized_dimensions": {
            "width": nd_width,
            "height": nd_height,
            "profile_id": profile_id,
            "loader_target_group_id": group_id,
            "unet": triple.get("unet", ""),
            "clip": triple.get("clip", ""),
            "vae": triple.get("vae", ""),
            "lora_selection_id": lora_id,
            "lora_signature": [list(s) for s in effective_signature],
            "prompt_id": prompt_id,
            "image_id": image_id,
        },
        "axis_values": _build_axis_values(
            sampler=sampler, scheduler=scheduler, steps=steps, steps_val=steps_val,
            guidance=guidance, guidance_val=guidance_val,
            denoise=denoise, denoise_val=denoise_val,
            model_str=model_str, clip_str=clip_str,
            width=width, width_val=width_val,
            height=height, height_val=height_val,
            seed=seed, seed_val=seed_val,
            extra=extra,
        ),
    }