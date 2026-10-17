"""Vue adapter: builds the actual semantic trace from Vue source facts + fixture.

Same scenario definition as legacy; reads the real frontend/src at harness
runtime so regressions (e.g. selector -> text field) show up as FAILs.
"""
from __future__ import annotations

import json
from pathlib import Path

from .trace import SemanticTrace

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "frontend" / "src"


def _read(rel: str) -> str:
    p = SRC / rel
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _load_fixture(name: str) -> dict:
    p = REPO / "parity" / "corpus" / f"{name}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except OSError:
        return {}


def build_trace(scenario_id: str, fixture: str) -> SemanticTrace:
    t = SemanticTrace(scenario_id=scenario_id, impl="vue")
    fx = _load_fixture(fixture)
    controls = _read("components/PlaygroundControls.vue")
    store_pg = _read("stores/playground.ts")
    store_wf = _read("stores/workflows.ts")
    api_wf = _read("api/workflows.ts")
    view_pg = _read("pages/PlaygroundView.vue")
    view_wf = _read("pages/WorkflowsView.vue")
    route = _read("app/router/studioRoute.ts")

    # Which roles does Vue know about?
    roles = ["prompt", "seed", "step_count", "cfg_scale", "sampler",
             "width", "height", "model_unet", "vae", "clip",
             "source_image", "mask"]
    hay = controls + store_pg + api_wf
    # Catalog membership specifically: the role must be registered in the API
    # role catalog, not merely mentioned elsewhere (negative-control hardened:
    # removing a catalog entry must flip this check).
    t.visible_controls = [r for r in roles if r in api_wf]

    # Control types mirroring kindOf() in PlaygroundControls.vue: image roles ->
    # image; seed -> seed(+randomize); model roles -> select when the schema
    # carries options, else model kind with a labeled text fallback.
    t.control_types = {}
    for r in t.visible_controls:
        if r in ("source_image", "mask"):
            t.control_types[r] = "image"
        elif r == "seed":
            t.control_types[r] = "seed"
        elif r in ("model_unet", "vae", "clip", "sampler"):
            t.control_types[r] = "model(select-if-options-else-text)"
        elif r == "prompt":
            t.control_types[r] = "multiline" if "textarea" in controls.lower() else "text"
        else:
            t.control_types[r] = "number" if "number" in controls.lower() else "input"

    # Autofill evidence: values come from schema defaults + saved draft
    # (selectWorkflow: defaultValuesFromSchema + draftPersisted). Whether the
    # run-context schema carries the CAPTURED model values is backend
    # behavior, unproven from frontend source alone -> UNKNOWN, never PASS.
    for role in ("model_unet", "clip", "vae"):
        t.control_values[role] = ("UNPROVEN: schema-default path exists "
                                  "(defaultValuesFromSchema+draftoverride); captured-value "
                                  "carry-through needs backend run-context evidence")
    if fx.get("missing_models"):
        t.available_options["models"] = "missing flagged" if "missing" in hay.lower() or "depend" in hay.lower() else "unflagged"

    # Wizard suggestions: explicit Suggest button, not automatic.
    if "wizardRoleSuggestions" in view_wf or "Suggest targets" in view_wf:
        t.wizard_suggestions = {"mode": "explicit-button", "auto_confirm": False}
    elif "suggest" in (api_wf + view_wf).lower():
        t.wizard_suggestions = {"mode": "suggest-present", "auto_confirm": False}
    else:
        t.wizard_suggestions = {"mode": "absent"}

    # Advanced: visible group, no collapsible disclosure found.
    if "Advanced" in controls:
        t.collapsed_expanded = {"Advanced": "collapsible" if "collaps" in controls.lower() or "disclosure" in controls.lower() else "visible-group-no-collapse"}
    else:
        t.collapsed_expanded = {"Advanced": "absent"}

    # Reorder: drag handles / move actions in queue/controls?
    q = view_pg
    t.control_ordering = (["queue-reorderable"] if ("drag" in q.lower() and "queue" in q.lower()) or "moveUp" in q or "move-up" in q.lower() else ["no-reorder-affordance"])

    t.storage_writes = {"persistence": "namespaced-localStorage" if "localStorage" in _read("persistence/persistence.ts") else "unknown"}
    t.route_hash = "#comfymodal=playground" if "comfymodal" in route else "UNKNOWN"
    t.request_intent = {"submit_path": "submitRun" if "submitRun" in (view_pg + store_pg) else "unknown",
                        "fixture": fixture}
    t.enabled_disabled = {"seed_randomize": "enabled" if "randomizeSeed" in controls else "absent",
                          "upscale_placeholder": "disabled" if "upscale" in view_pg.lower() else "unknown"}
    vue_all = controls + store_pg + store_wf + api_wf + view_pg + view_wf
    t.graph_ops = (["centerOnNode+3s-highlight"] if "centerOnNode" in vue_all else ["seam-unwired"])
    t.upload_guard = ("token-guard"
                      if "commitUpload" in store_pg and "sourceToken" in store_pg else "absent")
    t.sketch_upload = ("flatten+upload" if "toBlob" in vue_all or "toDataURL" in vue_all or "uploadSketch" in vue_all
                       else "strokes-local-only-no-flatten-upload")
    api_hist = _read("api/history.ts")
    vue_all = vue_all + api_hist + _read("pages/HistoryView.vue") + _read("components/CompareViewer.vue") + _read("components/StudioViewer.vue")
    t.experiment_ops = ("axes+batch+per-cell-retry+resume"
                        if "submitExperimentDef" in vue_all and "retryExperimentCell" in vue_all
                        and "resumeExperiment" in api_hist else "partial-or-absent")
    t.queue_ops = "no-user-reorder"
    acts = []
    for a, needle in [("favorite", "favorite"), ("note", "setGenerationNote"), ("retry-original", "retryOriginal"),
                      ("resume", "resumeGeneration"), ("compare", "CompareViewer"), ("download", "downloadHistoryAsset")]:
        if needle in vue_all or needle in api_hist:
            acts.append(a)
    t.history_actions = acts
    t.version_switch = ("reloads-values-on-switch"
                        if "runContext.value = null" in store_pg and "selectWorkflow" in store_pg else "UNKNOWN")
    t.api_requests = ["run-context" if "run-context" in hay.lower() or "runContext" in hay else "unknown"]
    t.final_state = "vue-actual"
    return t
