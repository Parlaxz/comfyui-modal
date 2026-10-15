"""Host-side Studio-workflow injection for the isolated Ideogram4 H100 profile.

Seam: ``__init__.py`` (``_execute_job``) calls
:func:`maybe_inject_ideogram_studio_workflow` immediately before
``build_execution_plan(execution_workflow)``. When the request targets the
isolated ``ideogram4_h100_20261015`` profile (or carries the canonical
``COMFYMODAL_V2_WORKFLOW_ID``/``..._VERSION_ID`` flags), the baked-in
production default plan is replaced with the checked-in Studio record
``Ideogram 4 Comfy UI Default`` (``.studio_workflow_versions.json``,
``wv_f3baf54d8f784b64``) plus an explicit ``steps=16`` scheduler override.
Every other profile falls through with the input workflow untouched.

Fail-closed: once active, any proof gap (absent/mismatched flags, unreadable
or mismatched stored graph, conversion failure, ambiguous node identity,
missing required nodes, unexpected sampler/scheduler/CFG values, wrong
resolution or seed) raises :class:`GateError` — never a silent fallback.

No Studio runtime dependency: only the pure UI->API converter
``studio_domain.graph.ui_graph_to_api_prompt`` is reused (same pattern as
``studio_domain.services``: prefer the stored executable prompt, derive from
the UI graph only when it is missing). The remote contract is unchanged:
``canonical_execution.build_execution_plan`` and ``run_plan_stream`` are not
touched, and no torch/compile/kernel/sampler changes are made here.

Revert: delete this file and its call block in ``__init__._execute_job``.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from studio_domain.graph import (
    extract_executable_prompt,
    is_ui_workflow_format,
    ui_graph_to_api_prompt,
)
from tools.v2_control.errors import GateError

NODE_DIR = Path(__file__).resolve().parent

# ── Canonical selection (mirrors tools/v2_control/cli.py IDEOGRAM4 block) ──
PROFILE = "ideogram4_h100_20261015"
WORKFLOW_ID = "wf_81513286bb304e9f"
WORKFLOW_VERSION_ID = "wv_f3baf54d8f784b64"
WORKFLOW_NAME = "Ideogram 4 Comfy UI Default"
GRAPH_DEFAULT_STEPS = 20
REQUIRED_STEPS = 16

PROFILE_ENV = "COMFYMODAL_V2CTL_PROFILE"
WORKFLOW_ID_ENV = "COMFYMODAL_V2_WORKFLOW_ID"
WORKFLOW_VERSION_ENV = "COMFYMODAL_V2_WORKFLOW_VERSION_ID"
WORKFLOW_STEPS_ENV = "COMFYMODAL_V2_WORKFLOW_STEPS"

# ── Pinned stored-graph invariants (recorded, never modified here) ─────────
EXPECTED_SAMPLER = "euler"
EXPECTED_SCHEDULER = "Ideogram4Scheduler"
EXPECTED_CFG = 7
EXPECTED_CFG_OVERRIDE = 3
EXPECTED_CFG_START = 0.7
EXPECTED_CFG_END = 1.0
EXPECTED_GUIDER = "DualModelGuider"
EXPECTED_WIDTH = 1024
EXPECTED_HEIGHT = 1024
EXPECTED_SEED = 71584314815009
EXPECTED_UNET = "ideogram4_int8_convrot.safetensors"
EXPECTED_UNCONDITIONAL_UNET = "ideogram4_unconditional_int8_convrot.safetensors"
EXPECTED_CLIP = "qwen3vl_8b_fp8_scaled.safetensors"
EXPECTED_CLIP_TYPE = "ideogram4"
EXPECTED_VAE = "flux2-vae.safetensors"


def _env(name: str) -> str:
    return str(os.environ.get(name, "") or "").strip()


def _selection_from_request(modal_options: Any) -> dict[str, str]:
    """Request-scoped override channel (takes precedence over environment).

    Reads the namespaced ``workflow_selection`` mapping only, so no existing
    ``modal_options`` key gains a new meaning.
    """
    selection = (modal_options or {}).get("workflow_selection")
    if not isinstance(selection, dict):
        return {}
    return {
        key: str(selection.get(key, "") or "").strip()
        for key in ("profile", "workflow_id", "workflow_version_id", "workflow_steps")
    }


def _resolve_signal(modal_options: Any) -> dict[str, str]:
    requested = _selection_from_request(modal_options)
    profile = requested.get("profile") or _env(PROFILE_ENV)
    workflow_id = requested.get("workflow_id") or _env(WORKFLOW_ID_ENV)
    workflow_version_id = requested.get("workflow_version_id") or _env(WORKFLOW_VERSION_ENV)
    workflow_steps = requested.get("workflow_steps") or _env(WORKFLOW_STEPS_ENV)
    return {
        "profile": profile,
        "workflow_id": workflow_id,
        "workflow_version_id": workflow_version_id,
        "workflow_steps": workflow_steps,
    }


def injection_active(modal_options: Any = None) -> bool:
    """True only for the isolated Ideogram profile or its explicit flags."""
    signal = _resolve_signal(modal_options)
    by_profile = signal["profile"] == PROFILE
    by_flags = (
        signal["workflow_id"] == WORKFLOW_ID
        and signal["workflow_version_id"] == WORKFLOW_VERSION_ID
    )
    return bool(by_profile or by_flags)


def _load_version_record(repo_root: Path) -> dict[str, Any]:
    path = repo_root / ".studio_workflow_versions.json"
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GateError(f"cannot prove workflow selection: {path} is unreadable ({exc})")
    versions = stored if isinstance(stored, list) else []
    record = next(
        (
            item for item in versions
            if isinstance(item, dict)
            and str(item.get("workflow_version_id") or "") == WORKFLOW_VERSION_ID
        ),
        None,
    )
    if record is None:
        raise GateError(
            f"workflow version {WORKFLOW_VERSION_ID!r} is not in {path}; "
            "refusing to fall back to another workflow"
        )
    if str(record.get("workflow_id") or "") != WORKFLOW_ID:
        raise GateError(
            f"stored version {WORKFLOW_VERSION_ID!r} binds to workflow "
            f"{record.get('workflow_id')!r} != canonical {WORKFLOW_ID!r}"
        )
    return record


def _check_static_record(repo_root: Path) -> None:
    """Prove id/version binding plus the 1024x1024 + seed record proof.

    The executable prompt carries resolution through a
    ResolutionSelector->math-expression chain that cannot be evaluated
    without executing it; the checked-in static record is the numeric proof
    (node 98 ``value``/``value_1``/``noise_seed``), cross-checked here.
    """
    path = repo_root / ".studio_workflows.json"
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GateError(f"cannot prove workflow selection: {path} is unreadable ({exc})")
    entries = stored if isinstance(stored, list) else []
    entry = next(
        (
            item for item in entries
            if isinstance(item, dict) and str(item.get("workflow_id") or "") == WORKFLOW_ID
        ),
        None,
    )
    if entry is None:
        raise GateError(f"workflow {WORKFLOW_ID!r} is not in {path}")
    if str(entry.get("latest_version_id") or "") != WORKFLOW_VERSION_ID:
        raise GateError(
            f"workflow {WORKFLOW_ID!r} stored version "
            f"{entry.get('latest_version_id')!r} != requested {WORKFLOW_VERSION_ID!r}"
        )
    nodes = (entry.get("static_graph") or {}).get("nodes") or []
    node_98 = next(
        (node for node in nodes if isinstance(node, dict) and str(node.get("id")) == "98"),
        None,
    )
    if node_98 is None:
        raise GateError(f"workflow {WORKFLOW_ID!r} stored graph is missing node 98")
    named = node_98.get("widgets_values_named")
    if not isinstance(named, dict):
        raise GateError(f"workflow {WORKFLOW_ID!r} stored node 98 has no named widgets")
    if int(named.get("value", -1)) != EXPECTED_WIDTH or int(named.get("value_1", -1)) != EXPECTED_HEIGHT:
        raise GateError(
            f"workflow {WORKFLOW_ID!r} stored resolution "
            f"{named.get('value')!r}x{named.get('value_1')!r} != "
            f"{EXPECTED_WIDTH}x{EXPECTED_HEIGHT}"
        )
    if int(named.get("noise_seed", -1)) != EXPECTED_SEED:
        raise GateError(f"workflow {WORKFLOW_ID!r} stored seed mismatch")
    for key, expected in (
        ("unet_name", EXPECTED_UNET),
        ("unet_name_1", EXPECTED_UNCONDITIONAL_UNET),
        ("clip_name", EXPECTED_CLIP),
        ("vae_name", EXPECTED_VAE),
    ):
        if str(named.get(key) or "") != expected:
            raise GateError(f"workflow {WORKFLOW_ID!r} stored model {key} mismatch")


def _load_executable_prompt(record: dict[str, Any]) -> dict[str, Any]:
    """Prefer the stored executable prompt; derive from UI graph if missing.

    Mirrors ``studio_domain.services`` (UI->API derivation only when no API
    prompt is captured). Raises :class:`GateError` when no executable prompt
    can be recovered — never an empty or partial graph.
    """
    executable = extract_executable_prompt(record.get("api_prompt_json") or {})
    if executable:
        return copy.deepcopy(executable)
    graph_json = record.get("graph_json") or {}
    if is_ui_workflow_format(graph_json):
        derived = ui_graph_to_api_prompt(graph_json)
        if derived:
            return copy.deepcopy(derived)
    raise GateError(
        f"workflow {WORKFLOW_ID!r} version {WORKFLOW_VERSION_ID!r} has no "
        "executable prompt and UI->API conversion produced nothing"
    )


def _nodes_of(prompt: dict[str, Any], class_type: str) -> dict[str, dict[str, Any]]:
    return {
        node_id: node for node_id, node in prompt.items()
        if isinstance(node, dict) and str(node.get("class_type") or "") == class_type
    }


def _exactly_one(prompt: dict[str, Any], class_type: str) -> tuple[str, dict[str, Any]]:
    found = _nodes_of(prompt, class_type)
    if len(found) != 1:
        raise GateError(
            f"workflow {WORKFLOW_ID!r} expects exactly one {class_type} node; "
            f"found {len(found)} (ambiguous node identity)"
        )
    node_id = next(iter(found))
    return node_id, found[node_id]


def _validate_invariants(prompt: dict[str, Any]) -> dict[str, str]:
    """Fail closed on any graph invariant mismatch. Returns key node ids."""
    unets = _nodes_of(prompt, "UNETLoader")
    unet_names = sorted(
        str((node.get("inputs") or {}).get("unet_name") or "") for node in unets.values()
    )
    if unet_names != sorted([EXPECTED_UNET, EXPECTED_UNCONDITIONAL_UNET]):
        raise GateError(f"workflow {WORKFLOW_ID!r} UNETLoader names {unet_names!r} mismatch")

    clip_id, clip = _exactly_one(prompt, "CLIPLoader")
    clip_inputs = clip.get("inputs") or {}
    if str(clip_inputs.get("clip_name") or "") != EXPECTED_CLIP:
        raise GateError(f"workflow {WORKFLOW_ID!r} CLIPLoader clip_name mismatch")
    if str(clip_inputs.get("type") or "") != EXPECTED_CLIP_TYPE:
        raise GateError(f"workflow {WORKFLOW_ID!r} CLIPLoader type mismatch")

    _, vae = _exactly_one(prompt, "VAELoader")
    if str((vae.get("inputs") or {}).get("vae_name") or "") != EXPECTED_VAE:
        raise GateError(f"workflow {WORKFLOW_ID!r} VAELoader vae_name mismatch")

    guider_id, guider = _exactly_one(prompt, EXPECTED_GUIDER)
    if (guider.get("inputs") or {}).get("cfg") != EXPECTED_CFG:
        raise GateError(f"workflow {WORKFLOW_ID!r} {EXPECTED_GUIDER} cfg mismatch")

    _, override = _exactly_one(prompt, "CFGOverride")
    override_inputs = override.get("inputs") or {}
    if override_inputs.get("cfg") != EXPECTED_CFG_OVERRIDE:
        raise GateError(f"workflow {WORKFLOW_ID!r} CFGOverride cfg mismatch")
    if float(override_inputs.get("start_percent", -1)) != EXPECTED_CFG_START:
        raise GateError(f"workflow {WORKFLOW_ID!r} CFGOverride start_percent mismatch")
    if float(override_inputs.get("end_percent", -1)) != EXPECTED_CFG_END:
        raise GateError(f"workflow {WORKFLOW_ID!r} CFGOverride end_percent mismatch")

    sampler_id, sampler = _exactly_one(prompt, "KSamplerSelect")
    if str((sampler.get("inputs") or {}).get("sampler_name") or "") != EXPECTED_SAMPLER:
        raise GateError(f"workflow {WORKFLOW_ID!r} sampler mismatch")

    scheduler_id, scheduler = _exactly_one(prompt, EXPECTED_SCHEDULER)

    _, advanced = _exactly_one(prompt, "SamplerCustomAdvanced")
    advanced_inputs = advanced.get("inputs") or {}
    if list(advanced_inputs.get("sampler") or []) != [sampler_id, 0]:
        raise GateError(f"workflow {WORKFLOW_ID!r} SamplerCustomAdvanced sampler wiring mismatch")
    if list(advanced_inputs.get("sigmas") or []) != [scheduler_id, 0]:
        raise GateError(f"workflow {WORKFLOW_ID!r} SamplerCustomAdvanced scheduler wiring mismatch")

    _, noise = _exactly_one(prompt, "RandomNoise")
    if (noise.get("inputs") or {}).get("noise_seed") != EXPECTED_SEED:
        raise GateError(f"workflow {WORKFLOW_ID!r} seed mismatch")

    _, latent = _exactly_one(prompt, "EmptyFlux2LatentImage")
    latent_inputs = latent.get("inputs") or {}
    for dim in ("width", "height"):
        value = latent_inputs.get(dim)
        if not (isinstance(value, list) and len(value) == 2):
            raise GateError(f"workflow {WORKFLOW_ID!r} latent {dim} wiring mismatch")
    return {
        "clip": clip_id,
        "guider": guider_id,
        "sampler": sampler_id,
        "scheduler": scheduler_id,
    }


def maybe_inject_ideogram_studio_workflow(
    workflow: dict,
    *,
    modal_options: Any = None,
    repo_root: str | Path | None = None,
    trace: Any = None,
) -> tuple[dict, dict]:
    """Return ``(execution_workflow, workflow_selection)`` for the plan seam.

    Inactive requests return the input workflow object unchanged with
    ``{"active": False}``. Active requests return the validated Studio graph
    (steps overridden to 16) with steps provenance, or raise :class:`GateError`.
    """
    if not injection_active(modal_options):
        return workflow, {"active": False}
    signal = _resolve_signal(modal_options)
    if signal["workflow_id"] != WORKFLOW_ID:
        raise GateError(
            f"workflow selection {signal['workflow_id']!r} != canonical "
            f"{WORKFLOW_ID!r}; refusing to fall back to another workflow"
        )
    if signal["workflow_version_id"] != WORKFLOW_VERSION_ID:
        raise GateError(
            f"workflow selection {signal['workflow_version_id']!r} != canonical "
            f"{WORKFLOW_VERSION_ID!r}; refusing to fall back"
        )
    try:
        requested = int(str(signal["workflow_steps"] or "").strip())
    except (TypeError, ValueError):
        requested = 0
    if requested != REQUIRED_STEPS:
        raise GateError(
            f"ideogram Studio injection requires explicit "
            f"{WORKFLOW_STEPS_ENV}={REQUIRED_STEPS}; got {signal['workflow_steps']!r} "
            f"(stored graph default is {GRAPH_DEFAULT_STEPS})"
        )

    root = Path(repo_root) if repo_root is not None else NODE_DIR
    record = _load_version_record(root)
    _check_static_record(root)
    prompt = _load_executable_prompt(record)
    key_nodes = _validate_invariants(prompt)

    scheduler_id = key_nodes["scheduler"]
    scheduler_inputs = prompt[scheduler_id].get("inputs") or {}
    prompt[scheduler_id]["inputs"] = dict(scheduler_inputs, steps=REQUIRED_STEPS)
    if prompt[scheduler_id]["inputs"].get("steps") != REQUIRED_STEPS:
        raise GateError(f"workflow {WORKFLOW_ID!r} scheduler steps override failed")

    selection = {
        "active": True,
        "profile": PROFILE,
        "workflow_id": WORKFLOW_ID,
        "workflow_version_id": WORKFLOW_VERSION_ID,
        "workflow_name": WORKFLOW_NAME,
        "steps": {
            "graph_default": GRAPH_DEFAULT_STEPS,
            "requested": requested,
            "effective": REQUIRED_STEPS,
            "source": "explicit",
        },
        "scheduler_node": scheduler_id,
    }
    print(
        f"[ideogram-studio-injection] active profile={PROFILE} "
        f"workflow={WORKFLOW_ID}/{WORKFLOW_VERSION_ID} "
        f"steps graph_default={GRAPH_DEFAULT_STEPS} requested={requested} "
        f"effective={REQUIRED_STEPS} scheduler_node={scheduler_id}"
    )
    if trace is not None and hasattr(trace, "set_metadata"):
        try:
            trace.set_metadata(workflow_selection=dict(selection))
        except Exception as exc:  # telemetry only; the gate already passed
            print(f"[ideogram-studio-injection] workflow_selection trace attach failed: {exc}")
    return prompt, selection
